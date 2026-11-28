# Kiểm thử HeaderHttpSessionIdResolver và đường đi không dùng cookie

Spring Session thường nhận diện HTTP session bằng cookie, nhưng ứng dụng Servlet cũng có thể truyền session ID trong một HTTP header. Cách này hữu ích cho mobile/native client, CLI, service client hoặc frontend chủ động quản lý credential. Spring Session cung cấp HeaderHttpSessionIdResolver để đọc ID từ request header và ghi ID vào response header.

Đường đi không dùng cookie vẫn là session có trạng thái. Header chỉ mang session ID; dữ liệu session vẫn được lưu trong Redis, JDBC hoặc repository khác. Để kiểm thử đúng, cần tạo session ở request đầu, đọc ID từ response header, gửi ID trong request tiếp theo và xác minh server khôi phục đúng attributes mà không cần cookie. Cần kiểm tra thêm ID thiếu/không tồn tại/hết hạn, logout, session ID rotation, CORS, proxy và bảo vệ bearer credential.

## 1. HeaderHttpSessionIdResolver hoạt động thế nào?

HttpSessionIdResolver là contract Spring Session dùng để đọc session ID từ request và ghi hoặc xóa định danh trong response. HeaderHttpSessionIdResolver triển khai contract này bằng một HTTP header thay cho cookie.

Các factory thường dùng:

- HeaderHttpSessionIdResolver.xAuthToken() sử dụng header X-Auth-Token.
- HeaderHttpSessionIdResolver.headerName("X-Session-Id") sử dụng tên header tùy chỉnh.

Luồng cơ bản:

1. Client gửi request không có session cookie.
2. Controller hoặc Spring Security tạo session qua Servlet API nếu cần.
3. SessionRepositoryFilter lưu session qua repository.
4. Resolver đặt session ID vào response header.
5. Client đọc header và giữ ID.
6. Request tiếp theo gửi ID trong request header.
7. Resolver đọc ID, repository tải session và filter bọc request để code phía sau dùng HttpSession bình thường.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant F as SessionRepositoryFilter
    participant R as SessionRepository
    C->>F: POST /session, không có cookie
    F->>R: Tạo và lưu session
    R-->>F: Session ID
    F-->>C: Response header X-Auth-Token
    Note over C: Client giữ session ID
    C->>F: GET /profile, X-Auth-Token
    F->>R: Tìm session theo ID
    R-->>F: Session attributes
    F-->>C: Response profile
~~~

Header chỉ mang định danh. Nó không chứa session attributes, không biến session thành JWT và không làm repository trở thành stateless. Server vẫn lưu session và kiểm tra ID trên mỗi request.

## 2. Cấu hình HeaderHttpSessionIdResolver

Trong Servlet application, khai báo bean HttpSessionIdResolver để Spring Session dùng header resolver:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.web.http.HeaderHttpSessionIdResolver;
import org.springframework.session.web.http.HttpSessionIdResolver;

@Configuration
class SessionIdResolverConfiguration {

    @Bean
    HttpSessionIdResolver httpSessionIdResolver() {
        return HeaderHttpSessionIdResolver.xAuthToken();
    }
}
~~~

Nếu muốn dùng header riêng:

~~~java
@Bean
HttpSessionIdResolver httpSessionIdResolver() {
    return HeaderHttpSessionIdResolver.headerName("X-Session-Id");
}
~~~

Chỉ chọn một resolver theo thiết kế. HeaderHttpSessionIdResolver đọc session ID từ header đã cấu hình; nó không tự động dùng cookie làm phương án dự phòng. Nếu ứng dụng cần hỗ trợ cả cookie và header, phải cấu hình resolver kết hợp có chủ đích và kiểm thử rõ thứ tự/ưu tiên. Không để một CookieHttpSessionIdResolver khác được đăng ký song song ngoài ý muốn.

