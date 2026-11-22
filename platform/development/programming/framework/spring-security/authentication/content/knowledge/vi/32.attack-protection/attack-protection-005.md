# HTTPS, cookie an toàn và bảo vệ trước đánh cắp phiên trong Spring Security

## 1. Mục tiêu và mô hình đe dọa

Đối với ứng dụng web có đăng nhập, **session hijacking** là việc kẻ tấn công chiếm quyền sử dụng phiên của một người dùng khác, thường vì biết được, cố định, đánh cắp hoặc lạm dụng **session identifier**. Khi server coi một cookie phiên là bằng chứng cho tài khoản đã xác thực, người nắm giữ cookie hợp lệ có thể gửi request dưới danh nghĩa người dùng nếu không có lớp bảo vệ bổ sung.

Ba lớp bảo vệ cần được thiết kế cùng nhau:

1. **HTTPS/TLS trên toàn vòng đời**: tránh lộ hoặc bị sửa cookie, thông tin đăng nhập và nội dung trao đổi trên đường truyền.
2. **Cookie/session policy đúng**: bí mật phiên được sinh an toàn, lưu trữ phía server, giới hạn cookie với `Secure`, `HttpOnly`, `SameSite`, `Path`, host-only domain và TTL; xoay session ID sau xác thực; hủy phiên khi logout/thu hồi.
3. **Phòng thủ chống sử dụng trái phép một phiên đã có**: ngăn XSS và CSRF, kiểm tra authorization, xác thực bổ sung cho hành động nhạy cảm, phát hiện bất thường và vô hiệu hóa phiên khi nghi bị chiếm đoạt.

Không một cơ chế đơn lẻ nào giải quyết hết: HTTPS không sửa lỗi XSS; `HttpOnly` không ngăn JavaScript độc hại gửi các request cùng origin; `SameSite` không thay CSRF token; việc đổi session ID lúc login không vô hiệu một **phiên mới** đã bị đánh cắp.

### Những tình huống tấn công điển hình

| Tình huống | Điều kẻ tấn công có | Lớp bảo vệ chính |
| --- | --- | --- |
| Đọc cookie trên kết nối HTTP không mã hóa | Quyền quan sát/chen giữa luồng mạng | HTTPS mọi request + `Secure` + HSTS |
| **Session fixation** | Session ID biết trước khi nạn nhân đăng nhập | Đổi session ID sau login, không chấp nhận ID do client tự cấp |
| **Session hijacking** qua log hoặc malware | Session ID hợp lệ của người dùng | Redact logs, kiểm soát endpoint, TTL, revoke, monitoring, MFA cho thao tác nhạy cảm |
| **XSS** | JavaScript chạy trong origin ứng dụng | Output encoding, sanitization, CSP, tránh HTML nguy hiểm; `HttpOnly` giảm lộ cookie trực tiếp |
| **CSRF** | Ép trình duyệt đã login gửi request ngoài ý muốn | CSRF token, SameSite phù hợp, Origin/Fetch Metadata khi áp dụng |
| **Subdomain cookie injection** | Điều khiển một host phụ | Cookie host-only, prefix `__Host-`, không đặt `Domain` quá rộng |
| Session quá lâu hoặc vẫn tồn tại sau thu hồi quyền | Cookie cũ còn hiệu lực | Idle + absolute timeout, session invalidation, revalidation |
| Proxy/header spoofing | Có thể gửi `X-Forwarded-*` tự khai | Trusted proxy boundary, loại bỏ/ghi đè inbound forwarded headers |

Ở đây trọng tâm là **Spring Security authentication trong ứng dụng Servlet/Spring MVC** với `HttpSession`. Phần cuối phân biệt với WebFlux, bearer JWT và kiến trúc SPA.

## 2. Phiên đăng nhập thực tế nằm ở đâu?

Trong ứng dụng session-based thông dụng:

```text
Browser                                         Spring MVC + Spring Security
  |                                                |
  | POST /login --username/password + CSRF token-> |
  |                                                | AuthenticationManager
  |                                                | xác thực credentials
  |                                                | SecurityContext + Authentication
  |                                                | HttpSession được cấp/đổi ID
  | <- Set-Cookie: __Host-SESSION=<random>; ... ----|
  |                                                |
  | GET /account                                    |
  | Cookie: __Host-SESSION=<random>                  |
  | ----------------------------------------------> |
  |                                                | container nhận diện HttpSession
  |                                                | SecurityContextRepository nạp context
  |                                                | AuthorizationFilter kiểm tra quyền
  | <---------------------------------------------- |
```

**Cookie phiên thường chỉ là một mã tham chiếu ngẫu nhiên**. `Authentication`, `GrantedAuthority` và các thuộc tính phiên nằm phía server, trong bộ nhớ container hoặc một session store được chia sẻ. Với Spring Security Servlet, `HttpSessionSecurityContextRepository` là một implementation dùng `HttpSession` để lưu/nạp `SecurityContext`; nó không có nghĩa toàn bộ dữ liệu xác thực được nhét thẳng vào cookie.

Tùy cấu hình, app có thể dùng tên cookie `JSESSIONID` hoặc tên khác; việc thay tên cookie **không thay thế** bảo mật thực sự. Spring Security cũng hỗ trợ chế độ stateless hoặc xác thực bằng bearer token, nơi mô hình lưu session có thể khác.

### Ranh giới trách nhiệm

- **TLS terminator / reverse proxy / load balancer**: chứng thư TLS, HTTPS redirect/HSTS, quản lý các header tin cậy, giới hạn giao thức/cipher và bảo vệ kênh kết nối.
- **Servlet container hoặc Spring Session**: tạo ID, lưu session, Set-Cookie, xử lý timeout/invalidate.
- **Spring Security**: xác thực, chống session fixation, `SecurityContext`, CSRF, logout, authorization và security headers.
- **Ứng dụng**: quản lý quyền theo dữ liệu nghiệp vụ, absolute session lifetime nếu cần, thu hồi phiên theo sự kiện, MFA/step-up và xử lý sự cố.

Nếu dự án dùng SSO/OIDC, **IdP session** và **local app session** là hai đối tượng khác nhau; cookie SSO của IdP không phải cookie phiên của Spring MVC.

## 3. HTTPS/TLS bắt buộc trên toàn phiên, không chỉ trang đăng nhập

Một số hệ thống chỉ dùng HTTPS cho `/login`, nhưng lại tải `/account` hoặc tài nguyên khác qua HTTP. Khi đó cookie có thể lộ hoặc request có thể bị sửa trên mạng, bất kể mật khẩu đã được gửi qua TLS.

### Yêu cầu về giao vận

1. Chỉ phục vụ các trang và API có phiên đăng nhập qua **HTTPS** với chứng thư đáng tin, đúng hostname và còn hiệu lực. Ưu tiên TLS 1.3, giữ TLS 1.2 khi cần và được cấu hình an toàn; vô hiệu giao thức/cipher lỗi thời.
2. Redirect HTTP sang HTTPS **trước khi cấp cookie xác thực**; không tạo session có giá trị bảo mật trên HTTP.
3. Dùng `Secure` trên mọi cookie xác thực; trình duyệt tuân thủ thuộc tính này không gửi cookie đó trong request HTTP không bảo mật.
4. Sử dụng **HTTP Strict Transport Security (HSTS)** để các browser đã nhận chính sách ghi nhớ host phải dùng HTTPS. HSTS không bảo vệ lần truy cập đầu tiên nếu chưa có chính sách hoặc preload; `Secure` vẫn cần.
5. Tránh mixed content và tài nguyên script từ HTTP. Một script không đáng tin chạy trong origin HTTPS có thể làm mất ý nghĩa của việc bảo vệ đường truyền.
6. Kiểm soát TLS ở các chặng giữa load balancer, ingress, proxy và application server; nếu backend đi qua mạng không tin cậy, cần mã hóa/kênh private tương ứng. Đừng mặc định TLS termination ở edge bảo vệ cả mạng nội bộ.

