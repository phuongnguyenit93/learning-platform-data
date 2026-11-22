# Kiểm soát trải nghiệm đăng nhập lại và bảo vệ dữ liệu trên trang đăng nhập

> **Chương: Đăng nhập người dùng.** Bài thuộc module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, hướng dẫn thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot. Bài tập trung vào **khi nào yêu cầu người dùng đăng nhập lại**, **cách quay về đúng giao dịch OIDC** sau xác thực và **cách bảo vệ thông tin người dùng trên trang đăng nhập**.

## 1. Vì sao trải nghiệm đăng nhập lại thuộc về Authorization Server?

Một ứng dụng đã đăng nhập qua OpenID Connect (OIDC) có thể có **hai phiên riêng**: phiên của ứng dụng khách (Relying Party, RP) và phiên đăng nhập tại Authorization Server/OpenID Provider (OP). Người dùng đã có phiên OP thì lần vào ứng dụng khác có thể được xác thực theo phiên có sẵn (SSO). Nhưng ở các thao tác như đổi mật khẩu, truy cập hồ sơ nhạy cảm hoặc xác nhận thanh toán, RP có thể cần một **lần xác thực mới** thay vì chỉ nhận lại trạng thái phiên cũ.

Ví dụ xuyên suốt:

- **OP/Authorization Server:** `https://login.example.vn`, issuer `https://login.example.vn`.
- **Ứng dụng khách:** `https://portal.example.vn`, `client_id=portal-web`, callback `https://portal.example.vn/login/oauth2/code/portal`.
- **Trang đăng nhập của OP:** `https://login.example.vn/login`.
- **Thao tác nhạy cảm:** người dùng đang có phiên RP muốn xem thông tin tài khoản có mức bảo vệ cao; RP yêu cầu OP xác thực gần đây bằng `max_age` hoặc `prompt=login`.

Có ba câu hỏi khác nhau:

| Câu hỏi | Thành phần chịu trách nhiệm chính |
|---|---|
| Người dùng có **phiên OP** hợp lệ không? | Spring Security trên Authorization Server: `SecurityContext`, session và các cơ chế authentication |
| Người dùng đã **chủ động xác thực** gần đây chưa? | Chính sách tái xác thực của OP: thời điểm đăng nhập thực tế, `prompt`, `max_age`, MFA/step-up |
| Client có thể tin người dùng được xác thực lúc nào? | RP kiểm tra ID Token có chữ ký hợp lệ, `iss`, `aud`, `nonce`, `auth_time` và chính sách phiên |

**Không đánh đồng** việc session còn hạn, cookie còn tồn tại, access token còn hiệu lực hoặc `iat` của ID Token mới với việc **người dùng vừa chủ động đăng nhập**. Nếu OP cấp ID Token mới từ phiên SSO cũ, `iat` có thể mới trong khi `auth_time` vẫn là thời điểm xác thực từ nhiều giờ trước.

## 2. Các tham số OIDC điều khiển đăng nhập lại

OpenID Connect Core 1.0 định nghĩa các tham số trong authorization request để RP yêu cầu một cách xử lý xác thực cụ thể. Chúng đến qua `/oauth2/authorize`, **không phải** query parameter tự do của `/login`.

| Tham số | Ví dụ | Ý nghĩa theo OIDC | Lưu ý khi triển khai |
|---|---|---|---|
| `prompt=login` | `prompt=login` | OP **SHOULD** yêu cầu người dùng xác thực lại; nếu không thể xác thực lại, phải trả lỗi, thường là `login_required` | Cần luồng fresh authentication thực, không chỉ render lại form rồi bỏ qua |
| `max_age` | `max_age=300` | Số giây tối đa kể từ lần **active authentication**; nếu vượt mức, OP **MUST** cố gắng xác thực lại | Khi dùng `max_age`, **ID Token MUST chứa `auth_time`** |
| `max_age=0` | `max_age=0` | Theo OIDC, tương đương yêu cầu `prompt=login` | Dùng khi muốn bắt buộc xác thực mới tại giao dịch này |
| `prompt=none` | `prompt=none` | OP **MUST NOT** hiện UI đăng nhập/consent | Nếu cần tương tác, trả lỗi OIDC như `login_required` hoặc `consent_required` theo tình huống |
| `prompt=consent` | `prompt=consent` | Yêu cầu xem xét lại sự đồng ý cấp quyền | **Consent** không đồng nghĩa người dùng đã xác thực lại |
| `prompt=select_account` | `prompt=select_account` | Yêu cầu chọn tài khoản khi OP có thể có nhiều phiên/tài khoản | Chọn tài khoản không tự chứng minh đủ mức xác thực |
| `login_hint` | `login_hint=alice%40example.vn` | Gợi ý định danh để hiển thị/điền trước | Là **dữ liệu không đáng tin cậy**, không được mặc định đã chứng minh danh tính |
| `ui_locales` | `ui_locales=vi%20en` | Gợi ý ngôn ngữ ưu tiên cho giao diện | Kiểm tra và dùng danh sách locale hỗ trợ; không đưa chuỗi thẳng vào HTML |
| `acr_values` | `acr_values=urn%3Aexample%3Aloa%3A2` | Yêu cầu mức/ngữ cảnh xác thực mong muốn | Phải có chính sách thực thi tương ứng; không chỉ chép giá trị vào ID Token |

Danh sách `prompt` có thể phân cách bằng dấu cách, ví dụ `prompt=login consent`. **`none` không được xuất hiện cùng giá trị prompt khác**. RP cần kiểm tra lỗi OIDC hợp lệ; OP cần kiểm tra request và redirect URI đã đăng ký **trước** khi phản hồi lỗi qua trình duyệt.

### 2.1. Sự khác nhau giữa `auth_time`, `iat`, thời hạn session và token

Một ID Token minh họa:

