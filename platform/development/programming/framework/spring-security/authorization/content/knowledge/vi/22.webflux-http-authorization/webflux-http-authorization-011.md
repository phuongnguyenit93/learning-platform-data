# CORS, CSRF và phạm vi request trong ứng dụng Reactive

## 1. Mục tiêu và ngữ cảnh WebFlux

Ứng dụng Spring WebFlux thường phục vụ giao diện web (SPA), API JSON, các endpoint tải lên/tải xuống, luồng dữ liệu và client service-to-service. Khi frontend chạy ở `https://app.example.test` còn API ở `https://api.example.test`, trình duyệt áp dụng **Same-Origin Policy** và cơ chế CORS; nếu browser tự gửi cookie/session credential, request thay đổi trạng thái còn đối mặt với **CSRF**. Trong WebFlux, thông tin request được truyền qua `ServerWebExchange` và **Reactor Context**, khác với cách dựa vào thread-local trong Servlet.

Ba chủ đề liên quan nhau nhưng giải quyết **ba bài toán khác nhau**:

| Cơ chế | Câu hỏi chính | Đối tượng áp dụng |
|---|---|---|
| **CORS** (Cross-Origin Resource Sharing) | JavaScript từ origin nào được trình duyệt cho phép truy cập response của API? | Browser, response headers và preflight |
| **CSRF** (Cross-Site Request Forgery) | Browser có đang gửi một yêu cầu thay đổi trạng thái trái ý người dùng vì tự mang thông tin đăng nhập không? | Request có ambient credentials như cookie/session, Basic trong tình huống phù hợp |
| **Request context/scope** | Danh tính, tenant, correlation ID và dữ liệu riêng của **request này** được giữ/truyền ở đâu trong reactive pipeline? | `ServerWebExchange`, Reactor Context, Authentication, WebSession |

CORS **không phải** authentication hoặc object authorization. CSRF token **không phải** role/authority để xem dữ liệu. Request context **không tự xác minh** tenant/subject chỉ vì chúng có sẵn trong một header.

Bài này tập trung vào **Spring Security WebFlux**: `ServerHttpSecurity`, `SecurityWebFilterChain`, `CorsWebFilter`, `CsrfWebFilter`, `WebSession` và `ReactiveSecurityContextHolder`. Không copy nhầm `HttpSecurity`, `SecurityFilterChain` hoặc Servlet `CorsFilter` từ hướng dẫn MVC.

## 2. Luồng request minh họa

~~~text
Browser (origin app.example.test)
    |
    | OPTIONS preflight (khi cần)
    v
WebFlux CORS processing / CorsWebFilter
    |   - kiểm Origin
    |   - kiểm requested method và headers
    |   - trả CORS preflight response hoặc từ chối
    |
    | Actual GET/POST/PUT/DELETE
    v
Spring Security WebFilterChain
    |   - CSRF token check khi request thuộc diện bảo vệ
    |   - authentication và request authorization
    v
Handler / reactive service
    |   - verified actor + tenant + resource policy
    |   - Reactor Context / ServerWebExchange attributes
    v
Reactive repository / side effect
    |
    v
Response + CORS response headers
    |
Browser quyết định có cho JavaScript đọc response hay không
~~~

Đây là **sơ đồ khái niệm**, không cam kết thứ tự tuyệt đối của mọi WebFilter trong mọi project. Điều quan trọng là **CORS preflight được xử lý trước authentication**, vì preflight thông thường không mang cookie hoặc bearer token. CSRF được kiểm cho các actual unsafe requests theo cấu hình, còn service vẫn phải thực hiện object-level authorization trước khi đọc/ghi dữ liệu.

Một actual request có thể vừa **được CORS chấp nhận**, vừa **bị CSRF hoặc authorization từ chối**. Đó là tình huống bình thường, không phải cấu hình CORS “chưa cho phép”.

## 3. Origin là scheme + host + port

Hai URL cùng origin khi scheme, host và port tương đương:

~~~text
https://app.example.test            <- origin A
https://app.example.test/dashboard  <- origin A
https://api.example.test            <- origin B, khác host
http://app.example.test             <- origin C, khác scheme
https://app.example.test:8443       <- origin D, khác port
~~~

Trình duyệt gửi header:

~~~http
Origin: https://app.example.test
~~~

Server có thể trả:

~~~http
Access-Control-Allow-Origin: https://app.example.test
~~~

Khi request dùng browser credentials và server cho phép, phản hồi còn cần header phù hợp:

~~~http
Access-Control-Allow-Credentials: true
~~~

**Origin không phải tenant hoặc danh tính.** Header Origin có thể được tạo hoặc giả bởi non-browser HTTP client. Đừng xây authorization như “Origin là trang quản trị nên user tự có ROLE_ADMIN”. Browser thực thi CORS; curl hoặc backend service có thể gọi API mà không chịu hạn chế giống JavaScript trên trình duyệt.

Cũng phân biệt **same-origin** và **same-site**: hai subdomain có thể khác origin nhưng cùng site theo tính toán của browser và cookie SameSite. `SameSite` là một thuộc tính cookie/defense-in-depth, **không thay thế** kiểm CORS, CSRF hay quyền tài nguyên.

## 4. CORS không ngăn mọi request đến server

Same-Origin Policy chủ yếu hạn chế **khả năng script đọc phản hồi cross-origin** và một số loại tương tác. Một web độc hại vẫn có thể khiến browser phát một số request cross-site dưới những điều kiện HTTP bình thường, chẳng hạn submit HTML form. Vì thế:

- Không được nghĩ “đã cấu hình CORS deny evil.com thì không thể bị CSRF”.
- Không được dựa vào Origin như biện pháp duy nhất để xác thực subject.
- Không bật CORS vô điều kiện cho mọi origin chỉ vì API có Bearer token.
- Không dùng response CORS để thay `hasAuthority`, `@PreAuthorize` hoặc scope `tenant + resource ID`.

Ví dụ người dùng đang login bằng session cookie với `api.example.test`. Trang độc hại có thể cố tạo form POST đến API; cho dù browser không cho script của nó đọc response, request có thể **đã được gửi**. CSRF protection phải làm request giả mạo không có token hợp lệ bị từ chối **trước khi cập nhật dữ liệu**.

Ngược lại, request hợp lệ có Bearer token nhưng Origin không thuộc allowlist có thể hoàn thành ở server song browser không cho frontend đọc response. Cấu hình CORS chỉ tác động trong cơ chế trình duyệt, không biến một hành động được phép thành một cơ chế xác thực mới.

## 5. Preflight là gì và khi nào xuất hiện?

Trình duyệt có thể gửi request `OPTIONS` trước một cross-origin actual request cần preflight, ví dụ POST JSON có custom CSRF header:

~~~http
OPTIONS /api/documents/42 HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Đây là **preflight**, không phải POST thật. Nó hỏi server: “Nếu script của origin này gửi POST với các headers ấy, có được CORS cho phép không?”. Server phản hồi phù hợp:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET,POST,PUT,DELETE
Access-Control-Allow-Headers: Content-Type,X-CSRF-TOKEN
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 1800
Vary: Origin
~~~

Status cụ thể có thể khác theo implementation; **không cố định** rằng mọi preflight thành công phải trả 200 (có server dùng 204). Browser đối chiếu các CORS headers và chỉ khi phù hợp mới gửi actual request theo luồng fetch đó.

**Preflight thông thường không mang cookie/session authentication**, và không phải hành động POST. Vì vậy, nếu Security WebFilterChain yêu cầu login trước khi xử lý CORS, preflight có thể bị 401/403 mà actual request chưa có cơ hội chạy. Tài liệu Spring Security nhấn mạnh CORS phải xử lý **trước security**. Xem [Spring Security Reactive CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html).

### Trình duyệt không preflight mọi request

Một số GET và form POST đáp ứng tiêu chuẩn “simple request” có thể được gửi trực tiếp mà không có preflight. Không có preflight **không có nghĩa không áp dụng CORS cho response** và càng không có nghĩa bỏ CSRF.