### HSTS là gì?

Server gửi response header, ví dụ:

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

Browser hỗ trợ HSTS sẽ nhớ chính sách cho host trong thời gian `max-age` kể từ khi nhận qua HTTPS hợp lệ. `includeSubDomains` chỉ nên bật khi **mọi subdomain cần nằm trong phạm vi** đều sẵn sàng HTTPS; dùng `preload`/đăng ký preload khi đã cân nhắc hậu quả dài hạn và có kế hoạch rollback.

**Spring Security Servlet 6.x mặc định cung cấp HSTS header cho HTTPS request** trong cấu hình security headers mặc định; nếu proxy kết thúc TLS và app nhìn thấy request HTTP, phải xác minh header cuối cùng do edge hoặc Spring Security thực sự gửi. Không chỉ nhìn file cấu hình mà kết luận HSTS đang hoạt động.

### Ví dụ kiểm tra tại biên HTTPS

```bash
curl -I https://app.example.org/login
curl -I http://app.example.org/login
```

Với HTTPS response, kiểm tra `Strict-Transport-Security` (nếu policy áp dụng), redirect/cookie/cache headers. Với HTTP, mong muốn redirect sang HTTPS, **không phát cookie phiên xác thực** trước redirect. `curl` không áp dụng chính sách HSTS giống một browser đã lưu HSTS; kiểm tra hành vi browser riêng.

## 4. Các thuộc tính cookie bảo mật

Ví dụ một **session cookie host-only**:

```http
Set-Cookie: __Host-SESSION=<random-unpredictable-id>; Path=/; Secure; HttpOnly; SameSite=Lax
```

`<random-unpredictable-id>` là ký hiệu minh họa, **không phải cookie value**. Không ghi raw session ID vào log hoặc ví dụ public.

| Thuộc tính | Ý nghĩa đúng | Điều nó không bảo đảm |
| --- | --- | --- |
| `Secure` | Browser chỉ gửi cookie theo kênh HTTPS phù hợp | Không chống XSS, CSRF, malware hay server compromise |
| `HttpOnly` | JavaScript không đọc/sửa trực tiếp cookie qua `document.cookie` | XSS vẫn có thể chạy các request cùng origin, dùng cookie tự động |
| `SameSite=Strict` | Hạn chế gửi cookie trong các request cross-site | Có thể làm hỏng một số flow SSO/navigation; không bảo vệ mọi cross-origin same-site |
| `SameSite=Lax` | Cho phép cookie ở top-level navigation cross-site bằng phương thức safe, hạn chế nhiều POST cross-site | Không ngăn mọi CSRF (đặc biệt GET có side effect, same-site subdomains và browser nuances) |
| `SameSite=None` | Cho phép cross-site cookie theo chính sách browser | **Phải kèm Secure**, có thể chịu chặn third-party cookies |
| `Path=/` | Chỉ dẫn phạm vi URL path mà browser gửi cookie | **Không phải** ranh giới cô lập bảo mật giữa ứng dụng |
| Không có `Domain` | Host-only cookie; giới hạn host đã phát cookie | Host vẫn cần được bảo vệ; không cản XSS trên chính host đó |
| `Domain=example.org` | Chia cookie cho domain và các subdomain tương ứng | Mở rộng bề mặt tấn công nếu sibling subdomain bị chiếm |
| `Max-Age` / `Expires` | Quy định browser giữ cookie bao lâu | Không thay server-side session timeout/revocation |
| Tên có prefix `__Host-` | Browser hỗ trợ bắt buộc `Secure`, `Path=/` và **không có Domain** | Không chứng minh nội dung cookie an toàn hoặc user thật |

**Khuyến nghị mặc định cho cookie phiên truyền thống:** host-only, `Secure`, `HttpOnly`, `SameSite=Lax` hoặc `Strict` tùy sản phẩm, hạn chế domain/path và không đặt Max-Age lâu không cần thiết. Với các flow nhúng iframe hoặc cross-site POST/OIDC `form_post`, phân tích kỹ trước khi chọn `SameSite=None`; không bỏ qua `state`, `nonce` và CSRF chỉ để giải quyết lỗi cookie.

### Cookie prefix và host-only

Tên `__Host-SESSION` bắt buộc phù hợp các điều kiện ở browser hỗ trợ prefix:

- Cookie được gửi từ một secure origin qua HTTPS và có thuộc tính `Secure`.
- `Path=/` là bắt buộc.
- **Không có `Domain`**; host phát cookie mới có thể kiểm soát cookie host-only đó.

Đối với ứng dụng chạy dưới servlet context path như `/portal`, hãy kiểm tra cách container đặt `Path`. Nếu cookie không có `Path=/`, dùng prefix `__Host-` sẽ bị browser từ chối. Không cố dùng prefix đẹp mắt nhưng sai điều kiện.

`__Secure-` chỉ yêu cầu `Secure`, không bảo đảm host-only hay `Path=/` như `__Host-`. Mọi cookie prefix đều cần được kiểm tra trong Network/Storage devtools của browser mục tiêu.

### Cookie và phiên là hai vòng đời khác nhau

`server.servlet.session.timeout: 20m` chủ yếu đặt **idle session timeout** phía Servlet container. Cookie phiên có thể còn trong browser sau khi server đã xóa session, và ngược lại cookie bị browser xóa không đảm bảo dữ liệu session phía server đã hết hạn.

- **Server-side timeout** quyết định cookie ID có còn truy xuất được `HttpSession` hợp lệ không.
- **Cookie Max-Age/Expires** quyết định browser giữ ID bao lâu; tùy browser có cơ chế restore session.
- **Absolute timeout** (ví dụ tối đa 8 giờ dù đang hoạt động) thường cần cơ chế ứng dụng/store bổ sung nếu policy yêu cầu; không mặc nhiên có chỉ vì cấu hình idle timeout.
- Khi logout, server phải vô hiệu hóa session; chỉ xóa cookie ở browser **không đủ** để ngăn dùng lại một session ID bị sao chép trước đó.

## 5. Cấu hình Spring Boot 3.x cho session cookie (Servlet)

Đây là cấu hình **Spring Boot 3.x / Spring MVC / Servlet**, Java 17+, với session-cookie name `__Host-SESSION`. Trong `src/main/resources/application.yml`:

```yaml
server:
  servlet:
    session:
      timeout: 20m
      tracking-modes: cookie
      cookie:
        name: "__Host-SESSION"
        secure: true
        http-only: true
        same-site: lax
        path: /

# Chỉ dùng khi triển khai sau proxy ĐƯỢC TIN CẬY:
# server:
#   forward-headers-strategy: framework
```

Giải thích:

