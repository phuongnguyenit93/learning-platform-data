# Session leakage qua browser

> **Chương:** Cookie và browser  
> **Phạm vi:** Module **SECURITY_AUTHENTICATION_FUNDAMENTALS** tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này tập trung vào cách session credential bị lộ hoặc bị lạm dụng trong trình duyệt, cách cookie và browser storage vận hành, cùng những kiểm soát để bảo vệ phiên trong toàn bộ vòng đời.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích session ID/cookie là bearer credential và vì sao người lấy được phiên có thể hành động như người dùng.
2. Nhận diện nơi session có thể bị lộ: URL, browser storage, log, referrer, cache, extension, thiết bị dùng chung và mã JavaScript độc hại.
3. Phân biệt session leakage, session hijacking, session fixation, CSRF và XSS.
4. Cấu hình cookie với Secure, HttpOnly, SameSite, host-only và prefix phù hợp.
5. Thiết kế session rotation, timeout, logout, revocation và re-authentication.
6. Lựa chọn cookie-based session, browser token storage hoặc Backend for Frontend (BFF) theo mô hình đe dọa.
7. Kiểm thử việc rò rỉ, tái sử dụng, fixation, cross-site request và truy cập trên browser dùng chung trong ứng dụng Java/Spring.

## 2. Session leakage là gì?

Sau khi người dùng đăng nhập, hệ thống thường tạo một **session** để ghi nhớ trạng thái xác thực qua nhiều HTTP request. Browser gửi một credential hoặc tham chiếu phiên trong các request tiếp theo; server dựa vào đó để nhận diện principal và áp dụng quyền.

Với session cookie truyền thống, browser thường lưu một **session identifier** (session ID) do server tạo. Server giữ trạng thái phiên ở phía mình và tra cứu session theo ID. Cookie thường là bearer credential: bên nào nắm được giá trị hợp lệ có thể thử dùng nó để tiếp tục phiên.

**Session leakage** xảy ra khi session ID, cookie hoặc token duy trì phiên bị tiết lộ ngoài phạm vi kiểm soát dự kiến. Ví dụ:

- Cookie bị đánh cắp từ browser hoặc thiết bị đã bị xâm nhập.
- Session token bị ghi vào URL, log, analytics hoặc crash report.
- Token được lưu trong localStorage rồi bị mã JavaScript độc hại đọc qua XSS.
- Một extension có quyền đọc dữ liệu trang hoặc cookie lấy được thông tin phiên.
- Người dùng để phiên đăng nhập trên máy tính công cộng hoặc thiết bị dùng chung.
- Session ID xuất hiện trong ảnh chụp màn hình, ticket hỗ trợ hoặc bản ghi chia sẻ.

Khi attacker dùng session credential bị lộ để truy cập, đó là **session hijacking**. Leakage là đường thông tin bị lộ; hijacking là hành vi chiếm dụng phiên. Hai khái niệm thường đi cùng nhau nhưng không đồng nghĩa.

## 3. Cookie, session và token: các thành phần liên quan

| Thành phần | Vai trò | Lưu ý bảo mật |
|---|---|---|
| **Browser cookie** | Cơ chế browser lưu và tự gửi dữ liệu theo domain/path/secure/samesite rules | Cookie có thể mang session ID; cần bảo vệ thuộc tính và phạm vi |
| **Session ID** | Định danh một phiên ở server | Phải ngẫu nhiên mạnh, không chứa PII, không đoán được |
| **Server-side session** | Trạng thái xác thực và ngữ cảnh phiên được giữ ở server/cache | Có thể thu hồi, hết hạn và cập nhật tập trung |
| **Access token** | Credential cho resource server theo audience/scope | Nếu lưu trong browser, cần xem khả năng bị đọc hoặc đánh cắp |
| **Refresh token** | Credential cấp token mới | Thường có quyền dài hạn hơn; phải bảo vệ chặt và xoay vòng/revoke |
| **Browser storage** | localStorage, sessionStorage, IndexedDB và các vùng lưu dữ liệu khác | JavaScript cùng origin thường có thể đọc; không coi là secret vault |
| **Browser cache/history** | Có thể giữ URL, response hoặc nội dung trang | Tránh đặt credential trong URL; kiểm soát cache nội dung nhạy cảm |

