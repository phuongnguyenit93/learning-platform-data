# Header bị thiếu trên tài nguyên đã bỏ qua security chain

> **Chương:** Chẩn đoán lỗi  
> **Mô-đun:** `SPRING_SECURITY_HTTP_PROTECTION` — áp dụng các lớp phòng vệ HTTP và trình duyệt trong Spring Security, từ CSRF, CORS, security headers, CSP, HSTS đến HTTP firewall và bảo vệ session. Người học cấu hình cho Servlet lẫn Reactive, kiểm thử các kịch bản tấn công web và chẩn đoán xung đột bảo mật khi triển khai.

## 1. Tình huống: trang HTML có security headers, file JavaScript thì không

Một ứng dụng Spring Boot dùng Spring Security để bảo vệ web UI. Response từ `GET /dashboard` có các header:

~~~http
HTTP/1.1 200 OK
Content-Type: text/html
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Content-Security-Policy: default-src 'self'; object-src 'none'
~~~

Nhưng một tài nguyên được tải từ cùng host:

~~~http
GET /assets/app.8ac4e1.js HTTP/1.1
Host: app.example.com
~~~

lại nhận:

~~~http
HTTP/1.1 200 OK
Content-Type: application/javascript
Cache-Control: public, max-age=31536000, immutable
~~~

Không thấy `X-Content-Type-Options: nosniff` trên JavaScript; các tài nguyên nằm dưới `/assets/**` cũng không đi qua các filter Spring Security. Developer tìm thấy cấu hình:

~~~java
@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring()
        .requestMatchers("/assets/**");
}
~~~

**Đây có thể là nguyên nhân trực tiếp:** `web.ignoring()` khiến các request khớp pattern không được xử lý qua security filter chain thông thường, trong đó có filter viết HTTP security headers. Một request **được phép truy cập công khai** không nhất thiết phải **bỏ qua toàn bộ bộ lọc bảo mật**.

Tuy nhiên, không thể chỉ nhìn thấy một header thiếu rồi kết luận do `web.ignoring()`. CSP không được Spring Security bật mặc định, HSTS có điều kiện HTTPS, cache headers có thể được ứng dụng chủ động ghi đè, và CDN hoặc web server có thể phục vụ tài nguyên **ngoài đường đi Spring**.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt `permitAll()` với `web.ignoring()` và với một URL không khớp bất kỳ security chain nào.
2. Hiểu vai trò của `HeaderWriterFilter` (Servlet) và `HttpHeaderWriterWebFilter` (Reactive).
3. Xác định header nào là mặc định, header nào cần cấu hình, header nào chỉ có ý nghĩa trên HTTPS hoặc HTML.
4. Tìm đúng nguồn thiếu header: matcher, nhiều chains, static handler, reverse proxy/CDN, response redirect/error hoặc custom filter.
5. Sửa cấu hình Spring Security **Servlet và WebFlux** mà không mở public API, không vô hiệu CSRF, CORS và bảo vệ session.
6. Viết kiểm thử MockMvc, WebTestClient, curl và Playwright trên đường public.

## 2. “Được phép truy cập” và “không đi qua security chain” là hai việc khác nhau

Trong Spring Security, authorization quyết định ai được phép dùng tài nguyên. Security filters còn thực hiện nhiều công việc khác: viết security headers, quản lý security context, xử lý CORS/CSRF khi cần, authentication entry points, logout, session hoặc exception handling.

### Đối chiếu cốt lõi

| Cách cấu hình | Request đi qua Spring Security filters? | Authorization | Security headers của chain? |
|---|---|---|---|
| `requestMatchers("/assets/**").permitAll()` trong một chain khớp | **Có** | Cho phép mọi người | Thường có, nếu header writer được bật |
| `web.ignoring().requestMatchers("/assets/**")` (Servlet) | **Không đi qua các filter bảo mật thông thường** cho path bị ignore | Không áp rule authorization của chain | Không được Spring Security header writer bảo đảm |
| URL không khớp `securityMatcher` của bất kỳ chain nào | Không có matching security chain để áp header | Các rule của chain khác không áp dụng | Không có header writer từ chain đó |
| Web server/CDN trả file trước khi request tới Spring | Không đi qua Spring | Chính sách thuộc server/CDN | Phải do server/CDN chịu trách nhiệm |
| Một chain khớp nhưng `headers().disable()` | Có, nhưng thiếu cơ chế ghi headers tương ứng | Theo chain | Có thể thiếu do chủ ý cấu hình |

**Quy tắc dễ nhớ:** `permitAll()` bỏ rào **quyết định quyền truy cập**, không tự bỏ những security filters khác. `ignoring()` là một **bypass filter chain** trong Servlet; cần sử dụng rất thận trọng.

### Sơ đồ hai đường đi

~~~mermaid
flowchart TD
    A[GET /assets/app.js] --> B{Bị web.ignoring hoặc ngoài mọi chain?}
    B -- Có --> C[Spring Security header writer không xử lý]
    C --> D[Static handler / container / proxy trả tài nguyên]
    B -- Không --> E[Matching SecurityFilterChain]
    E --> F[HeaderWriterFilter và các filters áp dụng]
    F --> G[Authorization permitAll cho assets]
    G --> H[Static handler trả tài nguyên]
    H --> I[Response được ghi headers theo chain]
~~~

Sơ đồ mang tính khái niệm; việc các headers được ghi lúc nào phụ thuộc filter và cách response commit. Nội dung cần kiểm chứng trên **response thực tế**, đặc biệt khi có proxy hoặc caching.

## 3. Servlet: web.ignoring() thực sự bỏ qua những gì?

Một cấu hình cũ khá phổ biến:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer;

@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring()
        .requestMatchers(
            "/css/**",
            "/js/**",
            "/images/**",
            "/assets/**"
        );
}
~~~

Khi đó request tới các đường này có thể được phục vụ bình thường bởi `ResourceHttpRequestHandler` của Spring MVC hoặc static resources của servlet container, **nhưng không chạy các Spring Security filters của matching path**.

Điều này có thể làm thiếu:

- Header `X-Content-Type-Options: nosniff` mà Spring Security lẽ ra thêm.
- HSTS trên HTTPS nếu header writer Spring là nguồn ghi.
- Header `X-Frame-Options` hoặc chính sách khác khi có liên quan.
- CSP, `Referrer-Policy`, `Permissions-Policy` hoặc custom headers **nếu bạn đã cấu hình chúng trong Spring Security chain**.
- CORS processing hoặc các chức năng filter khác đã đặt **trong** Spring Security chain, nếu chúng phù hợp route bị ignore.

Không phải mọi mục trong danh sách đều phải xuất hiện trên mọi file. Ví dụ **CSP response header trên một file JS không tương đương CSP trên HTML document**; trang HTML mới là nơi chính sách tải script/style/fetch thường được áp dụng. Cần đánh giá **header cụ thể và loại tài nguyên cụ thể**.

### Một phản ví dụ nguy hiểm

~~~java
@Bean
WebSecurityCustomizer dangerousIgnoring() {
    return web -> web.ignoring()
        .requestMatchers("/api/**");
}
~~~

Nếu `/api/**` chứa endpoints cần xác thực, cấu hình này có thể bỏ qua các phòng vệ Spring Security cho toàn bộ API. **Không dùng `ignoring()` để “sửa 401”, “bỏ CSRF” hoặc cho API công khai**. Hãy chọn một `SecurityFilterChain` khớp và khai báo authorization/CSRF theo threat model.

## 4. Sửa Servlet: permitAll cho tài nguyên công khai, giữ filter chain

Thay vì bỏ qua chain cho assets, một cấu hình Spring Security Servlet minh họa:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(
                "/assets/**",
                "/css/**",
                "/js/**",
                "/images/**",
                "/favicon.ico"
            ).permitAll()
            .requestMatchers("/login", "/public/page").permitAll()
            .anyRequest().authenticated()
        );

        http.formLogin(Customizer.withDefaults());
        http.csrf(Customizer.withDefaults());
        // Không disable headers: giữ các header writers mặc định.
        return http.build();
    }
}
~~~

**Điều kiện quan trọng:** không còn một `WebSecurityCustomizer` khác đang ignore chính các assets này. `permitAll()` ở một chain **không có tác dụng** nếu request đã bị ignore trước khi chain được lựa chọn.

### Vì sao giải pháp này có ý nghĩa?

Với GET `/assets/app.js`:

1. Request khớp security chain.
2. `HeaderWriterFilter` có cơ hội áp security header writers.
3. Authorization cho phép tài nguyên mà không cần authentication.
4. Static handler phục vụ file nếu nó tồn tại.

Không cần yêu cầu login để bảo vệ headers. **Public asset vẫn có thể được tải bởi anonymous users và được áp headers từ security chain.**

### Nếu API và UI có nhiều security chains

Code trên giả định một chain web tổng quát. Ứng dụng có API chain, admin chain và web chain cần xem **chain nào thực sự match assets**, không copy một đoạn `requestMatchers().permitAll()` vào chain không bao giờ xử lý `/assets/**`.

## 5. Spring Security ghi những HTTP security headers nào?

Spring Security hỗ trợ các HTTP security headers phổ biến. Nhưng **mặc định có thể khác giữa phiên bản, stack và cấu hình**. Với một ứng dụng Servlet hiện đại dùng Spring Security defaults, nhóm tiêu biểu:

| Header | Giá trị ví dụ | Ý nghĩa | Có nên kỳ vọng trên mọi response? |
|---|---|---|---|
| `X-Content-Type-Options` | `nosniff` | Hạn chế MIME sniffing | Thường hữu ích trên JS/CSS và nhiều tài nguyên |
| `X-Frame-Options` | `DENY` | Giảm nguy cơ frame embedding của document | Có ích nhất cho response có thể render như document |
| `Cache-Control` | `no-cache, no-store, max-age=0, must-revalidate` | Hạn chế lưu phản hồi nhạy cảm | **Không áp dụng máy móc cho fingerprinted static assets** |
| `Pragma`/`Expires` | `no-cache`/`0` | Cùng nhóm cache control | Tùy header writer và response caching |
| `Strict-Transport-Security` | `max-age=31536000 ; includeSubDomains` | Yêu cầu browser tiếp tục dùng HTTPS | **Chỉ trên HTTPS** và theo chính sách HSTS |
| `X-XSS-Protection` | Thường `0` trong cấu hình hiện đại | Tắt bộ lọc XSS cũ dễ có hành vi không mong muốn | Tùy phiên bản/header writer |
| `Content-Security-Policy` | `default-src 'self'; object-src 'none'` | Ràng buộc hành vi tài nguyên và script của document | **Không mặc định bật CSP** |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Hạn chế referrer data | Cần cấu hình nếu muốn bảo đảm |
| `Permissions-Policy` | `geolocation=(), camera=()` | Hạn chế browser features | Cần cấu hình nếu muốn bảo đảm |

