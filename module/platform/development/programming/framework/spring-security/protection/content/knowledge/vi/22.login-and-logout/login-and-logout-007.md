# Đăng xuất phía máy chủ và dữ liệu còn lưu trên trình duyệt

## Mục tiêu bài học

Nhấn nút **Đăng xuất** không có nghĩa tất cả dấu vết của phiên làm việc đã biến mất. Ứng dụng có thể hủy session ở máy chủ thành công nhưng trình duyệt vẫn hiển thị thông tin từ **DOM, lịch sử trang, back-forward cache (BFCache), HTTP cache, localStorage, sessionStorage, IndexedDB, Cache Storage hoặc service worker**. Ngược lại, xóa cookie trên trình duyệt mà không thu hồi session/token phía máy chủ cũng không đủ: một session ID hoặc refresh token đã bị sao chép có thể còn hiệu lực.

Bài thuộc chương **Đăng nhập và đăng xuất** của module **SPRING_SECURITY_HTTP_PROTECTION**. Phạm vi là cách Spring Security kết hợp **logout, CSRF, CORS, session, security headers, CSP, HSTS, HTTP firewall và bảo vệ trình duyệt** trên cả **Servlet** và **Reactive/WebFlux**, đồng thời kiểm thử các tình huống tấn công và chẩn đoán xung đột khi triển khai.

Sau bài học, bạn có thể:

1. Phân biệt **chấm dứt xác thực ở máy chủ**, **vô hiệu hóa credential phía client**, **dọn dữ liệu trình duyệt** và **đăng xuất khỏi nhà cung cấp danh tính (IdP)**.
2. Giải thích cơ chế **LogoutFilter, LogoutHandler, SecurityContextLogoutHandler, LogoutSuccessHandler** trong Spring Security Servlet và cơ chế tương ứng **LogoutWebFilter, ServerLogoutHandler, ServerLogoutSuccessHandler** trong WebFlux.
3. Cấu hình **POST /logout có CSRF**, session invalidation, SecurityContext clearing, cookie cleanup và response **303/204** theo hợp đồng HTML/SPA.
4. Phân biệt **session cookie, persistent remember-me cookie, access token, refresh token** và hậu quả của việc chỉ xóa một loại credential.
5. Kiểm tra **Domain/Path/Secure/SameSite/HttpOnly**, cách xóa cookie đúng phạm vi và giới hạn của lệnh xóa từ JavaScript.
6. Quản lý **HTTP cache, BFCache, lịch sử trình duyệt, service workers, Cache Storage, localStorage, sessionStorage, IndexedDB** và những dữ liệu không thể thu hồi như download, screenshot hoặc bản sao ngoài thiết bị.
7. Đánh giá **Clear-Site-Data** theo chính sách browser, phạm vi origin/site và nguy cơ ảnh hưởng ứng dụng/SSO dùng chung miền.
8. Thiết kế **đồng bộ logout nhiều tab**, trạng thái SPA, session timeout, token revocation, SSO/back-channel logout và phản ứng khi mất mạng.
9. Viết **MockMvc/WebTestClient/browser tests** chứng minh request cũ bị từ chối sau logout, dữ liệu client được dọn trong phạm vi kiểm soát và cơ chế cache không tạo quyền giả.
10. Xây dựng checklist và runbook cho lỗi **đã logout nhưng vẫn xem được thông tin**, vòng lặp login/CSRF, cookie chưa xóa hoặc logout không lan tới thiết bị khác.

## 1. “Đăng xuất” là một tập hợp cam kết, không phải một nút bấm

Một phiên làm việc có ít nhất **ba mặt phẳng trạng thái**:

~~~mermaid
flowchart LR
    B["Browser / client"] -->|"Cookie, token, request"| S["Spring Security + backend"]
    S --> SS["Session store / token registry"]
    B --> C["Cookie jar, tab DOM, storage, cache"]
    S --> I["IdP / SSO / upstream sessions"]
    B -->|"POST /logout + CSRF"| S
    S -->|"Clear context, invalidate, revoke"| SS
    S -->|"204 / 303, Set-Cookie, optional Clear-Site-Data"| B
    B -->|"Clear local state + notify tabs"| C
    S -.->|"Optional protocol logout"| I
~~~

**Ba câu hỏi phải được kiểm tra độc lập:**

1. **Máy chủ còn chấp nhận credential cũ không?** Ví dụ một request mới mang session cookie cũ hoặc token cũ phải bị từ chối theo chính sách revocation.
2. **Trình duyệt còn giữ và hiển thị dữ liệu nhạy cảm không?** Dữ liệu có thể đã được render vào DOM hoặc ghi vào storage/cache trước khi logout.
3. **Những phiên khác có bị ảnh hưởng không?** Session trên thiết bị khác, remember-me credential, refresh token hoặc phiên đăng nhập tại IdP có thể thuộc vòng đời riêng.

Nếu ứng dụng chỉ đổi giao diện từ **Dashboard** sang **Login**, nhưng server vẫn chấp nhận session ID cũ, đó là **logout chỉ ở UI**. Nếu server hủy session nhưng tab cũ vẫn hiển thị hồ sơ đã cache, đó là **server logout thành công nhưng browser chưa dọn hiển thị**. Hai vấn đề đòi biện pháp khác nhau.

### 1.1. Ví dụ gây hiểu lầm: bấm Back sau logout

~~~text
1. User login và xem GET /app/account.
2. Browser render tên, email, số dư.
3. User POST /logout; backend hủy HttpSession.
4. Browser chuyển tới /login?logout.
5. User nhấn Back.
6. Browser có thể hiển thị snapshot đã render của /app/account.
~~~

Bước 6 **không tự chứng minh session còn hiệu lực**. Browser có thể phục hồi DOM từ **BFCache** mà không gửi GET /app/account mới. Nhưng vẫn có nguy cơ **lộ thông tin trên thiết bị dùng chung**. Cần xử lý cả UI lifecycle, cache policy và khả năng server từ chối request mới.

### 1.2. Ví dụ nguy hiểm hơn: cookie bị xóa nhưng session vẫn còn

~~~text
Browser xóa JSESSIONID.
Server session có ID cũ vẫn tồn tại 30 phút.
Một bên khác có bản sao ID cũ tiếp tục gửi request.
~~~

Đây là lý do **xóa cookie phía client không thay session invalidation phía server**. Với access token kiểu bearer, vấn đề tương tự: xóa token ở browser **không vô hiệu hóa bản sao token đã bị lộ** nếu hệ thống chỉ kiểm tra chữ ký/exp và không có chính sách thu hồi.

### 1.3. Phạm vi logout phải được định nghĩa rõ

| Mục tiêu sản phẩm | Có thể cần thực hiện | Không được mặc nhiên suy ra |
| --- | --- | --- |
| **Logout tab hiện tại** | Xóa trạng thái UI và credential đang dùng trong tab. | Session/token của tab khác tự bị hủy. |
| **Logout trình duyệt hiện tại** | Hủy session, xóa/expire cookie, phối hợp nhiều tab. | Các thiết bị khác bị đăng xuất. |
| **Logout tất cả thiết bị** | Thu hồi mọi server sessions và refresh tokens theo user/device policy. | Mọi access token JWT đã cấp lập tức vô hiệu nếu vẫn verify offline. |
| **Logout khỏi SSO/IdP** | Thực thi giao thức logout tương ứng, validate callback/redirect. | Chỉ local app logout sẽ kết thúc IdP session. |
| **Xóa dữ liệu trình duyệt** | Clear storage/cache của origin/app theo phạm vi browser hỗ trợ. | Lịch sử, password manager, download, screenshot, thiết bị khác đều bị xóa. |

**Không dùng cùng một câu “Bạn đã đăng xuất khỏi mọi nơi”** nếu thực tế hệ thống chỉ invalidate một session tại ứng dụng hiện tại.

## 2. Bản đồ dữ liệu còn lại sau đăng xuất

### 2.1. Mỗi nơi lưu có chủ sở hữu và cách dọn khác nhau

| Nơi lưu | Có thể chứa | Phía nào kiểm soát | Sau server logout tự biến mất? |
| --- | --- | --- | --- |
| **Server HttpSession/WebSession** | SecurityContext, session ID mapping, dữ liệu workflow. | Ứng dụng/session store. | Chỉ khi invalidate/expire/thu hồi đúng. |
| **Spring Session/Redis** | Session chia sẻ nhiều instance. | Ứng dụng + distributed store. | Không tự biến mất vì SPA đổi trang; cần invalidation đúng. |
| **Session cookie** | JSESSIONID hoặc ID opaque. | Server phát Set-Cookie; browser lưu. | Không nhất thiết; cần expire cookie đúng scope. |
| **Remember-me persistent cookie** | Token để tái xác thực qua những lần mở browser. | Server + token repository, browser. | Không nếu logout không dọn/thu hồi remember-me token. |
| **Access token / refresh token** | Bearer credential, token rotation state. | Auth server/issuer + client. | Không nếu chỉ xóa SecurityContext của một session không liên quan. |
| **DOM / JS memory** | Hồ sơ, thông báo, bảng giao dịch đang hiển thị. | Tab đang mở. | Không tự biến mất khi server invalidate session. |
| **sessionStorage** | State theo tab và origin. | JavaScript trong tab. | Không tự biến mất khi server logout. |
| **localStorage** | Preferences và đôi khi thông tin user do app ghi. | JavaScript trong origin. | Không tự biến mất. |
| **IndexedDB** | Offline records, dữ liệu lớn theo origin. | JavaScript/service worker của origin. | Không tự biến mất. |
| **Cache Storage** | Responses, assets, offline HTML/JSON. | JS/service worker trong origin. | Không tự biến mất. |
| **HTTP cache** | Response trước đó theo browser/proxy caching rules. | Browser/proxy + cache headers. | Không nhất thiết; cần policy no-store phù hợp. |
| **BFCache** | Snapshot document và JS state để đi Back/Forward. | Browser page lifecycle. | Không thể coi server logout là lệnh xóa snapshot. |
| **Browser history** | URL và navigation history. | Browser/người dùng. | Không tự xóa chỉ vì logout. |
| **Downloads/screenshots/clipboard** | Bản sao dữ liệu đã đưa ra khỏi app. | Thiết bị/người dùng/phần mềm khác. | **Không thể thu hồi đáng tin bằng logout web.** |
| **IdP session** | SSO identity ở tổ chức/nhà cung cấp. | IdP. | Không, trừ khi logout protocol làm điều đó. |

### 2.2. Tách credential và thông tin được hiển thị

- **Credential** là bí mật/định danh bearer có thể giúp máy chủ nhận request như user, chẳng hạn session ID, remember-me token, access/refresh token. Cần **thu hồi hoặc làm cho không còn được chấp nhận**.
- **Rendered data** là nội dung đã được phép tải xuống/trình bày, có thể tồn tại trong DOM, caches, screenshots. Cần **hạn chế lưu và dọn trong phạm vi kiểm soát**, nhưng không thể bảo đảm xóa mọi bản sao.
- **Identity state** là dấu hiệu frontend “đang login”, chẳng hạn Redux store hoặc một cờ isLoggedIn trong localStorage. Cần đồng bộ với **thực trạng authentication phía server**, không dùng cờ này để cấp quyền.
- **Navigation state** là route sau logout, redirect/returnTo, history entries. Nó không phải chứng cứ xác thực và có thể tạo redirect loop hoặc open redirect nếu dùng không kiểm soát.

### 2.3. Mô hình đe dọa: thiết bị cá nhân và thiết bị dùng chung

Trên máy cá nhân, mục tiêu UX có thể là chuyển trang, xóa token, đồng bộ nhiều tab và ẩn thông tin sau Back. Trên máy tính công cộng/kiosk, mục tiêu có thể nghiêm ngặt hơn: **không giữ offline cache nội dung nhạy cảm**, thiết kế session timeout ngắn, xác minh lại danh tính trước các tác vụ rủi ro cao và hướng dẫn người dùng đóng phiên browser.

Không có header nào khiến website **xóa được bản sao file người dùng đã tải xuống, chụp màn hình hoặc ghi ra ngoài origin**. Tránh cam kết vượt khả năng browser.

## 3. Luồng logout đúng của Spring Security Servlet

Spring Security Servlet có **LogoutFilter** và một chuỗi **LogoutHandler**, sau đó chạy **LogoutSuccessHandler**. Logout thông thường không nên tự viết một controller chỉ gọi session.invalidate rồi bỏ các bước cleanup do Spring Security quản lý.

### 3.1. Các thành phần

| Thành phần | Vai trò | Cảnh báo |
| --- | --- | --- |
| **LogoutFilter** | Match request logout và kích hoạt logout chain. | Match URL/method phải đúng với CSRF policy. |
| **SecurityContextLogoutHandler** | Clear authentication/context và có thể invalidate HttpSession. | Không đồng nghĩa dọn localStorage/Cache Storage. |
| **CsrfLogoutHandler** | Xóa CSRF token khỏi repository theo logout lifecycle. | Client phải lấy token mới khi bắt đầu phiên sau. |
| **RememberMeServices / logout handler** | Xóa/thu hồi remember-me state tùy cấu hình. | Cookie persistent + server token repository phải cùng được xử lý. |
| **CookieClearingLogoutHandler** | Gửi cookie expiration theo tên đã cấu hình. | Domain/Path phải khớp cookie thực; có thể cần xử lý riêng. |
| **LogoutSuccessHandler** | Trả 302/303 hoặc 204 sau cleanup. | Không dùng open redirect từ returnTo/Referer. |
| **SecurityContextRepository** | Lưu/clear authentication context theo cấu hình. | Không tự thu hồi JWT phát cho client khác. |

### 3.2. Thứ tự khái niệm

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant F as CsrfFilter + LogoutFilter
    participant H as LogoutHandlers
    participant S as Session / token store
    participant U as LogoutSuccessHandler

    B->>F: POST /logout + CSRF + session cookie
    F->>F: Kiểm tra CSRF / logout matcher
    F->>H: Thực thi logout chain
    H->>S: Clear SecurityContext, invalidate session
    H->>S: Remove CSRF/remember-me/revocable credentials
    H->>B: Cookie expiration headers (nếu cấu hình)
    F->>U: Logout success
    U-->>B: 303 /login?logout hoặc 204
    B->>B: Dọn app state/storage và đồng bộ tabs
~~~

Bảo vệ **POST /logout bằng CSRF** quan trọng với ứng dụng cookie/session, vì cookie được browser tự gửi có thể khiến website khác gây logout ngoài ý định nếu endpoint unsafe không được bảo vệ. Mặc định của Spring Security Servlet khi CSRF bật yêu cầu request logout theo POST trong cấu hình thông thường.

### 3.3. Vì sao không dùng GET /logout làm mutation?

**GET phải an toàn (safe) theo ngữ nghĩa HTTP.** Nếu GET /logout thực sự invalidate session, link, preview, prefetch, image hoặc request cross-site có thể gây logout ngoài ý định. Để phù hợp HTTP semantics và CSRF:

~~~html
<form method="post" action="/logout">
  <!-- Ứng dụng/template phải chèn CSRF token hợp lệ tại đây. -->
  <button type="submit">Đăng xuất</button>
</form>
~~~

Một GET /logout có thể hiển thị **trang xác nhận** trong một số cấu hình, nhưng request thực hiện logout vẫn nên là **POST có token**. Không giải quyết lỗi POST 403 bằng cách biến logout thành GET không có CSRF.

### 3.4. Session invalidation khác xóa cookie

Khi server invalidate HttpSession:

- Session ID cũ không còn ánh xạ tới một **authenticated session hợp lệ** trong store đúng, theo mô hình đang triển khai.
- Browser vẫn có thể đang giữ cookie ID cũ cho tới khi expiration header được xử lý hoặc browser tự hết hạn.
- Một request mang ID cũ phải không trở thành user authenticated; server có thể tạo session mới anonymous để phục vụ CSRF/login page.
- Spring Security có thể cần clear SecurityContext khỏi repository theo cơ chế đang dùng; tự xóa cookie không bảo đảm điều đó.
- Nếu app có **JWT/refresh token/remember-me/SSO**, cần cleanup hoặc revocation riêng phù hợp.

**Kiểm chứng logout phía server bằng request mới**, không chỉ nhìn cookie đã mất trong DevTools.