- `secure: true` giúp phát thuộc tính `Secure` **kể cả** khi app sau proxy nhận kết nối backend HTTP; HTTPS ở phía client vẫn phải được kiểm tra tại edge.
- `http-only: true` ngăn JS đọc cookie phiên. Không nhầm với một CSRF token cookie đôi khi **cần được đọc bởi JavaScript** trong SPA.
- `same-site: lax` là chính sách thực dụng cho nhiều ứng dụng web và top-level redirect đăng nhập. `Strict` có thể phù hợp hơn nếu UX/SSO chấp nhận; đánh giá cross-site callback thực tế.
- `path: /` và **không cấu hình `cookie.domain`** để prefix `__Host-` hợp lệ. Đảm bảo container/proxy không tự thêm Domain/đổi Path.
- `tracking-modes: cookie` giúp ngăn cơ chế theo dõi session qua URL rewriting; xác minh container và link generation không chèn `;jsessionid=...`.
- `timeout: 20m` chỉ là ví dụ idle timeout, phải theo security policy và nhu cầu sản phẩm.
- Không dùng `cookie.max-age: 30d` rồi tưởng đã an toàn; cookie thường nên thuộc vòng đời browser session, còn server phải tự hết hạn/thu hồi.

### Nếu dùng proxy/ingress kết thúc TLS

`server.forward-headers-strategy: framework` giúp Spring Boot hiểu scheme, host, port từ các forwarded headers trong các môi trường phù hợp. **Chỉ bật khi reverse proxy đáng tin đã xóa/ghi đè giá trị `Forwarded` và `X-Forwarded-*` đến từ client không tin cậy**. Nếu không, kẻ tấn công có thể giả host/scheme để tác động redirect URL, absolute link hoặc logic kiểm tra bảo mật.

Cần phân biệt:

1. Trình duyệt ↔ ingress dùng HTTPS có chứng thư hợp lệ.
2. Ingress ↔ backend đi qua private network hoặc HTTPS nếu trust boundary đòi hỏi.
3. Backend xác định request gốc qua forwarded headers **được kiểm soát**.
4. Response ngoài cùng được browser nhận thực sự có cookie `Secure` và HSTS phù hợp.
5. Không xuất trực tiếp cổng backend ra Internet nếu nó dự kiến chỉ được ingress gọi.

**Không hard-code** mọi yêu cầu đang bảo mật chỉ từ việc nhận `X-Forwarded-Proto: https` từ bất kỳ nguồn nào. Không dùng `server.forward-headers-strategy` như một phép thay thế TLS.

## 6. Spring Security 6.5 Servlet: xác thực, session fixation và logout

Dưới đây là **một class cấu hình dùng được trong ứng dụng Spring Boot MVC** khi đã có `spring-boot-starter-web` và `spring-boot-starter-security`. Cần cung cấp nguồn user/credentials đúng ứng dụng; `formLogin` mặc định được bật để minh họa đường browser login.

File `src/main/java/demo/security/WebSecurityConfig.java`:

```java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .sessionManagement(session -> session
                        .sessionFixation(fixation -> fixation
                                .changeSessionId()))
                .logout(logout -> logout
                        .invalidateHttpSession(true)
                        .clearAuthentication(true))
                .build();
    }
}
```

Đoạn cấu hình này:

- Buộc xác thực ở tất cả đường ngoài `/public/**`; không có nghĩa đã có authorization theo quyền sở hữu tài nguyên.
- Dùng `changeSessionId()` để **đổi ID khi xác thực thành công**, tránh nạn nhân login bằng session ID đã bị tấn công cố định.
- Giữ **CSRF protection mặc định** cho browser form/session; không gọi `csrf.disable()` một cách tùy tiện.
- Hỗ trợ logout: invalidates HTTP session và clears authentication; Spring Security mặc định có xử lý logout phù hợp. Với CSRF bật, thao tác logout thông thường là `POST /logout` kèm CSRF token.
- Không phải cấu hình thay thế phần cookie ở `application.yml`; framework security và container cookie có trách nhiệm bổ sung cho nhau.

**Quan trọng về phiên bản:** ví dụ nhắm Spring Boot 3.x / Spring Security 6.5 Servlet. Với Spring Security 7.x / Boot 4.x hoặc ứng dụng WebFlux, đọc tài liệu đúng version và kiểm thử tương thích trước khi dùng.

### Khi nào cấu hình trên chưa đủ?

- Chưa định nghĩa DB user/credential hashing, password policy, MFA, rate limiting hoặc forgot-password.
- Chưa đặt absolute TTL, multi-device session management, session store phân tán.
- Chưa có policy logout tất cả thiết bị sau reset password hoặc thu hồi tài khoản.
- Chưa bảo vệ XSS trong nội dung HTML động của ứng dụng.
- Chưa bảo đảm ingress/HSTS/TLS backend và CSP đúng với trang thực tế.
- Chưa xử lý các thành phần bên ngoài như remember-me, OAuth2 authorized client/refresh token hoặc WebSocket session.

Không dựa vào một `SecurityFilterChain` minh họa để tuyên bố ứng dụng đã “chống hijacking hoàn toàn”.

## 7. Session fixation: vì sao cần xoay ID sau login?

**Session fixation** khác với hijacking sau đăng nhập. Trong fixation, attacker biết hoặc ép trình duyệt dùng một ID **trước** khi victim login. Nếu server tiếp tục dùng ID ấy sau khi xác thực, attacker có thể sử dụng lại ID đã biết.

```text
Trước login
  Attacker biết session ID = old-id
  Victim gửi old-id vào ứng dụng (vì lỗi fixation)
                       |
                       v
Victim login thành công
                       |
       [Không đổi ID]  |  [Đổi ID đúng]
            |          |        |
 old-id trở thành      |  new-id được tạo ngẫu nhiên
 authenticated         |  old-id không còn hợp lệ
            |          |        |
 Attacker truy cập     |  Attacker có old-id không
 bằng old-id           |  truy cập được session mới
```

Spring Security Servlet trên các container Servlet hiện đại **mặc định chống session fixation bằng `changeSessionId()`** khi xác thực thành công. Có các chiến lược:

| Chiến lược | Hành vi | Lưu ý |
| --- | --- | --- |
| `changeSessionId` | Đổi ID của session hiện có thông qua Servlet API | Mặc định trên Servlet 3.1+; thường phù hợp |
| `newSession` | Tạo phiên mới sạch, giữ lại một số dữ liệu liên quan Spring Security | Có thể mất state không có trong whitelist |
| `migrateSession` | Tạo phiên mới và sao chép thuộc tính từ phiên cũ | Cẩn trọng với thuộc tính không tin cậy hoặc quá lâu |
| `none` | Tắt chống session fixation | **Không nên dùng** |

Việc đổi ID **khi login** chỉ phòng fixation tại ranh giới xác thực. Nếu attacker đã lấy được **ID mới hiện tại** qua XSS, logs, malware hoặc endpoint không bảo vệ, họ vẫn có thể sử dụng ID đó. Vì vậy cần kết hợp các lớp bảo vệ khác.

### Không tự viết lại rotation yếu hơn framework

Không nên triển khai một cookie `sid` tùy chỉnh rồi giữ ID cũ còn hợp lệ sau login, hoặc “rotate” chỉ bằng cách đổi tên cookie. Nếu buộc tự xây session store, phải thu hồi mapping ID cũ trên server và kiểm chứng ID mới được sinh bằng CSPRNG. Với Spring Security, ưu tiên dùng session-fixation protection của framework/container đã kiểm thử.

Đối với **step-up** hoặc chuyển sang quyền quản trị, chính sách có thể yêu cầu rotation/re-authentication bổ sung, nhất là nếu security context có cấp độ đảm bảo khác. Cần làm rõ hệ thống đang dùng session của browser, JWT bearer, SSO hay API key để áp dụng đúng nơi.

