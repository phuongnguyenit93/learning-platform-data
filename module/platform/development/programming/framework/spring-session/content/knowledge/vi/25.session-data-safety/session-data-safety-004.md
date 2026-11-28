# HTTPS, cookie bảo vệ và tránh để lộ qua URL hoặc nhật ký

Session ID là một bearer credential: bất kỳ ai sở hữu một ID còn hợp lệ đều có thể thử dùng nó để tiếp tục phiên của người dùng. Vì vậy, Spring Session cần được triển khai cùng TLS, cookie có thuộc tính bảo vệ phù hợp và quy tắc xử lý log nghiêm ngặt. Chỉ lưu session trong Redis hoặc JDBC không làm ID an toàn nếu ID bị lộ qua URL, header log, proxy, trace hoặc trình duyệt.

Bài này tập trung vào đường đi của session ID từ server tới browser và quay lại: HTTPS bảo vệ dữ liệu trên đường truyền; cookie Secure, HttpOnly và SameSite giới hạn cách browser gửi và truy cập cookie; cấu hình proxy giúp ứng dụng nhận biết đúng HTTPS sau khi TLS kết thúc ở ingress; còn việc loại bỏ URL rewriting và che dữ liệu log ngăn ID rò rỉ qua các kênh phụ. Các biện pháp này phải phối hợp với session fixation protection, CSRF, XSS defense và bảo vệ kho session.

## 1. Session ID là thông tin xác thực nhạy cảm

Sau khi người dùng đăng nhập, server thường tạo hoặc đổi session ID rồi gửi ID cho browser trong Set-Cookie. Ở các request tiếp theo, browser gửi cookie đó trong header Cookie. Spring Session dùng ID để tìm dữ liệu session trong repository như Redis hoặc JDBC.

Luồng cơ bản:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant P as Reverse Proxy
    participant A as Spring Application
    participant R as Spring Session Repository
    B->>P: HTTPS request
    P->>A: Forward request tới ứng dụng
    A->>R: Tìm hoặc lưu session
    R-->>A: Session data
    A-->>P: Response + Set-Cookie
    P-->>B: HTTPS response
    B->>P: Request sau + Cookie: SESSION
~~~

Session ID có các đặc điểm:

- Nó thường không mang ý nghĩa nghiệp vụ để người dùng đọc, nhưng có giá trị xác thực.
- Người sở hữu ID có thể mạo danh phiên tương ứng nếu server chấp nhận ID đó.
- ID có thể bị sao chép từ cookie, log, URL, trace hoặc công cụ giám sát.
- Đổi tên cookie không làm ID bớt nhạy cảm.
- Mã hóa dữ liệu session ở Redis/JDBC không tự bảo vệ cookie đang truyền qua mạng.

Không ghi session ID thật vào log để debug. Không gửi ID trong JSON, URL hoặc thông báo lỗi. Hãy dùng request correlation ID riêng để liên kết log của một request mà không tiết lộ credential.

## 2. HTTPS bảo vệ cookie trên đường truyền

TLS mã hóa request và response giữa browser với endpoint HTTPS. Khi session cookie có thuộc tính Secure, browser chỉ gửi cookie qua kết nối an toàn theo quy tắc của trình duyệt.

Trong production:

- Chuyển toàn bộ lưu lượng người dùng sang HTTPS.
- Không cung cấp endpoint đăng nhập hoặc session qua HTTP không mã hóa.
- Chuyển hướng HTTP sang HTTPS ở edge proxy hoặc ứng dụng theo một chính sách rõ ràng.
- Bật Secure cho session cookie.
- Dùng TLS cả trên các chặng nội bộ nếu mạng giữa proxy, ứng dụng và kho dữ liệu không hoàn toàn tin cậy.
- Kiểm tra chứng thư, hostname, thời hạn và quy trình gia hạn.
- Không hạ cấp về HTTP khi TLS handshake lỗi.

Nếu TLS kết thúc tại load balancer hoặc ingress, browser vẫn kết nối HTTPS tới proxy nhưng proxy có thể chuyển request nội bộ bằng HTTP. Điều đó có thể chấp nhận trong một mạng nội bộ được cô lập, nhưng phải đánh giá threat model. Với môi trường có nhiều tenant, mạng dùng chung hoặc yêu cầu tuân thủ cao, nên dùng TLS/mTLS giữa proxy và ứng dụng cũng như TLS tới Redis/database.

