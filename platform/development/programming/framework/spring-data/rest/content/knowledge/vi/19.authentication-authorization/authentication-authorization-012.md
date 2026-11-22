# CSRF, session cookie và chiến lược cho API dùng token trong Spring Data REST

## Mục tiêu

Sau bài này, bạn có thể giải thích vì sao một REST API vẫn có thể bị CSRF; nhận biết khi nào session cookie làm trình duyệt tự gửi thông tin xác thực; cấu hình CSRF token cho ứng dụng Spring Data REST dùng session; phân biệt mô hình đó với API chỉ nhận Bearer token; và tổ chức Spring Security filter chain phù hợp cho từng kiểu xác thực.

## 1. CSRF là gì và vì sao REST API vẫn cần quan tâm?

Cross-Site Request Forgery (CSRF) là kiểu tấn công khiến trình duyệt của người dùng đã đăng nhập gửi một request ngoài ý muốn đến ứng dụng mà người dùng đang tin cậy. Kẻ tấn công thường dụ người dùng mở một trang web khác. Trang đó có thể tạo form hoặc request đến ứng dụng đích.

Điểm quan trọng là trình duyệt có thể tự đính kèm thông tin xác thực gắn với origin đích, ví dụ session cookie. Nếu server chỉ kiểm tra cookie hợp lệ mà không xác minh request được khởi tạo có chủ ý từ ứng dụng, thao tác thay đổi dữ liệu có thể được thực hiện dưới danh tính người dùng.

Ví dụ, người dùng đã đăng nhập vào ứng dụng quản lý đơn hàng tại `https://shop.example.com`. Trình duyệt giữ cookie session. Một trang độc hại có thể thử gửi form đến endpoint thay đổi địa chỉ giao hàng. Nếu trình duyệt tự gửi cookie session và server không yêu cầu CSRF token, request có thể được xác thực như người dùng thật.

CSRF không phụ thuộc API có trả HTML hay JSON. Spring Data REST vẫn nhận các thao tác ghi như POST, PUT, PATCH và DELETE. Nếu trình duyệt tự gửi cookie hoặc thông tin xác thực khác, các endpoint đó vẫn cần chính sách chống CSRF phù hợp.

## 2. Khi nào CSRF là rủi ro?

Hãy xem xét cách thông tin xác thực được gửi đến server:

| Cơ chế xác thực | Trình duyệt tự gửi thông tin xác thực trong request cross-site? | CSRF |
| --- | --- | --- |
| Session cookie | Có thể tự gửi cookie phù hợp với domain, path và SameSite | Cần bảo vệ CSRF |
| JWT hoặc token lưu trong cookie | Cookie vẫn được trình duyệt tự gửi | Vẫn cần bảo vệ CSRF |
| HTTP Basic Authentication được trình duyệt lưu/gửi tự động | Có thể tự gửi thông tin xác thực | Cần đánh giá và bảo vệ CSRF |
| Bearer token chỉ được client chủ động đặt trong header `Authorization` | Trang khác không thể tự đọc token của ứng dụng rồi gắn vào request | Thường không cần CSRF cho cơ chế đó |
| Client native tự đặt Bearer token trong header | Không có cơ chế cookie tự động của trình duyệt | Thường không cần CSRF cho cơ chế đó |

CSRF chủ yếu khai thác **ambient credentials**: thông tin xác thực được trình duyệt tự động gửi theo request. Cookie là ví dụ phổ biến nhất.

Tên gọi “REST API”, “JWT” hoặc “stateless” không tự quyết định API có cần CSRF hay không. Cần nhìn vào cách credential thực sự đến server. JWT lưu trong cookie vẫn có đặc tính ambient credential giống session cookie.

## 3. Spring Security bảo vệ request bằng CSRF token

Spring Security cung cấp `CsrfFilter` và `CsrfTokenRepository` để tạo, lưu và kiểm tra CSRF token. Với cấu hình mặc định, CSRF protection được bật cho các request có thể thay đổi trạng thái, thường gồm POST, PUT, PATCH và DELETE. Các method an toàn như GET, HEAD và OPTIONS không nên được dùng để thay đổi dữ liệu.

Với session-based application, token thường được lưu phía server gắn với HTTP session. Khi render HTML, ứng dụng đưa token vào hidden field hoặc meta tag. Client phải gửi lại token trong request ghi; chỉ có session cookie là chưa đủ.

Ví dụ form server-rendered:

```html
<form method="post" action="/orders">
    <input type="hidden" name="_csrf" value="...">
    <!-- Các trường dữ liệu -->
    <button type="submit">Create order</button>
</form>
```