## 8. Session hijacking: các nguồn lộ session ID cần chặn

### 8.1. Mạng và proxy

- Không cho client gửi cookie xác thực qua HTTP; dùng HTTPS, `Secure` và HSTS.
- Không cấu hình load balancer/edge log toàn bộ request headers trong đó có `Cookie` hoặc `Authorization`.
- Không phản chiếu cookie/token vào `Location`, URL query, HTML/JS error page, hoặc crash report.
- Không nhúng session ID vào path/query: `/profile;jsessionid=...`, `?sid=...` dễ xuất hiện trong browser history, Referer, proxy/CDN logs.
- Không đặt session secret làm header gửi tới third-party analytics hoặc monitoring SaaS.

### 8.2. XSS và client-side scripts

`HttpOnly` ngăn `document.cookie` đọc cookie phiên trong browser hỗ trợ, nhưng **không chặn script XSS chạy cùng origin gửi request được browser tự gắn cookie**. Ví dụ attacker có JavaScript trên trang user thì có thể thử gọi các endpoint nghiệp vụ thay vì đánh cắp giá trị cookie.

Cần áp dụng:

- Encode output đúng HTML/attribute/JS/URL context; không nối chuỗi dữ liệu user vào `innerHTML` khi không có sanitization đúng.
- Hạn chế các API DOM nguy hiểm, đánh giá template engine và thư viện markdown/HTML viewer.
- Thiết lập **Content Security Policy (CSP)** có giá trị thực, ví dụ chính sách nonce/hash và tránh `unsafe-inline` tùy dự án. CSP là phòng thủ bổ sung, **không thay output encoding**.
- Duy trì dependency hygiene, review third-party scripts, SRI khi thích hợp và hạn chế nguồn JavaScript.
- Tránh đọc bearer token hoặc session ID qua localStorage/sessionStorage trong các ứng dụng không cần JS giữ chúng.
- Đối với thao tác rủi ro cao, kiểm tra quyền hiện tại và step-up MFA/transaction confirmation, vì cookie HttpOnly vẫn được browser gửi tự động.

### 8.3. Browser extensions và thiết bị bị xâm nhập

Cookie flags không ngăn một attacker đã chiếm máy hoặc có quyền đọc browser profile lấy dữ liệu phiên. Rủi ro cũng có ở shared computers, extension độc hại và backup/profile sync không an toàn. Biện pháp ở đây là hạn chế TTL, revocation, giám sát, đăng xuất thiết bị và MFA cho hành động quan trọng, chứ không phải chỉ đặt thêm một cookie attribute.

## 9. CSRF: SameSite không thay CSRF token

**Cross-Site Request Forgery (CSRF)** xảy ra khi trang do attacker kiểm soát khiến browser của nạn nhân gửi request dùng cookie phiên hợp lệ đến ứng dụng. Cookie `Secure`, `HttpOnly` không ngăn browser tự gắn cookie.

### Vì sao SameSite chỉ là lớp bổ sung?

- `SameSite=Lax` vẫn cho cookie trong nhiều **top-level cross-site GET**. Endpoint GET **không được có side effect** như đổi email hoặc thanh toán.
- Các subdomain thuộc cùng site có thể được xem là **same-site** dù khác **origin**; một subdomain bị chiếm có thể tạo request mà SameSite không chặn như mong muốn.
- Browser policy và OAuth/OIDC callback có sự khác biệt; không phụ thuộc vào mọi browser cư xử hoàn toàn giống nhau.
- `SameSite=None; Secure` thường cần cho một số kịch bản cross-site, càng phải giữ CSRF/state/nonce.

Với **Spring Security Servlet**, CSRF mặc định bật cho browser/session. Các thao tác thay đổi trạng thái (POST/PUT/PATCH/DELETE) phải gửi token CSRF đúng, bao gồm login/logout nếu flow có yêu cầu. Không dùng `GET` cho mutation.

### Form logout đúng hướng

Ví dụ fragment trong một HTML server-rendered template đã có model CSRF của Spring Security:

```html
<form method="post" action="/logout">
  <input type="hidden" name="_csrf" value="...CSRF_TOKEN_FROM_SERVER...">
  <button type="submit">Đăng xuất</button>
</form>
```

`...CSRF_TOKEN_FROM_SERVER...` chỉ là **placeholder minh họa**; template engine/thư viện Spring Security phải inject giá trị CSRF thật, không hard-code. Nếu dùng Thymeleaf tích hợp Spring Security, framework có thể tạo hidden input phù hợp theo cấu hình.

Trong Spring Security 6.5, `GET /logout` mặc định thường hiển thị trang xác nhận; `POST /logout` xử lý logout khi CSRF được bật. Đừng tạo endpoint `GET /logout-all` thực hiện thay đổi trạng thái mà bỏ CSRF và re-authentication.

### SPA và CookieCsrfTokenRepository

Trong SPA gửi request same-origin với session cookie HttpOnly, một mô hình phổ biến là browser đọc **CSRF token** từ cookie hoặc endpoint được bảo vệ, rồi gửi qua header riêng.

```java
// Mảnh cấu hình Servlet Spring Security; không phải class độc lập.
http.csrf(csrf -> csrf
        .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse()));
```

Thư viện Spring Security có xử lý token theo version, bao gồm deferred token loading, XOR/BREACH handling và luồng refresh sau login/logout; khi cấu hình SPA với `CookieCsrfTokenRepository` cần xem hướng dẫn SPA CSRF cùng phiên bản. **`withHttpOnlyFalse()` chỉ áp dụng cho cookie chứa CSRF token** để JavaScript đọc được nếu app cần; **không được đổi `HttpOnly` của session cookie thành false**.

Với API thuần bearer token lưu ngoài browser cookie và không tự gắn credentials, threat model CSRF có thể khác. Đừng copy kết luận “CSRF không cần” sang ứng dụng dùng session cookie chỉ vì frontend gọi API JSON.

### CORS không phải CSRF defense

CORS chủ yếu quyết định JavaScript tại origin khác có được đọc response hoặc gửi một số request qua preflight hay không; nó **không thay thế CSRF token** đối với request tự động gắn cookie. Với `Access-Control-Allow-Credentials: true`, tuyệt đối không cấp wildcard origin bừa bãi, nhất là cho endpoint nhạy cảm. Tính năng nhiều frontend phải có allowlist origin cụ thể và kiểm thử chính xác cookie SameSite.

## 10. Logout, timeout và thu hồi phiên

Có ba sự kiện không đồng nghĩa:

1. Browser **xóa cookie**.
2. Server **invalidates session**.
3. Identity Provider **kết thúc SSO session** nếu đăng nhập qua OIDC/SAML.

Đối với logout tại ứng dụng MVC:

```text
POST /logout + CSRF token
    -> LogoutFilter
    -> SecurityContextLogoutHandler
       + clear SecurityContext
       + invalidate HttpSession
    -> xóa/thay đổi CSRF/remember-me data theo các handlers
    -> response /login?logout hoặc success handler được cấu hình
```

Spring Security 6.5 có cơ chế logout mặc định làm sạch authentication, context và invalidates session. `logout.deleteCookies(...)` hoặc `Clear-Site-Data` có thể hỗ trợ xóa cookie phía browser, nhưng **không được xem thao tác xóa cookie là thay thế invalidate phía server**. Khi cookie name, Path, Domain khác nhau, một lệnh xóa cookie có thể không khớp nên phải test trên container thật.

### Chọn TTL và cơ chế thu hồi