## 4. Server-side logout: chấm dứt credential chứ không chỉ đổi giao diện

### 4.1. Logout hiện tại khác logout tất cả thiết bị

Một account có thể có Session A tại trình duyệt này, Session B tại điện thoại, một refresh token C ở ứng dụng khác và phiên SSO tại IdP. Invalidate Session A **không tự hủy** Session B, refresh token C hoặc IdP session.

Nếu sản phẩm có nút **“Đăng xuất mọi thiết bị”**, backend phải triển khai cơ chế revoke session/token theo user/device hoặc credential version/revocation registry. Nếu access token là JWT tự kiểm tra chữ ký và thời hạn, không có denylist/introspection/version check, **token đã phát vẫn được chấp nhận đến khi hết hạn** dù browser đã xóa bản sao của nó.

### 4.2. Cam kết tối thiểu

Sau POST /logout thành công cần xác minh:

1. Request mới mang **session ID cũ** không còn authenticated.
2. SecurityContext cũ không được load lại từ repository.
3. CSRF state của phiên cũ được xử lý đúng.
4. Remember-me cookie/persistent token được thu hồi nếu có.
5. Refresh token hoặc token registry riêng được xử lý theo phạm vi logout đã công bố.
6. Response không chứa credential có quyền hoặc redirect tùy ý.
7. Invalidation có hiệu lực trên các instance dùng shared session store.
8. Request đã authentication trước khi logout được xử lý theo chính sách **in-flight request**, không tự coi mọi tác vụ đồng thời đã bị hủy.

Một test chỉ nhìn **POST /logout → 204 → UI /login** là chưa đủ. Phải thử:

~~~http
GET /api/me HTTP/1.1
Cookie: JSESSIONID=old-session-id
~~~

và kỳ vọng endpoint không trả protected user data. Nếu backend tạo **anonymous session mới** phục vụ login/CSRF, sự tồn tại cookie mới không chứng minh logout thất bại.

### 4.3. SecurityContext và custom authentication filter

Một SecurityContextLogoutHandler có thể clear context và invalidate session, nhưng nếu ứng dụng còn **remember-me cookie, API key, bearer token hoặc custom auto-login filter**, request sau logout có thể tạo lại Authentication từ credential chưa được revoke.

**Hãy xác định chính xác credential nào đang xác thực mỗi request**. Không coi xóa ThreadLocal SecurityContext hoặc xóa một cookie tùy ý là revoke toàn hệ thống.

### 4.4. LogoutHandler, LogoutSuccessHandler và partial failures

**LogoutHandler** phù hợp cleanup server state, **LogoutSuccessHandler** định nghĩa response. Những thao tác bắt buộc như invalidate session hiện tại hoặc revoke refresh token phải có chính sách khi DB/Redis lỗi. Fan-out event nhiều thiết bị có thể bất đồng bộ nhưng không được đánh dấu **global logout đã hoàn tất** nếu chưa có cơ sở.

Thiết kế idempotency: gửi lại POST logout sau timeout không được tạo credential mới, reset những trạng thái bất thường hay revoke nhầm người khác. Không log raw token/session IDs.

## 5. Spring Security Servlet: logout an toàn với CSRF

Các mẫu sau dùng Spring Security Servlet/Spring MVC. **Chọn một cấu hình phù hợp**, không đăng ký nhiều SecurityFilterChain bắt mọi request rồi mong chúng tự kết hợp.