Spring Boot có thể tự cấu hình SessionRepositoryFilter khi dependency và repository phù hợp. Xác minh ứng dụng chỉ có một filter quản lý HttpSession và bean resolver được filter đó sử dụng. Không đăng ký thêm filter thứ hai chỉ để đổi resolver.

## 3. Tạo session và nhận session ID trong response header

Ví dụ controller Servlet tạo session và ghi một thuộc tính:

~~~java
@RestController
class SessionProbeController {

    @PostMapping("/api/session")
    Map<String, Object> create(HttpServletRequest request) {
        HttpSession session = request.getSession();
        session.setAttribute("displayName", "Lan");
        return Map.of("created", true, "sessionPresent", true);
    }

    @GetMapping("/api/profile")
    Map<String, Object> profile(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session == null) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }
        return Map.of("displayName", session.getAttribute("displayName"));
    }
}
~~~

Controller không tự đặt session ID vào response. Spring Session filter phối hợp với resolver để phát header khi session được tạo hoặc định danh thay đổi. Ví dụ không trả session ID trong JSON vì ID phải được truyền qua response header và không nên xuất hiện trong body, URL hoặc log.

Với resolver mặc định, tên header thường là X-Auth-Token. Client cần đọc header từ response đầu tiên. Nếu session đã tồn tại và ID không đổi, response tiếp theo không nhất thiết phát lại header; client tiếp tục gửi ID đã nhận. Khi session fixation protection đổi ID, resolver có thể phát ID mới để client thay thế giá trị cũ.

## 4. Gửi request tiếp theo không dùng cookie

Ví dụ dùng curl:

~~~bash
# Tạo session và xem response headers
curl -i -X POST http://localhost:8080/api/session

# Dùng session ID đã nhận trong X-Auth-Token
curl -i -H "X-Auth-Token: <SESSION_ID>" http://localhost:8080/api/profile
~~~

SESSION_ID là placeholder. Trong thực tế, lấy giá trị từ response header và giữ trong client state; không ghi ID thật vào shell history, ticket hoặc log chia sẻ. Không dùng cookie jar trong phép thử này vì mục tiêu là xác nhận header là nguồn session ID.

Để chứng minh request không dựa vào cookie, gửi request có header nhưng không có Cookie, sau đó gửi request chỉ có cookie nhưng không có header. Với resolver header-only, request thứ nhất phải khôi phục session; request thứ hai không được dùng cookie để khôi phục session. Nếu kết quả ngược lại, kiểm tra xem resolver khác hoặc container session management mặc định có còn hoạt động không.

## 5. Kiểm thử resolver ở mức unit

HeaderHttpSessionIdResolver có thể được kiểm tra độc lập bằng mock Servlet request/response. Các hành vi cần xác minh:

- Không có header: không resolve được session ID.
- Có header hợp lệ: resolver trả session ID từ header.
- Header name tùy chỉnh: resolver đọc đúng header đã cấu hình.
- setSessionId: resolver đặt session ID vào response header.
- expireSession: resolver yêu cầu client loại bỏ định danh theo semantics của implementation.

Ví dụ minh họa với Spring test mocks:

~~~java
class HeaderResolverTest {

    private final HeaderHttpSessionIdResolver resolver =
            HeaderHttpSessionIdResolver.xAuthToken();

    @Test
    void resolvesIdFromHeader() {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader("X-Auth-Token", "test-session-id");

        assertThat(resolver.resolveSessionIds(request))
                .contains("test-session-id");
    }

    @Test
    void doesNotResolveIdFromCookie() {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.setCookies(new Cookie("SESSION", "cookie-only-id"));

        assertThat(resolver.resolveSessionIds(request)).isEmpty();
    }

    @Test
    void writesIdToResponseHeader() {
        MockHttpServletRequest request = new MockHttpServletRequest();
        MockHttpServletResponse response = new MockHttpServletResponse();

        resolver.setSessionId(request, response, "new-session-id");

        assertThat(response.getHeader("X-Auth-Token"))
                .isEqualTo("new-session-id");
    }
}
~~~

