# Phân biệt phiên ứng dụng với phiên đăng nhập của nhà cung cấp danh tính

> **Chủ đề:** Spring Security – federation. **Nhóm kiến thức:** Phiên và trình duyệt. Bài viết giải thích sự khác nhau giữa **phiên đăng nhập cục bộ của ứng dụng (SP/RP application session)** và **phiên Single Sign-On của nhà cung cấp danh tính (IdP/OP SSO session)** trong OIDC, SAML2 và CAS; áp dụng cho ứng dụng Spring Security servlet sử dụng trình duyệt.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Xác định ai tạo, duy trì và hết hạn **phiên ứng dụng** so với **phiên của IdP**.
2. Giải thích tại sao người dùng **logout khỏi ứng dụng A**, quay lại A và có thể đăng nhập ngay mà **không nhập mật khẩu**.
3. Hiểu vì sao **IdP hết phiên không tự xóa ngay** phiên ứng dụng đang hoạt động, trừ khi có thông báo logout/kiểm tra phiên và SP thực thi.
4. Phân biệt **session cookie**, **ID Token**, **OAuth Access Token**, **Refresh Token**, **SAML Assertion**, **CAS Service Ticket** và **CAS Ticket-Granting Ticket**.
5. Xác định tác động của **session timeout**, cookie `Secure`/`HttpOnly`/`SameSite`, HTTPS, session fixation, CSRF và ràng buộc phiên với trình duyệt.
6. Chọn đúng giữa **local logout**, **RP-initiated/IdP-initiated logout**, **SAML Single Logout (SLO)** và **OIDC back-channel logout**, nắm giới hạn khi IdP/ứng dụng không hỗ trợ.
7. Cấu hình Spring Security cho session web và local logout; biết khi nào dùng `OidcClientInitiatedLogoutSuccessHandler` hoặc `saml2Logout`.
8. Kiểm thử độc lập các trạng thái của hai phiên bằng nhiều tab, nhiều ứng dụng, cửa sổ ẩn danh, timeout và logout.
9. Giữ chính sách **reauthentication / step-up** cho tác vụ rủi ro cao, không đánh đồng “đã SSO” với “vừa nhập mật khẩu/MFA”.
10. Thiết kế quy trình hỗ trợ người dùng và điều tra lỗi login-loop / logout-không-hết phù hợp hệ thống federation.

**Nguyên tắc cốt lõi:** IdP xác nhận danh tính để ứng dụng **tạo phiên của chính ứng dụng**. Một lần xác thực tại IdP **không** biến session của tất cả ứng dụng thành **một session chung**. Sự phối hợp giữa các phiên chỉ diễn ra qua các giao thức đăng nhập/đăng xuất và chính sách đã cấu hình.

## 2. Hai phiên sống ở hai hệ thống khác nhau

Xét người dùng mở ba website:

```text
Browser
  |
  +-- https://app-a.example.org     (RP/SP A: báo cáo)
  |      Cookie: JSESSIONID=A-opaque
  |      Server: HttpSession A + SecurityContext A
  |
  +-- https://app-b.example.org     (RP/SP B: nhân sự)
  |      Cookie: JSESSIONID=B-opaque
  |      Server: HttpSession B + SecurityContext B
  |
  +-- https://login.example.org     (IdP / OIDC OP)
         Cookie: IDP_SSO=I-opaque
         Server: IdP login/SSO session I
```

Browser có thể giữ **ba cookie ở ba origin/path khác nhau**. Tên cookie là ví dụ; cookie IdP thực tế do sản phẩm quyết định. Khi browser gọi App A, theo scope cookie nó thường gửi cookie của **App A**, **không gửi cookie IdP cho App A**. Khi bị redirect đến `login.example.org`, browser gửi cookie IdP phù hợp scope của chính IdP, và IdP có thể biết user đã xác thực từ trước.

### 2.1. Phiên ứng dụng (local SP/RP session)

- **Ai sở hữu?** Từng ứng dụng Spring Security, ví dụ App A hay App B.
- **Được tạo khi nào?** Sau khi ứng dụng xác minh OIDC ID Token, SAML Response hoặc CAS Service Ticket và đăng nhập thành công cho user, rồi lưu `Authentication` trong `SecurityContext`/session.
- **Dữ liệu chính?** Session ID opaque ở browser cookie và trạng thái phía server (hoặc session store phân tán), `SecurityContext`, user ID, authorities và dữ liệu ứng dụng.
- **Được dùng khi nào?** Mỗi request browser tới **ứng dụng đó**, không phải mỗi lần đều chuyển sang IdP.
- **Hết hạn bởi ai?** Chính sách session timeout/invalidation của App A; local logout, admin revocation, mất session store, session ID rotation hoặc chính sách bảo mật.
- **Ranh giới?** Một session của App A không mặc nhiên là session của App B; kể cả hai đều xác thực qua cùng IdP.
- **Đặc tính:** Khi App A session còn hợp lệ, IdP có thể **không được gọi tới** cho từng page view; do vậy IdP session hết hạn không nhất thiết khiến App A logout tức thì.

Trong Spring Security Servlet với session persistence, `SecurityContextHolder` biểu diễn authentication hiện tại trong request, còn `HttpSession` (hoặc Spring Session storage) có thể lưu trạng thái phục vụ các request tiếp theo. Đừng dùng `SecurityContextHolder.clearContext()` **một mình** rồi cho rằng mọi session trên server/browser đã bị hủy; cần cơ chế logout/session invalidation phù hợp.

### 2.2. Phiên IdP (OP/IdP SSO session)

- **Ai sở hữu?** Nhà cung cấp danh tính: OpenID Provider, SAML IdP hoặc CAS server.
- **Được tạo khi nào?** Khi user đăng nhập/hoàn thành MFA hoặc chính sách xác thực tại IdP.
- **Dữ liệu chính?** Trạng thái xác thực IdP, browser cookie của IdP, có thể thêm `sid`/session identifier do OP cung cấp, phương thức/`auth_time`/context bảo đảm.
- **Được dùng khi nào?** Khi browser đến IdP ở một luồng đăng nhập mới của App A/B; IdP có thể tái sử dụng xác thực trước đó để phát ID Token/SAMLResponse/Service Ticket.
- **Hết hạn bởi ai?** Chính sách idle/absolute timeout, logout, khóa tài khoản, risk engine/MFA hoặc revocation của IdP.
- **Ranh giới?** Phiên IdP **không phải** cookie `JSESSIONID` của App A. IdP cũng không được tự sửa session store của mọi RP trừ khi có cơ chế liên kết/notification đã triển khai.
- **Đặc tính:** Khi IdP session còn hợp lệ, một ứng dụng vừa logout local có thể redirect về IdP rồi nhận bằng chứng đăng nhập mới **không cần nhập mật khẩu**.

**IdP session không đồng nghĩa “phiên của tổ chức trên mọi thiết bị”.** Browser khác, profile khác, máy khác thường có cookie/SSO session khác; IdP có thể quản lý thêm device-wide session hay remembered device tùy sản phẩm. Hành vi cụ thể phải kiểm thử, không suy đoán từ việc một tài khoản đã login ở trình duyệt khác.

### 2.3. Bảng so sánh nhanh

