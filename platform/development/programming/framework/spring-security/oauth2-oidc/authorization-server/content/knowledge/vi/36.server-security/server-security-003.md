# CSRF theo từng endpoint và bảo vệ các thao tác có người dùng

> **Chương: Bảo vệ máy chủ.** Bài thuộc module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, tập trung vào thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong Spring Boot. Mục tiêu là phân loại endpoint theo nguồn credential, giữ CSRF cho thao tác browser của người dùng và chỉ miễn kiểm tra ở những endpoint có cơ chế xác thực độc lập phù hợp.

## 1. CSRF là gì và vì sao Authorization Server phải quan tâm?

Cross-Site Request Forgery (CSRF) là kiểu tấn công lợi dụng việc browser tự động gửi credential của người dùng tới một website. Nếu người dùng đang đăng nhập vào `https://login.example.vn`, browser có thể tự đính kèm session cookie khi một trang độc hại khiến browser gửi request tới domain đó.

Ví dụ người dùng đang có phiên đăng nhập tại Authorization Server. Kẻ tấn công tạo một form ẩn:

~~~html
<form action="https://login.example.vn/account/change-email" method="post">
    <input name="email" value="attacker@example.net">
</form>
<script>
    document.forms[0].submit();
</script>
~~~

Nếu endpoint chỉ dựa vào session cookie để nhận diện user và không kiểm tra CSRF token, browser có thể gửi request cùng cookie hợp lệ. Server nhìn thấy một phiên đăng nhập thật và có thể thực hiện thay đổi mà người dùng không chủ ý.

Trong Authorization Server, các thao tác có thể bị ảnh hưởng gồm:

- Thay đổi mật khẩu, email, số điện thoại, MFA hoặc thông tin tài khoản.
- Tạo, sửa, xóa client registration hoặc redirect URI.
- Chấp thuận consent, thay đổi quyền hoặc membership.
- Thu hồi session, credential hoặc authorization.
- Thao tác quản trị user và tenant.
- Login/logout qua browser nếu endpoint không có bảo vệ phù hợp.

CSRF khác với XSS. CSRF khiến browser gửi request ngoài ý muốn bằng credential tự động đính kèm; XSS cho phép script độc hại chạy trong origin tin cậy và có thể đọc hoặc sử dụng CSRF token. CSRF token không thay thế output encoding, CSP hoặc phòng chống XSS.

## 2. Xác định endpoint có nguy cơ CSRF

Câu hỏi quan trọng là: **browser có tự gửi credential để endpoint xác thực request hay không?**

| Cách xác thực | Browser tự gửi credential? | Nguy cơ CSRF |
|---|---|---|
| Session cookie | Có | Cao nếu endpoint thay đổi trạng thái |
| Cookie chứa JWT/session state | Có | Vẫn có |
| HTTP Basic được browser lưu và tự gửi | Có thể có | Có |
| Bearer token trong `Authorization` header do client chủ động gắn | Thông thường không | Thấp hơn với CSRF truyền thống |
| Client authentication tại back-channel token endpoint | Không dựa trên browser session | Thường không cần CSRF token của browser |
| HMAC/mTLS cho webhook | Không dựa trên browser session | Dùng chữ ký và replay protection riêng |
| API dùng cookie để xác thực | Có | Vẫn cần CSRF, kể cả API trả JSON |

Không thể kết luận một API an toàn chỉ vì nó trả JSON, dùng HTTPS, hoặc được gọi bằng JavaScript. Browser vẫn có thể gửi form cross-site, request với content type đơn giản, hoặc tự đính kèm cookie.

`SessionCreationPolicy.STATELESS` cũng không tự loại bỏ CSRF. Một ứng dụng stateless nhưng xác thực bằng cookie vẫn có thể bị CSRF vì browser tự gửi cookie đó.

## 3. Nguyên tắc phân loại endpoint

Trước khi cấu hình `ignoringRequestMatchers`, hãy lập danh sách endpoint và xác định nguồn credential, hành động và cơ chế bảo vệ.

| Nhóm endpoint | Ví dụ | Bảo vệ phù hợp |
|---|---|---|
| Form đăng nhập và tài khoản | `/login`, `/account/email`, `/account/mfa` | Spring Security CSRF token |
| Thao tác quản trị | `/admin/clients`, `/admin/users` | CSRF + authorization + re-authentication khi nhạy cảm |
| Form consent trong app | `/consent`, `/device/approve` | CSRF token của ứng dụng hoặc state token của protocol |
| OAuth authorization endpoint | `/oauth2/authorize` | Quy tắc CSRF của Authorization Server và consent protocol |
| Token/introspection/revocation | `/oauth2/token`, `/oauth2/introspect`, `/oauth2/revoke` | Client authentication, grant/token validation |
| PAR/device authorization | `/oauth2/par`, `/oauth2/device_authorization` | Client authentication và protocol validation |
| UserInfo | `/userinfo` | Bearer access token và scope |
| Webhook | `/integrations/provider/webhook` | Chữ ký HMAC/mTLS, timestamp và chống replay |
| Discovery/JWKS | `/.well-known/openid-configuration`, `/oauth2/jwks` | GET chỉ đọc, không thay đổi trạng thái |