Đây là ví dụ theo Servlet Spring Test; cần thêm static imports và dependency test tương ứng. Nếu API thay đổi theo phiên bản Spring Session, dùng signature của phiên bản dự án nhưng giữ nguyên mục tiêu kiểm thử. Không assert session ID thật được sinh bởi repository; dùng ID giả trong unit test.

Test expireSession nên xác minh response header được xử lý theo phiên bản resolver đang dùng. Với header resolver phổ biến, response đánh dấu định danh hết hiệu lực bằng giá trị header rỗng; client phải xóa ID đã lưu thay vì gửi lại giá trị cũ. Đây không phải thao tác xóa cookie.

## 6. Kiểm thử end-to-end qua SessionRepositoryFilter

Unit test resolver chỉ xác nhận cách đọc/ghi header. Cần integration test để chứng minh session được tạo, lưu và khôi phục qua repository:

1. Gửi POST tạo session mà không gửi Cookie hoặc session header.
2. Xác minh response có X-Auth-Token hoặc header đã cấu hình khi session ID được phát.
3. Lấy ID trong bộ nhớ test, không in ra log.
4. Gửi GET tiếp theo chỉ với header ID; không gửi cookie.
5. Xác minh controller đọc được attribute đã lưu.
6. Gửi request chỉ với cookie giả và không có header; xác minh session cũ không được khôi phục.
7. Gửi request với ID không tồn tại; xác minh ứng dụng xử lý như không có phiên.
8. Logout session; gửi lại ID cũ và xác minh nó không còn hợp lệ.

Ví dụ một phần assertion bằng MockMvc:

~~~java
mockMvc.perform(post("/api/session"))
        .andExpect(status().isOk())
        .andExpect(header().exists("X-Auth-Token"));
~~~

Đây mới là một phần của test; cần lấy header từ MvcResult rồi gửi trong request tiếp theo. MockMvc phải có SessionRepositoryFilter trong filter chain. Nếu chỉ tạo MockMvc với controller mà bỏ qua filter, test không kiểm tra được resolver. Với cấu hình phức tạp, dùng embedded Servlet container để xác minh filter chain thực tế.

## 7. Kiểm thử header tùy chỉnh

Nếu cấu hình X-Session-Id, mọi request và response test phải dùng đúng tên đó. Kiểm thử cả hai hướng:

- Header X-Session-Id có giá trị: resolve thành session ID.
- Header X-Auth-Token có giá trị nhưng X-Session-Id không có: không khôi phục session.
- Response tạo session: ID được phát trong X-Session-Id.
- Expire session: response xử lý header custom theo semantics resolver.

HTTP header name không phân biệt chữ hoa/chữ thường theo chuẩn, nhưng không nên dựa vào việc proxy hoặc test framework tự chuẩn hóa sai cấu hình. Tên header trong CORS allow/expose, API gateway, WAF và logging policy phải thống nhất.

Không dùng tên header dễ va chạm với header do proxy quản lý như Host, Connection, Content-Length hoặc Forwarded. Chọn tên riêng và ghi rõ trong API contract.

## 8. Session ID rotation và session fixation

Spring Security có thể thay session ID sau khi xác thực thành công để giảm nguy cơ session fixation. Khi resolver dùng header, client phải thay ID cũ bằng ID mới được phát trong response header. Nếu client tiếp tục gửi ID cũ, request tiếp theo có thể không còn truy cập được session.

Các test cần có:

- Tạo session trước authentication.
- Thực hiện login với cùng header session ID.
- Xác minh session ID được rotate theo policy.
- Xác minh response mang ID mới trong header.
- Gửi request kế tiếp với ID mới và xác minh authentication/session hoạt động.
- Gửi request với ID cũ và xác minh không khôi phục được session đã thay ID.

Không tắt session fixation protection chỉ để tránh cập nhật token phía client. Hãy cập nhật client để nhận và lưu session ID mới. Với response không có header mới, client giữ ID hiện tại; với response logout/expire, client xóa ID.

