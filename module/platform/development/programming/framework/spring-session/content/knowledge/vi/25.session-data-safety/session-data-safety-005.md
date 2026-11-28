# CSRF, SameSite và giới hạn của việc chỉ dựa vào cookie

Spring Session cho phép ứng dụng dùng cookie để mang session ID giữa trình duyệt và máy chủ, trong khi dữ liệu phiên được lưu ở Redis, JDBC hoặc repository khác. Cookie giúp trình duyệt tự gửi session ID theo các request phù hợp. Chính đặc tính tự động gửi này tạo ra rủi ro Cross-Site Request Forgery (CSRF): một trang web khác có thể khiến trình duyệt của người dùng đã đăng nhập gửi request tới ứng dụng.

Thuộc tính `SameSite` giúp trình duyệt giới hạn việc gửi cookie trong một số ngữ cảnh cross-site. Đây là lớp phòng vệ hữu ích, nhưng không thay thế CSRF token và các biện pháp kiểm tra request. Cookie `HttpOnly`, `Secure` và `SameSite` giải quyết các rủi ro khác nhau; không thuộc tính nào tự chứng minh rằng người dùng có chủ ý thực hiện hành động thay đổi dữ liệu.

## Mục tiêu

Sau bài học, bạn có thể:

- Giải thích CSRF và vì sao cookie session tạo ra cơ chế xác thực tự động.
- Phân biệt same-origin với same-site và hiểu tác động của `SameSite`.
- Chọn `Strict`, `Lax` hoặc `None` theo luồng điều hướng thực tế.
- Cấu hình cookie session an toàn trong Spring Session.
- Bật và kiểm thử CSRF protection bằng Spring Security.
- Nhận biết giới hạn của CORS, `Origin`, `Referer`, `HttpOnly` và `Secure`.
- Thiết kế kiểm thử cho form, SPA, SSO, iframe và API dùng cookie.

## 1. Cookie session được trình duyệt gửi như thế nào?

Sau khi ứng dụng tạo session, server thường gửi một response header `Set-Cookie` chứa session ID:

~~~http
HTTP/1.1 200 OK
Set-Cookie: SESSION=abc123; Path=/; HttpOnly; Secure; SameSite=Lax
~~~

Ở request tiếp theo tới phạm vi cookie, trình duyệt tự đính kèm cookie:

~~~http
GET /account HTTP/1.1
Host: app.example.com
Cookie: SESSION=abc123
~~~

Server dùng session ID để tìm phiên trong Spring Session repository. Với Redis/JDBC, session ID là khóa tham chiếu tới dữ liệu được lưu phía server; bản thân cookie không chứa toàn bộ trạng thái phiên.

Đặc điểm quan trọng là trình duyệt tự gửi cookie mà không cần JavaScript đọc giá trị hoặc thêm một header xác thực riêng. Điều này thuận tiện cho ứng dụng web, nhưng cũng có nghĩa một trang web khác có thể kích hoạt trình duyệt gửi cookie tới domain đích trong những ngữ cảnh mà chính sách cookie cho phép.

Cookie session thường là credential dạng bearer: ai có session ID hợp lệ và gửi được nó có thể được xem như phiên đó, trừ khi ứng dụng có thêm kiểm soát. Vì vậy cần bảo vệ cookie khỏi đánh cắp, đồng thời bảo vệ endpoint khỏi request giả mạo.

## 2. CSRF là gì?

Cross-Site Request Forgery là kiểu tấn công trong đó kẻ tấn công khiến trình duyệt của người dùng đã đăng nhập gửi một request ngoài ý muốn tới ứng dụng đích. Trình duyệt có thể tự đính kèm cookie session hợp lệ, nên server nhìn thấy request đã được xác thực.

Ví dụ người dùng đăng nhập `bank.example.com`, sau đó mở một trang không đáng tin cậy. Trang đó có thể cố gửi form tới endpoint chuyển tiền:

~~~html
<form action="https://bank.example.com/transfer" method="POST">
  <input type="hidden" name="to" value="attacker-account">
  <input type="hidden" name="amount" value="1000">
</form>
<script>
  document.forms[0].submit();
</script>
~~~

Nếu trình duyệt gửi cookie phiên tới `bank.example.com` và server chỉ kiểm tra session hợp lệ, request có thể được xử lý như thao tác của người dùng. Kẻ tấn công không cần đọc được response; chỉ cần khiến hành động thay đổi trạng thái xảy ra.