~~~json
{
  "iss": "https://login.example.vn",
  "sub": "user-123",
  "aud": "portal-web",
  "iat": 1794825600,
  "exp": 1794825900,
  "auth_time": 1794796800,
  "nonce": "NONCE_FROM_AUTHORIZATION_REQUEST"
}
~~~

Đây chỉ là **payload minh họa**, không phải JWT đã ký hợp lệ. `iat` cho biết ID Token được tạo lúc nào, `exp` cho biết hết hiệu lực khi nào, `auth_time` cho biết người dùng **chủ động xác thực** lúc nào. Một ID Token vừa phát hành không tự chứng minh thời điểm active authentication cũng vừa xảy ra.

Khi RP gửi `max_age=300`, OP phải dựa trên **thời điểm xác thực thật** để quyết định có cần tương tác lại. Sau đó RP cũng có thể đối chiếu `auth_time` của ID Token với chính sách đã yêu cầu, bên cạnh kiểm tra chữ ký, `iss`, `aud`, `exp` và `nonce` khi áp dụng. Không gán `auth_time = Instant.now()` chỉ vì token vừa được cấp từ phiên SSO cũ.

### 2.2. Phương thức đăng nhập lại cần đúng mức bảo đảm

Yêu cầu “đăng nhập lại” có thể được thực hiện bằng mật khẩu, passkey/WebAuthn, MFA hay một cơ chế phù hợp chính sách. Với giao dịch rủi ro cao, chỉ hiện lại trang đăng nhập hoặc kiểm tra cookie phiên cũ là không đủ; OP cần thực sự thực hiện authentication mới đạt mức bảo đảm yêu cầu. Nếu `acr_values`/step-up được triển khai, phải đánh giá phương thức đã dùng (`amr`) và ngữ cảnh xác thực (`acr`) một cách có căn cứ.

**Lưu ý hỗ trợ thư viện:** OIDC Core quy định yêu cầu giao thức; cấu hình mặc định `formLogin()` và `server.oidc(...)` chưa phải lời cam kết mọi biến thể `prompt`, `max_age`, `auth_time`, MFA hay account selection đều được xử lý theo chính sách sản phẩm. Phải **kiểm thử từng tham số trên phiên bản Spring Security/Spring Authorization Server thực tế** và thêm phần xử lý có kiểm soát nếu thiếu.

## 3. Luồng SSO, tái xác thực và quay lại yêu cầu ban đầu

~~~mermaid
sequenceDiagram
    autonumber
    participant Browser as Trình duyệt
    participant RP as OIDC Client (portal-web)
    participant OP as Authorization Server (login.example.vn)
    participant Login as Trang đăng nhập / Authentication

    Browser->>RP: Yêu cầu thao tác nhạy cảm
    RP-->>Browser: Redirect /oauth2/authorize<br/>scope=openid, state, nonce, PKCE, max_age
    Browser->>OP: Authorization request
    OP->>OP: Validate client_id, redirect_uri, request
    OP->>OP: Đọc phiên OP, thời điểm active auth, prompt/max_age
    alt Phiên và auth_time đáp ứng policy
        OP->>OP: Tiếp tục đánh giá consent và cấp code
    else Cần xác thực mới, được phép tương tác
        OP-->>Browser: Chuyển tới GET /login (giữ request trên server)
        Browser->>Login: Hiện form qua HTTPS + CSRF
        Browser->>Login: POST /login, credentials + CSRF token
        Login->>OP: Xác thực thật và cập nhật auth_time
        OP->>OP: Khôi phục giao dịch authorization đã lưu
    else prompt=none và cần tương tác
        OP-->>Browser: OIDC error trên redirect_uri hợp lệ
    end
    OP-->>Browser: Redirect callback?code=...&state=...
    Browser->>RP: Nhận authorization code, state
    RP->>RP: Kiểm tra state và đổi code qua token endpoint bằng PKCE
    OP-->>RP: Token response có ID Token
    RP->>RP: Xác minh chữ ký, iss, aud, exp, nonce, auth_time
    RP-->>Browser: Cho phép thao tác nếu assurance đạt yêu cầu
~~~

Đối với request có `prompt=none`, OP **không** được hiển thị form. Nếu chưa có phiên hoặc cần consent/reauth thì trả lỗi thông qua authorization response đến **redirect URI đã xác thực**; không gửi lỗi hay authorization code đến URI bất kỳ.

### 3.1. Giữ lại giao dịch OAuth2/OIDC một cách an toàn

Luồng điển hình trên Spring Security:

1. RP gửi authorization request tới **`/oauth2/authorize`** với `client_id`, `redirect_uri`, `scope=openid`, `state`, `nonce`, PKCE và yêu cầu tái xác thực nếu có.
2. Authorization Server kiểm tra client/redirect URI, sau đó nếu người dùng chưa được xác thực sẽ chuyển sang **`/login`**, sử dụng cơ chế session/request cache để quay về request gốc sau đăng nhập.
3. Form POST `/login` được xử lý bởi Spring Security; sau thành công, request gốc được khôi phục từ nơi **server kiểm soát**, không dựa vào một `returnUrl` tùy ý người dùng gửi.
4. OP đánh giá lại phiên, điều kiện prompt/max_age/consent trước khi hoàn tất cấp authorization code.
5. RP kiểm tra `state`, đổi code với PKCE, xác minh ID Token và quyết định tiếp tục giao dịch nhạy cảm.

**Tránh open redirect:** Không dùng `?next=https://arbitrary-domain.test`, hidden form field `redirect` hoặc `Referer` chưa xác thực để làm URL sau login. Nếu trang login có chức năng quay về, chỉ dùng saved request thuộc server và kiểm tra đích cho phép. Cần bảo vệ request cache khỏi trộn lẫn giữa nhiều tab/phiên; OAuth2 state/nonce và đăng ký redirect URI ở giao thức vẫn phải hợp lệ.