## 9. Logout và xóa header token ở client

Logout cần invalidate session ở server. Resolver có thể phát response header báo session ID không còn dùng được. Client phải xóa session ID khỏi bộ nhớ và không gửi lại trong request sau.

Ví dụ client-side pseudocode:

~~~javascript
let sessionId = null;

async function createSession() {
  const response = await fetch("/api/session", { method: "POST" });
  const issuedId = response.headers.get("X-Auth-Token");
  if (issuedId) {
    sessionId = issuedId;
  }
}

async function loadProfile() {
  const headers = sessionId ? { "X-Auth-Token": sessionId } : {};
  const response = await fetch("/api/profile", { headers });
  return response.json();
}

async function logout() {
  const headers = sessionId ? { "X-Auth-Token": sessionId } : {};
  await fetch("/logout", { method: "POST", headers });
  sessionId = null;
}
~~~

Đây là minh họa luồng; endpoint logout thực tế phải tuân thủ Spring Security và CSRF policy. Nếu response trả ID mới do rotation, client cập nhật ID. Nếu response expire/logout, client xóa ID. Cần xử lý lỗi mạng: server có thể đã invalidate nhưng response bị mất, vì vậy client không nên giả định token vẫn hợp lệ chỉ vì chưa nhận được response.

Logout từ một tab không tự xóa biến JavaScript trong tab khác. Nếu nhiều tab chia sẻ token qua BroadcastChannel hoặc storage event, cần đồng bộ việc xóa token và không để tab cũ tiếp tục gửi ID đã thu hồi. Server-side invalidation vẫn là nguồn chân lý.

## 10. CORS khi frontend và API khác origin

Khi frontend chạy ở origin khác API, request có custom header như X-Auth-Token thường kích hoạt CORS preflight OPTIONS. Server phải cho phép origin cụ thể, method cần thiết và header session đã chọn.

Frontend cũng cần đọc session ID từ response header. Trình duyệt không cho JavaScript đọc mọi response header cross-origin trừ khi server công bố header đó bằng Access-Control-Expose-Headers.

Ví dụ cấu hình Spring MVC CORS:

~~~java
@Bean
WebMvcConfigurer corsConfigurer() {
    return new WebMvcConfigurer() {
        @Override
        public void addCorsMappings(CorsRegistry registry) {
            registry.addMapping("/api/**")
                    .allowedOrigins("https://frontend.example.com")
                    .allowedMethods("GET", "POST", "PUT", "DELETE", "OPTIONS")
                    .allowedHeaders("Content-Type", "X-Auth-Token", "X-CSRF-TOKEN")
                    .exposedHeaders("X-Auth-Token")
                    .allowCredentials(false);
        }
    };
}
~~~

Đây là ví dụ cho header-based session không dùng cookie. Nếu ứng dụng đồng thời dùng cookie hoặc credential browser-managed khác, chính sách allowCredentials và CORS phải được thiết kế lại; không dùng wildcard origin cùng credential mode. Khi dùng Spring Security, bảo đảm CORS được xử lý phù hợp trước authorization/CSRF và preflight không bị yêu cầu authentication.

Custom header không tự miễn CSRF. Browser thường không tự thêm X-Auth-Token vào request cross-site nếu frontend không có quyền gửi header; preflight và CORS giúp giới hạn việc đó. Nhưng XSS trong frontend origin hoặc CORS misconfiguration có thể cho phép mã độc đọc/đánh cắp session ID. Giữ CSRF protection cho endpoint thay đổi trạng thái theo threat model; không tắt CSRF chỉ vì session ID nằm trong header.

## 11. Bảo vệ session ID trong client

Khác cookie HttpOnly, session ID trong custom header thường phải được JavaScript đọc và tự gửi lại. Vì vậy, script chạy được trong origin frontend có thể có khả năng đọc ID từ response header hoặc biến lưu trữ. Header-based session không tự động có lợi thế chống XSS như cookie HttpOnly.