### 5.1. Form HTML: POST /logout và quay về login

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class FormLogoutSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/assets/**")
                            .permitAll()
                        .anyRequest().authenticated())
                .formLogin(form -> form
                        .loginPage("/login")
                        .permitAll())
                .csrf(Customizer.withDefaults())
                .logout(logout -> logout
                        .logoutUrl("/logout")
                        .logoutSuccessUrl("/login?logout")
                        .invalidateHttpSession(true)
                        .clearAuthentication(true)
                        .deleteCookies("JSESSIONID")
                        .permitAll())
                .build();
    }
}
~~~

- **invalidateHttpSession(true)**: hủy HttpSession theo logout strategy áp dụng.
- **clearAuthentication(true)**: clear Authentication thuộc SecurityContext.
- **deleteCookies("JSESSIONID")**: yêu cầu browser expire cookie tên đó. **Path/Domain cần khớp cookie thực**.
- **logoutSuccessUrl**: điều hướng HTML form về trang công khai, không phải thực thi dọn localStorage.
- **permitAll**: điều chỉnh authorization rules, **không bỏ CSRF trên POST /logout**.

Nếu app dùng Spring Session hoặc đổi tên cookie (ví dụ __Host-APPSESSION), không áp dụng mù quáng JSESSIONID. Nếu dùng remember-me, phải xác minh token repository và cookie có được Spring Security cleanup theo cấu hình.

### 5.2. Form HTML với CSRF field

~~~html
<form method="post" action="/logout">
  <input type="hidden" name="_csrf" value="TOKEN_FROM_SERVER">
  <button type="submit">Đăng xuất</button>
</form>
~~~

**TOKEN_FROM_SERVER** chỉ là placeholder. Template phải cấp CSRF token hợp lệ; nếu dùng Thymeleaf/Spring MVC tích hợp, RequestDataValueProcessor có thể chèn hidden field cho form POST có th:action. Kiểm tra HTML render thực tế, không hardcode token.

GET /logout có thể là **trang xác nhận** khi framework cấu hình như vậy; không biến GET thành mutation logout để né CSRF. Unsafe GET logout có thể bị trigger bởi prefetch, link, ảnh hoặc website khác.

### 5.3. SPA: LogoutSuccessHandler trả 204

Với SPA gọi fetch, backend trả **204 No Content** thường dễ xử lý hơn 302 vì fetch redirect không làm SPA router tự đổi trang.

~~~java
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SpaLogoutSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/csrf", "/assets/**")
                            .permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .logout(logout -> logout
                        .logoutUrl("/logout")
                        .invalidateHttpSession(true)
                        .clearAuthentication(true)
                        .deleteCookies("JSESSIONID")
                        .logoutSuccessHandler(
                                (request, response, authentication) -> {
                                    response.setStatus(
                                            HttpServletResponse.SC_NO_CONTENT);
                                    response.setHeader(
                                            "Cache-Control", "no-store");
                                })
                        .permitAll())
                .build();
    }
}
~~~

Mẫu này chỉ minh họa session-based logout response. Nếu dùng access/refresh token ngoài session, phải revoke riêng. Với SPA cross-origin cần CORS allowlist/credentials/OPTIONS policy, và cookie SameSite/Secure phù hợp. Đừng đưa returnTo chưa validate vào logout success handler vì có thể tạo **open redirect sau logout**.

### 5.4. Revoke ứng dụng qua custom LogoutHandler

~~~java
import org.springframework.security.web.authentication.logout.LogoutHandler;

// tokenService là service của ứng dụng, không phải Spring Security API.
LogoutHandler revokeCurrentDevice = (request, response, authentication) -> {
    if (authentication != null) {
        tokenService.revokeCurrentDeviceCredentials(
                authentication, request);
    }
};

// Trong cấu hình HttpSecurity.logout:
.logout(logout -> logout
        .addLogoutHandler(revokeCurrentDevice)
        .invalidateHttpSession(true)
        .clearAuthentication(true))
~~~

Đây là **điểm tích hợp**, không phải implementation của tokenService. Service phải nhận dạng credential/device hiện tại từ nguồn đáng tin, bảo đảm idempotency, quản lý store unavailable và không log token. Không nhận một device ID do client tùy ý khai rồi thu hồi token của user khác.

### 5.5. Trạng thái và response sau logout

| Client/tình huống | Phản hồi có thể phù hợp | Ghi chú |
| --- | --- | --- |
| Browser form POST | 302/303 tới /login?logout. | Trang đích phải an toàn/được kiểm soát. |
| SPA fetch POST | 204 hoặc JSON ngắn. | Frontend tự clear UI/router state. |
| Credential/CSRF không hợp lệ | 403/401 theo contract. | Không tự tắt CSRF. |
| Session đã hết hạn | Idempotent/no-op hoặc response được quy định. | Không tái tạo authenticated session. |
| Revoke store/IdP lỗi | Error contract đúng phạm vi. | Không tuyên bố đã revoke mọi nơi khi chưa xong. |

Khi client gặp network timeout sau POST logout, server có thể đã hủy session **dù client chưa nhận 204**. Client nên xử lý trạng thái thận trọng: dọn local sensitive UI, đánh dấu chưa chắc global logout đã hoàn tất và không tiếp tục gửi sensitive actions.

### 5.6. Cookie có thể còn sau response

Cookie vẫn có thể xuất hiện do Path/Domain sai, Spring Session dùng tên khác, response Set-Cookie bị chặn, response khác đang in-flight phát cookie mới, remember-me cookie còn hiệu lực, hoặc GET /login tạo anonymous session mới.

**Dùng protected GET sau logout để kiểm tra quyền thực**, kết hợp DevTools xem cookies. Xóa cookie không thu hồi một session bị sao chép hoặc bearer token còn hợp lệ.

### 5.7. CSRF token lifecycle sau logout

~~~text
POST /logout + token hiện hành
  → session/auth state invalidated, CSRF token dọn theo policy
  → frontend bỏ token cũ

GET /login hoặc GET /csrf
  → cấp token cho anonymous session mới

POST /login + token mới
  → authentication được phép tiếp tục
~~~

Khi login sau logout nhận 403, kiểm tra CSRF repository và session cookie thay vì suy rằng credential sai. Không giữ token cũ mãi trong localStorage để né refresh.

## 6. Spring Security Reactive/WebFlux: SecurityContext và WebSession

WebFlux dùng **LogoutWebFilter, ServerLogoutHandler và ServerLogoutSuccessHandler** thay cho Servlet LogoutFilter/LogoutHandler. WebSession không phải HttpSession; thao tác dọn session chạy bất đồng bộ trong reactive pipeline.

### 6.1. Luồng khái niệm

~~~text
POST /logout + CSRF token + WebSession cookie
  → CsrfWebFilter
  → LogoutWebFilter theo matcher
  → ServerLogoutHandler clear SecurityContext
  → WebSession invalidate theo policy
  → ServerLogoutSuccessHandler trả 204/redirect
  → Client dọn dữ liệu origin/app và đồng bộ tabs
~~~

Không suy mặc định WebFlux đã revoke **bearer JWT, refresh token hoặc custom authentication state** chỉ vì một logout handler clear SecurityContext. Kiểm tra chính xác handlers và repository đang được nối.

### 6.2. WebFlux SecurityWebFilterChain có cleanup tường minh

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive
        .EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.logout
        .SecurityContextServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout
        .ServerLogoutHandler;
import org.springframework.web.server.WebSession;

@Configuration
@EnableWebFluxSecurity
class ReactiveLogoutSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {

        SecurityContextServerLogoutHandler clearContext =
                new SecurityContextServerLogoutHandler();

        ServerLogoutHandler clearContextAndSession =
                (webFilterExchange, authentication) ->
                        clearContext.logout(
                                webFilterExchange, authentication)
                        .then(webFilterExchange.getExchange()
                                .getSession()
                                .flatMap(WebSession::invalidate));

        return http
                .authorizeExchange(auth -> auth
                        .pathMatchers("/login", "/csrf").permitAll()
                        .anyExchange().authenticated())
                .formLogin(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .logout(logout -> logout
                        .logoutHandler(clearContextAndSession)
                        .logoutSuccessHandler(
                                (webFilterExchange, authentication) -> {
                                    var response = webFilterExchange
                                            .getExchange().getResponse();
                                    response.setStatusCode(
                                            HttpStatus.NO_CONTENT);
                                    response.getHeaders()
                                            .setCacheControl("no-store");
                                    return response.setComplete();
                                }))
                .build();
    }
}
~~~

Mẫu này thể hiện **dọn SecurityContext và invalidate WebSession tường minh** cho session-based form login. Nó không phải lời khuyên phải thay thế mọi handler mặc định: nếu ứng dụng đang có CSRF logout cleanup, remember-me/token revocation hoặc nhiều ServerLogoutHandler, việc custom hóa cần **compose đủ những tác vụ bắt buộc** theo version của Spring Security.

**Điểm cần nhớ**:

- **WebSession::invalidate** là thao tác nonblocking; đừng gọi block()/subscribe() bên trong handler.
- **getSession()** trong WebFlux có session semantics riêng; test anonymous/no-session cases.
- Kiểm tra chính xác logout matcher/method và CsrfWebFilter trong security chain thực tế.
- Nếu nhiều SecurityWebFilterChain, URL /logout phải đi qua chain đúng.
- 204 dùng cho SPA; HTML form có thể yêu cầu redirect success handler tới path được allowlist.
- Nếu dùng reactive Redis/Spring Session, kiểm tra invalidation trên mọi instance và lỗi khi store unavailable.

### 6.3. Cookie WebSession có thể không tên JSESSIONID

WebFlux thường dùng cookie quản lý WebSession riêng, có thể mang tên **SESSION** hoặc tên được cấu hình bằng **CookieWebSessionIdResolver**. Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.session
        .CookieWebSessionIdResolver;
import org.springframework.web.server.session
        .WebSessionIdResolver;

@Configuration
class ReactiveSessionCookieConfig {

    @Bean
    WebSessionIdResolver webSessionIdResolver() {
        CookieWebSessionIdResolver resolver =
                new CookieWebSessionIdResolver();

        resolver.setCookieName("__Host-APPSESSION");
        resolver.addCookieInitializer(builder -> builder
                .path("/")
                .secure(true)
                .httpOnly(true)
                .sameSite("Lax"));

        return resolver;
    }
}
~~~

Tiền tố **__Host-** yêu cầu Secure, Path=/ và không có Domain; sử dụng HTTPS thật. Đo response Set-Cookie/expiration qua browser/proxy, đừng suy từ cookie name rằng invalidation chắc chắn xảy ra.

### 6.4. Token-based Reactive APIs là trường hợp khác

Một resource server dùng **Authorization: Bearer** có thể không dùng WebSession để xác thực. Invalidate WebSession không ảnh hưởng JWT đã phát hoặc bearer token được client khác giữ.

Thiết kế logout phải trả lời: token có **exp**, issuer/introspection, revocation store, refresh token rotation và phạm vi thiết bị nào; có cần thu hồi IdP session hay không. Không tuyên bố **JWT đã thu hồi toàn cầu** nếu resource server vẫn xác minh offline với chữ ký + thời hạn mà không kiểm tra bất kỳ revocation state nào.

## 7. Stateless tokens, remember-me và đăng xuất nhiều thiết bị

### 7.1. Session cookie khác bearer token

**Session ID** là khóa tra một server-side session. Khi backend invalidate entry tương ứng, ID cũ không còn ánh xạ tới principal authenticated.

**Self-contained JWT access token** thường được resource server xác minh theo chữ ký, issuer, audience và exp. Nếu hệ thống không tra revocation state, logout ở browser **không thể thay đổi một JWT đã ký**; nó tiếp tục hợp lệ cho đến khi hết hạn hoặc resource server thay chính sách chấp nhận.

**Opaque/reference token** có thể được introspect với authorization server; revocation có thể có tác dụng khi introspection phản ánh trạng thái mới, tùy caching và consistency.

### 7.2. Các lựa chọn chiến lược revoke

| Chiến lược | Tác dụng | Đánh đổi |
| --- | --- | --- |
| **Server-side session invalidation** | Chặn session ID cũ ở request tiếp theo. | Phải invalidation đúng shared store. |
| **Reference/opaque token revocation** | Token không còn active theo registry/introspection. | Phụ thuộc store và cache TTL. |
| **JWT denylist theo jti** | Từ chối token còn hạn nếu jti đã bị revoke. | Cần tra registry và TTL đến exp. |
| **Credential version/epoch** | Từ chối token phát trước security event. | Mọi token validation phải kiểm tra version/epoch. |
| **Access token ngắn hạn + revoke refresh** | Giới hạn cửa sổ sống sót của access token. | Access token cũ có thể vẫn dùng tới exp. |
| **Key rotation** | Có thể vô hiệu cả nhóm token. | Ảnh hưởng lớn; không phù hợp xử lý logout một user thường ngày. |
| **Device/session registry** | Cho user xem và thu hồi từng phiên/thiết bị. | Cần xác minh quyền và thiết kế distributed consistency. |

Không một lựa chọn nào tự bảo đảm **cắt ngay request đã được authentication trước thời điểm revoke**. Các API nhạy cảm có thể cần kiểm tra authz/reauthentication tại lúc mutation commit.

### 7.3. Refresh token rotation và logout

Một SPA/mobile client có thể nhận **access token ngắn hạn** và **refresh token** có khả năng lấy token mới. Sau logout:

- Xóa credential khỏi client theo phương thức lưu tương ứng.
- Backend thu hồi **refresh token hiện tại hoặc token family** theo chính sách.
- Phát hiện sử dụng lại refresh token cũ nếu dùng rotation/reuse detection.
- Phân biệt logout **thiết bị hiện tại** với logout **mọi phiên**.
- Không hiển thị refresh token hoặc Authorization header trong logs.
- Test việc dùng refresh token cũ sau logout bị từ chối; test access token còn hạn theo đúng cam kết revocation đã chọn.

Nếu chỉ xóa access token nhưng refresh token vẫn còn trong cookie HttpOnly, **request refresh sau đó có thể đăng nhập lại user**.

### 7.4. Remember-me không phải session cookie thông thường

Spring Security remember-me có thể tạo cookie dài hạn, và một số cấu hình dùng persistent token repository phía server. Khi user logout, cần:

1. Expire remember-me cookie với tên/Path/Domain đúng.
2. Thu hồi token hoặc series trong persistent repository nếu được dùng.
3. Bảo đảm filter remember-me không tự tạo authenticated principal ở request mới.
4. Không xóa toàn bộ user devices nếu chỉ muốn logout hiện tại.
5. Có kiểm thử khi browser đóng/mở lại, vì remember-me nhằm sống qua browser session.

Một logout có thể trông thành công ở UI nhưng user tự đăng nhập lại khi mở protected page bởi **remember-me cookie còn hiệu lực**.

### 7.5. “Đăng xuất mọi thiết bị” là workflow riêng

Một API global logout có thể:

~~~text
User đã xác thực + reauthentication/step-up nếu cần
   → xác nhận ý định logout tất cả thiết bị
   → revoke server sessions của user
   → revoke refresh token families/device sessions
   → cập nhật credential epoch nếu cơ chế có dùng
   → phát logout/revocation events có kiểm soát
   → clear local state trên thiết bị hiện tại
   → phản hồi đúng phạm vi đã hoàn tất
~~~

Khi dùng API thu hồi mọi session của user, server **không lấy userId từ body do client khai làm authority**. Principal đang xác thực và authorization policy quyết định đối tượng được thu hồi.

### 7.6. Không nhầm “logout thành công” với “xóa sạch mọi bản sao”

Ngay cả khi JWT/refresh token đã bị vô hiệu hóa, **một tab hoặc thiết bị đã tải dữ liệu** vẫn có thể giữ bản sao offline, screenshot hoặc file download. Token revocation làm giảm **truy cập tương lai**, không quay ngược thời gian để lấy lại dữ liệu đã phát cho client.

## 8. Cookie: xóa đúng tên, Path, Domain và loại credential

### 8.1. Cookie scope ảnh hưởng trực tiếp đến logout

Cookie có thể được phát:

~~~http
Set-Cookie: JSESSIONID=opaque; Path=/app; HttpOnly; Secure; SameSite=Lax
~~~

Nếu logout trả:

~~~http
Set-Cookie: JSESSIONID=; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

thì **Path=/ khác Path=/app**. Expiration cookie có thể không loại bỏ đúng cookie đang được browser giữ. Với cookie có **Domain=example.com**, expiration thường cần cùng Domain, trong khi host-only cookie không có Domain cần xóa theo host-only semantics.

**Cookie được xác định bởi tên và phạm vi host/domain/path theo cơ chế cookie jar**, không phải chỉ tên. Điều kiện xóa phải phản ánh cách cookie ban đầu được set; SameSite/HttpOnly/Secure là attributes cần nhất quán bảo vệ, còn Path/Domain là những yếu tố quan trọng để chọn đúng cookie.

### 8.2. Ví dụ expire cookie __Host-APPSESSION

Nếu app phát cookie:

~~~http
Set-Cookie: __Host-APPSESSION=opaque; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

server có thể gửi:

~~~http
Set-Cookie: __Host-APPSESSION=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
~~~

**__Host-** phải có Secure, Path=/ và không có Domain. Response phải đến từ host/scheme phù hợp. Nếu app dùng một cookie với tên tương tự nhưng Domain khác hoặc Path khác, chính sách xóa cần xem xét theo thực tế — không đặt Domain cho một cookie __Host-.

### 8.3. JavaScript không xóa cookie HttpOnly trực tiếp

Một cookie **HttpOnly** không được đọc/ghi bằng document.cookie theo cơ chế browser chuẩn. Vì vậy:

~~~javascript
// Không thể dùng document.cookie để xóa HttpOnly session cookie
// nếu JavaScript không có quyền thao tác cookie đó.
document.cookie = "JSESSIONID=; Max-Age=0; Path=/";
~~~

Đây **không phải giải pháp thay server Set-Cookie/logout**. Cũng không suy rằng xóa cookie bằng JavaScript đã invalidate server session.

Với các cookies không HttpOnly do frontend thực sự sở hữu, JS có thể expire bằng document.cookie khi đúng name/Path/Domain và browser policy cho phép. Cần tránh xóa những cookies của ứng dụng khác dùng chung origin/domain nếu không thuộc phạm vi logout.

### 8.4. Xóa cookie tại một subdomain không xóa mọi cookie

Ví dụ:

~~~text
app.example.com:    __Host-APPSESSION (host-only)
accounts.example.com: SSO_SESSION  (host-only)
.example.com:       shared-preference (Domain=example.com)
~~~

Một response từ app.example.com **không có quyền tùy ý xóa host-only cookie của accounts.example.com**. Cookie Domain rộng có thể được ảnh hưởng bởi các hosts đủ điều kiện, nhưng cách xóa tác động đến các ứng dụng khác và phải được thiết kế rõ.

Đặc biệt với **Clear-Site-Data: "cookies"**, phạm vi có thể rộng hơn kỳ vọng của một app (bao gồm cookies cho registered domain và subdomains trong những browser hỗ trợ). Xem mục 11 trước khi bật.

### 8.5. Tên cookie giống nhau ở nhiều Path

DevTools có thể hiển thị hai cookie JSESSIONID:

~~~text
JSESSIONID=abc; Path=/
JSESSIONID=def; Path=/app
~~~

Xóa cookie ở Path=/ có thể không xóa cookie Path=/app. Đồng thời, các requests tới /app có thể gửi nhiều cookies cùng tên, tạo nhầm lẫn trong session resolver. Tránh cấu hình chồng lắp và test **Cookie header thực gửi tới protected route** sau logout.

### 8.6. SameSite và logout cross-site

Nếu frontend ở app.example.com và API/IdP ở một site khác, cookie SameSite=Lax/Strict có thể không được gửi cho cross-site fetch POST tùy ngữ cảnh. Cần:

- Xác định **origin khác** có đồng nghĩa **site khác** không.
- Thiết kế SameSite=None; Secure cho những ngữ cảnh cross-site cookie thật sự cần, có cân nhắc privacy restrictions/third-party cookie blocking.
- Dùng credentials: include khi fetch cross-origin dựa vào cookie.
- CORS allowlist cụ thể và Allow-Credentials phù hợp.
- CSRF token/correlation khi có cookie tự gửi.
- Test browser thực tế; curl không thực thi SameSite/CORS như browser.

Một POST /logout không mang cookie phù hợp có thể **chỉ logout anonymous request**, trong khi authenticated cookie vẫn tồn tại tại origin khác. Đừng tuyên bố global logout thành công nếu app đang nhắm sai cookie/site.

## 9. Dữ liệu phía client: JavaScript memory, Web Storage, IndexedDB và service worker

Một ứng dụng có thể có SecurityContext đúng và session đã bị hủy, nhưng **frontend đã ghi dữ liệu ngoài session**. Với SPA hoặc PWA, đây thường là nguồn còn sót lớn nhất.

### 9.1. JavaScript memory/DOM là bản sao có thật

Thông tin user có thể nằm trong:

- React/Vue/Angular component state.
- Redux/Pinia/NgRx stores hoặc global singleton objects.
- JavaScript variables giữ access token/refresh token.
- DOM nodes của trang dashboard.
- Web workers đang hoạt động.
- Các request đang pending và callbacks sẽ cập nhật UI.
- GraphQL/React Query/SWR/HTTP client in-memory caches.
- Browser form controls đang giữ nội dung người dùng nhập.

**Chuyển route sang /login không tự dọn toàn bộ những dữ liệu đó**, nhất là SPA giữ root app và store còn sống. Khi logout, cần **reset auth-scoped state** một cách tập trung, abort/cancel pending requests và bảo đảm response của request cũ không ghi dữ liệu vào UI sau logout.

### 9.2. sessionStorage theo tab; localStorage theo origin

| API | Phạm vi phổ biến | Hậu quả khi logout |
| --- | --- | --- |
| **sessionStorage** | Theo origin và top-level browsing context/tab (có nuance khi tab được mở/copy). | Một tab không tự xóa sessionStorage của mọi tab khác. |
| **localStorage** | Theo origin, thường chia sẻ giữa tabs cùng origin. | Dữ liệu tồn tại sau reload/browser restart nếu không được xóa. |
| **IndexedDB** | Theo origin, asynchronous và dung lượng lớn. | Offline data/user records vẫn nằm lại. |
| **Cache Storage** | Theo origin, do app/service worker kiểm soát. | Responses/HTML/JSON offline có thể tiếp tục được phục vụ. |
| **Service worker registration** | Theo origin + scope, chạy tách khỏi trang. | Có thể tiếp tục intercept fetch/navigation nếu không có policy dọn cache. |
| **In-memory state** | Theo page lifetime, có thể giữ trong BFCache. | Browser Back có thể phục hồi snapshot cũ. |

**Origin** gồm scheme, host, port. Hai ứng dụng ở hai subdomain thường **không có chung localStorage/IndexedDB**; một ứng dụng không thể tùy tiện gọi localStorage.clear cho origin khác. **Site** và **origin** không nên nhầm khi thiết kế cleanup.

### 9.3. Không lưu bearer token tùy ý trong localStorage

Nếu access/refresh token nằm trong JavaScript-readable storage, một XSS trong origin có thể đọc chúng. HttpOnly Secure cookie thường giảm khả năng JS trực tiếp đọc session token, nhưng có tradeoffs với **CSRF và SameSite**; không có một lựa chọn lưu token áp dụng cho mọi hệ thống.

Khi logout:

- Clear tokens khỏi memory/owned storage.
- Thu hồi server-side refresh token/credential mà app có thể revoke.
- Không ghi token vào logs, analytics, URL hoặc exception.
- Không tin chỉ xóa localStorage là ngăn được **bản sao token bị lấy từ trước**.
- Với applications dùng cookie auth, đừng xóa/mở HttpOnly cookie bằng JS; server Set-Cookie + invalidation phải chịu trách nhiệm.

### 9.4. Dọn keys theo namespace thay vì xóa mọi thứ trên origin

Ví dụ:

~~~javascript
function clearOwnStorage() {
  const ownedLocalKeys = [
    "myapp:profile",
    "myapp:permissions",
    "myapp:lastViewedOrder",
    "myapp:sessionHint"
  ];

  for (const key of ownedLocalKeys) {
    localStorage.removeItem(key);
  }

  const ownedTabKeys = [
    "myapp:activeWorkspace",
    "myapp:unsavedDraftPreview",
    "myapp:csrfToken"
  ];

  for (const key of ownedTabKeys) {
    sessionStorage.removeItem(key);
  }
}
~~~

**Không mặc định gọi localStorage.clear()** nếu origin có nhiều ứng dụng hoặc các keys không thuộc ứng dụng này; điều đó có thể xóa dữ liệu của người dùng/ứng dụng khác ngoài phạm vi logout. Ngược lại, nếu chỉ xóa vài keys nhưng app còn dữ liệu nhạy cảm tại keys khác, cần hoàn thiện **inventory dữ liệu** thay vì tuyên bố đã dọn sạch.

### 9.5. IndexedDB cần thao tác bất đồng bộ và kiểm soát schema

Ví dụ xóa một database **do ứng dụng sở hữu**:

~~~javascript
function deleteOwnedIndexedDb(dbName) {
  return new Promise((resolve, reject) => {
    const request = indexedDB.deleteDatabase(dbName);

    request.onsuccess = () => resolve();
    request.onerror = () =>
      reject(request.error ?? new Error("IndexedDB delete failed"));

    request.onblocked = () =>
      reject(new Error("Other tabs still have the database open"));
  });
}

async function clearOwnedIndexedDb() {
  await deleteOwnedIndexedDb("myapp-offline-user-data");
}
~~~

Việc xóa có thể bị **blocked** do tab/worker khác giữ connection tới DB. Một app thực cần đóng các connections trước logout, gửi thông báo tới tabs khác và có retry/error UX phù hợp. **Không coi Promise resolved ngay** nếu browser vẫn chưa hoàn thành thao tác; cũng không đảm bảo xóa được cơ sở dữ liệu do origin khác quản lý.

Nếu PWA cần giữ offline data không nhạy cảm (ví dụ dữ liệu công khai), có thể xóa **record/table chứa user data** thay vì toàn bộ DB. Đây là quyết định data classification, retention và privacy policy.

### 9.6. Cache Storage riêng với HTTP cache

Ví dụ xóa các caches có prefix app do service worker dùng:

~~~javascript
async function clearOwnedCacheStorage() {
  if (!("caches" in window)) return;

  const names = await caches.keys();
  const owned = names.filter(name =>
    name.startsWith("myapp-user-cache-")
  );

  await Promise.all(owned.map(name => caches.delete(name)));
}
~~~

**Cache Storage có thể chứa cả JSON đã authenticated và tài nguyên offline** nếu service worker/app từng gọi cache.put. Việc một response có Cache-Control: no-store **không phải bảo đảm rằng custom service worker sẽ không chủ động giữ bản sao đó** nếu code của bạn cache nó không đúng thiết kế.

Không cache nội dung tài khoản bằng tên cache dùng chung giữa user A và user B. Với dữ liệu user-specific, có **partitioning theo user/session** hoặc tốt hơn **không offline-cache sensitive responses**; nếu có partitioning, không để raw user ID/token thành tên cache dễ lộ.

### 9.7. Service worker có lifecycle riêng

Service worker có thể intercept requests và phục vụ **offline HTML hoặc API data đã cached**. Vì thế server trả 401 sau logout nhưng khi browser offline, service worker vẫn có thể đưa ra trang private cũ.

Phòng vệ:

1. **Không cache authenticated API responses** trừ khi có yêu cầu/offline threat model rõ.
2. Nếu cache user data, phân vùng + xóa khi logout; không giữ cache sau account switch.
3. Đặt quy tắc **network-only/no-store** cho endpoints nhạy cảm.
4. Khi logout, gửi message tới service worker nếu có handler được kiểm soát để dọn caches của app.
5. Kiểm tra nhiều tabs/clients đang được service worker quản lý và cách xử lý message mất.
6. Không tự gọi unregister() với mọi service worker trên origin nếu điều đó phá ứng dụng khác; chỉ unregister worker do app sở hữu theo chính sách.
7. Offline logout có thể chỉ **xóa trạng thái local**, chưa revoke session ở server; cần báo đúng giới hạn cho user.
8. Test bằng cách chuyển **Network → Offline**, refresh protected route rồi dùng Back/Forward.

### 9.8. Không dùng browser storage làm nguồn quyền

Một cờ:

~~~javascript
localStorage.setItem("myapp:isAuthenticated", "true");
~~~

chỉ là **dữ liệu client**. Khi API nhận request, Spring Security phải xác thực cookie/token và kiểm tra authorization. Sau logout, xóa cờ trên để UI cập nhật, nhưng không bao giờ cho một request truy cập API chỉ vì cờ này còn true.

### 9.9. Dữ liệu ở forms và password managers

Browser có thể giữ autofill, email được nhập, form state hoặc credential trong password manager. Website không có quyền tin cậy **xóa mật khẩu đã lưu ở password manager của người dùng** khi logout. Đừng dùng mẹo vô hiệu password manager để “tăng an toàn” nếu điều đó làm user phải dùng mật khẩu yếu/khó quản lý.

Với ứng dụng trên thiết bị dùng chung, nên hướng dẫn người dùng đóng tab/browser, đăng xuất khỏi hệ thống thiết bị và tránh lưu credential vào password manager dùng chung, tùy chính sách tổ chức. Logout web không thay biện pháp bảo vệ thiết bị.

## 10. HTTP cache, BFCache, Back button và dữ liệu đã hiển thị

Đây là phần cần phân biệt rõ **security state phía server** với **content đã được browser lưu**.

### 10.1. Cache-Control: no-store cho tài nguyên nhạy cảm

Ví dụ response authenticated chứa thông tin cá nhân:

~~~http
HTTP/1.1 200 OK
Content-Type: text/html; charset=UTF-8
Cache-Control: no-store

<html>... thông tin account ...</html>
~~~

**no-store** chỉ thị HTTP caches không lưu response theo cơ chế caching chuẩn. Nó mạnh hơn **private** (chỉ cho cache cá nhân) và khác **no-cache** (có thể lưu nhưng phải revalidate trước khi dùng lại).

| Cache directive | Ý nghĩa chính | Có đủ để xóa mọi dữ liệu browser? |
| --- | --- | --- |
| **public** | Cho shared caches lưu khi đủ điều kiện. | Không phù hợp nhiều response riêng tư. |
| **private** | Cho browser/private cache lưu, hạn chế shared cache. | Không. |
| **no-cache** | Có thể lưu nhưng cần revalidation trước khi reuse. | Không. |
| **no-store** | Chỉ thị caches không lưu response. | Không xóa screenshot, downloads, JS memory hoặc mọi BFCache snapshot. |
| **max-age=0, must-revalidate** | Điều khiển độ mới/revalidation. | Không tương đương no-store. |

**Spring Security thường thiết lập một số cache-control headers mặc định**, nhưng không nên giả định mọi response **qua controller, gateway, CDN, service worker và tài nguyên tĩnh** đều nhận chính sách mong muốn. Kiểm tra HTTP headers thực tế, đặc biệt những response render dữ liệu người dùng.

### 10.2. BFCache không đơn giản là HTTP cache

**Back-forward cache (BFCache)** có thể giữ **snapshot của document, DOM và JavaScript runtime state** để browser quay lại nhanh mà không phải tải lại trang bằng network. Đây không chỉ là một HTTP cached response bình thường.

Trình duyệt có điều kiện riêng để chọn page được đưa vào BFCache. **Không hứa Cache-Control: no-store sẽ luôn loại bỏ mọi snapshot ở mọi browser/version**; hỗ trợ và chính sách BFCache thay đổi theo browser.

Sau logout, user nhấn Back có thể thấy snapshot account **dù GET /api/me mới sẽ trả 401**. Ứng dụng phải giải quyết cả yếu tố hiển thị và server authorization.

### 10.3. Revalidate khi page được phục hồi

Một frontend có thể lắng nghe sự kiện **pageshow** — nó có thuộc tính **persisted** khi trang được phục hồi từ BFCache trong nhiều browser — để kiểm tra trạng thái auth:

~~~javascript
window.addEventListener("pageshow", event => {
  if (event.persisted) {
    void refreshAuthStateFromServer();
  }
});

async function refreshAuthStateFromServer() {
  try {
    const response = await fetch("/api/me", {
      credentials: "include",
      cache: "no-store"
    });

    if (response.status === 401) {
      clearSensitiveUiImmediately();
      navigateToLogin();
      return;
    }

    if (!response.ok) {
      hideSensitiveUiUntilVerified();
      return;
    }

    updatePrincipalState(await response.json());
  } catch {
    // Không coi network error là bằng chứng user vẫn authenticated.
    hideSensitiveUiUntilVerified();
  }
}
~~~

Các hàm UI là **hàm của ứng dụng**, không phải browser API dựng sẵn. Trong thiết kế nghiêm ngặt, nên **ẩn sensitive UI ngay khi page được re-activated** trước lúc async fetch hoàn tất, tránh màn hình riêng tư được hiển thị trong khoảng chờ network.

Lưu ý: pageshow persisted không bao trùm mọi trường hợp **tab khác logout, refresh token expire, page vẫn đang visible hoặc service worker cache**. Bổ sung **visibilitychange, broadcast logout, route guards, API 401 handlers** theo thiết kế, không dựa vào một sự kiện duy nhất.

### 10.4. Không tải lại protected data từ cache khi session không còn

SPA data-fetching libraries có thể dùng in-memory cache. Sau logout, một navigation vào /app/orders có thể trả cache hit ngay, trước khi API kiểm tra session.

Phòng vệ:

- Reset authenticated data stores/cache khi logout.
- Không render account-specific content từ cache trước revalidation ở những view nhạy cảm.
- Đánh dấu data cache gắn với **principal/session generation** và invalidate khi identity đổi.
- Bỏ/cancel pending queries và bỏ kết quả của request bắt đầu trước logout.
- Khi API trả 401/403, xử lý **mất quyền hoặc auth expired** theo contract, không chỉ hiển thị cached success.
- Không phân biệt quyền chỉ bằng cờ local isLoggedIn.

### 10.5. Browser history, address bar và download

**History** có thể tiếp tục chứa URL đã truy cập. Website có thể dùng **history.replaceState** cho navigation hiện tại ở những trường hợp phù hợp, nhưng **không được phép xóa toàn bộ history của người dùng** hoặc các entries thuộc origin khác.

Vì thế:

- Tránh đặt token, session ID hoặc dữ liệu bí mật trong query/fragment URL.
- Dùng Referrer-Policy phù hợp để hạn chế tiết lộ URL cho website ngoài.
- Không coi chuyển về /login là đã xóa mọi URL trong lịch sử.
- File download, print/PDF, clipboard, screenshot đã được tạo **không bị server logout thu hồi**.
- Nếu thiết bị công cộng, sử dụng chính sách workstation/kiosk và hướng dẫn bảo vệ thiết bị thay vì hứa web app có thể dọn toàn bộ máy.

### 10.6. Offline PWA và “đã logout nhưng vẫn thấy trang”

Khi service worker trả cached HTML/JSON ở chế độ offline, không có request mới tới Spring Security. **Server-side authorization chỉ áp dụng khi request thực sự đến server**; nội dung đã lưu offline là một **bản sao dữ liệu**.

Nếu yêu cầu sản phẩm không cho giữ dữ liệu nhạy cảm offline, cần **chính sách không cache từ đầu**, không chỉ đợi tới logout để xóa. Nếu chấp nhận offline dữ liệu nhạy cảm, cần threat model về local encryption, key handling, expiration, user switch, delete reliability và nguy cơ dữ liệu trên thiết bị bị mất/đánh cắp.

## 11. Clear-Site-Data: dọn dữ liệu browser bằng response header

**Clear-Site-Data** là một HTTP response header mà một số trình duyệt hỗ trợ để xóa các nhóm dữ liệu gắn với origin/site theo chỉ thị. Nó là **lớp bổ sung** cho logout, không phải một API bắt buộc mọi browser phải thi hành và không thể thay việc invalidate session/token ở server.

### 11.1. Các chỉ thị thường gặp

~~~http
Clear-Site-Data: "cache", "cookies", "storage"
~~~

| Chỉ thị | Dữ liệu hướng tới | Điều cần lưu ý |
| --- | --- | --- |
| **"cache"** | Các dữ liệu cache do browser quản lý cho phạm vi áp dụng. | Không đồng nghĩa xóa download/screenshot hoặc cache ở proxy khác. |
| **"cookies"** | Cookies theo phạm vi domain/site mà browser áp dụng. | Có thể tác động **nhiều subdomain/app dùng chung registrable domain**, cần đánh giá trước. |
| **"storage"** | Dữ liệu storage origin như Web Storage, IndexedDB, Cache Storage và có thể service worker registrations theo browser implementation. | Có thể xóa dữ liệu **không thuộc riêng tính năng logout**, kể cả ứng dụng khác cùng origin. |
| **"executionContexts"** | Cơ chế yêu cầu reload/clear execution contexts ở browser hỗ trợ. | Hỗ trợ và hành vi khác nhau, không giả định mọi tab bị đóng hoặc reset tức thì. |

Không phải mọi browser/version hỗ trợ tất cả chỉ thị và có thể có giới hạn ở một số ngữ cảnh. **Đọc tài liệu browser hỗ trợ mà dự án dùng và kiểm thử thực tế**. Header cần được gửi trong ngữ cảnh an toàn, thông thường qua **HTTPS**.

### 11.2. Nguy cơ xóa rộng vì shared domain

Giả sử:

~~~text
accounts.example.com   → hệ thống SSO
app.example.com        → ứng dụng chính
admin.example.com      → dashboard quản trị
other.example.com      → ứng dụng khác
~~~

Nếu app.example.com bật **Clear-Site-Data: "cookies"**, phạm vi xóa cookies có thể ảnh hưởng nhiều host cùng registrable domain trong những browser hỗ trợ. Điều đó có thể làm người dùng **bị logout ở ứng dụng khác** dù họ chỉ muốn logout một ứng dụng.

Nếu nhiều ứng dụng chia sẻ **cùng origin** khác path, chỉ thị **"storage"** có thể xóa localStorage/IndexedDB/Cache Storage chung, không chỉ dữ liệu của /app. Đây không phải cơ chế dọn dữ liệu theo path.

**Chọn chỉ thị theo data ownership và mô hình SSO, không copy cả ba vào mọi logout response.**

### 11.3. Mẫu response logout với header có chủ đích

Với một **origin dành riêng cho ứng dụng** và đã đánh giá ảnh hưởng:

~~~http
HTTP/1.1 204 No Content
Cache-Control: no-store
Clear-Site-Data: "cache", "storage"
Set-Cookie: __Host-APPSESSION=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax
~~~

Đây là **ví dụ có chủ ý không bật "cookies"**, vì app tự expire cookie session đang sở hữu và không muốn xóa cookies của những ứng dụng khác trên cùng parent domain. Trong deployment khác, quyết định có thể khác; cũng cần kiểm tra response thực có bị proxy lọc header không.

**Clear-Site-Data không xóa token đã được copy ra ngoài browser**, cũng không thể revoke server session, JWT hoặc IdP session. Header này chỉ giúp browser hợp tác dọn một số trạng thái local.

### 11.4. Chỉ phát ở response logout đã xác minh

Đừng đặt:

~~~http
Clear-Site-Data: "storage"
~~~

lên **mọi response 401/403** hoặc mọi trang /login, vì một lỗi CSRF, sự cố mạng hoặc một link không mong đợi có thể xóa dữ liệu app/offline của user dù họ chưa chủ động đăng xuất.

Nếu sử dụng trên logout response, hãy phân biệt **logout request thật được server xử lý** với GET render trang login. Khi endpoint logout nhận POST thiếu CSRF, không phát một header dọn storage ngoài ý định chỉ để UI “trông như đã logout”.

### 11.5. Servlet SuccessHandler phát Clear-Site-Data có điều kiện

~~~java
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.web.authentication.logout
        .LogoutSuccessHandler;

// Minh họa cho origin dành riêng và sau khi đã đánh giá
// tác động lên caches và storage của browser.
LogoutSuccessHandler clearOwnedBrowserData =
        (request, response, authentication) -> {
            response.setStatus(
                    HttpServletResponse.SC_NO_CONTENT);
            response.setHeader(
                    "Cache-Control", "no-store");
            response.setHeader(
                    "Clear-Site-Data", "\"cache\", \"storage\"");
        };

// Dùng trong HttpSecurity.logout(...):
// .logoutSuccessHandler(clearOwnedBrowserData)
~~~

Nếu sản phẩm cần giữ offline drafts thuộc user, dọn toàn bộ "storage" có thể là hành động quá rộng; khi đó **xóa keys/databases/caches theo namespace bằng client code** và server token revocation có thể phù hợp hơn.

Header không bảo đảm thực thi trên browser không hỗ trợ. Không dùng việc header xuất hiện trong Network làm bằng chứng storage đã được xóa; phải kiểm tra **Storage/IndexedDB/Cache Storage** và các tabs thực tế.

### 11.6. Clear-Site-Data không thay script cleanup

Ngay cả khi server dùng Clear-Site-Data, ứng dụng vẫn có thể cần:

- **Clear sensitive in-memory state/DOM** trong tab hiện tại.
- **Broadcast logout** cho tabs đang mở.
- **Cancel in-flight requests**, drop results đến muộn.
- Đặt route guards và revalidate principal khi tab được phục hồi.
- Xử lý browser không hỗ trợ directive.
- Xác minh request mới bị từ chối ở backend.

Ở chiều ngược lại, **script cleanup cũng không thay invalidate server session hoặc revoke token**.

## 12. Logout cho SPA: multi-tab, async requests và nguồn sự thật

### 12.1. Mục tiêu của một logout coordinator

Giả sử user mở hai tabs cùng origin:

~~~text
Tab A: /app/account   → lưu tên và thông tin cá nhân trong memory
Tab B: /app/orders    → lưu orders trong IndexedDB/React Query
Tab A: POST /logout   → server invalidates session
Tab B:                 vẫn đang hiển thị orders
~~~

Các tabs **chia sẻ cookie theo phạm vi tương ứng**, nhưng **không tự động clear memory/DOM của nhau**. Một tab có thể tiếp tục hiển thị dữ liệu cũ dù API từ chối.

Mục tiêu:

1. Tab logout ngay lập tức không còn render sensitive data.
2. Các tabs còn mở cùng origin được thông báo để dọn local state.
3. Pending fetch trước logout không làm render lại dữ liệu sau logout.
4. Khi tab được mở lại/phục hồi sau Back, nó xác minh lại trạng thái auth.
5. Nếu server logout chưa được xác nhận do mạng, client không báo sai “đã logout khỏi mọi thiết bị”.
6. Dữ liệu nằm ở những origin/IdP khác **không được cho là đã dọn** nếu không có giao thức phối hợp.

### 12.2. BroadcastChannel theo origin

~~~javascript
const logoutChannel = "BroadcastChannel" in window
  ? new BroadcastChannel("myapp-auth-events")
  : null;

let authGeneration = 0;
let logoutPending = false;

function clearSensitiveClientState() {
  authGeneration += 1;
  logoutPending = true;

  // Các hàm app-specific:
  cancelAuthenticatedRequests();
  clearAuthenticatedDataStores();
  clearOwnStorage();
  hidePrivateViews();
}

function onLogoutFromAnotherTab(event) {
  if (event.data?.type !== "LOGOUT") return;
  if (event.data?.version !== 1) return;

  clearSensitiveClientState();
  navigateToLogin();
}

logoutChannel?.addEventListener(
  "message", onLogoutFromAnotherTab);
~~~

**BroadcastChannel không phải một lệnh xóa dữ liệu toàn thiết bị**: nó truyền message tới những contexts cùng origin và được browser hỗ trợ, còn tabs đã đóng, origin khác, browser profile khác hoặc thiết bị khác không nhận trực tiếp.

Bất kỳ script chạy trong cùng origin đều có thể gửi BroadcastChannel message; **đừng coi message này là bằng chứng authentication hay quyền**, chỉ là một tín hiệu cần dọn UI cục bộ. Server vẫn quyết định credential còn hợp lệ hay không.

### 12.3. Logout chủ động: dọn local trước, xác minh server riêng

~~~javascript
async function logoutCurrentBrowser() {
  // Che sensitive UI ngay khi người dùng chọn logout.
  clearSensitiveClientState();

  // Các tabs đang mở xóa state cùng origin.
  logoutChannel?.postMessage({
    type: "LOGOUT",
    version: 1
  });

  let confirmedByServer = false;

  try {
    const csrf = getCurrentCsrfToken();

    const response = await fetch("/logout", {
      method: "POST",
      credentials: "include",
      headers: { "X-CSRF-TOKEN": csrf },
      cache: "no-store"
    });

    confirmedByServer = response.status === 204;

  } catch {
    // Network error: server có thể đã logout hoặc chưa.
  } finally {
    await cleanupOwnedOfflineDataBestEffort();
    navigateToLogin();
  }

  if (!confirmedByServer) {
    showLogoutNotConfirmedNotice();
    // Không cho UI tự đăng nhập lại chỉ vì session cookie còn.
    // Ứng dụng cần retry/reconciliation policy phù hợp.
  }

  return confirmedByServer;
}
~~~

**getCurrentCsrfToken**, **cleanupOwnedOfflineDataBestEffort**, **navigateToLogin** và các hàm khác là **hàm của ứng dụng**. Đoạn code minh họa trạng thái **logoutPending** để UI không tự dựa vào GET /api/me thành công sau một lỗi mạng và hiển thị lại dữ liệu nhạy cảm ngay.

Một sản phẩm thực cần quản lý **retry/logout confirmation và xử lý error status cụ thể**, không tự retry vô hạn hoặc gửi lại token cũ sau session invalidation. Nếu backend báo 403 CSRF thì server logout có thể chưa chạy; frontend vẫn có thể ẩn UI và cảnh báo chưa xác nhận.

### 12.4. Chặn response cũ ghi dữ liệu mới vào UI

Giả sử GET /api/account bắt đầu trước logout, nhưng network trả response sau khi user đã logout. Nếu callback vẫn ghi vào React store, hồ sơ có thể **xuất hiện lại trong tab đã logout**.

Một mẫu kiểm soát generation:

~~~javascript
async function fetchPrivateProfile() {
  const requestGeneration = authGeneration;

  const response = await fetch("/api/me", {
    credentials: "include",
    cache: "no-store"
  });

  if (!response.ok) {
    if (response.status === 401) clearSensitiveClientState();
    return;
  }

  const profile = await response.json();

  // Bỏ kết quả đã bắt đầu trước khi logout/account switch.
  if (requestGeneration !== authGeneration || logoutPending) {
    return;
  }

  updatePrincipalState(profile);
}
~~~

Điều này **giảm rò từ race trong UI**, không thay backend authorization. Với abort controllers, vẫn kiểm tra generation vì abort không phải lúc nào cũng ngăn callback đã hoàn tất xử lý.

### 12.5. localStorage storage event và các phương án fallback

Có thể dùng **storage event** của localStorage để truyền tín hiệu cùng origin giữa tabs; nhưng event không được gửi tới chính tab tạo thay đổi và phụ thuộc storage availability/browser policy. Không dùng một key chứa token để signal; chỉ dùng **event marker không nhạy cảm**.

Ví dụ:

~~~javascript
localStorage.setItem(
  "myapp:logout-signal",
  String(Date.now())
);
~~~

Nếu browser chặn storage hoặc Clear-Site-Data xóa storage sớm, tín hiệu có thể không tới mọi tab. Vì vậy phải có **fallback revalidation khi pageshow/visibilitychange, route navigation và API 401**.

### 12.6. Không truyền token qua BroadcastChannel

BroadcastChannel là cơ chế **đồng bộ sự kiện**, không phải nơi vận chuyển session ID, refresh token, CSRF token hoặc PII. Một message logout đơn giản là đủ:

~~~json
{"type":"LOGOUT","version":1}
~~~

Nếu hệ thống truyền token giữa tabs, nó mở thêm đường rò khi origin bị XSS. Không dùng BroadcastChannel như cơ chế authentication hoặc permission granting.

### 12.7. Cross-origin tabs không nhận cùng BroadcastChannel

Một tab **app.example.com** không nhận BroadcastChannel trực tiếp từ **accounts.example.com** vì khác origin. Nếu sản phẩm cần đồng bộ:

- Dựa vào **server-side shared session/revocation** và các lần revalidation.
- Dùng giao thức SSO logout/front-channel/back-channel phù hợp, có kiểm tra state/origin.
- Nếu dùng postMessage giữa các windows hợp lệ, kiểm tra **targetOrigin và event.origin**, không postMessage với wildcard tới bên không tin cậy.
- Không công khai access/refresh tokens qua thông điệp cross-origin.
- Không giả định logout từ một ứng dụng con sẽ logout mọi subdomain có cookie riêng.

## 13. SSO, OAuth2/OIDC: logout khỏi ứng dụng khác logout tại IdP

Trong môi trường doanh nghiệp, Spring Security có thể đóng vai trò **OAuth2/OIDC client**. User có session tại ứng dụng A và đồng thời có **IdP SSO session** tại nhà cung cấp danh tính. Việc hủy session của app A không tự làm IdP session biến mất.

### 13.1. Ba phạm vi khác nhau

~~~mermaid
flowchart LR
    B["Browser: app.example.com"] --> A["Application A session"]
    B --> I["Identity Provider session"]
    B --> C["Application B session"]
    A -.->|"Local logout"| X["Invalidate A only"]
    I -.->|"RP-initiated logout (if configured)"| Y["IdP logout flow"]
    I -.->|"Back-channel event (if supported)"| Z["Revoke relying-party sessions"]
~~~

| Hành động | Thường tác động | Không tự bảo đảm |
| --- | --- | --- |
| **Logout local app** | HttpSession/WebSession và credential của app. | IdP và app B logout. |
| **RP-Initiated Logout (OIDC)** | Browser/ứng dụng được chuyển qua endpoint logout IdP theo giao thức. | Mọi relying party hoặc session thiết bị khác bị xóa nếu provider không hỗ trợ. |
| **Front-channel logout** | Browser điều hướng/nhúng request logout tới các clients theo cơ chế IdP hỗ trợ. | Sẽ hoạt động khi browser chặn third-party cookies/iframes. |
| **Back-channel logout** | IdP gửi thông điệp server-to-server cho RP, yêu cầu revoke phiên liên quan. | Browser localStorage/DOM được dọn ngay không cần client revalidation. |
| **Global account session revocation** | Registry sessions/refresh tokens theo policy. | Dữ liệu offline/browser history/downloads bị xóa. |

### 13.2. Spring Security OAuth2 Login và OIDC Logout

Trên Servlet, Spring Security có hỗ trợ xây dựng **OIDC client-initiated logout** bằng các thành phần như **OidcClientInitiatedLogoutSuccessHandler** khi ứng dụng đăng nhập qua OIDC, có ClientRegistrationRepository và provider metadata phù hợp.

Ý tưởng tích hợp:

~~~java
import org.springframework.security.oauth2.client.registration
        .ClientRegistrationRepository;
import org.springframework.security.oauth2.client.oidc.web.logout
        .OidcClientInitiatedLogoutSuccessHandler;

OidcClientInitiatedLogoutSuccessHandler oidcLogout =
        new OidcClientInitiatedLogoutSuccessHandler(
                clientRegistrationRepository);

// URI này phải phù hợp client/provider registration và được kiểm soát.
oidcLogout.setPostLogoutRedirectUri("{baseUrl}/signed-out");

// Trong HttpSecurity.logout(...):
// .logoutSuccessHandler(oidcLogout)
~~~

**clientRegistrationRepository** là dependency ứng dụng; đoạn này là ví dụ gắn handler, không phải toàn bộ cấu hình oauth2Login. Cần kiểm tra endpoint đăng xuất của IdP, id_token_hint và các điều kiện giao thức tương ứng trong phiên bản Spring Security sử dụng.

**Không nhận post_logout_redirect_uri từ query returnTo tùy ý** rồi chuyển cho IdP. Chỉ dùng URI thuộc allowlist/đăng ký theo provider policy. Tương tự, không tự chuyển mọi response lỗi callback tới một domain do client khai.

### 13.3. OIDC logout không giống OAuth2 access token revocation

- **RP-Initiated Logout** nhằm xử lý session SSO theo giao thức.
- **OAuth2 token revocation endpoint** nhằm vô hiệu token phù hợp nếu provider hỗ trợ.
- **App session invalidation** nhằm chấm dứt session tại Spring Security.
- **Browser cleanup** nhằm loại bỏ dữ liệu còn nằm ở tab/cache/storage.
- **Logout mọi thiết bị** là một workflow identity/device khác có thể cần nhiều biện pháp.

Một call tới endpoint logout IdP không tự chứng minh mọi access/refresh tokens đã bị revoke hoặc mọi app cookie bị expire. Phải đọc provider semantics và kiểm tra thực tế.

### 13.4. Back-channel logout cần xác thực thông điệp

Khi IdP gửi một **logout token** server-to-server, RP phải xác minh token theo giao thức/policy, ví dụ:

- Chữ ký, issuer, audience và thời hạn/thời gian.
- Cấu trúc sự kiện logout và các claims bắt buộc.
- sid hoặc sub đúng với session/subject liên quan.
- Chống replay và quản lý token IDs/event IDs phù hợp.
- Map tới đúng sessions của user/client/tenant, không thu hồi account khác.
- Xử lý duplicate delivery/idempotency và lỗi shared store.

**Không nhận một POST JSON chưa ký từ Internet nói "logout user 123" rồi xóa session theo userId trong body**. Đây là endpoint có ranh giới tin cậy riêng, không thay bằng CORS hay một header tùy ý.

Ngay cả khi back-channel đã thu hồi session, các tabs đang mở **có thể vẫn hiển thị DOM/cache cũ**; cần UI revalidation, API 401 và browser cleanup tại thời điểm browser biết mình đã mất session.

### 13.5. Logout callback và CSRF/CORS

Form logout local dùng **POST + CSRF** trong mô hình session cookie. Các callback OAuth2/OIDC/back-channel có thể có phương thức và xác minh giao thức riêng:

- Không tự áp một CSRF token form vào mọi callback nếu nó không thuộc giao thức tương ứng.
- Chỉ cân nhắc CSRF matcher exception **đúng endpoint giao thức** khi có cơ chế xác minh state/token/signature thay thế phù hợp.
- Không tắt CSRF toàn site để một callback hoạt động.
- CORS không chứng minh callback đến từ IdP; HTTP client ngoài browser có thể tự đặt Origin.
- Front-channel iframe có thể bị chặn cookie/third-party tracking protections; không mặc định nó hoàn tất trong mọi browser.

### 13.6. Điều user có thể kỳ vọng sau SSO logout

Tùy provider, logout khỏi IdP có thể khiến lần truy cập protected route tiếp theo yêu cầu login lại. Nhưng một app khác có session riêng vẫn có thể tiếp tục authenticated nếu chưa nhận thông điệp logout phù hợp.

Giao diện nên diễn đạt chính xác: **“Đã đăng xuất khỏi ứng dụng này”** hoặc **“Yêu cầu đăng xuất SSO đã được thực hiện”** theo kết quả thật, tránh cam kết quá mức rằng tất cả thiết bị và bản sao dữ liệu đã được xóa.

## 14. Concurrency, distributed session và những race sau logout

### 14.1. Logout không du hành ngược thời gian

Ví dụ:

~~~text
T0: Tab B gửi POST /api/transfer, qua authentication.
T1: Tab A gửi POST /logout, server invalidate session.
T2: POST /api/transfer của Tab B hoàn tất mutation.
T3: Browser nhận 204 logout.
~~~

Nếu POST /api/transfer **đã qua authentication tại T0**, logout ở T1 có thể không hủy tác vụ đang xử lý. Bảo vệ session ở entry point không tự rollback transaction đã chạy.

Các tác vụ nhạy cảm có thể cần:

- Authorization/reauthentication gần điểm commit.
- Idempotency và transaction isolation.
- Revocation check cho mutation rủi ro cao.
- Quy tắc hủy các tác vụ bất đồng bộ hoặc background jobs khi session revoke.
- Audit thời điểm server nhận logout và thời điểm request khác được chấp nhận.

**Đừng tuyên bố mọi request đã gửi trước logout đều chắc chắn bị hủy.**

### 14.2. Response đến muộn có thể phát cookie mới

Một GET/POST đang in-flight có thể trả **Set-Cookie** sau response logout, hoặc frontend callback từ request trước logout có thể ghi dữ liệu vào state. Khi đó browser có thể lại có cookie/DOM sau khi app vừa báo logout.

Với server, kiểm tra có tạo authenticated session mới sau khi session cũ bị invalidate hay không, session fixation/remember-me filters và cookie writer order.

Với frontend, dùng **auth generation/version**, abort requests và kiểm tra kết quả request cũ trước khi cập nhật UI (mục 12.4). Nếu request bắt đầu trước logout trả 200 ở T2, UI không nên dùng nó để phục hồi private view.

### 14.3. Spring Session/Redis và nhiều instances

~~~text
Browser → Load balancer
             ├── Spring A → shared session store
             ├── Spring B → shared session store
             └── Spring C → shared session store
~~~

Một logout từ Spring A phải được nhận biết bởi request sau đó trên Spring B/C. Nếu mỗi pod giữ authenticated state cục bộ không đồng bộ hoặc có cache session stale, có thể xuất hiện kết quả không nhất quán.

Cần kiểm tra:

- Session invalidate đã ghi vào shared store.
- Mọi instances dùng cùng repository và session cookie resolver.
- TTL, replication/failover và cache consistency semantics.
- HTTP cookies Path/Domain/SameSite thống nhất giữa gateway và instances.
- SecurityContext không bị nạp lại từ nơi khác sau invalidation.
- Trường hợp store unavailable: response success/failure có phản ánh chính sách hay không.
- Global logout có cơ chế revoke sessions across nodes và token registries.
- Session ID/token không được log raw trong phân tích.

### 14.4. Logout thành công ở một chain, nhưng API dùng chain khác

Một ứng dụng có nhiều SecurityFilterChain: chain web-session, chain REST bearer, chain actuator hoặc chain OAuth2. POST /logout có thể chỉ được xử lý bởi **web chain**, trong khi /api/** tiếp tục nhận bearer token cũ qua chain khác.

Để bảo vệ chính xác, cần kiểm tra:

1. URL/method logout được route qua chain nào.
2. Authentication tại POST logout đến từ đâu.
3. Protected resource khi test dùng **cookie session hay Authorization bearer**.
4. Các token có revoke tại issuer/resource server hay không.
5. Session/remember-me credential có bị auto-login lại không.
6. Các logout flows ở IdP và ứng dụng khác có chính sách riêng hay không.

Một test chỉ với web form session không bao phủ bearer API.

### 14.5. Logout retry khi mất mạng

**Mất mạng trong POST /logout không cho client biết chắc server đã thực hiện hay chưa**. Nếu local UI vẫn hiển thị dữ liệu, user dùng chung thiết bị có thể gặp rủi ro. Nhưng nếu UI nói “Đã logout toàn hệ thống” thì có thể là thông báo sai.

Một chiến lược an toàn:

- Dọn/ẩn sensitive UI và owned client storage ngay khi user yêu cầu logout.
- Đánh dấu server revoke **chưa được xác nhận** nếu response không nhận hoặc status không phù hợp.
- Không tiếp tục các thao tác authenticated từ tab đó.
- Cho user retry khi network phục hồi hoặc theo workflow thu hồi session/refresh token.
- Không retry credential vô hạn; xem CSRF token đã thay đổi hay chưa.
- Hướng dẫn người dùng thiết bị dùng chung đóng tab/browser khi chưa xác nhận logout.
- Khi API/IdP khả dụng, kiểm tra credential cũ bị từ chối nếu có thể kiểm thử theo policy.

### 14.6. Account switch và user-specific caches

Nếu user A logout rồi user B login ngay trên cùng browser/origin:

~~~text
A: /app/orders → cached A orders
A: POST /logout
B: POST /login
B: /app/orders → UI không được thấy cached A orders
~~~

Trong tình huống này cần:

- Reset user-scoped state/cache/storage ngay khi logout hoặc khi principal đổi.
- Không gắn dữ liệu offline của user A vào cache key chung.
- Không giữ token CSRF, permission hoặc userId cũ làm identity state cho user B.
- Revalidate principal bằng API được bảo vệ trước khi render private data.
- Mọi API cần authorization theo **user B thực**, không dựa vào route cached từ A.
- Không để BFCache/Back button làm lộ trang A trên thiết bị dùng chung mà không có revalidation.

### 14.7. Bảo vệ URL và log của logout

Một logout URL có thể chứa returnTo:

~~~text
/logout?returnTo=https://outside.test
~~~

Nếu backend dùng giá trị đó làm redirect, có thể tạo **open redirect** và phishing sau logout. Hãy dùng path/route ID cố định hoặc allowlist được kiểm tra, không tin Referer/Host/Forwarded ngoài trusted policy.

Đừng đưa session ID, refresh token, logout token, id_token_hint hay authorization code vào logs/URL không được kiểm soát. Khi OIDC flow yêu cầu mang token/identifier theo giao thức, giữ đúng scope, TLS, redaction và provider registration.

## 15. Servlet/MockMvc: chứng minh logout thật sự hủy session

Một test tốt phải phân biệt **logout response** với **server session state**. Test chỉ kiểm tra 302/204 là chưa đủ, và test dùng user mock cho request sau logout có thể vô tình **cấp Authentication giả** làm mất ý nghĩa kiểm thử.

### 15.1. Ma trận kiểm thử Servlet

| Kịch bản | Kỳ vọng |
| --- | --- |
| POST /logout không có CSRF. | Bị từ chối theo policy (thường 403), không coi là logout hoàn tất. |
| POST /logout có CSRF của session. | Logout handlers chạy, response theo contract. |
| Session trước logout đã authenticated. | GET protected resource trả dữ liệu user. |
| Sau logout gửi request với **session ID cũ**. | Không trả protected data, theo 401/redirect contract. |
| Cookie expire có đúng name/Path/Domain. | Browser bỏ cookie tương ứng; test bằng browser/HTTP integration. |
| Remember-me cookie/persistent token tồn tại. | Không tự login lại nếu logout có nghĩa revoke remember-me. |
| HTTP Basic/Bearer còn được gửi. | Hoạt động theo policy riêng, không suy session invalidation sẽ revoke. |
| Logout session đã hết hạn. | No-op/error theo contract, không tạo authenticated principal. |
| Logout request bị retry. | Idempotent và không tạo credential mới. |
| CSRF token từ phiên cũ sau logout. | Không được dùng cho unsafe request ở phiên mới. |
| Một tab logout, tab khác GET protected. | Request mới bị chặn bởi server; UI state đồng bộ riêng. |
| Shared Redis/Spring Session nhiều instances. | Một instance invalidate thì instance khác từ chối session cũ. |

### 15.2. MockMvc test logout HTML

Đoạn minh họa giả định application dùng **FormLogoutSecurityConfig** tại mục 5.1, có tài khoản test **learner/test-secret**, CSRF bật và controller GET /app/account yêu cầu authentication:

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class ServletLogoutLifecycleMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void logoutInvalidatesAuthenticatedSession() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "test-secret"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session = (MockHttpSession)
                login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(post("/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?logout"));

        assertTrue(session.isInvalid());
    }

    @Test
    void missingCsrfDoesNotPerformNormalLogout()
            throws Exception {

        mvc.perform(post("/logout"))
            .andExpect(status().isForbidden());
    }
}
~~~

**Giới hạn test:** MockMvc xác minh handler/status và HttpSession mock được invalidated, **không chứng minh session ID cũ bị mọi instance production từ chối**. Cần HTTP integration test thực với cookie jar + shared session store. Nếu logout handler chỉ dùng 204 thay vì redirect, đổi assertion theo SPA config; nếu app có custom auth entry point, status lỗi có thể khác.

Không dùng **with(user("learner"))** cho request kiểm tra sau logout nếu mục tiêu là chứng minh request **không còn authenticated**; helper sẽ tạo principal test độc lập với session, gây false positive.

### 15.3. Test logout success với SPA 204

Với **SpaLogoutSecurityConfig** và user fixture:

~~~java
mvc.perform(post("/logout")
        .with(csrf()))
    .andExpect(status().isNoContent());
~~~

Đây là kiểm tra hợp đồng HTTP, **chưa chứng minh token/session được revoke**. Kết hợp cùng một session đã login như test trên, rồi kiểm tra invalidation.

### 15.4. Integration test giữ cookie thật và gọi API bảo vệ

Một bài test end-to-end nên:

~~~text
1. GET /login hoặc GET /csrf để nhận cookie jar + CSRF token.
2. POST /login với cùng cookie jar + token + credential test.
3. GET /api/me → trả authenticated principal.
4. Ghi lại cookie session ID để kiểm chứng trong phạm vi test.
5. POST /logout với cookie jar + CSRF token hợp lệ.
6. GET /api/me với cookie/session ID cũ:
       → 401 / redirect / response không có private data.
7. GET /login/GET /csrf có thể phát anonymous cookie mới.
8. POST /login lần hai phải qua authentication bình thường.
~~~

Nếu có **Remember-me**, thực hiện thêm request chỉ mang remember-me cookie cũ để đảm bảo user không được auto-authenticate. Nếu có bearer access token, test riêng đúng phạm vi: token bị revoke hay còn sống đến exp theo thiết kế?

Đừng lưu raw credential/token/session ID vào báo cáo kiểm thử. Cookie jar test có thể chứa secrets; loại bỏ/tái tạo sau test.

### 15.5. Test Set-Cookie scope trong response

Kiểm tra response có expiration cookie đúng tên:

~~~http
Set-Cookie: JSESSIONID=; Max-Age=0; Path=/app; HttpOnly; Secure; SameSite=Lax
~~~

Nhưng **chỉ thấy Set-Cookie không chứng minh cookie đã biến mất**. Cần test browser thực hoặc cookie jar áp dụng cookie matching rules, kiểm tra Cookie header gửi tới protected path sau logout.

Nếu backend set cả **JSESSIONID Path=/** và **JSESSIONID Path=/app**, phải biết cookie nào được session resolver sử dụng. Delete cookie với Path sai có thể để lại credential cũ.

### 15.6. Test HTTP headers trên protected responses

Một response thông tin nhạy cảm có thể được kiểm tra:

~~~java
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;

// Với GET protected endpoint đã authenticated:
mvc.perform(get("/app/account").with(authenticatedTestUser()))
    .andExpect(header().string(
            "Cache-Control", "no-store"));
~~~

**authenticatedTestUser()** chỉ là test fixture helper chưa được định nghĩa ở đây. Nếu dùng mock user cho header test, nó **phù hợp kiểm tra response headers**, nhưng không dùng để kiểm tra session revocation. Nhiều apps có Cache-Control kết hợp các directives, vì vậy assertion theo exact string phải khớp policy thực; có thể thay bằng kiểm tra chứa **no-store**.

Không suy rằng header này dọn được BFCache, IndexedDB hoặc service worker cache. Cần test các tầng riêng.

## 16. WebTestClient, browser E2E và kiểm thử dữ liệu còn lưu

### 16.1. WebFlux logout response test

Với **ReactiveLogoutSecurityConfig** mục 6, WebTestClient đã bind vào ứng dụng có authenticated user test:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;

// Đoạn minh họa bên trong WebFlux test class.
// Authentication/CSRF/session fixture cần được cấu hình phù hợp.
webTestClient
    .mutateWith(csrf())
    .post().uri("/logout")
    .exchange()
    .expectStatus().isNoContent()
    .expectHeader().valueEquals(
        "Cache-Control", "no-store");
~~~

Đoạn này kiểm tra HTTP success handler; **không tự kiểm chứng** WebSession thực đã invalidate, cookie đã bị browser loại bỏ hay bearer token đã revoke.

### 16.2. Reactive integration test WebSession continuity

Một test nhiều request đúng cần giữ **WebSession cookie** từ phản hồi trước:

~~~text
GET /login hoặc /csrf
   → WebSession cookie + token được phát

POST /login + CSRF + cookie
   → Authentication thành công

GET /api/me + cùng cookie
   → authenticated principal

POST /logout + CSRF + cùng cookie
   → 204 + session invalidation

GET /api/me + cookie cũ
   → không trả authenticated profile
~~~

Nếu response logout xóa cookie/đổi session ID, vẫn cần test cố tình **gửi session cookie cũ** qua test HTTP client để xác minh server store đã vô hiệu hóa. WebTestClient helper mutateWith(csrf()) **không tái tạo tất cả browser cookie/CORS behaviors**, nên phải chạy integration test với server thật/cookie jar khi cần.

### 16.3. Browser test: nút Back

Một bài test browser có kiểm soát:

1. Đăng nhập bằng account test trong browser profile sạch.
2. Mở **/app/account** và xác nhận dữ liệu user test xuất hiện.
3. Bấm **Đăng xuất**, kiểm tra POST /logout được gửi cùng CSRF token hợp lệ.
4. Kiểm tra response 204/redirect và cookie expiration theo policy.
5. Bấm **Back**.
6. Xác định browser có gửi request mới hay phục hồi BFCache bằng **pageshow.persisted**.
7. Xác minh private view được ẩn/đổi sau revalidation và không có đường thao tác quyền.
8. Thử refresh protected route: phải bị từ chối hoặc về login.
9. Thử offline và Back nếu ứng dụng có service worker/PWA.
10. Lặp lại trên những browser chính dự án hỗ trợ.