| Cơ chế | Chống được gì | Hạn chế |
| --- | --- | --- |
| **Idle timeout** | Phiên không dùng một thời gian sẽ hết hạn | Attacker đang chủ động sử dụng có thể giữ session sống nếu không có absolute TTL |
| **Absolute timeout** | Chặn phiên dùng vô hạn dù có hoạt động | User có thể phải login/reauthenticate lại; cần lưu createdAt riêng |
| **Session ID rotation** | Chống fixation và giảm hiệu lực một số ID cũ | Không ngăn attacker dùng ID **hiện tại** đã bị đánh cắp |
| **Invalidate khi logout** | Từ chối ID cũ phía server | Session khác trên thiết bị khác vẫn còn nếu không revoke chúng |
| **Revoke theo sự kiện** | Đổi mật khẩu, disable account, phát hiện compromise | Cần session registry/index by account và propagation giữa node |
| **Step-up MFA** | Tăng assurance cho hành động nhạy cảm | Không tự vô hiệu hóa phiên bị đánh cắp, đặc biệt nếu attacker kiểm soát yếu tố thứ hai |
| **Concurrent session control** | Có thể giới hạn số phiên đang tồn tại | Không được mặc định coi một session là một thiết bị đã xác minh |

Ví dụ policy giả định: idle = 20 phút, absolute = 8 giờ, yêu cầu xác thực bổ sung trong 5 phút trước khi đổi MFA. Ba giá trị này được thiết kế **độc lập**; không có “TTL an toàn cho mọi ứng dụng”.

### Thu hồi tất cả phiên của một user

Khi password reset, khóa account hoặc phát hiện phiên bị chiếm:

1. Xác định account ID đáng tin từ hệ thống người dùng.
2. Tìm các session active thông qua session registry hoặc index của Spring Session.
3. Vô hiệu hóa chúng trên session store được chia sẻ.
4. Xem xét refresh tokens, remember-me tokens, API keys, mobile sessions và IdP sessions **theo từng hệ thống**; invalidate servlet session không tự revoke OAuth access token.
5. Ghi audit và thông báo người dùng theo policy, không đưa session ID raw vào email/log.

Nếu `Authentication` chứa authorities snapshot từ lúc login, thay đổi quyền ở DB có thể **chưa phản ánh ngay** ở phiên đang còn. Cần revalidate/invalidate hoặc có cơ chế version quyền trước các hành động nhạy cảm.

## 11. Multi-instance: Spring Session, Redis và consistency

Trong Kubernetes hoặc load-balanced application, mỗi instance giữ một session map riêng sẽ làm request sang pod khác không truy xuất được context, hoặc logout ở pod A không lập tức ảnh hưởng pod B.

**Spring Session** có thể thay `HttpSession` store bằng Redis hoặc một backend phù hợp để dùng chung giữa nhiều instance. Tuy vậy:

- Cần cấu hình TTL, keyspace/index, serializer và phiên bản Spring Session tương thích.
- Giới hạn quyền kết nối Redis, TLS nếu đi qua trust boundary, không phơi Redis trực tiếp ra Internet.
- Thiết kế invalidate/revoke ở toàn cluster, tránh cache tại node giữ phiên sau khi đã revoke.
- Tự kiểm thử phân biệt **session idle TTL** và **absolute TTL** nếu policy cần cả hai.
- Đừng lưu bearer token/refresh token hoặc thông tin PII quá mức trong session attributes.
- Không dùng sticky sessions như lý do bỏ qua cơ chế chia sẻ/invalidation khi yêu cầu scale/failover.
- Không thay đổi session ID bằng một UUID do frontend tự chọn rồi tin nó.
- Với WebSocket và server-sent events, kiểm tra thời gian sống kết nối, revocation propagation và re-authorization; logout HTTP không nhất thiết ngắt mọi kênh đã mở ngay tức thì.

Ví dụ ý tưởng multi-device:

```text
Account alice
  session S1 (laptop) -> lastSeen, createdAt, device label
  session S2 (mobile) -> lastSeen, createdAt, device label
  session S3 (shared computer) -> lastSeen, createdAt, device label

User nhấp "Đăng xuất tất cả thiết bị"
  -> invalidate S1, S2, S3 ở shared session store
  -> revoke remember-me / refresh-token families tùy sản phẩm
  -> buộc auth lại cho request tiếp theo
```

Label thiết bị và IP chỉ là gợi ý UX/audit; **không chứng minh định danh thiết bị**.

## 12. Ví dụ Java 17 chạy độc lập: rotation, Secure cookie, timeout và logout

Ví dụ bên dưới nhằm **minh họa state machine** chứ **không thay thế** HttpSession của container hoặc thực thi HTTPS/CSRF thật. Trong ứng dụng Spring Security thực tế, ưu tiên implementation được framework kiểm thử. Đây là chương trình Java SE 17 không cần Spring; có thể copy thành file `SessionCookieDemo.java`.

Mục tiêu:

- Session ID được sinh từ **32 bytes `SecureRandom`** và Base64URL (256 bit entropy).
- Kho dữ liệu chỉ dùng SHA-256 digest của session ID làm key; không ghi session ID ra console.
- Trước login, anonymous session không phải authenticated session.
- Sau khi “xác thực thành công” (giả lập bằng call từ code tin cậy), app **bỏ ID cũ và cấp ID mới**.
- Idle timeout và absolute timeout được kiểm tra ở server; logout xóa state.
- Cookie được minh họa có prefix `__Host-` và thuộc tính bảo vệ.

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

public class SessionCookieDemo {
    record Session(String userId, Instant idleUntil, Instant absoluteUntil) {}

    static final class TestClock extends Clock {
        private Instant current;

        TestClock(Instant start) {
            current = start;
        }

        @Override public Instant instant() {
            return current;
        }
        @Override public ZoneId getZone() {
            return ZoneOffset.UTC;
        }
        @Override public Clock withZone(ZoneId zone) {
            return Clock.fixed(current, zone);
        }

        void advance(Duration duration) {
            current = current.plus(duration);
        }
    }

    static final class SessionStore {
        private static final Duration IDLE = Duration.ofMinutes(15);
        private static final Duration ABSOLUTE = Duration.ofHours(8);

        private final ConcurrentHashMap<String, Session> sessions =
                new ConcurrentHashMap<>();
        private final SecureRandom random = new SecureRandom();
        private final Clock clock;

        SessionStore(Clock clock) {
            this.clock = Objects.requireNonNull(clock);
        }

        String anonymous() {
            return issue(null);
        }

        // Chỉ gọi SAU KHI credential/IdP được xác minh thật.
        // Chương trình này không tự kiểm tra password.
        String afterVerifiedLogin(String anonymousId, String userId) {
            if (userId == null || userId.isBlank() ||
                    anonymousId == null || anonymousId.isBlank()) {
                throw new IllegalArgumentException("Invalid login context");
            }

            Session old = sessions.remove(digest(anonymousId));
            Instant now = clock.instant();
            if (old == null || old.userId() != null ||
                    !now.isBefore(old.idleUntil()) ||
                    !now.isBefore(old.absoluteUntil())) {
                throw new SecurityException(
                        "Unknown or expired anonymous session");
            }
            return issue(userId); // new random ID; old ID invalid
        }