### 3.2. Xử lý trường hợp người dùng đổi tài khoản

Giả sử trình duyệt đang dùng tài khoản A, nhưng tại trang đăng nhập lại người dùng chọn tài khoản B. OP phải cấp code/token theo danh tính **đã xác thực ở phiên hiện hành**, không giữ nguyên `sub` hoặc consent của A. RP phải nhận biết `sub` có thể thay đổi; với thao tác nhạy cảm ràng buộc tài khoản A, RP phải từ chối tiếp tục hoặc yêu cầu người dùng khởi tạo giao dịch cho B.

Cảnh giác với **login CSRF** và session confusion: kẻ tấn công không được ép trình duyệt nạn nhân đăng nhập vào phiên của tài khoản do kẻ tấn công kiểm soát. Form login phải có CSRF protection và session identity rotation phù hợp.

## 4. Khung Spring Boot/Spring Authorization Server cho trang login

Các ví dụ dưới đây tập trung vào Spring Boot 3.x, Spring Security 6.x và Spring Authorization Server 1.5.x. Các package và API có thể thay đổi ở major version khác. Cấu hình gồm **hai filter chain**: một cho endpoint giao thức, một cho trang login và phần ứng dụng thông thường.

### 4.1. SecurityFilterChain cho Authorization Server và form login

~~~java
import java.time.Instant;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.LoginUrlAuthenticationEntryPoint;
import org.springframework.security.web.authentication.SavedRequestAwareAuthenticationSuccessHandler;
import org.springframework.security.web.header.writers.ReferrerPolicyHeaderWriter;
import org.springframework.security.web.util.matcher.MediaTypeRequestMatcher;

@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
public class LoginSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerChain(HttpSecurity http) throws Exception {
        OAuth2AuthorizationServerConfigurer authorizationServer =
                OAuth2AuthorizationServerConfigurer.authorizationServer();

        http.securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, server ->
                server.oidc(Customizer.withDefaults()))
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated())
            .exceptionHandling(errors ->
                errors.defaultAuthenticationEntryPointFor(
                    new LoginUrlAuthenticationEntryPoint("/login"),
                    new MediaTypeRequestMatcher(MediaType.TEXT_HTML)));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationChain(HttpSecurity http) throws Exception {
        SavedRequestAwareAuthenticationSuccessHandler savedRequestHandler =
                new SavedRequestAwareAuthenticationSuccessHandler();

        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/login", "/assets/login/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form
                .loginPage("/login")
                .successHandler((request, response, authentication) -> {
                    // Chỉ ghi thời điểm xác thực form thành công thật sự.
                    request.getSession().setAttribute(
                            "LAST_ACTIVE_AUTH_AT", Instant.now().getEpochSecond());
                    savedRequestHandler.onAuthenticationSuccess(
                            request, response, authentication);
                })
                .permitAll())
            .sessionManagement(session ->
                session.sessionFixation(fixation -> fixation.changeSessionId()))
            .headers(headers -> headers
                .cacheControl(Customizer.withDefaults())
                .referrerPolicy(referrer -> referrer.policy(
                    ReferrerPolicyHeaderWriter.ReferrerPolicy.NO_REFERRER))
                .contentSecurityPolicy(csp -> csp.policyDirectives(
                    "default-src 'none'; script-src 'self'; style-src 'self'; " +
                    "img-src 'self'; form-action 'self'; base-uri 'none'; " +
                    "frame-ancestors 'none'"))
                .frameOptions(frame -> frame.deny()));

        return http.build();
    }
}
~~~

Spring Security mặc định đã có cơ chế bảo vệ session fixation ở các cấu hình thông thường; đoạn trên thể hiện chủ đích thay session ID sau khi xác thực thành công. `SavedRequestAwareAuthenticationSuccessHandler` giữ hành vi quay về request gốc sau khi form login thành công.

**Quan trọng về `LAST_ACTIVE_AUTH_AT`:** Đây chỉ là ví dụ ghi dấu thời điểm **đăng nhập form** trong HTTP session. Nó **không tự động** làm Spring Authorization Server xử lý `max_age`/`prompt=login`, lưu thời điểm trong `OAuth2Authorization` hoặc xuất claim `auth_time` vào ID Token. Khi triển khai OIDC hoàn chỉnh, cần truyền một **bản ghi xác thực đáng tin** xuyên suốt authorization transaction, token issuance và customizer, tương thích nếu token exchange diễn ra qua back-channel không có cookie browser.

Ví dụ cũng chưa cung cấp `RegisteredClientRepository`, `UserDetailsService`/authentication provider, `JWKSource`, `JwtDecoder`, `AuthorizationServerSettings` và persistence/consent. Phải cấu hình đầy đủ những thành phần này để hệ thống vận hành thực tế. Nếu bật UserInfo, xem xét thêm Bearer resource server support theo phiên bản và yêu cầu của endpoint.

### 4.2. Cấu hình session cookie trong production

~~~yaml
server:
  servlet:
    session:
      timeout: 20m
      cookie:
        http-only: true
        secure: true
        same-site: lax
~~~

- `http-only: true` hạn chế JavaScript đọc session cookie, `secure: true` chỉ gửi cookie qua HTTPS.
- `same-site: lax` thường phù hợp điều hướng OIDC top-level GET của Authorization Code Flow, nhưng **phải kiểm thử** trên domain, browser, cách callback/response mode và cơ chế SSO thực tế. Một số luồng cross-site POST hoặc iframe có yêu cầu khác; không chuyển sang `SameSite=None` khi chưa có threat model và `Secure`.
- Session timeout giúp giảm thời gian phiên OP tồn tại; nó **không thay thế `max_age`** và không mặc định thu hồi JWT access token đã phát.
- Khi chạy sau reverse proxy/load balancer, kiểm tra TLS termination, trusted forwarded headers, domain/path của cookie; không tin `X-Forwarded-*` header từ internet.
- Khi triển khai multi-instance, cần session store/chính sách stickiness phù hợp. Phải nhất quán giữa session, record của lần active authentication và các đối tượng OAuth2 authorization.