HTTPS không ngăn XSS đọc dữ liệu mà JavaScript có quyền truy cập, không ngăn server ghi cookie sai và không bảo vệ log chứa cookie. Đây là lớp bảo vệ đường truyền, không thay thế các biện pháp còn lại.

## 3. Cấu hình session cookie bằng Spring Session

Spring Session Servlet thường dùng CookieHttpSessionIdResolver để đọc session ID từ request cookie và ghi ID vào response cookie. CookieSerializer quyết định tên cookie và các thuộc tính được phát hành. Có thể cung cấp một bean CookieSerializer để cấu hình rõ ràng.

Ví dụ production dùng cookie host-only:

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

        serializer.setCookieName("__Host-SESSION");
        serializer.setCookiePath("/");
        serializer.setUseSecureCookie(true);
        serializer.setUseHttpOnlyCookie(true);
        serializer.setSameSite("Lax");

        // Không đặt Domain: cookie giữ phạm vi host hiện tại.
        return serializer;
    }
}
~~~

Ví dụ này dành cho ứng dụng production chỉ phục vụ qua HTTPS. Cookie có tiền tố __Host- phải thỏa các điều kiện của browser: có Secure, Path=/ và không có thuộc tính Domain. Nếu cần chia sẻ cookie giữa nhiều subdomain, không dùng tiền tố này; hãy cân nhắc lại phạm vi cookie và rủi ro tin cậy giữa các subdomain.

Tên cookie mặc định và API cấu hình có thể khác theo phiên bản hoặc cấu hình dự án. Hãy xác nhận CookieSerializer thực sự được CookieHttpSessionIdResolver dùng trong ứng dụng. Nếu ứng dụng tự khai báo resolver, bảo đảm resolver đó nhận đúng serializer.

### Các thuộc tính quan trọng

| Thuộc tính | Mục đích | Khuyến nghị thông thường |
|---|---|---|
| Secure | Chỉ gửi cookie qua kết nối an toàn | Bật trong production HTTPS |
| HttpOnly | Ngăn JavaScript đọc cookie qua document.cookie | Bật cho session cookie |
| SameSite | Hạn chế cookie được gửi trong ngữ cảnh cross-site | Lax thường là điểm bắt đầu; đánh giá Strict/None theo luồng |
| Path | Giới hạn đường dẫn request gửi cookie | Dùng / nếu session phục vụ toàn ứng dụng |
| Domain | Xác định host/subdomain nhận cookie | Bỏ qua để dùng host-only nếu không cần chia sẻ |
| Max-Age/Expires | Thời hạn cookie ở browser | Chỉ đặt persistent cookie nếu có yêu cầu rõ ràng |

Secure, HttpOnly và SameSite không thay thế lẫn nhau. Mỗi thuộc tính giải quyết một vấn đề khác nhau.

## 4. Secure và cấu hình sau reverse proxy

Khi TLS kết thúc tại proxy, ứng dụng có thể nhận request nội bộ bằng HTTP và request.isSecure() có thể trả false nếu proxy headers chưa được xử lý. Nếu CookieSerializer tự suy ra Secure từ request, cookie có thể bị phát thiếu Secure.

Với session cookie production, cách rõ ràng là cấu hình Secure=true như ví dụ CookieSerializer ở trên. Đồng thời, cấu hình ứng dụng nhận forwarded headers đúng để tạo redirect, URL tuyệt đối và thông tin request chính xác.

Ví dụ Spring Boot:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Giá trị cụ thể phụ thuộc Spring Boot và container. framework sử dụng cơ chế xử lý forwarded header của Spring; native giao việc cho container; none không diễn giải các header đó. Chọn một cơ chế phù hợp và tránh đăng ký nhiều bộ lọc xử lý cùng forwarded header.

### Chỉ tin forwarded header từ proxy được tin cậy

Các header như Forwarded hoặc X-Forwarded-Proto có thể bị client giả mạo nếu proxy không xóa giá trị đầu vào rồi ghi lại giá trị do chính nó xác định. Vì vậy:

- Chỉ cho phép ứng dụng nhận traffic từ proxy/load balancer đã biết.
- Cấu hình proxy xóa forwarded headers do client gửi và đặt giá trị chính xác.
- Không công khai cổng nội bộ của ứng dụng nếu không cần.
- Không tin X-Forwarded-Proto từ mọi địa chỉ nguồn.
- Kiểm tra scheme, host và port được ứng dụng nhìn thấy trong integration test.
- Không dùng forwarded header như một bằng chứng duy nhất về danh tính client.