Một trang có thể **chớp nhoáng hiển thị snapshot** trước callback pageshow chạy; ứng dụng nhạy cảm cần UX che private content và cache policy nghiêm hơn, đồng thời hiểu giới hạn browser. Không kết luận logout thất bại chỉ vì Back cho thấy snapshot, nhưng cũng không bỏ qua rủi ro privacy trên thiết bị dùng chung.

### 16.4. Browser test: storage inventory trước và sau

Tạo dữ liệu test giả ở các nơi ứng dụng dùng:

| Trước logout | Sau logout được mong đợi |
| --- | --- |
| localStorage myapp:profile | Key bị xóa hoặc không còn dữ liệu user A. |
| sessionStorage myapp:csrfToken | Token cũ bị loại. |
| IndexedDB myapp-offline-user-data | Records nhạy cảm được xóa theo policy. |
| Cache Storage myapp-user-cache-v1 | Cache bị delete hoặc không còn user records. |
| Service worker trả cached /api/me | Không cung cấp stale profile từ offline cache. |
| React Query/Redux user store | Đã reset sau logout/account switch. |
| DOM của tab B | Đã nhận logout signal hoặc revalidate/ẩn. |
| Cookie session/remember-me | Expired/invalid theo scope. |
| GET /api/me dùng cookie cũ | Không còn authenticated. |
| Password manager/downloads/history | **Không được cam kết xóa bằng web logout.** |