**Không bật `SessionCreationPolicy.STATELESS` cho luồng form login + authorization redirect truyền thống** nếu chưa thiết kế toàn bộ cơ chế trạng thái tương đương. Stateless một cách tùy tiện sẽ làm mất saved request, session đăng nhập hoặc CSRF token.

## 5. Làm trang login riêng, không để lộ dữ liệu nhạy cảm

Định nghĩa controller GET `/login` nếu dùng `.loginPage("/login")`:

~~~java
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
class LoginPageController {
    @GetMapping("/login")
    String loginPage() {
        return "login"; // src/main/resources/templates/login.html
    }
}
~~~

View mẫu Thymeleaf rút gọn:

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Đăng nhập an toàn</title>
  <link rel="stylesheet" th:href="@{/assets/login/login.css}">
</head>
<body>
<main>
  <h1>Đăng nhập</h1>
  <p th:if="${param.error}" role="alert">
    Không thể đăng nhập với thông tin đã cung cấp.
  </p>
  <form th:action="@{/login}" method="post" autocomplete="on">
    <label for="username">Tên tài khoản</label>
    <input id="username" name="username" type="text"
           autocomplete="username" required>

    <label for="password">Mật khẩu</label>
    <input id="password" name="password" type="password"
           autocomplete="current-password" required>

    <input type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}">
    <button type="submit">Tiếp tục</button>
  </form>
</main>
</body>
</html>
~~~

**Cách đoạn form hoạt động:**

- `GET /login` chỉ hiển thị form qua HTTPS; `POST /login` được `UsernamePasswordAuthenticationFilter` xử lý vì cấu hình `formLogin` mặc định dùng cặp tên `username`/`password`.
- CSRF hidden input gắn token với phiên. Với tích hợp Thymeleaf/Spring Security thông thường, Spring có thể tự chèn CSRF input thông qua `RequestDataValueProcessor`; đoạn minh họa đặt input **tường minh**, cần tránh chèn trùng nếu template engine đã tự xử lý. Kiểm tra HTML render thực tế chỉ gửi **một** token hợp lệ.
- Không có `value` cho trường password; không ghi mật khẩu vào HTML, hidden field, URL, JavaScript, session attribute tùy tiện, thông báo lỗi hay log.
- `autocomplete="username"` và `autocomplete="current-password"` tương thích password manager; **không** buộc tắt autocomplete như một biện pháp bảo mật giả tạo.
- CSS và asset được tải từ cùng origin; không nhúng tài nguyên bên thứ ba trên trang có credential.

Trong dự án production, nên có cơ chế MFA hoặc passkey/WebAuthn tùy mức bảo đảm. Nếu dùng OTP, recovery code hay WebAuthn challenge, kiểm soát TTL, số lần thử và session binding; không hiển thị hay ghi lại toàn bộ giá trị nhạy cảm trong analytics.

### 5.1. Thông báo lỗi không tạo account enumeration

Không phân biệt công khai các thông báo như “email này chưa tồn tại”, “mật khẩu sai”, “tài khoản đã bị khóa do X lần thử” nếu chúng giúp kẻ tấn công dò danh tính. Nên dùng thông điệp nhất quán:

> Không thể đăng nhập với thông tin đã cung cấp. Vui lòng kiểm tra và thử lại.

Việc hỗ trợ người dùng khôi phục tài khoản có thể diễn ra qua kênh riêng, có rate limit và thông điệp không tiết lộ trạng thái tài khoản. Log server có thể ghi **mã lỗi phân loại** (bad credentials, locked, expired) với quyền truy cập hạn chế để điều tra, nhưng hạn chế dữ liệu cá nhân và không ghi password/OTP/token.

### 5.2. `login_hint` và dữ liệu đến từ RP

RP có thể gợi ý username/email qua `login_hint`, nhưng OP chỉ dùng làm **gợi ý UX** sau khi validate, độ dài, encoding và escape HTML. Không được dùng `login_hint` để đánh dấu account đã xác thực, thay đổi `sub` hoặc bypass authentication.

Nếu hiển thị tên client, logo hoặc địa chỉ redirect trên form/consent, chỉ lấy từ **RegisteredClient đã được tin cậy** và escape khi render. Metadata client có thể do một quá trình đăng ký động gửi tới; cần validation, review nội dung và CSP trước khi dùng. Tránh hiển thị untrusted HTML qua Thymeleaf `th:utext` hoặc chèn giá trị vào script inline.

## 6. Bảo vệ response HTML và các dữ liệu đi qua trình duyệt

### 6.1. HTTP response headers quan trọng

| Header/chính sách | Giá trị hướng dẫn | Mục tiêu |
|---|---|---|
| `Cache-Control` | `no-store` (có thể kèm `no-cache, max-age=0, must-revalidate`) | Hạn chế lưu trang/response nhạy cảm vào cache browser/proxy |
| `Pragma` / `Expires` | `no-cache` / `0` cho hệ thống cũ khi cần | Tương thích cache cũ; không thay thế `Cache-Control` |
| `Content-Security-Policy` | `default-src 'none'; script-src 'self'; style-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'` | Giảm XSS, form hijack, clickjacking và tải tài nguyên trái phép |
| `Referrer-Policy` | `no-referrer` | Tránh gửi URL có query context tới site khác qua Referer |
| `X-Content-Type-Options` | `nosniff` | Hạn chế MIME sniffing |
| `Strict-Transport-Security` | Chính sách HSTS phù hợp domain HTTPS production | Ép kết nối HTTPS ở trình duyệt đã ghi nhận policy |
| Cookie `Secure`, `HttpOnly`, `SameSite` | Theo threat model, thường Secure + HttpOnly + Lax cho luồng top-level GET | Hạn chế lộ cookie và request cross-site không mong muốn |