Không phải mọi ứng dụng đều dùng cookie session. Một SPA có thể gửi access token trong Authorization header; một BFF có thể giữ token ở server và chỉ đưa cookie phiên opaque cho browser. Mỗi kiến trúc có bề mặt rò rỉ riêng.

## 4. Ranh giới tin cậy trong browser

Browser là môi trường thực thi phía người dùng. Server không thể dựa vào JavaScript/UI để giữ bí mật hoặc tự thực thi authorization. Người dùng có thể kiểm tra request, sửa state, cài extension hoặc chạy mã khác trong cùng origin nếu ứng dụng có XSS.

~~~mermaid
flowchart LR
    U["User"] --> B["Browser profile<br/>Cookie, storage, cache"]
    B -->|"HTTPS request + session credential"| G["Ingress / Web server"]
    G --> A["Application / BFF"]
    A --> S["Server-side session store"]
    A --> R["Resource API / Database"]
    X["XSS / malicious extension<br/>or compromised device"] -.-> B
    P["Proxy, analytics, logs"] -.-> G
~~~

Các ranh giới chính:

1. **User → browser:** người dùng nhập thông tin, mở tab, chia sẻ màn hình hoặc dùng thiết bị chung.
2. **Page script → browser storage:** script cùng origin có thể đọc nhiều loại dữ liệu web; XSS có thể lợi dụng quyền này.
3. **Browser → server:** cookie và token đi qua mạng; TLS bảo vệ đường truyền nhưng không ngăn mã độc trên endpoint đọc dữ liệu.
4. **Ingress/proxy → application:** log, tracing và header forwarding có thể vô tình lưu credential.
5. **Application → session store:** server cần kiểm soát truy cập, timeout, rotation và revocation.

Mục tiêu là giữ session credential ở nơi có thể kiểm soát, giới hạn nơi browser tự gửi cookie và bảo đảm server có thể vô hiệu phiên khi cần.

## 5. Cookie session được browser gửi như thế nào?

Khi server gửi Set-Cookie, browser lưu cookie theo các thuộc tính và chính sách của mình. Ở request sau, browser có thể tự động thêm Cookie header nếu URL, domain, path, secure và SameSite conditions phù hợp.

Ví dụ:

~~~http
HTTP/1.1 302 Found
Set-Cookie: __Host-session=opaque-random-value; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
Location: /account
~~~

Giá trị trong ví dụ chỉ là placeholder. Session ID thật cần có entropy đủ lớn và được sinh bằng CSPRNG. Không tạo ID từ user ID, timestamp, email hoặc dữ liệu có thể đoán.

Request tiếp theo có thể mang:

~~~http
GET /account HTTP/1.1
Host: app.example.test
Cookie: __Host-session=opaque-random-value
~~~

### Các thuộc tính cookie quan trọng

| Thuộc tính | Tác dụng | Lưu ý |
|---|---|---|
| **Secure** | Browser chỉ gửi cookie qua kết nối HTTPS | Dùng cho cookie phiên; kết hợp TLS và HSTS |
| **HttpOnly** | JavaScript không đọc cookie qua document.cookie | Giảm khả năng XSS lấy trực tiếp giá trị; XSS vẫn có thể gửi request dưới phiên |
| **SameSite** | Kiểm soát một số ngữ cảnh gửi cookie cross-site | Lax/Strict/None phải chọn theo luồng đăng nhập và tích hợp |
| **Domain** | Mở rộng cookie tới domain/subdomain được chỉ định | Tránh đặt Domain nếu không cần; host-only cookie thu hẹp phạm vi |
| **Path** | Giới hạn URL path mà browser gửi cookie | Không phải ranh giới bảo mật mạnh giữa các ứng dụng cùng host |
| **Max-Age / Expires** | Xác định thời hạn cookie ở browser | Hết cookie ở browser không thay thế timeout/revocation phía server |

### Prefix __Host-

Cookie prefix **__Host-** được browser hỗ trợ theo quy tắc: cookie phải có Secure, Path=/ và không có Domain. Điều này giúp tạo cookie host-only, giảm nguy cơ subdomain khác đặt cookie cùng tên cho host.

Prefix **__Secure-** yêu cầu Secure nhưng không có cùng ràng buộc Domain/Path như __Host-. Nếu có thể dùng __Host- cho session cookie, đây thường là lựa chọn thu hẹp phạm vi tốt.

