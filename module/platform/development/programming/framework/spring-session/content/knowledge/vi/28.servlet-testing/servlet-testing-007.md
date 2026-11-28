# Kiểm tra Secure, HttpOnly, SameSite, Path, Domain của Set-Cookie

Spring Session gửi session ID tới client thông qua cookie hoặc một cơ chế resolver khác. Với ứng dụng Servlet dùng cookie, response thường chứa header Set-Cookie để browser lưu session ID. Các thuộc tính Secure, HttpOnly, SameSite, Path và Domain quyết định browser có chấp nhận cookie hay không, gửi cookie trong request nào và chia sẻ cookie tới host/path nào.

Không thể chỉ kiểm tra bean cấu hình rồi kết luận cookie an toàn. Điều cần kiểm chứng là header Set-Cookie thực tế sau khi request đi qua SessionRepositoryFilter, Spring Security, servlet container và reverse proxy. Một cấu hình đúng trong application context vẫn có thể bị ghi đè bởi resolver khác, filter khác hoặc proxy. Bài này hướng dẫn thiết kế cookie cho Spring Session, đọc đúng từng thuộc tính, viết integration test bằng MockMvc và kiểm tra hành vi thực tế trên browser.

## 1. Set-Cookie trong vòng đời Spring Session

Trong ứng dụng Servlet, Spring Session thường thay thế cách lưu HttpSession của container bằng SessionRepository. SessionRepositoryFilter bọc request/response, đọc session ID thông qua HttpSessionIdResolver và lưu session vào repository như Redis hoặc JDBC.

Khi cần tạo session mới hoặc phát hành ID mới, resolver ghi cookie vào response. Browser nhận Set-Cookie rồi tự gửi cookie ở các request sau theo thuộc tính của cookie.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant P as Reverse Proxy
    participant F as SessionRepositoryFilter
    participant R as SessionRepository
    B->>P: HTTPS request
    P->>F: Forward request
    F->>R: Find or create session
    R-->>F: Session
    F->>F: Controller updates session
    F->>R: Save session
    F->>B: Set-Cookie: SESSION=...
    B->>P: Next request + Cookie
    P->>F: Forward Cookie
    F->>R: Find session by ID
    R-->>F: Stored session
~~~

Header Set-Cookie là bằng chứng đầu tiên để kiểm tra cookie được phát. Nhưng nó chưa chứng minh browser sẽ lưu hoặc gửi cookie đúng cách. Browser còn áp dụng quy tắc Secure, SameSite, Domain, Path, prefix và chính sách cookie riêng tư.

Trong hệ thống nhiều instance, các node phải thống nhất cookie name và cookie attributes. Một node phát cookie tên SESSION nhưng node khác chỉ đọc cookie tên APPSESSION sẽ khiến phiên có vẻ mất ngẫu nhiên khi load balancer chuyển request.

## 2. Cấu hình DefaultCookieSerializer

Spring Session Servlet cung cấp CookieHttpSessionIdResolver và DefaultCookieSerializer. Resolver đọc session ID từ request cookie và ghi ID vào response. Serializer quyết định cookie name cùng các thuộc tính được phát hành.

Ví dụ cấu hình cookie host-only cho ứng dụng production chạy HTTPS:

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

        // Không đặt Domain: browser tạo host-only cookie.
        return serializer;
    }
}
~~~

Cấu hình trên giả định ứng dụng chỉ phát session cookie cho môi trường HTTPS. Cookie prefix __Host- có các điều kiện bắt buộc: phải có Secure, Path=/ và không được có Domain. Nếu ứng dụng cần chia sẻ session cookie giữa các subdomain, không dùng prefix __Host-; hãy cân nhắc lại phạm vi tin cậy của các subdomain.

Bean CookieSerializer phải được Spring Session resolver sử dụng thực tế. Nếu ứng dụng tự khai báo HttpSessionIdResolver hoặc cấu hình nhiều resolver, hãy kiểm tra bean nào đang hoạt động. Không giả định một bean serializer bất kỳ sẽ tự động ảnh hưởng tới mọi cookie trong ứng dụng.

API của DefaultCookieSerializer có thể thay đổi theo phiên bản Spring Session. Nếu setSameSite hoặc một thuộc tính không tồn tại trong dependency hiện tại, kiểm tra tài liệu của đúng phiên bản thay vì tự tạo header song song ở controller.