CORS preflight cache (`Access-Control-Max-Age`) giúp giảm OPTIONS nhưng không phải thời hạn xác thực/CSRF token. Browser cache lời chấp thuận CORS, không cache quyền sở hữu Document #42.

## 6. Các headers CORS thường dùng

| Header | Chiều | Ý nghĩa |
|---|---|---|
| `Origin` | Browser → server | Origin của script phát request |
| `Access-Control-Request-Method` | Preflight → server | HTTP method dự định |
| `Access-Control-Request-Headers` | Preflight → server | Header script muốn gửi |
| `Access-Control-Allow-Origin` | Server → browser | Origin được phép đọc response theo CORS |
| `Access-Control-Allow-Methods` | Preflight response | Các method được chấp nhận |
| `Access-Control-Allow-Headers` | Preflight response | Các custom request headers được chấp nhận |
| `Access-Control-Allow-Credentials` | Response | Cho phép browser expose credentialed response khi giá trị true và các điều kiện khác hợp lệ |
| `Access-Control-Expose-Headers` | Response | Những response headers không mặc định mà JS được đọc |
| `Access-Control-Max-Age` | Preflight response | Thời gian browser cache kết quả preflight, có giới hạn theo browser |
| `Vary: Origin` | Response/cache | Giúp cache phân biệt nội dung CORS theo Origin khi cần |

**Không nhầm Allow-Headers với Expose-Headers:** cái trước nói request headers nào được phép gửi, cái sau nói JS được đọc response headers nào.

Nếu dùng CDN/reverse proxy cache, phải kiểm tra CORS response headers, `Vary`, credentialed responses và cache key. Một cấu hình trả `Access-Control-Allow-Origin` bằng cách **echo mọi Origin không kiểm soát** có thể mở dữ liệu cho các website khác nếu browser còn gửi cookie.

## 7. Cấu hình WebFlux bằng CorsWebFilter

Trong Spring WebFlux, có thể dùng `CorsWebFilter` với `CorsConfiguration` và `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource`. Ví dụ giả định frontend là một origin xác định:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsWebFilter;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
public class ReactiveCorsConfiguration {