## 6. SameSite, CSRF và cookie leakage không phải một vấn đề

Các khái niệm này liên quan nhưng phải phân biệt:

- **Session leakage:** attacker lấy được giá trị cookie/session credential.
- **Session hijacking:** attacker dùng credential đó để chiếm phiên.
- **CSRF:** browser của nạn nhân tự gửi request có cookie tới server do cookie được đính kèm tự động; attacker không nhất thiết đọc được cookie hoặc response.
- **XSS:** mã độc chạy trong origin của ứng dụng; nó có thể đọc dữ liệu JavaScript-accessible và gửi request dưới phiên người dùng.

SameSite giúp giảm một số request cross-site có cookie, nhưng không phải giải pháp đầy đủ cho mọi CSRF. Ứng dụng cần token chống CSRF hoặc biện pháp phù hợp, kiểm tra Origin/Referer trong ngữ cảnh thích hợp và authorization ở server.

**CORS không phải cơ chế ngăn CSRF hoặc bảo vệ cookie khỏi bị đánh cắp.** CORS chủ yếu kiểm soát việc browser cho JavaScript đọc response cross-origin. Một request vẫn có thể tới server trong một số trường hợp dù script không đọc được response.

HttpOnly ngăn JavaScript đọc giá trị cookie trực tiếp, nhưng nếu XSS chạy cùng origin, script vẫn có thể gọi endpoint bằng cookie mà browser tự gửi. Vì vậy cần đồng thời ngăn XSS bằng output encoding, sanitization, CSP và kiểm soát dependency.

## 7. Session leakage qua URL, history và referrer

Không đặt session ID, access token hoặc refresh token trong URL query hoặc path. URL có thể bị lưu ở:

- Browser history, bookmark hoặc đồng bộ lịch sử.
- Web server, reverse proxy, CDN, WAF và analytics logs.
- Error report, tracing, monitoring hoặc hệ thống hỗ trợ.
- Referrer header khi browser điều hướng tới trang khác.
- Screenshot, link chia sẻ hoặc tài liệu được copy.

Ví dụ không an toàn:

~~~text
https://app.example.test/account?session=SECRET_SESSION_VALUE
https://app.example.test/callback#access_token=SECRET_ACCESS_TOKEN
~~~

Query string thường được gửi tới server và dễ lọt vào log. Fragment không được gửi trong HTTP request thông thường, nhưng vẫn có thể nằm trong browser history và được JavaScript/extension đọc. Cả hai đều không phù hợp để giữ session credential lâu dài.

### Referrer cần hiểu chính xác

Browser không tự đưa Cookie header vào Referer. Tuy nhiên, nếu URL chứa token hoặc dữ liệu nhạy cảm, URL đó có thể được truyền trong Referer tùy Referrer-Policy và ngữ cảnh điều hướng. Vì vậy:

- Không đưa secret vào URL ngay từ đầu.
- Đặt Referrer-Policy phù hợp, ví dụ strict-origin-when-cross-origin hoặc no-referrer tùy nhu cầu.
- Hạn chế third-party script/analytics trên trang callback hoặc trang nhạy cảm.
- Redact query string trong proxy, access log và APM.

OAuth Authorization Code Flow có thể đưa authorization code ngắn hạn qua callback URL theo giao thức. Code cần được bảo vệ bằng state, PKCE, redirect URI chính xác và đổi một lần; không dùng access token hoặc session ID dài hạn trong URL. Sau callback, nên điều hướng sang URL sạch và không ghi query nhạy cảm vào log.

## 8. Browser storage: localStorage, sessionStorage và IndexedDB

Browser storage tiện cho ứng dụng, nhưng không được thiết kế như secret vault trước JavaScript cùng origin.

| Nơi lưu | Đặc tính | Rủi ro với session/token |
|---|---|---|
| **localStorage** | Tồn tại qua lần đóng/mở tab/browser cho đến khi bị xóa | JavaScript cùng origin có thể đọc; XSS có thể lấy token |
| **sessionStorage** | Thường gắn với tab/page session | JavaScript cùng origin vẫn có thể đọc; không chống XSS |
| **IndexedDB** | Database phía browser, hỗ trợ dữ liệu lớn và bất đồng bộ | JavaScript cùng origin có thể truy cập; không phải nơi cất token chống XSS |
| **Cookie HttpOnly** | Browser tự gửi cookie; JS không đọc trực tiếp | Giảm nguy cơ trích xuất bằng XSS nhưng vẫn cần CSRF protection và server controls |
| **In-memory state** | Dữ liệu nằm trong runtime của page | Giảm lưu bền nhưng vẫn có thể bị XSS/extension đọc khi page đang chạy |