        boolean authenticated(String rawId) {
            if (rawId == null || rawId.isBlank()) {
                return false;
            }
            AtomicBoolean allowed = new AtomicBoolean(false);
            sessions.computeIfPresent(digest(rawId), (key, old) -> {
                Instant now = clock.instant();

                if (!now.isBefore(old.idleUntil()) ||
                        !now.isBefore(old.absoluteUntil())) {
                    return null;
                }
                if (old.userId() != null) {
                    allowed.set(true);
                }

                // Sliding idle timer, không gia hạn absolute lifetime.
                return new Session(
                        old.userId(), now.plus(IDLE), old.absoluteUntil());
            });
            return allowed.get();
        }

        void logout(String rawId) {
            if (rawId != null) {
                sessions.remove(digest(rawId));
            }
        }

        private String issue(String userId) {
            while (true) {
                byte[] bytes = new byte[32];
                random.nextBytes(bytes);
                String raw = Base64.getUrlEncoder()
                        .withoutPadding().encodeToString(bytes);
                Instant now = clock.instant();

                Session data = new Session(
                        userId, now.plus(IDLE), now.plus(ABSOLUTE));

                if (sessions.putIfAbsent(digest(raw), data) == null) {
                    return raw;
                }
            }
        }

        private static String digest(String value) {
            try {
                byte[] hash = MessageDigest.getInstance("SHA-256")
                        .digest(value.getBytes(StandardCharsets.UTF_8));
                return HexFormat.of().formatHex(hash);
            } catch (NoSuchAlgorithmException ex) {
                throw new IllegalStateException(ex);
            }
        }
    }

    static String cookieHeader(String rawSessionId) {
        return "__Host-SESSION=" + rawSessionId
                + "; Path=/; Secure; HttpOnly; SameSite=Lax";
    }