Với request JavaScript, token thường được gửi trong header. Header name mặc định của Spring Security là `X-CSRF-TOKEN` khi dùng repository session mặc định; với `CookieCsrfTokenRepository`, tên header mặc định là `X-XSRF-TOKEN`.

Nếu token bị thiếu hoặc không khớp token server mong đợi, Spring Security từ chối request trước khi controller/repository thực hiện thao tác. Response thường là `403 Forbidden`.

## 4. Session cookie và ứng dụng Spring Data REST

Một ứng dụng Spring Data REST có thể dùng session đăng nhập bằng form login hoặc một cơ chế xác thực dựa trên session khác. Trình duyệt lưu session cookie và tự gửi cookie đó khi gọi API cùng site theo quy tắc cookie.

Cấu hình Spring Security có thể giữ CSRF protection mặc định:

```java
@Configuration
@EnableWebSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        // CSRF được bật mặc định; không disable cho session-based app.
        return http.build();
    }
}
```

Với session-based API, request GET có thể đọc resource; request POST/PUT/PATCH/DELETE cần CSRF token. Ví dụ tạo Order qua collection resource:

```http
POST /api/orders HTTP/1.1
Cookie: JSESSIONID=...
Content-Type: application/json
Accept: application/hal+json
X-CSRF-TOKEN: <token đã lấy từ ứng dụng>

{
  "description": "Laptop order"
}
```

Tên session cookie thực tế có thể là `JSESSIONID` hoặc tên do container cấu hình. Token phải được lấy từ ứng dụng đã xác thực và gửi lại trong request; không tự tạo một chuỗi token ngẫu nhiên ở client.

## 5. Dùng CookieCsrfTokenRepository cho SPA

Một SPA chạy trong browser thường cần đọc CSRF token rồi gắn token vào header của các request thay đổi dữ liệu. Spring Security có `CookieCsrfTokenRepository` để lưu token trong cookie.

Cấu hình cơ bản:

```java
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {

    http
        .csrf(csrf -> csrf
            .csrfTokenRepository(
                CookieCsrfTokenRepository.withHttpOnlyFalse()));

    return http.build();
}
```

Mặc định, repository này dùng:

- Cookie tên `XSRF-TOKEN`.
- Header tên `X-XSRF-TOKEN`.
- Request parameter tên `_csrf`.

`withHttpOnlyFalse()` cho phép JavaScript đọc cookie CSRF để gửi giá trị vào header. Đây là cookie chứa CSRF token, không phải session cookie. Session cookie vẫn nên được đặt `HttpOnly` để JavaScript không đọc được credential xác thực.

Ví dụ JavaScript cùng origin:

```javascript
function readCookie(name) {
    const prefix = name + "=";
    const item = document.cookie
        .split("; ")
        .find(value => value.startsWith(prefix));

    return item ? decodeURIComponent(item.slice(prefix.length)) : null;
}

async function createOrder(order) {
    const csrfToken = readCookie("XSRF-TOKEN");

    return fetch("/api/orders", {
        method: "POST",
        credentials: "same-origin",
        headers: {
            "Content-Type": "application/json",
            "Accept": "application/hal+json",
            "X-XSRF-TOKEN": csrfToken
        },
        body: JSON.stringify(order)
    });
}
```

Ví dụ trên minh họa việc đọc cookie và gửi header. Ứng dụng cần bảo đảm token cookie đã được tạo trước khi gọi hàm và token được làm mới sau các sự kiện xác thực làm thay đổi session.

### Spring Security 6 và SPA token handling

Spring Security 6 dùng deferred CSRF token và BREACH protection với XOR encoding trong request attribute. SPA đọc token dạng cookie rồi gửi raw token trong header, nên cần cấu hình request handler phù hợp với cách token được phát và phân giải.

Chỉ thêm `CookieCsrfTokenRepository` có thể chưa đủ cho mọi SPA flow trên Spring Security 6. Hãy áp dụng mẫu `SpaCsrfTokenRequestHandler` trong tài liệu Spring Security của đúng phiên bản, bảo đảm handler:

- Dùng XOR handler cho token được đưa vào request attribute/HTML response.
- Chấp nhận raw token từ header SPA theo cách tương thích với cookie repository.
- Buộc token được tạo khi cần để cookie được gửi xuống browser.
- Làm mới token sau authentication success và logout nếu ứng dụng cần token mới cho session tiếp theo.

Đừng sao chép một handler từ phiên bản Spring Security khác mà không kiểm tra API và behavior của phiên bản dự án đang dùng. Các chi tiết deferred token và BREACH handling thay đổi giữa các phiên bản.

## 6. Thiết lập cookie an toàn