Không lưu refresh token hoặc session secret dài hạn trong localStorage chỉ vì dễ triển khai. Nếu SPA cần access token, cân nhắc BFF hoặc kiến trúc token phù hợp, scope hẹp và lifetime ngắn. Với cookie-based session, dùng HttpOnly, Secure và SameSite phù hợp.

Xóa localStorage khi logout là cần thiết nếu ứng dụng đã lưu dữ liệu ở đó, nhưng không thể thu hồi token đã bị sao chép trước đó. Server phải revoke phiên/token theo thiết kế.

## 9. XSS, extension và endpoint compromise

### XSS

XSS có thể xuất hiện qua HTML không được escape, template injection, DOM sink nguy hiểm hoặc dependency bị xâm nhập. Hậu quả tùy nơi credential được lưu:

- Token trong localStorage/sessionStorage có thể bị đọc và gửi ra ngoài.
- Cookie HttpOnly không đọc được trực tiếp bằng JavaScript, nhưng script có thể gửi request tới API trong phiên hiện tại.
- In-memory token có thể bị đọc từ runtime hoặc dùng trực tiếp bởi mã độc cùng page.
- Form và nội dung người dùng nhập có thể bị thu thập trước khi gửi tới server.

Kiểm soát:

- Output encoding theo ngữ cảnh và sanitization thư viện đáng tin.
- Content Security Policy hạn chế script nguồn ngoài và inline script không cần thiết.
- Tránh hàm thực thi chuỗi động và thao tác DOM nguy hiểm với dữ liệu không tin cậy.
- Dùng Trusted Types khi nền tảng và ứng dụng hỗ trợ.
- Giảm script bên thứ ba trên trang login, callback và trang nhạy cảm.

### Browser extension

Extension có thể được cấp quyền đọc tab, nội dung trang hoặc cookie tùy quyền và API nền tảng. Người dùng nên cài extension từ nguồn đáng tin, rà soát quyền và tránh cài extension không cần thiết trên profile truy cập hệ thống nhạy cảm.

Ứng dụng server không thể giả định extension luôn an toàn. Hãy giảm dữ liệu nhạy cảm hiển thị, bảo vệ session ở server và có cách thu hồi phiên khi phát hiện compromise.

### Malware và thiết bị bị kiểm soát

HttpOnly, SameSite và TLS không ngăn malware có quyền trên endpoint đọc bộ nhớ browser, điều khiển phiên hoặc chụp màn hình. Khi thiết bị bị xâm nhập, cần thu hồi session/token, xử lý credential liên quan và yêu cầu xác thực lại từ thiết bị đáng tin.

## 10. Browser dùng chung, kiosk và máy tính công cộng

Session leakage thường xảy ra do người dùng quên đăng xuất hoặc để browser lưu phiên trên thiết bị người khác có thể truy cập.

Biện pháp cho người dùng:

- Không chọn remember me trên máy công cộng hoặc profile dùng chung.
- Đăng xuất sau khi hoàn tất và đóng cửa sổ/tab theo hướng dẫn của dịch vụ.
- Không lưu mật khẩu/session vào browser profile mà nhiều người sử dụng.
- Dùng profile riêng hoặc chế độ khách khi phù hợp; tuy nhiên private/incognito không thay thế logout và không bảo vệ khỏi malware/extension có quyền.
- Nếu nghi quên đăng xuất, dùng chức năng đăng xuất mọi thiết bị/thu hồi phiên từ một thiết bị đáng tin.

Biện pháp cho ứng dụng:

- Có idle timeout và absolute session lifetime theo rủi ro.
- Có chức năng xem/thu hồi các phiên đang hoạt động nếu phù hợp.
- Không dựa vào việc đóng browser để kết thúc session phía server.
- Với kiosk, cân nhắc phiên ngắn, không persistent cookie, tự động kết thúc sau inactivity và xóa trạng thái client.
- Sau logout, server vô hiệu session; browser xóa cookie bằng Set-Cookie cùng tên/path/domain phù hợp.