Không gom toàn bộ `/api/**`, `/oauth2/**` hoặc mọi request POST vào một ngoại lệ chỉ vì một endpoint không dùng CSRF token.

## 4. Spring Security xử lý CSRF mặc định như thế nào?

Trong Servlet stack, Spring Security bật CSRF protection mặc định. `CsrfFilter` mặc định bỏ qua các HTTP method an toàn:

- `GET`
- `HEAD`
- `TRACE`
- `OPTIONS`

Các method còn lại như `POST`, `PUT`, `PATCH`, `DELETE` cần token hợp lệ nếu request không khớp một ngoại lệ được cấu hình.

CSRF token mặc định được lưu trong `HttpSession` bằng `HttpSessionCsrfTokenRepository`. Token được server tạo và so sánh với token client gửi lại trong form parameter hoặc request header.

~~~mermaid
flowchart TD
    A["HTTP request"] --> B{"GET / HEAD / TRACE / OPTIONS?"}
    B -->|Có| C["Không yêu cầu CSRF token"]
    B -->|Không| D{"Khớp matcher được miễn?"}
    D -->|Có| E["Bỏ qua CsrfFilter cho request này"]
    D -->|Không| F["Đọc token từ session và request"]
    F --> G{"Token hợp lệ?"}
    G -->|Có| H["Tiếp tục authorization và controller"]
    G -->|Không| I["403 Access Denied"]
~~~

Việc method an toàn không cần token không có nghĩa endpoint GET được phép thay đổi dữ liệu. Nếu `GET /account/delete` xóa tài khoản hoặc `GET /logout` kết thúc session, endpoint đã vi phạm semantics của HTTP và có thể bị kích hoạt qua link, image hoặc navigation.

**Quy tắc:** GET chỉ đọc dữ liệu hoặc hiển thị trang. Mọi thao tác thay đổi trạng thái phải dùng method không an toàn và có cơ chế bảo vệ tương ứng.

## 5. Cấu hình CSRF hẹp trong application SecurityFilterChain

Ví dụ dưới đây giữ CSRF cho các thao tác browser của người dùng và chỉ miễn một webhook có xác thực chữ ký độc lập.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.security.web.util.matcher.RequestMatcher;