Nếu dùng TLS end-to-end tới ứng dụng, request trực tiếp đã secure và ít phụ thuộc vào việc suy ra scheme. Nếu TLS terminate ở ingress, phải kiểm soát ranh giới tin cậy của ingress.

## 5. HSTS và chuyển hướng HTTPS

HTTP Strict Transport Security (HSTS) yêu cầu browser dùng HTTPS cho các lần truy cập tiếp theo trong thời gian được chỉ định. Header có dạng:

~~~http
Strict-Transport-Security: max-age=31536000
~~~

Có thể thêm includeSubDomains nếu mọi subdomain đều sẵn sàng HTTPS:

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

Spring Security có hỗ trợ HSTS trong cấu hình security headers. Ví dụ:

~~~java
http.headers(headers -> headers
    .httpStrictTransportSecurity(hsts -> hsts
        .maxAgeInSeconds(31536000)
        .includeSubDomains(true)
    )
);
~~~

Chỉ bật includeSubDomains khi toàn bộ subdomain liên quan đã được chuyển sang HTTPS và duy trì được chứng thư hợp lệ. HSTS preload có thêm điều kiện và ảnh hưởng lâu dài; không bật chỉ vì muốn có một header mạnh hơn.

HSTS chỉ có ý nghĩa khi response được gửi qua HTTPS. Không dựa vào HSTS để bảo vệ lần truy cập HTTP đầu tiên trước khi browser nhận được policy, trừ khi domain đã nằm trong preload list. Vẫn cần chuyển hướng HTTP sang HTTPS và không truyền session cookie qua HTTP.

## 6. SameSite: Lax, Strict và None

SameSite điều khiển việc browser gửi cookie trong request cross-site. Nó là một lớp giảm rủi ro CSRF nhưng cần chọn theo luồng đăng nhập, thanh toán và SSO thực tế.

| Giá trị | Hành vi khái quát | Tình huống thường cân nhắc |
|---|---|---|
| Strict | Hạn chế cookie trong điều hướng/request cross-site | Ứng dụng nội bộ, không cần luồng quay về từ site khác |
| Lax | Cho phép một số điều hướng top-level an toàn; hạn chế nhiều request cross-site | Điểm bắt đầu phổ biến cho ứng dụng web |
| None | Cho phép cookie trong ngữ cảnh cross-site theo chính sách browser | SSO/iframe/cross-site flow thực sự cần cookie |

Nếu dùng SameSite=None, browser yêu cầu Secure. Không phát SameSite=None trên cookie không Secure rồi kỳ vọng browser gửi cookie.

Strict có thể làm mất session cookie khi người dùng quay lại từ nhà cung cấp danh tính hoặc website bên ngoài. Lax thường tương thích hơn với luồng điều hướng top-level, nhưng vẫn cần test callback thực tế. None có thể cần cho iframe hoặc một số luồng SSO, song làm tăng bề mặt CSRF và phụ thuộc chính sách third-party cookie của browser.

Cấu hình trong ví dụ:

~~~java
serializer.setSameSite("Lax");
~~~

SameSite không phải là CSRF protection đầy đủ. Hãy giữ CSRF token và kiểm tra Origin/Referer phù hợp với mô hình ứng dụng. Không tắt CSRF chỉ vì session cookie dùng SameSite=Lax.

## 7. HttpOnly giảm khả năng đọc cookie từ JavaScript

HttpOnly khiến JavaScript trong browser không thể đọc cookie qua document.cookie. Đây là thuộc tính quan trọng cho session ID:

~~~http
Set-Cookie: __Host-SESSION=<redacted>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Tuy nhiên, HttpOnly không ngăn một đoạn JavaScript độc hại gửi request từ browser. Nếu trang bị XSS, script vẫn có thể thực hiện hành động bằng session cookie vì browser tự gắn cookie vào request phù hợp.

Do đó, HttpOnly cần kết hợp với:

- Output encoding và tránh đưa dữ liệu không tin cậy vào HTML/JavaScript.
- Content Security Policy phù hợp.
- Tránh inline script không cần thiết.
- Kiểm soát dependency JavaScript và third-party script.
- CSRF protection cho thao tác thay đổi trạng thái.
- Phân quyền server-side cho từng endpoint.

Không tắt HttpOnly để JavaScript đọc session ID rồi tự gắn vào header. Nếu frontend cần gọi API, browser tự gửi cookie theo cookie policy; JavaScript không cần biết giá trị session ID.

## 8. Domain và Path: thu hẹp phạm vi cookie