## 11. Session fixation và session rotation

**Session fixation** xảy ra khi attacker khiến nạn nhân sử dụng một session ID mà attacker đã biết hoặc kiểm soát trước khi nạn nhân đăng nhập. Nếu ứng dụng giữ nguyên ID sau đăng nhập, attacker có thể dùng ID đó để chiếm phiên đã xác thực.

Biện pháp:

1. Tạo session ID mới sau khi đăng nhập thành công.
2. Rotate session ID khi thay đổi mức đặc quyền hoặc hoàn tất step-up quan trọng.
3. Vô hiệu session ID cũ; không cho phép ID cũ tiếp tục truy cập.
4. Không nhận session ID từ URL hoặc tham số do client tự chọn.
5. Sinh ID bằng CSPRNG với entropy đủ lớn; lưu trạng thái ở server.

Session rotation không chỉ dành cho login. Khi user đổi mật khẩu, đổi quyền, recovery hoặc nâng privilege, xem xét rotate hoặc revoke các phiên khác theo policy.

## 12. Timeout, logout và revocation

Cookie hết hạn ở browser không đồng nghĩa session đã bị thu hồi ở server. Nếu attacker đã sao chép giá trị cookie trước đó, họ có thể tiếp tục dùng cho đến khi server từ chối session.

Các kiểm soát cần có:

- **Idle timeout:** hết hạn sau một khoảng không hoạt động.
- **Absolute timeout:** hết hạn tối đa dù người dùng vẫn hoạt động.
- **Re-authentication:** yêu cầu xác thực lại cho hành động nhạy cảm hoặc khi phiên quá cũ.
- **Server-side invalidation:** đánh dấu session không còn hợp lệ khi logout, compromise hoặc credential change.
- **Concurrent session policy:** giới hạn hoặc quản lý nhiều phiên theo loại tài khoản.
- **Global logout/revoke:** cho phép thu hồi các phiên khác khi cần.
- **Credential-change response:** đổi mật khẩu, recovery hoặc nghi ngờ compromise có thể kích hoạt thu hồi token/session.

### Logout đúng cách

Một luồng logout nên:

1. Xác minh request và bảo vệ CSRF nếu cookie tự động gửi.
2. Vô hiệu session ở server/session store.
3. Xóa cookie ở browser với cùng tên và phạm vi phù hợp, đặt Max-Age=0 hoặc Expires trong quá khứ.
4. Xóa client-side state/cached user data khi ứng dụng có lưu.
5. Nếu có refresh token hoặc token family, revoke theo policy.
6. Điều hướng về trang công khai và tránh để trang nhạy cảm còn hiển thị từ cache.

## 13. Cache, back button và dữ liệu nhạy cảm

Browser có cache HTTP, memory cache, back-forward cache (BFCache) và các cơ chế khôi phục trang. Sau logout, nội dung trang nhạy cảm có thể vẫn còn hiển thị trong một số tình huống nếu ứng dụng không quản lý trạng thái client.

Với response chứa dữ liệu nhạy cảm, cân nhắc:

~~~http
Cache-Control: no-store
Pragma: no-cache
~~~

no-store yêu cầu cache không lưu response theo HTTP caching semantics. Nó không phải biện pháp xóa mọi screenshot, clipboard, extension data hoặc nội dung đã bị người dùng sao chép; cũng không thay thế server-side authorization.

Ứng dụng SPA nên xóa state nhạy cảm khi logout/session invalid, kiểm tra session khi khôi phục page và không render dữ liệu cũ chỉ vì state vẫn còn trong memory. API vẫn phải từ chối request nếu session đã bị thu hồi.

## 14. BFF: giữ access token ở server

**Backend for Frontend (BFF)** là backend dành cho browser application. Browser giữ cookie phiên opaque của BFF; BFF thực hiện OIDC và lưu access/refresh token phía server, sau đó gọi API thay cho browser.

~~~mermaid
flowchart LR
    U["User"] --> B["Browser<br/>Opaque HttpOnly session cookie"]
    B -->|"Cookie + CSRF defense"| F["BFF<br/>Server session + token store"]
    F <-->|"OIDC authorization code flow"| I["Identity Provider"]
    F -->|"Access token đúng audience"| A["Resource API"]
    A --> D[("Protected data")]
    X["XSS"] -.-> B