Spring Security có các security header mặc định, nhưng cần **kiểm tra response thật** sau khi tùy biến, qua reverse proxy/CDN và trên trang login lẫn các redirect OAuth2. Ví dụ CSP ở mục 4 là một chính sách nghiêm ngặt cho trang login không có script inline. Nếu thêm JavaScript inline, đừng mở rộng bừa `'unsafe-inline'`; ưu tiên code đặt trong file first-party hoặc dùng nonce/hash CSP.

**Cache-Control không phải cơ chế xóa dữ liệu đã bị lưu** trong log, history hay screenshot. Tập trung giảm dữ liệu nhạy cảm xuất hiện từ đầu.

### 6.2. Tránh rò credentials, authorization code và định danh qua URL

- **Không gửi username/password/OTP qua GET query**; submit credential qua form POST HTTPS.
- Tránh đưa access token/ID Token/refresh token, authorization code hoặc `code_verifier` vào URL trang login, query `returnUrl`, hidden input hay client-side analytics.
- OIDC authorization request thường có `state`, `nonce`, `login_hint` và đôi khi thông tin gợi ý khác. Giới hạn log URL/query, không gửi chúng tới dịch vụ phân tích bên thứ ba trên trang login.
- Redirect sau login phải theo saved request/luồng OAuth2 hợp lệ. Không cho `next`/return URL từ client đi thẳng vào header `Location`.
- Không thiết lập `Access-Control-Allow-Origin: *` trên trang/login endpoint chỉ để “sửa CORS”. Trang login là giao diện trình duyệt có cookie session; cấu hình CORS theo use case cụ thể và không dùng CORS thay CSRF.
- Đừng thay đổi trang login thành một REST endpoint nhận và trả credential ở client browser nếu vẫn muốn dùng flow redirect chuẩn của Spring Security/Spring Authorization Server.

### 6.3. Chống tấn công trên trang login

| Rủi ro | Phòng vệ |
|---|---|
| **CSRF / login CSRF** | Giữ CSRF protection cho POST `/login`, bảo vệ session binding, xác minh token đúng phiên |
| **XSS** | Escape output, kiểm tra input, CSP và chỉ dùng asset first-party; tránh HTML do `login_hint`/client metadata kiểm soát |
| **Clickjacking** | `frame-ancestors 'none'`, `X-Frame-Options: DENY` khi không có yêu cầu nhúng chính đáng |
| **Session fixation** | Thay session ID sau xác thực thành công; cookie Secure/HttpOnly/SameSite; session timeout phù hợp |
| **Credential stuffing / brute force** | Rate limit theo IP/tài khoản/thiết bị với cơ chế chống lợi dụng khóa tài khoản; quan sát bất thường, MFA/passkey |
| **Phishing** | Domain OP thống nhất, TLS hợp lệ, UI rõ issuer và tổ chức; ưu tiên passkey/WebAuthn kháng phishing |
| **Sensitive data in logs** | Mask/không ghi body POST `/login`, cookie, Authorization, OTP, reset token và response chứa dữ liệu cá nhân |
| **Cache và bên thứ ba** | `no-store`, `Referrer-Policy: no-referrer`, chặn analytics/font/script không cần thiết |

## 7. Thiết kế chính sách tái xác thực theo ngữ cảnh

Không nên bắt người dùng nhập password liên tục cho mọi API call: điều đó tăng ma sát và có thể khiến người dùng kém cảnh giác trước các màn hình phishing. Hãy liên kết yêu cầu đăng nhập lại với **độ nhạy của thao tác, độ tin cậy của phiên và tuổi xác thực**.

| Hoạt động | Chính sách ví dụ | Trải nghiệm mong muốn |
|---|---|---|
| Xem trang thông tin công khai | Không cần authentication | Không hiện login |
| Vào dashboard sau khi OP đã có SSO session | Có thể dùng phiên OP hợp lệ | Bỏ qua form nếu policy cho phép |
| Xem thông tin tài khoản nhạy cảm | `max_age=300` và assurance phù hợp | Nếu lần active authentication quá 5 phút, yêu cầu xác thực lại |
| Thay mật khẩu/email khôi phục | Yêu cầu fresh authentication + MFA theo rủi ro | Xác minh bằng phương thức đủ mạnh; không chỉ gia hạn cookie |
| Gửi yêu cầu `prompt=login` | Yêu cầu xác thực lại theo OIDC | Không hoàn tất chỉ nhờ session SSO cũ |
| Kiểm tra SSO im lặng bằng `prompt=none` | Cấm UI tương tác | Có thể cấp code nếu mọi điều kiện đủ; nếu không trả lỗi OIDC |
| Phiên hết hạn khi đang nhập form | Hủy credential đã nhập chưa gửi; yêu cầu tải lại form/session | Thông báo đơn giản, không để lộ nội dung đang nhập |

Các thời hạn và hành vi trong bảng là **ví dụ chính sách**, không phải quy định cố định của OAuth2/OIDC. Nếu sản phẩm còn yêu cầu kiểm tra lại ở Resource Server hoặc backend của RP, RP vẫn phải tự thực thi chính sách cho thao tác nhạy cảm. Một `max_age` được gửi nhưng không có xác minh `auth_time` ở RP là kiểm tra chưa đầy đủ.

### 7.1. Mô hình quyết định tái xác thực (pseudocode)

~~~text
input:
  validatedAuthorizationRequest
  currentUserAuthentication
  lastActiveAuthTimeFromTrustedStore
  prompt, max_age, consentState, requestedAcr
  currentTime