Session cookie là credential xác thực, nên thường cần các thuộc tính:

- `HttpOnly`: ngăn JavaScript đọc session cookie.
- `Secure`: chỉ gửi cookie qua HTTPS.
- `SameSite=Lax` hoặc `Strict` khi phù hợp với luồng điều hướng và đăng nhập.
- `Path` và `Domain` đủ hẹp để cookie chỉ được gửi đến ứng dụng cần nó.

CSRF token cookie có thể cần JavaScript đọc, nên `HttpOnly=false` trong mô hình double-submit cookie. Giữ quyền đọc này chỉ cho token cookie; không đổi session cookie thành JavaScript-readable.

`SameSite` là lớp phòng vệ bổ sung. `Lax` thường cho phép cookie trong một số top-level navigation an toàn; `Strict` hạn chế cross-site hơn nhưng có thể ảnh hưởng luồng đăng nhập từ site khác. `None` cho phép cookie trong ngữ cảnh cross-site và yêu cầu `Secure`. Nếu ứng dụng thực sự cần cookie cross-site, hãy giữ CSRF token protection và cấu hình CORS/credentials chính xác.

Không dùng `SameSite` như lý do duy nhất để tắt CSRF. Hành vi cookie phụ thuộc browser, site topology, subdomain và các luồng tích hợp thực tế.

## 7. Bearer token API: khi nào có thể tắt CSRF?

Một API chỉ chấp nhận Bearer token trong header `Authorization` có thể không cần CSRF protection cho API đó, vì browser không tự đính kèm token này vào request cross-site. Client hợp lệ phải chủ động lấy token và gửi:

```http
GET /api/orders HTTP/1.1
Authorization: Bearer eyJ...
Accept: application/hal+json
```

Một form độc hại từ website khác không thể tự đọc token đang được giữ trong ứng dụng origin khác để thêm vào header `Authorization`. Với mô hình này, CSRF không phải mối đe dọa chính của cơ chế Bearer authentication.

Có thể cấu hình một filter chain riêng cho API stateless chỉ dùng Bearer token:

```java
@Configuration
@EnableWebSecurity
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain bearerApi(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserApp(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        // Browser chain giữ CSRF protection mặc định.
        return http.build();
    }
}
```

Đây là mẫu phân chia filter chain. Cần thay matcher, authorization và resource server configuration theo ứng dụng. Chain API chỉ được disable CSRF khi API thực sự chỉ xác thực bằng Bearer header và không dựa vào session cookie, JWT cookie, HTTP Basic hoặc credential tự động gửi khác.

`SessionCreationPolicy.STATELESS` tự nó không làm CSRF protection trở nên không cần thiết. Một ứng dụng có thể không lưu HTTP session nhưng vẫn xác thực bằng cookie; cookie đó vẫn được browser tự gửi. Quyết định bật/tắt CSRF dựa trên cơ chế credential, không dựa riêng vào tên “stateless”.

## 8. JWT trong cookie khác với Bearer token trong header

Hai ứng dụng cùng dùng JWT vẫn có thể có rủi ro CSRF khác nhau:

**JWT trong Authorization header**

Client chủ động đặt `Authorization: Bearer ...`. Browser không tự gắn token vào request do website khác tạo. CSRF thường không áp dụng cho cơ chế xác thực này.

**JWT trong cookie**

Server đặt JWT trong cookie và browser tự gửi cookie đến domain phù hợp. Một request cross-site có thể mang cookie đó theo chính sách cookie của browser. CSRF vẫn là rủi ro và cần token protection phù hợp.

Lưu token trong `localStorage` hoặc `sessionStorage` có thể giảm nguy cơ CSRF vì browser không tự gửi giá trị đó như cookie, nhưng làm token có thể bị JavaScript đọc nếu xảy ra XSS. Không có cách lưu token nào loại bỏ mọi rủi ro. Hãy lựa chọn theo threat model; với ứng dụng browser, mô hình Backend-for-Frontend (BFF) giữ access token ở server và dùng session cookie cùng CSRF protection cũng là một phương án thường dùng.

## 9. CSRF khác CORS và SameSite như thế nào?

Ba cơ chế này giải quyết các vấn đề liên quan nhưng không thay thế nhau:

| Cơ chế | Câu hỏi chính | Vai trò |
| --- | --- | --- |
| CSRF protection | Request thay đổi dữ liệu có được khởi tạo từ client được tin cậy không? | Kiểm tra CSRF token hoặc cơ chế xác minh request tương ứng |
| CORS | JavaScript từ origin khác có được browser cho phép đọc response không? | Điều khiển cross-origin access của browser |
| SameSite cookie | Cookie có được gửi trong ngữ cảnh site khác không? | Giảm việc browser gửi cookie trong một số cross-site request |