## 3. Ý nghĩa của Secure

Secure yêu cầu browser chỉ gửi cookie qua kết nối an toàn, thông thường là HTTPS. Nếu session cookie không có Secure, browser có thể gửi nó trong request HTTP tới host/path phù hợp, làm tăng nguy cơ lộ session ID trên mạng.

Header mẫu:

~~~http
Set-Cookie: __Host-SESSION=<redacted>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Với ứng dụng production:

- Bật Secure cho session cookie.
- Dùng HTTPS cho toàn bộ luồng đăng nhập và request mang session.
- Không phát session cookie qua endpoint HTTP.
- Kiểm tra TLS certificate và hostname.
- Không hạ cấp sang HTTP khi có lỗi TLS.
- Nếu TLS kết thúc tại proxy, kiểm tra cấu hình forwarded headers và cách serializer quyết định Secure.

DefaultCookieSerializer có thể suy ra Secure từ trạng thái request nếu không cấu hình rõ. Khi TLS terminate tại ingress, ứng dụng có thể nhận request nội bộ bằng HTTP và request.isSecure() trả false nếu forwarded headers không được xử lý. Với session cookie production, đặt Secure=true tường minh thường dễ kiểm chứng hơn.

Secure chỉ bảo vệ việc browser gửi cookie qua transport. Nó không ngăn XSS thực hiện request bằng cookie tự động, không che cookie khỏi application log và không mã hóa dữ liệu session ở Redis/JDBC.

## 4. Ý nghĩa của HttpOnly

HttpOnly ngăn JavaScript đọc cookie qua document.cookie. Đây là thuộc tính quan trọng đối với session ID vì JavaScript không cần biết giá trị ID để browser tự gửi cookie trong request phù hợp.

Ví dụ:

~~~http
Set-Cookie: SESSION=<redacted>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Khi HttpOnly được bật:

- document.cookie không hiển thị session cookie.
- Browser vẫn tự gửi cookie theo Domain, Path, Secure và SameSite.
- JavaScript vẫn có thể gửi request tới ứng dụng bằng fetch; browser có thể đính kèm cookie.
- XSS vẫn có thể thực hiện hành động trong quyền của người dùng dù không đọc được ID.

Vì vậy, HttpOnly không thay thế XSS defense hoặc CSRF protection. Ứng dụng vẫn cần output encoding, Content Security Policy phù hợp, kiểm soát script bên thứ ba, phân quyền server-side và CSRF token khi xác thực dựa trên cookie.

Không tắt HttpOnly chỉ để frontend đọc session ID rồi gắn vào header. Nếu frontend cần gọi API cùng origin, browser có thể tự gửi cookie mà JavaScript không cần truy cập giá trị.

## 5. Ý nghĩa của SameSite

SameSite giới hạn việc browser gửi cookie trong các ngữ cảnh cross-site. Nó là một lớp giảm rủi ro CSRF, nhưng lựa chọn phải phù hợp với login redirect, SSO, iframe và luồng tích hợp bên ngoài.

| Giá trị | Hành vi khái quát | Cân nhắc |
|---|---|---|
| Strict | Hạn chế cookie trong điều hướng/request cross-site | Phù hợp khi ứng dụng không cần luồng quay về từ site khác |
| Lax | Cho phép một số điều hướng top-level an toàn, hạn chế nhiều request cross-site | Điểm bắt đầu thường dùng cho web app |
| None | Cho phép cookie trong ngữ cảnh cross-site theo chính sách browser | Chỉ dùng khi SSO/iframe hoặc luồng cross-site thật sự cần |

SameSite=Lax thường tương thích hơn Strict với luồng người dùng quay lại từ một website bên ngoài. Tuy nhiên, callback có thể dùng POST hoặc iframe nên vẫn phải kiểm thử thực tế. SameSite=None cần Secure trong browser hiện đại. Nếu phát None mà thiếu Secure, browser có thể từ chối cookie.

SameSite áp dụng theo khái niệm site của browser, không hoàn toàn đồng nhất với origin. Hai subdomain có thể được xem là same-site trong một số trường hợp, nhưng vẫn khác origin. CORS và SameSite giải quyết các vấn đề khác nhau.

