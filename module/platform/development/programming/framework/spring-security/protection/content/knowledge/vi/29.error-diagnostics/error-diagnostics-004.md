# Token không khớp do session, cookie hoặc cơ chế che giá trị

> **Chương:** Chẩn đoán lỗi  
> **Mô-đun:** `SPRING_SECURITY_HTTP_PROTECTION` — áp dụng các lớp phòng vệ HTTP và trình duyệt trong Spring Security, từ CSRF, CORS, security headers, CSP, HSTS đến HTTP firewall và bảo vệ session. Người học cấu hình cho Servlet lẫn Reactive, kiểm thử các kịch bản tấn công web và chẩn đoán xung đột bảo mật khi triển khai.

## 1. Hiện tượng: có CSRF token nhưng POST vẫn nhận 403

Một người dùng đăng nhập vào `https://app.example.com` và mở trang chỉnh sửa hồ sơ. HTML đã có hidden input:

~~~html
<input type="hidden" name="_csrf" value="MASKED_TOKEN_FROM_SERVER">
~~~

Browser gửi:

~~~http
POST /profile HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=SESSION_B
Content-Type: application/x-www-form-urlencoded

displayName=Alice&_csrf=MASKED_TOKEN_FROM_SERVER
~~~

Kết quả:

~~~http
HTTP/1.1 403 Forbidden
~~~

Khác với tình huống **token chưa được tạo hoặc chưa được tải**, ở đây frontend **đã gửi một giá trị** nhưng Spring Security không chấp nhận. Nguyên nhân có thể là:

- Token được cấp khi browser ở **session A**, còn request thay đổi trạng thái sử dụng **session B**.
- Session hết hạn, được tái tạo, hoặc CSRF token bị xóa/làm mới sau login/logout.
- Cookie phiên hoặc cookie CSRF không được gửi/đọc đúng do `Domain`, `Path`, `Secure`, `SameSite`, `HttpOnly` hay thiết lập `credentials`.
- SPA lấy giá trị **raw CSRF token** từ cookie, nhưng handler của backend mong đợi **token đã được mask** theo cơ chế chống BREACH, hoặc ngược lại.
- Token bị cache, ghép vào trang từ một phiên khác hoặc bị một proxy thay đổi.
- Request GET phát token và POST xác minh đi qua **security chain/repository khác nhau**.
- Client gửi token đúng dạng nhưng sai tên header/parameter hoặc trùng nhiều giá trị.

Điều quan trọng: **“Có trường `_csrf`” không đồng nghĩa “token hợp lệ”.** Mã 403 cũng có thể do CSRF, authorization, CORS hoặc proxy/WAF; cần xác nhận tầng nào đã từ chối trước khi sửa.

### Mục tiêu

Sau bài học, người học có thể:

1. Mô tả quan hệ **expected token – submitted token – CSRF request handler**.
2. Xác định lỗi do session, cookie scope, login/logout, cache hoặc mismatch raw/masked.
3. Phân biệt token được che giá trị để chống BREACH với token trong repository.
4. Cấu hình và kiểm thử chiến lược CSRF cho **Servlet** và **Reactive/WebFlux**.
5. Tái hiện mismatch trong MockMvc/WebTestClient và browser mà không làm lộ giá trị token.
6. Đưa ra bản sửa tối thiểu, không tắt CSRF, authentication, CORS hoặc phòng vệ HTTP khác để che lỗi.

## 2. Mô hình chẩn đoán: ba dữ liệu phải cùng ngữ cảnh

Với request cần bảo vệ, CSRF filter về mặt khái niệm phải có:

1. **Expected token:** giá trị CSRF mà repository tải từ session, cookie hoặc nơi lưu đã cấu hình.
2. **Submitted token:** giá trị đi kèm request, ví dụ trong `_csrf`, `X-CSRF-TOKEN` hoặc `X-XSRF-TOKEN`.
3. **Quy tắc xử lý submitted token:** `CsrfTokenRequestHandler` (Servlet) hoặc request handler tương ứng của Reactive có thể chọn vị trí đọc và giải mã giá trị đã được mask.

~~~mermaid
flowchart TD
    A[POST /profile] --> B[Security chain thực sự áp dụng]
    B --> C[CSRF filter]
    C --> D[Repository tải expected token]
    C --> E[Request handler đọc submitted token]
    E --> F[Giải mã / xử lý masked hoặc raw]
    D --> G{Giá trị sau xử lý khớp expected token?}
    F --> G
    G -- Không --> H[CSRF từ chối, thường HTTP 403]
    G -- Có --> I[Tiếp tục authentication / authorization / controller]
~~~

Sơ đồ là mô hình tư duy, không thay thế thứ tự filter chính xác trong mọi phiên bản/cấu hình. CSRF có thể từ chối request trước khi bước authorization diễn ra, và proxy/container có thể từ chối trước Spring Security.

| Khái niệm | Nằm ở đâu? | Dùng để làm gì? |
|---|---|---|
| Expected token | `CsrfTokenRepository`/`ServerCsrfTokenRepository` | Giá trị tham chiếu để so khớp |
| Token render ở HTML | `_csrf.token` sau request handler | Đưa cho form; có thể là **masked token** |
| Raw cookie token | Ví dụ `XSRF-TOKEN` | SPA có thể đọc khi cookie được phép và gửi qua header |
| Submitted token | POST parameter hoặc request header | Bằng chứng client cung cấp |
| Request handler | Servlet/Reactive CSRF handler | Xử lý tên, vị trí, raw/masked |
| Session/cookie context | Cookie HTTP, session store, domain/path | Quyết định repository tải được expected token nào |

**Mục tiêu không phải so sánh trực tiếp hai chuỗi token trong DevTools.** Với masking, chuỗi hiển thị có thể khác raw value theo chủ đích. Đúng hơn phải xác minh request handler chấp nhận token đã cấp **trong ngữ cảnh phiên tương ứng**.

## 3. Xác nhận thật sự là lỗi CSRF trước khi chẩn đoán mismatch

Một POST trả 403 chưa đủ. Hãy thu những tín hiệu sau:

| Kết quả hoặc dấu hiệu | Hướng điều tra |
|---|---|
| `MissingCsrfTokenException` hoặc lỗi thiếu CSRF được log | Expected/submitted token chưa có theo quy trình cụ thể |
| `InvalidCsrfTokenException` hoặc thông điệp mismatch phù hợp | Token được cung cấp nhưng không được chấp nhận |
| 403 với `AccessDeniedException` từ authorization | Role, scope, method security, không nhất thiết CSRF |
| `OPTIONS` trả 403 và POST không xuất hiện | CORS preflight bị từ chối trước request thật |
| Network không có POST; Console báo `connect-src` | CSP của HTML có thể chặn trước khi gửi |
| 401 hoặc 302 đến login | Xác thực/phiên chưa hợp lệ hoặc entry point được gọi |
| `RequestRejectedException` | HTTP firewall, request bị từ chối trước authorization thông thường |
| Không có application request log nhưng edge trả 403 | WAF/reverse proxy/CDN có thể là nguồn từ chối |

Trong Spring Security Servlet, `CsrfFilter` và `CsrfTokenRepository` giữ vai trò chủ yếu. Trong WebFlux, cơ chế tương ứng dùng `CsrfWebFilter`, `ServerCsrfTokenRepository` và các loại `ServerCsrfTokenRequestHandler`.

**Không suy mã HTTP cố định từ một exception.** Status cuối cùng có thể được tùy biến bởi handler hoặc gateway; nguồn chứng cứ tốt nhất là security chain, exception/handler đã chạy và request–response thực tế.

## 4. Mismatch session A / session B

Với `HttpSessionCsrfTokenRepository`, expected CSRF token thường gắn với HTTP session.

~~~text
GET /profile
  Cookie: JSESSIONID=A
  => Server cung cấp CSRF token thuộc session A

Người dùng mở tab khác, đăng nhập lại, session thay đổi

POST /profile
  Cookie: JSESSIONID=B
  _csrf: token lấy từ session A
  => Server tải expected token theo session B
  => Mismatch, thường 403
~~~

Nếu session B chưa có token mới, lỗi có thể được mô tả là thiếu expected token thay vì invalid submitted token; điều quan trọng vẫn là **client gửi giá trị thuộc ngữ cảnh cũ**.

### Những tình huống tạo session mới

- Session timeout vì không hoạt động.
- Login sử dụng session fixation protection, đổi session ID hoặc tạo phiên mới theo cấu hình.
- Logout invalidates session, xóa/rotate thông tin xác thực và CSRF.
- Browser xóa cookie hoặc đổi profile/incognito context.
- Cookie session không được gửi ở request POST, khiến server coi đó là phiên khác.
- Load balancer gửi POST tới node không có trạng thái session tương ứng.
- Một custom authentication/session handler chủ động tạo session mới.

**Đổi session ID không luôn đồng nghĩa mọi attribute trong session bị mất.** Tùy chiến lược bảo vệ session fixation, dữ liệu session có thể được giữ hoặc chuyển. Để kết luận CSRF mismatch, phải xem token repository và vòng đời token thực tế, không chỉ thấy session ID đổi.

### Bằng chứng an toàn cần thu

Ghi **sự hiện diện** của cookie, loại session transition, correlation ID và thời điểm GET/POST; không ghi nguyên session ID hoặc CSRF token vào ticket. Nếu cần tương quan nhiều request trong môi trường kiểm thử, có thể sử dụng mã phiên rút gọn/định danh tạm được bảo vệ trong telemetry nội bộ, không phơi bày bí mật.