| Tiêu chí | Phiên ứng dụng A | Phiên IdP |
| --- | --- | --- |
| Chủ sở hữu | SP/RP A | OP/IdP |
| Cookie thông dụng | `JSESSIONID` hoặc cookie session A | Cookie SSO của IdP |
| Server xử lý | App A / Spring Session | IdP server/session store |
| Phạm vi | Các request web được phép của A | Các lần SSO đến IdP cho nhiều RP |
| Tạo khi | A xác minh federation response và thiết lập local authentication | User xác thực/thiết lập SSO tại IdP |
| Có phải token OIDC/SAML? | Không | Không; IdP có thể phát token dựa trên phiên |
| Hết hạn bởi | Timeout/logout/revocation của A | Timeout/logout/revocation của IdP |
| Ảnh hưởng đến B | Không trực tiếp | Có thể giúp B tạo **session B mới** khi browser đến IdP |
| Local logout ở A | Invalidate A session | Thường **không** hủy IdP session |
| IdP logout | Không tự bảo đảm A session bị xóa | Hủy IdP session; cần cơ chế propagated logout để xóa A |
| Đăng nhập lại sau local logout | Có thể SSO ngay nếu IdP session còn | Có thể tái xác thực tự động nếu chính sách cho phép |
| Đồng hồ/timeout | Do ứng dụng và store A cấu hình | Do IdP cấu hình riêng |

## 3. Một lượt đăng nhập OIDC thực tế có những session nào?

Giả sử App A dùng Spring Security `oauth2Login` với OIDC Authorization Code flow.

```text
(1) Browser -> GET https://app-a.example.org/reports
                 chưa có local session A

(2) App A -> 302 đến authorization endpoint của IdP
                 gửi state, nonce, client_id, redirect_uri, scope...
                 có thể dùng PKCE theo client/chính sách

(3) Browser -> IdP
                 đã có IdP cookie hợp lệ?
                 |-- Không -> đăng nhập/MFA -> IdP session I được tạo
                 +-- Có   -> IdP có thể tái sử dụng I nếu policy cho phép

(4) IdP -> 302 về callback App A với authorization code
                 App A xác minh state/correlation

(5) App A backend đổi code lấy token; xác minh ID Token
                 chữ ký, issuer, audience, exp, nonce theo flow

(6) App A -> tạo Authentication + HttpSession A
                 browser nhận cookie session A

(7) Browser -> GET /reports kèm cookie A
                 App A dùng local session; KHÔNG cần gọi IdP mỗi request
```

**Điểm phân biệt về thời gian:** Trong bước (5), ID Token có `iat`, `exp` và có thể `auth_time`; App A dùng chúng theo quy tắc validation **lúc đăng nhập/kiểm tra liên quan**. `exp` của ID Token **không tự động là timeout của HttpSession A**. Tương tự, access token hết hạn không mặc nhiên xóa phiên browser A. Một ứng dụng có thể còn session hợp lệ nhưng phải làm mới access token khi gọi API; nếu việc refresh thất bại thì ứng dụng phải áp chính sách riêng.

**Không suy luận từ ID Token để điều hành SAML/CAS.** OIDC, SAML và CAS dùng artifact và quy tắc đăng nhập riêng, dù cùng có hai tầng phiên.

### 3.1. Vì sao App B không cần nhập mật khẩu sau App A?

Sau khi App A login, IdP session I tồn tại. Browser tới App B:

```text
Browser -> App B /staff
  |
  +-- chưa có session B, chuyển browser sang IdP
        |
        +-- IdP nhận lại cookie I, xác thực vẫn hợp lệ
               |
               +-- IdP phát proof mới cho App B (OIDC/SAML/CAS)
                      |
                      +-- App B kiểm tra riêng
                             |
                             +-- tạo session B
```

App B không lấy `JSESSIONID=A` của App A; nó tạo session B theo kết quả federation **dành cho B** (đúng OIDC audience/client hoặc SAML AudienceRestriction/Recipient). Không nên chia sẻ cookie session giữa hai ứng dụng chỉ vì cả hai sử dụng một IdP.

### 3.2. Khi App A logout local rồi quay lại

```text
T0: App A session = ACTIVE      IdP session = ACTIVE
T1: Browser POST /logout tại A; A session = INVALIDATED
                                IdP session = ACTIVE
T2: Browser GET /reports tại A -> A redirect sang IdP
T3: IdP thấy session I hợp lệ, phát proof cho A
T4: A xác minh proof, tạo A session MỚI
=> User thấy "vừa đăng xuất lại vào ngay", không cần nhập mật khẩu.
```

Đây thường là hành vi **đúng của local logout** chứ không chứng minh `HttpSession.invalidate()` thất bại. Cần phân biệt với trường hợp logout A thật sự **không** xóa session (ví dụ request logout là GET bị chặn CSRF, session store chưa invalidate, browser vẫn gửi cookie A còn hiệu lực). Hai ca có biểu hiện UI giống nhau nhưng dấu vết network khác hẳn.

## 4. Khi IdP session hết hạn nhưng phiên ứng dụng còn sống

Kịch bản ngược:

```text
T0: App A session = ACTIVE       IdP session = ACTIVE
T1: IdP idle timeout/logout      IdP session = EXPIRED
                                App A session = ACTIVE
T2: Browser GET /reports tại A
    App A có session A hợp lệ -> vẫn có thể trả 200
T3: App A cần login lại (A session hết hạn, session bị revoke,
    policy yêu cầu step-up, hoặc IdP-initiated logout đã cập nhật A)
T4: Browser được đưa đến IdP; vì IdP session đã hết
    -> user phải xác thực lại (trừ khi cơ chế khác cho phép).
```

**Đừng suy rằng việc đổi mật khẩu/khóa IdP hoặc IdP logout sẽ ngay lập tức thu hồi mọi session của mọi ứng dụng.** Cần tích hợp back-channel/front-channel logout hoặc cơ chế server-side revocation phù hợp và thực thi trên các session đang tồn tại. Với API stateless, có thể còn access tokens hợp lệ cho tới khi token hết hạn hoặc bị revocation/introspection/policy từ chối.

**Quan trọng:** Chính sách bảo mật có thể quy định “tắt tài khoản ở IdP phải khóa truy cập ngay”. Điều đó cần thiết kế **deprovisioning/session revocation** độc lập, không chỉ giảm TTL của cookie IdP.

## 5. Đừng nhầm session với token và chứng chỉ giao thức

| Thứ người học nhìn thấy | Ai phát/giữ | Dùng để làm gì? | Có thay thế local session không? |
| --- | --- | --- | --- |
| **Application session cookie** `JSESSIONID` | App A/Servlet container hoặc Spring Session | Tham chiếu HttpSession/SecurityContext A | Chính là credential session browser A, nếu app dùng server-side session |
| **IdP SSO cookie** | IdP | Tham chiếu phiên SSO tại IdP khi browser tới IdP | **Không** dùng trực tiếp làm app session |
| **OIDC ID Token** | OP ký cho RP/client | Bằng chứng xác thực danh tính và thông tin phiên theo OIDC | Không tự là cookie session, không dùng làm Bearer token cho API tùy tiện |
| **OAuth Access Token** | Authorization Server phát cho resource audience/scope | Gọi API Resource Server | Không đồng nghĩa phiên RP browser; có hạn và scope riêng |
| **OAuth Refresh Token** | Authorization Server cấp tùy client/policy | Xin access token mới mà không nhất thiết hiện login UI | Không chứng minh IdP SSO cookie còn hiệu lực |
| **SAMLResponse/Assertion** | IdP phát và ký theo profile | SP xác minh và tạo session | Thông điệp đăng nhập, **không** phải session cookie SP |
| **SAML `SessionIndex`** | IdP đưa trong `AuthnStatement` khi có | Có thể liên quan SAML logout/session correlation | Không đồng nhất `HttpSession.getId()` |
| **CAS Service Ticket (ST)** | CAS server cấp cho từng service | Service xác minh ST, lập phiên ứng dụng | Dùng một lần/ngắn hạn, không phải session cookie ứng dụng |
| **CAS Ticket-Granting Ticket (TGT)** | CAS server | Đại diện phiên SSO CAS; browser thường có TGC liên kết | TGT là phiên CAS, không là session local SP |
| **Remember-me cookie / remembered device** | Ứng dụng hoặc IdP theo chính sách | Khôi phục một hình thức đăng nhập/thiết bị | Một cơ chế khác, có thể gây trải nghiệm “login lại” không prompt |