    @Bean
    CorsWebFilter corsWebFilter() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(
                List.of("https://app.example.test"));
        cors.setAllowedMethods(
                List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"));
        cors.setAllowedHeaders(
                List.of("Content-Type", "X-CSRF-TOKEN",
                        "X-XSRF-TOKEN", "Authorization"));
        cors.setExposedHeaders(List.of("X-Request-ID"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return new CorsWebFilter(source);
    }
}
~~~

Đây là **class cấu hình tích hợp WebFlux**, cần Spring WebFlux, Spring Security và application dependencies. Hai origin đều là tên mẫu, không phải địa chỉ thực.

Giải thích lựa chọn:
- `setAllowedOrigins` allowlist origin cụ thể, không cho phép mọi website.
- `setAllowedMethods` liệt kê methods mà frontend thực sự dùng; không có nghĩa chúng đều được business authorization cho phép.
- `setAllowedHeaders` bao gồm headers frontend cần cho JSON và CSRF.
- `setAllowCredentials(true)` phù hợp khi browser cần cookie/session cross-origin **và** bạn chủ đích tin origin đó.
- `setExposedHeaders` chỉ expose một response header hỗ trợ quan sát; **không expose Authorization, Set-Cookie hoặc token**.
- `registerCorsConfiguration("/api/**",...)` gắn chính sách cho API path, không mở tất cả endpoints.
- `CorsWebFilter` xử lý CORS request/preflight trong WebFlux.

**Không đăng ký nhiều cơ chế CORS có rule mâu thuẫn** (CorsWebFilter, global WebFlux mapping, `@CrossOrigin`, gateway) mà không kiểm tra kết quả cuối cùng. Nếu gateway cũng thêm headers, có thể tạo duplicate/invalid `Access-Control-Allow-Origin`. Hãy chọn owner của CORS policy và integration-test với hạ tầng ingress thật.

## 8. CORS và WebFlux SecurityWebFilterChain là hai lớp

Một filter chain cho request API cookie/session:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveSecurityConfiguration {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/api/documents/**")
                    .hasAuthority("documents:read")
                .pathMatchers(HttpMethod.POST, "/api/documents/**")
                    .hasAuthority("documents:write")
                .anyExchange().denyAll()
            )
            // Không disable CSRF: mặc định được bật.
            .build();
    }
}
~~~

Đây là **snippet Spring Security WebFlux**, chưa phải app hoàn chỉnh: thiếu authentication provider, endpoints và cấu hình login. Nó minh họa yêu cầu authority chức năng trên GET/POST; không tự kiểm tra owner/tenant Document #42.

Nếu frontend gửi POST với cookie/session:
1. CORS filter xác nhận origin/method/headers theo chính sách.
2. Security kiểm tra CSRF token nếu POST thuộc diện bảo vệ.
3. Security xác thực actor và kiểm tra authority `documents:write`.
4. Service kiểm tra tenant, object ID, owner/grant và trạng thái dữ liệu.
5. Nếu đủ, mutation mới được thực thi.

Nếu POST bị 403, phải xác định **CSRF, authentication/authority hay business policy** gây lỗi. Đừng tắt CSRF hoặc bật `permitAll` ngay khi thấy 403.

### CORS với nhiều chain hoặc gateway

Một ứng dụng có thể có nhiều `SecurityWebFilterChain`, đặc biệt nếu chia API Bearer, admin session, actuator và public paths. CORS phải được áp dụng phù hợp **cho mọi route browser cần dùng**, không chỉ chain đầu tiên. Test toàn bộ kết hợp:
- Origin được phép/không được phép.
- Preflight có/không có authentication.
- Cookie/session vs bearer.
- Các HTTP method và custom headers.
- Route được gateway rewrite.
- Rule fallback `denyAll` hoặc authenticated theo chủ đích.

## 9. Credentialed CORS: không ghép allowCredentials với "*" origin

Với cross-origin browser requests dùng cookies:

~~~text
Access-Control-Allow-Credentials: true
Access-Control-Allow-Origin: https://app.example.test
~~~

Origin phải được xác định phù hợp; không cấu hình:

~~~java
cors.setAllowedOrigins(List.of("*"));
cors.setAllowCredentials(true);
~~~

Đây là **mẫu sai** theo ràng buộc Spring CORS / browser credential semantics. Spring Framework yêu cầu `allowOrigins` không dùng special wildcard `"*"` khi credentials enabled. Có `allowedOriginPatterns` cho những cấu hình match động, nhưng nó vẫn phải được giới hạn cẩn trọng và không nên trở thành một wildcard cho mọi origin không đáng tin.

CORS credentialed access có thể làm website được allowlist **đọc phản hồi cá nhân hóa** từ API nếu cookie được browser gửi. Vì vậy:
- Chỉ allowlist frontend được quản trị.
- Kiểm soát DNS/subdomain takeover, deployment preview domains và lifecycle origin.
- Không echo mọi `Origin` rồi thêm allow-credentials.
- Đừng đưa Origin vào mapping user/tenant authorization.
- Kiểm tra cookie `Secure`, `HttpOnly`, `SameSite`, domain/path phù hợp.
- Dùng TLS cho frontend/API thật; tránh mixed content.
- Nếu muốn CORS public chỉ đọc dữ liệu công khai, có thể không cần allowCredentials.

Không mặc định CORS cho phép cookies chỉ vì server trả allowCredentials: browser còn áp chính sách SameSite, third-party cookie policy và fetch credentials mode.

## 10. Kết hợp với @CrossOrigin và WebFluxConfigurer

Spring WebFlux có thể khai CORS ở handler mapping:
- `@CrossOrigin` trên controller/method.
- `WebFluxConfigurer.addCorsMappings(...)` cho global path mapping.
- `CorsWebFilter` trên toàn web filter pipeline.

Các cách này cùng giải quyết CORS nhưng **khác vị trí thực thi**. Spring Framework WebFlux docs có thể kết hợp global và local config (thường cộng dồn ở một số field, một số field cục bộ override).

Ví dụ mapping:

~~~java
@Configuration
public class WebFluxCorsMappings implements WebFluxConfigurer {
    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/public/**")
            .allowedOrigins("https://docs.example.test")
            .allowedMethods("GET");
    }
}
~~~

Đây là snippet tích hợp; cần imports và WebFlux runtime. Với ứng dụng Spring Security, đừng chỉ dựa vào annotation/controller mapping cho preflight mà **không xác minh CORS được xử lý trước security filter**. `CorsWebFilter` là lựa chọn rõ ràng cho các route cần được security cho đi qua preflight.

Tránh khai hai policy khác nhau cùng một path rồi dựa vào hành vi ngẫu nhiên. Tạo một source of truth, test phản hồi thực tế sau khi qua gateway/security/handler mapping.

## 11. CSRF là gì: cookie hợp lệ không chứng minh ý định của user

Một tấn công điển hình:

~~~text
1. Alice đăng nhập https://api.example.test
2. Browser lưu cookie session hợp lệ
3. Alice mở https://evil.example
4. Trang evil tự submit form POST tới API
5. Browser có thể tự mang cookie phù hợp
6. Nếu API chỉ check session/role:
   server hiểu request là của Alice và thực hiện thay đổi
~~~

**CSRF** lợi dụng credential được browser đính kèm tự động (*ambient authority*). Để chống, server yêu cầu một giá trị chống giả mạo mà website attacker **không thể tự đọc/sinh đúng** chỉ bằng cách tạo cross-site request.

Một CSRF token là một trong những biện pháp chính. Browser phải gửi token trong **header hoặc form field** không tự phát sinh trong forged request. Server đối chiếu với token expected được quản lý. Token không thay user authentication và không cho phép resource access nếu role/owner/tenant không đúng.

Bảo vệ còn cần:
- Không thực hiện mutation qua GET/HEAD/OPTIONS.
- Cookie SameSite/Secure/HttpOnly theo ngữ cảnh.
- Origin/Referer checking phù hợp nếu thiết kế; không thay token một cách thiếu xem xét.
- Bảo vệ XSS vì script độc hại trong origin hợp lệ có thể lấy token hoặc thực hiện hành động như user.
- Authentication/authorization theo action/resource vẫn bắt buộc.

**Có CORS không đồng nghĩa có CSRF protection.** CSRF là lớp kiểm tra riêng.

## 12. HTTP methods an toàn phải thực sự read-only

Spring Security mặc định áp CSRF cho các method được coi là không an toàn; các method như `GET`, `HEAD`, `OPTIONS` và `TRACE` thường được coi là safe trong matcher mặc định. Điều này dựa trên giả định **safe methods không thay đổi dữ liệu**.

Nếu API dùng:
~~~http
GET /api/accounts/42/delete
~~~
để xóa tài khoản, đó là thiết kế nguy hiểm: browser, crawler, prefetch hoặc link bị khai thác có thể kích hoạt side effect mà không qua CSRF guard mặc định.

Đúng hơn:
~~~http
DELETE /api/accounts/42
X-CSRF-TOKEN: <token-if-cookie-auth>
~~~

và service phải kiểm quyền DELETE trên đúng account.

Một POST nhận JSON vẫn có thể cần CSRF nếu browser tự gửi cookie/session; việc dùng `Content-Type: application/json` không tự cho phép bỏ CSRF. Content-type góp phần thay đổi CORS/preflight nhưng **không thay threat model** của ambient credentials.

### Cách kiểm sai phổ biến

“Mọi POST đã preflight thì chắc chắn an toàn” là sai. Preflight chỉ kiểm CORS origin/method/headers, không xác nhận chính request có CSRF token hợp lệ. Với cùng một origin được phép, XSS hoặc frontend bug vẫn có thể gửi request nguy hiểm.

## 13. CSRF mặc định trong Spring Security WebFlux

Trong Spring Security WebFlux, CSRF protection **được bật mặc định**. Các thành phần chính:

| Thành phần | Nhiệm vụ |
|---|---|
| `CsrfWebFilter` | Kiểm request thuộc diện CSRF, lấy và so khớp token expected với token gửi lên |
| `ServerCsrfTokenRepository` | Contract sinh/lưu/tải CSRF token cho WebFlux |
| `WebSessionServerCsrfTokenRepository` | Mặc định lưu expected token trong `WebSession` |
| `CookieServerCsrfTokenRepository` | Một cách lưu token qua cookie, thường cho frontend JS |
| `ServerCsrfTokenRequestHandler` | Đưa token vào exchange attributes, xử lý giá trị presented |
| `XorServerCsrfTokenRequestAttributeHandler` | Handler mặc định từ Spring Security 6.0, bảo vệ BREACH bằng masking |
| `ServerCsrfTokenRequestAttributeHandler` | Handler khác, có thể dùng khi cân nhắc compatibility/masking |

CSRF token được quản lý trong bối cảnh reactive. `CsrfWebFilter` cung cấp một `Mono<CsrfToken>` trong attributes của `ServerWebExchange` với khóa `CsrfToken.class.getName()` theo tài liệu.

**Ba trạng thái khác nhau:**
- `WebSession`: nơi có thể lưu **expected token** qua nhiều requests.
- `ServerWebExchange attribute`: cách request **hiện tại** tiếp cận token publisher.
- `Reactor Context`: nơi reactive execution truyền dữ liệu theo subscription; không phải token repository mặc định.

Không lưu token expected vào một singleton field dùng chung mọi user. Không tự serialize toàn bộ `WebSession`/token vào log.

## 14. Mặt nạ token và BREACH trong phiên bản mới

Tài liệu Spring Security WebFlux nêu:
- Spring Security 5.8 dùng `ServerCsrfTokenRequestAttributeHandler` làm mặc định.
- Kể từ Spring Security 6.0, mặc định là `XorServerCsrfTokenRequestAttributeHandler` để hỗ trợ chống BREACH.

BREACH liên quan đến rò dữ liệu bí mật qua tương quan kích thước của response nén khi token xuất hiện trong nội dung phản hồi. XOR-based masking giúp giá trị được **hiển thị** khác nhau giữa requests dù token expected được quản lý theo repository.

Vì vậy, hãy phân biệt:
1. **Expected token** ở WebSession/cookie repository.
2. **Exposed/masked token** đưa vào form/template.
3. **Presented token** từ header hoặc form field khi user thực hiện POST.
4. **Request handler** giải mã/resolve token presented theo cơ chế đã cấu hình.

Nếu lấy **raw XSRF-TOKEN cookie** rồi gửi nguyên qua header trong SPA, phải xác minh cách `XorServerCsrfTokenRequestAttributeHandler` của phiên bản đang dùng xử lý nó. Một cấu hình cookie JS tự đọc + raw header có thể cần **custom request handler phù hợp** để nhận raw cookie token cho header nhưng vẫn mask token khi expose trong response. Đừng hạ handler về không mask chỉ để hết lỗi mà chưa đánh giá bảo vệ BREACH.

Chỉ dùng token đúng contract của CSRF request handler của project. Test actual browser flow qua login/logout và request JSON.

## 15. Trang HTML form: đưa CSRF token vào form field

Với server-rendered pages:
~~~html
<form method="post" action="/api/profile">
  <input type="hidden" name="_csrf" value="csrf-token-from-server">
  <button type="submit">Save</button>
</form>
~~~

Đây là **HTML minh họa**; giá trị thật phải được framework/template lấy từ token request hiện hành, không hard-code token vào mã nguồn. Với Thymeleaf tích hợp Spring Security, token form có thể được thêm tự động khi cấu hình đúng.

Với WebFlux, token có thể được lấy từ `ServerWebExchange`:

~~~java
import reactor.core.publisher.Mono;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.server.ServerWebExchange;

public Mono<CsrfToken> csrfToken(ServerWebExchange exchange) {
    Mono<CsrfToken> token =
            exchange.getAttribute(CsrfToken.class.getName());
    return token != null ? token : Mono.empty();
}
~~~

Đây là **snippet tích hợp trong component/controller WebFlux**, cần có Spring Security CSRF enabled; không nên coi `Mono.empty()` là một token hợp lệ. Trong một endpoint buộc phải expose token, trường hợp token publisher thiếu phải được xử lý theo thiết kế, không trả chuỗi ngẫu nhiên rồi bỏ CSRF.

Không đặt CSRF token trong URL query string, nơi nó dễ lộ qua browser history, referrer, proxy logs và analytics. Ưu tiên hidden form field hoặc header. Nếu form có token trong response HTML, cần kiểm soát cache và XSS.

## 16. AJAX/JSON: CSRF token thường nằm trong header

Frontend gửi một actual POST:

~~~http
POST /api/documents/42 HTTP/1.1
Origin: https://app.example.test
Content-Type: application/json
Cookie: SESSION=...
X-CSRF-TOKEN: <token-from-trusted-ui>

{"title":"Updated title"}
~~~

Server phải:
1. Xử lý CORS theo origin/method/headers.
2. Nhận authentication cookie/session hợp lệ.
3. So khớp presented CSRF token với expected token.
4. Kiểm authority DOCUMENT_WRITE và object authorization Document #42.
5. Thực thi transaction nếu các điều kiện đều đúng.

Không có CSRF token ⇒ POST với session/cookie auth có thể bị **403** trước khi business service chạy. Có CSRF token đúng nhưng caller không có quyền WRITE ⇒ vẫn **403/404** theo policy. CORS chấp nhận origin không thể biến một token sai thành token đúng.

Với SPA:
- Có thể dùng header `X-CSRF-TOKEN` hoặc `X-XSRF-TOKEN` tùy repository/request handler.
- Token nên được frontend lấy thông qua kênh đáng tin cùng site/origin được phép.
- Cookie readable bởi JS là trade-off, cần CSP/XSS defense và scoping cookie.
- Khi login/logout, session/token có thể thay đổi; client phải cập nhật token.
- Các lệnh fetch cần credentials mode phù hợp nếu API dựa vào cookie và CORS allowCredentials.
- Nếu dùng Axios/Angular tự đọc cookie, kiểm tra chính xác token raw/masked behavior của Spring Security version.
- Không log cookie, CSRF header hay JSON chứa dữ liệu nhạy cảm.

## 17. CookieServerCsrfTokenRepository: đọc từ XSRF-TOKEN

Nếu SPA cần token qua cookie, Spring Security cung cấp `CookieServerCsrfTokenRepository`:

~~~java
import org.springframework.security.web.server.csrf.CookieServerCsrfTokenRepository;

@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .csrf(csrf -> csrf.csrfTokenRepository(
                CookieServerCsrfTokenRepository.withHttpOnlyFalse()))
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/**").authenticated()
            .anyExchange().denyAll()
        )
        .build();
}
~~~

**Snippet tích hợp**, chưa phải cấu hình production hoàn chỉnh. `withHttpOnlyFalse()` cho JavaScript đọc cookie token; Spring Security docs khuyến nghị **không dùng** tùy chọn này khi JavaScript không cần đọc cookie trực tiếp. Có thể dùng `new CookieServerCsrfTokenRepository()` để giữ HttpOnly.

Tên theo convention:
- Cookie: `XSRF-TOKEN`.
- Header: `X-XSRF-TOKEN`.
- Form parameter: `_csrf` trong đường xử lý hỗ trợ.

**Điểm tương thích quan trọng:** đoạn snippet trên chỉ cấu hình **lưu token vào cookie**, chưa chứng minh SPA gửi raw header được chấp nhận bởi handler XOR mặc định của Spring Security 6+. Nếu cần cookie-to-header, thiết kế `ServerCsrfTokenRequestHandler` phù hợp và integration-test toàn flow; có thể cần handler phối hợp lấy raw token từ header và xử lý masked token trong HTML. Đừng lấy mã Servlet `SpaCsrfTokenRequestHandler` rồi dán vào Reactive project mà không đổi type.

Không dùng `withHttpOnlyFalse()` như cách “khắc phục mọi lỗi CSRF”. Nó thay đổi khả năng JS đọc token và có ảnh hưởng security; cần đánh giá XSS threat model.

## 18. WebSession không giống Reactor Context hay request attribute

Ba khái niệm rất dễ bị dùng lẫn:

| Đối tượng | Phạm vi thông thường | Dữ liệu nên lưu | Cảnh báo |
|---|---|---|---|
| `ServerWebExchange` | Một HTTP exchange/request-response | Request metadata, attributes phục vụ filter/handler | Không tái dùng object giữa requests |
| `exchange.getAttributes()` | Thuộc tính gắn với exchange hiện tại | Correlation ID, kết quả phân tích request đã xác minh | Header client tự khai không tự thành trusted |
| `Reactor Context` | Một subscriber/reactive chain | Security context, tracing/correlation, data flow scope | Không phải ThreadLocal; phụ thuộc subscription/context propagation |
| `WebSession` | Trạng thái session qua nhiều requests | Session ID-related state, expected CSRF token mặc định | Không chứa toàn bộ object domain/role stale không hạn |
| `SecurityContext` | Authentication đang áp dụng | Principal/authorities được authentication pipeline cấp | Không tự chứng minh resource-level quyền |
| Singleton Spring bean | Toàn app instance | Dependencies immutable, stateless services | Không đặt mutable currentUser/currentTenant vào field |

**Request scope ≠ WebSession scope.** Một request bị kết thúc không có nghĩa WebSession cũng kết thúc; một user/session có thể phát nhiều request đồng thời. Không dùng field như:

~~~java
private String currentTenant;
private Authentication currentUser;
~~~

trên singleton `@Service` hoặc `@Component` để lưu “request hiện tại”. Hai request đồng thời sẽ ghi đè trạng thái lẫn nhau. Truyền verified context dưới dạng method parameters, exchange attribute hoặc Reactor Context theo nhu cầu.

Đừng mặc định một Servlet `RequestContextHolder`/`HttpServletRequest` ThreadLocal luôn có trong WebFlux; reactive execution có thể chuyển thread và dùng nhiều subscriptions. Việc dùng `@RequestScope`/scoped proxy cũng không nên được giả định tương đương servlet request binding nếu chưa kiểm tra khả năng hỗ trợ và lifecycle thực tế của WebFlux setup. Ưu tiên những cơ chế reactive công khai và test propagation.

## 19. ReactiveSecurityContextHolder và Reactor Context

Spring Security WebFlux sử dụng Reactor Context để truyền security context theo reactive chain, thay vì chỉ dựa vào một ThreadLocal từ đầu đến cuối request.

Ví dụ đọc principal:

~~~java
import reactor.core.publisher.Mono;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

public Mono<String> currentSubject() {
    return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());
}
~~~

Đây là **snippet tích hợp Reactor/Spring Security**, không phải class chạy độc lập. Nếu publisher không có security context, kết quả có thể là `Mono.empty()`. Với operation cần authentication, **không chuyển empty thành user mặc định**.

Một custom service nên nhận `Mono<Authentication>` hoặc principal từ method đã xác thực khi có thể, không tự đọc raw header. Với việc kiểm role, WebFlux HTTP manager và reactive method security làm việc với authenticated context; domain service vẫn cần kiểm tenant/object.

### Reactor Context không phải biến toàn cục

~~~java
Mono<String> operation = Mono.deferContextual(ctx -> {
    String requestId = ctx.getOrDefault(
            "trusted.requestId", "not-set");
    return Mono.just(requestId);
});

Mono<String> withContext = operation.contextWrite(
        ctx -> ctx.put("trusted.requestId", "req-123"));
~~~

Đây là **mảnh ghép reactive Java**, có thể dùng trong chương trình Reactor đã cấu hình. `contextWrite` tạo context áp dụng theo subscription/upstream semantics, không set global variable cho mọi request.

Một giá trị context chỉ là **dữ liệu**: đặt `tenantId=north` vào Reactor Context không tự chứng minh actor có membership north. Tầng authentication/tenant resolver phải xác minh rồi mới đưa vào trusted context.

## 20. WebFilter gắn correlation ID cho từng exchange

Ví dụ một filter độc lập về trách nhiệm: tạo request ID và truyền trong exchange attributes + Reactor Context cho xử lý bất đồng bộ.

~~~java
import java.util.UUID;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
@Order(-100)
public class RequestCorrelationWebFilter implements WebFilter {

    public static final String REQUEST_ID_KEY = "trusted.requestId";

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {
        String requestId = UUID.randomUUID().toString();

        exchange.getAttributes().put(REQUEST_ID_KEY, requestId);
        exchange.getResponse().getHeaders().set("X-Request-ID", requestId);

        return chain.filter(exchange)
            .contextWrite(ctx -> ctx.put(REQUEST_ID_KEY, requestId));
    }
}
~~~

Đây là **class Spring WebFlux tích hợp**, chưa có application configuration/test. `@Order(-100)` chỉ là ví dụ về precedence; phải kiểm tra thứ tự thật với security/CORS filters của dự án, không giả định một số cố định bảo đảm mọi filter relation.

Lợi ích:
- Không dùng mutable field trên singleton để giữ ID.
- Request ID tạo phía server, không tin giá trị `X-Request-ID` bất kỳ từ client.
- Handler/service reactive có thể đọc giá trị từ exchange attribute hoặc `Mono.deferContextual`.
- Có thể nối audit và tracing mà không log credentials.

**Lưu ý:** lưu thêm correlation ID trong response header không có nghĩa mọi JS frontend cross-origin sẽ đọc được. Nếu cần, phải include header vào `Access-Control-Expose-Headers`. Header này không chứa secret hay quyền.

Không đặt CSRF expected token, raw JWT hay dữ liệu nhạy cảm vào một context hay response header chỉ để debug. Correlation ID cũng không phải capability để xem log; endpoint tra cứu cần authorization riêng.

## 21. Per-request tenant phải đến từ authenticated scope

Giả sử request:

~~~http
GET /api/tenants/north/documents/42
X-Tenant-ID: north
Authorization: Bearer <access-token>
Origin: https://app.example.test
~~~

Ba giá trị cần phân biệt:
- `Origin`: browser CORS context, **không xác minh role**.
- `X-Tenant-ID` hoặc tenant trong path: **tenant target do client chọn**.
- `Authorization`: token phải được resource server xác thực; identity/claims sau validation mới dùng được.

Một resolver an toàn:
1. Lấy authenticated issuer+subject hoặc internal principal.
2. Đọc tenant target từ path/header có validate format/allowlist phù hợp.
3. Tra active membership/entitlement actor tại tenant target.
4. Ràng buộc role/authority **trong chính tenant**.
5. Khi lấy Document #42, query `id AND tenant AND owner/allowedScope`.
6. Khi ghi, dùng scoped mutation hoặc transaction/lock/version policy phù hợp.

Không đặt `currentTenant = request.getHeaders().getFirst("X-Tenant-ID")` rồi coi nó là trusted tenant cho truy vấn RLS nếu chưa xác minh.

**CORS allowed origin không cấp membership:** frontend hợp lệ vẫn có thể hiển thị một user không thuộc tenant north. CSRF token hợp lệ cũng không cấp membership; nó chỉ là bằng chứng chống request giả mạo trong threat model tương ứng.

## 22. Tránh rò context giữa subscriptions, cache và async

Một reactive service dễ mắc lỗi khi cache toàn bộ `Mono<Authentication>`, `Mono<Document>` hoặc `SecurityContext` ở singleton dùng chung nhiều request.

Anti-pattern:

~~~java
@Service
public class UnsafeContextCache {
    private Mono<String> cachedUser;

    public Mono<String> userName() {
        if (cachedUser == null) {
            cachedUser = ReactiveSecurityContextHolder.getContext()
                .map(ctx -> ctx.getAuthentication().getName())
                .cache();
        }
        return cachedUser;
    }
}
~~~

Đây là **mẫu sai**: cache publisher kết quả security context của một subscription rồi dùng lại cho người gọi khác. Dù reactive context có cơ chế isolation, **.cache() trên publisher chia sẻ** có thể biến dữ liệu một actor thành dữ liệu actor khác nếu scope không đúng.

Cách khắc phục:
- Lấy subject/tenant cho **mỗi request/subscription**.
- Truyền `VerifiedActor`/`VerifiedTenantScope` qua method parameters hoặc context gắn riêng.
- Không dùng `.cache()` toàn cục cho kết quả phụ thuộc user/tenant/action.
- Nếu cache authorization data, key theo issuer+subject+tenant+action+resource+revision với TTL/revoke phù hợp.
- Không dùng `subscribe()` thủ công trong service authorization; để framework điều khiển subscription/context.
- Nếu chuyển sang Reactor Scheduler/thread khác, test Context propagation thay vì dựa ThreadLocal.
- Với callback không thuộc reactive chain, truyền đủ context được xác minh qua message/command có kiểm soát, không tin thread-local stale.

## 23. CSRF khi dùng JWT Bearer token khác cookie session

Có thể cân nhắc tắt CSRF cho một API **thực sự stateless** nếu:
- Client gửi Bearer token tường minh qua `Authorization` header.
- Browser **không tự** đính kèm credential đó cho cross-site request như cookie hoặc browser-managed Basic auth.
- Không có session/cookie auth fallback cho cùng protected routes.
- Không có CSRF-sensitive authentication/refresh/logout endpoints dùng cookie và side effect.
- Không có các thao tác dựa trên ambient credentials khác (client certificates, proxy auth/cookie flows) mà threat model cần bảo vệ.
- CORS và object authorization vẫn được áp dụng đúng.

Ví dụ tách biệt cho một **Bearer-only resource API đã được xác minh stateless**:

~~~java
import static org.springframework.security.config.Customizer.withDefaults;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class BearerOnlyApiSecurity {

    @Bean
    SecurityWebFilterChain bearerApi(ServerHttpSecurity http) {
        return http
            .csrf(csrf -> csrf.disable())
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("SCOPE_reports.read")
                .pathMatchers(HttpMethod.POST, "/api/reports/**")
                    .hasAuthority("SCOPE_reports.write")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

**Mã cấu hình minh họa, không phải khuyến nghị tắt CSRF mặc định.** Bạn chỉ nên áp dụng khi kiểm chứng toàn bộ yêu cầu kể trên, biết Spring Security/Boot version, đã cấu hình issuer/JWK/audience và test thực tế. Nếu cùng ứng dụng vẫn có form login, cookie session, SPA refresh cookie hoặc Basic auth, không copy nguyên việc `csrf.disable()` sang mọi filter chain.

Ngoài ra, JWT có thể được lưu trong cookie; khi token được browser tự gửi bằng cookie, **đó vẫn là ambient credential** và nguy cơ CSRF quay lại. Cách lưu token quan trọng hơn việc nó được gọi tên “JWT”.

## 24. Cookie SameSite, HttpOnly và Secure giúp gì?

Một session cookie có thể được thiết lập với các thuộc tính phù hợp:

~~~http
Set-Cookie: SESSION=opaque-session-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Mô tả:
- `Secure` hạn chế cookie chỉ qua kết nối an toàn phù hợp.
- `HttpOnly` khiến JS không đọc cookie qua `document.cookie`; không chặn browser gửi cookie.
- `SameSite=Lax/Strict/None` điều khiển một số tình huống gửi cookie cross-site; `SameSite=None` đi kèm yêu cầu Secure theo browser hiện đại.
- `Domain`/`Path` ảnh hưởng phạm vi cookie, cần tránh mở quá rộng cho subdomains ngoài kiểm soát.
- Session token cần đủ entropy, rotation và bảo vệ khỏi fixation/hijacking.

Cookie SameSite là **defense in depth**, không thay CSRF token trong mọi browser/workflow. Nếu frontend và API ở hai subdomain cùng site nhưng khác origin, SameSite có thể không chặn request của subdomain bị compromise. Tương tự, XSS trên origin được tin có thể gửi CSRF token hợp lệ.

Không tự tin `HttpOnly` làm CSRF bất khả thi; HttpOnly chống **JS đọc cookie**, không ngăn tự gửi cookie trong request.

## 25. CSRF khi đăng nhập, đăng xuất và tải file

**Login CSRF:** Một hành vi đăng nhập bị giả mạo có thể khiến victim browser vào một session không mong muốn. Spring Security docs khuyến nghị bảo vệ request login bằng CSRF.

**Logout CSRF:** Tránh cho một GET link gây logout ngoài ý muốn. Theo mặc định Spring Security WebFlux áp dụng logout qua POST cần token phù hợp khi CSRF enabled.

**Upload multipart:** Nếu token chỉ nằm trong multipart body, hệ thống có thể phải parse/ghi tạm upload trước khi kiểm token. Với frontend JS, gửi CSRF token bằng header thường dễ kiểm tra hơn và giảm rủi ro xử lý body sớm. Nhưng phải bảo vệ toàn bộ upload pipeline bằng size limits, content validation, malware scanning khi cần và authorization trên resource.

**File download GET:** Download thường là safe read; không cần CSRF chỉ vì nó là GET, nhưng phải kiểm authentication/object permission và tránh presigned URL có thời hạn quá dài. Nếu GET download đồng thời tạo một side effect quan trọng, cần tách thiết kế/đánh giá an toàn.

**Streaming/SSE/WebSocket:** Một kết nối dài có handshake/upgrade và browser auth context riêng; đừng suy luận rằng mọi luồng WebSocket/SSE được bảo vệ y hệt POST JSON. Tìm security requirements phù hợp cho handshake, origin, authentication và authorization từng message, đặc biệt khi dùng cookie. CORS HTTP không tự thay WebSocket origin checks hoặc message-level authorization.

## 26. Vì sao một POST có thể bị 403 dù đã CORS allow?

Một bảng chẩn đoán:

| Dấu hiệu | Khả năng | Cách kiểm |
|---|---|---|
| OPTIONS trả 401/403 | Preflight bị Security chặn hoặc CORS rule sai | Kiểm CorsWebFilter/order và allow origin/method/headers |
| Browser báo “blocked by CORS policy” | Thiếu/mâu thuẫn CORS response headers | Xem OPTIONS + actual headers; không mặc định backend authorization lỗi |
| OPTIONS thành công, POST 403 | CSRF token sai/thiếu hoặc quyền không đủ | Kiểm CSRF logs, authentication, authority, object policy |
| POST cùng origin được, khác origin bị CORS | Origin không trong allowlist hoặc credentials config sai | So scheme+host+port, allowedOrigins và fetch credentials |
| GET được, POST 403 | CSRF enabled, thiếu token; hoặc POST yêu cầu quyền WRITE | Test với token hợp lệ và role phù hợp |
| User khác tenant đọc được | Thiếu tenant/object authorization | Kiểm scoped repository/service, **không chỉnh CORS để sửa** |
| Curl gọi được, browser không đọc response | CORS chỉ tác động browser | Kiểm preflight/response headers |
| Token hợp lệ nhưng 401 | JWT validation/audience/issuer/session mismatch | Kiểm authentication converter và authn failure |
| POST SPA với XSRF cookie raw bị 403 | Request handler masking/CSRF token version mismatch | Test expected token và handler; không tắt CSRF tùy tiện |

Một sai lầm là dùng cùng từ “cross-origin bị chặn” cho cả CORS và 403 của CSRF. Hãy tách **preflight** khỏi **actual request** trong Network tab hoặc integration tests.

## 27. WebTestClient: kiểm tra CSRF trong WebFlux

Spring Security Test hỗ trợ `WebTestClient`. Ví dụ:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class CsrfWebFluxTests {

    @Autowired
    WebTestClient client;

    @Test
    void postWithoutCsrfIsRejected() {
        client.mutateWith(mockUser().authorities(
                new org.springframework.security.core.authority
                    .SimpleGrantedAuthority("documents:write")))
            .post().uri("/api/documents")
            .bodyValue("{\"title\":\"Sample\"}")
            .header("Content-Type", "application/json")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void postWithCsrfPassesSecurityGate() {
        client.mutateWith(mockUser().authorities(
                new org.springframework.security.core.authority
                    .SimpleGrantedAuthority("documents:write")))
            .mutateWith(csrf())
            .post().uri("/api/documents")
            .bodyValue("{\"title\":\"Sample\"}")
            .header("Content-Type", "application/json")
            .exchange()
            .expectStatus().is2xxSuccessful();
    }
}
~~~

**Đây là snippet integration test**, cần Spring Boot WebFlux/Security Test/JUnit và controller POST `/api/documents` thực trả 2xx với payload hợp lệ sau khi authorization. Nếu controller trả 201/204, assertion 2xx vẫn chấp nhận; nếu app validation hoặc resource policy không cho phép, cần fixture phù hợp.

Lưu ý khi test:
- Security test context phải được gắn đúng với WebTestClient; khi bind thủ công có thể cần `springSecurity()` test configurer.
- `mutateWith(csrf())` là **CSRF test helper** để kiểm security behavior, không thay test cookie/SameSite/real token negotiation với browser.
- Mock principal bỏ qua một phần authentication provider; cần ít nhất test khác đi qua login/JWT conversion thật.
- Nếu filter chain được cấu hình `csrf.disable()` cho Bearer-only API, test trên sẽ không kiểm CSRF nữa; cần test ngữ cảnh tương ứng.
- Không chỉ assert status: denied request phải không tạo document, event hoặc side effect.
- Với requests GET/HEAD, token không bắt buộc theo matcher mặc định, nhưng authentication/authority vẫn bắt buộc nếu route yêu cầu.

## 28. Test CORS preflight đúng cách

Một integration test cần gửi **preflight giả lập** với Origin, requested method và requested headers:

~~~http
OPTIONS /api/documents/42
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Expected:
- Response cho phép đúng origin đã allowlist.
- Header allow methods có POST; allow headers có những headers đã yêu cầu.
- Preflight không đòi cookie/session hoặc CSRF token.
- Một Origin ngoài allowlist không được phản hồi bằng CORS headers cho phép nó.
- Requested method DELETE ở endpoint chỉ allow GET/POST không được CORS chấp thuận.
- Header tùy ý không nằm allowlist bị từ chối trong preflight tương ứng.
- Credentialed response không dùng wildcard `Access-Control-Allow-Origin: *`.
- Actual POST vẫn cần authn/authz/CSRF theo policy ngay cả khi preflight PASS.

Một request curl để quan sát:

~~~bash
curl -i -X OPTIONS 'https://api.example.test/api/documents/42' \
  -H 'Origin: https://app.example.test' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,x-csrf-token'
~~~

**Không thể dùng curl như bằng chứng browser đã enforce CORS**: curl không áp Same-Origin Policy. Nó chỉ giúp xem headers server; phải kiểm tiếp trong browser hoặc WebTestClient và gateway proxy tương ứng.

Nếu CORS cấu hình ở ingress/CDN thay vì app, test cả deployment path thật. Một preflight successful ở localhost chưa bảo đảm ingress không xóa response headers ở production.

## 29. Java 17 độc lập: phân biệt preflight, CSRF và tenant authorization

Đây là **demo Java 17 thuần, không sử dụng Spring**. Nó không tự xác thực danh tính, không triển khai CORS browser protocol và không tạo token cryptographically secure; mục đích là chứng minh các câu hỏi độc lập:
1. Preflight origin/method/headers có được chấp thuận không?
2. Một actual request có authentication không?
3. Với cookie-based unsafe method, CSRF token đã được trình bày đúng chưa?
4. Actor được xác minh thuộc tenant sở hữu resource không?

Tạo file `ReactiveRequestSecurityDemo.java`:

~~~java
import java.util.Objects;
import java.util.Set;

public class ReactiveRequestSecurityDemo {
    private static final String TRUSTED_ORIGIN =
            "https://app.example.test";

    record Request(
            String method,
            String actorTenant,
            String resourceTenant,
            boolean authenticated,
            boolean ambientCredentials,
            String expectedCsrf,
            String providedCsrf) { }

    static boolean preflightAllowed(
            String origin,
            String requestedMethod,
            Set<String> requestedHeaders) {

        Set<String> allowedMethods =
                Set.of("GET", "POST", "PUT", "DELETE");
        Set<String> allowedHeaders =
                Set.of("content-type", "x-csrf-token", "authorization");

        return TRUSTED_ORIGIN.equals(origin)
                && allowedMethods.contains(requestedMethod)
                && requestedHeaders != null
                && allowedHeaders.containsAll(requestedHeaders);
    }

    static boolean unsafe(String method) {
        return Set.of("POST", "PUT", "PATCH", "DELETE")
                .contains(method);
    }

    static String handle(Request request) {
        if (request == null || !request.authenticated()) {
            return "UNAUTHENTICATED";
        }

        if (request.ambientCredentials()
                && unsafe(request.method())
                && (request.expectedCsrf() == null
                    || request.expectedCsrf().isBlank()
                    || !Objects.equals(
                        request.expectedCsrf(),
                        request.providedCsrf()))) {
            return "CSRF_BLOCKED";
        }

        if (request.actorTenant() == null
                || request.resourceTenant() == null
                || !request.actorTenant().equals(
                    request.resourceTenant())) {
            return "AUTHZ_BLOCKED";
        }

        return "ALLOW";
    }

    public static void main(String[] args) {
        Set<String> headers =
                Set.of("content-type", "x-csrf-token");

        System.out.println("preflight-valid="
                + preflightAllowed(
                    TRUSTED_ORIGIN, "POST", headers));
        System.out.println("preflight-evil-origin="
                + preflightAllowed(
                    "https://evil.example", "POST", headers));
        System.out.println("preflight-unknown-header="
                + preflightAllowed(
                    TRUSTED_ORIGIN, "POST",
                    Set.of("x-internal-secret")));

        Request cookiePost = new Request(
                "POST", "north", "north",
                true, true, "csrf-123", null);

        System.out.println("cookie-post-without-token="
                + handle(cookiePost));
        System.out.println("cookie-post-valid="
                + handle(new Request(
                    "POST", "north", "north",
                    true, true, "csrf-123", "csrf-123")));
        System.out.println("cookie-post-cross-tenant="
                + handle(new Request(
                    "POST", "north", "south",
                    true, true, "csrf-123", "csrf-123")));
        System.out.println("cookie-get="
                + handle(new Request(
                    "GET", "north", "north",
                    true, true, "csrf-123", null)));
        System.out.println("bearer-post="
                + handle(new Request(
                    "POST", "north", "north",
                    true, false, null, null)));
        System.out.println("anonymous-post="
                + handle(new Request(
                    "POST", "north", "north",
                    false, true, "csrf-123", null)));
    }
}
~~~

Lệnh chạy:

~~~bash
javac ReactiveRequestSecurityDemo.java
java ReactiveRequestSecurityDemo
~~~

Stdout chính xác:

~~~text
preflight-valid=true
preflight-evil-origin=false
preflight-unknown-header=false
cookie-post-without-token=CSRF_BLOCKED
cookie-post-valid=ALLOW
cookie-post-cross-tenant=AUTHZ_BLOCKED
cookie-get=ALLOW
bearer-post=ALLOW
anonymous-post=UNAUTHENTICATED
~~~

Giải thích:
- Preflight hợp lệ được chấp thuận **nhưng chưa nói user được phép POST tài liệu**.
- Origin độc hại hoặc header ngoài allowlist không được preflight chấp thuận.
- Cookie POST thiếu token bị CSRF_BLOCKED.
- Cookie POST có token nhưng actor thuộc tenant khác vẫn AUTHZ_BLOCKED.
- Cookie GET không đòi CSRF trong mô hình safe method **nhưng vẫn cần authentication/authorization**.
- Bearer POST ở ví dụ không dùng ambient credential nên không áp token CSRF theo mô hình stateless-only; đây **không** là lời khuyên bỏ CSRF cho mọi JWT.
- Anonymous POST không được thực hiện.

**Giới hạn demo:** Đây chỉ là mô phỏng kiểm tra điều kiện. CORS thật do browser/server headers thực hiện; CSRF token thật phải có entropy, repository, masking/request handler và so khớp an toàn theo framework; authorization thật phải dùng authentication và data source đáng tin. Hệ thực tế còn xử lý redirect, cookies, preflight, timeouts, method override và CSRF/XSS threat model.

## 30. Test matrix cho ứng dụng Reactive

| Tình huống | CORS | CSRF | Authn/Authz | Kết quả kỳ vọng |
|---|---|---|---|---|
| Browser preflight allowed origin + POST headers | PASS | Không áp | Không cần cookie | OPTIONS được xử lý thành công |
| Preflight Origin không cho phép | REJECT | Không áp | Không liên quan | Browser không được phép đọc/send actual theo preflight |
| GET từ allowed origin, authenticated | PASS | Safe method | READ scope cần đủ | Đọc nếu đúng object |
| POST cookie, Origin allowed, token thiếu | PASS | FAIL | Có thể có session | Chặn mutation |
| POST cookie, token đúng, role thiếu | PASS | PASS | FAIL | Chặn mutation |
| POST cookie, token đúng, role đủ, tenant sai | PASS | PASS | Object scope FAIL | Không ghi resource |
| POST cookie, token đúng, role/object đủ | PASS | PASS | PASS | Cho operation, phụ thuộc business validation |
| POST với Bearer-only auth từ allowed origin | PASS | Theo design stateless | Token/authority bắt buộc | Chỉ cho khi resource policy đúng |
| HTTP Basic/browser ambient credential không CSRF | CORS không chữa | Rủi ro CSRF | Có thể authn PASS | Không tắt CSRF tùy tiện |
| GET endpoint vô tình mutate | Có thể PASS | Không check theo safe matcher | Có thể authn PASS | Lỗi thiết kế phải sửa |
| Cookie `SameSite=None` ở cross-site SPA | Theo allowlist | Vẫn cần CSRF nếu ambient | Session/authorization | Kiểm tra toàn browser flow |
| JWT trong cookie | Theo allowlist | CSRF risk tồn tại | JWT validation | Không bỏ CSRF chỉ vì token là JWT |
| WebSession hết hạn | Có thể PASS | Token expected thay đổi/không còn | Authn có thể fail | Không execute, refresh/login theo flow |
| CSRF token masked vs raw header mismatch | PASS | FAIL | Authn có thể PASS | 403, sửa request handler tương thích |
| CORS PASS nhưng protected 403 | PASS | Có thể PASS | FAIL | Đây là authorization, không “CORS lỗi” |
| Origin allowed, no authenticated user | PASS | Theo method | FAIL | 401/challenge hoặc redirect |
| API gateway xóa CORS response header | Browser FAIL | App có thể xử lý | Tùy | Fix gateway, không bật permitAll |
| Request context singleton dùng chung | Không liên quan | Không liên quan | Rò actor/tenant | Bắt lỗi qua concurrency test |
| Reactor context bị mất qua task | Không liên quan | Không liên quan | Missing auth | Fail closed, không user mặc định |

**Cần test ở ba cấp:** unit test cấu hình/logic, WebTestClient integration với Spring Security và browser E2E thực (cookie, SameSite, credentials mode, preflight, gateway). Không thể chỉ dùng một cấp để chứng minh mọi cơ chế.

## 31. Những lỗi phổ biến và cách sửa

**1. CORS lỗi thì thêm `permitAll()` cho mọi API.** Việc này mở authorization rộng. **Sửa:** cấu hình CORS preflight đúng vị trí, giữ rule security.

**2. Có CORS allowlist thì tắt CSRF.** CORS không ngăn mọi cross-site form request. **Sửa:** duy trì CSRF nếu browser tự gửi session/cookie/Basic credentials.

**3. Tắt CSRF chỉ vì API có JWT.** Nếu JWT trong cookie hoặc có session fallback, nguy cơ CSRF vẫn tồn tại. **Sửa:** phân tích cách credential được gửi.

**4. Dùng `Access-Control-Allow-Origin: *` với credentials.** Không phù hợp browser/Spring constraints. **Sửa:** allowlist origins cụ thể.

**5. Echo Origin tùy ý và bật allowCredentials.** Website độc hại có thể đọc response được cá nhân hóa khi browser gửi cookie. **Sửa:** origin trust review, DNS/subdomain hygiene.

**6. Quên xử lý OPTIONS preflight trước authentication.** Browser không gửi actual request. **Sửa:** CorsWebFilter phù hợp, kiểm order.

**7. Chỉ thêm `OPTIONS permitAll` mà không có CORS headers.** Browser vẫn không được phép. **Sửa:** cấu hình xử lý preflight thực.

**8. Chỉ allow GET, POST nhưng frontend dùng PUT/PATCH hoặc custom X-CSRF-TOKEN.** Preflight thất bại. **Sửa:** allow đúng methods/headers cần dùng.

**9. Xem `X-Tenant-ID` là verified tenant.** Client có thể đổi header. **Sửa:** kiểm membership/role và object tenant ở server.

**10. Dùng mutable currentUser field trên singleton bean.** Request cạnh tranh làm lẫn context. **Sửa:** exchange/Reactor Context và method parameters.

**11. Dựa ThreadLocal của Servlet trong WebFlux.** Reactive flow chuyển thread/subscription. **Sửa:** `ReactiveSecurityContextHolder` và Reactor Context.

**12. Cache publisher authentication dùng chung.** Identity của một request bị dùng lại cho request khác. **Sửa:** context per subscription, cache key/scope chính xác.

**13. Lấy raw XSRF-TOKEN cookie gửi lên nhưng handler mặc định đòi masked token.** CSRF 403 khó hiểu. **Sửa:** xác định contract handler và test SPA flow, không tắt bảo vệ.

**14. Dùng `CookieServerCsrfTokenRepository.withHttpOnlyFalse()` vô điều kiện.** Mở khả năng JS đọc token mà không có nhu cầu. **Sửa:** chỉ bật khi frontend cần và có XSS controls.

**15. CSRF token xuất hiện trong URL/log.** Token có thể lộ qua referrer/history. **Sửa:** header/form field, không log.

**16. Dùng GET để thay đổi dữ liệu.** Safe method thường không bị CSRF check mặc định. **Sửa:** dùng POST/PUT/PATCH/DELETE.

**17. CSRF token đúng thì coi user được phép sửa object.** Token không phải role/ACL. **Sửa:** method/object authorization bắt buộc.

**18. Test bằng curl rồi kết luận browser CORS PASS.** Curl không enforce browser SOP. **Sửa:** WebTestClient và browser E2E.

**19. Chỉ test HTTP status, không kiểm database.** Denied vẫn có thể tạo side effect qua worker/event. **Sửa:** assert state và outbox không đổi.

**20. Bật debug full request/headers để tìm lỗi CSRF.** Dễ log cookie/token/PII. **Sửa:** structured reason/correlation, redaction và TTL.

## 32. Checklist vận hành và review

- [ ] Xác định ứng dụng dùng Spring WebFlux Reactive stack, không copy Servlet API.
- [ ] CORS configured trước auth cho preflight, có một nguồn rule rõ.
- [ ] `Origin`, `Allow-Methods`, `Allow-Headers`, credentials và maxAge phù hợp.
- [ ] Không dùng wildcard Origin khi allowCredentials true.
- [ ] Gateway/CDN/proxy không nhân đôi hoặc xóa CORS headers.
- [ ] Không dùng CORS để thay authentication/authorization.
- [ ] Cookie/session/Basic/browser ambient-auth endpoints giữ CSRF phù hợp.
- [ ] Không tắt CSRF khi chưa xác minh thực sự Bearer-only, stateless, không ambient credentials.
- [ ] Safe HTTP methods không chứa mutation.
- [ ] CSRF token được tạo/lưu/đọc qua ServerCsrfTokenRepository hợp lệ.
- [ ] Biết WebSession repository mặc định và masked XOR handler của phiên bản Spring đang dùng.
- [ ] SPA cookie/header CSRF contract được test thật, bao gồm sau login/logout.
- [ ] Cookie Secure/HttpOnly/SameSite/Domain/Path được thiết kế theo browser flow.
- [ ] Không đưa CSRF token, session cookie, bearer token vào URL/log/trace.
- [ ] ServerWebExchange attributes, Reactor Context, WebSession và singleton state không bị dùng lẫn.
- [ ] Authentication/context được truyền theo reactive subscription, không dựa request ThreadLocal tùy ý.
- [ ] Không cache currentUser/tenant trong mutable singleton hoặc publisher shared across actors.
- [ ] Tenant từ request được xác minh với authenticated membership, không tin Origin/header.
- [ ] Object-level read/write luôn có scope ID + tenant + owner/ACL/action phù hợp.
- [ ] Custom reactive policy không `block()` event loop hoặc biến timeout thành ALLOW.
- [ ] WebTestClient test đủ GET/POST, CSRF yes/no, allowed/denied origin, role và tenant.
- [ ] Browser E2E test preflight, credentials mode, SameSite, cross-site and same-site flows.
- [ ] Test denied requests không tạo mutation, outbox, file hoặc event bất hợp pháp.
- [ ] Tài liệu/version Spring Security được khóa và đối chiếu trước rollout.

**Kết luận:** Trong WebFlux, **CORS** quyết định browser origin có được chia sẻ response qua cơ chế trình duyệt hay không; **CSRF** chống request giả mạo khi browser tự mang credential; **request context** bảo đảm dữ liệu của mỗi reactive execution không bị lẫn giữa users/requests. Cả ba **không thay thế** authentication, role/authority và object-level authorization. Hãy xử lý preflight trước security, giữ CSRF cho các flow có ambient credentials, truyền identity/tenant theo nguồn đáng tin trong Reactor Context/ServerWebExchange và test toàn bộ flow từ browser đến transaction.

## Tài liệu tham khảo

- [Spring Security — Reactive CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html): preflight trước security, tích hợp CorsWebFilter.
- [Spring Framework — WebFlux CORS](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html): CorsConfiguration, @CrossOrigin, WebFluxConfigurer, CorsWebFilter, credentials và wildcards.
- [Spring Security — WebFlux CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): WebSessionServerCsrfTokenRepository, CookieServerCsrfTokenRepository, XOR token handler, form/AJAX/JSON.
- [Spring Security — CSRF Considerations](https://docs.spring.io/spring-security/reference/features/exploits/csrf.html): safe methods, login/logout và multipart upload.
- [Spring Security — WebFlux HTTP Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): SecurityWebFilterChain, authorizeExchange và matchers.
- [Spring Security — Reactive Authentication](https://docs.spring.io/spring-security/reference/reactive/authentication/index.html): reactive authentication context.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): method-level authorization và Reactor Context.
- [Spring Security — Reactive Test Support](https://docs.spring.io/spring-security/reference/reactive/test/index.html): WebTestClient, csrf() và mockUser().
- [Spring Framework — WebFlux Architecture](https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html): ServerWebExchange, handlers và reactive request processing.
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): token patterns, SameSite, Origin validation và threat model.