Cấu hình:

~~~java
serializer.setSameSite("Lax");
~~~

Không tắt CSRF chỉ vì đã đặt SameSite=Lax hoặc Strict. SameSite là defense-in-depth; hãy giữ CSRF protection cho các request thay đổi trạng thái khi browser tự động gửi cookie xác thực.

## 6. Ý nghĩa của Path

Path xác định các đường dẫn request mà browser gửi cookie. Ví dụ:

- Path=/ gửi cookie tới mọi path phù hợp trên host.
- Path=/app gửi cookie tới /app và các path con theo quy tắc cookie path-match.
- Path=/admin giới hạn cookie vào vùng đường dẫn tương ứng.

Ví dụ header:

~~~http
Set-Cookie: SESSION=<redacted>; Path=/app; Secure; HttpOnly; SameSite=Lax
~~~

Nếu ứng dụng đặt context path là /portal và muốn cookie chỉ dùng cho vùng đó, có thể cấu hình Path tương ứng sau khi kiểm tra cách triển khai thực tế. Với cookie prefix __Host-, Path bắt buộc là /.

Path không phải ranh giới bảo mật đáng tin cậy giữa các ứng dụng cùng host. Không dùng Path để cô lập hoàn toàn hai ứng dụng có mức tin cậy khác nhau trên cùng domain. Nếu cần cách ly mạnh, dùng host riêng hoặc một cơ chế xác thực riêng.

Với ứng dụng dùng session cho toàn bộ site, Path=/ thường đơn giản và dễ kiểm thử nhất. Đừng đặt Path quá hẹp khiến callback đăng nhập, logout hoặc endpoint API không gửi cookie.

## 7. Ý nghĩa của Domain

Domain quyết định host nào có thể nhận cookie. Nếu bỏ thuộc tính Domain, browser tạo host-only cookie: cookie chỉ được gửi tới host đã phát nó.

Ví dụ, host-only cookie phát từ app.example.com không tự động được gửi tới admin.example.com. Nếu cấu hình Domain=example.com, cookie có thể được gửi tới các subdomain phù hợp.

| Cấu hình | Phạm vi |
|---|---|
| Không có Domain | Host-only cookie |
| Domain=app.example.com | Domain cookie có phạm vi host/domain đó theo quy tắc browser |
| Domain=example.com | Có thể chia sẻ tới các subdomain phù hợp |
| Domain quá rộng | Tăng phạm vi nơi cookie có thể bị gửi/ghi đè |

Nếu không cần chia sẻ session giữa subdomain, bỏ Domain là lựa chọn tốt hơn. Một subdomain kém an toàn hoặc bị chiếm quyền có thể làm tăng rủi ro khi cookie được chia sẻ ở domain cha.

DefaultCookieSerializer hỗ trợ cấu hình domain tĩnh hoặc pattern trong những phiên bản tương ứng. Chỉ dùng domain pattern khi có yêu cầu multi-tenant/subdomain cụ thể và đã kiểm thử cách regex chọn domain. Không dùng regex rộng đến mức một Host header không tin cậy có thể làm cookie được phát tới domain ngoài ý muốn.

Cookie prefix __Host- không được đi cùng Domain. Nếu muốn Domain=example.com hoặc chia sẻ giữa subdomain, phải dùng tên cookie khác và đánh giá rủi ro mở rộng phạm vi.

## 8. Cookie prefix __Host- và __Secure-

Browser hiện đại hỗ trợ các quy ước prefix cho cookie:

| Prefix | Điều kiện quan trọng |
|---|---|
| __Secure- | Cookie phải có Secure |
| __Host- | Phải có Secure, Path=/ và không có Domain |

Dùng __Host-SESSION là cách tăng cường ràng buộc host-only cookie. Browser sẽ từ chối cookie có prefix này nếu thiếu điều kiện bắt buộc.

Ví dụ đúng:

~~~http
Set-Cookie: __Host-SESSION=<redacted>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Ví dụ không hợp lệ với prefix __Host-:

~~~http
Set-Cookie: __Host-SESSION=<redacted>; Domain=example.com; Path=/; Secure
~~~

Ví dụ thứ hai có Domain nên browser phải từ chối cookie theo quy tắc prefix. Việc chỉ đặt tên cookie bắt đầu bằng __Host- không tự tạo bảo vệ; header phải thỏa toàn bộ điều kiện.