**Session ID trong cookie thường là một giá trị opaque**, không phải JWT. Server có thể dùng Redis/JDBC để lưu session. Nếu ứng dụng áp dụng một thiết kế cookie tự chứa có chữ ký thay vì server-side HttpSession, mô hình lưu trữ khác nhưng **vẫn có phiên ứng dụng độc lập** và cần cơ chế revoke/expiry; bài này tập trung vào Spring Security Servlet dùng HttpSession/Spring Session.

### 5.1. Access token hết hạn có logout web không?

Không thể kết luận chỉ từ `exp`:

- Ứng dụng OIDC Client có thể lưu `OAuth2AuthorizedClient`/refresh token theo repository/service riêng và refresh access token khi cần, trong khi local session vẫn hoạt động.
- Resource Server nhận Bearer token cho từng request thường kiểm tra token mỗi request; nếu API không dùng browser session thì việc token hết hạn có thể gây `401` mà **không liên quan phiên IdP hoặc phiên UI**.
- Nếu ứng dụng chủ động liên kết thời gian session A với thời gian xác thực IdP hoặc token, đó là **chính sách ứng dụng phải cấu hình/kiểm thử**, không phải tương đương mặc định trong mọi framework.

Câu “Token hết hạn, bắt buộc user nhập lại mật khẩu” cũng không luôn đúng: có thể refresh token, IdP SSO cookie hoặc một cơ chế session khác làm đăng nhập lại tự động, trừ khi chính sách yêu cầu tương tác mới.

## 6. Session timeout: ai đo idle và ai đặt absolute lifetime?

Ba bộ đồng hồ thường độc lập:

1. **Ứng dụng A idle timeout:** Sau N phút không có request làm duy trì session, server A có thể expire session; tùy session store và heartbeat, “không thao tác” trong UI vẫn có thể phát request nền.
2. **Ứng dụng A absolute lifetime / max session age:** Chính sách buộc tạo session mới sau một khoảng kể từ lần đăng nhập dù vẫn đang dùng; phải triển khai riêng nếu container/session API chỉ hỗ trợ inactivity timeout.
3. **IdP idle/absolute SSO lifetime:** IdP quyết định cookie/SSO session còn hợp lệ bao lâu, có thể có “remember me” và chính sách authentication context.

Ngoài ra còn `exp` của ID Token, access token, SAML `NotOnOrAfter`, CAS ticket TTL, thời gian của MFA và thời hạn remember-me. Những mốc này **không tự động đồng bộ**.

Ví dụ cấu hình Spring Boot Servlet:

```yaml
server:
  servlet:
    session:
      timeout: 20m
      cookie:
        secure: true
        http-only: true
        same-site: lax
```

Đây là ví dụ **HTTPS web application** sử dụng session của Servlet container. `server.servlet.session.timeout: 20m` là inactivity timeout ở phía ứng dụng, **không cấu hình IdP SSO timeout** và không tự tạo absolute lifetime. Khi dùng Spring Session Redis/JDBC, kiểm tra cấu hình timeout và store thực tế; bảo đảm không có mismatch giữa cookie max-age, session TTL và load balancer.

**Cảnh báo SameSite:** `SameSite=Lax` thường phù hợp nhiều luồng OIDC redirect GET, nhưng **SAML HTTP-POST binding từ IdP về ACS là cross-site POST** trong nhiều deployment. Cookie session của SP có thể không được gửi nếu chính sách browser chặn; việc này làm mất `AuthnRequest`/`InResponseTo` correlation. Cần đánh giá SameSite tương thích SAML POST (có thể cần `SameSite=None; Secure` theo topology/browser), đồng thời giữ CSRF và các bảo vệ khác. Không chọn `None` toàn hệ thống mà không kiểm thử/rà soát rủi ro.

### 6.1. Session cookie và phiên server không cùng một thứ

- **Cookie còn trên browser nhưng session server đã hết:** Browser vẫn gửi cookie, server từ chối Session ID cũ/tạo phiên mới theo policy; không được xem cookie tồn tại là đã xác thực.
- **Server session còn nhưng browser xóa cookie A:** Browser không còn session handle để đến session A; user có thể được redirect tới IdP và tạo session A khác. Server session cũ có thể cần dọn bởi timeout/cleanup; xóa cookie chỉ trên browser không phải đảm bảo revoke server-side.
- **Tab 1 logout local, Tab 2 vẫn có trang cũ đã render:** HTML trong tab có thể còn hiện từ cache, nhưng request API mới phải bị từ chối khi session bị invalidate. Kiểm thử bằng network/reload, không chỉ nhìn nội dung đã tải.
- **Browser restart:** Session cookie có thể được phục hồi bởi tính năng restore; không dùng “đóng browser” làm biện pháp đăng xuất/thu hồi session đáng tin cậy.
- **IdP cookie còn sau RP logout:** Browser có thể silently SSO lại; đây là bản chất local vs IdP session.

## 7. Spring Security: local logout đúng cách

Giả sử ứng dụng sử dụng Spring Boot servlet và `spring-boot-starter-security` + `spring-boot-starter-oauth2-client`, đăng ký OIDC client phù hợp.

File `src/main/java/com/example/sessionlab/OidcLocalLogoutConfig.java`:

```java
package com.example.sessionlab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcLocalLogoutConfig {

    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/signed-out", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/signed-out")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID"))
            .build();
    }
}
```

**Đọc cấu hình:**

- `oauth2Login` đảm nhận OIDC login và tạo local authenticated session sau khi xác minh; không cần tự viết controller xử lý authorization code.
- `logoutUrl("/logout")` cấu hình endpoint logout **của App A**. Với CSRF enabled ở web app, logout thường cần **POST có CSRF token**; không mặc định dùng link GET để logout.
- `invalidateHttpSession(true)` và `clearAuthentication(true)` xóa phiên xác thực ứng dụng theo logout flow. `deleteCookies("JSESSIONID")` yêu cầu browser bỏ session cookie tương ứng; nếu cookie có Domain/Path đặc biệt, kiểm tra header Set-Cookie thực tế.
- `logoutSuccessUrl("/signed-out")` chuyển browser đến trang công khai của **ứng dụng** sau local logout. Ứng dụng cần có route/controller hoặc page tương ứng; chỉ `permitAll` không tự tạo nội dung.
- **Không có bước tới IdP logout endpoint.** Sau khi session A bị hủy, IdP SSO cookie có thể vẫn hợp lệ. Một GET vào URL bảo vệ của A có thể tạo session A mới qua OIDC mà không yêu cầu mật khẩu.
- Đừng chuyển `logout` thành `web.ignoring` hoặc tắt CSRF toàn app. Không dùng `SecurityContextHolder.clearContext()` trong controller riêng như một thay thế đầy đủ cho logout filter.

Đây là class Spring nằm trong dự án Maven/Gradle đã có dependency; nó không biên dịch độc lập bằng `javac OidcLocalLogoutConfig.java` nếu không có classpath Spring. Nếu dự án đã có `SecurityFilterChain` khác, **không đăng ký hai bean chain cùng match toàn bộ URL**; tích hợp logic vào chain phù hợp.

### 7.1. Form logout có CSRF của Spring MVC/Thymeleaf

Một ứng dụng dùng server-side template và Spring Security CSRF integration có thể render:

```html
<form method="post" action="/logout">
  <input type="hidden" name="_csrf" value="CSRF_TOKEN_TU_SERVER">
  <button type="submit">Đăng xuất khỏi ứng dụng này</button>
</form>
```