Cần test cả **browser không hỗ trợ Clear-Site-Data** hoặc không xử lý các directives đã chọn. Nếu app phụ thuộc header để bảo vệ privacy, phải có fallback/script cleanup tương ứng.

### 16.5. Multi-tab test

~~~text
Tab A: mở /app/account, tải dữ liệu A.
Tab B: mở /app/orders, tải dữ liệu A.
Tab A: logout.
Tab B: nhận BroadcastChannel event hoặc revalidate.
Tab B: xóa DOM/store/cache user A, không tiếp tục private calls.
Tab B: reload/GET /api/me → không còn authenticated.
~~~

Test thêm một tab **suspended/BFCache**, một tab mở sau logout, và trường hợp browser không hỗ trợ BroadcastChannel. Đừng chỉ kiểm tra localStorage event; sessionStorage và JS memory của các tabs cần cleanup riêng.

### 16.6. Account switch test

~~~text
User A đăng nhập → load /api/orders/A
User A logout    → session invalidated, state A cleared
User B đăng nhập → load /api/orders/B

Expected:
  UI không hiển thị orders A
  Cache/IndexedDB không cung cấp orders A cho B
  GET /api/orders/A dưới quyền B bị từ chối nếu không có quyền
  CSRF token/phân quyền/session đều thuộc phiên B