Nếu không đặt Domain, cookie thường là host-only và chỉ được gửi tới host đã phát nó. Đây thường là lựa chọn an toàn hơn so với đặt Domain rộng cho toàn bộ domain gốc.

Ví dụ, một cookie host-only cho app.example.com không tự động được gửi tới admin.example.com. Nếu đặt Domain .example.com, nhiều subdomain có thể nhận cookie. Một subdomain yếu hoặc bị chiếm quyền có thể làm tăng rủi ro cookie bị đánh cắp hoặc bị ghi đè.

Chỉ đặt Domain khi ứng dụng thật sự cần chia sẻ session giữa subdomain và các subdomain đó có cùng mức tin cậy. Không dùng wildcard domain tùy tiện.

Path giới hạn request path mà browser gửi cookie. Tuy nhiên, Path không phải ranh giới bảo mật đáng tin cậy giữa các ứng dụng cùng host. Các ứng dụng trên cùng host có thể có những tương tác phức tạp; không dựa vào Path để cô lập hoàn toàn hai ứng dụng có mức tin cậy khác nhau.

Với cookie prefix __Host-, bắt buộc Path=/ và không có Domain. Prefix này giúp browser từ chối một số cấu hình cookie yếu, nhưng không thay thế kiểm soát quyền truy cập subdomain và TLS.

## 9. Tránh session ID trong URL và URL rewriting

Không đưa session ID vào query string hoặc path. Ví dụ không an toàn:

~~~text
https://app.example.com/account?sessionId=abc123
https://app.example.com/account;jsessionid=abc123
~~~

Session ID trong URL có thể bị lộ qua:

- Browser history và bookmark.
- Copy/paste URL vào chat hoặc email.
- HTTP Referer khi điều hướng sang site khác.
- Access log của reverse proxy, CDN, WAF và web server.
- Analytics, monitoring và error tracking.
- Cache key, screenshot hoặc công cụ hỗ trợ người dùng.
- Link được gửi qua email hoặc lưu trong hệ thống ticket.

Servlet container có thể hỗ trợ URL rewriting để gắn ;jsessionid=... khi cookie không được dùng. Đối với ứng dụng sử dụng session cookie, hãy giới hạn session tracking mode ở COOKIE.

Ví dụ Spring Boot:

~~~yaml
server:
  servlet:
    session:
      tracking-modes: cookie
~~~

Với ứng dụng Servlet tự cấu hình, có thể đặt tracking mode qua ServletContext trước khi servlet được khởi tạo:

~~~java
servletContext.setSessionTrackingModes(
    EnumSet.of(SessionTrackingMode.COOKIE)
);
~~~

Tên property và điểm cấu hình phụ thuộc phiên bản Spring Boot/container. Cần kiểm tra cấu hình runtime và test response để bảo đảm URL không chứa ;jsessionid.

Spring Session thường dùng CookieHttpSessionIdResolver cho Servlet session. Nếu ứng dụng dùng resolver tùy chỉnh hoặc header resolver, vẫn phải bảo đảm session ID không bị nối vào URL bởi code hoặc thư viện khác.

Không dùng response.encodeURL() để tạo link chứa session ID. Nếu framework/template gọi encodeURL, tracking mode COOKIE giúp ngăn container dùng URL rewriting, nhưng vẫn cần kiểm tra URL cuối cùng được render.

## 10. Không truyền session ID qua query, fragment hoặc redirect

Query parameter thường được log và lưu trong history. Fragment không gửi tới server theo HTTP request thông thường, nhưng vẫn có thể bị JavaScript, analytics hoặc công cụ browser đọc. Không dùng fragment như một nơi lưu session credential.

Redirect cần giữ nguyên nguyên tắc:

- Không nối session ID vào Location header.
- Không đưa ID vào returnUrl hoặc continue parameter.
- Không copy toàn bộ query string từ request lỗi sang URL đăng nhập.
- Không đưa ID vào deep link hoặc URL callback.
- Không tạo link có ID để “giữ session” khi browser không nhận cookie.

Nếu cookie không hoạt động, hãy sửa cookie policy, domain, TLS hoặc browser compatibility. Không fallback sang URL session ID.

## 11. Header resolver cho client không dùng browser cookie

Spring Session có thể dùng HeaderHttpSessionIdResolver cho một số client API. Khi đó session ID được gửi trong HTTP header thay vì cookie. Đây vẫn là bearer credential.

Nếu dùng header resolver:

- Chỉ truyền qua HTTPS.
- Không đặt ID trong URL.
- Cấu hình reverse proxy, gateway và APM không log header chứa ID.
- Không đưa header vào trace baggage hoặc error report.
- Xác thực quyền và kiểm soát CORS phù hợp.
- Không chia sẻ header session ID với JavaScript hoặc third-party script không cần thiết.
- Đảm bảo client lưu và xóa ID an toàn khi logout.

Header không tự động an toàn hơn cookie. Cookie có các thuộc tính Secure, HttpOnly và SameSite; header tùy chỉnh cần chính sách tương đương ở client và hạ tầng.

Với REST API, cân nhắc bearer access token theo thiết kế OAuth2 thay vì dùng session ID như một token tùy chỉnh. Dù chọn cơ chế nào, không log credential.

## 12. Session fixation và đổi ID sau xác thực

Nếu attacker biết trước session ID của một browser rồi nạn nhân đăng nhập trong cùng session, session fixation có thể cho phép attacker dùng lại ID đó. Spring Security có session fixation protection để thay đổi session ID sau khi xác thực thành công.

Ví dụ cấu hình rõ ràng:

~~~java
http.sessionManagement(session -> session
    .sessionFixation(fixation -> fixation.changeSessionId())
);
~~~

Chính sách mặc định và cơ chế cụ thể có thể thay đổi theo Servlet version và cấu hình Spring Security. Hãy kiểm tra hành vi của phiên bản đang dùng. Với Spring Session, thao tác đổi ID phải được phản ánh trong repository và cookie mới phải được phát cho browser.

Kiểm thử:

1. Tạo session trước đăng nhập.
2. Ghi nhận ID trong test harness, không log ra output.
3. Đăng nhập thành công.
4. Xác nhận ID được thay đổi.
5. Xác nhận ID cũ không còn được chấp nhận theo chính sách.
6. Xác nhận response phát cookie mới với cùng thuộc tính bảo vệ.
7. Kiểm tra request tiếp theo sử dụng ID mới.

Không tự tạo session ID bằng UUID trong controller. Để Spring Security và Spring Session quản lý việc đổi ID.

## 13. Logout phải xóa session phía server và cookie phía browser

Logout cần làm hai việc riêng:

- Invalidate session ở repository để ID cũ không còn trỏ tới session hợp lệ.
- Gửi Set-Cookie hết hạn để browser ngừng gửi cookie hiện tại.

Ví dụ:

~~~java
http.logout(logout -> logout
    .invalidateHttpSession(true)
    .clearAuthentication(true)
    .deleteCookies("__Host-SESSION")
);
~~~

Cookie xóa phải khớp tên, Domain và Path của cookie đã phát. Với cookie __Host-SESSION, dùng Path=/ và không có Domain. Nếu serializer dùng cookie khác, cập nhật cấu hình logout tương ứng.

Nếu chỉ xóa cookie phía browser mà không invalidate session, bản sao cookie đã bị đánh cắp có thể vẫn hoạt động. Nếu chỉ invalidate session mà không xóa cookie, browser có thể tiếp tục gửi ID cũ, dẫn tới lookup miss và có thể tạo trải nghiệm lỗi.

Với CSRF protection bật, logout thường là POST và cần CSRF token. Không đổi logout thành GET chỉ để dễ dùng; GET không nên thực hiện hành động thay đổi trạng thái.

## 14. Tránh lộ cookie trong application log

Request header Cookie chứa session ID. Response header Set-Cookie cũng có thể chứa ID mới. Vì vậy, các kiểu log sau rất nguy hiểm:

- Log toàn bộ request/response headers.
- Log đối tượng HttpServletRequest hoặc ServerHttpRequest bằng toString không kiểm soát.
- Log exception kèm toàn bộ request.
- Ghi access log có Cookie hoặc Authorization header.
- Ghi Set-Cookie vào debug log.
- Log query string khi ứng dụng từng dùng URL rewriting.
- Gửi toàn bộ headers vào APM, distributed tracing hoặc error tracking.

Thay vào đó:

- Chỉ log method, route template, status, latency và request correlation ID.
- Cấu hình proxy access log loại bỏ Cookie, Set-Cookie và Authorization.
- Redact header nhạy cảm ở gateway/APM trước khi dữ liệu rời process.
- Không thêm session ID vào MDC.
- Không dùng session ID làm metric label.
- Không ghi nội dung SecurityContext hoặc thuộc tính session.
- Kiểm tra log ở cả mức INFO, DEBUG và TRACE.

Ví dụ log an toàn hơn:

~~~java
log.info(
    "Request completed: method={}, route={}, status={}, requestId={}",
    method,
    routeTemplate,
    status,
    requestId
);
~~~

Tránh log raw URL nếu URL có thể chứa query string nhạy cảm. Dùng route template như /orders/{orderId} thay cho toàn bộ URL cụ thể.

### Có thể dùng fingerprint để tương quan không?

Nếu có nhu cầu điều tra session qua nhiều log, tốt hơn là dùng request ID hoặc correlation ID. Trong trường hợp bắt buộc cần một fingerprint session, chỉ tạo giá trị HMAC bằng khóa giám sát được bảo vệ, giới hạn thời gian lưu và không ghi raw ID. Fingerprint vẫn là dữ liệu có thể liên kết hoạt động của một người dùng, nên cần chính sách truy cập và retention riêng. Không tạo fingerprint bằng cách hash đơn giản ID rồi coi là vô danh.

## 15. Reverse proxy và access log

Proxy, ingress, CDN và WAF thường ghi access log ở trước ứng dụng. Cần rà soát log format và quy tắc capture:

- Không log Cookie request header.
- Không log Set-Cookie response header.
- Không log Authorization header.
- Không log full query string nếu có thể chứa credential hoặc dữ liệu cá nhân.
- Không ghi request body đăng nhập hoặc refresh token.
- Không gửi raw header sang tracing backend.
- Không bật chế độ debug capture toàn bộ HTTP traffic trong production.

Nếu cần điều tra lỗi cookie, ghi lại thuộc tính cookie như Secure, HttpOnly, SameSite, Path và Domain mà không ghi giá trị cookie. Có thể kiểm tra tên cookie và việc header tồn tại mà không xuất giá trị.

Log retention, backup log và quyền truy cập log cũng cần được kiểm soát. Một session ID đã hết hạn vẫn có thể hữu ích cho kẻ tấn công nếu log bị truy cập khi session còn hiệu lực hoặc nếu có token khác bị lộ cùng log.

## 16. Cookie bảo vệ không thay thế CSRF và XSS defense

Các thuộc tính cookie giải quyết các vấn đề khác nhau:

- Secure bảo vệ việc browser gửi cookie qua transport không an toàn.
- HttpOnly ngăn JavaScript đọc giá trị cookie.
- SameSite hạn chế một số request cross-site.
- CSRF token xác nhận request thay đổi trạng thái được tạo từ một luồng hợp lệ.
- XSS defense ngăn script không tin cậy chạy trong origin ứng dụng.

Nếu ứng dụng dùng cookie để xác thực, browser tự gửi cookie theo domain/path/samesite policy. Do đó, các request thay đổi trạng thái cần CSRF protection phù hợp. SameSite là defense-in-depth, không phải lý do mặc định để tắt CSRF.

HttpOnly cũng không ngăn XSS thực hiện thao tác thay mặt người dùng. Script độc hại có thể gọi fetch tới ứng dụng và browser tự đính kèm cookie. Vì vậy, vẫn cần output encoding, CSP, kiểm soát dependency và kiểm tra authorization server-side.

CORS không thay thế CSRF. CORS chủ yếu điều khiển quyền JavaScript đọc response cross-origin; nó không ngăn mọi request cross-site được gửi.

## 17. Bảo vệ kho session và dữ liệu backup

Session ID trong cookie chỉ là một phần của dữ liệu nhạy cảm. Repository có thể lưu SecurityContext, principal, authorities và thuộc tính ứng dụng. Hãy bảo vệ cả kho dữ liệu:

- Chỉ cho phép ứng dụng và tài khoản quản trị được truy cập Redis/JDBC.
- Dùng TLS tới Redis và database khi mạng có thể bị nghe lén.
- Bật xác thực và ACL tối thiểu cho Redis.
- Dùng tài khoản database riêng, giới hạn quyền trên bảng session.
- Mã hóa volume, backup và snapshot theo chính sách tổ chức.
- Không dùng Redis MONITOR hoặc query dump tùy tiện trong production.
- Không export session payload vào ticket hoặc file hỗ trợ.
- Đặt retention phù hợp và xác nhận cleanup session hết hạn.
- Bảo vệ secret kết nối bằng secret manager.
- Có quy trình rotation credential và xử lý khi nghi ngờ lộ session.

Spring Session không tự động mã hóa mọi thuộc tính session ở tầng ứng dụng chỉ vì repository là Redis hoặc JDBC. Hãy xác minh encryption at rest của hạ tầng và yêu cầu bảo vệ payload. Nếu cần mã hóa thuộc tính ở tầng ứng dụng, thiết kế key management, rotation và khả năng đọc dữ liệu cũ trước khi triển khai.