## 5. Token cũ sau login/logout: chuyện khác với token bị mask lại

Spring Security có thể xóa CSRF token cũ khi authentication thành công hoặc logout. Trình duyệt vẫn có thể giữ một trang, form hoặc biến JavaScript đã lấy token trước đó.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant S as Spring Security
    B->>S: GET /csrf (session ban đầu)
    S-->>B: token A
    B->>S: POST /login với token A
    S-->>B: Login success; token cũ có thể bị clear
    B->>S: POST /profile vẫn dùng token A
    S-->>B: 403 nếu token A không còn hợp lệ
    B->>S: GET /csrf sau login
    S-->>B: token cho ngữ cảnh mới
    B->>S: POST /profile với token mới
    S-->>B: Request được xét tiếp bởi auth/authorization
~~~

Một flow SPA hợp lý:

1. Dùng token phù hợp để submit login form/POST login nếu CSRF đang bảo vệ nó.
2. Sau khi authentication success và cookie/session ổn định, **lấy CSRF token mới**.
3. Chỉ gửi yêu cầu cập nhật dữ liệu sau khi token mới đã được nhận.
4. Khi logout, reset token state; luồng tiếp theo cũng cần tải token cho ngữ cảnh mới.

**Phân biệt:**

- *Rotate/invalidate expected token* → token cũ có thể bị từ chối vì repository thay đổi.
- *Mask lại token để giảm BREACH* → chuỗi HTML gửi browser có thể khác dù expected token trong repository không đổi.

Không kết luận “session reset” chỉ vì hai hidden input có chuỗi khác nhau; cần xác minh repository, request handler và ngữ cảnh.

## 6. Cookie nào đang có mặt, cookie nào thật sự được gửi?

Với web app dùng session, browser có thể giữ:

~~~http
Cookie: JSESSIONID=SESSION_VALUE; XSRF-TOKEN=RAW_CSRF_VALUE
~~~

Hai cookie phục vụ mục đích khác nhau:

- `JSESSIONID` hoặc cookie session tùy cấu hình: giúp server khôi phục phiên xác thực.
- `XSRF-TOKEN` nếu dùng cookie repository: lưu giá trị liên quan CSRF; SPA có thể cần copy nó vào header `X-XSRF-TOKEN`.

**Cookie XSRF không phải tự động là bearer credential**, và việc nó được gửi như cookie chưa chắc đáp ứng điều kiện CSRF: server thường cần **giá trị submitted trong header/parameter** theo request handler.

### Phân biệt các thuộc tính cookie

| Thuộc tính | Ảnh hưởng chính | Triệu chứng dễ gặp |
|---|---|---|
| `Domain` hoặc cookie host-only | Host nào nhận cookie | SPA/API khác hostname không có cùng cookie |
| `Path` | Những URL mà browser gửi cookie | GET có cookie, POST tới path khác không có |
| `Secure` | Chỉ gửi cookie trên kết nối bảo mật phù hợp | HTTP lab/proxy sai scheme không gửi đúng cookie |
| `SameSite=Lax` | Hạn chế gửi cookie trong nhiều ngữ cảnh cross-site | Cross-site fetch/POST không mang cookie |
| `SameSite=Strict` | Hạn chế chặt hơn đối với cross-site context | Chuyển hướng từ site ngoài có hành vi cookie khác kỳ vọng |
| `SameSite=None` | Cho phép một số ngữ cảnh cross-site theo chính sách browser | Thường đòi `Secure`; vẫn chịu cookie policy của browser |
| `HttpOnly` | Ngăn JavaScript đọc cookie qua `document.cookie` | SPA không đọc được raw CSRF cookie |
| `Max-Age`/`Expires` | Tuổi thọ cookie | Cookie CSRF còn nhưng session hết hạn hoặc ngược lại |

**Same-site và same-origin không đồng nghĩa.** `https://app.example.com` và `https://api.example.com` thường là **khác origin** nên chịu CORS, dù có thể được coi là cùng site trong chính sách cookie phù hợp. Domain/Path, CORS, SameSite, Secure và credentials vẫn cần đồng bộ.

### HttpOnly có phải lỗi?

Không. Với form server-rendered hoặc endpoint `GET /csrf` trả token JSON, cookie session và có thể cả cookie CSRF **không cần JavaScript đọc trực tiếp**. `HttpOnly` là một lớp bảo vệ hữu ích.

Chỉ khi bạn **chủ đích dùng SPA đọc raw token từ cookie** thì cookie token mới cần đọc được theo JavaScript. Ví dụ `CookieCsrfTokenRepository.withHttpOnlyFalse()` phục vụ chiến lược đó; không nên bật một cách máy móc trên mọi ứng dụng.

## 7. DevTools: GET và POST phải được so theo cùng ngữ cảnh

Mở browser DevTools → Network và quan sát **theo thứ tự thời gian**:

| Bước | Cần ghi nhận | Tránh kết luận nhầm |
|---|---|---|
| GET trang hoặc `GET /csrf` | URL, response, session/cookie scope, tên header token, cache | Chỉ vì HTTP 200 không có nghĩa token hợp lệ |
| Login/logout (nếu có) | `Set-Cookie`, redirect, session transition, token refetch | Session ID đổi không chứng minh token bị mất |
| OPTIONS preflight (nếu cross-origin) | Origin, requested method/headers, status CORS | Preflight 403 không phải CSRF của POST |
| POST/PATCH/... | Có đúng cookie session và header/parameter token không? | Có token không chứng minh token khớp |
| Server logs | CSRF exception, chain, repository/handler | 403 không tự chứng minh do CSRF |

**Không chia sẻ token hoặc cookie đầy đủ qua screenshot/ticket.** Đối với lỗi, ghi có/không, header name, cookie attributes và ID request có thể liên kết log; giữ bí mật trong công cụ bảo mật thích hợp.

### Biểu mẫu mẫu để đối chiếu

~~~text
GET request ID:            req-101
Session cookie present:    yes
Repository:                HttpSessionCsrfTokenRepository
Returned token form:       masked / raw / none
Login or logout occurred:  yes/no
POST request ID:           req-102
Session cookie present:    yes
Submitted token present:   yes
Submitted token location:  _csrf parameter
Handler strategy:          XOR/masked expected
CSRF exception:            InvalidCsrfTokenException
POST status:               403
~~~

Đây là mẫu thông tin chẩn đoán, **không phải dữ liệu log đã thu thật**. Trường “Handler strategy” phải được xác nhận từ cấu hình runtime, không suy từ giá trị token.

## 8. Tách lỗi cookie khỏi lỗi security chain

Giả sử hai chain:

~~~text
Chain 1: /api/** → CookieCsrfTokenRepository + custom handler
Chain 2: còn lại → HttpSessionCsrfTokenRepository + form login
~~~

SPA thực hiện:

~~~text
GET /csrf          → Chain 2, nhận token theo session
POST /api/profile  → Chain 1, expected token lấy từ cookie
~~~

Token từ GET và expected token của POST **có thể không cùng repository hoặc cơ chế biểu diễn**, dẫn đến 403. Lỗi này không khắc phục được bằng cách đổi role người dùng.

Kiểm tra:

1. GET token và POST đi qua chain nào? Thứ tự `@Order` và `securityMatcher` có đúng không?
2. Mỗi chain đang dùng repository và CSRF request handler nào?
3. Token bootstrap có phục vụ **đúng nhóm endpoint** không?
4. Có rule `web.ignoring()` hoặc proxy route nào khiến GET token bỏ qua Spring Security filter không?
5. Có sự khác nhau giữa Servlet main app và WebFlux/management context không?

**`permitAll()` không tắt CSRF**: một POST được phép truy cập ở bước authorization vẫn có thể cần CSRF token trong chain đó. Ngược lại, nếu request bị bỏ qua hoàn toàn bởi Spring Security filter chain thì đây là lỗ hổng bảo vệ cần phân tích, không phải cách sửa token mismatch.

## 9. Raw token và masked token: hai dạng hiển thị của cùng một bí mật

Với Spring Security Servlet 6.x, cơ chế mặc định ở nhiều cấu hình sử dụng `XorCsrfTokenRequestAttributeHandler` để giảm rủi ro BREACH khi đưa token vào phản hồi nén. Token có thể được **mask bằng một giá trị ngẫu nhiên mới mỗi lần expose**, rồi gửi giá trị masked trong HTML.

~~~text
Repository lưu raw token R

GET /profile lần 1:
  _csrf.token được trình bày thành masked value M1(R)

GET /profile lần 2:
  _csrf.token được trình bày thành masked value M2(R)

M1(R) ≠ M2(R) là điều có thể hoàn toàn bình thường.

POST /profile với giá trị M1(R):
  handler phù hợp giải mask -> R
  so sánh R với expected token trong repository
~~~

**Không so sánh chuỗi `M1` với `R` rồi tuyên bố token không khớp.** Chúng cố ý có biểu diễn khác nhau. Chỉ handler phía server mới quyết định cách giải token đã mask và kiểm tra against expected token.

### Vì sao BREACH có liên quan?

Nếu một secret cố định xuất hiện trong nội dung HTTP response được nén và attacker kiểm soát một phần input phản xạ gần đó, các khác biệt về kích thước nén có thể làm rò thông tin trong một số mô hình tấn công. Masking CSRF token theo mỗi response giúp giảm việc đưa **cùng chuỗi secret** cố định vào HTML.

Điều đó không thay thế các biện pháp chống XSS, CSRF repository, quyền cookie hoặc kiểm soát response caching.

### Một ví dụ dạng byte chỉ để hình dung, không phải mã triển khai

~~~text
Raw token:      R
Random mask:    K1
Masked token:   encode(K1 || XOR(K1, R))

Lần sau:
Random mask:    K2
Masked token:   encode(K2 || XOR(K2, R))
~~~

Sơ đồ nhằm giải thích “mỗi lần một biểu diễn khác”; không tự hiện thực thuật toán XOR/Base64 tại frontend. Cấu trúc/chuyển đổi chính xác phụ thuộc handler và phiên bản framework. Client phải gửi lại **giá trị được server cấp**, không tự giải mã, strip, hash hoặc tự tạo một masked token.

## 10. Dấu hiệu của lỗi raw-cookie vs XOR request handler

Giả sử bạn chủ động dùng cookie repository cho SPA:

~~~java
CookieCsrfTokenRepository repository =
    CookieCsrfTokenRepository.withHttpOnlyFalse();
~~~

Browser có cookie `XSRF-TOKEN`, JavaScript đọc giá trị raw và gửi:

~~~http
POST /api/profile HTTP/1.1
Cookie: JSESSIONID=...; XSRF-TOKEN=RAW_COOKIE_VALUE
X-XSRF-TOKEN: RAW_COOKIE_VALUE
~~~

Nếu phía server dùng handler đang **giải mask** giá trị được nhận, nhưng browser gửi **raw token** trong header, handler có thể không giải mã được và CSRF validation thất bại dù raw cookie token là giá trị repository mong đợi.

### Cách phân biệt với lỗi mất session

| Quan sát | Nghi vấn chính |
|---|---|
| Cookie/session đúng và ổn định; raw header có nhưng POST 403 | Handler raw/masked không tương thích |
 Cookie/session đổi giữa GET và POST | Session/rotation/cookie scope |
 Hidden HTML token gửi và POST thành công, nhưng SPA header raw thất bại | Sự khác biệt cách handler xử lý form parameter và header |
 GET `/csrf` không trả giá trị nào | Token chưa materialize hoặc sai chain |
 POST thành công khi dùng endpoint JSON trả masked token, thất bại khi tự đọc cookie raw | Chiến lược token đang bị trộn |

**Đừng giải quyết bằng cách cấu hình server chấp nhận mọi giá trị bất kể expected token.** Cần chọn một hợp đồng rõ ràng: form dùng masked value, SPA dùng raw cookie với handler phù hợp, hoặc SPA dùng giá trị token do endpoint bootstrap cung cấp và handler xử lý tương ứng.

## 11. Chọn chiến lược CSRF theo kiểu ứng dụng

| Kiến trúc | Nguồn token cho client | Xử lý khuyến nghị | Bẫy cần test |
|---|---|---|---|
| Spring MVC + Thymeleaf form | Hidden input từ `_csrf` | Request handler của Spring cho giá trị form | Form không được chèn input; form bị cache |
| SPA cùng origin + session | GET `/csrf` trả token/headerName | Gửi nguyên token được cấp theo hợp đồng backend | Login rotation; request chạy trước bootstrap |
| SPA đọc CSRF cookie | `XSRF-TOKEN` readable cookie | Header raw và request handler tương thích | Cookie chưa được phát; XOR handler tưởng token bị mask |
| SPA và API khác origin | Endpoint bootstrap có CORS credentials có kiểm soát | Cookie scope/Origin/CSRF handler phải được thiết kế cùng nhau | Preflight, SameSite, credentials, third-party-cookie restrictions |
| Servlet API stateless Bearer-only, không dùng ambient browser credentials | Có thể có threat model khác | Phân tích cần hay không cần CSRF trên route cụ thể | Tưởng mọi API JSON đều miễn CSRF |
| WebFlux server-rendered | Token từ WebFlux exchange/view | Reactive handler và session repository tương ứng | Mono chưa được consume, web session thay đổi |

Một ứng dụng có thể có nhiều kiểu frontend nhưng **đừng để các chain dùng chiến lược token khác nhau mà không có hợp đồng cụ thể cho từng nhóm endpoint**.

### Một quy tắc quan trọng

Nếu endpoint **đã cấp một masked token** cho client, hãy gửi lại **chính chuỗi đó** theo cơ chế handler dự kiến. Nếu frontend lấy **raw token từ cookie**, backend phải có cách đọc raw header. Đừng tự đoán dựa trên độ dài hoặc ký tự Base64 của token.

## 12. Servlet: session repository và form đã được mask

Một ứng dụng Spring MVC với form server-rendered có thể sử dụng CSRF mặc định và tập trung vào việc expose token đúng trong template:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SessionFormSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/login", "/css/**").permitAll()
            .requestMatchers("/profile/**").authenticated()
            .anyRequest().authenticated()
        );
        http.formLogin(Customizer.withDefaults());
        http.csrf(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Trong template Thymeleaf, khi cần chèn token tường minh:

~~~html
<form th:action="@{/profile}" method="post">
  <input type="text" name="displayName">
  <input type="hidden"
         th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}">
  <button type="submit">Lưu</button>
</form>
~~~

Tích hợp Spring MVC/Thymeleaf có thể tự chèn token qua form-processing integration cho form POST. **Kiểm tra HTML cuối cùng để tránh chèn hai input cùng tên**. Nếu form được render thuần ở CDN hoặc bằng framework SPA, request attribute `_csrf` của MVC không tự tồn tại ở HTML đó.

### Điều gì chứng minh lỗi do session mismatch?

Một phép thử tốt có ít nhất hai đối chứng:

1. Lấy form token A và POST bằng **chính session A** → được CSRF filter chấp nhận, sau đó còn phụ thuộc auth/authorization/controller.
2. Lấy form token A nhưng POST với **session B đã có token B** → bị CSRF filter từ chối.

Chỉ thay hidden input A thành B trong cùng session mà không xác minh expected token cũng chưa đủ giải thích session transition.

## 13. Servlet: endpoint bootstrap trả token mà handler có thể xử lý

Một phương án cho SPA là GET `/csrf` chủ động expose token cho browser:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CsrfBootstrapController {

    @GetMapping("/csrf")
    ResponseEntity<Map<String, String>> bootstrap(HttpServletRequest request) {
        CsrfToken token = (CsrfToken) request.getAttribute("_csrf");
        if (token == null) {
            throw new IllegalStateException(
                "No CSRF request attribute; check security chain"
            );
        }

        // getToken() giải quyết deferred token nếu cần.
        Map<String, String> body = Map.of(
            "headerName", token.getHeaderName(),
            "parameterName", token.getParameterName(),
            "token", token.getToken()
        );
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(body);
    }
}
~~~

Điều kiện của ví dụ:

- Route GET `/csrf` đi qua **chain có CSRF enabled**, request attribute name đúng với handler.
- Nếu handler đã expose một **masked token**, JSON chứa token dạng đó và client phải gửi lại theo cách server đọc được.
- Nếu dùng session repository, GET token và POST cần giữ **cùng session hiện hành**.
- Không cache public response có CSRF token; không đưa token lên URL query, logs hoặc analytics.
- CORS cho endpoint này phải hạn chế origin; không cấp token để website lạ đọc tự do trong khi cookie credentials được gửi.

Ví dụ cấu hình giới hạn chain:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/csrf").permitAll()
    .requestMatchers("/profile/**").authenticated()
    .anyRequest().authenticated()
);
~~~

`permitAll()` chỉ quyết định authorization, **không bypass CSRF filter**. Nó có thể hợp lý nếu SPA cần token để đăng nhập, nhưng phải được đánh giá cùng session và CORS; không đơn giản sao chép vào ứng dụng có luồng bảo mật khác.

## 14. SPA dùng GET /csrf: không tự biến token thành raw hay masked

Ví dụ JavaScript cho SPA và API cùng origin:

~~~javascript
let csrfState = null;

async function refreshCsrf() {
  const response = await fetch("/csrf", {
    method: "GET",
    credentials: "same-origin",
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error("CSRF bootstrap failed: " + response.status);
  }
  const body = await response.json();
  if (!body.token || !body.headerName) {
    throw new Error("CSRF bootstrap is missing fields");
  }
  csrfState = body;
  return csrfState;
}

async function saveProfile(displayName) {
  const csrf = csrfState ?? await refreshCsrf();

  const response = await fetch("/profile", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      [csrf.headerName]: csrf.token
    },
    body: JSON.stringify({displayName})
  });

  if (!response.ok) {
    throw new Error("Profile update failed: " + response.status);
  }
  return response;
}

async function onLoginSucceeded() {
  // Không sử dụng token được cấp trước khi authentication chuyển trạng thái.
  csrfState = null;
  await refreshCsrf();
}
~~~

Đoạn JavaScript minh họa luồng token, không phải mã điều phối đăng nhập, xử lý lỗi nghiệp vụ hoặc retry hoàn chỉnh. Nó giả định API xử lý JSON và route POST tồn tại. **Nếu session hết hạn hoặc logout ở tab khác**, token vẫn có thể stale; ứng dụng cần thiết kế lại bước xác thực/refresh phù hợp.

Không tạo vòng lặp **“mỗi lần 403 thì tự POST lại mãi”**. 403 có thể do thiếu quyền hoặc CSRF; với thao tác không idempotent như thanh toán/đặt hàng, retry thiếu kiểm soát có thể gây tác động nghiêm trọng. Nên xác nhận nguyên nhân, refresh có kiểm soát và chỉ retry khi hiểu rõ tính an toàn của request.

## 15. Servlet: cookie CSRF cho SPA và handler raw/masked

Nếu chủ đích cho SPA đọc cookie `XSRF-TOKEN` rồi gửi raw value trong header `X-XSRF-TOKEN`, backend cần bảo đảm hai việc:

1. CSRF cookie được materialize khi cần (deferred token không bị bỏ qua).
2. Giá trị raw trong header được request handler xử lý **khác** với masked token mà form HTML sử dụng.

### Ví dụ handler kết hợp

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.util.function.Supplier;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRequestHandler;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;
import org.springframework.security.web.csrf.XorCsrfTokenRequestAttributeHandler;
import org.springframework.util.StringUtils;

public final class SpaCsrfTokenRequestHandler
        implements CsrfTokenRequestHandler {

    private final CsrfTokenRequestHandler plain =
        new CsrfTokenRequestAttributeHandler();

    private final CsrfTokenRequestHandler xor =
        new XorCsrfTokenRequestAttributeHandler();

    @Override
    public void handle(HttpServletRequest request,
                       HttpServletResponse response,
                       Supplier<CsrfToken> csrfToken) {
        // Form vẫn nhận masked token, giảm rủi ro BREACH.
        xor.handle(request, response, csrfToken);

        // Khi dùng cookie repo, chủ động materialize token cần cấp cho SPA.
        csrfToken.get();
    }

    @Override
    public String resolveCsrfTokenValue(
            HttpServletRequest request, CsrfToken csrfToken) {
        String header = request.getHeader(csrfToken.getHeaderName());
        return StringUtils.hasText(header)
            ? plain.resolveCsrfTokenValue(request, csrfToken)
            : xor.resolveCsrfTokenValue(request, csrfToken);
    }
}
~~~

Cấu hình trong Servlet chain được chọn:

~~~java
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

http.csrf(csrf -> csrf
    .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
    .csrfTokenRequestHandler(new SpaCsrfTokenRequestHandler())
);
~~~

Ở frontend, JavaScript có thể đọc raw cookie CSRF **nếu cookie cho phép**, rồi gửi giá trị ấy trong header mà repository định nghĩa. Cách đọc cookie phải tôn trọng tên, URL decoding và cookie scope; không sử dụng một regex đơn giản như một bằng chứng rằng cookie luôn chỉ có một bản ở mọi Path.

**Giới hạn của ví dụ:**

- Dành cho Spring Security Servlet có API handler tương thích (kiểm tra phiên bản đang sử dụng).
- Không ghép với một handler khác phát token dạng hoàn toàn khác mà không xác định hợp đồng.
- Có thể làm token được nạp ở nhiều GET hơn cơ chế deferred mặc định; đây là trade-off có chủ đích.
- Cookie readable chỉ dành cho mô hình SPA cần JavaScript đọc token; form session thông thường không nhất thiết cần nó.
- Token/cookie có thể bị clear sau login/logout và cần được materialize lại; test luồng này riêng.
- Nếu header và form parameter cùng được gửi, handler ưu tiên header theo code; cần tránh nguồn token mâu thuẫn trong cùng request.

**Đừng áp dụng handler này cho API stateless Bearer-only một cách máy móc.** Phải có threat model, repository và đường authentication phù hợp.

## 16. Reactive/WebFlux: nguyên nhân tương đương, API không giống Servlet

Với WebFlux, Spring Security dùng:

- `CsrfWebFilter` thay cho `CsrfFilter` Servlet.
- `ServerCsrfTokenRepository` thay cho `CsrfTokenRepository` Servlet.
- `WebSessionServerCsrfTokenRepository` hoặc `CookieServerCsrfTokenRepository` cho cách lưu tương ứng.
- `ServerCsrfTokenRequestHandler` cho việc expose, lấy và xử lý submitted token theo cơ chế reactive.
- `Mono<CsrfToken>`/`ServerWebExchange` thay cho `HttpServletRequest` và request attributes kiểu Servlet.

**Không dùng `HttpSessionCsrfTokenRepository` trong WebFlux** và không dùng `CookieServerCsrfTokenRepository` trong Servlet chain. Kết quả 403 có ý nghĩa bảo mật tương tự nhưng vị trí filter, session management và cách token materialize khác.

### 16.1. WebFlux security chain ví dụ

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveSessionSecurity {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        http.authorizeExchange(exchanges -> exchanges
            .pathMatchers("/login", "/csrf").permitAll()
            .pathMatchers("/profile/**").authenticated()
            .anyExchange().authenticated()
        );

        http.formLogin(Customizer.withDefaults());
        http.csrf(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Đây là cấu hình minh họa ứng dụng có session/form login. Nếu WebFlux chỉ là API stateless hoặc ứng dụng có nhiều `SecurityWebFilterChain`, phải xác định chính sách cho đúng route và stack thực tế.

### 16.2. Endpoint trả token được materialize trong Reactive

WebFlux có thể đặt một `Mono<CsrfToken>` trong exchange attributes theo key `CsrfToken.class.getName()`. Endpoint phải **trả hoặc tiêu thụ publisher** để token được resolve:

~~~java
import java.util.Map;
import org.springframework.http.CacheControl;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class ReactiveCsrfBootstrap {

    @GetMapping("/csrf")
    public Mono<Map<String, String>> csrf(ServerWebExchange exchange) {
        exchange.getResponse().getHeaders()
            .setCacheControl(CacheControl.noStore());

        Mono<CsrfToken> mono =
            exchange.getAttribute(CsrfToken.class.getName());
        if (mono == null) {
            return Mono.error(new IllegalStateException(
                "No CSRF token publisher: check security chain"
            ));
        }

        return mono.map(token -> Map.of(
            "headerName", token.getHeaderName(),
            "parameterName", token.getParameterName(),
            "token", token.getToken()
        ));
    }
}
~~~

Ví dụ giả định phiên bản Spring Security WebFlux có request attribute như đã nêu. `mono.map(...)` khiến token được resolve khi response được subscribe; chỉ gán publisher vào biến rồi không dùng có thể khiến việc lazy materialization chưa xảy ra. **Không gọi `block()` trên request thread của Reactive** để cố lấy token.

Với default handler có masking, giá trị `token` trong JSON có thể là dạng đã mask; client gửi lại chính giá trị ấy theo cơ chế backend. Đừng dựa vào API của Servlet để tự giải mask trong WebFlux.

### 16.3. Cookie repository Reactive

~~~java
import org.springframework.security.web.server.csrf.CookieServerCsrfTokenRepository;

http.csrf(csrf -> csrf.csrfTokenRepository(
    CookieServerCsrfTokenRepository.withHttpOnlyFalse()
));
~~~

**Chỉ đổi repository chưa chứng minh SPA hoạt động.** Phải kiểm tra token được materialize, cookie được phát đúng scope, header mà frontend gửi và cách `ServerCsrfTokenRequestHandler` của phiên bản hiện hành xử lý raw/masked. Nếu frontend đang dùng một chiến lược token khác, cần cập nhật toàn bộ hợp đồng thay vì sửa riêng một dòng cấu hình.

### 16.4. WebFlux session khác Servlet HttpSession

Reactive dùng `WebSession`. Khi theo dõi lỗi trên nhiều node, cần kiểm tra session storage/config của WebFlux hoặc Spring Session Reactive nếu ứng dụng sử dụng. Một cookie phiên còn nguyên trên browser không chứng minh node backend đã khôi phục đúng dữ liệu expected token.

## 17. Cookie scope, CORS và proxy: ba thứ dễ bị lẫn

Giả sử frontend ở `https://app.example.com`, API ở `https://api.example.com`. Đây là **cross-origin**, dù có thể cùng site theo cookie policy. Một request fetch:

~~~javascript
await fetch("https://api.example.com/profile", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({displayName: "Alice"})
});
~~~

Để flow hoạt động, cần kiểm tra **đồng thời**:

1. Cookie session có scope và attributes cho phép gửi đến API hostname không?
2. API có cho phép Origin cụ thể, method và header CSRF trong CORS config không?
3. Preflight OPTIONS có thành công để browser gửi POST thật không?
4. Backend có trả `Access-Control-Allow-Credentials: true` khi thiết kế dùng credentials và có allowed origin phù hợp không?
5. CSRF repository có đọc expected token từ **đúng ngữ cảnh** không?
6. Token header do frontend gửi có đúng tên và raw/masked format không?

**Không dùng `Access-Control-Allow-Origin: *` cho credentialed requests.** Đồng thời, CORS được cấu hình đúng vẫn **không tự đảm bảo** token CSRF đúng; nó điều khiển một lớp chính sách browser khác.

### Phân biệt preflight 403 và POST CSRF 403

~~~http
OPTIONS /profile HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Nếu OPTIONS bị từ chối:

~~~text
Browser không gửi POST tiếp theo
=> CSRF filter của POST chưa kiểm tra token
~~~

Nếu OPTIONS thành công nhưng POST 403:

~~~text
Browser gửi POST thật
=> xem CSRF exception, session, handler, authorization...
~~~

Đừng thay đổi CSRF handler để sửa một preflight mà CSRF POST chưa từng xử lý.

## 18. Proxy, TLS termination và session cookie bị thay đổi

Ứng dụng chạy nội bộ:

~~~text
http://spring-service:8080
~~~

Browser truy cập:

~~~text
https://app.example.com
~~~

Reverse proxy kết thúc TLS và có thể ảnh hưởng các header liên quan:

- `Set-Cookie` và cookie attributes của response.
- `Host`, `Forwarded`, `X-Forwarded-Proto`/`X-Forwarded-Host` theo trust boundary.
- Path prefix (ví dụ `/gateway/profile` ngoài public khác `/profile` nội bộ).
- Routing của GET token và POST tới các service/cluster khác nhau.
- Cache HTML/JSON/token và các rewrite rules.

Nếu server sinh cookie với Path/Domain hoặc Secure attribute không đúng cho origin công khai, browser có thể **không gửi lại cookie**, dẫn tới một expected token khác. Đừng chữa bằng cách tắt `Secure` hoặc mở `Domain` rộng không kiểm soát.

### Kiểm tra ở hai điểm

| Điểm đo | Câu hỏi |
|---|---|
| Origin Spring | Repository/handler nào chạy? Có session/token tương ứng không? |
| Response qua proxy | `Set-Cookie` có bị thay/loại không? Path/Domain/Secure đúng chưa? |
| Browser cookie store | Cookie được nhận/lưu trong phạm vi nào? Có bị chặn không? |
| POST cuối cùng | Cookie nào được gửi, header CSRF nào còn nguyên? |
| Application logs | Node nào xử lý, chain nào chọn, exception gì? |

**Không mặc định tin mọi header forwarded do client gửi.** Chỉ cấu hình hỗ trợ forwarded headers theo proxy đáng tin, tránh tạo thêm vấn đề Host/header spoofing khi sửa lỗi cookie.

## 19. Load balancer và session storage: lỗi “chỉ xảy ra vài lần”

Xét mô hình:

~~~mermaid
flowchart LR
    B[Browser] --> LB[Load balancer]
    LB --> N1[Spring node 1]
    LB --> N2[Spring node 2]
    N1 --> S[(Shared session store?)]
    N2 --> S
~~~

Nếu node 1 lưu expected token trong local session nhưng POST đến node 2 không khôi phục được session/token:

~~~text
GET /csrf -> node 1
  Session A chứa expected token R

POST /profile -> node 2
  Không thấy session A / expected token R
  => thường bị CSRF validation từ chối
~~~

Các khả năng:

- Ứng dụng chưa cấu hình session sharing trong môi trường nhiều node.
- Session affinity/sticky routing không hoạt động như dự kiến.
- Node dùng cookie path/session identifier khác nhau.
- Session serializer/schema hoặc TTL khác nhau.
- User đăng nhập ở node 1 rồi POST rơi sang node 2 thiếu authentication state.

### Không chỉ “bật sticky session” là xong

Session affinity có thể là một phần giải pháp vận hành nhưng không thay thế thiết kế session storage, failover, logout và bảo vệ phiên. Khi cần nhiều node, hãy xác định yêu cầu của ứng dụng: shared session store, affinity có bảo vệ/failover hoặc mô hình khác. Đo qua **cùng luồng GET token → POST** tại nhiều node.

Nếu cả authentication và CSRF đều không được khôi phục, request có thể trả 401/302 thay vì 403; status là một chỉ dấu, không phải mô tả toàn bộ lỗi cluster.

## 20. Cache và fragment HTML: token sai phiên dù cookie đúng

Một nguy cơ nghiêm trọng khác: reverse proxy hoặc CDN cache HTML chứa token:

~~~text
GET /profile của user A:
  HTML chứa hidden _csrf của phiên A
  CDN lưu body

GET /profile của user B:
  CDN trả HTML đã lưu
  Browser B có session B
  POST dùng _csrf của A
  => 403 hoặc hành vi không mong muốn
~~~

Đây không chỉ là lỗi chức năng. Nếu response chứa thông tin cá nhân, cache chung có thể gây **rò rỉ dữ liệu**.

Với HTML cá nhân hóa hoặc JSON CSRF bootstrap, thường cần cache policy phù hợp, ví dụ:

~~~http
Cache-Control: no-store
~~~

Và cấu hình thực tế để CDN/proxy không cache những response đó. `Cache-Control` chỉ hiệu quả khi các cache tuân thủ hoặc được cấu hình tương thích; cần test **cache hit và cache miss** thay vì tin vào một dòng header.

### ETag/304 và trang cũ

Một GET có điều kiện có thể trả `304 Not Modified`; browser/cache có thể dùng body HTML cũ cùng metadata cập nhật theo HTTP caching. Nếu token/session đã thay đổi nhưng body HTML cũ được dùng, hidden token có thể stale. Không kết luận chỉ bằng response 304 không body: cần xác định **HTML nào thật sự được submit**.

### SPA state cache cũng là cache

Ngay cả khi CDN không cache, frontend có thể giữ token trong module singleton, state store hoặc một tab sống lâu. Sau login/logout/session expiry, CSRF state này vẫn cũ. Cần thiết kế refresh token có chủ đích, không chỉ sửa HTTP cache.

## 21. MockMvc: kiểm tra filter trước, rồi kiểm tra đúng session

Ở Servlet, `spring-security-test` cung cấp `csrf()` để test đường xác minh:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// User có quyền nhưng không có token: CSRF từ chối.
mockMvc.perform(post("/profile")
        .with(user("alice").roles("USER"))
        .contentType("application/json")
        .content("{\"displayName\":\"Alice\"}"))
    .andExpect(status().isForbidden());

// Test helper thêm token hợp lệ theo cấu hình test.
mockMvc.perform(post("/profile")
        .with(user("alice").roles("USER"))
        .with(csrf())
        .contentType("application/json")
        .content("{\"displayName\":\"Alice\"}"))
    .andExpect(status().isNoContent());

// Helper sinh một token không hợp lệ để test đường reject.
mockMvc.perform(post("/profile")
        .with(user("alice").roles("USER"))
        .with(csrf().useInvalidToken())
        .contentType("application/json")
        .content("{\"displayName\":\"Alice\"}"))
    .andExpect(status().isForbidden());
~~~

Ví dụ giả định:

- MockMvc đã tích hợp Spring Security filters.
- Có endpoint `POST /profile` mà user `ROLE_USER` được phép gọi.
- Khi request đến controller, nó trả HTTP 204; response khác cần thay kỳ vọng test.
- Chain đang kiểm tra CSRF, không phải một API chain đã chủ đích loại CSRF.

**`with(csrf())` PASS không chứng minh frontend thật biết nhận token hoặc giữ cookie đúng phiên.** Nó kiểm tra cơ chế filter ở môi trường test, không kiểm tra luồng bootstrap, masking từ HTML, CORS hay proxy.

### Một controller fixture đơn giản cho lab

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProfileLabController {

    record ProfileUpdate(String displayName) {}

    @PostMapping("/profile")
    ResponseEntity<Void> update(@RequestBody ProfileUpdate body) {
        // Demo không thực hiện cập nhật dữ liệu thật.
        return ResponseEntity.noContent().build();
    }
}
~~~

Trong ứng dụng thực tế, controller còn phải bảo vệ quyền trên tài nguyên cụ thể và validate input; CSRF chỉ là một lớp bảo vệ request của browser.

## 22. MockMvc: test chính xác token A của session A không hợp lệ với session B

Đây là phép thử quan trọng nhất cho lỗi “có token nhưng sai phiên”. Sử dụng endpoint `GET /csrf` của mục 13, repository dựa trên session, `ObjectMapper` và Spring Security Test:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

ObjectMapper objectMapper = new ObjectMapper();

// GET A: materialize CSRF token thuộc session A.
MvcResult bootstrapA = mockMvc.perform(get("/csrf"))
    .andExpect(status().isOk())
    .andReturn();

JsonNode jsonA = objectMapper.readTree(
    bootstrapA.getResponse().getContentAsString()
);
String tokenA = jsonA.path("token").asText();
String headerNameA = jsonA.path("headerName").asText();
MockHttpSession sessionA =
    (MockHttpSession) bootstrapA.getRequest().getSession(false);
assertNotNull(sessionA);

// GET B ở một request mới không có cookie của A:
// tạo token khác thuộc session B.
MvcResult bootstrapB = mockMvc.perform(get("/csrf"))
    .andExpect(status().isOk())
    .andReturn();

JsonNode jsonB = objectMapper.readTree(
    bootstrapB.getResponse().getContentAsString()
);
String tokenB = jsonB.path("token").asText();
String headerNameB = jsonB.path("headerName").asText();
MockHttpSession sessionB =
    (MockHttpSession) bootstrapB.getRequest().getSession(false);
assertNotNull(sessionB);

// Token A + session A: CSRF validation phải chấp nhận.
mockMvc.perform(post("/profile")
        .session(sessionA)
        .with(user("alice").roles("USER"))
        .header(headerNameA, tokenA)
        .contentType("application/json")
        .content("{\"displayName\":\"Alice\"}"))
    .andExpect(status().isNoContent());

// Token A + session B: không được chấp nhận.
mockMvc.perform(post("/profile")
        .session(sessionB)
        .with(user("alice").roles("USER"))
        .header(headerNameB, tokenA)
        .contentType("application/json")
        .content("{\"displayName\":\"Alice\"}"))
    .andExpect(status().isForbidden());

// Token B + session B: đối chứng hợp lệ.
mockMvc.perform(post("/profile")
        .session(sessionB)
        .with(user("alice").roles("USER"))
        .header(headerNameB, tokenB)
        .contentType("application/json")
        .content("{\"displayName\":\"Alice\"}"))
    .andExpect(status().isNoContent());
~~~

Đây là code mẫu để **đặt vào một test method đã có `MockMvc mockMvc`** và controller/config tương ứng, không phải một class tự biên dịch độc lập. Test dùng `HttpSessionCsrfTokenRepository` và handler có thể nhận giá trị từ endpoint JSON đúng dạng. Với cookie repository hoặc custom handler, phải sửa cách giữ cookie và đối chiếu token.

### Kết luận có thể rút ra

Nếu A+A và B+B thành công, còn A+B bị từ chối, hệ thống đang gắn expected CSRF token với session đúng như thiết kế. Khi lỗi tương tự xảy ra ở production, cần tìm **lý do browser đã dùng token A với session B**.

Nếu A+B thành công bất ngờ, phải kiểm tra lại test fixture, repository thực tế, CSRF matcher, security chain và việc `POST /profile` có thật sự được CSRF filter bảo vệ hay không. Không kết luận “framework tự chấp nhận token khác phiên” từ một assertion thiếu context.

### Lưu ý về token được mask

Hai GET độc lập có thể trả token string khác nhau **vì masking** ngay cả khi thuộc cùng underlying session. Phép thử trên phân tách session A/B nên vẫn cần hiểu masking. Để xác minh **masking riêng biệt**, hãy gửi hai GET **trong cùng một session** và kiểm tra cả hai token được handler chấp nhận, thay vì ép chuỗi phải giống nhau.

## 23. WebTestClient: test CSRF Reactive và ranh giới của mock helper

Trong Reactive/WebFlux, test cơ bản:

~~~java
import org.springframework.http.MediaType;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;

// CSRF enabled; POST không token.
webTestClient.mutateWith(mockUser("alice").roles("USER"))
    .post()
    .uri("/profile")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue("{\"displayName\":\"Alice\"}")
    .exchange()
    .expectStatus().isForbidden();

// Mock CSRF token hợp lệ giúp request đi qua CSRF filter.
webTestClient.mutateWith(mockUser("alice").roles("USER"))
    .mutateWith(csrf())
    .post()
    .uri("/profile")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue("{\"displayName\":\"Alice\"}")
    .exchange()
    .expectStatus().isNoContent();
~~~

Test giả định WebTestClient đã được tích hợp Spring Security và route có controller trả 204. Header `Content-Type: application/json` giúp request tới controller nhận JSON kiểu record không bị lỗi binding hoặc 415 Unsupported Media Type sau khi vượt qua CSRF.

### Test endpoint bootstrap thực sự materialize Mono

~~~java
import static org.hamcrest.Matchers.not;
import static org.hamcrest.Matchers.emptyOrNullString;

webTestClient.get()
    .uri("/csrf")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().valueMatches(
        "Cache-Control", ".*no-store.*"
    )
    .expectBody()
    .jsonPath("$.token").value(not(emptyOrNullString()))
    .jsonPath("$.headerName").exists();
~~~

Test này xác minh endpoint WebFlux ở mục 16 trả token và không cache, nhưng **chưa kiểm tra cookie/session có được chuyển qua browser và proxy như production**.

Khi cần chứng minh token A/B khác session, hãy dùng HTTP integration test với cookie jar hoặc Playwright với hai browser contexts tách biệt; mock helper `csrf()` không đại diện luồng tải token thực tế.

## 24. Playwright: hai browser contexts để tái hiện mismatched session

Playwright có thể tạo **hai browser contexts độc lập**, mỗi context có cookie jar riêng. Một test lab có thể so:

~~~text
Context A:
  GET /csrf -> token A, session A
  POST /csrf-lab/submit với token A -> 204

Context B:
  GET /csrf -> token B, session B
  POST /csrf-lab/submit với token A -> 403
  POST /csrf-lab/submit với token B -> 204
~~~

Để làm một fixture tập trung vào CSRF, route `/csrf-lab/submit` có thể `permitAll()` ở authorization, **nhưng vẫn qua CSRF filter** và chỉ trả 204 khi request hợp lệ. Như vậy kết quả không bị nhiễu bởi login.

Ví dụ Playwright JavaScript giả định backend lab có `GET /csrf` và `POST /csrf-lab/submit`:

~~~javascript
import { test, expect } from "@playwright/test";

test("token từ session khác bị từ chối", async ({ browser }) => {
  const contextA = await browser.newContext();
  const contextB = await browser.newContext();

  try {
    const pageA = await contextA.newPage();
    const pageB = await contextB.newPage();
    const base = "http://localhost:8080";

    // Thiết lập một document cùng origin để fetch dùng cùng cookie jar.
    await pageA.goto(base + "/csrf-lab");
    await pageB.goto(base + "/csrf-lab");

    async function load(page) {
      return page.evaluate(async () => {
        const response = await fetch("/csrf", {
          credentials: "same-origin",
          cache: "no-store"
        });
        if (!response.ok) throw new Error("Failed to load CSRF");
        return response.json();
      });
    }

    async function submit(page, tokenInfo) {
      return page.evaluate(async csrf => {
        const response = await fetch("/csrf-lab/submit", {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/json",
            [csrf.headerName]: csrf.token
          },
          body: JSON.stringify({value: "demo"})
        });
        return response.status;
      }, tokenInfo);
    }

    const tokenA = await load(pageA);
    const tokenB = await load(pageB);

    expect(await submit(pageA, tokenA)).toBe(204);
    expect(await submit(pageB, tokenA)).toBe(403);
    expect(await submit(pageB, tokenB)).toBe(204);
  } finally {
    await contextA.close();
    await contextB.close();
  }
});
~~~

**Điều kiện của ví dụ:** route `/csrf-lab` tồn tại trong ứng dụng demo; `/csrf` cho phép lấy token và materialize repository; `/csrf-lab/submit` được authorization cho phép, CSRF vẫn bật và controller trả 204. Nếu không có những fixture ấy, test không thể chạy nguyên trạng.

Test với hai contexts xác minh session isolation và browser cookie behavior cơ bản. Để chẩn đoán **raw/masked cookie handler**, cần thêm biến thể gửi raw cookie và biến thể gửi token JSON, so với response/exception để tách lỗi format khỏi lỗi session.

## 25. Kiểm tra bằng curl nhưng không đưa bí mật vào shell history

Lệnh sau minh họa hai thao tác HTTP có quyền trên máy test:

~~~bash
# GET bootstrap và lưu cookie.
curl -i -c cookies-A.txt -b cookies-A.txt \
  -H 'Accept: application/json' \
  http://localhost:8080/csrf

# POST không token làm đối chứng âm tính.
curl -i -b cookies-A.txt \
  -H 'Content-Type: application/json' \
  --data '{"displayName":"Demo"}' \
  http://localhost:8080/profile
~~~

Ở ứng dụng yêu cầu login, request POST trên còn có thể bị authentication từ chối; hãy tạo session test hợp lệ hoặc dùng fixture CSRF-only. Giá trị token và cookie không được đặt trong ticket, terminal transcript hoặc chat công khai.

Để gửi token thật trong test HTTP, nên dùng công cụ có **biến bí mật** hoặc file cấu hình tạm được bảo vệ, điền đúng `headerName` do bootstrap trả; tránh viết nguyên CSRF token và session cookie trong command line. Cookie jars `cookies-A.txt` và `cookies-B.txt` cũng chứa dữ liệu nhạy cảm: giới hạn quyền truy cập, không commit và xóa an toàn khi test kết thúc.

### Cách tạo kiểm thử session B

1. Tạo một cookie jar mới, không dùng lại jar A.
2. GET token qua jar B để expected token thuộc session B được materialize.
3. Gửi token A cùng jar B trong môi trường lab đã kiểm soát.
4. Đối chiếu status và exception ở backend, rồi gửi token B cùng jar B làm đối chứng.

Nếu cả hai token thành công hoặc đều thất bại, kiểm tra chain, repository, auth, token format và session cookie trước khi rút ra kết luận.

## 26. Logging chẩn đoán không tiết lộ token

Trong môi trường dev/staging, bật log có chọn lọc khi cần:

~~~properties
logging.level.org.springframework.security=DEBUG
logging.level.org.springframework.security.web.csrf=DEBUG
logging.level.org.springframework.security.web.server.csrf=DEBUG
~~~

Ở production, tránh bật TRACE/DEBUG rộng hoặc lâu dài. Security logging có thể phát sinh nhiều dữ liệu; áp dụng kiểm soát truy cập, lưu giữ và che thông tin nhạy cảm.

Nên thu:

| Trường chẩn đoán | Ví dụ diễn giải an toàn |
|---|---|
| Request ID/trace ID | Gắn GET token → login → POST |
| Security chain | Chain session, chain API hoặc reactive chain |
| Repository type | HttpSession, Cookie, WebSession hoặc custom |
| Token expected present | true/false (không in giá trị) |
| Submitted token present | true/false |
| Submitted location | header `X-CSRF-TOKEN` hoặc form parameter |
| Token format path | masked form, raw cookie header, JSON bootstrap |
| Session continuity | cùng/khác context được xác minh an toàn |
| Cookie present/scope | Có gửi cookie; Path, Domain, Secure, SameSite |
| Authentication transition | login/logout/session recreation xảy ra giữa các request |
| CSRF error class | Missing/Invalid hoặc thông báo cụ thể của framework |
| Response source | Spring, reverse proxy/WAF, browser preflight |

**Không log:** CSRF token raw/masked, session cookie, JWT, password, Authorization header hoặc body chứa dữ liệu riêng tư. Nếu cần correlation, ưu tiên ID request và cờ trạng thái; một hash/fingerprint của token cũng có thể nhạy cảm và có nguy cơ làm tăng khả năng liên kết dữ liệu, nên phải được security review trước khi dùng.

### Lỗi ở handler không chứng minh thiếu role

Nếu log ghi `InvalidCsrfTokenException`, việc thêm `ROLE_ADMIN` cho user không sửa được token. Nếu CSRF validation thành công nhưng tiếp theo `AuthorizationDeniedException`/`AccessDeniedException`, lại phải điều tra quyền. Phân biệt **filter nào từ chối trước** rồi sửa đúng lớp.

## 27. Bảng chẩn đoán nhanh: dấu hiệu nào gợi ý lỗi gì?

| Hiện tượng | Giả thuyết cần kiểm tra | Bằng chứng phản biện và hướng xử lý |
|---|---|---|
| GET token thành công, POST có token nhưng 403 sau login | Token cũ bị clear/rotate | GET token lại sau authentication; test cùng phiên mới |
| POST chỉ lỗi khi session timeout | Session cũ hoặc cookie không còn hợp lệ | Kiểm tra timeout và trình tự refetch sau tái xác thực |
| Chỉ lỗi trên SPA dùng cookie token, HTML form vẫn hoạt động | Raw cookie header vs XOR-masked handler | So sánh request handler cho header và parameter |
| Hai GET cùng session có hidden token khác nhau | Masking thay đổi biểu diễn | Test cả hai giá trị bằng handler đúng; không so chuỗi trực tiếp |
| POST thiếu `JSESSIONID` nhưng có `X-CSRF-TOKEN` | Session mismatch | Kiểm tra Domain/Path/SameSite/Secure và fetch credentials |
| POST có cookie nhưng backend không tìm thấy session | Session storage, cluster, TTL | Đối chiếu node và session store; không chỉ nhìn cookie |
| GET token và POST ở hai route qua chain khác | Repository/handler không tương thích | Log first-match security chain của cả hai |
| Header CSRF không đến backend | Proxy/gateway rewrite hoặc client chưa gắn | Browser Network so với upstream logs |
| OPTIONS 403, không có POST | CORS preflight | Xem Origin/allowed methods/headers; không sửa CSRF |
| Console nêu CSP `connect-src`, không có API request | CSP chặn browser | Sửa CSP trên HTML theo origin hợp lệ |
| Cookie `XSRF-TOKEN` xuất hiện nhưng JS không đọc được | HttpOnly hoặc cookie khác origin/path | Chọn strategy; không tắt HttpOnly tùy tiện |
| Local HTTP ổn, HTTPS qua proxy lỗi | Cookie Secure/forwarded host hoặc gateway rules | So sánh origin và public response/cookies |
| Chỉ một phần người dùng gặp lỗi | Edge cache, canary variant, node routing | So sánh cache hit/miss, node và policy version |
| Từ browser POST 403, `with(csrf())` PASS | Frontend token loading/session flow sai | Test GET token → POST thật với cookie |
| 403 trên endpoint cần admin, CSRF vẫn hợp lệ | Authorization hoặc method security | Kiểm tra authority thực tế sau CSRF validation |
| 400 với `RequestRejectedException` | HTTP firewall không chấp nhận URL | Sửa URL/request normalization; không đổi token |
| 403 có trang WAF, không có app log | Edge từ chối trước Spring | Tìm WAF rule/trace, không nới CSRF repo |
| Response token có thể bị cache công khai | Lộ hoặc sai phiên | Chặn cache nhạy cảm; điều tra tác động dữ liệu |

**Không có một dấu hiệu đơn lẻ chứng minh toàn bộ nguyên nhân.** Tạo đối chứng: cùng token đúng session, token sai session, raw cookie so với masked form, same-origin so với cross-origin; luôn đối chiếu **filter thực sự trả lỗi**.

## 28. Kịch bản A — Hai tab và session đổi sau đăng nhập lại

**Hiện tượng:** Tab 1 mở form profile. Tab 2 logout, sau đó login lại. Khi quay lại Tab 1 và nhấn **Lưu**, server trả 403 dù hidden input vẫn có token.

~~~text
Tab 1: GET /profile → token A, session A
Tab 2: POST /logout → session/token A bị xóa
Tab 2: POST /login → session/token B có hiệu lực
Tab 1: POST /profile với token A và cookie B → 403
~~~

**Cách kiểm tra:**

1. Quan sát session cookie hiện hành và thời điểm login/logout trên cả hai tab.
2. Xác nhận Tab 1 vẫn dùng hidden token từ response cũ.
3. Tái hiện với GET token mới sau login; nếu POST mới hợp lệ, đã có bằng chứng về stale token.
4. Kiểm tra handler và chain vẫn như cũ, tránh nhầm với permission changed.

**Cách sửa:** sau authentication transition, làm mới form/token trước khi cho submit. Với ứng dụng có tab sống lâu, cân nhắc UX cảnh báo phiên đã thay đổi và tải lại dữ liệu; không tái gửi thao tác thay đổi trạng thái một cách tự động vô hạn.

Nếu session ID đổi nhưng token vẫn hợp lệ theo repository, phải tiếp tục tìm nguyên nhân khác thay vì kết luận ngay.

## 29. Kịch bản B — Form Thymeleaf thành công, SPA cookie header 403

**Hiện tượng:** cùng backend Servlet, form server-rendered POST thành công nhưng request `fetch` từ SPA gửi `X-XSRF-TOKEN` lấy từ cookie lại 403.

**Phân tích khác biệt:**

| Form SSR | SPA cookie |
|---|---|
| Token được expose qua `_csrf.token` | Raw token từ `document.cookie` |
| Mặc định có thể là masked value | Có thể là raw repository value |
| Gửi qua parameter `_csrf` | Gửi qua header `X-XSRF-TOKEN` |
| XOR handler biết giải mask form | Phải có nhánh handler hiểu raw header |

**Thử nghiệm:**

1. Xác nhận cả hai request dùng cùng authentication session và expected repository.
2. Kiểm tra frontend gửi đúng tên header và raw cookie value (không ghi value vào log).
3. Kiểm tra request handler của Spring Security; có đang chỉ giải token dạng mask không?
4. Thử một GET `/csrf` trả token được request handler chuẩn bị, rồi gửi lại đúng giá trị ấy.
5. Nếu chọn chiến lược cookie raw, cấu hình handler theo hợp đồng; kiểm tra lại cả **form HTML** và **SPA**.

**Không** chuyển toàn bộ ứng dụng sang `'unsafe-inline'` CSP, tắt CORS hoặc bỏ CSRF. Những cấu hình đó không giải quyết nguyên nhân biểu diễn token không khớp.

## 30. Kịch bản C — Frontend và API khác origin, cookie không được gửi

**Hiện tượng:** SPA ở `https://app.example.com` gọi `https://api.example.com`. GET token đôi khi thành công nhưng POST trả 403 hoặc thậm chí JavaScript chỉ thấy lỗi CORS.

**Trình tự kiểm tra đúng:**

1. Ở GET token: browser có gửi cookie credentials với request tới API không? API có trả token được phép đọc theo SOP/CORS không?
2. Ở POST: browser có gửi request thật, hay OPTIONS preflight bị từ chối?
3. Nếu POST đã gửi, cookie session có thật sự nằm trong request không? `Domain`/`Path`/`SameSite`/`Secure` có phù hợp?
4. Backend dùng repository nào? Header token đúng tên và raw/masked format không?
5. Các rule tại reverse proxy có thay cookie/path hoặc chặn custom header không?

**Sửa đúng lớp:** nếu preflight lỗi thì sửa CORS; nếu thiếu cookie thì sửa cookie scope/credentials theo thiết kế; nếu token không khớp thì sửa repository/handler/session continuity. Không cho mọi origin đọc token và không dùng wildcard CORS cho credentialed requests.

## 31. Kịch bản D — Một node thành công, node còn lại 403

**Hiện tượng:** trong staging một instance, CSRF POST luôn thành công. Khi chạy nhiều instance sau load balancer, POST thất bại ngẫu nhiên.

Đối chiếu:

~~~text
GET /csrf:     request req-1001 -> node A, session storage SA
POST /profile: request req-1002 -> node B, session storage SB

Nếu node B không có expected token cho cùng session,
submitted token có thể bị đánh giá là thiếu hoặc không khớp.
~~~

**Điểm cần kiểm tra:**

- Các node có cùng session store hoặc chiến lược session affinity được thiết kế không?
- Có lỗi serialize/deserialize CSRF token hoặc session state không?
- Session TTL, cookie name, Path hoặc key storage có khác giữa node không?
- Các instance có cùng version Spring Security/config/repository không?
- CDN có cache response bootstrap chứa token từ node khác không?

**Hướng sửa:** đồng bộ hạ tầng session, bảo vệ cache nhạy cảm và triển khai nhất quán; không tăng quyền hoặc vô hiệu CSRF để giải quyết một lỗi state distribution.

## 32. Cách xử lý 403 ở frontend mà không làm suy yếu bảo mật

Khi nhận 403, frontend nên phân biệt **lỗi cần đăng nhập lại**, **thiếu quyền**, **CSRF token stale** và **request bị chặn khác**. Không thể suy chính xác từ một mã HTTP chung nếu backend không có error contract phù hợp.

Một phương án API có thể trả body lỗi có cấu trúc:

~~~json
{
  "type": "https://app.example.com/problems/csrf-validation",
  "title": "Request rejected",
  "status": 403,
  "requestId": "req-example"
}
~~~

Đây chỉ là **ví dụ định dạng**, không phải endpoint hay contract mặc định của Spring Security. Không nên để response body tiết lộ expected token, phân tích chi tiết phiên hoặc chính sách nhạy cảm.

### Quy trình UX phù hợp

1. Nếu session hết hạn, hướng dẫn người dùng xác thực lại.
2. Nếu token stale đã được xác định, tải token mới theo luồng đã review.
3. Với form chứa dữ liệu chưa lưu, giữ input cục bộ an toàn để người dùng xác nhận submit lại sau khi phiên hợp lệ.
4. Với thao tác không idempotent hoặc có tác động lớn, không tự retry chỉ vì 403; cân nhắc idempotency key và trạng thái nghiệp vụ.
5. Nếu là thiếu quyền, hiển thị thông báo access denied, **không liên tục làm mới CSRF token**.

Với hệ thống quan trọng, backend nên có log phân loại lý do từ chối cho đội vận hành và message an toàn cho client. **Không biến mọi 403 thành “CSRF expired”**: điều đó che lỗi authorization và sai hạ tầng.

## 33. Quy trình điều tra có thể dùng ngay

~~~mermaid
flowchart TD
    A[POST thất bại] --> B{POST thực đã tới Spring?}
    B -- Không --> C[CORS preflight / CSP / proxy / mạng]
    B -- Có --> D{CSRF filter có từ chối?}
    D -- Không --> E[Authentication / authorization / firewall / app]
    D -- Có --> F{Submitted token hiện diện?}
    F -- Không --> G[Form, SPA bootstrap, header name]
    F -- Có --> H{Repository có expected token?}
    H -- Không --> I[Session, cookie, timeout, login/logout, lazy]
    H -- Có --> J{Handler nhận đúng dạng token?}
    J -- Không --> K[Raw/masked, XOR handler, header/parameter]
    J -- Có --> L{Session/token context còn trùng?}
    L -- Không --> M[Cookie scope, cache, cluster, stale token]
    L -- Có --> N[Xem custom validation/repository và log]
    G --> O[GET token -> POST cùng session, đối chứng]
    I --> O
    K --> O
    M --> O
    N --> O
    O --> P[Browser E2E + integration test + regression]
~~~

**Thao tác thực tế:**

1. Chụp lại HTTP method, route, timestamp, request ID và status; **che secrets**.
2. Xác nhận browser có gửi POST, không bị CORS/CSP chặn trước.
3. Xác nhận đúng Servlet/Reactive security chain và CSRF filter/repository.
4. Kiểm tra submitted token **có hiện diện, nằm ở đâu**, handler dùng raw/masked thế nào.
5. Kiểm tra expected token có gắn với đúng session/cookie của POST không.
6. Tìm login/logout/session timeout, tab cũ, cache và cluster giữa GET/POST.
7. Dùng test đối chứng A+A, A+B, B+B, thêm test form masked/SPA raw.
8. Chỉ sửa tầng đã xác định; chạy lại test authorization, CSRF, CORS và browser.

## 34. Bài thực hành tổng hợp

**Bối cảnh:** tạo ứng dụng Spring Boot demo có `GET /csrf`, trang form `/profile`, SPA gọi `POST /profile` bằng session cookie. Mục tiêu không phải “làm POST thành công bằng mọi giá”, mà là chứng minh **khi nào server chấp nhận token và khi nào đúng ra phải từ chối**.

1. **Servlet baseline:** cấu hình Spring Security, giữ CSRF enabled, tạo route GET token và POST profile trả 204 khi được phép.
2. GET CSRF token qua session A; gửi POST cùng session A và token nhận được. Xác minh hành vi hợp lệ.
3. Tạo session B độc lập, materialize token B; gửi POST với **token A cùng session B**. Xác nhận bị từ chối.
4. Gửi POST với token B/session B làm đối chứng. Đo sự khác biệt và log lý do.
5. Làm mới HTML form hai lần trong cùng session; quan sát masked token có thể khác dù cả hai đều hợp lệ theo handler.
6. Thử SPA đọc raw `XSRF-TOKEN` và gửi `X-XSRF-TOKEN` vào backend đang dùng XOR handler. Phân loại lỗi, sau đó áp dụng hợp đồng raw-header phù hợp.
7. Thực hiện login/logout rồi gửi request với token trước khi chuyển phiên. Quan sát token stale và refresh sau login/logout.
8. Thử cookie `Path`/`Domain` hoặc `SameSite` trong các context lab có kiểm soát. Dùng DevTools chứng minh browser có/không gửi cookie.
9. Thử SPA/API cross-origin, ghi preflight OPTIONS, phân biệt 403 do CORS với 403 do CSRF của POST.
10. Tạo hai browser contexts bằng Playwright để thử session isolation; không dùng dữ liệu/token thật.
11. Chạy MockMvc với `csrf()` và kiểm thử GET token → POST không qua helper, so sánh chứng cứ.
12. Chuyển sang WebFlux: dùng `CsrfWebFilter`, `Mono<CsrfToken>` và WebTestClient; so sánh lỗi do WebSession/cookie.
13. Đặt reverse proxy hoặc hai node thử nghiệm trước ứng dụng; kiểm tra cookie attributes, cache và session persistence.
14. Lập bảng kết quả gồm: request, chain, repository, token presentation, cookie/session continuity, handler, exception, HTTP status, nguyên nhân và cách sửa.

### Câu hỏi tự đánh giá

1. Khi server thấy token trong POST nhưng vẫn trả 403, cần tách những khả năng nào trước tiên?
2. Expected token, submitted token và request handler giữ vai trò khác nhau như thế nào?
3. Vì sao hidden token trong hai response HTML khác nhau chưa chắc là lỗi token rotation?
4. BREACH masking làm thay đổi cách frontend nên gửi token như thế nào?
5. Tại sao raw cookie token có thể bị handler mong đợi masked token từ chối?
6. `HttpSessionCsrfTokenRepository` khác `CookieCsrfTokenRepository` về expected token như thế nào?
7. Tại sao cookie có trong browser storage không chứng minh cookie đã được gửi tới đúng API route?
8. `SameSite`, `Secure`, `Domain` và `Path` có thể làm POST dùng session khác thế nào?
9. Sau login/logout, tại sao SPA có thể cần bootstrap lại CSRF token?
10. Nếu session ID đổi nhưng CSRF token vẫn hợp lệ, kết luận nào là sai?
11. CORS preflight trả 403 có chứng minh POST đã bị `CsrfFilter` từ chối không?
12. Nếu HTTP status không phải 403 mà là 400 hoặc 302, có thể có tầng nào từ chối trước CSRF?
13. `permitAll()` có bỏ qua CSRF không? Nếu không, cần test gì?
14. Khi GET token và POST vào hai security chains khác nhau, lỗi gì có thể xuất hiện?
15. Vì sao `with(csrf())` test PASS chưa chứng minh SPA có token đúng session?
16. Cách dùng hai browser contexts trong Playwright giúp chứng minh điều gì?
17. Với WebFlux, vì sao không được dùng `HttpSessionCsrfTokenRepository`?
18. Một `Mono<CsrfToken>` chưa được tiêu thụ có thể gây hiểu nhầm gì về lazy loading?
19. Khi production lỗi ngẫu nhiên giữa nhiều node, cần thu những log/bằng chứng nào mà không lộ secret?
20. Tại sao không cache chung response JSON/HTML có CSRF token?
21. Vì sao không nên tự động retry POST thanh toán chỉ vì nhận 403?
22. Khi nào nên sửa CORS, khi nào sửa CSRF handler, khi nào sửa session/cookie?

## 35. Ghi nhớ

**Một CSRF token có mặt trong request vẫn có thể không hợp lệ.** Hãy kiểm tra ba thành phần: **expected token** được repository nạp theo đúng session/cookie, **submitted token** mà browser gửi qua header/parameter, và **request handler** có hiểu đúng định dạng raw/masked hay không. Ở Spring Security Servlet 6.x, token expose cho form có thể được XOR-mask để giảm nguy cơ BREACH; chuỗi HTML thay đổi giữa các GET không đồng nghĩa expected token đã rotate. Với SPA đọc raw `XSRF-TOKEN` cookie, cần handler phù hợp để đọc raw header.

Session timeout, login/logout, cookie `Domain`/`Path`/`SameSite`/`Secure`, reverse proxy, cluster và cache có thể làm **token A được gửi cùng session B**. Trong Servlet, hãy kiểm tra `CsrfFilter`, `CsrfTokenRepository`, `CsrfTokenRequestHandler` và `SecurityFilterChain`; trong Reactive/WebFlux, sử dụng `CsrfWebFilter`, `ServerCsrfTokenRepository`, `ServerWebExchange` và `SecurityWebFilterChain`. Dùng MockMvc/WebTestClient để kiểm tra filter, sau đó kiểm chứng GET token → POST cùng phiên qua browser thật và public path. Không tắt CSRF, CORS, HTTP firewall hoặc bảo vệ session để che một lỗi mismatch trong `SPRING_SECURITY_HTTP_PROTECTION`.