~~~

Test này đặc biệt hữu ích cho PWA/offline caches và ứng dụng dùng global query cache theo route chung.

### 16.7. curl không thể xác minh browser cleanup

curl có thể kiểm tra session invalidation và HTTP headers khi quản lý cookie jar, nhưng **không có DOM, BFCache, localStorage, IndexedDB, service worker và browser SameSite/CORS enforcement** như browser.

Một POST logout không có CSRF token thường bị 403, nên **không được dùng kết quả đó để kết luận server logout logic sai**. Luồng curl phải lấy token/cookie hợp lệ trước, giữ cùng session và theo dõi Set-Cookie.

### 16.8. Kiểm tra offline và mạng lỗi

Hai test quan trọng:

- **Client offline trước khi logout**: app có thể xóa UI/storage local, nhưng không được tuyên bố server session/refresh token đã revoke. Khi online trở lại, retry/reconciliation phải theo policy và không tự render private data.
- **Response logout bị mất sau khi server xử lý**: server session đã revoke nhưng browser không nhận 204/Set-Cookie/Clear-Site-Data. UI cần vẫn an toàn, retry idempotent và tránh giữ dữ liệu cache.

Ngoài ra cần test **Redis/session store outage**, request in-flight trả 200 sau logout và service worker trả cached authenticated response trong offline mode.

## 17. Chẩn đoán lỗi logout theo từng tầng

### 17.1. Bảng triệu chứng

| Triệu chứng | Tầng cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| **Bấm logout nhưng vẫn vào API bằng session cũ.** | LogoutFilter/LogoutWebFilter, session repository, SecurityContext. | Xác minh POST /logout chạy đúng chain, invalidation, shared store. |
| **UI về login nhưng refresh lại tự đăng nhập.** | Remember-me, refresh token hoặc IdP SSO auto-login. | Thu hồi credential thích hợp, phân biệt local/SSO logout. |
| **Xóa cookie rồi nhưng server vẫn nhận ID cũ.** | Session invalidation và session store. | Invalidate session server-side, không chỉ Set-Cookie expiration. |
| **JSESSIONID vẫn xuất hiện sau logout.** | Cookie Path/Domain, tên cookie và anonymous session mới. | Kiểm tra Cookie/Set-Cookie, ID cũ có còn quyền không. |
| **Hai cookie cùng tên vẫn tồn tại.** | Cookie scope theo Path/Domain. | Expire đúng từng cookie app sở hữu; tránh tên/path chồng lắp. |
| **Logout form POST bị 403.** | CsrfFilter/CsrfWebFilter hoặc session cookie. | Cấp CSRF token đúng phiên, giữ POST, không tắt CSRF. |
| **GET /logout tự đăng xuất.** | Logout matcher và unsafe GET semantics. | Chuyển mutation về POST có CSRF, GET chỉ xác nhận nếu cần. |
| **SPA fetch 302 nhưng không chuyển tới login.** | fetch vs navigation. | API 204 + client router, hoặc xử lý redirect UI rõ. |
| **SPA logout báo CORS error.** | OPTIONS preflight/actual response/gateway. | CORS allowlist và credentials, không mở wildcard sai. |
| **Sau logout, nhấn Back thấy hồ sơ.** | BFCache/DOM/http cache. | Kiểm tra server từ chối request mới; revalidate pageshow và che UI. |
| **Reload trang sau logout vẫn hiện dữ liệu cũ offline.** | Service worker + Cache Storage. | Không cache private data, xóa owned caches, test offline. |
| **Tab B vẫn thấy orders sau Tab A logout.** | Memory state, multi-tab messaging. | BroadcastChannel + route revalidation + drop stale data. |
| **Tab B gửi API sau logout và bị 401 nhưng vẫn render data.** | In-memory query cache. | Clear cache, handle 401 và auth generation check. |
| **Clear-Site-Data có trong Network nhưng localStorage còn.** | Browser support, origin, header context, shared app. | Test browser hỗ trợ và fallback JS cleanup, HTTPS. |
| **Clear-Site-Data xóa settings của app khác.** | Origin/shared domain policy. | Giới hạn directives, app-owned keys; không dùng blanket storage clear. |
| **Logout một app khiến nhiều subdomain mất login.** | Clear-Site-Data "cookies"/Domain cookie. | Đánh giá registrable-domain scope và SSO shared cookies. |
| **Bị logout ở app nhưng vào lại không cần nhập mật khẩu.** | IdP SSO session còn active. | RP-Initiated Logout nếu chính sách yêu cầu và provider hỗ trợ. |
| **IdP đã logout nhưng app B vẫn xem được data.** | RP session riêng, thiếu back-channel/session revocation. | Kiểm tra logout protocol/registry và browser revalidation. |
| **JWT cũ vẫn gọi API được sau logout.** | Stateless bearer validator không có revocation. | Access token TTL/revocation registry/introspection theo policy. |
| **Refresh token còn dùng được.** | Refresh rotation/store không revoke. | Revoke token/family tại server; test refresh flow. |
| **Login lại sau logout nhận 403 CSRF.** | CSRF token cũ trong SPA/DOM. | Lấy token mới từ phiên hiện tại. |
| **Spring Session logout có lúc hiệu lực, lúc không.** | Shared store/cluster consistency/chain mismatch. | Kiểm tra repository trên mọi instance, TTL, cookies. |
| **API chain vẫn authn dù web chain logout.** | Multiple SecurityFilterChain và bearer token. | Kiểm tra credential mechanism/chain độc lập. |
| **Request cũ trả 200 sau logout.** | In-flight request qua auth trước invalidation. | Kiểm tra timing; drop frontend response, cân nhắc commit-time checks. |
| **Logout response mất do network timeout.** | Client không biết server đã revoke hay chưa. | Ẩn UI local, trạng thái chưa xác nhận, retry idempotent. |
| **Browser vẫn giữ download/screenshot.** | Bản sao ngoài phạm vi web app. | Không thể xóa đáng tin; dùng device/privacy controls. |
| **Lịch sử có URL reset token.** | Secret URL/referrer/history. | Tránh secrets trong URL, bảo vệ Referrer-Policy và flow reset. |
| **CSRF/SSO callback bị chặn sau thay logout settings.** | Matcher/chains/giao thức. | Giữ CSRF cho unsafe app actions, ngoại lệ hẹp theo protocol. |
| **Logout redirect ra website ngoài.** | Unvalidated returnTo/Referer/Host. | Fixed route/allowlist; kiểm tra proxy headers. |
| **Cookie HttpOnly không thể xóa bằng JavaScript.** | Browser cookie access model. | Server Set-Cookie expiration và server invalidation. |