## 18. Kiểm thử cookie và HTTPS

Một bộ integration test nên kiểm tra header Set-Cookie thực tế, không chỉ kiểm tra bean configuration.

Các điều kiện cần xác nhận cho production cookie:

~~~http
Set-Cookie: __Host-SESSION=<redacted>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Giá trị ID phải được che trong test report và log. Các assertion nên kiểm tra:

- Tên cookie đúng.
- Có Secure.
- Có HttpOnly.
- SameSite đúng.
- Path=/ nếu dùng prefix __Host-.
- Không có Domain nếu dùng prefix __Host-.
- Cookie được gửi lại trong request HTTPS tiếp theo.
- Cookie không được browser gửi qua HTTP.
- Logout phát cookie hết hạn với đúng tên và scope.
- Login đổi session ID nếu session fixation protection được bật.

Nếu dùng __Host-SESSION, test cần xác nhận không có Domain attribute. Nếu test chạy HTTP local, browser có thể từ chối cookie Secure hoặc prefix __Host-; dùng HTTPS test server hoặc profile riêng với tên cookie development khác. Không hạ cấu hình production chỉ để test local dễ hơn.

## 19. Kiểm thử URL rewriting và rò rỉ log

Các ca kiểm thử:

| Ca kiểm thử | Hành động | Kết quả cần xác nhận |
|---|---|---|
| Cookie tracking mode | Gọi endpoint có tạo session | URL/Location không có ;jsessionid |
| Redirect | Đăng nhập và redirect về trang đích | Không có session ID trong Location |
| Query string | Gửi request với query nhạy cảm giả lập | Log chỉ ghi route template hoặc query đã redacted |
| Request logging | Gửi Cookie chứa giá trị test | Log không chứa giá trị cookie |
| Response logging | Tạo session mới | Log không chứa Set-Cookie value |
| Proxy access log | Đi qua ingress | Cookie/Authorization bị loại khỏi log |
| Tracing | Bật instrumentation | Không capture session ID hoặc raw Cookie header |
| Error handling | Gây lỗi có kiểm soát | Error report không chứa request headers nhạy cảm |
| Logout | Invalidate session | Repository không còn session và cookie được hết hạn |

Dùng một chuỗi giả lập như test-session-secret-DO-NOT-LOG trong test để tìm kiếm log output. Không dùng session ID của người dùng thật để kiểm thử redaction.

Nếu log nằm ở nhiều hệ thống, test hoặc audit cấu hình ở từng lớp: reverse proxy, application logger, APM agent, tracing collector và error reporting. Việc che log trong ứng dụng không tự động che access log của ingress.

## 20. Kiểm thử proxy headers và TLS termination

Trong môi trường staging, kiểm thử cả request hợp lệ và header giả mạo:

1. Gửi HTTPS request qua ingress.
2. Xác nhận ứng dụng nhìn thấy scheme/secure state đúng theo cấu hình.
3. Xác nhận Set-Cookie có Secure.
4. Gửi request HTTP tới endpoint công khai và xác nhận chuyển hướng/không xử lý session theo policy.
5. Gửi X-Forwarded-Proto giả từ client trực tiếp nếu có đường truy cập test.
6. Xác nhận proxy xóa header giả và đặt giá trị đúng.
7. Xác nhận ứng dụng không chấp nhận forwarded header từ nguồn không tin cậy.
8. Kiểm tra redirect không tạo URL HTTP hoặc host do client giả mạo.

Không mở cổng ứng dụng nội bộ ra Internet để test forwarded headers. Thực hiện trong mạng staging được kiểm soát.