CORS không phải CSRF defense đầy đủ. Một cross-origin HTML form có thể gửi một số request đơn giản mà không cần JavaScript đọc response. CORS có thể chặn script đọc response nhưng không nhất thiết ngăn request đã được gửi đến server.

SameSite giúp giảm một số request mang cookie cross-site, nhưng vẫn nên dùng CSRF token cho session-based application theo chính sách của Spring Security. Có thể bổ sung kiểm tra `Origin` hoặc `Referer` như lớp defense in depth, nhưng không nên thay thế token protection chỉ bằng kiểm tra header này.

## 10. CORS và CSRF cho SPA khác origin

Nếu SPA và Spring Data REST chạy ở hai origin khác nhau, ví dụ `https://app.example.com` và `https://api.example.com`, cần cấu hình CORS rõ ràng.

Với request có cookie/session, client cần gửi credentials và server phải cho phép origin cụ thể cùng credentials. Không dùng wildcard origin khi bật credentials. Đồng thời cho phép header CSRF mà client gửi, ví dụ `X-XSRF-TOKEN`.

Ví dụ cấu hình CORS minh họa:

```java
@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of("https://app.example.com"));
    config.setAllowedMethods(
        List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"));
    config.setAllowedHeaders(
        List.of("Content-Type", "Accept", "X-XSRF-TOKEN"));
    config.setAllowCredentials(true);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/**", config);
    return source;
}
```

Bật CORS trong Spring Security:

```java
http.cors(Customizer.withDefaults());
```

Client gửi cookie:

```javascript
fetch("https://api.example.com/api/orders", {
    method: "POST",
    credentials: "include",
    headers: {
        "Content-Type": "application/json",
        "X-XSRF-TOKEN": csrfToken
    },
    body: JSON.stringify(order)
});
```

Để JavaScript đọc CSRF cookie từ API origin, cookie domain/path và cách triển khai frontend cần được thiết kế phù hợp. Cookie host-only của API origin không thể được JavaScript ở một origin khác đọc trực tiếp. Có thể cung cấp endpoint lấy token hoặc triển khai BFF/reverse proxy cùng origin để đơn giản hóa việc chia sẻ token.

CORS phải xử lý preflight OPTIONS trước khi request thực hiện thao tác. CSRF token vẫn cần có trên request ghi thực tế. Cấu hình CORS ở Spring Security và Spring Data REST phải thống nhất để không có một lớp cho phép nhưng lớp khác chặn.

## 11. CSRF với các endpoint Spring Data REST

Spring Data REST tự động tạo endpoint repository. Nếu các endpoint này được truy cập bằng session cookie, giữ CSRF protection cho thao tác ghi:

| Thao tác | Ví dụ | CSRF token |
| --- | --- | --- |
| Đọc collection | `GET /api/orders` | Không cần |
| Đọc item | `GET /api/orders/42` | Không cần |
| Tạo resource | `POST /api/orders` | Cần khi dùng cookie/session |
| Thay thế resource | `PUT /api/orders/42` | Cần khi dùng cookie/session |
| Cập nhật một phần | `PATCH /api/orders/42` | Cần khi dùng cookie/session |
| Xóa resource | `DELETE /api/orders/42` | Cần khi dùng cookie/session |

Không biến GET thành thao tác thay đổi dữ liệu. Nếu GET có side effect, ứng dụng sẽ phá vỡ semantics HTTP và làm cache, crawler, prefetch cũng như CSRF protection khó dự đoán.

Nếu API có base path Spring Data REST, dùng matcher tương ứng với URL thực tế. Khi tách filter chains, bảo đảm custom controller và repository endpoints đều nằm trong chain có chính sách xác thực/CSRF đúng.

## 12. Những endpoint đặc biệt cần lưu ý

**Login và logout:** CSRF cũng có thể liên quan đến thao tác đăng nhập/đăng xuất. Không loại trừ endpoint login/logout khỏi bảo vệ một cách tùy tiện. Khi đăng nhập hoặc logout làm token/session thay đổi, SPA cần lấy token mới trước request ghi tiếp theo.

**Endpoint lấy CSRF token:** SPA có thể cần một request GET ban đầu để server tạo token và gửi cookie/representation. Endpoint này không được làm thay đổi nghiệp vụ. Bảo đảm token được khởi tạo trước request POST/PUT/PATCH/DELETE.

**Upload file:** Multipart request cũng là request thay đổi dữ liệu và cần CSRF token. Spring Security hỗ trợ các cách gửi token phù hợp cho multipart; cân nhắc thứ tự filter và giới hạn kích thước file.