@Bean
@Order(2)
SecurityFilterChain applicationSecurityFilterChain(HttpSecurity http)
        throws Exception {

    RequestMatcher signedPaymentWebhook = request ->
            "POST".equals(request.getMethod())
                    && "/integrations/payments/webhook"
                            .equals(request.getServletPath());

    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/login", "/assets/**").permitAll()
            .requestMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated())
        .csrf(csrf -> csrf
            .csrfTokenRepository(new HttpSessionCsrfTokenRepository())
            .ignoringRequestMatchers(signedPaymentWebhook))
        .formLogin(Customizer.withDefaults())
        .logout(Customizer.withDefaults());

    return http.build();
}
~~~

`RequestMatcher` chỉ khớp đúng `POST /integrations/payments/webhook`. Những request khác, kể cả POST tới endpoint khác trong cùng nhóm `/integrations`, vẫn phải có CSRF token nếu chúng dùng browser session.

Đoạn code này chỉ định nghĩa ngoại lệ CSRF. Controller/filter xử lý webhook vẫn phải xác minh chữ ký HMAC hoặc mTLS, timestamp, request body nguyên bản và replay/idempotency key trước khi thực hiện nghiệp vụ. Không chấp nhận webhook chỉ vì request có header `X-Signature`.

Nếu ứng dụng có context path hoặc servlet mapping riêng, hãy kiểm tra `getServletPath()` thực tế và viết test cho matcher. Một matcher sai path có thể vô tình mở rộng vùng được miễn.

### 5.1. Không tắt CSRF trên toàn application chain

Không dùng cấu hình sau chỉ để làm một API hoặc webhook hoạt động:

~~~java
http.csrf(csrf -> csrf.disable());
~~~

Cấu hình này loại bỏ bảo vệ khỏi login form, logout, account management, admin console và mọi form khác nằm trong chain đó. Nếu có endpoint không dùng browser credential, hãy tạo ngoại lệ hẹp cho endpoint đó hoặc đặt nó trong một SecurityFilterChain riêng với authentication model rõ ràng.

## 6. Phân tách filter chain theo loại ứng dụng

Một hệ thống có thể có Authorization Server protocol endpoints, browser application, Resource Server API và webhook. Có thể tách các filter chain để chính sách dễ kiểm tra.

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, server ->
                    server.oidc(Customizer.withDefaults()))
            .authorizeHttpRequests(authorize ->
                    authorize.anyRequest().authenticated());

    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain browserApplicationSecurityFilterChain(HttpSecurity http)
        throws Exception {

    http.authorizeHttpRequests(authorize -> authorize
                    .requestMatchers("/login", "/assets/**").permitAll()
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults());

    return http.build();
}
~~~

Chain thứ nhất dành cho các protocol endpoints của Spring Authorization Server. Chain thứ hai dành cho browser login và các thao tác nghiệp vụ của người dùng. Trong chain browser, CSRF vẫn được bật mặc định.

Spring Authorization Server 1.4.x/1.5.x tự cấu hình `csrf.ignoringRequestMatchers(endpointsMatcher)` trong `OAuth2AuthorizationServerConfigurer`. Điều đó có nghĩa các protocol endpoints được loại khỏi `CsrfFilter` tiêu chuẩn của Spring Security. Không nên hiểu điều này là toàn bộ hệ thống không cần CSRF; các endpoint protocol phải dùng cơ chế bảo vệ tương ứng của OAuth/OIDC, còn các form nghiệp vụ ngoài matcher vẫn phải được bảo vệ.

Không thêm `csrf.disable()` vào browser chain. Nếu thay đổi thứ tự hoặc matcher của filter chain, hãy kiểm tra request thực sự đi vào chain nào bằng integration test và security debug logs.

## 7. Bảo vệ HTML form và thao tác tài khoản

Với form HTML, gửi CSRF token trong hidden input. Thymeleaf/Spring MVC có thể cung cấp `CsrfToken` dưới request attribute `_csrf`.

~~~html
<form method="post" action="/account/email">
    <input type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}">

    <label for="email">Email mới</label>
    <input id="email" name="email" type="email" required>

    <button type="submit">Cập nhật email</button>
</form>
~~~

Với Thymeleaf, có thể dùng cú pháp `th:name` và `th:value` để render tên parameter/token. Không đặt CSRF token trong URL, query string, log hoặc analytics vì các vị trí này có thể bị lưu trong browser history, proxy logs và Referer header.

Các thao tác cần bảo vệ gồm:

- Thay đổi email/số điện thoại, mật khẩu hoặc thông tin hồ sơ.
- Bật/tắt MFA, đăng ký passkey, thay recovery codes.
- Tạo hoặc thu hồi API key, refresh token, session và trusted device.
- Thay đổi quyền, membership, role hoặc tenant.
- Tạo/sửa/xóa OAuth client, redirect URI và secret.
- Chấp thuận hoặc thu hồi consent.

CSRF token chứng minh request có token phù hợp với session; nó không thay thế authorization. Server vẫn phải kiểm tra user có quyền thực hiện hành động đó trên đúng account/client/tenant.

### 7.1. Login và logout cũng là thao tác cần bảo vệ

Spring Security bảo vệ login request để ngăn login CSRF, ví dụ attacker ép browser của nạn nhân đăng nhập vào account do attacker kiểm soát. Khi nạn nhân tiếp tục sử dụng browser, dữ liệu riêng tư có thể bị ghi vào account của attacker.

Logout cũng nên dùng POST có CSRF token. `LogoutFilter` của Spring Security mặc định xử lý logout qua POST khi CSRF được bật. Không biến logout thành GET chỉ để tạo một link dễ dùng.

## 8. CSRF token cho JavaScript và SPA

Ứng dụng JavaScript có thể gửi CSRF token trong request header thay vì form parameter. Một lựa chọn là `CookieCsrfTokenRepository`, thường dùng cookie `XSRF-TOKEN` và header `X-XSRF-TOKEN`.

~~~java
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

http.csrf(csrf -> csrf
        .csrfTokenRepository(
                CookieCsrfTokenRepository.withHttpOnlyFalse()));
~~~

`HttpOnly=false` cho phép JavaScript đọc cookie để lấy token và gắn vào header. Chỉ dùng lựa chọn này khi frontend thật sự cần đọc token; giữ session cookie xác thực ở chế độ HttpOnly.

Ví dụ request:

~~~javascript
const csrfToken = readCookie("XSRF-TOKEN");

await fetch("/account/email", {
    method: "POST",
    credentials: "same-origin",
    headers: {
        "Content-Type": "application/json",
        "X-XSRF-TOKEN": csrfToken
    },
    body: JSON.stringify({ email: "new@example.vn" })
});
~~~

Với các phiên bản Spring Security mới có hỗ trợ SPA CSRF handler, có thể dùng `csrf.spa()` để áp dụng các xử lý cần thiết cho deferred token và BREACH protection. Cần theo đúng phiên bản Spring Security của ứng dụng. Sau authentication success và logout success, CSRF token cũ có thể bị xóa; SPA phải lấy token mới trước request thay đổi trạng thái tiếp theo.

Không đọc CSRF token từ cookie rồi gửi nó như một credential xác thực. CSRF token chỉ là một phần của cơ chế kiểm tra request; session cookie vẫn phải được bảo vệ riêng.

## 9. Endpoint API và webhook: khi nào được miễn CSRF?

### 9.1. Bearer-only Resource Server API

Một request mang access token trong `Authorization: Bearer ...` header thường không bị browser tự động đính kèm như session cookie. Spring Security Resource Server cũng tự cấu hình bỏ qua CSRF cho request khớp Bearer token request matcher.

~~~java
@Bean
@Order(1)
SecurityFilterChain resourceApiSecurity(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated())
        .oauth2ResourceServer(resourceServer ->
                resourceServer.jwt(Customizer.withDefaults()));

    return http.build();
}
~~~

Đây là chain cho API xác thực bằng Bearer token trong header. Không thêm cookie-based authentication hoặc HTTP Basic vào cùng API mà không đánh giá lại CSRF. Nếu browser gửi session cookie để xác thực API, endpoint đó vẫn có nguy cơ CSRF dù response là JSON.

Spring Security `OAuth2ResourceServerConfigurer` sử dụng matcher cho request có Bearer token để bỏ qua CSRF ở loại request này. Matcher không phải ngoại lệ theo toàn bộ path `/api/**`: request không mang Bearer header vẫn phải đi qua authentication và CSRF policy của chain.

Không dùng `STATELESS` làm bằng chứng duy nhất rằng CSRF không cần thiết. Một cookie tự chứa JWT cũng là ambient credential và vẫn có thể bị browser tự gửi.

### 9.2. Webhook từ hệ thống bên ngoài

Webhook có thể được miễn CSRF khi nó không dựa trên browser session và có authentication độc lập:

- HMAC trên raw request body với secret riêng của provider.
- mTLS hoặc chữ ký bất đối xứng khi provider hỗ trợ.
- Timestamp có giới hạn thời gian và replay protection.
- Idempotency key để xử lý gửi lặp.
- Giới hạn kích thước body, rate limit và kiểm tra schema.
- So sánh chữ ký constant-time khi tự triển khai HMAC verification.

Không cho phép request webhook thay đổi nghiệp vụ chỉ vì nó tới từ IP được cho là của provider. IP allowlist có thể là lớp bổ sung, không thay thế chữ ký hoặc mTLS.

### 9.3. CORS không thay thế CSRF

CORS quyết định JavaScript từ origin nào được phép đọc response hoặc thực hiện một số loại cross-origin request. CORS không tự chặn mọi form POST hoặc navigation request mà browser có thể gửi.

Một API bật CORS vẫn có thể bị CSRF nếu nó xác thực bằng cookie. Ngược lại, API chỉ chấp nhận Bearer header và không dùng ambient credential thường có mô hình CSRF khác với browser session application.

## 10. CSRF trong các protocol endpoint của Spring Authorization Server

Không áp dụng một quy tắc CSRF duy nhất cho tất cả OAuth2/OIDC endpoints. Cần phân biệt giao thức back-channel với thao tác người dùng trên browser.

| Endpoint | Cách xác thực/bảo vệ chính | Cách đánh giá CSRF |
|---|---|---|
| `/oauth2/authorize` | Authorization request validation, user authentication và consent | GET là protocol navigation; consent POST dùng state token của SAS |
| `/oauth2/token` | Client authentication/identification theo loại client, authorization code/PKCE/refresh grant validation | Back-channel endpoint; không dựa vào browser session cookie |
| `/oauth2/par` | Client identification/authentication theo loại client và pushed request validation | Back-channel; kiểm tra client và request parameters |
| `/oauth2/device_authorization` | Client identification/authentication theo registration và device grant validation | Back-channel; không phải form thao tác user |
| `/oauth2/device_verification` | User code, authenticated resource owner và consent | User interaction; consent flow có state token của SAS |
| `/oauth2/introspect` | Client authentication và token validation | Back-channel endpoint |
| `/oauth2/revoke` | Client authentication và token validation | Back-channel endpoint |
| `/userinfo` | Bearer access token | Header token; không dựa vào cookie session |
| Discovery/JWKS | GET metadata/key set | Endpoint đọc dữ liệu |
| OIDC logout | `id_token_hint`, client và post-logout redirect validation | RP-initiated browser navigation; cần xét logout CSRF riêng |

### 10.1. Ba loại state/token không được nhầm lẫn

Trong ứng dụng Authorization Server có thể cùng lúc xuất hiện ba giá trị:

| Giá trị | Ai tạo | Mục đích |
|---|---|---|
| OAuth `state` trong authorization request | OAuth client | Ràng buộc authorization response với request của client, bảo vệ client khỏi response injection/CSRF |
| Consent `state` trong custom consent page của SAS | Spring Authorization Server | Bảo vệ consent transaction; form phải gửi lại state khi POST |
| Spring `_csrf` token | Spring Security application | Bảo vệ browser form/request dùng session cookie của ứng dụng |

OAuth client `state` không thay thế CSRF token của form quản trị. Spring `_csrf` cũng không thay thế `state` mà Spring Authorization Server yêu cầu trong consent protocol.

### 10.2. Consent page của Authorization Server

Spring Authorization Server 1.5.8 cho phép cấu hình `authorizationEndpoint(...).consentPage(...)`. Query string của custom consent page chứa `client_id`, `scope` và `state`. Tài liệu API xác định `state` là CSRF protection token của consent flow.

Form consent phải:

1. Dùng HTTP POST.
2. Gửi tới `AuthorizationServerSettings.getAuthorizationEndpoint()`.
3. Gửi lại `client_id` nhận được.
4. Gửi lại `state` nhận được.
5. Gửi các scope mà resource owner thực sự chấp thuận.

~~~html
<form method="post" th:action="${authorizationEndpoint}">
    <input type="hidden" name="client_id" th:value="${clientId}">
    <input type="hidden" name="state" th:value="${state}">

    <label th:each="scope : ${requestedScopes}">
        <input type="checkbox"
               name="scope"
               th:value="${scope.name}">
        <span th:text="${scope.description}"></span>
    </label>

    <button type="submit">Chấp thuận</button>
</form>
~~~

Trong cấu hình chuẩn, `OAuth2AuthorizationServerConfigurer` tự loại endpoint matcher của Authorization Server khỏi `CsrfFilter`. Vì vậy consent state của SAS là một phần quan trọng của protocol. Không bỏ `state`, không nhận `client_id` hoặc scope tùy ý từ browser, và không tự tạo authorization code trong controller.

RFC 6749 §10.12 yêu cầu Authorization Server bảo vệ authorization endpoint để một client độc hại không thể nhận authorization của resource owner mà người dùng không nhận biết và không consent rõ ràng. OAuth client `state` chủ yếu ràng buộc response ở phía client; nó không thay thế consent/interaction protection ở phía Authorization Server. Với client bên thứ ba hoặc scope nhạy cảm, phải có consent policy bảo đảm user awareness và explicit approval; không tự động bỏ qua consent chỉ vì request có session cookie hợp lệ.

Nếu tổ chức muốn thêm một lớp synchronizer token của ứng dụng lên consent interaction, cần thiết kế integration riêng với filter/protocol flow và kiểm thử cả hai lớp; chỉ thêm `csrf.requireCsrfProtectionMatcher(...)` không tự khôi phục request đã bị endpoint matcher loại trừ.

### 10.3. Device Authorization và Device Verification

Device Verification là một endpoint có người dùng tương tác: người dùng nhập `user_code`, xem tên client và scope, sau đó chấp thuận hoặc từ chối. Với custom device consent page, Spring Authorization Server 1.5.8 cung cấp `client_id`, `scope`, `state` và `user_code`; form phải POST về `AuthorizationServerSettings.getDeviceVerificationEndpoint()` và gửi lại các giá trị protocol yêu cầu.

Không tự động chấp thuận chỉ vì `user_code` hợp lệ. Hiển thị rõ ứng dụng/thiết bị đang yêu cầu quyền, xác minh người dùng đã đăng nhập, yêu cầu consent rõ ràng và giữ `state` của SAS. Nếu xây dựng trang nhập user code hoặc interaction route riêng, hãy dùng session-bound one-time interaction token và ràng buộc nó với user code/phiên hiện tại; không dùng hidden `tenant_id` hoặc `user_code` đơn lẻ như bằng chứng CSRF.

### 10.4. OIDC logout và logout CSRF

Logout tại browser application nên là POST được bảo vệ bởi Spring CSRF. RP-Initiated Logout của OIDC là protocol navigation tới end-session endpoint; server cần xác minh `id_token_hint`, client registration và `post_logout_redirect_uri` theo protocol.

Một request logout bị kích hoạt ngoài ý muốn thường gây session termination/availability impact hơn là thay đổi dữ liệu, nhưng vẫn cần được đưa vào threat model. Với thao tác logout nhạy cảm hoặc local account security, có thể hiển thị confirmation page và yêu cầu user action rõ ràng. `state` trong RP-Initiated Logout dùng để tương quan response sau logout; không nhầm nó với Spring `_csrf`.

## 11. Bảo vệ thao tác người dùng có rủi ro cao

CSRF token chỉ chứng minh request có token phù hợp với session. Nó không xác nhận user có quyền, không chứng minh ý định đối với mọi thao tác và không thay thế xác thực lại.

| Thao tác | Kiểm soát cần kết hợp |
|---|---|
| Đổi email/số điện thoại | CSRF + xác minh địa chỉ mới + thông báo bảo mật |
| Đổi mật khẩu | CSRF + xác minh mật khẩu hiện tại hoặc step-up authentication |
| Bật/tắt MFA, thêm passkey | CSRF + re-authentication/MFA hiện tại + confirmation |
| Tạo client hoặc đổi redirect URI | CSRF + quyền admin + audit + approval theo policy |
| Cấp role/admin hoặc đổi tenant membership | CSRF + authorization chặt + step-up + audit |
| Thu hồi tất cả session/token | CSRF + xác nhận tác động + audit |
| Thay signing key hoặc client secret | CSRF + quyền đặc biệt + re-authentication + quy trình quản trị |

Các endpoint có thể được tổ chức theo resource và method:

~~~text
POST   /account/email
POST   /account/password
POST   /account/mfa/enroll
DELETE /account/mfa/{credentialId}
POST   /admin/clients
PATCH  /admin/clients/{clientId}
DELETE /admin/clients/{clientId}
POST   /admin/users/{userId}/roles
POST   /admin/sessions/revoke
~~~

Mọi thao tác thay đổi đều đi qua authorization policy và CSRF validation nếu dùng browser session. Không dùng GET để xóa credential, chấp thuận consent, thay quyền hoặc revoke session.

## 12. Defense in depth: SameSite, Origin và Fetch Metadata

CSRF token là lớp bảo vệ chính cho stateful browser application. Có thể bổ sung các lớp sau:

### 12.1. SameSite cookie

`SameSite=Lax` hoặc `Strict` giúp hạn chế việc browser gửi cookie trong cross-site request. Tuy nhiên:

- `Lax` vẫn cho phép cookie trong một số top-level safe navigation.
- Subdomain cùng registrable domain có thể được coi là same-site.
- GET thay đổi trạng thái vẫn có thể bị kích hoạt.
- Hành vi khác nhau giữa browser và embedded user-agent.

Do đó SameSite là defense in depth, không thay thế synchronizer token trong ứng dụng session-based.

### 12.2. Kiểm tra Origin/Referer

Với request thay đổi trạng thái, server có thể kiểm tra `Origin` và fallback `Referer` so với public origin đã cấu hình. Nếu ứng dụng đứng sau reverse proxy, chỉ tin forwarded headers từ proxy đã xác thực; proxy phải xóa header client gửi và tạo header chuẩn.

Không cho phép `Origin: null`, không dùng kiểm tra substring kiểu `endsWith("example.vn")`, và không tự động chấp nhận request thiếu cả Origin lẫn Referer nếu không có CSRF token hợp lệ hoặc fallback được thiết kế rõ.

### 12.3. Fetch Metadata

Header `Sec-Fetch-Site` có thể giúp phát hiện request cross-site. Với thao tác thay đổi trạng thái, có thể từ chối `cross-site` và áp dụng fallback cho browser không gửi Fetch Metadata. Không xem `same-site` là an toàn nếu hệ thống có subdomain hoặc tenant content không hoàn toàn tin cậy.

### 12.4. Các biện pháp không thay thế CSRF token

- CORS không chặn mọi form/navigation request.
- HTTPS không ngăn browser gửi cookie tới request do attacker khởi tạo.
- CAPTCHA không ràng buộc request với session.
- Idempotency key chống xử lý trùng, không chứng minh request có nguồn gốc hợp lệ.
- Re-authentication/MFA tăng assurance nhưng không thay thế kiểm tra CSRF của form.

## 13. Ma trận kiểm thử CSRF theo endpoint

| # | Tình huống | Kết quả mong đợi |
|---|---|---|
| 1 | POST `/account/email` có session nhưng thiếu CSRF token | 403 |
| 2 | POST `/account/email` có token hợp lệ | Được chuyển sang authorization/business validation |
| 3 | POST `/account/email` có token sai | 403 |
| 4 | PUT/PATCH/DELETE thao tác tài khoản thiếu token | 403 |
| 5 | GET `/account/email` bị dùng để thay đổi dữ liệu | Không có state change; thiết kế endpoint bị coi là lỗi |
| 6 | Login form POST thiếu token | Bị từ chối |
| 7 | Logout POST thiếu token | Bị từ chối |
| 8 | Logout POST có token hợp lệ | Kết thúc local session |
| 9 | Admin thay redirect URI thiếu token | 403 |
| 10 | Admin có token nhưng thiếu role | 403 từ authorization layer |
| 11 | Webhook đúng path, sai HTTP method | Không được miễn CSRF |
| 12 | Webhook đúng path/method nhưng chữ ký sai | Bị từ chối bởi signature validation |
| 13 | Webhook chữ ký hợp lệ nhưng timestamp quá cũ | Bị từ chối bởi replay/time validation |
| 14 | POST `/integrations/other` | Vẫn cần CSRF token |
| 15 | Bearer-only API có Authorization header hợp lệ | Được xác thực theo JWT/resource policy |
| 16 | API dùng cookie session thay Bearer token | CSRF vẫn phải được áp dụng |
| 17 | Request JSON cross-site dùng `text/plain` | Không được coi là an toàn chỉ vì JSON API |
| 18 | Consent POST thiếu SAS state | Authorization Server từ chối |
| 19 | Consent POST sửa client_id | Không cấp consent sai client |
| 20 | Consent POST gửi scope ngoài requested scopes | Không cấp scope ngoài request/policy |
| 21 | Consent POST tới endpoint khác issuer/tenant | Không hoàn tất authorization transaction |
| 22 | Consent state đã dùng hoặc hết hiệu lực | Từ chối transaction |
| 23 | Device verification user_code không hợp lệ | Không xác thực thiết bị |
| 24 | Device consent thiếu state | Không chấp thuận device authorization |
| 25 | Device consent chỉ dựa vào user_code, không có user approval | Không được tự động chấp thuận |
| 26 | RP-Initiated Logout có id_token_hint không hợp lệ | Từ chối hoặc xử lý theo OIDC error policy |
| 27 | post_logout_redirect_uri không đăng ký | Không redirect tới URI đó |
| 28 | Browser gửi Origin khác origin đã cấu hình | Request nhạy cảm bị từ chối |
| 29 | Request có Origin: null | Không tự động chấp nhận |
| 30 | Request thiếu Origin/Referer và CSRF token | Bị từ chối |
| 31 | Request có Sec-Fetch-Site: cross-site tới endpoint đổi dữ liệu | Bị chặn theo policy |
| 32 | Request cùng origin có CSRF token hợp lệ | Được tiếp tục |
| 33 | Session hết hạn nhưng form giữ token cũ | CSRF validation thất bại; UI yêu cầu tải lại/lấy token mới |
| 34 | Login thành công rồi SPA gửi token CSRF cũ | Client phải lấy token mới |
| 35 | Logout thành công rồi SPA gửi token CSRF cũ | Client phải lấy token mới |
| 36 | Hai tab dùng session token hợp lệ | Cả hai flow hoạt động theo token/session policy |
| 37 | API chain stateless nhận request không có Bearer header | Không được coi là authenticated |
| 38 | Request từ sibling subdomain cùng site | Vẫn phải tuân thủ token/origin policy |
| 39 | CSRF matcher bỏ qua `/integrations/**` | Test phát hiện phạm vi miễn quá rộng |
| 40 | CSRF bị disable toàn application chain | Security configuration review phải thất bại |

### 13.1. Ví dụ test với MockMvc

Spring Security Test cung cấp request post-processor `csrf()` để kiểm tra hành vi của `CsrfFilter`.

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void accountMutationRequiresCsrfToken() throws Exception {
    mockMvc.perform(post("/account/email")
            .with(user("alice"))
            .param("email", "new@example.vn"))
        .andExpect(status().isForbidden());
}

@Test
void accountMutationAcceptsValidCsrfToken() throws Exception {
    mockMvc.perform(post("/account/email")
            .with(user("alice"))
            .with(csrf())
            .param("email", "new@example.vn"))
        .andExpect(status().is3xxRedirection());
}
~~~

Test thứ hai giả định user có quyền và controller redirect sau khi thành công. Nếu business validation hoặc authorization policy khác, điều chỉnh expected response nhưng vẫn phải chứng minh request có token được vượt qua CSRF layer.

Có thể dùng `csrf().useInvalidToken()` để kiểm tra token sai và `csrf().asHeader()` để kiểm tra header-based token. Với webhook và Spring Authorization Server protocol endpoints, cần integration test xác minh chữ ký/client authentication/protocol state thực tế; `csrf()` của MockMvc không thay thế các cơ chế đó.

## 14. Troubleshooting và checklist production

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Form POST trả 403 | Thiếu _csrf hoặc token không khớp session | Render hidden input và kiểm tra session |
| SPA POST trả 403 sau login | CSRF token cũ bị xóa sau authentication | Lấy token mới sau login |
| Webhook trả 403 từ CsrfFilter | Matcher sai path/method hoặc request vào chain khác | Kiểm tra servletPath, chain order và matcher |
| Webhook được xử lý dù chữ ký sai | Chỉ miễn CSRF nhưng quên signature validation | Xác minh HMAC/mTLS và replay protection |
| API bearer request bị 403 CSRF | Request không match bearer matcher hoặc dùng cookie auth | Kiểm tra Authorization header và authentication model |
| API cookie session bị CSRF | Nhầm JSON API với bearer-only API | Bật CSRF cho cookie-authenticated requests |
| Consent page trả 403 | Thiếu hoặc làm mất SAS state | Giữ nguyên client_id/state/scopes và POST đúng endpoint |
| Device consent bị từ chối | Thiếu user_code/state hoặc sai verification flow | Kiểm tra form contract của SAS |
| Đổi csrf.disable() nhưng vẫn 403 ở SAS | Configurer thêm endpoint matcher vào CSRF ignore trong lifecycle cấu hình | Kiểm tra đúng filter chain và phiên bản SAS |
| GET làm thay đổi trạng thái | Endpoint vi phạm safe method semantics | Chuyển thao tác sang POST/PUT/PATCH/DELETE |
| Origin check sai sau reverse proxy | Target origin lấy từ forwarded header không tin cậy | Cấu hình trusted proxy và canonical origin |

### 14.1. Checklist production

- [ ] Phân loại endpoint theo nguồn credential và loại tương tác.
- [ ] CSRF được bật cho browser application và user-facing forms.
- [ ] Không dùng GET cho thao tác thay đổi trạng thái.
- [ ] Không tắt CSRF toàn cục để xử lý một endpoint.
- [ ] Mọi ngoại lệ ignoringRequestMatchers đều có method/path cụ thể và authentication độc lập.
- [ ] Webhook xác minh HMAC/mTLS, timestamp và replay protection.
- [ ] Bearer-only API không chấp nhận cookie auth ngoài thiết kế.
- [ ] API dùng cookie/session vẫn có CSRF protection.
- [ ] Login, logout, account, admin và consent forms được kiểm tra.
- [ ] Consent form của SAS giữ client_id, state và subset scopes được chấp thuận.
- [ ] Device verification yêu cầu user approval rõ ràng và giữ protocol state.
- [ ] RP-Initiated Logout xác minh ID Token hint và post-logout redirect URI.
- [ ] SameSite, Origin/Referer và Fetch Metadata chỉ là defense in depth.
- [ ] Forwarded headers chỉ được tin từ proxy đã xác thực.
- [ ] CSRF token không xuất hiện trong URL, log hoặc analytics.
- [ ] SPA refresh token CSRF sau authentication/logout theo framework behavior.
- [ ] High-risk operations có authorization, re-authentication/MFA và audit.
- [ ] Có negative tests cho mọi endpoint được miễn CSRF.
- [ ] Review filter chain order và matcher sau mỗi lần nâng cấp Spring Security/SAS.

**Câu hỏi tự đánh giá**

1. Vì sao SessionCreationPolicy.STATELESS không đủ để kết luận API không cần CSRF?
2. Khác nhau giữa synchronizer token, OAuth client state và consent state của SAS là gì?
3. Vì sao login form cũng cần CSRF protection?
4. Vì sao logout nên dùng POST thay vì GET?
5. Khi nào có thể miễn CSRF cho webhook?
6. Vì sao JSON API vẫn có thể bị CSRF?
7. ignoringRequestMatchers nên được thiết kế theo path và method như thế nào?
8. Vì sao không nên miễn CSRF cho toàn bộ /api/**?
9. Spring Authorization Server 1.5.8 custom consent page nhận những parameter nào?
10. Device verification consent page cần giữ những giá trị protocol nào?
11. Vì sao CORS không thay thế CSRF token?
12. SameSite có những giới hạn nào với subdomain và top-level navigation?
13. Khi chạy sau reverse proxy, Origin validation cần cấu hình gì?
14. Vì sao CSRF token không thay thế authorization hoặc re-authentication?
15. Cần kiểm thử những negative cases nào trước khi miễn CSRF một endpoint?

## Tài liệu tham khảo

- [Spring Security — Cross Site Request Forgery (CSRF)](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): mặc định method matcher, token repository, HTML form, SPA và endpoint exclusions.
- [Spring Security — CSRF Considerations](https://docs.spring.io/spring-security/reference/features/exploits/csrf.html): khi nào cần CSRF, stateless cookie authentication và các giới hạn của CORS/JSON.
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): authorization endpoint, consent form, state và protocol endpoint extension points.
- [Spring Authorization Server 1.5.8 — OAuth2AuthorizationEndpointConfigurer API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2AuthorizationEndpointConfigurer.html): custom consent page và form POST contract.
- [Spring Authorization Server 1.5.8 — OAuth2DeviceVerificationEndpointConfigurer API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2DeviceVerificationEndpointConfigurer.html): user_code, consent state và device verification form contract.
- [Spring Authorization Server 1.5.8 — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): protocol endpoints, endpoint matcher và cấu hình Authorization Server.
- [Spring Authorization Server 1.5.8 — OAuth2AuthorizationServerConfigurer source](https://github.com/spring-projects/spring-authorization-server/blob/1.5.8/oauth2-authorization-server/src/main/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2AuthorizationServerConfigurer.java): lifecycle cấu hình endpoint matcher và CSRF exclusions của protocol chain.
- [RFC 6749 — The OAuth 2.0 Authorization Framework, Section 10.12](https://www.rfc-editor.org/rfc/rfc6749.html#section-10.12): CSRF threats và yêu cầu bảo vệ authorization endpoint.
- [OWASP Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): synchronizer token, SameSite, Origin/Referer và Fetch Metadata.