# Validate client_id, redirect_uri, PKCE/state/scope như chính sách trước.
needsLogin = currentUserAuthentication is absent
needsFreshAuth = prompt contains "login"
if max_age is present:
    needsFreshAuth =
        needsFreshAuth
        OR lastActiveAuthTimeFromTrustedStore is absent
        OR max_age == 0
        OR (currentTime - lastActiveAuthTimeFromTrustedStore) > max_age

needsStepUp = requestedAcr is not satisfied by real authentication evidence
needsConsent = requested scopes require new consent

if prompt contains "none":
    if needsLogin OR needsFreshAuth OR needsStepUp:
        return OIDC_ERROR(login_required) to validated redirect_uri
    if needsConsent:
        return OIDC_ERROR(consent_required) to validated redirect_uri
    proceed without interactive UI
else:
    if needsLogin OR needsFreshAuth OR needsStepUp:
        start appropriate interactive authentication, preserving safe request state
    if needsConsent:
        show consent UI after identity/assurance verified
    proceed to authorization code issuance

# Bind actual authentication time to authorization transaction.
# When max_age was requested, include verified auth_time in ID Token.
~~~

Pseudocode trên mô tả **chính sách mong muốn**, **không phải code có thể dán vào filter chain để dùng ngay**. Phải xử lý thứ tự xác thực/consent, account switching, giao dịch đang chờ, multi-tab, concurrency và timeout. Nếu prompt không hợp lệ hoặc redirect URI không đáng tin, server phải trả lỗi theo quy tắc giao thức mà **không redirect đến URI chưa được xác minh**.

### 7.2. Lưu `auth_time` đúng chỗ

Để xuất `auth_time` đúng trên ID Token khi token request diễn ra qua **back-channel**, OP cần bảo toàn thông tin từ authorization request sang token issuance, ví dụ:

1. Tại thời điểm **active authentication** được hoàn tất, ghi một record đáng tin gồm user subject, thời điểm, phương thức xác thực/assurance, phiên và context giao dịch.
2. Khi xử lý `/oauth2/authorize`, kiểm tra `prompt`/`max_age` so với record; nếu không đủ thì yêu cầu login/step-up.
3. Khi tạo authorization code và đối tượng authorization được lưu, ràng buộc thời điểm xác thực thực với authorization đó; không dựa vào HTTP session của token request vì request `/oauth2/token` thường tới từ backend RP.
4. Khi xây dựng ID Token qua hook/token customizer thích hợp, lấy dữ liệu đã được ràng buộc với authorization, thêm `auth_time` (NumericDate) khi `max_age` được yêu cầu và phù hợp OIDC; không lấy `Instant.now()` tại token minting làm auth_time.
5. Kiểm thử khi user xác thực từ nhiều provider (mật khẩu, WebAuthn, federated IdP) và khi server chạy nhiều instance. Thời điểm đến từ IdP ngoài phải được kiểm tra và hiểu theo trust policy, không mặc định coi mọi federated session là xác thực mới.

Các hook cụ thể phụ thuộc phiên bản Spring Authorization Server và cơ chế user authentication tự triển khai. Không thiết kế hệ thống dựa trên một request attribute chỉ còn tồn tại ở lần GET `/login`, vì dữ liệu đó biến mất trước lần POST `/oauth2/token`.

## 8. Không biến trải nghiệm đăng nhập lại thành vòng lặp

Một lỗi phổ biến là chuyển người dùng từ `/oauth2/authorize` đến `/login`, rồi sau khi login thành công lại quay về `/oauth2/authorize` nhưng bị coi là **chưa đăng nhập** hoặc liên tục nhận `prompt=login`, tạo vòng lặp.

Nguyên nhân điển hình:

- Session cookie không được gửi qua domain/HTTPS/proxy hoặc sai `SameSite`.
- Request cache không giữ được request gốc do session/stateless/filter chain hoặc load balancer.
- Chính sách `prompt=login` chỉ đọc giá trị query mà không đánh dấu giao dịch đã thỏa fresh authentication; mỗi lần quay lại `/authorize` lại bắt đăng nhập.
- `auth_time` không được cập nhật sau authentication thật; lưu trong nơi không dùng chung giữa các pod.
- Các request từ nhiều tab ghi đè nhau trong session/request cache, khiến `state`/nonce và saved request bị trộn.
- RP tự khởi tạo lại OIDC login khi nhận `login_required`, nhưng OP luôn trả lỗi do policy hoặc phiên bị chặn.
- Login hint/selector chuyển sang account khác, còn transaction vẫn gắn `sub` cũ và không thể hoàn tất.

**Biện pháp:** ràng buộc kết quả fresh authentication vào **giao dịch authorization đang chờ**, có state/expiry rõ ràng và kiểm tra một lần sau login. Không giải quyết vòng lặp bằng cách bỏ CSRF, nới redirect URI, tắt kiểm tra `state`, bỏ `nonce` hoặc tự động coi mọi session là mới.

Các trình duyệt hạn chế third-party cookies có thể làm silent authentication trong iframe không ổn định. Thiết kế trải nghiệm dựa trên **top-level redirect** an toàn và có đường xử lý `login_required` rõ ràng từ RP.

## 9. Kiểm thử bảo mật và trải nghiệm đăng nhập lại

Cần dùng browser hoặc integration test có quản lý cookie/session, không chỉ kiểm tra HTTP GET tĩnh. Với token/JWT, sử dụng test key và tài khoản giả, không ghi credential thật ra log hoặc test report.