**WebSocket hoặc giao thức khác:** Không mặc định rằng CSRF filter HTTP bảo vệ mọi handshake hoặc message. Kiểm tra cơ chế xác thực và origin validation riêng của giao thức.

## 13. Lỗi 403 do CSRF và cách chẩn đoán

Nếu request ghi trả `403 Forbidden`, kiểm tra:

1. Ứng dụng có đang dùng session cookie hoặc credential tự động gửi không?
2. CSRF token đã được cấp cho browser chưa?
3. Token cookie có tồn tại, đúng domain/path và chưa bị xóa không?
4. Client có gửi đúng header name không: `X-CSRF-TOKEN` hoặc `X-XSRF-TOKEN` tùy repository?
5. Header token có khớp token được lưu trong session/cookie không?
6. Token có bị thay đổi sau login/logout hoặc session rotation không?
7. Với Spring Security 6 SPA, request handler có xử lý đúng raw cookie token và XOR token không?
8. Request có đi qua đúng SecurityFilterChain không?
9. CORS/preflight có cho phép header custom và credentials cần thiết không?

Bật log Spring Security ở môi trường phát triển để xem CSRF filter từ chối vì thiếu hay sai token. Không ghi CSRF token, session ID hoặc access token vào log production. Response 403 cũng có thể đến từ authorization; xem log để phân biệt lỗi CSRF với thiếu quyền.

## 14. Checklist lựa chọn chiến lược

**Ứng dụng browser dùng session cookie**

- Giữ CSRF protection mặc định của Spring Security.
- Dùng session cookie `HttpOnly`, `Secure` và SameSite phù hợp.
- Với server-rendered form, render token trong hidden field.
- Với SPA, dùng CSRF cookie hoặc endpoint bootstrap và gửi token trong header.
- Làm mới token sau login/logout nếu flow của phiên bản yêu cầu.
- Không tắt CSRF chỉ vì endpoint trả JSON hoặc được gọi là REST API.

**API chỉ dùng Bearer token**

- Chỉ nhận token trong header `Authorization`.
- Không dùng session cookie/JWT cookie/HTTP Basic làm credential thay thế trong cùng filter chain.
- Dùng session policy stateless nếu phù hợp.
- Có thể disable CSRF trong chain dành riêng cho API này.
- Bảo vệ token trước XSS và kiểm tra authorization trên từng request.
- Giữ CORS allowlist riêng nếu browser client gọi API cross-origin.

**Ứng dụng kết hợp browser session và API token**

- Tách SecurityFilterChain bằng request matcher và thứ tự rõ ràng.
- Browser chain giữ CSRF protection.
- Bearer-only API chain có thể disable CSRF khi đáp ứng điều kiện không dùng ambient credentials.
- Không để URL overlap khiến request đi vào chain sai.
- Kiểm thử cả POST/PATCH/DELETE với session cookie và Bearer token.

## Tóm tắt

- CSRF khai thác credential mà browser tự gửi; REST/JSON không tự miễn CSRF.
- Session cookie và JWT trong cookie cần CSRF protection cho request thay đổi dữ liệu.
- Spring Security mặc định bật CSRF; giữ bảo vệ cho session-based Spring Data REST.
- SPA có thể dùng `CookieCsrfTokenRepository` với cookie `XSRF-TOKEN` và header `X-XSRF-TOKEN`; session cookie vẫn nên HttpOnly.
- Spring Security 6 dùng deferred/XOR token handling; SPA cần request handler tương thích và flow làm mới token.
- API chỉ nhận Bearer token chủ động đặt trong `Authorization` thường không cần CSRF; có thể disable trong filter chain stateless riêng.
- `STATELESS` không tự chứng minh CSRF không cần thiết; JWT trong cookie vẫn là ambient credential.
- CORS và SameSite là các cơ chế khác; chúng bổ sung nhưng không thay thế CSRF token.
- Giữ CSRF cho POST/PUT/PATCH/DELETE khi xác thực bằng cookie/session và kiểm tra lỗi 403 theo token, cookie, handler, filter chain và CORS.

## Tài liệu tham khảo

- [Spring Security — Cross Site Request Forgery (CSRF)](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — CSRF protection for JavaScript applications](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html#csrf-integration-javascript)
- [Spring Security — CookieCsrfTokenRepository API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/web/csrf/CookieCsrfTokenRepository.html)
- [Spring Security — Multiple HttpSecurity instances](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html#_multiple_httpsecurity_instances)
- [Spring Framework — CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html)
- [OWASP Cheat Sheet — Cross-Site Request Forgery Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