Đây là **hình dạng minh họa**, không chép giá trị `CSRF_TOKEN_TU_SERVER` nguyên văn. Trong Thymeleaf/Spring MVC, lấy token động từ request/template integration. Không đặt CSRF token tĩnh trong source và không dùng query string chứa token rồi chia sẻ qua ticket.

**Chạy thử trong trình duyệt:** Login OIDC, GET URL bảo vệ trả 200, POST logout hợp lệ, sau đó GET lại URL bảo vệ sẽ bắt đầu OIDC login; nếu IdP SSO còn thì quá trình có thể hoàn thành ngay. Để phân biệt, kiểm tra network redirect sang IdP và session ID mới chứ không dựa vào việc user có nhìn thấy form mật khẩu hay không.

### 7.2. Không “logout” bằng JavaScript xóa cookie bừa bãi

Browser JavaScript không thể đọc/xóa cookie `HttpOnly` bằng cách thông thường; server mới có quyền invalidation HttpSession. Các thao tác như `document.cookie="JSESSIONID=..."` có thể không đụng đúng Domain/Path/Secure và không xóa session server. Local logout chuẩn đi qua Spring Security `LogoutFilter`/`LogoutHandler`; thành phần ứng dụng khác như OAuth authorized client repository, refresh tokens hoặc state tùy biến cũng cần kiểm tra cleanup theo policy.

## 8. OIDC: đăng xuất từ RP và IdP phải phối hợp

OIDC hỗ trợ **RP-Initiated Logout**, một cơ chế để RP yêu cầu OP đăng xuất user. Các bên cần thống nhất endpoint và redirect sau logout.

### 8.1. Sơ đồ

```text
Browser        App A (OIDC RP)                   IdP (OP)
   |                |                               |
   | POST /logout   |                               |
   |--------------->|                               |
   |  local logout  |                               |
   |<-- 302 to OP end_session_endpoint ------------|
   |----------------------------------------------->|
   |                |    OP xác nhận/logout session |
   |<--------------- post-logout redirect ----------|
   | GET /signed-out|                               |
   |--------------->|                               |
   |<--- public page|                               |
```

**Có thể xảy ra trường hợp OP yêu cầu xác nhận của người dùng** hoặc không có endpoint hỗ trợ. Một redirect đến `end_session_endpoint` **không tự chứng minh** OP thực sự hủy session, cũng không đảm bảo mọi RP khác đã được thông báo/hủy session. OIDC RP-Initiated Logout định nghĩa các tham số như `id_token_hint` và `post_logout_redirect_uri` với điều kiện kiểm tra của OP; ứng dụng không nên tự ghép URL logout từ dữ liệu đầu vào.

### 8.2. Ví dụ Spring Security với `OidcClientInitiatedLogoutSuccessHandler`

Đây là **cấu hình thay thế** mục 7 khi muốn yêu cầu logout OP. Không đặt cả hai config toàn URL trong cùng một ứng dụng.

File `src/main/java/com/example/sessionlab/OidcFederatedLogoutConfig.java`:

```java
package com.example.sessionlab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.oidc.web.logout.OidcClientInitiatedLogoutSuccessHandler;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcFederatedLogoutConfig {

    @Bean
    SecurityFilterChain web(
            HttpSecurity http,
            ClientRegistrationRepository registrations) throws Exception {

        OidcClientInitiatedLogoutSuccessHandler oidcLogout =
            new OidcClientInitiatedLogoutSuccessHandler(registrations);
        oidcLogout.setPostLogoutRedirectUri("{baseUrl}/signed-out");

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/signed-out", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .logoutSuccessHandler(oidcLogout))
            .build();
    }
}
```

**Điều kiện tiên quyết:** OP hỗ trợ RP-Initiated Logout và công bố `end_session_endpoint` trong discovery (hoặc cơ chế cấu hình được framework hỗ trợ), client registration đúng `issuer-uri`/client, và `post_logout_redirect_uri` đã được đăng ký/cho phép ở OP. Dùng HTTPS và kiểm tra canonical URL qua reverse proxy; `{baseUrl}` phụ thuộc scheme/host mà Spring nhìn thấy.

**Hành vi:** Spring xử lý local logout rồi logout success handler cố chuyển browser đến OP. Theo OP/policy, browser có thể được hỏi xác nhận hoặc redirect về. Để thực hiện POST đến OP thay vì redirect GET, Spring có chiến lược `FormPostRedirectStrategy` theo phiên bản/khả năng; không tự viết JavaScript gửi token nhạy cảm khi không cần.

**Chú ý:** RP-Initiated Logout là **yêu cầu** đăng xuất ở OP, không mặc nhiên là “global logout chắc chắn thành công”. Nếu browser mất mạng, user đóng tab, OP từ chối yêu cầu, hoặc sản phẩm không hỗ trợ endpoint, kết quả có thể chỉ mới hủy session A. Ứng dụng vẫn phải thông báo mức độ thực sự đạt được, không hiển thị “đã đăng xuất tất cả nơi” khi không có bằng chứng.

### 8.3. OP-initiated / Back-channel logout

OIDC có các cơ chế OP gửi thông báo tới RP:

- **Front-channel logout:** OP yêu cầu browser chuyển/tải endpoint logout của các RP; phụ thuộc browser/cookie, có thể bị chặn bởi chính sách third-party cookie hoặc frame/redirect.
- **Back-channel logout:** OP gửi **Logout Token** qua kết nối server-to-server tới endpoint RP. RP phải xác minh JWT logout token (issuer, audience, sự kiện logout, `iat`, `jti`/replay, `sid` hoặc `sub` theo profile), rồi tìm và hủy local sessions phù hợp.
- **Session Management:** có thể theo dõi thay đổi phiên OP qua cơ chế được thỏa thuận; độ tin cậy chịu tác động từ browser.

Spring Security có hỗ trợ OIDC back-channel logout theo phiên bản, thường cần bật cấu hình riêng như `oidcLogout(...).backChannel(...)` và bảo đảm registry ánh xạ OP session/user với local sessions. Endpoint mặc định có thể có dạng `/logout/connect/back-channel/{registrationId}`, **không phải POST /logout cục bộ của người dùng**. Đối chiếu đúng tài liệu servlet của bản Spring Security thực tế; đừng dùng code WebFlux trong ứng dụng Servlet.

**Không đánh đồng `sid` của OP với `HttpSession.getId()`:** `sid` là IdP-side session identifier có thể được IdP đưa trong token; backend cần registry liên kết các giá trị đã được xác minh. Một OP logout event theo `sub` có thể liên quan nhiều phiên RP của cùng user/client, trong khi event theo `sid` nhắm phạm vi OP session cụ thể; mọi thao tác invalidation phải giới hạn theo issuer/client đã xác minh.

**Nếu RP không xử lý thông báo logout:** IdP đã logout không có nghĩa session A tự biến mất. Cần kiểm tra failure behavior, retry, idempotency, ordering, HA registry và session-store consistency trong thử nghiệm.

## 9. SAML2: IdP session, SP session và Single Logout

Trong SAML 2.0 Web Browser SSO:

```text
SP A: lưu local HttpSession A
IdP: lưu SSO session do IdP quản lý
AuthnRequest -> IdP
SAMLResponse/Assertion -> SP A ACS
SP A xác minh -> tạo Authentication + HttpSession A
```

SAML assertion có thể chứa `AuthnStatement` và `SessionIndex`, nhưng **`SessionIndex` không phải session ID của SP**. IdP có thể dùng `SessionIndex` trong SAML Single Logout để xác định phiên/đối tượng logout. Mỗi SP vẫn phải tìm và invalidation **session cục bộ tương ứng**.

### 9.1. Local logout khác SAML SLO