CSRF khác với đánh cắp session:

- CSRF lợi dụng việc trình duyệt tự gửi credential hợp lệ để tạo request trái ý muốn.
- Session theft là lấy được session ID hoặc credential để sử dụng phiên như người dùng.
- XSS cho phép mã độc chạy trong origin của ứng dụng; nó có thể đọc nội dung trang và thực hiện request cùng origin, làm suy yếu nhiều biện pháp chống CSRF.

Một hệ thống cần phòng vệ cho cả ba nhóm rủi ro. CSRF token không thay thế việc bảo vệ session cookie khỏi XSS hoặc đánh cắp.

## 3. Same-origin và same-site không giống nhau

Trình duyệt dùng hai khái niệm khác nhau:

| Khái niệm | Thành phần so sánh | Ví dụ |
|---|---|---|
| Same-origin | Scheme, host và port | `https://app.example.com` và `https://api.example.com` là khác origin |
| Same-site | Scheme và registrable domain theo quy tắc public suffix | Hai subdomain HTTPS của `example.com` thường được xem là same-site |

Ví dụ:

- `https://app.example.com` gọi `https://api.example.com`: khác origin nhưng thường same-site.
- `https://app.example.com` gọi `https://evil.test`: khác origin và cross-site.
- `http://app.example.com` và `https://app.example.com`: khác scheme; với schemeful same-site, chúng không cùng site.

Điều này quan trọng vì `SameSite` kiểm soát cookie theo ngữ cảnh site, còn CORS kiểm soát việc JavaScript từ origin khác có được đọc response hay không. Một request cross-origin nhưng same-site có thể không bị `SameSite` chặn; ngược lại, CORS không tự ngăn mọi request gây thay đổi trạng thái.

Không dùng cụm “cùng domain” một cách mơ hồ. Hãy xác định rõ origin, site, subdomain, scheme và port khi thiết kế cookie, CORS và CSRF protection.

## 4. SameSite kiểm soát điều gì?

Thuộc tính `SameSite` hướng dẫn trình duyệt khi nào gửi cookie trong các request cross-site. Ba giá trị phổ biến:

| Giá trị | Hành vi khái quát | Tình huống |
|---|---|---|
| `Strict` | Chỉ gửi cookie trong ngữ cảnh same-site | Ứng dụng nhạy cảm, không cần giữ đăng nhập khi người dùng đi từ liên kết ngoài |
| `Lax` | Cho phép cookie trong same-site và một số điều hướng top-level cross-site an toàn, thường là GET | Lựa chọn cân bằng cho nhiều ứng dụng web |
| `None` | Cho phép cookie trong cả ngữ cảnh cross-site | Tích hợp cross-site như iframe hoặc một số luồng SSO; phải dùng `Secure` trên trình duyệt hiện đại |

`Lax` thường không gửi cookie trong các request cross-site như form POST, iframe hoặc fetch cross-site. Tuy nhiên, chi tiết phụ thuộc trình duyệt và phiên bản; một số trình duyệt có cơ chế tương thích đặc biệt cho cookie không khai báo SameSite. Không dựa vào hành vi mặc định không được cấu hình tường minh.

### 4.1. SameSite=Strict

Với `Strict`, cookie không được gửi trong các request cross-site, kể cả khi người dùng bấm một liên kết từ email hoặc trang bên ngoài để mở ứng dụng. Người dùng có thể phải tải lại hoặc đăng nhập lại theo cách ứng dụng thiết kế.

Chọn `Strict` khi:

- Ứng dụng nhạy cảm và chấp nhận trải nghiệm điều hướng chặt chẽ.
- Không cần cookie session trong luồng quay về từ nhà cung cấp bên ngoài.
- Đã kiểm thử các luồng deep link, đăng nhập liên kết và điều hướng từ email.

Không đặt `Strict` một cách máy móc nếu ứng dụng cần nhận callback hoặc điều hướng cross-site có session. Một số luồng đăng nhập liên kết có thể bị gián đoạn.

### 4.2. SameSite=Lax

`Lax` là lựa chọn thực tế cho nhiều ứng dụng web có điều hướng thông thường. Cookie thường được gửi khi người dùng điều hướng top-level tới site đích bằng phương thức an toàn như GET, nhưng không gửi trong nhiều request cross-site nền hoặc POST.