    public static void main(String[] args) {
        TestClock clock = new TestClock(
                Instant.parse("2026-01-01T00:00:00Z"));
        SessionStore store = new SessionStore(clock);

        String anonymousId = store.anonymous();
        System.out.println("anonymousAuthenticated="
                + store.authenticated(anonymousId));

        String loggedInId = store.afterVerifiedLogin(
                anonymousId, "alice");
        System.out.println("oldIdAccepted="
                + store.authenticated(anonymousId));
        System.out.println("newIdAccepted="
                + store.authenticated(loggedInId));

        String cookie = cookieHeader(loggedInId);
        System.out.println("cookieHasSecure="
                + cookie.contains("; Secure"));
        System.out.println("cookieHasHttpOnly="
                + cookie.contains("; HttpOnly"));
        System.out.println("cookieHasLax="
                + cookie.contains("; SameSite=Lax"));

        clock.advance(Duration.ofMinutes(15));
        System.out.println("atIdleTimeoutAccepted="
                + store.authenticated(loggedInId));

        String anotherAnonymousId = store.anonymous();
        String anotherLoginId = store.afterVerifiedLogin(
                anotherAnonymousId, "alice");
        store.logout(anotherLoginId);
        System.out.println("afterLogoutAccepted="
                + store.authenticated(anotherLoginId));
    }
}
```

Chạy từ thư mục chứa file bằng JDK 17+:

```bash
javac SessionCookieDemo.java
java SessionCookieDemo
```

**Stdout đã kiểm tra:**

```text
anonymousAuthenticated=false
oldIdAccepted=false
newIdAccepted=true
cookieHasSecure=true
cookieHasHttpOnly=true
cookieHasLax=true
atIdleTimeoutAccepted=false
afterLogoutAccepted=false
```

### Phân tích chính xác giới hạn của demo

1. `SecureRandom` tạo mã khó đoán; việc hash session ID trong map không thay thế HTTPS hoặc chống lộ ID ở browser. ID thô vẫn được browser giữ và gửi trên mỗi request.
2. `SessionStore` là giả lập trong một JVM. Spring MVC production nên dùng session store và fixation strategy của Servlet container/Spring Security/Spring Session thay vì tự dùng map như trên.
3. `afterVerifiedLogin` **không xác minh password**, vì chương trình chỉ kiểm tra lifecycle. Trong ứng dụng thật, chỉ đường code **sau khi authentication thành công** được phép gọi rotation/markAuthenticated.
4. `cookieHeader` chỉ **tạo chuỗi Set-Cookie mẫu**, không thực sự phục vụ HTTPS, gửi HTTP response hoặc chứng minh browser chấp nhận cookie. Cần integration test với TLS và browser.
5. `authenticated()` gia hạn idle timeout trên request hợp lệ, nhưng không gia hạn absoluteUntil. Nếu đã quá hạn, map entry bị xóa.
6. `logout()` xóa session phía server, không phát response xóa cookie; trong Spring Security, logout filter/container xử lý phần còn lại theo cấu hình.
7. Ví dụ mô phỏng một server đơn, không có CSRF, XSS, account roles, password reset, MFA, session registry hoặc multi-node revocation.
8. `TestClock` phục vụ test deterministic; production nên dùng clock đáng tin và kiểm soát lệch đồng hồ giữa các node.
9. Kiểm tra các thuộc tính bằng `String.contains` chỉ xác minh chuỗi **do chương trình vừa tạo**; không phải trình phân tích cookie hoặc bài kiểm thử bảo mật của browser.

Điểm quan trọng là **sau login, ID cũ không còn dùng được** và **sau logout hoặc vượt TTL, server từ chối ID còn lại**, dù browser có thể còn cookie.

## 13. OIDC/SSO, iframe và cross-site cookie

Ứng dụng dùng `oauth2Login()` có thể nhận authorization code qua top-level redirect từ IdP, dùng `state`/`nonce` và một số session/cookie nội bộ để liên kết callback. Lựa chọn `SameSite` không thể được quyết định chỉ bằng khẩu hiệu “Strict luôn an toàn nhất”.

| Luồng | Hành vi cookie có thể cần | Hướng xử lý |
| --- | --- | --- |
| Browser login trực tiếp tại app | Cookie host-only `Lax` hoặc `Strict` thường phù hợp | Bật CSRF, TLS và rotation |
| OIDC top-level redirect GET callback | `Lax` thường tương thích với top-level cross-site safe navigation | Kiểm chứng state/nonce/callback, test thực tế |
| OIDC `form_post` callback | Cross-site POST có thể không gửi cookie `Lax` | Thiết kế state/cookie flow phù hợp, cân nhắc `SameSite=None; Secure` chỉ cho cookie cần thiết |
| App nhúng trong iframe site khác | Third-party cookie policies có thể chặn | Tránh phụ thuộc cookie third-party, đánh giá CHIPS/Storage Access theo browser |
| Cross-domain logout | IdP cookie, RP cookie và nhiều phiên khác nhau | RP-initiated/back-channel logout nếu có hỗ trợ; không mặc định logout liên thông |

Cẩn trọng với cookie `SameSite=None`: browser hiện đại có xu hướng hạn chế third-party cookies, và `Secure` là bắt buộc; cookie có thể **vẫn không hoạt động** trong iframe dù thuộc tính đúng. Không mở rộng `Domain=.example.org` để “sửa SSO” nếu đang làm tăng phạm vi cookie phiên sang các ứng dụng khác.

**SSO logout khác local logout:** invalidate `HttpSession` của App A không nhất thiết đăng xuất IdP hoặc App B. Ngược lại, xóa cookie IdP không tự làm local app sessions của mọi Relying Party mất hiệu lực. Cần thiết kế tích hợp logout chính thức theo IdP.

## 14. Bearer JWT, SPA và browser session khác nhau

Hai mô hình dễ bị nhầm:

### Mô hình A — server session + HttpOnly cookie

- Browser nhận cookie session ID, tự gắn cookie cho request theo domain/path/SameSite.
- Server lưu `Authentication`/SecurityContext và có thể invalidate session ngay.
- Khi dùng cookie authentication, CSRF protection là lớp cần xem xét nghiêm túc.
- Cookie `HttpOnly` giảm rủi ro raw ID bị JS đọc, nhưng XSS vẫn có thể thực hiện hành động trong phiên.

### Mô hình B — API stateless + Authorization bearer token

- Client gửi `Authorization: Bearer ...` mỗi request, server xác thực token JWT hoặc opaque theo policy.
- Token access thường không nằm trong `HttpSession`; revoke hiệu lực phụ thuộc TTL/introspection/denylist.
- Nếu SPA lưu access token trong `localStorage`, XSS có thể lấy raw token trực tiếp. Nếu chuyển token vào cookie HttpOnly, browser tự gắn cookie và CSRF threat model thay đổi.
- Không dùng `sessionCreationPolicy(STATELESS)` cho browser form login mà vẫn kỳ vọng có `HttpSession` lưu đăng nhập sau request.
- Giữ HTTPS và không log bearer token trong cả hai kiến trúc.

Không nhầm Spring MVC `HttpSecurity` với WebFlux `ServerHttpSecurity`/`WebSession`. Spring Boot hỗ trợ cấu hình cookie reactive qua namespace riêng như `server.reactive.session.cookie.*`; code `WebSecurityConfig` ở phần trước **không áp dụng nguyên xi cho WebFlux**.

## 15. Đánh giá bất thường và ứng phó khi nghi mất phiên

Ngay cả khi HTTPS, Cookie flags và CSRF đều đúng, attacker vẫn có thể chiếm browser profile, token từ log đã lộ trước đây hoặc thông qua XSS. Ứng dụng nên có đường ứng phó chủ động:

1. **Nhận tín hiệu:** session xuất hiện ở thiết bị mới, địa lý/IP thay đổi đột ngột, nhiều lần thất bại MFA, hành vi vượt mức thông thường, token bị dùng lại sau revoke.
2. **Đánh giá rủi ro:** không tự coi đổi IP hoặc User-Agent là bằng chứng chắc chắn bị chiếm; mobile, VPN, carrier NAT và cập nhật browser có thể đổi các tín hiệu này.
3. **Bảo vệ tạm thời:** yêu cầu re-auth/step-up cho tác vụ rủi ro cao, giảm phạm vi quyền tạm hoặc chặn session theo policy.
4. **Revoke:** invalidate session nghi vấn và các session liên quan; nếu có khả năng credential compromise, buộc đổi password/rotate credentials và thu hồi refresh/remember-me tokens.
5. **Giữ audit an toàn:** log event time, account ID đã kiểm soát truy cập, session correlation ID **không phải raw session secret**, action và quyết định policy.
6. **Thông báo người dùng:** nêu hoạt động bất thường và cách khôi phục an toàn, không gửi session ID hoặc mã xác minh trong email thông báo.
7. **Ngăn tái diễn:** xử lý nguyên nhân lộ qua log, XSS, cấu hình proxy, cookie domain hoặc TLS; đổi cookie flag một mình chưa giải quyết khi dữ liệu đã lộ.

**Session binding vào IP/UA** có thể làm tín hiệu phát hiện gian lận nhưng hard-fail mọi thay đổi IP có thể khóa người dùng hợp lệ hoặc bị attacker giả mạo. Không coi địa chỉ IP là yếu tố xác thực độc lập.

## 16. Những lỗi cấu hình phổ biến và cách khắc phục

**1. Cookie không có `Secure` trong production.** Browser có thể gửi ID qua HTTP, đặc biệt khi có lỗi chuyển hướng hoặc link nội bộ. Đặt `secure:true`, bắt buộc HTTPS và kiểm tra cookie ngoài ingress.

**2. Đặt `HttpOnly=false` cho session để SPA đọc cookie.** JS có thể lấy ID trực tiếp khi XSS xảy ra. Giữ session cookie HttpOnly; nếu SPA cần đọc CSRF token thì cấu hình **cookie CSRF riêng** theo chuẩn.

**3. Cho `SameSite=None` mà không có `Secure`.** Browser hiện đại có thể từ chối. Khi cross-site thật sự cần, áp dụng `None; Secure` và CSRF/state/nonce; không mở rộng toàn bộ cookie một cách tùy tiện.

**4. Tưởng `SameSite=Lax` chặn mọi CSRF.** Nó vẫn cho một số top-level GET; subdomain có thể same-site. Bật CSRF tokens, không dùng GET để đổi trạng thái và kiểm tra Origin/Fetch Metadata khi phù hợp.

**5. Dùng `Domain=.example.org` cho cookie xác thực của app.example.org.** Sibling subdomains cùng gửi/ghi cookie rộng, làm tăng rủi ro. Ưu tiên host-only và prefix `__Host-`.

**6. Đặt tên `__Host-SESSION` nhưng cookie Path là `/app`.** Browser có thể không chấp nhận cookie. Bắt buộc Path=/, Secure và không có Domain.

**7. Chỉ HTTPS cho `/login`.** Cookie bị gửi trong các request khác qua HTTP; dùng HTTPS toàn ứng dụng và HSTS.

**8. Bật `includeSubDomains`/HSTS preload khi subdomain cũ chưa hỗ trợ HTTPS.** Có thể khiến dịch vụ phụ không truy cập được. Audit hostname/subdomain trước.

**9. App sau proxy nhận HTTP và bỏ `Secure` hoặc không gửi HSTS.** Đặt cookie secure rõ ràng, cấu hình trusted proxy đúng và kiểm tra response cuối từ Internet.

**10. Tin mọi `X-Forwarded-Proto` hoặc `Forwarded` từ client.** Attacker giả scheme/host; edge phải strip/rewrite headers, giới hạn nguồn kết nối backend.

**11. Không đổi session ID sau login.** Session fixation vẫn khả thi. Dùng `changeSessionId()`/framework và test trước–sau login.

**12. Chỉ xóa cookie ở browser khi logout.** ID bị sao chép vẫn hợp lệ trên server. Invalidate phía server.

**13. Chỉ đặt cookie Max-Age=15m mà không có server timeout.** Session bị giữ trong backend; browser và server timeouts khác nhau.

**14. Dùng unlimited sliding expiration.** Attacker liên tục gửi request để giữ session sống vô hạn. Dùng absolute max age và step-up cho tác vụ nhạy cảm.

**15. Cookie xuất hiện trong access logs hoặc APM traces.** Mỗi người đọc logs có thể impersonate user. Redact `Cookie`, `Set-Cookie`, `Authorization` và URL secret.

**16. Không kiểm tra account disabled sau login.** `Authentication` snapshot trong session có thể vẫn hợp lệ. Invalidate sessions và revalidate quyền khi cần.

**17. Cho phép session identifier trong URL `;jsessionid`.** Rò qua history/Referrer/logs. Chỉ dùng cookie tracking, kiểm thử khi browser tắt cookie.

**18. Đọc cookie HttpOnly bằng JS để “kiểm tra đã login”.** Không cần và không thể như kỳ vọng. Gọi endpoint trạng thái authenticated do server trả về (chỉ metadata tối thiểu), tránh expose session secret.

**19. Nhầm cookie SameSite với origin trong CORS.** Hai cơ chế khác nhau; cross-site và cross-origin không trùng nhau. Test đúng host, scheme, browser và request method.

**20. Lưu session chỉ ở RAM một pod nhưng chạy nhiều replica.** Login/logout thất thường, revocation không thống nhất. Dùng Spring Session hoặc kiến trúc shared store phù hợp.

**21. Đặt `csrf.disable()` vì frontend là SPA.** Nếu browser tự gửi session cookie, request thay đổi trạng thái có CSRF risk. Chỉ tắt khi đã phân tích kiến trúc thực sự stateless/no ambient credentials.

**22. Dùng CSP nhưng vẫn render HTML không sanitize.** CSP là phòng thủ bổ sung; lỗi XSS vẫn có thể vượt qua tùy policy/bypass. Sửa output encoding và sanitization theo ngữ cảnh.

## 17. Ma trận kiểm thử ở trình duyệt, proxy và backend

| Test | Cách kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| HTTP truy cập trang bảo vệ | Gọi `http://app.example.org` | Redirect HTTPS trước session; không phát cookie auth qua HTTP |
| HTTPS response | Browser Network/`curl -I` | TLS hợp lệ, HSTS theo policy |
| Set-Cookie sau login | Browser devtools | `Secure`, `HttpOnly`, `SameSite` đúng, Path=/, không Domain nếu host-only |
| Prefix `__Host-` | Inspect response/browser cookie store | Browser chấp nhận khi đủ điều kiện; không bị path/domain sai |
| Cookie raw trong JS | `document.cookie` trong test environment | Không thấy session cookie HttpOnly |
| Anonymous -> authenticated | Capture cookie IDs trước và sau login trong môi trường test bảo vệ | ID thay đổi; ID cũ không truy cập được |
| Cookie cũ sau logout | Replay ID cũ từ HTTP client test | 401/redirect login hoặc bị từ chối theo endpoint |
| Idle timeout | Giả lập/integration test đồng hồ | Session hết hạn sau inactivity |
| Absolute timeout | Giữ session hoạt động liên tục | Hết hạn khi chạm absolute TTL theo policy |
| CSRF thiếu/sai token | POST endpoint session-based | Từ chối theo policy, thường 403 |
| Cross-site form POST | Browser test trên domain khác | Không thực hiện thay đổi trái phép |
| XSS payload | Test các ngữ cảnh HTML/JS/DOM | Không thực thi script độc hại |
| Wrong tenant/role | Authenticated user sai quyền | 403, không lộ dữ liệu |
| Reverse proxy spoof | Gửi `X-Forwarded-*` giả từ Internet | Edge làm sạch; không thay redirect/issuer/host an toàn |
| HSTS includeSubDomains | Test tất cả subdomains liên quan | Không phá dịch vụ chưa sẵn sàng HTTPS |
| Login OIDC callback GET | Redirect thực qua IdP | `state`, `nonce` và session correlation hợp lệ |
| OIDC `form_post` callback | Cross-site POST qua browser | Cookie/state flow đúng mà không tắt security controls |
| Password reset / disable account | User có nhiều session | Sessions cần thiết bị revoke đúng phạm vi |
| Multi-node | Login pod A, request pod B, logout pod C | Shared store và revocation thống nhất |
| Log/trace scan | Kiểm tra sanitized logs | Không có session cookie, JWT, password, refresh token |
| Logout all devices | Đăng nhập 2–3 clients | Tất cả ID cần thu hồi bị từ chối |
| Cookie deletion | Logout trong browser | Cookie bị xóa/expire theo Path/Domain đúng; server session cũng invalid |
| API bearer và browser session riêng | So sánh security chains | Cookie và bearer không tạo bypass hoặc session sai |
| Existing stolen session | Replay ID bị đánh cắp trong test kiểm soát | Phát hiện/revoke và step-up policy như thiết kế |