Nếu dùng prefix __Secure-, vẫn phải tự kiểm tra Domain và Path. Prefix này chỉ ràng buộc Secure, không bắt buộc host-only hoặc Path=/.

## 9. Cấu hình host-only cookie và cookie chia sẻ subdomain

Với ứng dụng một host, cấu hình không đặt Domain:

~~~java
DefaultCookieSerializer serializer =
        new DefaultCookieSerializer();

serializer.setCookieName("SESSION");
serializer.setCookiePath("/");
serializer.setUseSecureCookie(true);
serializer.setUseHttpOnlyCookie(true);
serializer.setSameSite("Lax");
// Không gọi setDomainName.
~~~

Khi đó, header Set-Cookie không nên có thuộc tính Domain. Đây là điều cần test trực tiếp.

Nếu yêu cầu chia sẻ giữa app.example.com và api.example.com, có thể cấu hình domain cha sau khi đánh giá rủi ro:

~~~java
serializer.setCookieName("APPSESSION");
serializer.setCookiePath("/");
serializer.setDomainName("example.com");
serializer.setUseSecureCookie(true);
serializer.setUseHttpOnlyCookie(true);
serializer.setSameSite("Lax");
~~~

Không kết hợp cấu hình Domain trên với prefix __Host-. Ngoài ra, các subdomain phải có cùng mức tin cậy, cùng chính sách HTTPS và cùng hiểu session repository. Nếu các ứng dụng dùng session store khác nhau hoặc serializer khác nhau, chia sẻ cookie ID không đủ để chia sẻ phiên thành công.

## 10. Cấu hình cookie trong Spring Boot và reverse proxy

Khi TLS kết thúc tại load balancer/ingress, ứng dụng có thể nhận request HTTP từ proxy. Spring Boot cần được cấu hình để xử lý forwarded headers đúng cách khi ứng dụng cần biết scheme/host bên ngoài.

Ví dụ:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Tùy phiên bản Spring Boot và servlet container, có thể dùng framework, native hoặc none. Chọn một cơ chế và tránh xử lý forwarded headers nhiều lần.

Chỉ tin forwarded headers từ proxy được kiểm soát:

- Proxy phải xóa Forwarded/X-Forwarded-* do client gửi.
- Proxy tự ghi giá trị scheme, host và port chính xác.
- Ứng dụng không được nhận traffic trực tiếp từ nguồn không tin cậy nếu đang tin các header đó.
- Không mở cổng backend ra Internet chỉ để tiện truy cập.
- Kiểm thử request qua ingress thật.

Với cookie Secure cố định true, việc suy ra scheme không còn quyết định thuộc tính Secure của cookie. Nhưng forwarded headers vẫn ảnh hưởng redirect, URL tuyệt đối và các logic khác. Đừng coi X-Forwarded-Proto do client gửi là bằng chứng HTTPS.

## 11. Kiểm tra Set-Cookie thực tế bằng MockMvc

MockMvc có thể kiểm tra response sau khi request đi qua Spring MVC và filter chain. Để test có ý nghĩa, phải bật SessionRepositoryFilter thực tế trong test context và gọi endpoint thật sự tạo session.

Ví dụ endpoint test:

~~~java
@RestController
class SessionProbeController {

    @GetMapping("/test/session")
    String createSession(HttpServletRequest request) {
        HttpSession session = request.getSession(true);
        session.setAttribute("test.marker", "created");
        return "ok";
    }
}
~~~

Integration test:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class SessionCookieIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void emitsProtectedHostOnlySessionCookie() throws Exception {
        MvcResult result = mockMvc.perform(
                get("/test/session").secure(true)
            )
            .andExpect(status().isOk())
            .andReturn();

        Collection<String> setCookies =
                result.getResponse().getHeaders(HttpHeaders.SET_COOKIE);

        String cookie = setCookies.stream()
            .filter(value -> value.startsWith("__Host-SESSION="))
            .findFirst()
            .orElseThrow();

        String normalized = cookie.toLowerCase(Locale.ROOT);

        assertThat(normalized).contains("; path=/");
        assertThat(normalized).contains("; secure");
        assertThat(normalized).contains("; httponly");
        assertThat(normalized).contains("; samesite=lax");
        assertThat(normalized).doesNotContain("; domain=");
    }
}
~~~