### 17.2. Trình tự debug một logout thất bại

1. Xác định **cơ chế auth** của request: session cookie, remember-me, bearer JWT, opaque token, SSO hoặc tổ hợp.
2. Xác định **URL/method/security chain** xử lý logout.
3. Kiểm tra **CSRF/CORS/preflight** nếu request không tới logout handler.
4. Xác nhận **response status, Set-Cookie, Cache-Control, Clear-Site-Data** trên Network.
5. Kiểm tra logout handler đã clear SecurityContext và invalidate **đúng session store** chưa.
6. Gửi **request mới bằng credential cũ** đến protected endpoint và quan sát status/data.
7. Nếu credential còn hiệu lực, tìm remember-me/refresh/bearer filters hoặc cache/session replication.
8. Kiểm tra **browser cookies** với tên/Path/Domain/Secure/SameSite và anonymous session mới.
9. Kiểm tra DOM, SPA store, localStorage, sessionStorage, IndexedDB, Cache Storage và service worker.
10. Test Back/Forward, BFCache, offline và nhiều tabs.
11. Nếu có IdP, kiểm tra local logout khác logout IdP/front-channel/back-channel và token revocation.
12. Kiểm tra race/concurrent requests và account switch.
13. Rà security headers/proxy/URL redirect policy; không mở rộng CORS hoặc tắt CSRF để né triệu chứng.
14. Ghi nhận kết quả **đã hoàn tất ở server**, **đã dọn tại origin**, **chưa kiểm chứng/không thể thu hồi** riêng biệt.

### 17.3. Kiểm tra HTTP headers trên trang bảo vệ

Một bộ header tham khảo cho nội dung nhạy cảm:

~~~http
Cache-Control: no-store
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
Strict-Transport-Security: max-age=31536000
~~~

Đây là **policy minh họa**, không copy nguyên trong mọi ứng dụng. CSP phải phù hợp các script/assets/SSO flows được phép và đặt trên **HTML document cần bảo vệ**, không chỉ API JSON. HSTS chỉ cho HTTPS hosts đủ điều kiện; trước khi bật includeSubDomains phải kiểm kê toàn bộ subdomain.

**Không có header đơn lẻ bảo đảm logout**. Cache-Control giúp giảm HTTP caching; CSP giảm một số rủi ro XSS/clickjacking; HSTS bảo vệ kênh kết nối, không hủy sessions hay dọn JS memory.

### 17.4. HTTP firewall không phải logout engine

Spring Security HTTP firewall giúp từ chối request bất thường về URL/method/path, không thu hồi session/token. Nếu logout endpoint có nhiều dạng đường dẫn do proxy rewriting, cần thống nhất canonical path và matcher; không nới StrictHttpFirewall chỉ để GET /logout bị encode bất thường chạy được.

### 17.5. Thông báo cho user phải nói đúng phạm vi

Có thể dùng các thông điệp:

| Trạng thái thực | Thông báo phù hợp |
| --- | --- |
| Server đã invalidate phiên hiện tại. | “Đã đăng xuất khỏi phiên này.” |
| Browser local cleanup hoàn tất, server chưa xác nhận do mất mạng. | “Đã ẩn dữ liệu trên thiết bị này, nhưng chưa xác nhận được đăng xuất với máy chủ.” |
| Global device revoke đã thành công theo policy. | “Các phiên đăng nhập đã chọn đã được thu hồi.” |
| IdP logout đã được khởi tạo nhưng callback chưa xác nhận. | “Đang hoàn tất đăng xuất qua nhà cung cấp danh tính.” |
| Offline cached content có thể vẫn tồn tại. | “Nội dung đã tải xuống hoặc lưu offline có thể vẫn còn trên thiết bị.” |

Tránh câu **“Mọi dữ liệu của bạn đã bị xóa khỏi thiết bị”** nếu ứng dụng không thể kiểm tra screenshots, downloads, password manager, browser history hoặc những ứng dụng khác.

## 18. Bài tập tình huống: server logout và dấu vết browser

### Tình huống A — Chuyển UI về login có đủ không?

SPA xóa cờ isLoggedIn rồi điều hướng tới /login, nhưng không gửi POST /logout. Một request tiếp theo với cookie cũ vẫn nhận dữ liệu tài khoản. Đây có phải logout thành công?

**Đáp án:** Không. Đây chỉ là **client-side logout state**. Server session/credential vẫn còn hiệu lực. Cần invalidate session hoặc revoke credential phía server và kiểm tra bằng GET protected resource sau logout.

### Tình huống B — Chỉ xóa cookie

Developer xóa JSESSIONID bằng JavaScript nhưng không invalidate HttpSession. Một bên khác đã có bản sao session ID cũ tiếp tục gọi API được. Vì sao?

**Đáp án:** Browser cookie deletion không thu hồi server-side session. Cần **SecurityContextLogoutHandler/session invalidation** tại backend; JavaScript còn không được đọc/xóa HttpOnly cookie theo cách thông thường.

### Tình huống C — HttpSession invalidated, cookie vẫn xuất hiện

Sau POST /logout, DevTools vẫn hiện JSESSIONID. Developer cho rằng session chưa hủy. Kết luận đúng không?

**Đáp án:** Chưa đủ. Cookie có thể còn do Path/Domain không khớp hoặc browser nhận **anonymous session mới** sau GET /login. Hãy thử **request mới với session ID cũ** đến protected endpoint: nếu server từ chối, server invalidation có thể đã thành công.

### Tình huống D — Cookie cùng tên nhưng hai Path

Browser giữ JSESSIONID ở Path=/ và Path=/app. Logout chỉ expire Path=/. Khi mở /app, browser vẫn gửi cookie thứ hai. Sửa như thế nào?

**Đáp án:** Dọn **đúng tên và Path/Domain scope** của cookie ứng dụng thực dùng, tránh cấu hình cookie chồng lắp. Đồng thời invalidate session server-side; expiration cookie không thay revocation.

### Tình huống E — Logout bằng GET

Ứng dụng định nghĩa GET /logout làm invalidation và tắt CSRF vì GET “không thay đổi dữ liệu”. Có vấn đề gì?

**Đáp án:** Có. Logout thay đổi trạng thái xác thực; GET phải có semantics an toàn. Link, prefetch hoặc trang ngoài có thể trigger logout. Dùng **POST /logout có CSRF token** trong mô hình cookie/session.

### Tình huống F — POST logout bị 403

User bấm logout nhưng backend trả 403. Team đề nghị tắt CSRF. Cách tiếp cận đúng?

**Đáp án:** Xác minh CSRF token/header/field, session cookie và matcher; cấp token hợp lệ cho POST. **Không tắt CSRF** chỉ vì UI chưa truyền token hoặc session đã thay đổi.

### Tình huống G — Logout 204 nhưng SPA vẫn hiển thị dashboard

Server xác nhận 204, backend từ chối session cũ nhưng React store và DOM của tab vẫn chứa dữ liệu user. Đây là lỗi ở đâu?

**Đáp án:** Phần **client cleanup/UI lifecycle**. Xóa stores, cache query, sensitive UI, pending requests và điều hướng tới màn hình phù hợp. Server revoke không tự dọn JavaScript memory.

### Tình huống H — Back button hiển thị profile

Sau logout, người dùng bấm Back và thấy trang hồ sơ trong chốc lát. GET /api/me mới trả 401. Có nhất thiết session vẫn sống không?

**Đáp án:** Không. **BFCache hoặc in-memory snapshot** có thể hiển thị nội dung mà không request lại server. Cần Cache-Control cho nội dung nhạy cảm, revalidate pageshow/visibilitychange và che private view khi chưa xác minh.

### Tình huống I — no-store có đủ để xóa IndexedDB?

Backend đặt Cache-Control: no-store cho /api/orders, nhưng PWA đã ghi orders vào IndexedDB. Khi logout, orders vẫn còn. Vì sao?

**Đáp án:** HTTP cache policy không tự xóa **IndexedDB** do app ghi. Cần tránh lưu user data vào offline DB khi không cần hoặc xóa theo schema/namespace lúc logout/account switch.

### Tình huống J — Service worker phục vụ profile offline

Server đã logout nhưng browser chuyển Offline rồi mở /app/account và service worker trả cached profile. Đây có phải Spring Security bỏ qua authorization không?

**Đáp án:** Không hẳn. Browser **không gửi request mới tới server** khi service worker phục vụ dữ liệu offline. Xây policy không cache private responses, dọn Cache Storage/service worker-owned user state và kiểm thử offline.

### Tình huống K — Xóa localStorage.clear làm mất dữ liệu app khác

Hai ứng dụng cùng origin nhưng ở /app-a và /app-b. App A gọi localStorage.clear() khi logout, làm mất preferences App B. Có cần không?

**Đáp án:** Không mặc định. localStorage được phân theo **origin**, không theo path. Dọn **keys thuộc ứng dụng** hoặc điều chỉnh origin isolation khi cần, tránh xóa toàn bộ storage dùng chung.

### Tình huống L — IndexedDB delete bị blocked

Một tab mở database offline, tab khác logout và gọi indexedDB.deleteDatabase nhưng nhận sự kiện blocked. Có được báo “đã xóa hoàn toàn dữ liệu offline” không?

**Đáp án:** Không. Phải đóng DB connections ở các tabs/workers, phối hợp cleanup và kiểm tra kết quả. Khi chưa xong, UI không được tuyên bố đã xóa hoàn toàn.

### Tình huống M — Clear-Site-Data làm logout nhiều subdomain

App A phát Clear-Site-Data: "cookies" khi logout; người dùng bị mất SSO cookie của ứng dụng B cùng parent domain. Vì sao?

**Đáp án:** Phạm vi cookies directive trong những browsers hỗ trợ có thể ảnh hưởng **registrable domain/subdomains**. Phải đánh giá blast radius; có thể chỉ expire app-owned cookie và dùng các directives hẹp hơn.

### Tình huống N — Browser không hỗ trợ Clear-Site-Data

API trả header "storage", team nghĩ mọi browser đã xóa localStorage/IndexedDB. Một browser không xử lý directive, dữ liệu còn nguyên. Cần làm gì?

**Đáp án:** Không phụ thuộc hoàn toàn vào một header có hỗ trợ khác nhau. **Thực hiện app-owned client cleanup** và kiểm thử trong các browsers mục tiêu; khi không thể bảo đảm, diễn đạt giới hạn rõ.

### Tình huống O — Tab A logout, Tab B không biết

Tab A đã logout và xóa storage, nhưng tab B vẫn đang render account A. Server từ chối API mới ở tab B. Cần thêm gì?

**Đáp án:** **BroadcastChannel hoặc cơ chế đồng bộ cùng origin**, route guard, pageshow/visibility revalidation và reset state tại tab B. Không coi cookie mất là lệnh xóa DOM tự động.

### Tình huống P — Response cũ trả sau logout

Tab A logout, sau đó GET /api/orders khởi động trước logout hoàn tất với 200 và callback ghi vào store. Dữ liệu xuất hiện lại. Phòng vệ nào phù hợp?

**Đáp án:** Bỏ/cancel request cũ và dùng **auth generation/session version** khi apply response. Callback chỉ cập nhật UI nếu request thuộc generation hiện tại và user vẫn authenticated theo client policy.

### Tình huống Q — Browser offline khi user bấm Logout

App dọn giao diện và localStorage nhưng POST /logout không tới server. UI báo “Đã đăng xuất khỏi mọi nơi”. Có đúng không?

**Đáp án:** Không. Đó chỉ là **local logout** chưa được server xác nhận. Nên ẩn private UI ngay, đánh dấu revoke pending và retry/reconciliation khi online; không đưa ra cam kết global logout sai.

### Tình huống R — Remember-me tự đăng nhập lại

User logout, HttpSession bị hủy; sau đó vào protected route browser lại có Authentication mà không nhập mật khẩu. Có thể do đâu?

**Đáp án:** **Remember-me persistent cookie/token** chưa bị clear/revoke hoặc một SSO/refresh flow còn hoạt động. Kiểm tra authentication filter và repository, dọn đúng credential theo policy.

### Tình huống S — Refresh token còn hiệu lực

SPA xóa access token memory, backend invalidates web session, nhưng refresh token HttpOnly còn hợp lệ và endpoint /refresh cấp access token mới. Điều gì thiếu?

**Đáp án:** **Revoke refresh token/token family** và expire cookie tương ứng đúng scope. Logout một HttpSession không tự chặn token issuance ở một cơ chế khác.

### Tình huống T — JWT access token đã phát vẫn gọi API được

User bấm logout và xóa JWT ở localStorage, nhưng bản sao token cũ vẫn hợp lệ tới exp. Điều này có thể đúng theo kiến trúc không?

**Đáp án:** Có, nếu resource server xác minh JWT offline và **không có revocation mechanism**. Phải công bố đúng giới hạn, hoặc thêm denylist/reference/introspection/version-check, access token ngắn hạn và revoke refresh theo threat model.

### Tình huống U — Logout local nhưng IdP vẫn cho đăng nhập tức thì

App logout thành công; user mở lại app, OIDC login redirect tới IdP và quay về mà không nhập password. Có phải local logout bị lỗi?

**Đáp án:** Không nhất thiết. **IdP SSO session vẫn active**. Nếu mục tiêu yêu cầu logout khỏi IdP, triển khai OIDC RP-Initiated Logout hoặc giao thức tương ứng, validate redirects và hiểu giới hạn provider.

### Tình huống V — Back-channel logout gửi JSON unsigned

Một public endpoint nhận POST chứa userId và xóa mọi sessions tương ứng mà không xác minh chữ ký/issuer/audience. Có an toàn không?

**Đáp án:** Không. Back-channel logout là **giao thức server-to-server cần xác thực thông điệp** và map sid/sub theo policy; JSON bất kỳ có thể trở thành công cụ logout DoS.

### Tình huống W — Spring Session đa node

Logout được xử lý ở Node A, nhưng request tiếp theo tới Node B vẫn có SecurityContext authenticated. Phải kiểm tra gì?

**Đáp án:** Shared session store/repository, replication consistency, local cache stale, cookie resolver và security chain. Không chỉ xóa cookie ở A; tất cả nodes phải không chấp nhận session cũ theo chính sách.

### Tình huống X — Hai user đăng nhập luân phiên trên cùng trình duyệt

User A logout rồi user B login, nhưng Cache Storage hoặc React Query cache trả orders A cho B. Hậu quả và sửa?

**Đáp án:** **Cross-account data exposure trong client**. Partition hoặc không cache user-specific responses, reset stores/IndexedDB/service worker caches lúc logout và principal change; server authorization vẫn bắt buộc.

### Tình huống Y — App muốn xóa password manager và screenshots khi logout