Điều này giảm một số dạng CSRF mà vẫn cho phép người dùng bấm liên kết từ website khác để tới ứng dụng. Tuy vậy, endpoint thay đổi trạng thái không được dùng GET. Nếu endpoint có side effect qua GET, `Lax` có thể không bảo vệ được luồng điều hướng top-level.

### 4.3. SameSite=None

`None` cho phép cookie được gửi trong ngữ cảnh cross-site, thường cần khi ứng dụng chạy trong iframe của site khác hoặc khi một kiến trúc nhiều site cần cookie trong request cross-site.

Trình duyệt hiện đại yêu cầu cookie `SameSite=None` phải có `Secure`, nghĩa là chỉ gửi qua HTTPS. Một số trình duyệt hoặc chế độ riêng tư còn có thể chặn cookie bên thứ ba hoàn toàn. Do đó, `SameSite=None; Secure` không bảo đảm cookie chắc chắn hoạt động trong mọi môi trường.

Nếu cần cross-site authentication, hãy kiểm tra hỗ trợ cookie bên thứ ba, chính sách privacy của trình duyệt và phương án thay thế như top-level redirect, authorization code flow hoặc token exchange phù hợp. Không mở `SameSite=None` rộng hơn nhu cầu.

## 5. SameSite là lớp phòng vệ, không phải toàn bộ CSRF protection

`SameSite` giúp giảm khả năng cookie session tự động được gửi trong một số request cross-site, nhưng vẫn có giới hạn:

- Các subdomain cùng site có thể được xem là same-site dù khác origin. Nếu một subdomain bị chiếm quyền hoặc có nội dung không đáng tin cậy, cookie có thể vẫn được gửi.
- Điều hướng top-level cross-site bằng GET có thể mang cookie `Lax`; vì thế GET phải an toàn và không thay đổi trạng thái.
- Một số luồng cần `SameSite=None`, làm tăng nhu cầu CSRF token và kiểm tra request.
- Trình duyệt, phiên bản và chế độ privacy có thể khác nhau.
- SameSite không chống XSS cùng origin và không ngăn kẻ tấn công đã đánh cắp session cookie.

Hãy coi `SameSite` là defense-in-depth. Ứng dụng dùng session cookie vẫn nên bật CSRF protection phù hợp với mô hình xác thực và framework.

## 6. CSRF token hoạt động ra sao?

CSRF token là giá trị khó đoán được server liên kết với session hoặc một ngữ cảnh người dùng. Trang hợp lệ lấy token và gửi token cùng request thay đổi trạng thái. Trang của kẻ tấn công không thể đọc token từ origin ứng dụng do same-origin policy, nên khó tạo request hợp lệ.

Với form HTML truyền thống:

~~~html
<form method="post" action="/profile/email">
  <input type="hidden" name="_csrf" value="TOKEN_FROM_SERVER">
  <input type="email" name="email">
  <button type="submit">Lưu</button>
</form>
~~~

Server so sánh token nhận được với token mong đợi. Nếu thiếu hoặc không hợp lệ, request bị từ chối, thường bằng HTTP 403.

CSRF token không cần thay thế session ID. Hai giá trị có vai trò khác nhau:

- Session cookie giúp server nhận diện phiên đã xác thực.
- CSRF token chứng minh request thay đổi trạng thái có thông tin mà trang hợp lệ được cấp.

Không ghi CSRF token vào URL, log, analytics hoặc thông báo lỗi. URL có thể xuất hiện trong browser history, referrer và log của proxy.

## 7. Bật CSRF protection trong Spring Security

Với ứng dụng Servlet dùng Spring Security và session cookie, CSRF protection thường được bật mặc định cho các phương thức thay đổi trạng thái. Không tắt chỉ vì ứng dụng có `SameSite=Lax` hoặc `HttpOnly`.

Ví dụ cấu hình mặc định với form login:

~~~java
@Configuration
@EnableWebSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/assets/**").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .build();
    }
}
~~~

Với cấu hình này, không gọi `csrf.disable()`. Spring Security sử dụng CSRF token repository mặc định phù hợp cho ứng dụng Servlet. Template engine tích hợp như Thymeleaf có thể tự đưa token vào form khi sử dụng integration tương ứng; với HTML thuần, cần render token theo cách ứng dụng kiểm soát.

Đối với SPA cần JavaScript đọc token từ cookie CSRF riêng, có thể cấu hình `CookieCsrfTokenRepository`:

~~~java
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    return http
            .csrf(csrf -> csrf
                    .csrfTokenRepository(
                            CookieCsrfTokenRepository.withHttpOnlyFalse()))
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .build();
}
~~~

Trong mô hình này:

- Cookie CSRF thường có tên `XSRF-TOKEN`.
- JavaScript đọc token CSRF và gửi lại trong header `X-XSRF-TOKEN` theo cấu hình mặc định tương ứng.
- Cookie session vẫn nên là `HttpOnly`; `withHttpOnlyFalse()` áp dụng cho cookie CSRF để SPA có thể đọc token.
- Token CSRF không phải session ID và không được dùng để xác thực người dùng.

Tên cookie, header, request handler và cách token được expose có thể thay đổi theo phiên bản Spring Security. Đặc biệt, các phiên bản mới có cơ chế deferred token và XOR encoding để giảm rủi ro BREACH. Hãy dùng tài liệu của đúng phiên bản và kiểm thử request thực tế thay vì sao chép cấu hình SPA từ một phiên bản khác.

## 8. Cấu hình cookie session trong Spring Session

Spring Boot cho phép cấu hình cookie session thông qua `server.servlet.session.cookie` trong các phiên bản hỗ trợ:

~~~yaml
server:
  servlet:
    session:
      cookie:
        name: SESSION
        http-only: true
        secure: true
        same-site: lax
        path: /
~~~

Ý nghĩa:

| Thuộc tính | Mục đích | Giới hạn |
|---|---|---|
| `HttpOnly` | Ngăn JavaScript đọc cookie qua `document.cookie` | Không ngăn trình duyệt gửi cookie và không tự chống CSRF |
| `Secure` | Chỉ gửi cookie qua HTTPS | Không mã hóa dữ liệu ở server hoặc bảo vệ endpoint khỏi CSRF |
| `SameSite` | Giới hạn cookie trong một số ngữ cảnh cross-site | Không thay thế CSRF token; same-site có thể gồm nhiều origin |
| `Path` | Giới hạn URL path được gửi cookie | Không phải ranh giới bảo mật mạnh giữa ứng dụng cùng host |
| `Domain` | Xác định host/domain nhận cookie | Domain rộng có thể khiến nhiều subdomain cùng nhận cookie |
| `Max-Age`/`Expires` | Điều khiển thời gian cookie tồn tại ở trình duyệt | Không quyết định duy nhất thời gian session còn hiệu lực ở server |

Với Spring Session Servlet, cookie resolver mặc định thường dùng tên cookie `SESSION` và có thể được tùy chỉnh bằng `CookieSerializer` hoặc cấu hình Boot tương ứng. Nếu ứng dụng tự cấu hình `DefaultCookieSerializer`, hãy đặt thuộc tính nhất quán:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.web.http.CookieSerializer;
import org.springframework.session.web.http.DefaultCookieSerializer;

@Configuration
public class SessionCookieConfiguration {

    @Bean
    CookieSerializer cookieSerializer() {
        DefaultCookieSerializer serializer =
                new DefaultCookieSerializer();
        serializer.setCookieName("SESSION");
        serializer.setUseHttpOnlyCookie(true);
        serializer.setUseSecureCookie(true);
        serializer.setSameSite("Lax");
        serializer.setCookiePath("/");
        return serializer;
    }
}
~~~

Chọn một cách cấu hình phù hợp với phiên bản và cơ chế auto-configuration của dự án. Tránh khai báo nhiều `CookieSerializer` cạnh tranh. Nếu ứng dụng đứng sau reverse proxy TLS termination, phải cấu hình forwarded headers và xác định chính xác scheme bên ngoài để cookie `Secure` được phát đúng. Không tắt `Secure` trong production chỉ vì kết nối nội bộ từ proxy tới ứng dụng dùng HTTP.

## 9. Vì sao HttpOnly không chống CSRF?

`HttpOnly` ngăn script đọc giá trị cookie qua API JavaScript. Nó giúp giảm khả năng đánh cắp session cookie trực tiếp trong một số kịch bản XSS.

Nhưng trình duyệt vẫn gửi cookie `HttpOnly` theo chính sách cookie. Một trang độc hại không cần đọc session ID; nó chỉ cần khiến trình duyệt gửi request tới ứng dụng. Server vẫn nhận cookie và có thể xác thực session.

Vì vậy:

- `HttpOnly` hữu ích chống đọc cookie qua JavaScript.
- `SameSite` hạn chế việc gửi cookie trong một số ngữ cảnh cross-site.
- CSRF token kiểm tra request thay đổi trạng thái có token hợp lệ.
- Content Security Policy, output encoding và input validation giúp giảm nguy cơ XSS.

Không dùng một thuộc tính cookie để thay thế các lớp bảo vệ khác.

## 10. Vì sao Secure không chống CSRF?

`Secure` chỉ yêu cầu trình duyệt gửi cookie qua kết nối HTTPS. Nó bảo vệ cookie khỏi bị gửi qua HTTP không mã hóa, nhưng không chứng minh request đến từ trang hợp lệ.

Một trang độc hại trên HTTPS vẫn có thể gửi form tới ứng dụng HTTPS. Nếu cookie được phép gửi và server không kiểm tra CSRF token hoặc nguồn request, thao tác trái ý muốn vẫn có thể xảy ra.

Hãy bật HTTPS toàn bộ, dùng cookie `Secure`, bật HSTS phù hợp, nhưng vẫn giữ CSRF protection cho các endpoint dùng cookie xác thực.

## 11. CORS không phải là CSRF protection

CORS chủ yếu điều khiển việc JavaScript từ origin khác có được đọc response hay thực hiện một số request preflighted hay không. CORS không ngăn mọi request cross-site được gửi.

Ví dụ form HTML có thể gửi một số request đơn giản mà không cần preflight CORS. Trình duyệt có thể gửi request đó dù JavaScript của site ngoài không được đọc response. Nếu cookie session được gửi, server vẫn phải kiểm tra CSRF.

Không dựa vào:

- `Access-Control-Allow-Origin` như cơ chế chống CSRF duy nhất.
- Việc không bật CORS như bảo đảm không có cross-site request.
- `Content-Type: application/json` như bảo vệ hoàn chỉnh; cần xem mọi endpoint, content type được chấp nhận và cách browser gửi request.
- CORS wildcard hoặc allow-origin reflection mà không kiểm tra credentials và origin.

Nếu API cần CORS với cookie credentials, cấu hình allowlist origin cụ thể, bật credentials có kiểm soát, không dùng wildcard `*` cho credentialed response, và vẫn giữ CSRF token cho request thay đổi trạng thái dùng cookie.

## 12. Kiểm tra Origin, Referer và Fetch Metadata

Server có thể kiểm tra `Origin` hoặc `Referer` đối với request thay đổi trạng thái. Nếu header hiện diện và không thuộc allowlist origin hợp lệ, server từ chối request. Đây là lớp phòng vệ bổ sung, đặc biệt với endpoint nhạy cảm.

Tuy nhiên, không nên coi header này là cơ chế duy nhất:

- Một số client hoặc môi trường privacy có thể bỏ `Referer`.
- Request nội bộ, proxy hoặc native client có thể có semantics khác.
- Cần xác định chính xác public origin sau reverse proxy.
- Allowlist phải so sánh scheme, host và port, không chỉ chuỗi con của domain.

Fetch Metadata như `Sec-Fetch-Site`, `Sec-Fetch-Mode` và `Sec-Fetch-Dest` có thể giúp server nhận diện ngữ cảnh request. Ví dụ, server có thể từ chối một số request `cross-site` tới endpoint nhạy cảm. Đây là defense-in-depth; không thay thế CSRF token khi ứng dụng dựa vào cookie session.

## 13. GET phải an toàn, không thay đổi trạng thái

CSRF protection thường tập trung vào các phương thức thay đổi trạng thái như POST, PUT, PATCH và DELETE. Vì vậy, endpoint GET phải chỉ đọc dữ liệu:

~~~http
GET /account
GET /orders/123
~~~

Không thiết kế endpoint thay đổi dữ liệu qua GET:

~~~http
GET /account/delete
GET /transfer?to=attacker&amount=1000
~~~

Một liên kết, ảnh nhúng hoặc điều hướng top-level có thể kích hoạt GET. Với `SameSite=Lax`, một số điều hướng top-level cross-site vẫn gửi cookie. Nếu GET có side effect, lớp bảo vệ SameSite có thể không ngăn được hành động.

Thao tác thay đổi trạng thái phải dùng phương thức phù hợp và yêu cầu CSRF token hoặc cơ chế xác minh tương đương. Không dùng HEAD, OPTIONS hoặc GET để thực hiện thay đổi nghiệp vụ.

## 14. Các luồng cross-site cần thiết kế riêng

Một số kiến trúc cần cookie hoạt động trong ngữ cảnh cross-site:

| Luồng | Vấn đề | Hướng xử lý |
|---|---|---|
| Ứng dụng trong iframe bên thứ ba | Cookie `Lax`/`Strict` có thể không được gửi | Nếu cần, cân nhắc `SameSite=None; Secure`, kiểm tra chặn third-party cookie và bổ sung CSRF protection |
| SSO qua top-level redirect | Cookie `Strict` có thể không có trong bước quay về | Kiểm thử callback, dùng state/nonce và luồng giao thức đúng |
| Frontend và API khác origin nhưng cùng site | CORS áp dụng dù cookie có thể same-site | Cấu hình credentialed CORS theo allowlist và CSRF token |
| Frontend và API khác site | Cookie cần `SameSite=None; Secure` nếu xác thực bằng cookie | Kiểm tra third-party cookie policy; cân nhắc BFF hoặc token flow |
| Subdomain không cùng mức tin cậy | Có thể cùng site và cookie domain rộng | Thu hẹp domain, tách origin và không tin cậy mọi subdomain |

Với OAuth 2.0/OIDC, callback cần kiểm tra `state`, và OIDC cần kiểm tra `nonce` khi sử dụng. Không coi cookie session hoặc SameSite là thay thế cho kiểm tra state của giao thức.

## 15. Session fixation và xoay session ID

CSRF token và SameSite không xử lý session fixation. Khi người dùng đăng nhập hoặc thay đổi mức đặc quyền, session ID cần được bảo vệ khỏi việc kẻ tấn công cố định trước đó.

Spring Security có cơ chế session fixation protection, thường thay đổi session ID sau khi xác thực thành công. Hãy không tắt cơ chế này nếu không có lý do rõ ràng. Kiểm thử rằng:

- Session ID trước và sau đăng nhập được xử lý theo chính sách bảo vệ của ứng dụng.
- Dữ liệu cần giữ qua đăng nhập được chuyển đúng cách.
- Logout invalidate phiên và xóa cookie phù hợp.
- Cookie mới có lại `HttpOnly`, `Secure`, `SameSite`, `Path` và `Domain` đúng.

Khi đổi session ID, CSRF token có thể cần được tạo lại hoặc tải lại theo cơ chế Spring Security. SPA cần biết cách lấy token mới sau login/logout.

## 16. Kiểm thử CSRF và cookie trong trình duyệt

Unit test của controller không đủ để xác minh chính sách cookie của trình duyệt. Cần kiểm thử integration và browser test cho các ngữ cảnh thực tế.

Ma trận kiểm thử:

| Tình huống | Kết quả mong đợi |
|---|---|
| POST hợp lệ có session cookie và CSRF token | Request được xử lý nếu người dùng có quyền |
| POST có session cookie nhưng thiếu token | Bị từ chối, thường là 403 |
| POST có token sai hoặc token thuộc session khác | Bị từ chối |
| GET từ site khác tới endpoint chỉ đọc | Có thể được gửi theo `Lax`; không thay đổi dữ liệu |
| GET tới endpoint có side effect | Endpoint cần được thiết kế lại; không dựa vào SameSite |
| Cross-site POST với cookie `Lax` | Trình duyệt hiện đại thường không gửi cookie trong ngữ cảnh này; vẫn kiểm tra token phía server |
| Cookie `SameSite=None` trong iframe | Phụ thuộc third-party cookie policy; kiểm thử trình duyệt mục tiêu |
| Cookie session | Có `HttpOnly`, `Secure` và SameSite theo chính sách |
| Cookie CSRF của SPA | JavaScript đọc được nếu cấu hình chủ đích; session cookie vẫn HttpOnly |
| Logout | Session bị invalidate, cookie hết hạn và token cũ không còn dùng được |

Với Spring Security MockMvc, có thể dùng request postprocessor `csrf()` để tạo request có token hợp lệ:

~~~java
mockMvc.perform(post("/profile/email")
        .with(csrf())
        .param("email", "new@example.com"))
    .andExpect(status().is3xxRedirection());
~~~

Kiểm tra request thiếu token:

~~~java
mockMvc.perform(post("/profile/email")
        .param("email", "new@example.com"))
    .andExpect(status().isForbidden());
~~~

Các ví dụ cần import static tương ứng từ Spring Security Test, ví dụ `SecurityMockMvcRequestPostProcessors.csrf` và `MockMvcRequestBuilders.post`. Để xác minh `SameSite`, `Secure`, cookie domain và hành vi third-party, cần kiểm tra header `Set-Cookie` và chạy browser automation trên các trình duyệt mục tiêu.

## 17. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Request POST từ site khác vẫn được xác thực | Cookie được gửi trong ngữ cảnh đó và server không kiểm tra token | Bật CSRF protection và kiểm tra token |
| Đăng nhập qua SSO bị mất session | `SameSite=Strict` hoặc chính sách cookie không phù hợp callback | Kiểm thử luồng redirect; chọn chính sách cookie phù hợp và xác minh state/nonce |
| SPA không gửi được CSRF token | Cookie token không được expose hoặc header sai tên | Kiểm tra `CookieCsrfTokenRepository`, CORS và header request |
| Nghĩ `HttpOnly` đã ngăn CSRF | Nhầm khả năng đọc cookie với khả năng trình duyệt tự gửi cookie | Giữ CSRF token và SameSite |
| CORS đã cấu hình nhưng request giả mạo vẫn chạy | CORS không ngăn mọi form/simple request | Bật CSRF protection cho cookie authentication |
| Cookie không được gửi trong iframe | `SameSite=Lax/Strict` hoặc trình duyệt chặn third-party cookie | Xem xét `None; Secure`, kiểm thử privacy policy và phương án kiến trúc |
| Cookie không có `Secure` sau reverse proxy | Ứng dụng nhận diện request nội bộ là HTTP hoặc forwarded headers sai | Cấu hình proxy headers và cookie serializer |
| GET làm thay đổi dữ liệu | Thiết kế endpoint sai semantics HTTP | Chuyển side effect sang POST/PUT/PATCH/DELETE và yêu cầu CSRF token |
| CSRF token cũ không hợp lệ sau login | Session ID/token được thay đổi sau xác thực | Lấy token mới theo flow của Spring Security |

## 18. Checklist bảo vệ session cookie

- [ ] Dùng HTTPS cho toàn bộ luồng đăng nhập và phiên.
- [ ] Cookie session có `Secure` và `HttpOnly`.
- [ ] Chọn `SameSite` theo luồng thực tế, ưu tiên chính sách chặt nhất vẫn đáp ứng sản phẩm.
- [ ] Thu hẹp cookie `Domain` và `Path` khi có thể.
- [ ] Không dùng GET cho hành động thay đổi trạng thái.
- [ ] Giữ CSRF protection của Spring Security cho xác thực dựa trên cookie.
- [ ] Kiểm tra CSRF token trên POST, PUT, PATCH và DELETE.
- [ ] Cấu hình CORS allowlist nếu frontend khác origin; không xem CORS là CSRF defense.
- [ ] Kiểm tra `Origin`/`Referer` hoặc Fetch Metadata như lớp bổ sung khi phù hợp.
- [ ] Bảo vệ chống XSS vì XSS có thể vượt qua nhiều ranh giới CSRF.
- [ ] Kiểm thử login, session ID rotation, logout và cấp lại CSRF token.
- [ ] Kiểm thử SameSite trên browser thật, đặc biệt iframe, SSO và third-party cookie.
- [ ] Không ghi session ID hoặc CSRF token vào log, URL hay analytics.

Cookie là cách trình duyệt mang session ID tới server, nhưng việc cookie được gửi tự động không chứng minh request là ý định hợp lệ của người dùng. `SameSite` giảm một số request cross-site, `HttpOnly` hạn chế JavaScript đọc cookie và `Secure` yêu cầu HTTPS; mỗi thuộc tính giải quyết một vấn đề riêng. Với Spring Session dùng cookie xác thực, hãy kết hợp cấu hình cookie phù hợp, CSRF token của Spring Security, endpoint GET chỉ đọc, CORS/Origin được cấu hình đúng và kiểm thử trên trình duyệt mục tiêu.