Đoạn test giả định ứng dụng đã cấu hình CookieSerializer như ví dụ và có AssertJ cùng các static import cần thiết. Endpoint chỉ dùng trong test profile, không cần đưa vào production.

Lấy toàn bộ Set-Cookie values bằng getHeaders. Không dùng getHeader nếu có thể có nhiều cookie trong response. Không nối nhiều Set-Cookie thành một chuỗi rồi split bằng dấu phẩy vì thuộc tính Expires có thể chứa dấu phẩy.

Không in giá trị cookie ra console hoặc test report. Khi assertion thất bại, tránh để framework dump toàn bộ header nhạy cảm.

## 12. Kiểm tra Secure khi request được đánh dấu HTTPS

MockMvc có thể mô phỏng request secure:

~~~java
mockMvc.perform(get("/test/session").secure(true))
       .andExpect(status().isOk());
~~~

Điều này kiểm tra cách ứng dụng phản ứng với trạng thái request mà MockMvc cung cấp. Nó không kiểm tra TLS handshake, certificate, ingress hoặc browser thật.

Nếu CookieSerializer đặt useSecureCookie=true, cookie phải có Secure kể cả khi test chạy qua mock request. Nếu ứng dụng dựa vào request.isSecure(), cần thêm test request secure=false và secure=true để xác nhận hành vi được mong muốn.

Không coi việc secure(true) trong MockMvc là bằng chứng reverse proxy production đã cấu hình đúng. Cần một integration test qua staging ingress để kiểm tra TLS termination và forwarded headers.

## 13. Kiểm tra HttpOnly và SameSite

MockMvc không chạy JavaScript hoặc mô phỏng đầy đủ chính sách cookie của browser. Nó chỉ cho phép kiểm tra header được phát.

Với HttpOnly, kiểm tra header có thuộc tính:

~~~java
assertThat(normalized).contains("; httponly");
~~~

Với SameSite, kiểm tra giá trị không phân biệt hoa thường:

~~~java
assertThat(normalized).contains("; samesite=lax");
~~~

Nên kiểm tra các cấu hình khác nhau theo profile hoặc luồng:

- Lax cho web application thông thường.
- Strict cho ứng dụng không cần cross-site navigation.
- None cho luồng cross-site đã được xác định và luôn đi cùng Secure.

Không chỉ kiểm tra cấu hình property. Test phải lấy Set-Cookie từ response thực tế để phát hiện serializer không được sử dụng, resolver khác ghi cookie hoặc proxy sửa header.

## 14. Kiểm tra Path và Domain

Với Path, assertion cần xác nhận giá trị chính xác:

~~~java
assertThat(normalized).contains("; path=/");
~~~

Nếu ứng dụng cần Path=/portal, kiểm tra đúng Path=/portal và kiểm tra browser có gửi cookie tới các endpoint cần thiết hay không.

Với host-only cookie, xác nhận không có Domain:

~~~java
assertThat(normalized).doesNotContain("; domain=");
~~~

Với domain cookie, xác nhận giá trị chính xác:

~~~java
assertThat(normalized).contains("; domain=example.com");
~~~

Không dùng một assertion chỉ tìm chuỗi example.com ở mọi nơi vì chuỗi đó có thể xuất hiện trong cookie value hoặc một thuộc tính khác. Hãy kiểm tra ranh giới thuộc tính và tên cookie trước.

Test host-only và domain cookie nên là hai cấu hình riêng. Không dùng cookie prefix __Host- cho test có Domain. Khi kiểm thử domain trên localhost, browser có thể áp dụng quy tắc khác với domain DNS thông thường; dùng hostname test như app.example.test trong môi trường kiểm soát.

## 15. Kiểm tra nhiều Set-Cookie trong cùng response

Một response có thể chứa nhiều Set-Cookie: session cookie, remember-me cookie, CSRF cookie hoặc cookie của ứng dụng khác. Không giả định chỉ có một header.

Ví dụ cách chọn đúng cookie:

~~~java
Collection<String> headers =
        response.getHeaders(HttpHeaders.SET_COOKIE);