Developer hứa website có thể xóa mọi password đã lưu trong browser, download, clipboard và ảnh chụp màn hình của user. Có khả thi không?

**Đáp án:** Không thể bảo đảm từ web app. Logout chỉ kiểm soát server credentials và một phần origin-owned data theo browser APIs/policies; bản sao ngoài origin hoặc do user/thiết bị tạo cần **thiết bị và chính sách riêng**.

### Tình huống Z — Test logout chỉ xem mã 204

QA chỉ assert POST /logout trả 204 nên kết luận đạt. Những kiểm tra quan trọng còn thiếu?

**Đáp án:** Gửi request mới với **credential/session ID cũ**, kiểm tra remember-me/refresh/JWT, server session store đa node, cookie expiration đúng scope, localStorage/IndexedDB/Cache Storage, service worker offline, BFCache Back, multi-tab, in-flight requests và IdP logout theo phạm vi sản phẩm. **HTTP success status không phải bằng chứng mọi trạng thái đã bị thu hồi/dọn sạch**.

## 19. Checklist triển khai logout trước khi phát hành

### 19.1. Phạm vi và hợp đồng logout

- [ ] Tài liệu sản phẩm phân biệt **logout phiên hiện tại**, **logout mọi thiết bị**, **logout IdP** và **xóa dữ liệu browser**.
- [ ] Định nghĩa rõ credential nào được thu hồi: server session, remember-me, refresh, access token, device session.
- [ ] Không hứa tất cả JWT lập tức vô hiệu nếu không có revocation state check.
- [ ] Không hứa xóa lịch sử, download, password manager, clipboard hoặc screenshot bằng web logout.
- [ ] UI phân biệt **server confirmed logout** với **local cleanup nhưng server chưa xác nhận**.
- [ ] Logout có response contract HTML 302/303 hoặc SPA 204/JSON rõ ràng.
- [ ] Redirect sau logout dùng path/allowlist an toàn, không arbitrary returnTo/Referer/Host.
- [ ] Logout retry/idempotency không làm phát sinh authenticated session mới.
- [ ] Những thao tác revoke bắt buộc có error policy khi store/IdP không khả dụng.
- [ ] Các sự kiện async/global logout không bị báo hoàn tất trước khi có bằng chứng theo policy.

### 19.2. Spring Security Servlet

- [ ] Sử dụng **LogoutFilter** và chuỗi LogoutHandler đúng security chain.
- [ ] POST /logout cần CSRF token hợp lệ trong mô hình cookie/session.
- [ ] GET /logout không tự thực hiện mutation logout không được bảo vệ.
- [ ] **SecurityContextLogoutHandler** clear context và invalidate session khi yêu cầu.
- [ ] **CsrfLogoutHandler** / repository lifecycle được áp dụng phù hợp.
- [ ] Remember-me logout handler và persistent token repository được xử lý nếu dùng.
- [ ] Custom LogoutHandler revoke application credentials theo đúng user/device.
- [ ] Custom token revoke không tin arbitrary deviceId/userId trong request body.
- [ ] LogoutSuccessHandler không bỏ qua cleanup hoặc tạo quyền mới.
- [ ] Cookie expire từ deleteCookies hoặc Set-Cookie có đúng tên/Path/Domain.
- [ ] Không dùng nhiều SecurityFilterChain trùng matcher khiến logout chạy sai chain.
- [ ] Trang login sau logout là public, có token CSRF mới khi cần.
- [ ] Không tắt CSRF toàn site chỉ để POST /logout thành công.
- [ ] API dùng bearer token có chính sách revoke riêng, không suy từ form logout.

### 19.3. Spring Security Reactive/WebFlux

- [ ] Dùng **LogoutWebFilter/ServerLogoutHandler/ServerLogoutSuccessHandler**, không trộn Servlet APIs.
- [ ] SecurityContext reactive được clear khỏi repository phù hợp.
- [ ] WebSession được invalidate khi logout policy yêu cầu, và được kiểm tra trên request mới.
- [ ] ServerLogoutHandler trả Mono<Void> hoàn chỉnh, không block()/subscribe() thủ công.
- [ ] Những handlers khác cần thiết không bị bỏ sót khi custom logoutHandler.
- [ ] WebFlux CSRF bảo vệ POST logout theo matcher và token repository thực.
- [ ] Cookie WebSession có tên/scope đúng (không mặc định JSESSIONID).
- [ ] CookieWebSessionIdResolver dùng Secure/HttpOnly/SameSite/Path phù hợp.
- [ ] Logout 204/redirect response được kiểm tra qua WebTestClient và browser.
- [ ] Reactive token APIs thu hồi bearer/refresh credential bằng cơ chế riêng.
- [ ] Distributed WebSession store invalidate đúng trên nhiều instances.
- [ ] Reactive Redis/client handling không block event loop trong revoke path.

### 19.4. Cookies và authentication credentials

- [ ] Session ID cũ không còn authenticated khi gửi protected GET sau logout.
- [ ] Cookie expiration đúng **name/Path/Domain**, không chỉ đúng name.
- [ ] Cookie __Host- dùng Secure, Path=/ và không có Domain.
- [ ] Session cookies cần Secure/HttpOnly/SameSite phù hợp với HTTPS, CSRF và browser policy.
- [ ] Không dùng document.cookie làm cơ chế duy nhất để xóa HttpOnly credential.
- [ ] Cookies cùng tên nhưng khác Path/Domain được kiểm kê và dọn đúng.
- [ ] Cookie của IdP/host khác không được coi là tự xóa bởi app logout.
- [ ] Anonymous session mới sau logout không bị nhầm với authenticated session cũ.
- [ ] Remember-me cookie/persistent repository không tự đăng nhập lại user ngoài ý muốn.
- [ ] Refresh token hiện tại/family được revoke theo scope và rotation policy.
- [ ] Access token JWT có TTL/revocation semantics rõ, không phóng đại bảo đảm.
- [ ] Global logout chỉ tác động sessions/devices được xác định từ principal đã xác minh.
- [ ] Header Cookie/Authorization/Set-Cookie không bị log raw trong audit.
- [ ] Quy trình session fixation và CSRF token rotation vẫn hoạt động ở lần login kế tiếp.

### 19.5. Browser storage, offline và UI

- [ ] Logout dọn sensitive DOM và authenticated in-memory stores ngay khi user chọn logout.
- [ ] Query/GraphQL/Redux/Pinia caches chứa user data được reset.
- [ ] Pending requests bị cancel hoặc kết quả bị bỏ nếu auth generation thay đổi.
- [ ] localStorage keys thuộc ứng dụng được xóa, không dùng blanket clear nếu origin chia sẻ.
- [ ] sessionStorage keys theo từng tab được xóa đúng, không giả định tab khác tự clear.
- [ ] IndexedDB user data được xóa/partition đúng; đóng connections khi cần.
- [ ] Xử lý indexedDB.deleteDatabase blocked và failure, không báo dọn hoàn tất giả.
- [ ] Cache Storage chứa user-specific responses được xóa theo namespace.
- [ ] Service worker không phục vụ stale private API/HTML sau logout/offline.
- [ ] Có chính sách không cache sensitive responses khi offline không được phép.
- [ ] Cân nhắc browser profile/tab có thể bị suspend hoặc restore từ BFCache.
- [ ] Dùng pageshow/visibility revalidation và che sensitive views khi chưa xác minh session.
- [ ] Nút Back không tạo khả năng truy cập resource mới bằng session bị revoke.
- [ ] User B sau user A trên cùng browser không nhìn thấy cached A data.
- [ ] Không dùng client isAuthenticated flag để cấp quyền API.
- [ ] Download, screenshot, clipboard, password manager được ghi rõ là ngoài phạm vi xóa đáng tin của web app.
- [ ] Browser history/query không chứa secrets trong các URL login/logout/recovery.

### 19.6. Clear-Site-Data, cache và security headers

- [ ] Protected HTML/API responses nhạy cảm có **Cache-Control: no-store** theo policy.
- [ ] Hiểu no-store khác private, no-cache và không tự bảo đảm xóa BFCache.
- [ ] Clear-Site-Data chỉ được dùng khi biết browser support và scope.
- [ ] Clear-Site-Data "cookies" được đánh giá tác động lên sibling subdomains/SSO.
- [ ] Clear-Site-Data "storage" không xóa dữ liệu ngoài ý định ở ứng dụng khác cùng origin.
- [ ] Header dọn site data được phát **trong logout response thực**, không tùy tiện ở mọi 401/403.
- [ ] Không cho rằng header xuất hiện thì browser đã thi hành; có test storage sau logout.
- [ ] Có script cleanup/fallback khi browser không hỗ trợ Clear-Site-Data.
- [ ] HTTPS/HSTS được cấu hình đúng phạm vi, không tự bật includeSubDomains thiếu kiểm kê.
- [ ] CSP trên HTML frontend giảm XSS/clickjacking nhưng không được coi là logout mechanism.
- [ ] CORS allowlist cho SPA cross-origin/OPTIONS/actual responses đúng với cookies.
- [ ] HTTP firewall/matcher từ chối URL logout bất thường, không nới policy để sửa lỗi.
- [ ] Referrer-Policy giảm tiết lộ URLs nhạy cảm; không đưa token vào Location.
- [ ] Shared CDN/reverse proxy không cache personalized responses ngoài ý định.

### 19.7. Multi-tab, SSO và concurrency

- [ ] BroadcastChannel hoặc cơ chế tương đương thông báo logout cho tabs cùng origin.
- [ ] Tabs đã suspend/đóng được xử lý bằng revalidation lúc mở/hiện lại.
- [ ] Cross-origin tabs không được giả định nhận BroadcastChannel của origin khác.
- [ ] Broadcast/logout messages không truyền raw token/session ID.
- [ ] PostMessage cross-origin nếu dùng phải kiểm tra event.origin và targetOrigin.
- [ ] SSO/IdP session được phân biệt rõ với local Spring session.
- [ ] OIDC RP-Initiated Logout chọn post-logout URI theo provider registration.
- [ ] Front-channel logout có kiểm thử với browser third-party cookie restrictions.
- [ ] Back-channel logout token có chữ ký, issuer/audience/time/events/sid/sub checks theo protocol.
- [ ] Back-channel messages không được tin chỉ vì Origin/CORS hoặc JSON có userId.
- [ ] Global revoke / device logout được đồng bộ qua shared repository.
- [ ] Request in-flight sau logout được đánh giá, không hứa hồi tố chặn mọi tác vụ đã bắt đầu.
- [ ] Response đến muộn/Set-Cookie khác được test để không rehydrate UI.
- [ ] Spring Session/Redis failover/replication và multi-chain auth đã được kiểm thử.
- [ ] Network timeout trong logout dẫn tới trạng thái **chưa xác nhận**, không báo global success sai.

### 19.8. Kiểm thử và vận hành

- [ ] MockMvc kiểm tra POST logout có CSRF, session invalidation và success redirect.
- [ ] MockMvc kiểm tra POST thiếu/sai CSRF bị từ chối theo policy.
- [ ] HTTP integration test dùng cookie jar chứng minh session ID cũ bị từ chối.
- [ ] WebTestClient kiểm tra Reactive logout success và WebSession lifecycle.
- [ ] Test remember-me auto-login không quay lại sau logout khi policy yêu cầu.
- [ ] Test refresh token cũ bị từ chối và JWT còn hạn theo revocation contract.
- [ ] Test trên nhiều instances dùng shared store/session repository.
- [ ] Browser test Back/BFCache với pageshow.persisted và protected GET mới.
- [ ] Test IndexedDB/Cache Storage/service worker ở trạng thái offline.
- [ ] Test storage cleanup trên browser không hỗ trợ Clear-Site-Data.
- [ ] Test multi-tab và account switch A→B không lộ offline user A data.
- [ ] Test race GET cũ trả 200 sau logout không render lại private UI.
- [ ] Test CORS preflight/actual response khi logout cross-origin.
- [ ] Test cookie name/Path/Domain, HttpOnly, SameSite và Set-Cookie expiration.
- [ ] Test mất mạng trước/sau POST logout cùng retry và partial revocation.
- [ ] Test IdP logout/back-channel khi module SSO được sử dụng.
- [ ] Audit phân biệt logout requested, server success, client cleanup và global revoke completed.
- [ ] Logs/metrics không chứa password, bearer/refresh token, session IDs, PII ngoài mục đích.

## 20. Tổng kết

1. **Logout an toàn không phải chỉ đổi UI hoặc xóa cookie.** Server phải chấm dứt credential hiện hành theo chính sách, và browser phải dọn những bản sao dữ liệu do ứng dụng kiểm soát.
2. **HttpSession/WebSession invalidation** và SecurityContext cleanup bảo vệ request tương lai dùng session cũ; test bằng **protected GET sau logout với credential cũ**, không chỉ HTTP 204/302.
3. **CSRF vẫn quan trọng cho POST /logout** trong ứng dụng cookie/session. Không đổi thành unsafe GET hoặc tắt CSRF chỉ để né 403.
4. Trong **Servlet**, dùng LogoutFilter/LogoutHandlers/LogoutSuccessHandler và cấu hình session invalidation, CSRF, remember-me và cookie cleanup phù hợp.
5. Trong **Reactive/WebFlux**, dùng LogoutWebFilter/ServerLogoutHandler/ServerLogoutSuccessHandler, WebSession invalidation bất đồng bộ và đúng security chain.
6. **Cookie expiration phải khớp name/Path/Domain**; JavaScript không thay server logout và không trực tiếp xóa HttpOnly cookie.
7. **JWT access token, refresh token, remember-me và IdP session** có vòng đời riêng; server session logout không tự revoke tất cả.
8. **Browser giữ nhiều bản sao dữ liệu** trong DOM/memory, localStorage/sessionStorage, IndexedDB, Cache Storage, service worker, HTTP cache và BFCache. Logout không xóa tự động những nơi này.
9. **Cache-Control: no-store** cần thiết cho nhiều protected responses, nhưng không phải lời hứa xóa BFCache/history/downloads/screenshot.
10. **Clear-Site-Data** hữu ích trong browser hỗ trợ, nhưng phải đánh giá domain/origin scope, SSO và apps dùng chung storage; luôn có fallback khi cần.
11. **Đồng bộ multi-tab và vô hiệu response cũ** giúp ngăn data A tái xuất hiện sau logout/account switch, nhưng authorization vẫn chỉ do server quyết định.
12. **OIDC/SSO logout là giao thức riêng**, phải kiểm tra logout URI, token validation, back-channel và phạm vi IdP session.
13. **Concurrent requests** có thể đã qua authentication trước logout; không hứa hủy giao dịch đang chạy nếu chưa có cơ chế phù hợp.
14. **Logout thất bại do mạng** cần ẩn dữ liệu local và thông báo server chưa xác nhận, thay vì nói sai rằng mọi session đã bị thu hồi.
15. **Kiểm thử đầy đủ** gồm Servlet, WebFlux, cookie jar, browser Back/BFCache, offline PWA, multi-tab, SSO, token revocation và shared session store.

## Tài liệu tham khảo định hướng

Khi áp dụng, đối chiếu **Spring Security Reference và API phiên bản dự án**, cùng tài liệu browser thực tế về khả năng Clear-Site-Data/BFCache:

- [Spring Security Reference — Servlet Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html)
- [Spring Security Reference — Servlet CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security Reference — Servlet Security Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html)
- [Spring Security Reference — Reactive Logout](https://docs.spring.io/spring-security/reference/reactive/authentication/logout.html)
- [Spring Security Reference — Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Security Reference — OIDC Logout](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html)
- [MDN — Clear-Site-Data](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Clear-Site-Data)
- [MDN — Cache-Control](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control)
- [MDN — Back/forward cache](https://developer.mozilla.org/en-US/docs/Web/Performance/Guides/Back-forward-cache)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html)

**Nguyên tắc kết thúc bài:** Một logout chỉ được mô tả là hoàn tất trong **phạm vi đã kiểm chứng**: server từ chối credential cũ, ứng dụng dọn những dữ liệu browser thuộc quyền kiểm soát và mọi phiên/token/IdP ngoài phạm vi đó được xử lý hoặc giải thích rõ ràng. Không có một nút hay một HTTP header nào có thể xóa mọi bản sao dữ liệu đã được đưa ra khỏi máy chủ.