**Không có một bộ headers duy nhất áp cứng cho mọi response.** Ví dụ `Strict-Transport-Security` không được browser xử lý khi gửi qua HTTP; Spring Security thường chỉ thêm trên secure request. CSP cần được thiết kế cho HTML document và các response loại liên quan, không thể dùng mặc định một policy phức tạp cho mọi app.

### Vắng header không đồng nghĩa luôn bị bypass

Ví dụ:

- Không có CSP: ứng dụng có thể **chưa cấu hình CSP**.
- Không có HSTS trên HTTP local: đó có thể là **hành vi theo điều kiện HTTPS**.
- Có `Cache-Control: public, max-age=31536000, immutable` trên JS có hash trong filename: **có thể là chính sách cache hợp lệ**.
- Không có ACAO trên response same-origin: **CORS không nhất thiết phải phát header khi không có cross-origin request**.
- Không có `X-Frame-Options` trên image do CDN: cần xem image đó có thực sự được phục vụ bởi Spring hay không và nguy cơ cụ thể, thay vì suy rằng security hoàn toàn tắt.

**Chỉ kết luận missing do filter bypass khi có đối chứng path cùng header policy và xác nhận filter không chạy trên path đó.**

## 6. HeaderWriterFilter: lý do permitAll vẫn được áp headers

Trên **Servlet**, Spring Security sử dụng `HeaderWriterFilter` (trong `org.springframework.security.web.header`) để áp danh sách `HeaderWriter`.

Một flow khái niệm:

~~~text
Browser GET /assets/app.js
  -> Servlet container / proxy
  -> Spring Security FilterChainProxy
  -> SecurityFilterChain phù hợp
  -> HeaderWriterFilter / header writers
  -> Các filter authentication/CSRF/authorization khi áp dụng
  -> MVC ResourceHttpRequestHandler
  -> HTTP response + headers đã được writer áp
~~~

Authorization `permitAll()` **không dừng `HeaderWriterFilter`**. Nếu chỉ thay `authenticated()` thành `permitAll()` trên assets, header writer vẫn có cơ hội ghi header.

### Header writers có thể không ghi đè cache policy do ứng dụng đã đặt

Trong một số cấu hình, Spring Security cache-control writer không ghi đè `Cache-Control` đã có. Với static resources có filename được fingerprint, ResourceHandler/CDN có thể cố ý cấp:

~~~http
Cache-Control: public, max-age=31536000, immutable
~~~

Đừng đổi tất cả assets sang `no-store` chỉ để thấy chính xác một header trong scanner. **Header security và header caching có thể có mục tiêu khác nhau**: cache tốt cho asset bất biến, trong khi HTML/session/CSRF response thường cần chính sách cache riêng.

## 7. Những header cần chú ý trên HTML, JavaScript và tài nguyên khác

| Loại response | Header đáng kiểm tra | Ghi chú |
|---|---|---|
| HTML page | CSP, X-Frame-Options hoặc CSP `frame-ancestors`, Referrer-Policy, HSTS qua HTTPS | Đánh giá chính sách trên **document** |
| JavaScript bundle | `X-Content-Type-Options: nosniff`, Content-Type JS phù hợp, cache policy phù hợp | Không cần copy CSP của HTML vào JS để HTML được bảo vệ |
| CSS bundle | `nosniff`, Content-Type CSS, cache cho fingerprint assets | CSP `style-src` thường được quyết định bởi HTML |
| Images/fonts | Content-Type, cache, CORS/CORP khi có dùng cross-origin | Tùy loại resource và browser context |
| JSON API | `nosniff`, Content-Type, cache/no-store nếu nhạy cảm, CORS nếu browser cross-origin | Không nhầm CORS với header security mặc định |
| Trang login/logout/CSRF bootstrap | Cache hạn chế, CSP phù hợp, framing/referrer policy, HSTS trên HTTPS | Có state và dữ liệu nhạy cảm |
| Redirect/error page | HSTS/headers phù hợp và CORS khi API yêu cầu | Response có thể sinh trước controller |

**CSP trên HTML khác CSP trên file .js.** Chính sách `script-src` của document điều khiển script được tải/chạy; đặt `Content-Security-Policy` trên script file riêng không tự thay thế CSP của HTML document.

## 8. HSTS có điều kiện HTTPS: không thấy trên HTTP chưa chắc là lỗi chain

HSTS là một trường hợp rất dễ bị hiểu sai khi đánh giá scanner:

~~~http
GET http://localhost:8080/assets/app.js
~~~

Không nên kỳ vọng `Strict-Transport-Security` từ một URL HTTP local. Với HTTPS:

~~~http
GET https://app.example.com/assets/app.js

HTTP/1.1 200 OK
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

Trong một hệ thống đúng, HSTS có thể được phát tại CDN/reverse proxy thay vì Spring. Điều quan trọng là **browser nhận header HSTS trên HTTPS public**, và chính sách domain/subdomains đã được review.

### Khi Spring nằm sau proxy kết thúc TLS

~~~text
Browser HTTPS
  -> Reverse proxy terminate TLS
  -> HTTP upstream Spring Boot
~~~

Nếu Spring nhìn request như HTTP và không được cấu hình forwarded headers **từ proxy đáng tin**, header HSTS của Spring có thể không được áp như mong đợi. Dù assets đi qua security chain, HSTS vẫn có thể thiếu.

**Đừng tự đặt `X-Forwarded-Proto: https` từ client** để ép HSTS. Phải kiểm soát trust boundary: proxy làm sạch forwarded headers do client cung cấp và tạo giá trị chính xác. Nếu edge sở hữu HSTS, test trên response public; không bắt origin HTTP nội bộ tự thể hiện như HTTPS một cách mù quáng.

### Đừng copy includeSubDomains/preload khi chưa đánh giá

`includeSubDomains` và HSTS preload có thể ảnh hưởng các subdomain chưa sẵn sàng HTTPS. Chúng là quyết định triển khai ở cấp host/domain, không phải cách sửa từng file JS thiếu header.

## 9. Những đường đi không tới Spring Security dù không có web.ignoring()

Giả sử API được chạy sau CDN và reverse proxy:

~~~mermaid
flowchart LR
    B[Browser] --> E[CDN/edge]
    E --> P[Reverse proxy]
    P --> S[Spring Security]
    S --> M[Spring MVC/WebFlux]
    E --> C[Cached static asset]
    P --> F[File hệ thống do nginx phục vụ]
~~~

Một file `/assets/app.js` có thể được trả bởi:

1. **Spring MVC ResourceHttpRequestHandler** — request có thể đi qua Servlet filter chain nếu không bị ignore.
2. **Servlet container default servlet** — có thể đi qua một phần filters hoặc không, tùy mapping và dispatch.
3. **Spring WebFlux resource handler** — đi qua WebFilters nếu request được router chuyển vào stack tương ứng.
4. **Nginx/Apache static file location** — Spring hoàn toàn không nhận request.
5. **CDN cache hit** — Spring không xử lý request lần này, headers phụ thuộc cached response và edge policies.
6. **Object storage/static hosting** — tài nguyên được host ngoài Spring, Spring headers không liên quan.

Vì vậy một `SecurityFilterChain` hoàn hảo cũng không thể thêm header vào file đang được nginx hoặc CDN phục vụ **mà không đi qua Spring**.

### Câu hỏi định vị đầu tiên

**GET /assets/app.js có xuất hiện trong origin Spring access log không?** Nếu không, hãy theo đường CDN/proxy/static server trước. Nếu có, tiếp tục tìm selected security chain và header writer.

## 10. Servlet nhiều SecurityFilterChain: tài nguyên khớp chain nào?

Không cần dùng `web.ignoring()` vẫn có thể xảy ra trường hợp **không có security chain nào match** một path. Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**");
    http.authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated()
    );
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain adminChain(HttpSecurity http) throws Exception {
    http.securityMatcher("/admin/**");
    http.authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated()
    );
    return http.build();
}
~~~

Trong ví dụ này, `/assets/**` không khớp `/api/**` hay `/admin/**`. Nếu **không có chain fallback**, tài nguyên ấy không nhận HTTP security headers **từ hai security chains trên**, dù không xuất hiện `web.ignoring()`.

### Bổ sung fallback chain có mục đích

~~~java
import org.springframework.security.config.Customizer;