String sessionCookie = headers.stream()
    .filter(value -> value.startsWith("SESSION="))
    .findFirst()
    .orElseThrow();
~~~

Tên cookie phải khớp cấu hình CookieSerializer của ứng dụng. Nếu đổi tên cookie, cập nhật cả test, logout và các client liên quan.

Không gộp các Set-Cookie values thành một header phân cách bằng dấu phẩy. Theo cách xử lý HTTP, Set-Cookie là header cần giữ riêng từng giá trị; dấu phẩy trong Expires có thể làm parser đơn giản tách sai.

## 16. Kiểm tra cookie khi logout hoặc invalidate

Logout cần thu hồi session ở repository và làm browser hết hạn cookie. Chỉ xóa cookie phía client không thu hồi session ID đã bị sao chép.

Khi xóa cookie, tên, Path và Domain phải khớp cookie ban đầu. Với host-only cookie, response xóa cũng không nên thêm Domain. Với cookie prefix __Host-, phải giữ Secure và Path=/.

Ví dụ cấu hình logout:

~~~java
http.logout(logout -> logout
    .invalidateHttpSession(true)
    .clearAuthentication(true)
    .deleteCookies("__Host-SESSION")
);
~~~

Tùy tích hợp Spring Session, resolver có thể phát cookie hết hạn khi session bị invalidate. Test cần quan sát response thực tế, không chỉ kiểm tra logout config.

Các điều kiện cần xác nhận:

- Session đã bị xóa hoặc invalidated trong repository.
- Response phát Set-Cookie cho đúng tên cookie.
- Cookie có Max-Age=0 hoặc Expires đã ở quá khứ theo cách serializer/container triển khai.
- Path và Domain khớp cookie ban đầu.
- Cookie Secure/HttpOnly/SameSite theo policy phù hợp.
- Cookie cũ được gửi lại không khôi phục session đã bị thu hồi.

Nếu dùng Spring Security CSRF, logout thường là POST và cần CSRF token hợp lệ. Không đổi logout thành GET chỉ để test đơn giản.

## 17. Kiểm tra cookie sau session fixation protection

Sau đăng nhập, Spring Security có thể đổi session ID để chống session fixation. Response cần phát ID mới trong cookie với các thuộc tính bảo vệ tương tự.

Test nên:

1. Tạo session trước đăng nhập.
2. Ghi nhận cookie ban đầu trong biến test, không in giá trị.
3. Thực hiện login thành công.
4. Lấy Set-Cookie mới.
5. Xác nhận session ID đã thay đổi theo cơ chế đang dùng.
6. Xác nhận Secure, HttpOnly, SameSite, Path và Domain vẫn đúng.
7. Gửi request tiếp theo bằng cookie mới.
8. Xác nhận cookie cũ không còn được chấp nhận.

Không so sánh toàn bộ header cookie nếu giá trị được encode hoặc format thay đổi hợp lệ giữa phiên bản. Tách phần cookie name/value và attributes, đồng thời chỉ so sánh giá trị ID trong bộ nhớ test.

## 18. Kiểm tra cookie trên browser thật

MockMvc kiểm tra server phát header. Browser E2E kiểm tra browser có chấp nhận và gửi cookie theo quy tắc thực tế.

Với Playwright, có thể đọc metadata cookie mà không in giá trị:

~~~javascript
const cookies = await page.context().cookies("https://app.example.test");
const session = cookies.find(c => c.name === "__Host-SESSION");

expect(session).toBeDefined();
expect(session.secure).toBe(true);
expect(session.httpOnly).toBe(true);
expect(session.sameSite).toBe("Lax");
expect(session.path).toBe("/");
expect(session.domain).toBe("app.example.test");
~~~

Browser API có thể biểu diễn host-only domain theo hostname của cookie. Đối chiếu cả Set-Cookie header và browser cookie metadata để xác định Domain thực sự được phát hay không.

Các tình huống nên kiểm tra trên browser:

- Cookie Secure không được gửi qua HTTP.
- HttpOnly cookie không xuất hiện trong document.cookie.
- SameSite=Lax trong cross-site top-level navigation.
- SameSite=Strict trong luồng quay về từ site ngoài.
- SameSite=None chỉ hoạt động khi Secure và được browser chấp nhận.
- Host-only cookie không được gửi tới subdomain khác.
- Domain cookie được gửi tới subdomain phù hợp.
- Path giới hạn request theo cookie path-match.
- Logout xóa cookie trong browser storage.
- Cookie prefix __Host- bị từ chối nếu thiếu điều kiện bắt buộc.