| Ca kiểm thử | Thiết lập và thao tác | Kết quả mong đợi |
|---|---|---|
| Chưa có phiên OP | RP khởi tạo Authorization Code + PKCE | OP chuyển tới trang login; đăng nhập thành công quay lại flow đã xác thực và trả code tới đúng redirect URI |
| Đã có phiên OP còn hiệu lực | RP không yêu cầu fresh auth | Tái sử dụng SSO khi policy cho phép; không bắt nhập password vô cớ |
| `prompt=login` | RP yêu cầu đăng nhập mới khi OP đã có session | Phải có cơ chế reauth thật theo policy; không cấp code ngay chỉ vì cookie |
| `max_age=300`, auth trước 2 phút | RP yêu cầu auth age 5 phút | Có thể sử dụng phiên nếu assurance khác hợp lệ; ID Token chứa `auth_time` |
| `max_age=300`, auth trước 10 phút | RP yêu cầu auth age 5 phút | Tái xác thực; `auth_time` trong ID Token phản ánh thời điểm auth mới |
| `max_age=0` | RP yêu cầu fresh auth | Xử lý tương đương `prompt=login`; ID Token có `auth_time` theo yêu cầu `max_age` |
| `prompt=none` khi không có session | Không thể hoàn tất im lặng | Không hiển thị login; trả lỗi OIDC thích hợp tới redirect URI đã kiểm tra |
| `prompt=none` cần consent | Client xin scope mới chưa được chấp thuận | Không hiện consent page; trả lỗi OIDC như `consent_required` |
| `prompt=login none` | Hai giá trị không tương thích | Request bị từ chối theo quy tắc OIDC |
| Đăng nhập sai password | POST `/login` với CSRF hợp lệ | Lỗi thân thiện, không phân biệt user tồn tại; không rò password/username ngoài chính sách |
| Thiếu hoặc sai CSRF | POST `/login` thiếu/sai `_csrf` | Bị từ chối; không thay session/đăng nhập |
| Session fixation | Kiểm tra session ID trước và sau login thành công | ID được thay đổi theo cấu hình; không dùng ID phiên do attacker áp trước |
| Session hết hạn | Authorization đang chờ nhưng cookie/session mất | Yêu cầu login mới an toàn; không cấp code từ trạng thái mất/không hợp lệ |
| Đổi tài khoản | Đang login A, chọn B khi reauth | Token dùng `sub` B; RP xác minh ràng buộc giao dịch/tài khoản cần thao tác |
| `login_hint` chứa HTML/script | Giá trị do RP gửi không đáng tin | Được escape/truncate/validate; không XSS hoặc ghi vào script |
| Truy cập `GET /login` qua proxy | Kiểm tra headers, HTTPS, cookie | CSP, no-store, no-referrer và cookie flags đúng |
| Open redirect | Form/login link có `next=https://evil.test` | Không chuyển hướng theo URL tùy ý; chỉ quay về saved request hợp lệ |
| Browser nhiều tab | Hai authorization requests có `state` khác nhau | Không trộn request; mỗi RP nhận đúng response giao dịch |
| Credential stuffing | Nhiều lần thử sai khác IP/account | Rate limit, detection, MFA và log/alert theo chính sách, không lộ bí mật |
| Phân tán nhiều pod | Login ở pod A, authorize ở pod B | Session/auth_time/request state hợp lệ qua kiến trúc chia sẻ hoặc routing |

### 9.1. Kiểm tra response headers

Trong môi trường test với domain thật, có thể kiểm tra **chỉ header**:

~~~bash
curl -sSI https://login.example.vn/login
~~~

Xác minh các header `Cache-Control`, `Content-Security-Policy`, `Referrer-Policy`, `X-Content-Type-Options` và HSTS phù hợp deployment. Một số endpoint login có redirect nếu session hiện hành hoặc cấu hình đặc biệt; khi đó kiểm tra từng response trong chuỗi redirect, không suy kết luận từ response cuối cùng.

Chạy trình duyệt với Developer Tools để kiểm tra POST form gửi CSRF và session cookie được cấp đúng thuộc tính. **Không** xuất toàn bộ request body/cookie vào ticket hoặc bản ghi test công khai.

### 9.2. Kiểm tra ID Token `auth_time`

RP phải giải mã **sau khi đã xác minh** JWT chữ ký, issuer, audience, thời hạn và nonce. Nếu đã yêu cầu `max_age` mà ID Token thiếu `auth_time`, RP phải xem đó là **không thỏa chính sách OIDC**. Kiểm tra `auth_time` với mốc thời gian dựa trên policy và mức clock skew cho phép; không chỉ kiểm `iat`.

Test quan trọng là RP phát một request `max_age=0` khi browser đã có session OP, rồi xác minh server thật sự buộc bước active authentication mới và ID Token trả về `auth_time` của lần mới đó. Một hệ thống hiển thị UI nhưng không đổi bằng chứng xác thực chưa đủ.

### 9.3. Kiểm thử theo phiên bản Spring

Các API và hành vi có thể khác giữa Spring Authorization Server 1.x và phần tích hợp trong Spring Security 7.x. Đặc biệt, **`prompt=none` phải được kiểm thử bằng request thật khi người dùng chưa đăng nhập**, vì thứ tự filter và authentication entry point có thể quyết định việc trả `login_required` hay chuyển hướng sai đến login.

Đừng coi việc bật `.oidc(Customizer.withDefaults())` là bằng chứng hệ thống đã tuân thủ mọi yêu cầu reauthentication. Ghi lại phiên bản, security filter order và ma trận prompt/max_age trong test suite cho lần nâng cấp framework.