- **Local logout:** SP A invalidates own `HttpSession`; IdP session thường còn. Truy cập lại A có thể dẫn đến `AuthnRequest` mới và IdP SSO không yêu cầu nhập mật khẩu.
- **SP/RP-initiated SLO:** SP A gửi `saml2:LogoutRequest` đã ký theo chính sách đến IdP. IdP xử lý, có thể thông báo tới SP khác, rồi gửi `LogoutResponse` về SP A. Phải xử lý đủ tình huống lỗi/partial completion.
- **IdP/AP-initiated SLO:** IdP gửi `LogoutRequest` đến SP A; SP xác minh chữ ký/issuer/destination/correlation/profile rồi hủy session liên quan và gửi `LogoutResponse`.
- **Không hỗ trợ SLO:** Nếu IdP hoặc SP không có đăng ký `SingleLogoutService`/signing credentials/binding phù hợp, local logout **không trở thành SLO** chỉ bằng việc gọi logout endpoint thông thường.

**Ví dụ cấu hình Spring Security SAML (là alternative độc lập với OIDC):**

```java
package com.example.sessionlab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlLogoutChoiceConfig {

    @Bean
    SecurityFilterChain samlWeb(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/signed-out", "/error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())

            // Chỉ hủy phiên SP, không gọi IdP SLO.
            .logout(logout -> logout
                .logoutUrl("/logout-local")
                .logoutSuccessUrl("/signed-out"))

            // Chỉ hoạt động đúng khi IdP và RP đã cấu hình SLO.
            .saml2Logout(saml -> saml
                .logoutUrl("/logout-federated"))

            .build();
    }
}
```

**Điều kiện trước khi triển khai SLO:** Bean `RelyingPartyRegistrationRepository` phải có IdP metadata hỗ trợ `SingleLogoutService`, URL SLO/ACS chính xác, SP signing private key/certificate (khi cần) và IdP signing verification certificate đáng tin. `saml2Logout` không tạo ra signing key hay đăng ký đối tác thay cho bạn. Mẫu class là thành phần dự án Spring Boot/Spring Security có SAML2 dependency; không phải chương trình Java thuần biên dịch độc lập.

Spring Security reference có ví dụ tách `POST /logout` local và `POST /saml2/logout` federated. Đường `/logout-federated` ở trên là **tên do bài chọn**; URL IdP gửi LogoutRequest tới SP là endpoint SLO protocol khác, thường `/logout/saml2/slo` theo cấu hình/default framework. Không dùng `permitAll("/logout/**")` hoặc tự nhận XML logout để xóa session bất kỳ.

### 9.2. Vì sao SAML SLO có thể thất bại một phần?

- Một SP khác offline hoặc URL SLO không truy cập được.
- Các SP khác còn session nhưng không hỗ trợ SLO, hoặc không lưu liên kết `NameID + SessionIndex` đúng.
- Binding Redirect/POST, ký số, `Destination`, certificate rollover hoặc correlation sai.
- Browser đóng tab khi SLO front-channel chưa hoàn tất; cookie SameSite/bảo vệ browser làm request không được chuyển.
- Cluster SP không thể tìm session tương ứng do session store/registry không đồng bộ.
- Một ứng dụng đã logout nhưng phiên của những ứng dụng khác vẫn hoạt động.

Do đó, không nên hứa “đăng xuất khỏi hệ thống” là chắc chắn đã xóa **mọi phiên trên mọi ứng dụng/thiết bị**. Với yêu cầu rủi ro cao, cần kiểm tra bằng số liệu phiên thực tế/điều phối revocation và định nghĩa SLA.

## 10. CAS: TGT/TGC khác Service Ticket và session ứng dụng

Apereo CAS dùng thuật ngữ:

- **Ticket-Granting Ticket (TGT):** đại diện phiên SSO ở CAS server; thường liên kết với **Ticket-Granting Cookie (TGC)** của browser tại miền CAS.
- **Service Ticket (ST):** credential một lần dành cho một `service` cụ thể; CAS phát khi user được xác thực hoặc có TGT hợp lệ.
- **Application session:** sau khi App A xác minh ST với CAS, App A tạo local session của mình. CAS không quản lý trực tiếp HttpSession của từng app.

Ví dụ:

```text
Browser -- GET /app-a/private --> App A
App A -- redirect /login?service=app-a --> CAS
CAS có TGT/TGC hợp lệ?
    Có -> phát ST cho App A, không nhập lại mật khẩu
    Không -> user login -> CAS tạo TGT/TGC -> phát ST
Browser -- ST một lần --> App A callback
App A -- /serviceValidate --> CAS
App A -- tạo HttpSession A
```

**Local logout App A** có thể xóa session A mà TGT/TGC vẫn còn; lần vào tiếp theo CAS phát ST mới không cần nhập mật khẩu. **CAS /logout** hủy CAS SSO session/TGT nhưng local sessions của các service **cần cơ chế Single Logout** để bị hủy. CAS có thể gửi logout notifications; từng CAS client/service phải nhận, xác minh/đối chiếu ticket-session và thực hiện invalidation đúng. Không coi CAS SLO chỉ là redirect user tới `/logout` mà bỏ qua service-side cleanup.

Đừng cố sử dụng ST như long-lived session cookie, vì ST có phạm vi service và quy tắc dùng một lần. TGT/TGC cũng không phải `JSESSIONID` của Spring app.

## 11. Yêu cầu nhập lại mật khẩu/MFA: “SSO còn” không bằng “xác thực mới”

Một trường hợp hay gây hiểu nhầm: người dùng đã SSO từ sáng, buổi chiều mở chức năng chuyển tiền/đổi quyền admin. Ứng dụng có local session và IdP session hợp lệ, nhưng chính sách có thể yêu cầu **fresh authentication** hoặc step-up.

### 11.1. OIDC `prompt`, `max_age` và `auth_time`

OIDC hỗ trợ các tham số authorization request:

- `prompt=login`: yêu cầu OP **xác thực lại** user, kể cả đang có OP session.
- `max_age=300`: yêu cầu lần xác thực tại OP có tuổi không vượt quá 300 giây; nếu quá thì OP phải thực hiện active reauthentication. Khi gửi `max_age`, ID Token trả về phải có `auth_time`.
- `prompt=none`: yêu cầu OP không tương tác với user; nếu không thể đáp ứng thì trả lỗi thích hợp như `login_required` hoặc `interaction_required`.
- `acr_values` hoặc claim `acr`/`amr` có thể mô tả mức/kiểu xác thực theo hợp đồng OP, **không tự chứng minh** user đã MFA đúng yêu cầu của tổ chức nếu không map policy.

**Lưu ý:** OIDC `max_age` nói về **thời gian xác thực tại OP**, không phải HTTP idle timeout của App A. `auth_time` là mốc từ OP đã ký/kiểm tra; không tin `auth_time` từ query string browser. Nếu app cần chứng minh “user vừa reauthenticate”, phải buộc flow mới, kiểm tra `auth_time`/`acr` theo policy và gắn kết quả vào local session/authorization decision. Không chỉ hiển thị login screen mà không kiểm tra ID Token trả về.

### 11.2. SAML `ForceAuthn` và `IsPassive`

Trong SAML `AuthnRequest`, SP có thể yêu cầu:

- `ForceAuthn="true"`: IdP cần trực tiếp xác thực lại presenter thay vì chỉ dựa vào phiên xác thực cũ, theo profile/quy tắc IdP.
- `IsPassive="true"`: IdP không được tương tác trực tiếp với user; nếu không thể xác thực thụ động có thể trả trạng thái lỗi thích hợp.

SAML `AuthnStatement/AuthnInstant` và `AuthnContextClassRef` có thể cung cấp tín hiệu về thời gian/ngữ cảnh xác thực. Chỉ sử dụng sau khi assertion được xác minh và đối chiếu với policy đã ký kết. Tương tự OIDC, **`ForceAuthn` không tự rút ngắn HttpSession đã có**; phải khởi tạo một round-trip mới khi chính sách cần.