Dùng browser automation trong môi trường test, với domain giả lập và TLS hợp lệ. Không dùng session cookie production để kiểm thử.

## 19. SameSite và CSRF: kiểm thử theo luồng người dùng

Nếu ứng dụng dùng session cookie, browser có thể tự đính kèm cookie khi gửi request. Cần kiểm thử CSRF theo đúng luồng:

| Luồng | Điều cần xác nhận |
|---|---|
| Form POST cùng site | CSRF token hợp lệ được chấp nhận |
| Form POST cross-site | Request không có CSRF token hợp lệ bị từ chối |
| Top-level navigation GET từ site khác | Hành vi phù hợp với SameSite=Lax |
| SSO callback GET | Cookie có được gửi theo thiết kế |
| SSO callback POST | SameSite policy và state validation hoạt động |
| iframe cross-site | Nếu cần, SameSite=None; Secure và browser policy được kiểm tra |
| API fetch cross-origin | CORS, credentials và CSRF được kiểm tra riêng |

CORS không thay thế CSRF. CORS chủ yếu kiểm soát JavaScript có được đọc response cross-origin hay không; nó không phải cơ chế thu hồi cookie hoặc xác nhận ý định của người dùng.

Không tắt CSRF chỉ vì đã đặt SameSite=Strict. Nếu browser tự động gửi cookie xác thực, hãy giữ CSRF defense phù hợp.

## 20. Kiểm tra cookie qua reverse proxy và ingress

Proxy có thể thêm, xóa hoặc ghi đè response headers. Vì vậy, kiểm tra trực tiếp MockMvc chưa đủ nếu production có ingress, gateway, CDN hoặc WAF.

Một kiểm thử staging nên:

1. Gửi HTTPS request qua ingress tới endpoint tạo session.
2. Lưu Set-Cookie header trong test harness có redaction.
3. Xác nhận Secure, HttpOnly, SameSite, Path và Domain.
4. Kiểm tra proxy không xóa hoặc thêm thuộc tính ngoài ý muốn.
5. Gửi request tiếp theo qua ingress với cookie.
6. Xác nhận ứng dụng tải đúng session.
7. Thử HTTP endpoint công khai và xác nhận session cookie không bị phát qua HTTP.
8. Kiểm tra forwarded headers giả mạo bị proxy xóa.
9. Kiểm tra response logout xóa đúng cookie.

Không log nguyên header Set-Cookie trong pipeline CI hoặc staging. Có thể ghi trạng thái assertion PASS/FAIL và các thuộc tính không nhạy cảm, nhưng phải che giá trị ID.

## 21. Các lỗi thường gặp khi kiểm thử Set-Cookie

| Triệu chứng | Nguyên nhân có thể | Cách chẩn đoán |
|---|---|---|
| Cookie thiếu Secure trong production | App nhận request nội bộ HTTP hoặc serializer không cấu hình tường minh | Kiểm tra Secure config và ingress |
| Cookie thiếu HttpOnly | Resolver/serializer khác được sử dụng | Kiểm tra bean và header thực tế |
| Browser bỏ cookie SameSite=None | Thiếu Secure hoặc chính sách browser | Kiểm tra header và browser console |
| SSO callback không có session | SameSite quá chặt hoặc callback dùng POST | Kiểm thử luồng SSO thực tế |
| Cookie không gửi tới API path | Path quá hẹp | Kiểm tra Path và URL request |
| Cookie bị chia sẻ ngoài ý muốn | Domain đặt rộng | Bỏ Domain hoặc thu hẹp phạm vi |
| __Host- cookie bị từ chối | Có Domain, thiếu Secure hoặc Path khác / | Kiểm tra cả ba điều kiện |
| Logout không xóa cookie | Sai tên, Path hoặc Domain | So sánh Set-Cookie ban đầu và header hết hạn |
| Test chỉ thấy một cookie | Dùng getHeader thay vì getHeaders | Đọc toàn bộ Set-Cookie values |
| Test pass nhưng browser không lưu | MockMvc không mô phỏng browser policy | Thêm browser E2E |
| Cookie bị thay đổi ở production | Proxy/gateway rewrite response header | Kiểm thử qua ingress |
| Test report lộ session ID | Assertion failure in toàn header | Redact cookie value và log |