## 21. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Cookie production thiếu Secure | App nhận request nội bộ HTTP và serializer suy ra từ request | Cấu hình Secure=true và kiểm tra TLS/proxy |
| Browser không lưu cookie __Host- | Thiếu Secure, Path không phải / hoặc có Domain | Sửa cookie attributes |
| SSO callback mất session | SameSite=Strict hoặc cookie policy không phù hợp | Kiểm thử flow và chọn SameSite phù hợp |
| Cookie gửi tới subdomain không cần thiết | Domain đặt quá rộng | Dùng host-only cookie nếu có thể |
| Session ID xuất hiện trong URL | URL rewriting hoặc code tự nối ID | Chỉ cho tracking mode COOKIE và bỏ code đó |
| Logout nhưng cookie vẫn xuất hiện | Xóa cookie sai Path/Domain/name | Đồng bộ cookie deletion scope |
| Log chứa session ID | Log toàn header hoặc raw URL | Redact ở app, proxy, APM và trace |
| HttpOnly bật nhưng vẫn có hành động trái phép | XSS vẫn gửi request với cookie tự động | Sửa XSS, giữ CSRF và authorization |
| SameSite=None nhưng browser bỏ cookie | Thiếu Secure hoặc browser policy | Dùng HTTPS và test browser thực |
| Ứng dụng tin X-Forwarded-Proto giả | Proxy không xóa header đầu vào hoặc app trust mọi nguồn | Chỉ tin proxy được kiểm soát |
| Session bị chiếm dụng sau login | Không đổi ID sau xác thực | Bật và test session fixation protection |

## 22. Checklist triển khai an toàn

Trước khi phát hành Spring Session:

- Toàn bộ luồng đăng nhập và session dùng HTTPS.
- Session cookie có Secure và HttpOnly.
- SameSite được chọn theo luồng ứng dụng; None luôn đi cùng Secure.
- Domain được bỏ nếu không cần chia sẻ subdomain.
- Cookie Path và tên cookie được thống nhất giữa phát hành và logout.
- Nếu dùng __Host-, cookie có Secure, Path=/ và không có Domain.
- Proxy chỉ đặt forwarded headers từ nguồn tin cậy.
- TLS nội bộ và TLS tới Redis/JDBC được đánh giá theo threat model.
- HSTS chỉ bật với max-age và includeSubDomains phù hợp.
- Servlet tracking mode giới hạn ở COOKIE.
- Không có session ID trong URL, query string, redirect hoặc fragment.
- Session fixation protection được bật và kiểm thử.
- Logout invalidate session ở repository và hết hạn cookie đúng scope.
- CSRF vẫn được bảo vệ khi xác thực bằng cookie.
- XSS defense không dựa riêng vào HttpOnly.
- Cookie, Authorization và Set-Cookie được redacted ở application log, proxy, APM và tracing.
- Metric không chứa session ID hoặc principal có định danh.
- Redis/JDBC, backup và snapshot được phân quyền/mã hóa phù hợp.
- Có integration test cho HTTPS, cookie flags, proxy headers, URL rewriting và log redaction.

## 23. Quy tắc xử lý khi nghi ngờ session ID bị lộ

Nếu phát hiện session ID xuất hiện trong URL, log hoặc hệ thống bên thứ ba, hãy coi đó là credential có khả năng bị lộ:

1. Xác định phạm vi log, URL, trace và thời gian dữ liệu đã bị lưu.
2. Xác định session còn hiệu lực hay đã hết hạn.
3. Thu hồi session bị ảnh hưởng trong repository.
4. Xóa hoặc hạn chế quyền truy cập log chứa ID theo quy trình lưu trữ.
5. Kiểm tra truy cập bất thường và các request dùng session liên quan.
6. Xoay credential hoặc refresh token liên quan nếu có nguy cơ bị lộ cùng session.
7. Sửa cấu hình redaction/URL trước khi mở lại luồng.
8. Ghi nhận incident theo quy trình bảo mật của tổ chức.

Không chỉ đổi tên cookie hoặc xóa URL khỏi browser history rồi coi sự cố đã kết thúc. Nếu session vẫn còn hợp lệ, bản sao ID ở log hoặc hệ thống khác có thể tiếp tục được dùng.

HTTPS, cookie attributes và log redaction tạo thành một chuỗi bảo vệ. TLS bảo vệ đường truyền; Secure, HttpOnly và SameSite điều khiển browser; host-only scope giảm chia sẻ không cần thiết; URL tracking mode ngăn session ID bị nối vào URL; còn redaction giữ credential khỏi log, trace và APM. Kết hợp các lớp này với CSRF, XSS defense, session fixation protection và repository access control giúp Spring Session an toàn hơn khi chạy qua proxy và nhiều instance.

## Tài liệu tham khảo

- [Spring Session — HttpSession Integration](https://docs.spring.io/spring-session/reference/http-session.html)
- [Spring Session — CookieSerializer API](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/web/http/CookieSerializer.html)
- [Spring Session — DefaultCookieSerializer API](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/web/http/DefaultCookieSerializer.html)
- [Spring Security — Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Boot — Forwarded Headers](https://docs.spring.io/spring-boot/how-to/webserver.html#howto.webserver.use-behind-a-proxy-server)
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)