Các nguyên tắc:

- Chỉ truyền session ID qua HTTPS.
- Không đưa ID vào URL, query string, fragment, HTML, analytics hoặc error tracking.
- Không log request/response header chứa ID tại application, reverse proxy, API gateway hoặc APM.
- Ưu tiên giữ ID trong memory nếu UX cho phép; tránh lưu lâu trong localStorage nếu không có threat model rõ ràng.
- Áp dụng CSP, output encoding và dependency hygiene để giảm nguy cơ XSS.
- Giới hạn TTL, rotate ID sau authentication và invalidate khi logout.
- Không dùng cùng session ID cho nhiều ứng dụng có trust boundary khác nhau.

Nếu cần giữ trạng thái đăng nhập qua reload/browser restart, phải cân nhắc cách lưu credential an toàn và rủi ro XSS. Không có lựa chọn storage phía client nào làm bearer token an toàn tuyệt đối trước script độc hại chạy cùng origin. Với browser application truyền thống, cookie HttpOnly có thể phù hợp hơn; header resolver thường hữu ích cho client có khả năng quản lý credential rõ ràng như mobile/native client hoặc service client.

## 12. Proxy, gateway và giới hạn header

Header session ID phải được chuyển nguyên vẹn từ client tới Servlet container. Reverse proxy, API gateway, WAF hoặc ingress có thể:

- Chặn header chưa được allowlist.
- Đổi tên hoặc xóa header.
- Giới hạn tổng kích thước header.
- Ghi header vào access log.
- Chuyển request tới upstream có resolver không tương thích.

Kiểm tra cấu hình proxy để cho phép đúng header đã chọn và redaction giá trị trong log. Không tăng giới hạn header toàn hệ thống quá mức chỉ để chấp nhận token bất thường; session ID nên có độ dài hợp lý theo resolver/implementation.

Nếu API gateway tự xác thực token rồi chuyển tiếp identity header tới ứng dụng, không dùng nhầm identity header đó làm session ID. Phân biệt rõ header mang session ID với header mang principal/claims. Chỉ tin header identity do gateway đáng tin cậy xóa giá trị client gửi trước đó và tự ghi lại.

## 13. Kiểm thử các trường hợp lỗi

| Trường hợp | Kết quả cần xác minh |
| --- | --- |
| Không có session header | Không khôi phục session cũ |
| Header rỗng | Không khôi phục session |
| Header có ID không tồn tại | Session miss; request theo authentication policy |
| Chỉ có cookie, không có header | Header-only resolver không khôi phục session từ cookie |
| Header đúng nhưng proxy bỏ header | Request không có session; log/metric giúp xác định proxy path |
| Header name sai | Không khôi phục session |
| Session đã hết hạn | ID cũ không khôi phục được session |
| Logout | Repository invalidate; client xóa ID |
| Session ID rotation | Client thay bằng ID mới trong response header |
| CORS preflight | OPTIONS và header được allow/expose đúng |
| Thiếu expose header | Browser JS không đọc được ID |
| Redis/JDBC unavailable | Lỗi repository được phân biệt với ID không tồn tại |
| Header bị log | Redaction test phát hiện và ngăn lộ credential |

Đừng chỉ test resolveSessionIds() rồi kết luận đường đi HTTP hoàn chỉnh. Cần integration test có SessionRepositoryFilter, repository thật hoặc Testcontainers, và request kế tiếp gửi header đã nhận. Nếu frontend chạy cross-origin, bổ sung browser test để xác minh CORS expose header.

## 14. Phân biệt header session với Authorization bearer token

X-Auth-Token trong cấu hình HeaderHttpSessionIdResolver là session ID. Nó giúp repository tìm session. Nó không mặc nhiên là OAuth access token, JWT hoặc credential do resource server xác minh chữ ký.