## 22. Ma trận kiểm thử tối thiểu

Trước khi phát hành, nên có các kiểm tra sau:

| Thuộc tính | MockMvc/Integration | Browser E2E | Tiêu chí đạt |
|---|---|---|---|
| Secure | Kiểm tra Set-Cookie có Secure | Cookie không gửi qua HTTP | Có Secure trong production |
| HttpOnly | Kiểm tra header | Không đọc được qua document.cookie | Có HttpOnly |
| SameSite | Kiểm tra giá trị header | Cross-site flow đúng policy | Đúng Lax/Strict/None đã chọn |
| Path | Kiểm tra Path chính xác | Cookie chỉ gửi theo path-match | Không quá rộng hoặc quá hẹp |
| Domain | Kiểm tra có/không có Domain | Host/subdomain nhận cookie đúng | Host-only nếu không cần chia sẻ |
| Prefix | Kiểm tra tên và attributes | Browser chấp nhận cookie | __Host- hoặc __Secure- thỏa điều kiện |
| Logout | Kiểm tra header hết hạn và repository | Browser xóa cookie | ID cũ không còn dùng được |
| Session fixation | Kiểm tra cookie sau login | Browser dùng ID mới | ID cũ bị thu hồi |
| Proxy | Test qua ingress | Browser kết nối HTTPS thực | Header không bị rewrite sai |
| CSRF | Test token và status | Cross-site form/fetch | Request không hợp lệ bị từ chối |

Đối với môi trường production, test cần chạy với đúng Spring Session version, servlet container, reverse proxy và browser hỗ trợ. MockMvc là lớp kiểm tra nhanh trong CI; browser E2E và staging ingress xác nhận hành vi cuối cùng.

## 23. Quy tắc thực hành

- Cấu hình CookieSerializer một cách tường minh cho production.
- Dùng Secure và HttpOnly cho session cookie.
- Chọn SameSite dựa trên luồng login/SSO thực tế.
- Bỏ Domain để có host-only cookie nếu không cần chia sẻ subdomain.
- Chọn Path phù hợp với toàn bộ endpoint cần session.
- Nếu dùng __Host-, bắt buộc Secure, Path=/ và không có Domain.
- Không phát session ID trong URL.
- Giữ CSRF protection khi browser tự động gửi cookie xác thực.
- Đảm bảo logout invalidates repository và hết hạn cookie đúng scope.
- Kiểm tra tất cả Set-Cookie values, không giả định chỉ có một header.
- Không in cookie value trong log hoặc test report.
- Kiểm tra response sau reverse proxy, không chỉ ở MockMvc.
- Dùng browser E2E cho SameSite, Domain, Path và Secure behavior.
- Đồng bộ cookie name/attributes giữa mọi instance.

Set-Cookie là hợp đồng giữa Spring Session và browser. Secure bảo vệ việc gửi cookie qua transport, HttpOnly hạn chế JavaScript đọc ID, SameSite giảm một số request cross-site, Path giới hạn URL gửi cookie và Domain quyết định phạm vi host. Hãy kiểm tra header thực tế được phát qua SessionRepositoryFilter, xác minh browser chấp nhận và gửi cookie đúng như mong đợi, rồi lặp lại các phép thử qua ingress production-like. Một cấu hình chỉ được coi là đúng khi cookie được phát, lưu, gửi lại và xóa đúng trong toàn bộ vòng đời session.

## Tài liệu tham khảo

- [Spring Session — HttpSession Integration](https://docs.spring.io/spring-session/reference/http-session.html)
- [Spring Session — CookieSerializer API](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/web/http/CookieSerializer.html)
- [Spring Session — DefaultCookieSerializer API](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/web/http/DefaultCookieSerializer.html)
- [Spring Session — CookieHttpSessionIdResolver API](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/web/http/CookieHttpSessionIdResolver.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Boot — Forwarded Headers](https://docs.spring.io/spring-boot/how-to/webserver.html#howto.webserver.use-behind-a-proxy-server)
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)