### 11.3. CAS `renew=true`

CAS protocol hỗ trợ tham số `renew=true` để yêu cầu xác thực bằng primary credentials cho một service request, thay vì chỉ dùng TGT/TGC SSO hiện tại. Cách áp dụng và enforcement phải được kiểm tra trong CAS client/server thực tế; không gửi tham số tùy tiện ở mọi URL mà không xác minh service-ticket validation tương ứng.

**Không suy luận rằng SSO = MFA liên tục.** Mức bảo đảm cần được quyết định theo thời điểm và ngữ cảnh của hành động, không chỉ dựa vào việc phiên IdP còn tồn tại.

## 12. An ninh session/browser cần áp dụng cho từng phía

### 12.1. Cookie và đường truyền

- **`Secure`:** chỉ gửi session cookie qua HTTPS (trừ cơ chế/ngoại lệ phát triển có kiểm soát); production phải dùng HTTPS cho cả SP và IdP.
- **`HttpOnly`:** hạn chế JavaScript đọc session cookie, giảm khả năng bị đánh cắp qua một số XSS; **không thay thế chống XSS**.
- **`SameSite`:** giảm một số CSRF/cross-site cookie flows; cần thử nghiệm OIDC redirect, SAML POST ACS, iframe/front-channel logout và browser mới.
- **Domain/Path:** giới hạn phạm vi cookie; không tùy tiện chia `JSESSIONID` giữa nhiều subdomain; quản lý host-only cookie khi có thể.
- **HSTS/CSP:** áp dụng policy phù hợp HTTPS/frontend; CSP có thể ảnh hưởng form POST auto-submit và front-channel SLO.
- **Không ghi session ID vào URL/query/log:** Session fixation và leak qua referrer/proxy là nguy cơ. Không dùng `jsessionid` trong URL nếu có thể tắt URL rewriting.

### 12.2. Session fixation và CSRF

Spring Security Servlet có session fixation protection: sau khi login thành công, framework có thể **đổi session ID** (mặc định `changeSessionId` trên servlet hiện đại). Điều này không liên quan tới việc đổi IdP SSO cookie. Không tắt `sessionFixation` để “giữ cùng JSESSIONID” trong mọi lần login.

Logout là tác vụ thay đổi trạng thái, nên dùng **POST có CSRF token** với ứng dụng session cookie. Nếu cho GET `/logout` không cần CSRF, một website ngoài có thể làm người dùng bị logout ngoài ý muốn (logout CSRF). Với OIDC/SAML các endpoint callback giao thức có cơ chế correlation/signature/state riêng; đừng dùng chúng làm lý do tắt CSRF toàn bộ web.

### 12.3. Session ID, quyền và account liên kết

Sau login, local session chứa **Authentication của đúng account và quyền đã được map**. Nếu người dùng đổi account tại IdP mà App A vẫn còn local session A, UI App A có thể tiếp tục hiển thị user A cũ cho tới khi logout/re-authentication theo policy. Đừng giả định “tài khoản vừa chọn ở IdP” đã tự thay Authentication trong session hiện tại.

Khi app có nhiều IdP/tenant, phải lưu issuer+subject (OIDC), hoặc SAML issuer+stable identifier và registration, không tự link cùng user bằng email. Session của tenant A phải được ràng buộc với tenant A; logout/revocation phải tìm đúng sessions, tránh xóa nhầm user/tenant khác.

**Thu hồi quyền:** Nếu user bị xóa `ROLE_ADMIN` ở IdP, session A đã tạo từ trước có thể giữ authorities cũ. Chính sách nhạy cảm có thể cần tái đánh giá quyền theo server-side store, session invalidation, event deprovisioning hoặc short lifetimes, không chỉ tin session đến idle timeout.

## 13. Ví dụ Java 17 độc lập: mô phỏng hai trạng thái phiên

Ví dụ sau **chỉ minh họa state machine**, không thực hiện HTTP, OIDC/SAML, ký token, cookie hay lưu session. Nó cho thấy một browser có IdP SSO session và hai session ứng dụng độc lập.

File `TwoSessionModelDemo.java`:

```java
public class TwoSessionModelDemo {

    static final class Browser {
        boolean idpSession;
        boolean appASession;
        boolean appBSession;

        String visitA() {
            if (appASession) {
                return "A: existing local session";
            }
            if (idpSession) {
                appASession = true;
                return "A: new local session via SSO";
            }
            return "A: login at IdP required";
        }

        String loginAAtIdp() {
            idpSession = true;
            appASession = true;
            return "A: login at IdP and new local session";
        }

        String visitB() {
            if (appBSession) {
                return "B: existing local session";
            }
            if (idpSession) {
                appBSession = true;
                return "B: new local session via SSO";
            }
            return "B: login at IdP required";
        }

        void localLogoutA() {
            appASession = false;
        }

        void endIdpSessionWithoutNotifications() {
            idpSession = false;
        }

        void localLogoutB() {
            appBSession = false;
        }
    }

    public static void main(String[] args) {
        Browser browser = new Browser();

        System.out.println("firstA=" + browser.visitA());
        System.out.println("login=" + browser.loginAAtIdp());
        System.out.println("firstB=" + browser.visitB());

        browser.localLogoutA();
        System.out.println("afterLocalLogoutA=" + browser.visitA());

        browser.endIdpSessionWithoutNotifications();
        System.out.println("afterIdpEndB=" + browser.visitB());

        browser.localLogoutA();
        browser.localLogoutB();
        System.out.println("afterBothLocalEndA=" + browser.visitA());
    }
}
```

Chạy trên JDK 17+:

```bash
javac --release 17 TwoSessionModelDemo.java
java TwoSessionModelDemo
```

Stdout xác định:

```text
firstA=A: login at IdP required
login=A: login at IdP and new local session
firstB=B: new local session via SSO
afterLocalLogoutA=A: new local session via SSO
afterIdpEndB=B: existing local session
afterBothLocalEndA=A: login at IdP required
```

**Giải thích từng trạng thái:**

1. `firstA`: chưa có session nào nên cần xác thực tại IdP.
2. `login`: sau xác thực, IdP session và App A session được tạo.
3. `firstB`: App B chưa có session nhưng có thể SSO qua IdP, rồi tạo session B riêng.
4. `afterLocalLogoutA`: A đã hủy local session; vì IdP còn phiên nên lần vào tiếp theo tạo phiên A mới mà không cần nhập mật khẩu.
5. `afterIdpEndB`: mô phỏng **chỉ kết thúc IdP session mà không gửi/nhận thông báo logout**; session B vẫn được chấp nhận.
6. `afterBothLocalEndA`: khi cả local sessions bị xóa và IdP session không còn, lần vào A phải xác thực lại.

**Đây không phải mô phỏng global SLO.** Trong một triển khai thật có OIDC back-channel logout/SAML SLO và notifications thành công, việc IdP kết thúc phiên **có thể** khiến A/B cũng bị hủy. Chương trình cố ý chỉ kiểm tra trường hợp không có propagation để làm rõ hai vòng đời độc lập.

## 14. Kiểm thử browser thật: phải quan sát cả cookie và phiên server

Chuẩn bị hai ứng dụng test A/B (hoặc một app test cùng IdP), HTTPS, một IdP test và user không nhạy cảm. Không sử dụng production session/cookie/token để debug công khai.

### 14.1. Quy trình chứng minh local logout không phải IdP logout