~~~

Ưu điểm:

- Access/refresh token không phải nằm trong JavaScript storage.
- BFF có thể quản lý token rotation, session timeout và logout tập trung.
- Browser chỉ giữ session credential có phạm vi tới BFF.

Rủi ro vẫn còn:

- Cookie phiên là bearer credential và cần HttpOnly/Secure/SameSite phù hợp.
- Cookie tự động gửi nên BFF cần CSRF protection.
- XSS có thể gửi request qua browser dưới session của người dùng, dù không đọc được cookie HttpOnly.
- BFF phải kiểm tra authorization/delegation, không dùng service token rộng thay user một cách mù quáng.
- Server-side token store và session store cần bảo vệ, phân quyền và audit.

BFF giảm một số rủi ro token exposure ở browser, nhưng không loại bỏ XSS, CSRF, session hijacking hoặc lỗi authorization.

## 15. Java/Spring: cấu hình session cookie

Ví dụ cấu hình Spring Boot cho cookie session:

~~~yaml
server:
  servlet:
    session:
      cookie:
        name: __Host-session
        http-only: true
        secure: true
        path: /
        same-site: lax
      timeout: 20m
~~~

Tên thuộc tính và cách binding có thể thay đổi theo phiên bản Spring Boot. Với cookie prefix __Host-, không cấu hình Domain; cookie cần Secure và Path=/ để đáp ứng quy tắc prefix. Chỉ bật Secure trong môi trường có HTTPS thực tế; production nên phục vụ toàn bộ ứng dụng qua HTTPS và cấu hình HSTS phù hợp.

### Session fixation protection

Spring Security hỗ trợ đổi session ID sau xác thực. Ví dụ khung:

~~~java
@Bean
SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/login", "/public/**").permitAll()
            .anyRequest().authenticated())
        .sessionManagement(session -> session
            .sessionFixation(fixation -> fixation.changeSessionId()))
        .csrf(Customizer.withDefaults())
        .logout(logout -> logout
            .invalidateHttpSession(true)
            .clearAuthentication(true)
            .deleteCookies("__Host-session"))
        .build();
}
~~~

Đây là cấu hình minh họa; cần kiểm tra hành vi logout/cookie deletion với servlet container và tên cookie thực tế. Với prefix __Host-, cookie xóa phải dùng đúng path và không đặt Domain. Nếu dùng custom session repository hoặc distributed session, phải xác minh thao tác invalidate được truyền tới store.

### Không cache response nhạy cảm

Có thể thêm header ở controller/filter:

~~~java
response.setHeader("Cache-Control", "no-store");
response.setHeader("Pragma", "no-cache");
~~~

Áp dụng cho response chứa dữ liệu nhạy cảm theo policy. Không cần đặt một cấu hình cache quá rộng gây ảnh hưởng tài nguyên công khai nếu không có lý do.

## 16. Kiểm tra session ở server và tránh tin dữ liệu browser tự khai

Server phải tra session/token từ bằng chứng đã xác minh, không dựa vào:

- userId, role hoặc tenant do JavaScript gửi.
- Một biến isLoggedIn=true trong localStorage.
- Cookie tùy chỉnh do client tự tạo mà server không xác minh.
- User-Agent, IP hoặc device fingerprint như bằng chứng danh tính.
- Trang vẫn hiển thị sau logout.

Với server-side session, mỗi request cần tra session còn hiệu lực và lấy principal/authorization context từ nguồn server-side. Với JWT, phải xác minh chữ ký, issuer, audience, thời hạn, token type và policy. Dù dùng cách nào, object/tenant authorization vẫn phải thực hiện ở server.

## 17. Các sai lầm phổ biến

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Đưa session ID vào URL | Lộ qua history, log, referrer và link chia sẻ | Dùng cookie hoặc header theo kiến trúc |
| Lưu refresh token trong localStorage | XSS có thể đọc và lấy token dài hạn | Cân nhắc BFF hoặc storage/rotation phù hợp |
| Cookie thiếu HttpOnly | Script có thể đọc trực tiếp cookie | Bật HttpOnly cho session cookie |
| Cookie thiếu Secure | Có thể bị gửi qua HTTP nếu kết nối không an toàn | HTTPS, Secure và HSTS |
| Cookie Domain mở rộng toàn subdomain | Subdomain bị chiếm có thể tăng rủi ro cookie | Host-only cookie; ưu tiên __Host- |
| Chỉ dùng SameSite để chống CSRF | Không bao phủ mọi luồng và cấu hình | CSRF token/Origin checks và authorization |
| Nghĩ HttpOnly ngăn XSS | XSS vẫn có thể gửi request dưới session | Ngăn XSS và bảo vệ API |
| Không rotate ID sau login | Session fixation | Rotate và vô hiệu ID cũ |
| Chỉ xóa cookie khi logout | Session server/token bị sao chép vẫn có thể hoạt động | Server-side invalidate/revoke |
| Dựa vào đóng browser để logout | Session có thể còn hiệu lực trên server | Timeout, logout và revoke phiên |
| Tin CORS bảo vệ cookie | CSRF và API access có thể vẫn xảy ra | Tách CORS, CSRF, authentication và authorization |
| Để trang nhạy cảm cache lâu | Nội dung có thể còn hiển thị sau logout | no-store phù hợp, xóa client state và kiểm tra session |

## 18. Ma trận kiểm thử session leakage qua browser

| Kiểm thử | Kết quả mong đợi |
|---|---|
| Cookie session thiếu Secure trong production | Cấu hình bị phát hiện; cookie production chỉ gửi qua HTTPS |
| JavaScript đọc document.cookie | Session cookie HttpOnly không xuất hiện |
| Cookie có Domain rộng không cần thiết | Kiểm tra cấu hình phát hiện; dùng host-only nếu phù hợp |
| Cookie session dùng prefix __Host- nhưng có Domain | Browser không chấp nhận theo quy tắc prefix; cấu hình phải được sửa |
| Session ID cũ sau login | Bị vô hiệu sau session rotation |
| Attacker gửi session ID đã biết trước login | Không thể dùng ID cũ để chiếm phiên đã xác thực |
| Session cookie bị copy sau logout | Server từ chối vì session đã bị invalidate |
| Request cross-site thay đổi trạng thái | Bị CSRF protection chặn theo policy |
| XSS chạy trong origin | Không đọc được HttpOnly cookie; API vẫn có authorization và XSS controls |
| URL có query token giả lập | Secret scanner/log redaction phát hiện; thiết kế loại bỏ token khỏi URL |
| Trang nhạy cảm sau logout/back button | API từ chối; client xóa state và không hiển thị dữ liệu cũ theo policy |
| Browser dùng chung sau idle timeout | Session hết hạn ở server |
| Cookie hết hạn ở browser nhưng session server còn tồn tại | Kiểm thử xác nhận hành vi; server timeout/revocation mới là nguồn quyết định |
| Access token dành cho API khác | Resource server từ chối audience không đúng |
| BFF logout | Session server bị vô hiệu, cookie bị xóa và token liên quan được revoke theo policy |
| Extension/endpoint compromise giả lập | Có quy trình thu hồi phiên và yêu cầu xác thực lại |
| Browser gửi Referer tới origin khác | URL không chứa secret; Referrer-Policy giới hạn dữ liệu phù hợp |

Kiểm thử bằng session/token giả lập trong môi trường test. Không sao chép cookie hoặc access token thật của người dùng vào công cụ kiểm thử, ticket hay log.

## 19. Tình huống phân tích

### Tình huống A: token xuất hiện trong URL

Một ứng dụng đặt session token trong query string để hỗ trợ bookmark. Người dùng mở link rồi điều hướng tới một trang có analytics script.

**Phân tích:** URL có thể được lưu trong history, log và có thể được gửi trong Referer theo policy. Bỏ token khỏi URL, dùng cookie/header đúng kiến trúc, redaction query và kiểm tra các bản log đã lưu. Nếu token thật đã lộ, revoke/rotate theo loại credential.

### Tình huống B: HttpOnly nhưng vẫn bị chiếm phiên

Ứng dụng bật HttpOnly cho cookie. Một lỗi XSS cho phép attacker chạy script cùng origin và gọi endpoint chuyển dữ liệu.

**Phân tích:** attacker có thể lợi dụng browser tự gửi cookie dù không đọc được giá trị. HttpOnly giảm khả năng trích xuất cookie, nhưng không ngăn hành động dưới phiên. Cần xử lý XSS, giới hạn quyền API, CSRF defense và kiểm tra/thu hồi phiên khi compromise.

### Tình huống C: session không đổi sau đăng nhập

Ứng dụng nhận session ID từ một nguồn trước login rồi giữ nguyên sau khi người dùng nhập mật khẩu.

**Phân tích:** có nguy cơ session fixation. Tạo ID mới sau login, vô hiệu ID cũ và kiểm tra session store không còn chấp nhận ID cũ.

### Tình huống D: người dùng quên logout trên máy công cộng

Người dùng đóng tab nhưng không logout. Người tiếp theo mở lại browser profile và truy cập ứng dụng.

**Phân tích:** đóng tab không bảo đảm session server đã kết thúc. Dùng idle/absolute timeout, logout server-side, không persistent session trên kiosk và có chức năng revoke all sessions.

### Tình huống E: logout chỉ xóa cookie

Ứng dụng gửi cookie rỗng khi logout nhưng không invalidate session trong store. Attacker đã sao chép cookie trước đó vẫn truy cập được.

**Phân tích:** logout phải thu hồi trạng thái phía server. Xóa cookie chỉ làm browser hiện tại ngừng gửi giá trị; nó không vô hiệu bản sao ở nơi khác.

## 20. Quy trình thiết kế và vận hành

Trước khi phát hành luồng session/browser, hãy xác định:

1. Session credential là cookie ID, access token hay token khác; ai tạo và ai xác minh?
2. Credential có được giữ trong URL, JavaScript storage, log, analytics, extension-accessible data hoặc artifact không?
3. Cookie có Secure, HttpOnly, SameSite, host-only, Path và prefix phù hợp không?
4. Domain/subdomain có cần chia sẻ cookie không; có nguy cơ subdomain takeover không?
5. TLS/HSTS, proxy termination và redirect HTTP→HTTPS được cấu hình thế nào?
6. Session ID có entropy mạnh, không chứa PII và được rotate sau login/privilege change không?
7. Idle timeout, absolute timeout, logout và global revocation hoạt động ra sao?
8. CSRF và XSS được xử lý riêng nhưng phối hợp thế nào?
9. Response nhạy cảm có cache policy phù hợp; client có xóa state sau logout không?
10. Browser dùng chung/kiosk có timeout và quy trình kết thúc phiên phù hợp không?
11. Nếu dùng BFF, token store và cookie session có được bảo vệ và audit không?
12. Có diễn tập session theft, fixation, logout, revoke và endpoint compromise bằng credential giả lập không?

## 21. Ghi nhớ trọng tâm

- **Session ID và token duy trì phiên là credential.** Ai lấy được bearer credential còn hiệu lực có thể thử chiếm phiên.
- **Không đặt session/token dài hạn trong URL.** History, log, analytics và referrer có thể làm dữ liệu lan ra ngoài.
- **Cookie session cần Secure, HttpOnly, SameSite và phạm vi host/path phù hợp.** Ưu tiên host-only cookie và cân nhắc prefix __Host-.
- **HttpOnly giảm việc JavaScript đọc cookie nhưng không ngăn XSS gửi request.** Phải ngăn XSS và kiểm tra quyền ở server.
- **CSRF, CORS, XSS và session leakage là các vấn đề khác nhau.** Một cơ chế không thay thế toàn bộ các cơ chế còn lại.
- **Rotate session ID sau login và thay đổi privilege.** Thu hồi ID cũ để chống fixation.
- **Logout phải invalidate session ở server.** Xóa cookie ở browser một mình không thu hồi bản sao đã bị đánh cắp.
- **Browser dùng chung cần timeout và logout rõ ràng.** Đóng tab hoặc dùng private mode không thay thế thu hồi phiên.
- **BFF có thể giảm token exposure trong browser**, nhưng vẫn cần CSRF, XSS defense, session protection và authorization.

Bảo vệ session qua browser đòi hỏi kiểm soát cả nơi lưu credential, cách browser gửi credential, mã chạy trong origin và vòng đời session phía server. Khi một phiên có thể bị thu hồi nhanh, cookie có phạm vi hẹp và ứng dụng không để token rơi vào URL/log/storage không phù hợp, nguy cơ session hijacking sẽ giảm đáng kể.