## 10. Tình huống thực tế và hướng xử lý sự cố

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
|---|---|---|
| Login thành công nhưng không về client | Request cache mất trạng thái, redirect handler thay bằng URL cố định | Dùng saved request an toàn, kiểm tra security filter chain và session |
| Trang login lặp vô hạn | `prompt=login` chưa có dấu giao dịch đã fresh, session cookie không duy trì, `auth_time` không được cập nhật | Lưu xác thực theo transaction, kiểm tra cookie/proxy/time, ngăn loop |
| RP yêu cầu `max_age=0` nhưng vẫn SSO thẳng | OP chưa thực thi chính sách `max_age` hoặc chỉ kiểm tra session | Thêm reauth handling, tạo `auth_time` đúng và integration test |
| `prompt=none` lại hiện form | Entry point/filter xử lý authentication trước OIDC error | Kiểm tra thứ tự filter và version, bổ sung xử lý protocol chuẩn |
| Sau login lại nhận `invalid_state` | OAuth2 state bị thay/mất, nhiều tab hoặc session bị tái tạo | Rà soát RP session, request state/cookie/PKCE; không bỏ kiểm `state` |
| Người dùng A đăng nhập lại thành B | Login/account selection không gắn giao dịch với subject đúng | Xác minh `sub`, consent và account binding tại OP/RP |
| POST login bị 403 | CSRF token thiếu/sai, session khác, reverse proxy/cookie issue | Kiểm tra template `_csrf`, form action, cookie và chain |
| Người dùng thấy cảnh báo tài khoản tồn tại hay không | Thông báo lỗi quá chi tiết, thời gian phản hồi khác nhau | Dùng thông điệp chung, kiểm thử timing và rate limit |
| Content Security Policy chặn style/script của login | Asset khác origin, script inline, chính sách quá chặt | Dùng tài nguyên first-party và CSP phù hợp, tránh `unsafe-inline` không cần |
| Thông tin `login_hint` bị lộ ra analytic | Trang login có third-party script/pixel hoặc gửi Referer | Gỡ tracker, hạn chế query data, dùng `Referrer-Policy: no-referrer` |
| Cookie không gửi sau redirect | Secure/SameSite/domain/path/TLS termination sai | Test trình duyệt thật và endpoint công khai, sửa cấu hình trusted proxy |
| JWT ID Token có `auth_time` mới dù không reauth | Claim được gán tại token issuance thay vì active auth | Lưu trusted authentication time qua authorization và token exchange |

## 11. Checklist bảo mật, vận hành và quyền riêng tư

- [ ] Xác định rõ chính sách fresh authentication cho SSO thông thường, thao tác nhạy cảm và MFA/step-up.
- [ ] Xử lý `prompt=login`, `max_age`, `prompt=none` theo OIDC; test cả trường hợp **đang có OP session** và **chưa có OP session**.
- [ ] Theo dõi thời điểm **active authentication thực**, ràng buộc với authorization và tạo claim `auth_time` khi `max_age` yêu cầu.
- [ ] RP xác minh ID Token, `auth_time`, `iss`, `aud`, `exp`, `nonce` và `sub` trước khi cho phép thao tác nhạy cảm.
- [ ] Form POST `/login` dùng HTTPS + CSRF; session ID được thay sau login, cookie có Secure/HttpOnly/SameSite phù hợp.
- [ ] Trang login có CSP, no-store, no-referrer, không chèn third-party scripts hoặc gửi credentials/authorization data tới analytics.
- [ ] Đưa password/OTP qua POST; không dùng query string, hidden return URL, log hay DOM để lưu credential.
- [ ] Thông báo lỗi không tiết lộ tài khoản tồn tại; có rate limit, phát hiện credential stuffing, ưu tiên MFA/passkey khi cần.
- [ ] Tránh open redirect: chỉ khôi phục saved request/redirect URI đã được kiểm tra.
- [ ] Kiểm thử multi-tab, account switching, session expiry, proxy, nhiều instance và nâng cấp framework.
- [ ] Giám sát số lần reauthentication, lỗi `login_required`, `invalid_state`, CSRF, login failure và vòng lặp redirect, nhưng hạn chế dữ liệu cá nhân.
- [ ] Có quy trình xóa/giảm thời gian giữ audit/log nhạy cảm theo yêu cầu tổ chức.

**Câu hỏi tự kiểm tra**

1. Một ID Token vừa được ký tại thời điểm hiện tại có chứng minh người dùng vừa đăng nhập lại không? Nên kiểm tra claim nào?
2. `prompt=login` và `max_age=300` khác nhau ở điều kiện nào?
3. Nếu RP gửi `max_age=0`, ID Token được trả về bắt buộc cần claim nào?
4. Tại sao `prompt=none` không được chuyển trình duyệt đến trang login khi người dùng chưa có phiên?
5. Vì sao không nên dùng trường `returnUrl` nhận từ browser để redirect sau login?
6. Nếu người dùng đã đăng nhập A nhưng xác thực lại thành B, OP và RP phải bảo vệ ràng buộc tài khoản ra sao?
7. Khi token request xảy ra qua back-channel, có thể lấy `auth_time` từ HTTP session của request đó không?
8. Những header nào giúp giảm rủi ro XSS, clickjacking, rò referrer và lưu cache trên trang login?

## Tài liệu tham khảo

- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): `prompt`, `max_age`, `auth_time`, `login_hint`, `acr_values` và xác minh ID Token.
- [Spring Authorization Server — Getting Started](https://docs.spring.io/spring-authorization-server/reference/getting-started.html): cấu hình hai filter chain và form login.
- [Spring Authorization Server — SPA with PKCE](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-pkce.html): luồng browser redirect đến login và quay về authorization endpoint.
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html): cơ chế form login và cấu hình `loginPage`.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): bảo vệ request thay đổi trạng thái và CSRF token trong form.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): session fixation, session persistence, timeout và concurrency.
- [Spring Security — Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html): cache, CSP, frame options, Referrer Policy và HSTS.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): reauthentication, generic errors, MFA và bảo vệ chống brute force.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session cookies, renewal và expiration.
- [Spring Security issue: OIDC `prompt=none` in 7.0](https://github.com/spring-projects/spring-security/issues/18647): ví dụ tình huống cần regression test theo phiên bản; kiểm tra trạng thái issue/upstream trước khi áp dụng workaround.