@Bean
@Order(3)
SecurityFilterChain webFallback(HttpSecurity http) throws Exception {
    // Không khai báo securityMatcher -> áp dụng cho các request
    // chưa được chain có thứ tự cao hơn match.
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/assets/**", "/css/**", "/images/**")
            .permitAll()
        .requestMatchers("/login", "/public/page").permitAll()
        .anyRequest().authenticated()
    );
    http.formLogin(Customizer.withDefaults());
    return http.build();
}
~~~

**Lưu ý:** fallback chain phải giữ chính sách authentication, CSRF, headers và các quy tắc phù hợp. Không tạo một fallback `anyRequest().permitAll()` để “cho assets đi qua” vì nó có thể vô tình mở các endpoints chưa được gán vào chain khác.

### Quy tắc first-match

Spring Security chọn **security chain đầu tiên phù hợp**, không cộng dồn toàn bộ headers của các chains. Nếu API chain áp `securityMatcher("/api/**")` nhưng `/api/assets/**` thực ra chứa tài nguyên tĩnh, path đó có thể vào API chain thay vì fallback; muốn biết headers, phải xem chính sách của **chain được chọn**.

Các điểm cần kiểm tra:

1. Thứ tự `@Order`.
2. Phạm vi `securityMatcher`.
3. Authorization `requestMatchers` **bên trong** chain.
4. Header writer có bật/được tùy biến trong chain đó không.
5. Có `web.ignoring()` hoặc filter registration bypass ở tầng cao hơn không.

**Phân biệt:** `securityMatcher()` chọn chain xử lý request; `requestMatchers().permitAll()` chọn **quyết định authorization khi chain đã được chọn**. Nhầm hai tầng matcher sẽ dẫn tới chẩn đoán sai.

## 11. Đặt chính sách headers khác nhau theo từng chain một cách có chủ đích

Một số hệ thống cần CSP khác giữa trang quản trị, web app và API. Có thể cấu hình trên **chain phù hợp**, nhưng phải bảo đảm assets không nằm ngoài toàn bộ các chains:

~~~java
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
SecurityFilterChain siteChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/assets/**", "/favicon.ico").permitAll()
        .requestMatchers("/", "/login", "/public/page").permitAll()
        .anyRequest().authenticated()
    );

    http.headers(headers -> headers
        .contentSecurityPolicy(csp -> csp
            .policyDirectives(
                "default-src 'self'; " +
                "object-src 'none'; " +
                "base-uri 'self'; " +
                "frame-ancestors 'none'"
            )
        )
    );
    http.formLogin(Customizer.withDefaults());
    return http.build();
}
~~~

Ví dụ **chỉ có ý nghĩa khi chain này thực sự match route**, không bị một catch-all chain ưu tiên cao hơn xử lý, và không có WebSecurityCustomizer ignore assets. Trong ứng dụng thực, CSP cần xét nguồn script/style/fonts/connect, nonce hoặc hash theo frontend. Cấu hình này chỉ minh họa cách **header writer được gắn vào chain**, không bảo đảm mọi SPA có thể chạy nguyên trạng với CSP đã cho.

### Không chép CSP vào file JS để “sửa CSP trên trang”

Đối với HTML document, CSP thông thường được lấy từ response của **HTML**, giúp browser quyết định script, style và connection nào được phép. Một request `GET /assets/app.js` có thể không cần CSP header giống HTML, nhưng vẫn có thể cần `nosniff` và MIME type chuẩn.

**Vì vậy bài toán chẩn đoán có hai lớp:**

- Asset có đi qua security chain không, và những headers nào lẽ ra writer phải cấp?
- Header đó có **ý nghĩa bảo vệ** ở chính loại response đó không?

Đừng lấy yêu cầu “mọi file phải có cùng bộ headers” thay cho thiết kế security controls phù hợp.

## 12. Header configuration bị disable trên một chain

Nếu developer cấu hình:

~~~java
http.headers(headers -> headers.disable());
~~~

thì những HTTP security headers từ Spring Security sẽ bị vô hiệu hóa trên chain ấy. Request **vẫn đi qua** authentication/authorization/CSRF filters tùy cấu hình, nhưng header writer mặc định không còn thực thi.

Đây là nguyên nhân hoàn toàn khác với `web.ignoring()`:

| Tình huống | Có matching chain? | HeaderWriterFilter/headers | Authorization/CSRF |
|---|---|---|---|
| `web.ignoring()` | Request bị đưa ra ngoài normal security filter chains | Bị bỏ qua | Bị bỏ qua |
| Không có matching chain | Không | Không áp dụng | Không áp dụng từ chain |
| `headers().disable()` | Có | Bị disable | Có thể vẫn hoạt động |
| `permitAll()` | Có | Vẫn có thể hoạt động | Authorization công khai; các filters khác vẫn chạy |

Đừng “sửa” bằng cách xóa tất cả security configuration rồi dựa vào proxy headers không có hợp đồng rõ ràng. Nếu thực sự cần một proxy sở hữu headers, ghi rõ cấu hình, các routes, HTTPS và cách test public responses; Spring Security headers có thể được bật lại có chọn lọc.

### Cũng cần tìm cấu hình writer cụ thể bị tắt

Ví dụ `frameOptions(frame -> frame.disable())` chỉ ảnh hưởng header liên quan framing, không chứng minh toàn bộ security chain bị bypass. Khi thiếu **một header duy nhất**, kiểm tra cấu hình của **chính header đó** và default version trước khi tìm `ignoring()`.

## 13. Spring Boot mặc định không bảo đảm một fallback chain trong mọi cấu hình

Khi ứng dụng Spring Boot có Spring Security dependency nhưng developer **tự khai báo các `SecurityFilterChain` beans**, phần auto-configuration bảo mật mặc định có thể thay đổi hoặc không còn cung cấp catch-all chain như trước.

Ví dụ một API bean chỉ bảo vệ `/api/**` không có nghĩa Spring Boot sẽ tự tạo thêm chain web cho mọi path.

**Cách kiểm tra đáng tin:**

- Tìm các bean `SecurityFilterChain` đã được khởi tạo trong ứng dụng.
- Xem `securityMatcher` và `@Order`.
- Bật log chain selection có kiểm soát.
- Test trực tiếp GET tài nguyên ngoài API chain.
- Không suy từ việc “Spring Boot có dependency security” rằng mọi response đều có security headers.

**Chưa có matching chain không đồng nghĩa application hoàn toàn không có filters ngoài Spring Security.** Servlet container, reverse proxy hoặc custom filters có thể vẫn thêm headers riêng; chỉ có thể kết luận **Spring Security header writers từ chain không được áp**.

## 14. Spring Security Reactive/WebFlux: không áp dụng WebSecurityCustomizer Servlet

WebFlux không sử dụng Servlet `HttpServletRequest`, `HttpSecurity` hay `WebSecurityCustomizer` theo cách Servlet. Nó dùng:

- `SecurityWebFilterChain` và `ServerHttpSecurity`.
- `WebFilterChainProxy` để xử lý các security web filters theo matcher.
- `HttpHeaderWriterWebFilter` cho HTTP response security headers.
- `ServerWebExchangeMatcher` để chọn Reactive security chain.
- `WebSession` và các thành phần reactive cho session.

Nếu một WebFlux application chỉ khai báo một chain cho `/api/**`, assets `/assets/**` có thể **không khớp bất kỳ security chain nào**. Khi đó WebFlux resource handler vẫn trả file, nhưng security header writer trong API chain không xử lý file ấy.

### Ví dụ chain chỉ áp dụng cho API

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Bean
@Order(1)
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    http.securityMatcher(ServerWebExchangeMatchers.pathMatchers("/api/**"));
    http.authorizeExchange(auth -> auth
        .anyExchange().authenticated()
    );
    http.httpBasic(Customizer.withDefaults());
    return http.build();
}
~~~

Code chỉ áp dụng cho `/api/**`; **không tự bảo vệ `/assets/**` bằng headers**. Nếu không có fallback chain, hãy bổ sung một chain đúng chức năng, không sao chép `WebSecurityCustomizer` từ Servlet vào Reactive code.

## 15. WebFlux fallback: permitAll assets nhưng vẫn qua security filters

Một ví dụ bổ sung:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Bean
@Order(2)
SecurityWebFilterChain webFallback(ServerHttpSecurity http) {
    // Không giới hạn securityMatcher: fallback match các route còn lại.
    http.authorizeExchange(auth -> auth
        .pathMatchers("/assets/**", "/css/**", "/images/**")
            .permitAll()
        .pathMatchers("/", "/login", "/public/page").permitAll()
        .anyExchange().authenticated()
    );
    http.formLogin(Customizer.withDefaults());
    http.csrf(Customizer.withDefaults());
    return http.build();
}
~~~

Khi `GET /assets/app.js` đi vào fallback chain, `HttpHeaderWriterWebFilter` có thể áp security headers của chain, trong khi authorization vẫn cho anonymous tải file. Các headers được cấu hình trên **Reactive chain**, không phải Servlet `HeaderWriterFilter`.

### Nếu cần CSP trên WebFlux HTML

~~~java
http.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp
        .policyDirectives(
            "default-src 'self'; object-src 'none'; base-uri 'self'"
        )
    )
);
~~~

Đây là ví dụ cú pháp Spring Security WebFlux phù hợp với các phiên bản có cấu hình `contentSecurityPolicy` theo lambda DSL. Hãy đối chiếu API/version thực tế và kiểm thử response HTML. **CSP không được tự phát chỉ vì bạn dùng WebFlux hoặc `permitAll()`**.

### Đừng suy mọi response Reactive đều đi qua fallback

Nếu Spring Cloud Gateway hoặc một static server trả file **trước WebFlux handler**, security WebFilters trong ứng dụng API không có cơ hội ghi header. Cần kiểm tra request thật có đi vào ứng dụng hay không.

## 16. CORS và static resources: một trường hợp khác của filter bypass

Nếu assets được dùng từ frontend origin khác, CORS có thể liên quan đến việc browser đọc tài nguyên hoặc dùng font/canvas/API theo quy tắc riêng. Việc ignore assets khỏi Spring Security có thể đồng thời bỏ qua **CORS processing được cấu hình bên trong chain**.

Ví dụ:

~~~http
GET /assets/font.woff2 HTTP/1.1
Origin: https://frontend.example.com
~~~

Nếu yêu cầu CORS cho font và chỉ có Spring Security chain quản lý CORS, một request bị ignore có thể không nhận `Access-Control-Allow-Origin` thích hợp.

**Nhưng không phải mọi image/script tải từ origin khác đều cần CORS theo cùng cách**. Việc browser cho phép nhúng tài nguyên, đọc nội dung tài nguyên và gửi request credentials là những hành vi khác nhau. Hãy test **đúng loại tài nguyên và cơ chế browser thực sử dụng**.

### Preflight không nhất thiết xảy ra

GET một JS bundle thông thường có thể không có OPTIONS preflight, dù response headers bị thiếu. Không thấy OPTIONS **không chứng minh CORS config đã được áp** hay assets đã đi qua chain. Kiểm tra request/response thực của chính tài nguyên.

## 17. Authentication, CSRF và headers cần được chẩn đoán riêng

Một form submit POST có thể bị 403 vì CSRF hoặc authorization; một JS bundle GET bị thiếu `nosniff` có thể vẫn trả 200 và tải được. Đây là những vấn đề khác nhau:

| Quan sát | Kiểm tra trước |
|---|---|
| Public JS 200 nhưng thiếu `nosniff` | Có matching chain/header writer hoặc do CDN phục vụ? |
| HTML authenticated thiếu CSP | CSP đã được cấu hình trên chain HTML chưa? |
| POST 403 sau login | CSRF token/session/auth; không mặc định do headers thiếu |
| OPTIONS preflight 401 | CORS trước authentication, đúng chain/proxy? |
| API 401 nhưng thiếu ACAO | CORS error response path và filter order |
| HTTP 400 `RequestRejectedException` | Servlet HTTP firewall/URL normalization |
| HTTPS document không có HSTS | Header writer/HSTS config, proxy/TLS, secure request? |
| Asset có cache public lâu | Filename immutable/caching có chủ ý hay lộ data? |

Không bỏ CSRF để “làm assets chạy”, cũng không dùng `web.ignoring()` như giải pháp cho CORS hoặc authentication. Nếu tài nguyên cần công khai, ưu tiên **một matching chain với `permitAll()`** để giữ các lớp bảo vệ phù hợp.

## 18. DevTools: xác nhận response asset đang được phục vụ từ đâu

Trong browser DevTools → Network, chọn đúng tài nguyên bị nghi thiếu header. Ghi:

| Thông tin | Câu hỏi |
|---|---|
| Request URL | Là URL public của Spring, CDN hay host static riêng? |
| Scheme và hostname | HTTPS hay HTTP, có redirect hoặc host chuyển đổi không? |
| HTTP method và status | GET thật trả 200, 304 từ cache, 302 redirect, 404 hay 403? |
| Response Headers | Chính xác header nào thiếu, header nào có? |
| `Content-Type` | Có phù hợp với .js/.css/.html không? |
| `Cache-Control`/`Age`/cache status | Có phải response từ CDN/browser cache? |
| Response source/remote address | Edge, service worker, proxy hay origin? |
| Initiator/document URL | Asset được nhúng từ trang HTML nào? |
| Security header trên **HTML document** | CSP/HSTS/framing policy của trang có được áp không? |

**Không lấy headers của HTML áp đặt cho request JS mà không xét ngữ nghĩa.** Với CSP, thường phải quan sát response HTML. Với `nosniff` hoặc MIME type JS, quan sát chính response JS.

### Cache có thể che nguồn header thật

Nếu tài nguyên được phục vụ từ memory cache, disk cache hoặc service worker, một thay đổi ở Spring origin có thể chưa xuất hiện trong response mà browser sử dụng.

Để tạo đối chứng:

1. Mở browser context mới hoặc kiểm soát cache trong DevTools.
2. Gọi lại chính URL public, tránh query cache-busting bừa bãi cho asset fingerprint có chính sách riêng.
3. Kiểm tra status và cache source, không chỉ một dòng header.
4. Đối chiếu với curl hoặc integration test theo cùng URL và TLS.

Một `304 Not Modified` không có toàn bộ body/headers giống response 200 vì HTTP cache sẽ kết hợp metadata theo quy tắc caching. Đừng đánh giá thiếu header chỉ từ một response 304; cần xem **representation thực sự được browser dùng** và header policy trên lần 200/updated response.

## 19. Curl: lấy đúng response GET và so các paths

Ví dụ với môi trường staging/production được phép:

~~~bash
curl -i 'https://app.example.com/'
curl -i 'https://app.example.com/assets/app.8ac4e1.js'
curl -i 'https://app.example.com/login'
~~~

Tìm:

~~~http
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Strict-Transport-Security: max-age=...
Content-Security-Policy: ...
Cache-Control: ...
~~~

**Không sử dụng `curl -I` làm phép thử duy nhất.** `-I` gửi HEAD, trong khi application filter matcher, static handler, proxy hoặc CDN có thể xử lý HEAD khác GET. Hãy đo **GET thực tế** đang lỗi, rồi thêm HEAD như phép kiểm tra phụ nếu cần.

### So origin và public path

Trong hệ thống có proxy:

~~~text
Public URL: https://app.example.com/assets/app.js
Origin internal: http://spring-service:8080/assets/app.js
~~~

Gửi cùng GET qua đường public và đường origin **được phép trong môi trường kiểm thử**. So:

| Origin response | Public response | Khả năng |
|---|---|---|
| Có nosniff | Có nosniff | Đường đi có header đúng |
| Có nosniff | Thiếu nosniff | Proxy/CDN loại hoặc cache phiên bản cũ |
| Thiếu nosniff | Có nosniff | Header được thêm ở edge (có thể là kiến trúc chủ ý) |
| Thiếu cả hai | Thiếu security chain, writer disable hoặc cấu hình edge thiếu |
| Origin không nhận GET | File có thể được phục vụ tại edge/static host, không đi vào Spring |

Không gọi trực tiếp private origin nếu không có quyền. Thay bằng access logs/trace ID/hop-by-hop header snapshots có kiểm soát. Nếu proxy đổi `Host` và path, xác nhận hai request được so thực sự tương đương.

### Curl không mô phỏng hoàn toàn browser

`curl` không tự áp CSP, HSTS, preflight, SameSite, service worker hoặc browser cache như người dùng. Nó rất hữu ích để đọc HTTP headers, nhưng cần browser E2E cho hiệu ứng bảo vệ thực tế.

## 20. Logging: tìm đúng filter chain thay vì suy từ HTTP 200

Ở dev/staging, bật log tạm:

~~~properties
logging.level.org.springframework.security=DEBUG

# Chẩn đoán Servlet FilterChainProxy và selected filters.
logging.level.org.springframework.security.web.FilterChainProxy=TRACE

# Chẩn đoán Reactive security web filter proxy.
logging.level.org.springframework.security.web.server.WebFilterChainProxy=TRACE
~~~

Tên logger và chi tiết phát ra phụ thuộc Spring Security version. TRACE có thể nhiều dữ liệu, **không bật rộng/lâu dài ở production**. Đối chiếu với access logs tại nginx/CDN và request ID.

### Cách diễn giải

| Dấu vết | Cách hiểu |
|---|---|
| Asset xuất hiện trong origin access log, nhưng không có selected security chain | Có thể ignored/no matching chain hoặc logging thiếu; xác minh config |
| Asset chọn một chain và HeaderWriterFilter có mặt | Header vẫn có thể thiếu vì writer config/HTTPS/proxy |
| HTML vào chain A, assets vào chain B | Chính sách headers có thể khác nhau |
| Asset không vào Spring origin | Edge/static server có thể sở hữu response |
| `headers().disable()` trong chain khớp | Có filter chain nhưng header writer bị disable |
| HSTS chỉ thiếu trên HTTP origin | Kiểm tra HTTPS public/forwarded scheme |
| CSP thiếu ở HTML dù HeaderWriterFilter hoạt động | CSP writer có được bật đúng chain không? |

Không nhất thiết mỗi request đều có log line “đã viết header” trong framework. **Response headers thực và selected chain** cùng quan trọng hơn việc đoán từ một chuỗi log không xuất hiện.

## 21. MockMvc: fixture chứng minh asset vẫn được phục vụ công khai

Để test mà không cần thêm file JS vào project, có thể tạo **controller chỉ dùng trong lab/test profile**:

~~~java
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class AssetLabController {

    @GetMapping("/assets/lab.js")
    ResponseEntity<String> js() {
        return ResponseEntity.ok()
            .contentType(MediaType.parseMediaType("application/javascript"))
            .body("console.log('lab');");
    }

    @GetMapping("/public/page")
    ResponseEntity<String> page() {
        return ResponseEntity.ok()
            .contentType(MediaType.TEXT_HTML)
            .body("<!doctype html><title>Lab</title><p>Demo</p>");
    }
}
~~~

Tạo test integration dùng `@SpringBootTest` và `@AutoConfigureMockMvc` để ứng dụng thật sự gắn Spring Security filters. **Không dùng `MockMvcBuilders.standaloneSetup(...)` rồi mặc nhiên kết luận Spring Security đã chạy**.

### Test với cấu hình permitAll

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PublicAssetHeadersTest {

    @Autowired MockMvc mockMvc;

    @Test
    void assetPublicButSecurityHeadersPresent() throws Exception {
        mockMvc.perform(get("/assets/lab.js"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "X-Content-Type-Options", "nosniff"
            ));
    }
}
~~~

Test giả định:

- Controller fixture `/assets/lab.js` có trong application test context.
- Không có `web.ignoring()` cho path này.
- Một matching `SecurityFilterChain` bật default headers và `permitAll()` cho assets.

Kết quả PASS chứng minh **anonymous request nhận JS và `nosniff`** trong môi trường MockMvc. Nó không chứng minh CDN/HTTPS browser đã phát đúng headers ngoài public path.

### Test HTML và CSP do ta bật riêng

Nếu chain đã khai báo CSP writer:

~~~java
mockMvc.perform(get("/public/page"))
    .andExpect(status().isOk())
    .andExpect(header().exists("Content-Security-Policy"));
~~~

Không viết assertion CSP này vào test mặc định chưa cấu hình CSP, vì Spring Security **không tự thêm CSP cho mọi app**.

## 22. MockMvc: thử tái hiện lỗi do web.ignoring() để xác định nguyên nhân

Trong **một test configuration riêng** cố ý cấu hình ignore:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer;

@Bean
WebSecurityCustomizer ignoredAssetsForNegativeTest() {
    // PHẢN VÍ DỤ CHỈ DÙNG TRONG TEST — không triển khai production.
    return web -> web.ignoring()
        .requestMatchers("/assets/**");
}
~~~

Test so sánh:

~~~java
import org.springframework.test.web.servlet.MvcResult;
import static org.junit.jupiter.api.Assertions.assertTrue;

MvcResult ignored = mockMvc.perform(get("/assets/lab.js"))
    .andExpect(status().isOk())
    .andReturn();

assertTrue(ignored.getResponse()
    .getHeaders("X-Content-Type-Options").isEmpty());
~~~

Kết quả trên chỉ là **kỳ vọng trong một test context đã chủ động loại Security header writer và không có filter/proxy khác thêm header**. Không phải mọi ignored response ngoài thực tế đều thiếu `nosniff`: web server, CDN hoặc filter khác có thể cung cấp.

### Không để hai cấu hình cùng hoạt động trong một test

Để test đối chứng đúng, cần **hai application contexts hoặc hai profiles riêng**:

- Context A: assets chỉ `permitAll()`, không ignore.
- Context B: assets bị `web.ignoring()` (âm tính).

Không khai báo đồng thời `@Bean WebSecurityCustomizer` ignore trong cùng context rồi mong `permitAll()` “thắng”. Khi ignore đã được áp dụng, authorization matcher phía sau không khôi phục security chain.

### Đối chứng phải gồm cả hành vi anonymous

Test không chỉ headers: cả A và B đều có thể trả HTTP 200 anonymous. Chính điều này giải thích vì sao chỉ kiểm tra “static assets tải được” không phát hiện đường đi đã bỏ qua Spring Security.

## 23. MockMvc: nhiều chains và route public chưa chắc có header

Một test regression nên bao phủ ít nhất:

~~~text
GET /assets/lab.js  -> public, nosniff present
GET /public/page    -> public, HTML header policy đúng
GET /admin/home     -> unauthorized nếu anonymous
GET /api/private    -> unauthorized nếu anonymous
~~~

Các route sau chỉ là **tên minh họa**; authentication entry point có thể trả 401 hoặc 302 tùy Basic/Bearer/form login, không ép mọi hệ thống một status.

### Test một path không khớp chain

Tạo một test context với **chỉ API chain** `securityMatcher("/api/**")`. Với controller fixture `/assets/lab.js`:

~~~java
MvcResult result = mockMvc.perform(get("/assets/lab.js"))
    .andExpect(status().isOk())
    .andReturn();

// Nếu không có fallback chain và không có nguồn header khác,
// expected result trong negative test là không có nosniff.
boolean hasNosniff =
    result.getResponse().containsHeader("X-Content-Type-Options");
~~~

Quan sát giá trị `hasNosniff` và selected chain logs. Nếu test thực nhận nosniff, có thể một fallback/auto-configured chain hoặc custom header filter vẫn tồn tại; điều đó đòi hỏi điều tra, **không “sửa test” bằng cách bỏ assertion**.

### Kiểm tra không mở nhầm API

Khi thêm fallback chain, test rằng các endpoints chưa được cấp quyền **vẫn đòi authentication**. Một fallback `anyRequest().permitAll()` có thể làm header xuất hiện nhưng làm mất quyền truy cập; đó không phải bản sửa an toàn.

## 24. WebTestClient: chứng minh Reactive public asset vẫn nhận headers

Với WebFlux, có thể dùng cùng ý tưởng controller fixture `GET /assets/lab.js`:

~~~java
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ReactiveAssetLabController {

    @GetMapping("/assets/lab.js")
    ResponseEntity<String> js() {
        return ResponseEntity.ok()
            .contentType(MediaType.parseMediaType("application/javascript"))
            .body("console.log('webflux-lab');");
    }
}
~~~

Controller trả `ResponseEntity<String>` đồng bộ; WebFlux vẫn có thể xử lý kiểu return này. Trong ứng dụng Reactive thật, không dùng Servlet classes cho WebFlux route. Nếu muốn return reactive type, có thể dùng `Mono<ResponseEntity<String>>` nhưng không cần chỉ để kiểm tra response header.

### WebTestClient với security WebFilters

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactivePublicAssetHeadersTest {

    @Autowired WebTestClient webTestClient;

    @Test
    void assetCanBeReadAnonymouslyAndHasNosniff() {
        webTestClient.get()
            .uri("/assets/lab.js")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .valueEquals("X-Content-Type-Options", "nosniff");
    }
}
~~~

**Điều kiện:** ứng dụng chạy WebFlux, test client bind đúng security web filter chain, fixture có tồn tại, fallback chain xử lý assets và default headers chưa bị disable. Nếu test chỉ bind trực tiếp một controller bằng chế độ mock không tích hợp Spring Security, nó có thể bỏ qua cả `WebFilterChainProxy` và gây false negative.

### Negative case: chỉ có API SecurityWebFilterChain

Trong một application context **chỉ có** `securityMatcher(pathMatchers("/api/**"))` và không có fallback chain, request `/assets/lab.js` có thể trả 200 mà thiếu nosniff từ Spring Security.

**Không biến negative setup thành production config.** Mục tiêu test là cô lập nguyên nhân, sau đó đưa fallback chain hoặc điều chỉnh security matcher đúng phạm vi.

## 25. WebTestClient: HSTS trên HTTPS không kiểm tra bằng mock HTTP một cách mù quáng

Một WebTestClient được bind trực tiếp vào mock server request có thể sử dụng URI scheme `http` mặc định. Khi đó:

~~~java
webTestClient.get()
    .uri("/assets/lab.js")
    .exchange()
    .expectStatus().isOk();
~~~

không đủ để kết luận HSTS đúng hay sai trong **production HTTPS**. HSTS writer có thể chỉ thêm header trên secure requests.

### Phương án kiểm tra đáng tin

1. Dùng HTTP integration test qua **HTTPS embedded server hoặc HTTPS staging/public endpoint** có certificate hợp lệ.
2. Gửi GET tới đúng public hostname.
3. Assert HSTS header khi chính sách yêu cầu.
4. Kiểm tra `includeSubDomains` và `max-age` theo quyết định đã review.
5. Nếu HSTS do edge sở hữu, test **qua edge**, không chỉ gọi HTTP origin.

Một kiểm tra chỉ tìm “HSTS present” chưa đủ: giá trị `max-age=0` thực chất yêu cầu bỏ HSTS policy, còn `includeSubDomains` có tác động triển khai rộng.

### Test bằng WebTestClient với base URL HTTPS

Khi WebTestClient được cấu hình trỏ tới HTTPS endpoint thật, có thể test:

~~~java
webTestClient.get()
    .uri("/assets/lab.js")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().exists("Strict-Transport-Security");
~~~

Điều kiện là `webTestClient` **đã được bind tới HTTPS public/staging** và endpoint thực sự được HSTS policy áp dụng. Đừng sao chép assertion này vào mock HTTP WebTestClient rồi kết luận Spring Security lỗi khi test fail.

## 26. Browser E2E: headers trên document và resource thực

Một bài kiểm thử Playwright có thể so HTML với JS asset:

~~~javascript
import { test, expect } from "@playwright/test";

test("HTML và JS public được phục vụ với headers phù hợp",
  async ({ page }) => {
    const origin = "https://app.example.test";

    const documentResponse = await page.goto(
      origin + "/public/page"
    );
    expect(documentResponse).not.toBeNull();
    expect(documentResponse.status()).toBe(200);

    const htmlHeaders = documentResponse.headers();
    expect(htmlHeaders["x-content-type-options"]).toBe("nosniff");

    // Chỉ assert CSP khi ứng dụng lab thực sự đã cấu hình CSP.
    expect(htmlHeaders["content-security-policy"]).toContain(
      "default-src"
    );

    const jsResponse = await page.request.get(
      origin + "/assets/lab.js"
    );
    expect(jsResponse.status()).toBe(200);
    expect(jsResponse.headers()["x-content-type-options"])
      .toBe("nosniff");
});
~~~

**Giới hạn:** `page.request.get()` dùng APIRequestContext của Playwright, **không phải subresource request do browser render**. Nó giúp kiểm tra response headers của URL public; muốn chứng minh browser áp header theo ngữ cảnh nhúng script hoặc CSP, cần để document **thực sự tải JS** và theo dõi Network/browser behavior.

### Để chứng minh resource được browser tải

Trong test fixture HTML, nhúng:

~~~html
<!doctype html>
<html lang="vi">
<head><meta charset="utf-8"><title>Security Headers Lab</title></head>
<body>
  <script src="/assets/lab.js"></script>
</body>
</html>
~~~

Rồi dùng Playwright quan sát resource response:

~~~javascript
const jsResponsePromise = page.waitForResponse(response =>
  response.url().endsWith("/assets/lab.js")
);

await page.goto("https://app.example.test/public/page");
const jsResponse = await jsResponsePromise;

expect(jsResponse.status()).toBe(200);
expect(jsResponse.headers()["x-content-type-options"])
  .toBe("nosniff");
~~~

Đây là đoạn code bổ sung **trong một test đã có biến `page`**; fixture phải thực sự nhúng script và CSP cho phép `script-src` tương ứng. Browser/engine có thể cache resource, vì thế cần kiểm soát cache và request events khi test. Không kết luận script không tải **chỉ vì** một event không được bắt; cũng phải xem CSP/MIME/network logs.

### Không bật tùy chọn bỏ qua web security

Không chạy browser với flag tắt CORS/CSP hoặc bỏ kiểm tra TLS để làm test xanh. Mục tiêu là xác minh **hành vi browser mặc định trên đường HTTPS thật**.

## 27. So sánh cùng một header ở nhiều response paths

Một bài chẩn đoán tốt có **ma trận theo đường đi**:

| URL path | Loại tài nguyên | Nguồn response | Selected chain? | Header cần xem |
|---|---|---|---|---|
| `/public/page` | HTML | Spring MVC/WebFlux | Web fallback | CSP, nosniff, framing, cache, HSTS HTTPS |
| `/assets/lab.js` | JavaScript | Spring MVC/WebFlux fixture | Web fallback | Content-Type, nosniff, cache |
| `/assets/app.hash.js` | JS cacheable | CDN/origin | Có thể không | nosniff tại public response, correct MIME, cache |
| `/api/private` | JSON API | Spring API chain | API chain | nosniff, cache/no-store nếu cần, CORS theo Origin |
| `/login` | HTML | Spring web chain | Web chain | framing/CSP, cache, HSTS HTTPS |
| `/error` hoặc 404 page | HTML/error | Dispatcher/container/proxy | Tùy nguồn | Các headers có ý nghĩa cho error response |
| `/favicon.ico` | Image/icon | Static handler/CDN | Tùy route | Content-Type, cache, header policy thích hợp |

**Đừng dùng một URL duy nhất làm đại diện cho toàn bộ app**. Tài nguyên và chain có thể khác nhau, response 404/500 cũng có thể do component khác tạo.

### Response status không phải bản đồ đầy đủ của filter order

Một file JS `200 OK` có thể do Spring ResourceHandler, nginx hay CDN trả. Một tài nguyên `404 Not Found` có thể vẫn đi qua security chain (và vẫn có headers). **Status không tự chứng minh selected chain**.

## 28. Header thiếu chỉ trên response lỗi hoặc redirect

Khi GET asset thành công có headers nhưng lỗi thì thiếu, cần xác định response được tạo ở đâu:

~~~text
GET /assets/app.js          -> 200 từ Spring -> nosniff present
GET /assets/missing.js      -> 404 từ nginx  -> nosniff absent
GET /assets/private.js      -> 302 login     -> headers tùy chain
GET /api/private            -> 401 từ proxy  -> Spring không xử lý
~~~

Nếu response 404/500 do servlet container error dispatch hoặc gateway trả trước/ngoài selected chain, header writer của application có thể không được gọi cho response ấy. Ngược lại, một error response do Spring Security entry point tạo **trong chain** có thể vẫn nhận security headers khi writer hoạt động.

**Hướng sửa:** xác định nguồn lỗi, mapping/dispatch và owner của headers. Không tự thêm header writer mới trong từng exception handler nếu điều đó tạo headers trùng hoặc policy bất nhất.

### Dispatcher types và filter registration

Servlet filters có thể được đăng ký cho những dispatcher types nhất định như `REQUEST`, `ASYNC`, `ERROR`. Nếu `ERROR` dispatch không đi qua chain tương tự, response lỗi có thể thiếu header mà request thường có.

Hãy kiểm tra filter registration của ứng dụng **trong phiên bản Spring Boot đang dùng**, thay vì mặc định mọi error dispatch đều qua cùng filter set. Đừng tự thay đổi dispatcher types thiếu kiểm soát: điều đó có thể ảnh hưởng việc security filters chạy lại, error handling và request wrappers.

## 29. Spring Boot PathRequest: tiện ích matcher không buộc phải dùng ignoring()

Spring Boot cung cấp tiện ích chọn các vị trí static resource phổ biến:

~~~java
import org.springframework.boot.autoconfigure.security.servlet.PathRequest;
~~~

Một cấu hình thường thấy:

~~~java
@Bean
WebSecurityCustomizer ignoringCommonStaticResources() {
    return web -> web.ignoring()
        .requestMatchers(
            PathRequest.toStaticResources().atCommonLocations()
        );
}
~~~

**Điểm dễ bị bỏ qua:** `PathRequest.toStaticResources().atCommonLocations()` chỉ giúp tạo matcher; hành vi **ignore** đến từ `web.ignoring()`. Không phải API PathRequest tự quyết định phải bỏ toàn bộ security filters.

### Sử dụng matcher đó trong permitAll

~~~java
import org.springframework.boot.autoconfigure.security.servlet.PathRequest;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers(
            PathRequest.toStaticResources().atCommonLocations()
        ).permitAll()
        .requestMatchers("/", "/login", "/public/page").permitAll()
        .anyRequest().authenticated()
    );
    return http.build();
}
~~~

Ở đây matcher static resource được dùng trong **authorization của security chain**, nên request vẫn đi qua chain nếu có matcher phạm vi phù hợp và không bị ignore ở đâu khác. Nếu ứng dụng dùng đường `/assets/**` riêng ngoài những common locations, khai báo thêm matcher rõ ràng.

### Những điểm cần xác minh

- PathRequest này dành cho **Spring Boot Servlet**; không mang nguyên vào WebFlux.
- “Common locations” phụ thuộc Spring Boot conventions, không bảo đảm bao phủ CDN path hoặc custom resource chain.
- Resource handler có thể có cache policy riêng, đừng xóa cache optimization khi đổi ignore sang permitAll.
- Nếu có nhiều chains, matcher cần nằm trong chain thực sự xử lý static resources.

## 30. Kịch bản A — CSS/JS được ignore, HTML có nosniff/CSP

**Triệu chứng:** scanner phát hiện:

~~~text
GET /dashboard         -> 200, nosniff present, CSP present
GET /css/site.css      -> 200, nosniff missing
GET /js/app.js         -> 200, nosniff missing
~~~

Trong code:

~~~java
@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring()
        .requestMatchers("/css/**", "/js/**");
}
~~~

**Chẩn đoán có kiểm chứng:**

1. Xác nhận hai assets thực sự được Spring origin phục vụ, không phải CDN.
2. Kiểm tra FilterChainProxy logs: asset paths có bị ignore?
3. So với một path public `permitAll()` vẫn vào chain và nhận nosniff.
4. Kiểm tra có header writer ở chain đó không; không vội sửa CSP vì thiếu `nosniff`.

**Cách sửa:** gỡ ignore cho các path phù hợp; đưa `/css/**` và `/js/**` vào `permitAll()` trong matching chain. Xác minh asset vẫn tải anonymous, đúng MIME type, cache policy và nosniff.

**Không chỉ kiểm tra GET 200.** Sau sửa, test rằng trang login vẫn load CSS/JS khi anonymous, và API/admin khác vẫn yêu cầu quyền.

## 31. Kịch bản B — API chain và admin chain đều đúng, assets không khớp chain nào

**Triệu chứng:** không tìm thấy `web.ignoring()`, nhưng file `/assets/app.js` thiếu security headers và backend nhận GET.

Application có:

~~~text
Chain @Order(1): /api/**
Chain @Order(2): /admin/**
Không có chain fallback
~~~

**Nguyên nhân:** security matcher không bao phủ static resources; authorization của các chain đó chưa từng được đánh giá cho `/assets/**`.

**Cách kiểm tra:** bật chain selection logs và gọi GET assets, kiểm tra beans/`@Order`/`securityMatcher`. Không chỉ tìm `requestMatchers("/assets/**").permitAll()` ở một class bất kỳ — nó có thể nằm trong chain bị giới hạn `/api/**` nên không bao giờ match.

**Sửa:** thêm một chain fallback cho web paths, công khai assets và login, yêu cầu authentication ở các route còn lại. Giữ header writers được bật. Test ít nhất assets, login, API private và admin protected.

### Tại sao không tạo fallback permitAll toàn bộ?

Nếu route nghiệp vụ mới chưa được gán vào API/admin chain, `anyRequest().permitAll()` có thể mở nó công khai. Bản sửa đúng nên dùng **default-deny hoặc authenticated fallback phù hợp**, không chỉ làm scanner “hết thiếu header”.

## 32. Kịch bản C — WebFlux có securityMatcher chỉ cho API

**Triệu chứng:** cùng Spring Boot project nhưng chọn WebFlux, JSON API có `X-Content-Type-Options`, còn CSS/JS phục vụ bởi WebFlux resource handler không có.

Cấu hình:

~~~java
http.securityMatcher(
    ServerWebExchangeMatchers.pathMatchers("/api/**")
);
~~~

Nếu không có `SecurityWebFilterChain` khác bao phủ assets, Reactive `HttpHeaderWriterWebFilter` sẽ không được áp cho paths ấy.

**Cách sửa:** tạo fallback `SecurityWebFilterChain` công khai resources bằng `pathMatchers(...).permitAll()`, giữ default headers và bảo vệ các routes còn lại. Kiểm thử bằng WebTestClient gắn WebFlux security và browser public path.

**Tránh nhầm stack:** việc thêm Servlet `WebSecurityCustomizer` vào ứng dụng WebFlux không phải cách cấu hình security matching cho Reactive WebFilters. Đọc đúng các beans/filters của WebFlux.

## 33. Kịch bản D — HSTS thiếu vì proxy TLS, không phải assets bị ignore

**Triệu chứng:** scanner ở HTTPS public thấy HSTS thiếu trên một vài paths, nhưng local HTTP origin và MockMvc đều không có HSTS. Developer kết luận ngay security chain bỏ qua assets.

**Điều tra:**

1. HTTPS response public có HSTS trên **HTML** không?
2. Nguồn HSTS theo thiết kế là Spring hay CDN/edge?
3. Spring có nhìn request là secure qua forwarded headers đáng tin không?
4. Assets đi qua Spring hay được CDN trả từ cache?
5. Một response 301 từ HTTP sang HTTPS có bị nhầm với HTTPS response thực không?

**Hướng sửa:** nếu edge sở hữu HSTS, cấu hình nhất quán trên các HTTPS responses thích hợp của host. Nếu Spring sở hữu, bảo đảm secure request detection qua proxy tin cậy và matching security chain. Test HTTPS public; không ép HSTS trên HTTP upstream bằng header giả do client gửi.

**Không tắt `Secure` cookie, HSTS hoặc CSP để giải quyết một vấn đề route/header.** HSTS là security policy domain-level cần đánh giá subdomain và khả năng triển khai HTTPS đầy đủ.

## 34. Kịch bản E — CDN phục vụ assets nên Spring headers không xuất hiện

**Triệu chứng:**

~~~text
GET /dashboard       -> Spring Boot -> nosniff present
GET /assets/app.js   -> CDN cache HIT -> nosniff absent
~~~

**Phép thử:**

- Ghi URL thực, response source và cache hit/miss.
- So asset origin headers với asset qua CDN.
- Xem CDN có giữ/drop headers khi cache hay khi dùng stale object không.
- Nếu static file trên object storage, xác định chính sách metadata/header tại object store/CDN.
- Test GET lần đầu và lần sau qua public endpoint sau khi đã cập nhật cache đúng.

**Sửa đúng tầng:** cấu hình headers tại CDN/static hosting hoặc bảo đảm nó giữ headers phù hợp từ origin. Thay `web.ignoring()` bằng `permitAll()` trong Spring **không thể sửa** một response hoàn toàn không đi qua Spring.

### Cache và khả năng cập nhật security header

Một bundle có tên hash được cache lâu có thể tiếp tục được edge phát với header cũ. Khi thay đổi policy, phải có chiến lược versioning/invalidation phù hợp; không tự ghi `Cache-Control: no-store` cho mọi asset để né cache nếu không có lý do bảo mật.

## 35. Kịch bản F — “Thiếu CSP trên JS” thực ra CSP của HTML đã hoạt động

**Triệu chứng:** công cụ quét tất cả HTTP responses và đánh dấu “missing Content-Security-Policy” trên `app.js`, `style.css`, images và fonts.

**Điều tra kỹ thuật:**

1. Xác định CSP của HTML document tải những resources ấy.
2. Kiểm tra `script-src`, `style-src`, `connect-src`, `img-src`, `font-src` có phù hợp chính sách không.
3. Xem browser Console và violation reports thực tế.
4. Kiểm tra header `nosniff`/MIME type riêng trên JavaScript/CSS.
5. Phân biệt một scanner rule quá rộng với lỗi bảo mật thực.

**Kết luận có thể đúng:** HTML đã có CSP phù hợp; CSP trên một file JS **không phải cách truyền policy script-src cho document**. Vẫn cần xem resource đó có đi qua security chain hay CDN, nhưng không tự coi mọi response thiếu CSP là cùng một lỗi.

### Trường hợp vẫn cần điều tra

Nếu một path dưới `/assets/**` lại trả **HTML** (ví dụ SPA fallback, tài liệu HTML, preview page), CSP hoặc framing policy trên response HTML đó có thể quan trọng. **Phân loại theo Content-Type và cách browser sử dụng response**, không chỉ theo đuôi URL.

## 36. Kịch bản G — Public resources tải được nhưng API private bị ignore theo pattern rộng

**Triệu chứng:** sau khi “sửa” bằng:

~~~java
return web -> web.ignoring().requestMatchers("/**");
~~~

mọi tài nguyên load nhanh hơn, nhưng API private không yêu cầu authentication và security headers cũng biến mất.

**Đây là một lỗi an ninh nghiêm trọng hơn missing header.** Bypass toàn bộ Spring Security khiến authorization, authentication, CSRF và các security filters khác không bảo vệ endpoints tương ứng.

**Khắc phục:** bỏ pattern ignore quá rộng, thiết kế security matchers cho đúng public assets và protected APIs, dùng `permitAll()` hẹp và `authenticated()` hoặc `denyAll()` cho routes còn lại. Kiểm thử:

~~~text
GET /assets/lab.js anonymous    -> 200 + nosniff
GET /login anonymous            -> 200 theo cấu hình
GET /api/private anonymous      -> bị từ chối
POST /api/private không CSRF    -> bị từ chối nếu flow yêu cầu CSRF
GET /admin/home anonymous       -> bị từ chối
~~~

HTTP status của các route bị từ chối phụ thuộc form login (302), Basic/Bearer (401) hoặc authorization (403). Không ép tất cả thành 403.

## 37. Bảng chẩn đoán nhanh: cái gì thiếu, ở đâu, và vì sao?

| Quan sát | Giả thuyết ưu tiên | Phép thử phân biệt |
|---|---|---|
| HTML có nosniff, JS thiếu; cả hai do Spring trả | Assets bị ignore hoặc không match chain | FilterChainProxy logs, WebSecurityCustomizer, fallback chain |
| Có bean `WebSecurityCustomizer` ignore CSS/JS | Servlet security filters bị bypass cho paths ấy | Bỏ ignore trong test context, dùng permitAll |
| Không có `web.ignoring()` nhưng assets thiếu headers | Không có matching chain hoặc headers disabled | Xem securityMatcher/@Order/selected chain |
| Security chain có `permitAll()` nhưng thiếu nosniff | HeaderWriterFilter không chạy, disable hoặc custom writer | Xem selected filters, response origin/public |
| Chỉ thiếu CSP, các default headers vẫn có | CSP chưa được cấu hình cho đúng HTML chain | Kiểm tra ContentSecurityPolicy config và HTML response |
| Chỉ thiếu HSTS trên HTTP local | HSTS chỉ áp dụng cho secure response | Test HTTPS public, forwarding và edge policy |
| Chỉ thiếu HSTS trên HTTPS sau proxy | Scheme detection/edge policy/cache | So HTTPS public, proxy and origin |
| JS có `Cache-Control: public, immutable` | Có thể là cache policy có chủ ý | Kiểm tra fingerprinted asset vs HTML/token |
| Chỉ CDN cache HIT thiếu header | CDN giữ/drop header hoặc cached object cũ | So cache hit/miss, public/origin |
| 404/500 thiếu header, 200 có | Nguồn error response khác | Dispatcher types, gateway error handling |
| OPTIONS không có ACAO | CORS filter/matcher hoặc Origin không hợp lệ | Preflight logs, CORS policy, path |
| JavaScript bị CSP chặn, không có asset GET | CSP `script-src`/`connect-src` trên HTML | Browser Console và CSP document |
| Response có header nhưng browser vẫn chặn script | MIME type sai cùng nosniff, CSP hoặc CORP | Network Content-Type, browser violation |
| API private trả 200 anonymous sau sửa config | Ignore/matcher quá rộng | Authorization negative regression test |
| WebFlux API có headers, assets không | Không có fallback SecurityWebFilterChain | Matchers, HttpHeaderWriterWebFilter |
| Response đã có headers ở Spring nhưng thiếu public | Proxy/CDN rewrite, cache hoặc custom edge | So cùng request origin/public |

**Không suy từ một header thiếu rằng toàn bộ security chain đã mất.** Nếu `X-Content-Type-Options`, `Cache-Control` và framing headers đều biến mất trên cùng một path nhưng xuất hiện ở paths khác cùng server, khả năng bypass/chain selection đáng kiểm tra. Nếu chỉ một header thiếu, kiểm tra **điều kiện và cấu hình riêng của header ấy** trước.

## 38. Runbook tám bước: từ request public tới header writer

~~~mermaid
flowchart TD
    A[Header thiếu trên một tài nguyên] --> B{Response thực do Spring trả?}
    B -- Không --> C[CDN, static server, object storage, edge headers]
    B -- Có --> D{Request bị ignore?}
    D -- Có --> E[Thay ignore hẹp bằng matching chain + permitAll]
    D -- Không --> F{Có SecurityFilterChain match path?}
    F -- Không --> G[Thêm hoặc chỉnh fallback chain an toàn]
    F -- Có --> H{Header writer được bật?}
    H -- Không --> I[Bật hoặc cấu hình header policy đúng chain]
    H -- Có --> J{Header có điều kiện hoặc bị ghi đè?}
    J -- Có --> K[HTTPS, Content-Type, cache, proxy, error path]
    J -- Không --> L[Kiểm tra custom filters và actual response]
    C --> M[Positive/negative regression tests]
    E --> M
    G --> M
    I --> M
    K --> M
    L --> M
~~~

### Bước 1 — Xác định chính xác header và loại response

Chọn một URL thực, GET thực, scheme/host/path, Content-Type, status và security header đang thiếu. Ghi loại tài nguyên: HTML, JS, CSS, JSON, font/image hay redirect/error. **Không đặt mục tiêu “mọi URL có mọi header” khi chưa xét ngữ nghĩa.**

### Bước 2 — Đọc headers qua public HTTPS

Dùng DevTools/curl để xem response cuối cùng. Nếu có CDN, ghi cache hit/miss và response source. HSTS đo trên HTTPS, CSP trên HTML; kiểm tra GET thay vì chỉ HEAD.

### Bước 3 — Truy vết nguồn response

Đối chiếu edge → proxy → Spring origin qua request ID/timestamp. Nếu response không đi qua Spring, chuyển đến cấu hình server/CDN; không thay Spring `HttpSecurity` để chữa một file do nginx trả.

### Bước 4 — Kiểm tra ignoring trước

Trong Servlet, tìm `WebSecurityCustomizer` và `web.ignoring()` trên đúng path. Đặc biệt chú ý pattern `/**`, `/assets/**`, `PathRequest.toStaticResources().atCommonLocations()`. Không đọc nhầm `permitAll()` là ignore.

### Bước 5 — Kiểm tra selected chain và order

Xem `SecurityFilterChain.securityMatcher`/`@Order` hoặc Reactive `SecurityWebFilterChain` matcher/order. Nếu không có chain phù hợp, thêm fallback an toàn cho resources; nếu chọn nhầm chain, sửa matcher/order thay vì làm tất cả public.

### Bước 6 — Kiểm tra writer và điều kiện của header

Servlet: `HeaderWriterFilter`/`HttpSecurity.headers(...)`. Reactive: `HttpHeaderWriterWebFilter`/`ServerHttpSecurity.headers(...)`. Xác minh có `headers().disable()` hoặc một writer cụ thể bị disable; CSP/Referrer/Permissions có cần bật riêng không; HSTS có secure request không.

### Bước 7 — Đối chiếu caching, error và proxy

Nếu origin có header mà public thiếu, xem edge. Nếu chỉ 404/500 thiếu, xem error response source/dispatcher. Nếu header bị ghi đè bởi cache policy custom, xác định behavior có chủ ý hay không.

### Bước 8 — Sửa nhỏ nhất và test cả bảo vệ khác

Thay ignore bằng permitAll hẹp, bổ sung fallback chain hoặc header writer thích hợp. Kiểm thử lại anonymous assets, private API authorization, CSRF của unsafe requests, CSP của HTML, MIME/nosniff của JS, HTTPS HSTS và cache policy.

### Mẫu ghi nhận sự cố không lộ bí mật

| Trường | Ví dụ |
|---|---|
| Request ID | `req-asset-42` |
| URL | `GET https://app.example.com/assets/app.hash.js` |
| Status, content type | `200 application/javascript` |
| Response source | `Spring MVC origin` |
| Expected header | `X-Content-Type-Options: nosniff` |
| Actual header | `missing` |
| Security chain | `ignored by /assets/**` |
| Proposed fix | `permitAll()` trong fallback chain |
| Regression | Anonymous GET 200 + nosniff; API private vẫn protected |

Không ghi session IDs, bearer tokens, CSRF token values, cookie bodies, mật khẩu hoặc phản hồi cá nhân hóa trong ticket.

## 39. Anti-pattern: sửa thiếu header bằng cách phá bảo vệ

| Cách sửa sai | Nguy cơ | Cách đúng |
|---|---|---|
| `web.ignoring("/**")` để tránh authorization | Toàn bộ endpoints bỏ qua Spring Security | Matching chains + permitAll hẹp |
| Bỏ security matcher để mọi path public | Có thể vô tình lộ API/admin | Fallback authenticated/denyAll, permit chỉ tài nguyên công khai |
| `headers().disable()` để tắt header “khó chịu” | Mất nhiều headers mặc định cùng lúc | Sửa writer cụ thể, review header policy |
| Cấu hình CSP tùy tiện trên mọi JS/CSS mà không xem HTML | Không giải quyết CSP của document, có thể gây lỗi | Thiết kế CSP từ HTML và nhu cầu browser |
| Bắt mọi asset có `Cache-Control: no-store` | Mất tối ưu caching không cần thiết | Cache immutable cho fingerprint assets, no-store cho dữ liệu nhạy cảm |
| Đòi HSTS trên HTTP origin local | Kiểm thử sai điều kiện secure request | Test HTTPS public/edge |
| Tự thêm `X-Forwarded-Proto: https` do client gửi | Forwarded-header spoofing | Proxy đáng tin làm sạch và thiết lập header |
| Chỉ sửa Spring khi CDN trả assets | Thay đổi không đến người dùng | Đặt headers tại CDN/static host |
| Dùng `permitAll()` toàn API để giữ header | Mở endpoints ngoài ý muốn | Phân quyền API riêng, public assets riêng |
| Tắt CSRF/CORS vì JS bundle không tải | Chữa sai lớp, giảm bảo vệ | Kiểm tra Content-Type/nosniff/CSP và path |
| Tắt StrictHttpFirewall vì static URL bị reject | Mở bề mặt URL/path confusion | Sửa path/encoding, review ngoại lệ hẹp |
| Log toàn Cookie/Authorization để tìm chain | Rò credentials | Chỉ log request ID, chain, presence flags |
| Chỉ chạy unit test controller rồi khẳng định headers OK | Không có Security filters trong standalone test | MockMvc/WebTestClient integration + public browser |
| Chỉ kiểm tra 200, bỏ qua 404/500/redirect | Header thiếu trên response path khác | Test success/failure/error routes |
| Sửa header scanner mà bỏ test authentication | Có thể mở lỗ hổng nghiêm trọng | Regression security positive và negative |

**Một cấu hình tốt không nhất thiết áp mọi header giống nhau cho HTML, JS, JSON và images.** Nhưng những headers đã được thiết kế có ý nghĩa bảo vệ phải được phát **ở đúng tầng** và **trên đúng responses**, kể cả các public resources.

## 40. Bài thực hành tổng hợp: tái hiện và khắc phục header bị thiếu

**Bối cảnh:** tạo Spring Boot lab với `GET /public/page` trả HTML, `GET /assets/lab.js` trả JavaScript, `GET /api/private` cần authentication, `POST /api/change` cần authentication và CSRF với browser session. Triển khai một phiên bản Servlet, một phiên bản WebFlux và thêm reverse proxy HTTPS trong môi trường staging được kiểm soát.

### Bước thực hành

1. **Baseline:** xác minh trang HTML và JS có `X-Content-Type-Options: nosniff` khi đi qua matching security chain; CSP chỉ assert sau khi đã cấu hình trên HTML.
2. **Servlet negative:** tạo profile test với `WebSecurityCustomizer web.ignoring("/assets/**")`. Gọi GET JS anonymous bằng MockMvc, so headers với `/public/page`. Ghi selected chain.
3. **Servlet fix:** bỏ ignore, dùng `requestMatchers("/assets/**").permitAll()` trong chain khớp. Test JS vẫn HTTP 200 anonymous và có nosniff.
4. **Không làm mất bảo vệ:** gọi `/api/private` anonymous, xác nhận vẫn bị authentication yêu cầu; `POST /api/change` thiếu token vẫn bị CSRF từ chối khi flow áp CSRF.
5. **Multi-chain negative:** chỉ tạo API/admin security chains, bỏ fallback; quan sát GET JS vẫn 200 nhưng thiếu headers từ security chain.
6. **Multi-chain fix:** thêm fallback chain bảo vệ các paths còn lại; assets và login permitAll, những route khác authenticated theo thiết kế. Test chain order.
7. **HeaderWriter disabled:** trong một test profile, disable HTTP headers của selected chain; xác nhận khác biệt so với `ignoring()`: authorization/CSRF vẫn có thể hoạt động.
8. **CSP đúng context:** bật CSP trên HTML, test document response; xem JS bundle có nosniff/MIME đúng mà không yêu cầu nó mang y hệt CSP document.
9. **HSTS:** đo HTTPS staging public, so HTTP origin. Nếu đi qua proxy, cấu hình forwarded headers đáng tin hoặc HSTS tại edge; không bắt HTTP origin phát HSTS để test xanh.
10. **Caching:** dùng file `app.hash.js` với policy cache phù hợp, không áp no-store máy móc. So lần lấy từ CDN cache hit và miss.
11. **Reactive negative:** chỉ khai báo `SecurityWebFilterChain` cho `/api/**`. Dùng WebTestClient đo asset thiếu header do không match chain.
12. **Reactive fix:** thêm fallback `SecurityWebFilterChain` với `permitAll()` assets. Test WebTestClient thấy nosniff và API vẫn được bảo vệ.
13. **Browser:** dùng Playwright tải HTML và JS trên HTTPS public; so response headers từ document và asset, kiểm tra browser Console khi MIME/CSP không phù hợp.
14. **Error route:** tạo 404 từ static server/edge rồi so với error response Spring; xác định header owner cho từng loại response.
15. **Bàn giao:** lập bảng URL, status, Content-Type, source, selected chain, intended headers, actual headers, nguyên nhân, cách sửa và regression PASS/FAIL.

### Mẫu kết quả kiểm tra

| Tình huống | GET asset public | Security header từ Spring | Đánh giá |
|---|---|---|---|
| Servlet permitAll trong matching chain | 200 | Thường có theo config | Hướng đúng |
| Servlet web.ignoring | 200 | Không được chain bảo đảm | Cần review nếu header dựa vào Spring |
| Không matching chain | 200 nếu handler phục vụ | Không có từ các chains khác | Thiếu fallback hoặc sai matcher |
| Chain match nhưng headers disabled | Có thể 200 | Không có từ disabled writers | Sửa header policy |
| Reactive fallback với permitAll | 200 | Có thể có default headers | Hướng đúng |
| CDN tự phục vụ asset | 200 | Spring không tham gia | Edge phải chịu trách nhiệm |
| HTTPS edge HSTS present | 200 | Có thể không cần Spring sở hữu HSTS | Đo public HTTPS |
| JS có immutable cache | 200 | nosniff có thể có, cache public | Không nhất thiết phải no-store |

### Câu hỏi tự đánh giá

1. Vì sao `permitAll()` và `web.ignoring()` không tương đương?
2. `HeaderWriterFilter` làm gì, và tại sao ignored path không nhận header từ nó?
3. Khi dùng `PathRequest.toStaticResources().atCommonLocations()`, điều gì mới quyết định ignore hay permitAll?
4. Vì sao một `SecurityFilterChain` chỉ match `/api/**` không tự áp headers cho `/assets/**`?
5. Khác biệt giữa `securityMatcher()` và `requestMatchers(...).permitAll()` là gì?
6. Tại sao fallback `anyRequest().permitAll()` có thể nguy hiểm?
7. Trường hợp nào `headers().disable()` khác với ignore?
8. Những headers nào Spring Security thường áp mặc định, header nào phải bật riêng?
9. Vì sao không nên giả định CSP của HTML phải được copy vào file JS?
10. Vì sao `X-Content-Type-Options: nosniff` đáng kiểm tra trên JS/CSS?
11. Tại sao HSTS không xuất hiện trên HTTP origin chưa chắc là lỗi?
12. Khi proxy terminate TLS, Spring phải tin forwarded headers từ đâu?
13. Vì sao `Cache-Control: public, immutable` có thể hợp lệ trên file JS có hash?
14. Những nguồn nào có thể phục vụ asset mà không bao giờ gọi Spring?
15. Vì sao MockMvc standaloneSetup không đủ chứng minh Spring Security header writers hoạt động?
16. Test âm tính với ignoring nên được cô lập ở context nào?
17. Tại sao một WebTestClient mock HTTP không đủ chứng minh HSTS trên HTTPS?
18. Trong WebFlux, lớp nào chịu trách nhiệm security header writer?
19. Vì sao WebFlux không dùng `WebSecurityCustomizer` như Servlet?
20. Nếu CDN cache hit thiếu nosniff nhưng Spring origin có, cần sửa tầng nào?
21. Vì sao một 304 không nên được đánh giá như response 200 độc lập?
22. Nếu 404 thiếu headers nhưng 200 có, nên kiểm tra những request paths nào?
23. Tại sao file JS có HTTP 200 vẫn có thể bị browser chặn vì MIME/CSP?
24. Khi đổi ignore thành permitAll, kiểm thử nào xác minh API private chưa bị mở?

## 41. Ghi nhớ

**Header bị thiếu trên tài nguyên đã bỏ qua security chain** thường xuất hiện khi cấu hình Servlet dùng `web.ignoring()` cho static resources, hoặc khi request không khớp bất kỳ security chain nào. `permitAll()` là cách **cho phép truy cập công khai mà vẫn đi qua Spring Security filters** nếu chain match. Trên Servlet, kiểm tra `HeaderWriterFilter` và `SecurityFilterChain`; trên Reactive/WebFlux, kiểm tra `HttpHeaderWriterWebFilter` và `SecurityWebFilterChain`.

Nhưng phải **đánh giá đúng header trên đúng response**: `nosniff` hữu ích cho JS/CSS có MIME type phù hợp; CSP chủ yếu được xác định trên HTML document; HSTS kiểm tra trên HTTPS public; cache policy của fingerprinted static assets có thể khác hoàn toàn HTML/session/CSRF. Một asset do nginx/CDN phục vụ ngoài Spring phải nhận header từ **chính tầng phục vụ nó**, không thể kỳ vọng Spring Security tự tác động lên response ấy.

Quy trình đúng trong `SPRING_SECURITY_HTTP_PROTECTION` là **xác minh nguồn response → kiểm tra ignoring/chain matcher → kiểm tra header writer và điều kiện header → sửa nhỏ nhất → kiểm thử cả security headers lẫn authentication, authorization, CSRF, CORS và bảo vệ session**. Không đánh đổi một bộ security filters lấy việc public resource tải được hoặc một scanner hết cảnh báo.