Đừng chỉ test kết quả 200 của một request hợp lệ. Các negative tests (replay, CSRF, URL session ID, cookie attributes, logout sau nhiều replica) là phần quan trọng để chứng minh bảo mật.

### Cách kiểm thử mà không phơi ID bí mật

Trong test automation có thể đọc ID session để so sánh trước/sau, nhưng phải giữ nó chỉ trong memory của test runner và không in ra CI logs hoặc video/screenshot công khai. Khi báo cáo, ghi `oldIdChanged=true` hoặc hash không thể đảo/thời gian sống ngắn thay vì raw session ID.

Dùng `curl` để kiểm tra headers; dùng **browser thật** để xác nhận cookie prefix, SameSite, redirect, iframe và HSTS vì các điều kiện này được enforce ở trình duyệt, không phải chỉ bởi HTTP client test.

## 18. Checklist triển khai ngắn gọn

1. Toàn bộ traffic có authentication/session dùng HTTPS; TLS hiện đại, certificate chuẩn, HTTP redirect và HSTS đã kiểm tra tại edge?
2. Cookie phiên có `Secure`, `HttpOnly` và `SameSite=Lax/Strict` theo use case; host-only, Path thích hợp và không share tới sibling subdomain?
3. Nếu dùng `__Host-`, cookie có **Secure + Path=/ + không Domain** và browser đã chấp nhận?
4. Spring Boot đã đặt `server.servlet.session.cookie.*` đúng Servlet; proxy headers chỉ được tin từ ingress kiểm soát?
5. Session ID có được sinh từ CSPRNG và thay sau login/đổi privilege không?
6. Đã tắt session tracking qua URL và tránh log `Cookie`/`Set-Cookie`/`Authorization`?
7. CSRF còn bật cho browser session; form/login/logout/POST mutation sử dụng token và policy đúng?
8. XSS được ngăn bằng encoding/sanitization/CSP; không cho third-party script không tin cậy chạy cùng origin?
9. Idle timeout và absolute timeout có được tách đúng; logout invalidates phía server?
10. Đổi mật khẩu, disable account, đổi quyền, sự cố hijacking có thể revoke **mọi session liên quan** ở store chung?
11. Multi-instance và WebSocket có xử lý session consistency/revocation không?
12. Hành động nhạy cảm có step-up/re-authentication và authorization theo ownership/tenant không?
13. SSO/OIDC callback, browser cross-site và iframe có được test với SameSite thực tế mà không nới rộng domain/cookie sai không?
14. Test matrix gồm old ID after login, replay after logout, wrong CSRF, browser cookie flags và proxy spoofing?
15. Logs/metrics có thể điều tra mà không giữ raw secrets; có runbook thu hồi phiên và thông báo sự cố không?

### Tài liệu tham khảo chính thức

- Spring Security 6.5 — Session Management và Session Fixation: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security 6.5 — Security HTTP Response Headers / HSTS: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/headers.html
- Spring Security 6.5 — CSRF: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Spring Security 6.5 — Logout: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html
- Spring Boot 3.5 — Servlet Web Applications / SameSite Cookie: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 3.5 — Common Application Properties: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
- Spring Session — Documentation: https://docs.spring.io/spring-session/reference/
- OWASP — Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP — Transport Layer Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html
- OWASP — Cross Site Scripting Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html
- OWASP — Cross-Site Request Forgery Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html

**Kết luận:** chỉ khi **HTTPS/TLS đúng**, cookie được ràng buộc an toàn, session ID được **xoay sau login** và **thu hồi ở server**, CSRF/XSS/authorization được bảo vệ, và nhiều node có cơ chế session/revocation nhất quán, ứng dụng mới giảm đáng kể rủi ro đánh cắp hoặc lạm dụng phiên. Cookie flags quan trọng nhưng không thể thay cho một kiến trúc session an toàn từ browser đến backend.