1. Xóa session test từ trước trong **profile test riêng**, không ảnh hưởng profile làm việc thật.
2. Vào URL bảo vệ của A, chuyển IdP, nhập mật khẩu user test, hoàn tất SSO.
3. Vào B cùng profile browser: kiểm tra browser đến IdP rồi tự hoàn tất SSO, tạo **B session cookie** riêng.
4. Tại A, thực hiện **POST local logout** bằng form/CSRF đúng; kiểm tra App A session bị invalidate.
5. Không logout IdP. Vào URL bảo vệ A lần nữa: nếu OP SSO còn, browser có thể login lại mà không hiện password prompt; **A session ID mới**.
6. Vào B: B session vẫn hợp lệ. Kết luận local logout A không có quyền xóa tự động B session/IdP session.

**Bằng chứng kỹ thuật:** Network waterfall có redirect A→IdP→A, cookie A được rotate/invalidate; B cookie/session không bị thay do A logout. Không chỉ nhìn giao diện “Hello user” hay dropdown tên vì page cũ có thể cache.

### 14.2. Quy trình chứng minh IdP session hết không đồng nghĩa SP hết

1. Login A và B, ghi thời gian phiên test, không copy cookie raw vào ticket.
2. Trong test IdP, kết thúc **SSO session** theo giao diện admin hoặc endpoint được hỗ trợ; **không** gửi logout notifications tới A/B trong bài thử cô lập (hoặc dùng môi trường test không bật SLO).
3. GET endpoint bảo vệ A bằng cookie A **còn hợp lệ**: có thể vẫn 200.
4. Invalidate local session A: GET A lại sẽ cần IdP reauthentication; đây là lúc ảnh hưởng IdP session hết được nhìn thấy.
5. Lặp với B; kiểm tra session B có chính sách riêng.
6. Bật lại logout notification trong môi trường test rồi thử riêng: nếu tích hợp đúng, các phiên SP được nhắm tới phải bị invalidate theo policy.

### 14.3. Kiểm thử cookie/SameSite/khác browser

- Trong cùng browser profile, mở hai tab của A: chúng thường chia sẻ session cookie A. Logout một tab làm request bảo vệ mới của tab còn lại cần xác thực lại.
- Mở A trong cửa sổ **ẩn danh**: cookie jar riêng, không tự chia sẻ A/IdP session của profile thường, trừ những cơ chế OS/SSO đặc biệt cần kiểm thử riêng.
- Mở A trên điện thoại hoặc browser khác: session IdP và session A khác; một local logout ở máy 1 không mặc nhiên logout máy 2.
- SAML HTTP-POST ACS có thể mất correlation nếu `SameSite=Lax` không gửi session cookie trong cross-site POST; xem DevTools Cookies và response headers.
- Khi browser chặn third-party cookies/iframes, front-channel logout và silent auth có thể không hoạt động; cần đánh giá back-channel logout nếu phù hợp.
- Test sau restart browser và session restore; không dựa vào việc “đóng browser” như cách thu hồi server sessions.
- Test ở ingress/proxy HTTPS thực tế vì sai scheme/host/Secure cookie dễ tạo redirect loop.

### 14.4. Ma trận kết quả

| Trạng thái local A | Trạng thái IdP | Request A | Hành vi thường thấy |
| --- | --- | --- | --- |
| ACTIVE | ACTIVE | GET tài nguyên A | Dùng session A; không cần IdP round-trip |
| INACTIVE | ACTIVE | GET tài nguyên A | Redirect IdP rồi có thể SSO lại, tạo session A mới |
| ACTIVE | INACTIVE | GET tài nguyên A | Có thể vẫn dùng session A; phụ thuộc revocation/reauth policy |
| INACTIVE | INACTIVE | GET tài nguyên A | Cần xác thực tại IdP hoặc cơ chế khác được phép |
| ACTIVE | ACTIVE nhưng policy step-up | GET tác vụ nhạy cảm | Cần reauthentication/assurance theo policy, dù session A còn |
| INACTIVE | ACTIVE, `prompt=login` | OIDC login mới | OP phải yêu cầu reauthentication theo OIDC |
| INACTIVE | ACTIVE, `max_age` chưa vượt | OIDC login mới | OP có thể tái sử dụng chứng cứ xác thực nếu policy cho phép |
| ACTIVE | OP đã gửi logout notification hợp lệ và RP xử lý | Request A sau invalidate | Không được dùng session A cũ |
| ACTIVE | OP logout notification thất bại | Request A | Có thể vẫn được cho phép nếu không có cơ chế revocation khác |
| B ACTIVE, A vừa logout local | IdP ACTIVE | GET B | B vẫn hoạt động theo session riêng |

**Chữ “có thể” là có chủ ý:** Mỗi ứng dụng có policy session và mỗi IdP có policy riêng; các kết quả phụ thuộc vào việc đã triển khai SLO/back-channel/absolute timeout/step-up hay chưa. Kiểm thử cần ghi **cấu hình hiệu lực**, không dự đoán từ tài liệu sản phẩm.

## 15. Các lỗi vận hành và chẩn đoán theo dấu hiệu

| Hiện tượng | Nguyên nhân có thể | Kiểm tra/sửa |
| --- | --- | --- |
| “Tôi bấm logout rồi vẫn đăng nhập vào ngay” | App A local logout thành công nhưng IdP session vẫn ACTIVE; redirect sang IdP SSO | Kiểm tra network A→IdP→A và session ID mới. Nếu muốn logout cả IdP, cấu hình OIDC RP-initiated logout/SAML SLO phù hợp |
| “Logout xong, bấm Back vẫn thấy trang” | Browser cache lưu HTML, chưa kiểm tra request mới | Reload và test API; bảo vệ response dữ liệu nhạy cảm bằng Cache-Control hợp lý |
| “Logout không thành công, cookie A không đổi” | GET /logout bị CSRF chặn, endpoint sai, session chưa invalidate | Dùng POST có CSRF, kiểm tra LogoutFilter, session store và Set-Cookie |
| “IdP logout nhưng App A vẫn xem báo cáo được” | App A session còn; chưa có hoặc lỗi SLO/back-channel/revocation | Kiểm tra session A, logout notifications, registry và policy |
| “A logout làm B logout theo” | Đã bật federated/global logout, hoặc chung session store/cookie không đúng thiết kế | Xác nhận mong muốn nghiệp vụ, phân biệt local vs global, kiểm tra phạm vi notifications |
| “Ứng dụng cứ vòng lại trang login” | Session cookie không được gửi/ghi, `SameSite`, Secure/HTTPS proxy, request correlation | Kiểm tra cookie/headers/ACS/redirect URI và session ID; không tắt state/nonce/InResponseTo |
| “Token OIDC hết hạn nhưng user vẫn dùng app” | Token expiration khác HttpSession timeout; authorized client có thể refresh | Kiểm tra app session, refresh token policy, API tokens và session lifetime |
| “IdP không hiện prompt dù yêu cầu fresh MFA” | Chưa gửi `prompt=login`/`max_age` hay chưa kiểm tra `auth_time`/`acr` | Thiết kế reauthentication flow, kiểm tra claims đã xác minh và assurance policy |
| “SAML `ForceAuthn` không đổi local session” | ForceAuthn chỉ áp dụng khi tạo AuthnRequest mới; local session hiện tại vẫn được dùng | Buộc đúng round-trip và cập nhật security context sau khi xác thực lại |
| “CAS /logout đã gọi nhưng app vẫn login” | TGT bị hủy nhưng CAS SLO notification/client không hủy local session | Kiểm tra CAS client hỗ trợ Single Logout và store ticket→session |
| “SAML SLO có lúc hủy A, lúc không” | SessionIndex/NameID, SLO binding/signature, cache, HA hoặc browser đóng tab | Kiểm tra LogoutRequest/Response được verify, session mapping và timeout |
| “Bị 401 API, nhưng website vẫn login” | Access Token API hết hạn/sai audience; web session riêng | Kiểm tra resource server JWT/opaque token, refresh và session policy |
| “Người dùng bị xóa group, app vẫn cho phép” | Spring session lưu authorities tại login, chưa refresh/revoke | Đồng bộ deprovision và kiểm tra quyền động ở tác vụ nhạy cảm |
| “Safari/chrome privacy làm silent login/logout fail” | Third-party cookie/iframe policies, SameSite, IdP tracking protections | Thử top-level redirect và back-channel phù hợp; không tắt browser protections |
| “Logout tài khoản A nhưng vào thấy tài khoản B” | OP session của user khác, account chooser/remembered IdP login, local session cũ | Kiểm tra issuer/sub/NameID, browser profiles, IdP user selection và local account mapping |