| Header credential | Ý nghĩa |
| --- | --- |
| X-Auth-Token do HeaderHttpSessionIdResolver dùng | Định danh session stateful trong Spring Session repository |
| Authorization: Bearer JWT | Access token được resource server xác minh theo issuer, audience, signature/claims và policy |
| X-User-Id do proxy gửi | Identity metadata; chỉ tin khi proxy đáng tin cậy kiểm soát và ghi lại |

Không đổi tên session ID thành Authorization: Bearer rồi coi nó tự động tương thích OAuth. Nếu muốn Spring Security xác thực JWT, cấu hình resource server và bearer token authentication riêng. Nếu dùng session-based security, Spring Security khôi phục SecurityContext từ session theo repository.

## 15. Lưu ý khi dùng nhiều ứng dụng hoặc nhiều node

Header resolver không thay đổi cách session được lưu. Nhiều node của cùng ứng dụng vẫn cần repository dùng chung. Nếu client gửi cùng session ID tới node A rồi node B, cả hai node phải dùng cùng Redis namespace hoặc JDBC schema/table và serializer tương thích.

Nếu hai ứng dụng độc lập cùng dùng header X-Auth-Token nhưng repository riêng, cùng một giá trị có thể chỉ hợp lệ ở một ứng dụng. Không chia sẻ session ID giữa ứng dụng chỉ vì header name giống nhau. Chia sẻ chủ động cần cùng repository contract, namespace/schema, header policy, serializer và trust boundary.

Nếu ứng dụng A và B dùng session timeout hoặc logout policy khác nhau, một bên có thể invalidate session mà bên kia vẫn kỳ vọng còn hiệu lực. Xác định rõ logout có tác động toàn hệ thống hay chỉ trong một ứng dụng; nếu cần SSO giữa các ứng dụng độc lập, cân nhắc OpenID Connect thay cho chia sẻ trực tiếp session.

## 16. Checklist kiểm thử và triển khai

- [ ] Có đúng một HttpSessionIdResolver được sử dụng bởi SessionRepositoryFilter.
- [ ] Resolver được cấu hình là HeaderHttpSessionIdResolver với header name thống nhất.
- [ ] Request tạo session không cần cookie và response phát session ID qua header.
- [ ] Client giữ ID và gửi lại header trong request tiếp theo.
- [ ] Request không có header không thể khôi phục session chỉ nhờ cookie.
- [ ] ID không tồn tại/hết hạn được xử lý như không có phiên; datastore error không bị biến thành miss.
- [ ] Session ID rotation phát ID mới và client cập nhật giá trị.
- [ ] Logout invalidate repository session và client xóa ID.
- [ ] CORS allow header và expose response header đúng origin.
- [ ] CSRF policy vẫn phù hợp với browser threat model.
- [ ] HTTPS, XSS protection, log redaction và header size được kiểm tra.
- [ ] Integration test đi qua filter/repository; browser test xác minh CORS nếu có.
- [ ] Nhiều node dùng chung repository nếu cùng session ID phải được chuyển giữa node.

## 17. Kết luận

HeaderHttpSessionIdResolver cho phép Spring Session nhận session ID từ HTTP header và phát ID qua response header, giúp xây dựng đường đi không dùng cookie. Để kiểm thử đúng, cần tạo session ở request đầu, đọc ID từ header, gửi lại ID trong request tiếp theo và xác minh repository khôi phục đúng attributes mà không có cookie. Cần kiểm tra thêm ID không tồn tại, hết hạn, logout, session fixation rotation, CORS và proxy.

Header-based session vẫn là stateful session và session ID vẫn là bearer credential. Vì JavaScript hoặc client phải giữ và gửi lại ID, cần bảo vệ nó khỏi XSS, log leakage và truyền tải không mã hóa. Chỉ dùng đường đi này khi client thực sự cần quản lý header; giữ repository, resolver, CORS và lifecycle thống nhất để tránh ứng dụng vô tình chấp nhận cả cookie lẫn header theo các quy tắc khác nhau.