### 15.1. Cây quyết định cho hỗ trợ kỹ thuật

```text
User nói "không logout được"
  |
  +-- Có POST local logout hợp lệ chưa? (CSRF, status, route)
       |
       +-- Chưa -> sửa UI/logout endpoint
       |
       +-- Rồi -> session A trên server đã invalidated chưa?
                    |
                    +-- Chưa -> sửa session store/filter/handler
                    |
                    +-- Rồi -> browser có redirect sang IdP không?
                                 |
                                 +-- Có -> IdP SSO còn, A tạo session mới
                                 |         -> kỳ vọng local vs federated logout?
                                 |
                                 +-- Không -> kiểm tra cache/page/session khác
  |
  +-- User muốn "logout toàn bộ"?
       |
       +-- Chọn và xác minh RP-initiated/SLO/back-channel,
           kiểm tra các RP tham gia, sessions trên thiết bị khác,
           thời gian xử lý và partial failures.
```

Log nên ghi `requestId`, issuer/registration, local account ID dạng tham chiếu an toàn, login/logout event type, session lifecycle action, IdP/logout-correlation status và kết quả; **không ghi raw session cookie, ID Token, Access Token, SAMLResponse, CAS TGT/ST hay refresh token**.

## 16. Thiết kế UX: ghi đúng phạm vi đăng xuất

Nút logout cần mô tả đúng tác dụng:

- **“Đăng xuất khỏi ứng dụng này”** khi chỉ invalidates local app session.
- **“Đăng xuất khỏi tài khoản SSO”** khi có yêu cầu OP/IdP logout, nhưng vẫn cần đánh giá notification và trạng thái thực tế.
- **“Đăng xuất khỏi các thiết bị”** chỉ khi hệ thống thật có inventory session/device và cơ chế revoke tương ứng, không dựa vào redirect browser đến IdP.
- Trang thành công không nên hứa “tất cả ứng dụng đã đăng xuất” khi chỉ chứng minh được A local logout.
- Khi IdP SSO còn, hiển thị thông điệp rõ: truy cập lại trang cần bảo vệ có thể tự động đăng nhập nếu phiên IdP vẫn còn.
- Khi là thiết bị dùng chung, khuyến nghị logout ứng dụng và IdP theo policy, đóng browser profile và không lưu thông tin đăng nhập/remember-me; **không** coi xóa browser history là revoke session.

Việc tách hai nút “logout ứng dụng” và “logout SSO” có thể hữu ích trong môi trường nhiều ứng dụng: người dùng muốn rời một ứng dụng nhưng tiếp tục làm việc ở ứng dụng khác. Tuy nhiên khi rủi ro truy cập cao, policy có thể ưu tiên centralized logout/revocation. UX phải phản ánh chính sách đó.

## 17. Checklist production cho Spring Security federation

- [ ] Sơ đồ hệ thống phân biệt **A HttpSession**, **B HttpSession** và **IdP SSO session**; không gộp bởi cookie/domain tùy tiện.
- [ ] Đã viết rõ idle timeout/absolute timeout/revocation policy **của từng bên**, không suy ID Token exp = app session timeout.
- [ ] Spring Security login xác minh đúng OIDC `iss/aud/nonce/state` hoặc SAML issuer/signature/audience/recipient/InResponseTo trước khi tạo local Authentication.
- [ ] Cookie SP có `Secure`, `HttpOnly`, Domain/Path phù hợp và SameSite đã kiểm thử với callback OIDC/SAML/SSO.
- [ ] Login có session fixation protection; logout local invalidates server session và không chỉ xóa cookie bằng JavaScript.
- [ ] Logout POST có CSRF token; không biến GET hoặc open redirect thành logout endpoint nguy hiểm.
- [ ] UX phân biệt local logout với federated logout; kiểm thử kết quả thực tế và các ca partial failure.
- [ ] Với OIDC RP-initiated logout, OP hỗ trợ `end_session_endpoint` và post-logout URI đã đăng ký; đã thử browser redirect và OP confirmation.
- [ ] Với OIDC back-channel logout, RP xác minh Logout Token đúng issuer/audience/event/replay và tìm đúng local sessions; có registry/HA phù hợp.
- [ ] Với SAML SLO, IdP có `SingleLogoutService`, SP signing credentials, request/response validation và session correlation đúng.
- [ ] Với CAS, client/server xử lý SLO notification và ánh xạ ticket/session đúng; TGT/TGC không bị nhầm với ST/local cookie.
- [ ] Có chính sách fresh authentication/MFA/step-up theo thời gian `auth_time`/`ForceAuthn`/`renew` và quyền nghiệp vụ.
- [ ] Có cơ chế thu hồi sessions khi user bị khóa, mất group quan trọng hoặc tài khoản/IdP bị xâm phạm; không chờ IdP cookie tự hết.
- [ ] Đã kiểm thử cả trường hợp local logout→silent SSO, IdP timeout→A vẫn active, multi-tab, incognito, browser restart, SAML POST SameSite, proxy HTTPS và cluster.
- [ ] Có logs/metrics về login/logout/session invalidation, không ghi bí mật hoặc PII không cần thiết.
- [ ] Tài liệu vận hành có đường đi chẩn đoán “local session chưa bị xóa” so với “local session mới vừa được tạo nhờ IdP SSO”.

**Kết luận:** Một user có thể đồng thời có **phiên ứng dụng của từng RP/SP** và **phiên SSO do IdP quản lý**. Local session quyết định các request đã đăng nhập tại ứng dụng; IdP session quyết định khả năng nhận **bằng chứng đăng nhập mới** ở một RP khi browser được chuyển đến IdP. Hủy một phiên **không tự hủy** phiên còn lại. Muốn “đăng xuất liên kết” cần giao thức/logout notifications, xử lý phiên tại mỗi RP, giới hạn rủi ro và kiểm thử tương thích browser/IdP. Muốn “xác thực mới” cần một flow reauthentication/step-up có kiểm tra chứng cứ, không chỉ đợi session hết hạn.

## 18. Tài liệu đối chiếu

1. [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html) — HttpSession, SecurityContext, session fixation, concurrency và session policy.
2. [Spring Security — Logout (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html) — LogoutFilter, local logout, CSRF và cleanup.
3. [Spring Security — OIDC Logout (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html) — local logout, `OidcClientInitiatedLogoutSuccessHandler`, RP-initiated/back-channel logout.
4. [Spring Security — SAML 2.0 Single Logout](https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html) — RP-initiated/AP-initiated SLO, signing credentials, SessionIndex và logout filters.
5. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html) — `prompt`, `max_age`, `auth_time`, ID Token, authentication context.
6. [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html) — `end_session_endpoint`, `id_token_hint`, `post_logout_redirect_uri`, trách nhiệm RP/OP.
7. [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html) — Logout Token, `sid`/`sub`, chữ ký và chống replay.
8. [OASIS SAML 2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf) — Web Browser SSO, `ForceAuthn` và Single Logout.
9. [Apereo CAS — Logout & Single Logout](https://apereo.github.io/cas/7.3.x/installation/Logout-Single-Signout.html) — phân biệt CAS SSO session với application session và thông báo SLO.
10. [Apereo CAS — CAS Protocol Specification](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html) — ST/TGT/TGC, `renew` và `/logout`.
