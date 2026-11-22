# Login CSRF, đăng nhập không được yêu cầu và nhầm lẫn phiên trong Spring Security federation

## 1. Mục tiêu và bối cảnh

Trong **Spring Security – federation**, người dùng có thể đăng nhập bằng form truyền thống hoặc được chuyển sang Identity Provider thông qua **OIDC/OAuth 2.0, SAML 2.0, CAS, SPNEGO** và identity-aware proxy. Ở các luồng chuyển hướng, một phản hồi xác thực **hợp lệ về mặt mật mã** chưa đủ để chứng minh rằng **trình duyệt này đã chủ động yêu cầu chính lần đăng nhập đó**.

Đây là nguồn gốc của **Login CSRF** (Cross-Site Request Forgery ở điểm đăng nhập), **unsolicited login** (đăng nhập không có yêu cầu tương ứng từ ứng dụng) và **session/account confusion** (phiên đang mang danh tính không mong muốn hoặc thuộc người khác).

Một kịch bản:

~~~text
1. Mallory có tài khoản tại website kinh doanh.
2. Mallory dùng lỗ hổng login CSRF khiến trình duyệt Alice
   hoàn tất đăng nhập vào tài khoản Mallory.
3. Alice không nhận ra danh tính đang hoạt động đã đổi.
4. Alice điền đơn hàng, lịch sử hoạt động hoặc thông tin nhạy cảm.
5. Dữ liệu được lưu dưới tài khoản Mallory; Mallory có thể xem được.
~~~

Kẻ tấn công **không cần mật khẩu của Alice**. Hắn muốn **Alice dùng một tài khoản mà hắn kiểm soát**. Vì vậy kiểm thử chỉ kiểm “attacker có lấy được tài khoản Alice không?” sẽ bỏ sót login CSRF.

Bài học thuộc nhóm **Gia cố an toàn**, giúp bạn:

- Phân biệt login CSRF, CSRF nghiệp vụ, session fixation, unsolicited IdP SSO, identity switch, account linking CSRF và AS mix-up.
- Biết yêu cầu một **login transaction được khởi tạo, có expiry, chỉ dùng một lần và liên kết browser/pre-session** trước khi nhận callback.
- Hiểu vai trò và giới hạn của **CSRF token form**, OAuth/OIDC **state**, **PKCE S256**, OIDC **nonce**, RFC 9207 **iss**, SAML **InResponseTo** và **RelayState**.
- Không tự chuyển authenticated user **Alice thành Mallory** chỉ vì callback mới có token hợp lệ.
- Khóa đúng **issuer + tenant + stable subject**, quản lý local session, fixation protection, session rotation và saved state.
- Chẩn đoán SAML IdP-initiated login, OIDC authorization response injection, CAS callback, SPNEGO automatic authentication và proxy header/session mismatch.
- Cấu hình Spring Security đúng vùng chức năng và viết kiểm thử bảo mật theo các luồng thực tế.
- Chạy ví dụ **Java 17 độc lập** mô phỏng state binding, wrong browser, unsolicited/replayed response, wrong IdP, nonce, audience và silent account switch.

**Nguyên tắc cốt lõi:** trước khi tạo Spring `Authentication`, kiểm **(a) chứng từ IdP thực sự hợp lệ**, **(b) chứng từ thuộc đúng yêu cầu RP đã phát cho browser này**, **(c) identity mới được phép gắn với local session hiện tại**. Ba điều kiện **không thay thế nhau**.

## 2. Phân biệt các lớp tấn công

| Tên | Attacker muốn gì? | Sai lầm kỹ thuật | Cơ chế khắc phục |
| --- | --- | --- | --- |
| **Business CSRF** | Ép user đang login chuyển tiền/đổi địa chỉ | Thiếu CSRF token trên POST/PUT/... | `CsrfFilter`, token, Origin/Fetch Metadata defense in depth |
| **Form login CSRF** | Ép browser đăng nhập bằng credentials của attacker | Form POST login không kiểm CSRF token | Pre-session + CSRF token + fresh authenticated session |
| **OAuth/OIDC response CSRF** | Đưa code/token response không thuộc browser/login transaction vào callback | Không kiểm state/PKCE/nonce/binding | Correlate state/nonce/PKCE với browser, one-time consume |
| **IdP-initiated SAML unsolicited** | Gửi SAMLResponse mà SP không hề phát AuthnRequest | Không có InResponseTo để chứng minh request | SP-initiated mặc định; unsolicited chỉ mở có policy |
| **Session fixation** | Dùng lại session ID attacker biết qua login | Pre-session thành authenticated session mà không rotate/replace | Session fixation protection; audit session attribute migration |
| **Account/session confusion** | Alice tiếp tục dùng phiên/role Bob hoặc bị đổi Mallory | Không so principal/tenant/session khi callback mới | Explicit account-switch policy, session invalidation/rotation |
| **OAuth AS mix-up** | Gửi code/credentials tới AS/token endpoint không đúng | Không bind issuer với giao dịch và callback | RFC 9207 iss / RFC 9700 mix-up defense |
| **Account-linking CSRF** | Liên kết identity của attacker với local account victim | Link OAuth/SAML không có consent/transaction | Reauth + CSRF/user intent + full binding |

**Đăng nhập không được yêu cầu không luôn đồng nghĩa tấn công**: nhiều IdP cho user bắt đầu SSO từ một ứng dụng portal/tile. Tuy nhiên nếu SP không khởi tạo request, **khả năng tương quan giao dịch với trình duyệt tại SP bị giảm**; phải thừa nhận và quản trị rủi ro đó.

## 3. Vì sao login CSRF xuất hiện ở trạng thái anonymous?

OWASP chỉ rõ **form login cũng cần CSRF protection**, dù user chưa authenticated. Khi chưa có phiên đăng nhập, browser vẫn có thể nhận **pre-session cookie** để giữ CSRF token. Nếu endpoint login bỏ qua token, một trang thứ ba có thể tự POST thông tin đăng nhập của kẻ tấn công vào app mục tiêu.

Ví dụ an toàn:

~~~text
GET /login:
    tạo pre-session A
    cấp CSRF token tương ứng A

POST /login:
    yêu cầu token hợp lệ từ pre-session A
    xác minh username/password với provider thật
    vô hiệu hóa/thay pre-session A
    cấp authenticated session B với ID mới
~~~

**Không nâng nguyên pre-session thành authenticated session một cách vô điều kiện.** OWASP khuyến nghị sau login phải tạo phiên mới, tránh session fixation. Spring Security cung cấp session fixation strategies nhưng bạn vẫn phải audit **attrs nào được giữ lại** và không mang dữ liệu user cũ sang session mới.

Một form minh họa:

~~~html
<form method="post" action="/login">
  <input type="hidden" name="_csrf" value="render-from-CsrfToken">
  <input type="text" name="username" autocomplete="username">
  <input type="password" name="password" autocomplete="current-password">
  <button type="submit">Đăng nhập</button>
</form>
~~~

Giá trị `render-from-CsrfToken` là **mô tả cách render**, không phải token sử dụng được. Với Thymeleaf/Spring MVC, phải lấy `CsrfToken` thực do framework cung cấp, không hard-code hay đặt một token chung cho tất cả browsers.

### 3.1. Spring Security bảo vệ form login

~~~java
package com.example.portal.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class FormSecurity {
    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/public/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form
                .loginPage("/login").permitAll())
            .sessionManagement(session -> session
                .sessionFixation(fixation -> fixation.newSession()));
        return http.build();
    }
}
~~~

Đây là **Spring Boot Servlet configuration fragment**, cần login page, provider, CSRF token, project/dependencies và integration test; **không phải file Java độc lập**. Spring Security Servlet **bật CSRF mặc định** và tài liệu nêu rõ cần CSRF cho login requests. Đừng viết `csrf.disable()` hoặc `csrf.ignoringRequestMatchers("/login")` chỉ để POST login không còn lỗi 403.

**CSRF token hợp lệ chưa chứng minh credentials đúng**: sau `CsrfFilter` vẫn phải qua AuthenticationManager, user status và authorization rules. Cần HTTPS, rate limit, không log mật khẩu và request body.

## 4. Login transaction: hợp đồng bắt buộc trước callback

Một luồng federation redirect an toàn thường cần dữ liệu server-side như:

~~~text
LoginTransaction:
  transactionId       = one-time random secret/state
  browserBinding      = pre-session identifier
  providerRegistration= corp
  expectedIssuer      = https://login.example.test/realms/corp
  clientId            = portal-client
  redirectUri         = https://portal.example.test/login/oauth2/code/corp
  nonce               = fresh random value (OIDC khi áp dụng)
  pkceVerifier        = secret (OAuth Authorization Code + PKCE)
  createdAt/expiresAt = short-lived
  intent              = normal login / reauth / switch / link
  existingAccountKey  = nếu browser đã authenticated
  consumed            = false
~~~

Đây là **model học tập**, không phải cấu trúc Spring lưu nguyên xi. Tùy protocol, SAML dùng **AuthnRequest ID/InResponseTo**; OAuth dùng **state/nonce/PKCE**; các flow khác có cơ chế riêng. **Không dùng email, Origin giả, IP hoặc User-Agent làm thay thế browser binding**.

Callback phải:

1. Xác nhận request đến **callback endpoint đúng** được định tuyến tới đúng SecurityFilterChain/protocol filter.
2. Không nhận `state`/request ID thiếu, blank, lặp hoặc không có pending transaction.
3. Kiểm pending transaction gắn với **browser/pre-session này**, chưa dùng, chưa hết hạn.
4. Kiểm **issuer/provider/registration/client/redirectUri** đúng giao dịch đã bắt đầu.
5. Thực hiện **protocol validation thực sự** (signature, audience, nonce, assertion conditions, service binding, v.v.).
6. **Consume một lần** transaction; từ chối replay/concurrent callbacks.
7. Kiểm account-switch/login-intent policy nếu browser đã authenticated.
8. Nạp local user và authorities đúng **issuer+tenant+subject**, tạo/rotate authenticated session.
9. Không cho callback cũ tạo một `SecurityContext` mới sau logout hoặc switch sang account khác.

**Nếu request thiếu transaction phù hợp thì fail closed**: không “xây lại” pending transaction từ chính `state` hoặc query của caller.

## 5. OAuth/OIDC Authorization Code: state, PKCE, nonce, iss

### 5.1. Luồng hợp lệ

~~~text
Browser                   Spring RP                       OIDC Provider
   |                         |                                  |
   | chọn /login             |                                  |
   |------------------------>|                                  |
   |                         | tạo state, nonce, PKCE,            |
   |                         | lưu provider + browser session     |
   |<------------------------| 302 /authorize?state=...          |
   |----------------------------------------------------------->|
   |                         |                                  | Auth user
   |<-----------------------------------------------------------|
   | callback?code=...&state=... (có thể có iss=...)            |
   |------------------------>|                                  |
   |                         | lookup transaction               |
   |                         | compare browser, state, issuer  |
   |                         | check expiry / one-time         |
   |                         | validate iss before code routing|
   |                         | exchange code + code_verifier   |
   |                         | verify ID Token + nonce         |
   |                         | local user / consent policy     |
   |                         | fresh local session             |
~~~

- `state` là **giá trị khó đoán** dùng liên kết authorization response với authorization request/browser. Nếu chứa application state, phải bảo vệ chống **tampering/swapping**.
- `nonce` OIDC gắn authorization request với **ID Token** để kiểm replay/injection; phải kiểm theo request/response profile.
- **PKCE S256** gắn code được phát với `code_verifier` bí mật chỉ client biết ở token exchange; giúp phòng code interception/injection.
- `iss` theo **RFC 9207** xác định authorization server đã phát response, dùng chống **mix-up** khi RP có nhiều providers.
- `redirect_uri` và `client_id` phải đúng client registration; tuyệt đối không lấy token endpoint hoặc JWKS URL từ một query chưa kiểm.
- Với OIDC, ID Token cần chữ ký hợp lệ, issuer, audience, expiry, nonce và những claim bắt buộc theo cấu hình; không tin `sub` khi chưa validate.
- Nếu có access token, nó không tự thay ID Token trong OIDC login. Không sử dụng raw `code` làm session credential.

### 5.2. Một lưu ý đúng chuẩn về CSRF defense

**RFC 9700 (OAuth 2.0 Security Best Current Practice)** cho phép client **dựa vào PKCE** hoặc OIDC **nonce** để chống authorization response CSRF **khi thỏa các điều kiện mô tả**, như bảo đảm authorization server hỗ trợ và bắt buộc PKCE. Không chính xác nếu nói mọi OAuth client bắt buộc dùng đồng thời cả `state`, PKCE, nonce trong mọi profile.

Tuy vậy, với ứng dụng Spring OIDC dùng Authorization Code, thực hành rõ ràng là **giữ state/browser transaction binding**, sử dụng PKCE S256 nơi áp dụng và kiểm nonce trong OIDC. Tránh:

- `state` cố định hoặc dự đoán được;
- `state` chỉ gồm base64(username);
- lưu state global không gắn browser;
- cho state được tái dùng;
- dùng `nonce` cố định qua nhiều logins;
- chấp nhận PKCE downgrade khi AS thực tế không enforce;
- exchange code đến endpoint được client chỉ định ở callback.

### 5.3. Khi có nhiều providers: AS mix-up

~~~text
Browser muốn đăng nhập IdP A.
RP đã lưu expectedIssuer = A.
Callback lại có code/issuer từ IdP B.
Nếu RP chọn token endpoint theo parameter từ browser:
  có thể đưa code/credential sang endpoint sai.
~~~

Theo **RFC 9700**, RP làm việc với **nhiều authorization servers** phải có bảo vệ mix-up. Thông thường dùng:

- Kiểm `iss` trong authorization response theo **RFC 9207** so khớp **issuer đã lưu**, trước khi định tuyến code tới token endpoint;
- Hoặc một issuer indication tương đương được kiểm đúng chuẩn;
- Nếu không có phương pháp trên, có thể dùng **redirect URIs tách biệt theo issuer** theo BCP.

**Cảnh báo:** chỉ kiểm ID Token `iss` **sau** khi code đã được gửi đến sai endpoint có thể **quá muộn** để ngăn lộ code ở kịch bản mix-up. Cần ràng buộc issuer/provider ngay từ transaction và routing của OAuth client.

### 5.4. Authorization request là khác với ý định người dùng

Spring Security thường cho phép khởi tạo bằng GET:

~~~text
GET /oauth2/authorization/{registrationId}
~~~

Một attacker có thể dẫn browser nạn nhân vào URL này bằng link/redirect, khiến RP tạo `state` hoàn toàn hợp lệ. Vì thế **state chứng minh giao dịch tồn tại**, chứ **không chứng minh người dùng chủ ý chọn chuyển account**.

Đối với **account linking, switch, step-up, nâng quyền hoặc đổi tenant**, cần một lớp **explicit user intent**: trang xác nhận, reauth, một POST/CSRF-protected action hoặc flow coordinator có approval, và kiểm identity kết quả. Không để một GET từ nguồn ngoài tự gắn IdP identity vào tài khoản đang login.

## 6. Spring Security oauth2Login và AuthorizationRequestRepository

Spring Security có các thành phần:

| Thành phần | Trách nhiệm |
| --- | --- |
| `OAuth2AuthorizationRequestRedirectFilter` | Bắt đầu OAuth authorization request |
| `AuthorizationRequestRepository<OAuth2AuthorizationRequest>` | Lưu pending authorization request để correlation |
| `HttpSessionOAuth2AuthorizationRequestRepository` | Implementation lưu request trong HttpSession |
| `OAuth2LoginAuthenticationFilter` | Nhận authorization code response và xử lý login |
| `ClientRegistrationRepository` | Lưu registrationId, issuer/provider, redirect URI, client metadata |
| `OAuth2AccessTokenResponseClient` | Thực hiện token exchange theo client registration |
| `OidcUserService` và token validators | Nạp và kiểm identity/claims OIDC phù hợp |

Mặc định route thường là:

~~~text
Start:    /oauth2/authorization/{registrationId}
Callback: /login/oauth2/code/{registrationId}
~~~

Ví dụ cấu hình nhấn mạnh không bỏ request repository:

~~~java
package com.example.portal.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.web.AuthorizationRequestRepository;
import org.springframework.security.oauth2.client.web.HttpSessionOAuth2AuthorizationRequestRepository;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcLoginConfig {
    @Bean
    AuthorizationRequestRepository<OAuth2AuthorizationRequest>
    authorizationRequestRepository() {
        return new HttpSessionOAuth2AuthorizationRequestRepository();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            AuthorizationRequestRepository<OAuth2AuthorizationRequest> repo)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/public/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oidc -> oidc
                .loginPage("/login")
                .authorizationEndpoint(authz -> authz
                    .authorizationRequestRepository(repo)))
            .sessionManagement(session -> session
                .sessionFixation(fixation -> fixation.newSession()));
        return http.build();
    }
}
~~~

**Đây là Spring configuration sample**, không phải Java chạy với `javac` đơn độc. Cần dependencies OAuth2 Client, ClientRegistration đúng, HTTPS, real IdP và `GET /login` nếu dùng loginPage tùy chỉnh. `oauth2Login` xử lý giao thức; **policy cấm silent account switch cần được bổ sung vào application success/flow coordinator**.

Nếu tự thay repository bằng cookie hoặc Redis:

- Bảo vệ **integrity/confidentiality** nếu lưu dữ liệu nhạy cảm trong cookie.
- Bind state với browser/pre-session, expected issuer/client/redirectUri/nonce/verifier.
- Atomic consume, TTL và logout invalidation.
- Tránh global shared map theo state **không kiểm browser session**.
- Test multi-tab và multi-node thật.
- Không khắc phục lỗi state bằng cách “accept callback anyway”.

## 7. SAML SP-initiated: InResponseTo là transaction correlation

~~~text
Browser -> /saml2/authenticate/corp
SP -> tạo <AuthnRequest ID="_req123"> và lưu theo browser session
SP -> IdP SAMLRequest
IdP -> Browser -> SP ACS SAMLResponse
Response/SubjectConfirmationData InResponseTo="_req123"
SP -> xác minh signature, issuer, audience, destination, recipient,
      Conditions, SubjectConfirmation và correlation với request gốc.
SP -> replay check, local account binding, authenticated session mới.
~~~

**`InResponseTo` có ý nghĩa**: response hoặc subject confirmation thuộc AuthnRequest nào do SP tạo. Một response có chữ ký IdP hợp lệ nhưng `InResponseTo` không khớp request đã lưu **phải bị từ chối** trong flow SP-initiated.

**`RelayState`** dùng truyền trạng thái quay về, nhưng **không phải chứng cứ tự thân** rằng SP đã yêu cầu authentication trong browser đang nhận callback. Nếu RP lookup một request chỉ theo `InResponseTo`/RelayState trong **global cache**, và không bind browser, attacker có thể thử **login fixation**.

Spring Security Servlet SAML 2.0 có:

- `Saml2WebSsoAuthenticationRequestFilter` phát AuthnRequest.
- `Saml2AuthenticationRequestRepository` để lưu request.
- `HttpSessionSaml2AuthenticationRequestRepository` là mặc định nêu trong tài liệu Spring.
- `CacheSaml2AuthenticationRequestRepository` có thể được dùng khi không giữ session; **phải quản lý browser binding thật sự**.
- `Saml2WebSsoAuthenticationFilter` và converters/validators đọc request + assertion.

Spring docs cảnh báo: khi AuthnRequest được tìm trong **HttpSession**, có lợi ích chống login fixation tự nhiên; nếu chỉ lookup theo một `InResponseTo`/`RelayState` dùng trên mọi browser thì không còn bằng chứng “browser này đã khởi tạo request ấy”.

## 8. SAML IdP-initiated / unsolicited response

Một IdP có thể đưa user vào ứng dụng khi họ bấm tile trên IdP portal, mà **SP không hề phát AuthnRequest**. IdP gửi SAMLResponse đến ACS, thường **không có InResponseTo**.

~~~text
User -> IdP portal tile
IdP -> POST signed SAMLResponse -> SP ACS
SAML Response: no SP AuthnRequest, no corresponding InResponseTo
~~~

Đây là một use case **có thật**, không mặc định là malicious. Nhưng nó **mất lớp correlation với RP transaction**; nếu attacker có khả năng đưa một assertion hợp lệ cho account của mình vào browser người khác, SP dễ gặp **unsolicited login / login CSRF** nếu tự accepted/replace session.

Khuyến nghị:

1. Với ứng dụng nhạy cảm, **ưu tiên SP-initiated** và reject unsolicited response nếu không có nhu cầu.
2. Nếu phải cho IdP-initiated, giới hạn **IdP/registration/service/tenant** được duyệt; không chấp nhận tất cả.
3. Vẫn kiểm đầy đủ SAML signature với keys tin cậy, issuer, audience, recipient, destination, Conditions, SubjectConfirmationData, clock skew và replay của assertion/response IDs.
4. **Không gán InResponseTo giả hoặc coi RelayState không được bảo vệ là bằng chứng SP-initiated**.
5. Không dùng unsolicited response tự **thay một authenticated user đang có**; yêu cầu explicit account switch/consent nếu policy cần.
6. Với app có yêu cầu chứng minh user intent phía SP, có thể cho IdP tile mở một landing page rồi **khởi tạo SP-initiated SSO**.
7. Test browser anonymous, đang login cùng user, đang login user khác, hai tabs, SAML response replay và cross-browser POST.
8. Không copy cấu hình `supportUnsolicitedResponse` từ **Spring SAML Extension cũ** vào Spring Security SAML 2.0 hiện đại mà không kiểm API/version.

### 8.1. SAML POST và Spring Servlet CSRF

SAML HTTP-POST binding gửi form POST **từ IdP bên ngoài đến ACS**. Nó thường **không thể** gửi cùng `_csrf` token của form business app. Do đó nếu có cấu hình CSRF exception cho ACS:

- Chỉ giới hạn **ACS endpoint** được SAML filter kiểm; không `csrf.disable()` toàn ứng dụng.
- Dùng **SAML signature + request correlation + audience/recipient/timing/replay** để bảo vệ chính ACS.
- Không chuyển sang tin bất kỳ `SAMLResponse` nào chỉ vì request đi qua CSRF exception.
- Browser cookie `SameSite=Lax` thường **không gửi trên cross-site POST**; có thể mất HttpSession chứa AuthnRequest. Cần thiết kế cookie/correlation sao cho vừa giữ khả năng callback vừa không bỏ browser binding.

## 9. CAS, SPNEGO và proxy-auth không có cùng state parameter

### 9.1. CAS Service Ticket

CAS ST có thể được CAS xác minh một lần và ràng buộc service:

~~~text
Browser -> /login/cas?ticket=ST-...
App -> CAS /serviceValidate(ticket, service)
CAS -> valid service ticket + CAS username
~~~

ST hợp lệ **không tự chứng minh browser đã chủ ý yêu cầu login lần này**. App vẫn cần chính sách **login initiation**, local session switch, tenant/identity binding. Nếu thêm state vào service URL, phải bảo toàn **service identity** đúng CAS registered service và validator; không gắn bừa query rồi nghĩ mọi CAS deployments đều support.

### 9.2. Kerberos/SPNEGO

Domain browser có thể tự động gửi `Authorization: Negotiate` dựa vào OS Kerberos cache. Tính tự động đó **khác** OAuth callback state. Nếu browser hiện đã có local session Alice nhưng OS/browser authentication chuyển Bob, phải kiểm **principal continuity** và policy user switch, không giữ role/cache Alice cho Bob.

### 9.3. Identity-aware proxy

Gateway gửi trusted headers, ví dụ `X-Authenticated-Subject`. App có thể có HttpSession cũ Alice. Nếu gateway bỏ header hoặc gửi Bob, app **không được** tiếp tục dùng SecurityContext Alice. Cần trusted gateway/network, header stripping, per-request identity binding và session invalidation, không chỉ kiểm header string.

**Bài học chung:** không có một chuẩn `state` dùng đồng loạt cho OIDC, SAML, CAS, SPNEGO và pre-auth proxy. Mỗi giao thức có cơ chế chứng minh nguồn gốc khác nhau, nhưng mọi đường đều cần **ngăn identity/session confusion**.

## 10. Session fixation, session swapping, silent user change

Ba tình huống khác nhau:

### 10.1. Fixation — vấn đề session ID

~~~text
Pre-session S0: anonymous, attacker biết/ấn định session ID S0.
User login thành công.
Ứng dụng sai: authenticated session vẫn dùng S0.
=> attacker có khả năng dùng S0 trong threat model fixation.
~~~

Spring Security có `changeSessionId()`, `newSession()` và `migrateSession()` theo servlet/session version. `changeSessionId` đổi ID nhưng giữ session attributes; `migrateSession` copy attributes; `newSession` tạo session mới sạch hơn nhưng framework có các Spring Security attrs cần thiết. Phải kiểm project/app data có đi theo session không, không coi chỉ đổi ID là mọi state đã an toàn.

### 10.2. Session swapping — vấn đề identity, không phải ID

~~~text
Browser đang sử dụng Alice hoặc anonymous.
Response login hợp lệ cho Mallory xuất hiện.
App tạo/đổi authenticated principal = Mallory.
User không nhận ra account đã đổi; nhập dữ liệu vào account Mallory.
~~~

Session ID có thể **đã được rotate hoàn hảo** nhưng vẫn có **login CSRF** vì user không định đăng nhập Mallory.

### 10.3. Session confusion — dữ liệu/roles của hai users bị trộn

~~~text
Session S_A: Alice, tenant A, cart của Alice, ROLE_APPROVER.
Callback mới: Bob, tenant B.
App chỉ đổi Authentication principal thành Bob.
SavedRequest/cart/cache/roles cũ chưa được xóa.
=> Bob có thể nhìn thấy state của Alice hoặc dùng sai quyền.
~~~

Hai chiến lược:

- **Deny-on-switch (đề xuất mặc định đơn giản):** không đổi identity âm thầm; reject callback, giữ current session hoặc yêu cầu logout/reauth tùy policy và risk.
- **Explicit switch:** user chủ ý chọn **Đổi tài khoản**, có CSRF/intent-bound transaction, app validate response, invalidate old session, tạo clean session mới, nạp local UserDetails/roles của user mới và đảm bảo không mang dữ liệu cũ.

**Không chỉ dựa vào `Authentication.getName()`**: email có thể trùng/đổi, tenant/issuer có thể khác dù username trùng. Dùng stable key như `(trusted issuer, tenant, subject)` hoặc SAML issuer-qualified NameID được quản trị; việc linking hai identities khác nhau cần phê duyệt riêng.

### 10.4. Local logout không phải IdP logout

Nếu local `HttpSession` bị xóa nhưng IdP SSO session còn, browser có thể đăng nhập lại nhanh bằng một **giao dịch mới**. Đây không tự là lỗi session invalidation. Ngược lại, nếu IdP session đã logout mà app vẫn chấp nhận local session trái contract, cần kiểm back-channel/front-channel logout hoặc session freshness policy.

## 11. Pre-session, SecurityContext và phiên mới

Spring Security `SecurityContextHolder` lưu Authentication của request hiện tại; `SecurityContextRepository` chịu trách nhiệm khôi phục/lưu vào HttpSession hoặc store phù hợp. **Chỉ gọi `SecurityContextHolder.clearContext()` không đương nhiên xóa Authentication đang lưu trong HttpSession**.

Với custom login/switch:

1. Xác minh transaction và identity trước khi tạo Authentication.
2. Kiểm account switch / linking policy.
3. Áp session fixation/session authentication strategy đúng.
4. Vô hiệu hóa session/user-specific attributes cũ, session store state và pending transactions không còn hợp lệ.
5. Tạo SecurityContext mới với Authentication có roles **từ user/tenant mới**.
6. `SecurityContextRepository.saveContext(...)` khi muốn persist trong Spring Security Servlet có explicit-save semantics.
7. Trả redirect đến internal return path allowlisted; không làm open redirect.
8. Đảm bảo old session/cookie không còn truy cập được.
9. Nếu lưu trong Redis/JDBC/Spring Session, kiểm invalidation giữa replicas và concurrent callbacks.
10. Test cả browser refresh/back, two tabs, re-login sau logout, same-account reauth và different-account switch.

**Đừng chuyển pre-session vô điều kiện thành một phiên authenticated**, và cũng đừng coi việc login success handler trả `302` là bằng chứng session/account mapping đúng.

## 12. Multi-provider, multiple tabs và concurrent callbacks

Trình duyệt có thể mở:

~~~text
Tab A: /oauth2/authorization/idp-a -> state=A
Tab B: /oauth2/authorization/idp-b -> state=B
Tab C: /logout hoặc switch-account
~~~

Nếu app lưu **chỉ một pending auth request**, tab B ghi đè transaction A. Điều đó có thể dẫn đến login fail hoặc, nguy hiểm hơn, custom code tự fallback chấp nhận response không khớp.

Thiết kế an toàn:

- Mỗi flow có random state/request ID riêng, issuer/client/nonce/PKCE riêng.
- Bind với browser session **không chỉ global cache lookup theo state**.
- Atomic **compare-and-consume** để cùng response không được xử lý hai lần.
- Với wrong browser callback, reject không dùng response làm login; quản lý DoS khi attacker biết state.
- Nếu logout/switch account trong lúc pending flow, hủy hoặc version transactions cũ.
- Khi hai callbacks cùng session về gần đồng thời, một **account/session policy** quyết định thắng/thua; không được tạo user A rồi user B giữ lại business state A.
- Dùng distributed TTL store + atomic operations khi nhiều nodes; không dựa vào `HashMap` một máy.
- Test session ID rotation, stale cookie, cookies SameSite, user đổi, issuer đổi, multiple tabs, redirect loops.

### 12.1. Login intent là gì?

Ngay cả khi OIDC state hợp lệ, attacker có thể **chủ động dẫn browser đến start endpoint**. Với hệ thống cần chứng minh user đã lựa chọn account hoặc link IdP:

- Dùng trang đăng nhập/ chọn IdP rõ ràng và có confirmation.
- Với sensitive account switch/link, yêu cầu POST có CSRF token hoặc một transaction có **user-intent proof** tương đương.
- Xem callback mới như **một yêu cầu thay đổi identity**, không tự thay session hiện hữu.
- Không tin `intent=link` từ query parameter nếu không có server-side transaction đã bind.

**Điểm phân biệt:** yêu cầu do browser gửi ≠ yêu cầu mà chủ browser đã có ý định thực hiện.

## 13. Cookie SameSite, HTTPS và open redirect

| Profile | Hình dạng callback | Cookie cần chú ý |
| --- | --- | --- |
| OIDC Authorization Code truyền thống | Top-level GET cross-site | `SameSite=Lax` thường cho RP cookie trong top-level GET |
| SAML HTTP-POST | Cross-site POST ACS | `SameSite=Lax` thường không gửi cookie; SP có thể mất AuthnRequest |
| Form login cùng site | POST tới /login | CSRF token vẫn cần |
| Iframe/SPA/BFF đặc biệt | Embedded/cross-site contexts | Third-party cookie policy, SameSite và security context cần thiết kế riêng |

Cookie nên dùng `Secure`, `HttpOnly` nếu có thể, `Path/Domain` chặt, session timeout và server-side invalidation. `SameSite=None` đòi `Secure` trên browser hiện đại và **tăng tầm quan trọng của CSRF/correlation**. `SameSite=Strict` có thể làm OIDC/SAML callback mất cookie dù có auth response hợp lệ; sửa cookie/binding strategy thay vì **tắt state/InResponseTo validation**.

**Return URL/open redirect:**

~~~text
Login success?return=https://attacker.example.test/collect
~~~

Không redirect tùy ý tới URL do browser/RelayState/state chứa nếu chưa validate. Chỉ cho phép **relative internal paths hoặc allowlist chính xác**, protect state integrity. Redirect sai có thể làm lộ `code`, token hoặc thông tin identity; không đưa code/ID Token/SAMLResponse/ServiceTicket vào URL downstream.

**Logging:** redact query `code`, `state`, `ticket`, SAMLResponse, cookies, Authorization headers, code_verifier, user credentials và PII.

## 14. Java 17 độc lập: login transaction và bảo vệ session

Ví dụ sau **biên dịch với JDK 17+**, chạy mà không cần IdP/Spring. Nó mô phỏng:

- Server chỉ tạo flow nếu **userIntent** đã được kiểm trước.
- `SecureRandom` sinh state/nonce 32 bytes Base64URL.
- Mỗi flow lưu browser session, expected issuer, audience/client và creation time.
- Callback từ sai browser, state không có, hết hạn, bị sửa/replay hoặc issuer/nonce/audience khác bị từ chối.
- `VerifiedIdToken` chỉ là **mock output của verifier**, không phải JWT và không thực sự kiểm chữ ký.
- Login hợp lệ tạo **session mới**, xóa pre-session; callback cũ không thể mở lại.
- Browser đang login Alice không bị Mallory tự động thay; same-account reauth có thể rotate session.

**Cảnh báo:** `userIntent`/`signatureValid` là **đầu ra giả lập do test quyết định**, không được đọc thẳng từ JSON/HTTP request trong code thật. Production phải dùng framework OIDC verify JWT/issuer/audience/nonce/token endpoint và PKCE, browser cookies, TLS, CSRF token, session store/atomic operations. `HashMap` và `SecureRandom` ở demo **không tạo một OIDC client production**.

Tệp **LoginCsrfSessionDemo.java**:

~~~java
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.HashMap;
import java.util.Map;

public class LoginCsrfSessionDemo {
    static final String IDP_A = "https://idp-a.example.test";
    static final String IDP_B = "https://idp-b.example.test";
    static final String CLIENT = "portal-client";
    static final Instant NOW = Instant.parse("2026-01-01T12:00:00Z");
    static final Duration FLOW_TTL = Duration.ofMinutes(5);

    record Identity(String issuer, String subject) {}
    record Session(String id, Identity user) {}
    record Flow(String sessionId, String state, String nonce,
                String expectedIssuer, String audience, Instant started) {}
    // This record models a token ALREADY verified by a trusted OIDC library.
    // Never take signatureValid from request parameters or JSON in real code.
    record VerifiedIdToken(String issuer, String subject, String audience,
                           String nonce, boolean signatureValid) {}
    record Outcome(boolean accepted, String reason, String sessionId) {}

    private final SecureRandom random = new SecureRandom();
    private final Map<String, Session> sessions = new HashMap<>();
    private final Map<String, Flow> pending = new HashMap<>();

    private String fresh() {
        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    Session newBrowser() {
        Session s = new Session(fresh(), null);
        sessions.put(s.id(), s);
        return s;
    }

    Flow initiate(String sid, String issuer, boolean userIntent, Instant now) {
        if (!userIntent || !sessions.containsKey(sid) ||
            (!IDP_A.equals(issuer) && !IDP_B.equals(issuer))) return null;
        Flow f = new Flow(sid, fresh(), fresh(), issuer, CLIENT, now);
        pending.put(f.state(), f);
        return f;
    }

    VerifiedIdToken token(Flow f, String issuer, String user) {
        return new VerifiedIdToken(issuer, user, CLIENT, f.nonce(), true);
    }

    Outcome finish(String sid, String state, VerifiedIdToken token, Instant now) {
        Session browser = sessions.get(sid);
        if (browser == null) return new Outcome(false, "unknown-session", null);
        if (state == null || state.isBlank()) {
            return new Outcome(false, "missing-state", sid);
        }
        Flow f = pending.get(state);
        if (f == null) return new Outcome(false, "unsolicited-or-replay", sid);
        if (!sid.equals(f.sessionId())) {
            // A foreign browser must not consume the real browser's flow.
            return new Outcome(false, "cross-browser", sid);
        }
        if (now.isBefore(f.started()) ||
            !now.isBefore(f.started().plus(FLOW_TTL))) {
            pending.remove(state, f);
            return new Outcome(false, "expired-flow", sid);
        }
        if (!pending.remove(state, f)) {
            return new Outcome(false, "concurrent-replay", sid);
        }
        if (token == null || !token.signatureValid() ||
            token.subject() == null || token.subject().isBlank() ||
            !f.expectedIssuer().equals(token.issuer()) ||
            !f.audience().equals(token.audience()) ||
            !f.nonce().equals(token.nonce())) {
            return new Outcome(false, "invalid-id-token", sid);
        }

        Identity incoming = new Identity(token.issuer(), token.subject());
        if (browser.user() != null && !browser.user().equals(incoming)) {
            // Explicit logout/account switch required; keep existing identity.
            return new Outcome(false, "account-switch-requires-consent", sid);
        }
        // Successful authentication gets a NEW session, not a reused pre-session.
        sessions.remove(sid);
        Session authenticated = new Session(fresh(), incoming);
        sessions.put(authenticated.id(), authenticated);
        return new Outcome(true, "authenticated", authenticated.id());
    }

    static void expect(String name, boolean condition) {
        System.out.println(name + "=" + condition);
    }

    public static void main(String[] args) {
        LoginCsrfSessionDemo app = new LoginCsrfSessionDemo();
        Session a = app.newBrowser();
        expect("startRequiresUserIntent",
            app.initiate(a.id(), IDP_A, false, NOW) == null);

        Flow good = app.initiate(a.id(), IDP_A, true, NOW);
        Outcome ok = app.finish(a.id(), good.state(),
            app.token(good, IDP_A, "alice"), NOW.plusSeconds(3));
        expect("legitimateLoginAccepted", ok.accepted());
        expect("sessionRotated", !a.id().equals(ok.sessionId()));
        expect("oldSessionRejected", !app.finish(
            a.id(), good.state(), app.token(good, IDP_A, "alice"),
            NOW.plusSeconds(4)).accepted());
        expect("replayedStateRejected", !app.finish(
            ok.sessionId(), good.state(), app.token(good, IDP_A, "alice"),
            NOW.plusSeconds(4)).accepted());

        Session b = app.newBrowser();
        expect("unsolicitedCallbackRejected", !app.finish(
            b.id(), "not-issued-by-app",
            new VerifiedIdToken(IDP_A, "mallory", CLIENT, "x", true),
            NOW).accepted());
        expect("missingStateRejected", !app.finish(
            b.id(), null, null, NOW).accepted());

        Flow foreign = app.initiate(b.id(), IDP_A, true, NOW);
        Session c = app.newBrowser();
        expect("crossBrowserStateRejected", !app.finish(
            c.id(), foreign.state(), app.token(foreign, IDP_A, "alice"),
            NOW.plusSeconds(2)).accepted());
        expect("crossBrowserAttemptDoesNotConsumeOwnerFlow",
            app.finish(b.id(), foreign.state(),
                app.token(foreign, IDP_A, "alice"), NOW.plusSeconds(3))
                .accepted());

        Session d = app.newBrowser();
        Flow wrongIssuer = app.initiate(d.id(), IDP_A, true, NOW);
        expect("issuerMixupRejected", !app.finish(
            d.id(), wrongIssuer.state(),
            app.token(wrongIssuer, IDP_B, "alice"),
            NOW.plusSeconds(2)).accepted());

        Flow noProof = app.initiate(d.id(), IDP_A, true, NOW);
        expect("invalidTokenProofRejected", !app.finish(
            d.id(), noProof.state(),
            new VerifiedIdToken(IDP_A, "alice", CLIENT,
                noProof.nonce(), false), NOW.plusSeconds(2)).accepted());

        Flow nonce = app.initiate(d.id(), IDP_A, true, NOW);
        expect("nonceMismatchRejected", !app.finish(
            d.id(), nonce.state(),
            new VerifiedIdToken(IDP_A, "alice", CLIENT, "wrong", true),
            NOW.plusSeconds(2)).accepted());

        Flow audience = app.initiate(d.id(), IDP_A, true, NOW);
        expect("audienceMismatchRejected", !app.finish(
            d.id(), audience.state(),
            new VerifiedIdToken(IDP_A, "alice", "other-client",
                audience.nonce(), true), NOW.plusSeconds(2)).accepted());

        Flow expired = app.initiate(d.id(), IDP_A, true, NOW);
        expect("expiredStateRejected", !app.finish(
            d.id(), expired.state(), app.token(expired, IDP_A, "alice"),
            NOW.plusSeconds(301)).accepted());

        Flow alice = app.initiate(d.id(), IDP_A, true, NOW);
        Outcome loginAlice = app.finish(d.id(), alice.state(),
            app.token(alice, IDP_A, "alice"), NOW.plusSeconds(1));
        Flow mallory = app.initiate(loginAlice.sessionId(), IDP_A, true, NOW);
        expect("silentAccountSwitchRejected", !app.finish(
            loginAlice.sessionId(), mallory.state(),
            app.token(mallory, IDP_A, "mallory"),
            NOW.plusSeconds(2)).accepted());
        expect("existingAccountUnchanged",
            "alice".equals(app.sessions.get(loginAlice.sessionId()).user().subject()));

        Flow same = app.initiate(loginAlice.sessionId(), IDP_A, true, NOW);
        Outcome sameUser = app.finish(loginAlice.sessionId(), same.state(),
            app.token(same, IDP_A, "alice"), NOW.plusSeconds(2));
        expect("sameAccountReauthenticationAccepted", sameUser.accepted());
        expect("reauthenticationRotatesSession",
            !loginAlice.sessionId().equals(sameUser.sessionId()));

        Flow old = app.initiate(sameUser.sessionId(), IDP_A, true, NOW);
        expect("stateTamperingRejected", !app.finish(
            sameUser.sessionId(), old.state() + "x",
            app.token(old, IDP_A, "alice"), NOW.plusSeconds(2)).accepted());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 LoginCsrfSessionDemo.java
java LoginCsrfSessionDemo
~~~

**Stdout chính xác sau khi biên dịch/chạy:**

~~~text
startRequiresUserIntent=true
legitimateLoginAccepted=true
sessionRotated=true
oldSessionRejected=true
replayedStateRejected=true
unsolicitedCallbackRejected=true
missingStateRejected=true
crossBrowserStateRejected=true
crossBrowserAttemptDoesNotConsumeOwnerFlow=true
issuerMixupRejected=true
invalidTokenProofRejected=true
nonceMismatchRejected=true
audienceMismatchRejected=true
expiredStateRejected=true
silentAccountSwitchRejected=true
existingAccountUnchanged=true
sameAccountReauthenticationAccepted=true
reauthenticationRotatesSession=true
stateTamperingRejected=true
~~~

Giải thích quan trọng:

- **startRequiresUserIntent=true:** mô hình chỉ cho khởi tạo flow sau khi điều kiện chủ ý người dùng được kiểm. Production cần thực hiện kiểm đó bằng CSRF/confirmation thật.
- **sessionRotated=true** và **oldSessionRejected=true:** không nâng lại pre-session ID thành authenticated session.
- **replayedStateRejected=true**, **unsolicitedCallbackRejected=true** và **missingStateRejected=true:** không dùng callback không có transaction hoặc đã được dùng.
- **crossBrowserStateRejected=true**: state browser B không thể dùng để đăng nhập browser C. Test tiếp theo cho biết B vẫn có thể hoàn tất flow hợp lệ.
- **issuerMixupRejected=true**, **nonceMismatchRejected=true**, **audienceMismatchRejected=true**: mỗi loại binding được kiểm độc lập.
- **silentAccountSwitchRejected=true**: callback Mallory không tự thay session Alice.
- **sameAccountReauthenticationAccepted=true** và **reauthenticationRotatesSession=true**: reauth cùng subject được cho phép nhưng có session mới.
- **stateTamperingRejected=true**: giá trị state bị sửa không xác thực được.

**Không dùng demo như security middleware**. Nó không thực hiện OAuth code exchange, PKCE, TLS, JWT signature verification, SAML XML validation, browser cookies, session cleanup cluster, atomic state store hay phân quyền thực.

## 15. Spring MockMvc / integration testing strategy

Kiểm thử **form**:

~~~java
// Fragment test Spring Security Test; cần MockMvc + static imports.
mockMvc.perform(post("/login")
    .param("username", "mallory")
    .param("password", "example-password"))
  .andExpect(status().isForbidden());

mockMvc.perform(post("/login").with(csrf())
    .param("username", "alice")
    .param("password", "example-password"));
// Có CSRF hợp lệ chưa có nghĩa login thành công:
// AuthenticationProvider còn phải xác thực credentials thật.
~~~

Kiểm thử **callback OAuth** không có pending flow:

~~~http
GET /login/oauth2/code/corp?code=attacker-code&state=made-up HTTP/1.1
Cookie: JSESSIONID=pre-session-without-authorization-request
~~~

Kỳ vọng: **không tạo Authentication**, không link account, không gọi token endpoint sai issuer. Status có thể là 302 về login error page hoặc 401 tùy failure handler, nên **đừng chỉ assert status**.

Kiểm thử **cross-browser**:

~~~text
Browser A tạo pending state A1.
Browser B có HttpSession khác.
B gọi callback code=...&state=A1.

Expected:
  Reject B, không tạo session dưới user A ở B.
  A có policy rõ xử lý transaction A1.
~~~

Kiểm thử **account switch**:

~~~text
Browser có session Alice.
Callback hợp lệ về mặt IdP cho Mallory đến.
Không có approved account-switch transaction.

Expected:
  Alice không bị thay bằng Mallory.
  SavedRequest/cart/roles/tenant cache của Alice không dùng cho Mallory.
  Nếu cho switch, phải qua confirmation/reauth và fresh session.
~~~

Kiểm thử **SAML ACS** cần mock response/assertion đã ký trong test environment hoặc IdP test, không dùng XML string chưa được ký rồi đánh dấu authenticated.

## 16. Ma trận negative tests

| Test | Đầu vào | Kỳ vọng |
| --- | --- | --- |
| Form login không CSRF | POST /login + credentials của attacker | 403/deny, không auth |
| Form token sai | Token của browser B dùng ở A | Deny |
| Pre-session reuse | Session ID trước login vẫn dùng sau | Deny nếu policy yêu cầu fresh ID |
| Form token hợp lệ + password sai | `_csrf` đúng nhưng credentials sai | Không authenticated |
| OIDC callback thiếu state | Có code, không state | Deny |
| OIDC callback state rỗng | `state=` | Deny |
| State không có pending | State do attacker bịa | Deny |
| State của browser khác | B lấy state A | Deny |
| State replay | Callback đã thành công lần trước | Deny |
| State hết hạn | Authorization request quá TTL | Deny |
| State duplicate | `state=A&state=B` | Deny ambiguity |
| Code duplicate | `code=A&code=B` | Deny ambiguity |
| Issuer mix-up | Request IdP A, response B | Deny trước code exchange sai |
| OIDC nonce sai | ID Token nonce khác transaction | Deny |
| ID Token signature invalid | Forged token | Deny |
| ID Token expired | `exp` đã quá hạn | Deny |
| Wrong audience | ID Token aud khác client | Deny |
| PKCE verifier mismatch | Code/challenge không khớp | Token exchange fail |
| PKCE downgrade | AS không enforce theo client assumption | Deny/mitigate theo RFC9700 |
| Wrong redirect URI | Client URI không đăng ký | Deny |
| Open redirect | Login returnUrl external | Deny |
| Unsolicited OAuth callback | Không có transaction | Deny |
| Cross-site forced login initiation | Attacker dẫn browser vào start GET | Không mặc nhiên là approved account switch/link |
| Current user Alice, callback Mallory | Không có intent switch | Không replace Alice |
| Same email, different issuer | Email trùng nhưng `iss/sub` khác | Không merge accounts |
| Account linking injection | Link IdP B từ attacker callback | Không link nếu thiếu approval transaction |
| SAML SP-init InResponseTo mismatch | Wrong AuthnRequest ID | Deny |
| SAML SP-init missing request | Không có pending request | Deny nếu chỉ SP-init |
| SAML issuer/cert wrong | Chữ ký từ IdP không được tin | Deny |
| SAML audience/destination wrong | Assertion cho SP khác | Deny |
| SAML replay | Response/Assertion ID đã dùng | Deny |
| SAML expired conditions | NotOnOrAfter quá hạn | Deny |
| IdP-init SAML mở ngoài ý muốn | IdP lạ gửi unsolicited response | Deny |
| IdP-init user switch | Signed response của Bob khi session Alice | Không silent switch |
| SAML RelayState external URL | Return URL attacker | Deny/open-redirect protection |
| CAS ticket wrong service | ST phát cho app khác | CAS validation fail |
| CAS ST reuse | Ticket đã tiêu thụ | CAS validation fail |
| SPNEGO account switch | OS user khác app session | Không giữ roles của principal cũ |
| Proxy missing identity header | Local JSESSIONID cũ còn | Fail closed nếu contract yêu cầu header |
| Proxy header mới Bob | Local session Alice | Invalidate/switch policy |
| User local disabled | Token IdP còn hợp lệ | Deny local user |
| Roles revoked | Session cũ vẫn giữ ROLE_ADMIN | Refresh/invalidate by policy |
| SAML SameSite Lax POST | Cookie pre-session không gửi | Fail closed; sửa cookie/correlation |
| OAuth Strict cookie | Callback GET mất pre-session | Fail closed, không bỏ state |
| Multi-tab overwrite | Pending state A bị B ghi đè | Reject không trộn flow |
| Multi-node replay | State tồn tại ở hai nodes | Atomic one-time consume |
| Pending flow sau logout | Callback cũ sau logout | Reject theo policy |
| Cookie session fixation | ID bị dự đoán/ấn định | New session ID và old invalidation |
| Log lộ code/state | Proxy ghi full callback URL | Redact, incident response |

**Test phải kiểm principal/account/session/roles và dữ liệu thực nhận**, không chỉ HTTP status. Một callback lỗi có thể trả 302 về login page và vẫn an toàn nếu **không thay Authentication**.

## 17. Troubleshooting

| Triệu chứng | Khả năng | Cách kiểm |
| --- | --- | --- |
| POST /login 403 | CSRF token thiếu/sai pre-session | Login view, CsrfTokenRepository, cookie |
| OIDC về callback nhưng fail | State/pending authorization request không tìm được | HttpSessionOAuth2AuthorizationRequestRepository |
| OAuth chỉ fail khi SameSite Strict | RP cookie không về trong redirect | Cookie Path/SameSite, browser network trace |
| SAML ACS POST mất request | SameSite=Lax chặn cross-site POST | Cookie profile và SAML AuthnRequest repository |
| OIDC wrong nonce | Transaction bị ghi đè/mix-up | Per-flow nonce, multiple tabs |
| User bị thay sau callback | No account-switch policy | Current authenticated principal vs verified new |
| OIDC callback nhắm sai token endpoint | Provider/issuer mix-up | RFC9207 iss, expected issuer, registrations |
| SAML IdP-init vào app không chủ ý | Unsolicited allowed rộng | IdP registration, SP-init policy |
| SAML Response signed nhưng bị reject | InResponseTo/audience/recipient mismatch | AuthnRequest, assertion, clock |
| OIDC/SAML flow fail khi nhiều tabs | Single pending flow hoặc browser binding sai | Per-state store, concurrent flows |
| Đăng nhập xong còn giỏ hàng user trước | Session data migrated | newSession/invalidation/business state cleanup |
| Login xong vẫn session ID cũ | Custom auth bypass fixation strategy | SessionAuthenticationStrategy |
| Session tự login lại sau local logout | IdP SSO session vẫn active | Upstream logout vs local |
| Request sau custom login anonymous | Context chưa được save | SecurityContextRepository |
| Multi-node callbacks khác kết quả | State store local, cache/sticky sessions | Redis/JDBC atomicity/binding |
| Error open redirect | Return URL không allowlist | SavedRequest/redirect config |
| Log lộ state/code/nonce | APM/proxy logging raw query | Redact sensitive auth parameters |

### 17.1. Runbook

1. Phân loại flow: form, OAuth/OIDC, SAML SP-init/IdP-init, CAS, SPNEGO hay proxy.
2. Xác định browser trước callback có local session Alice/Bob hay anonymous.
3. Tìm pending transaction bằng **internal correlation reference**, không lấy raw state/token từ production log.
4. Kiểm client/issuer/binding/TTL/one-time consume, nonce/PKCE hoặc SAML InResponseTo.
5. Kiểm chữ ký, audience, recipient, time và replay của giao thức.
6. Kiểm account-switch user intent, local user/tenant mapping và authority revocation.
7. Kiểm session ID trước/sau login, saved request, pre-session attrs và old session invalidation.
8. Kiểm cookie Secure/HttpOnly/SameSite/Path, TLS termination, multiple tabs và multi-node.
9. Audit logs không để lộ credentials; log reason codes, correlation, provider/policy version.
10. Vá lỗi bằng integration tests; không tắt CSRF/state/InResponseTo để hết lỗi.

## 18. Quy trình thiết kế production

1. Inventory mọi login entrypoints: `/login`, `/oauth2/authorization/*`, `/login/oauth2/code/*`, `/saml2/authenticate/*`, ACS, CAS callback, proxy identity, account-link/switch.
2. Xác định flow nào yêu cầu explicit user intent, flow nào có thể IdP-init/automatic SSO và risk acceptance.
3. Thiết kế pending login transaction theo protocol: state/nonce/PKCE hoặc AuthnRequest ID, issuer, client, browser binding, TTL.
4. Cấu hình framework repository an toàn, nếu dùng distributed cache phải có atomic consume và session binding.
5. Bật protocol validation issuer/signature/audience/recipient/timestamps/replay.
6. Với nhiều IdPs, bảo vệ mix-up và không gửi code sang token endpoint bị attacker điều khiển.
7. Tách unauthenticated pre-session khỏi authenticated session, fixation protection + xóa stale business state.
8. Định nghĩa account-switch confirmation/reauth/account linking riêng, không cho login response ngẫu nhiên ghi đè user.
9. Dùng identity key ổn định issuer+tenant+subject, local user policy, không hợp nhất qua email.
10. Cấu hình HTTPS, cookies, SameSite theo OIDC GET/SAML POST, CSRF trên form/business actions và redirect allowlist.
11. Test multi-tab/multi-node, replay, cross-browser callback, wrong issuer, wrong account và stale session.
12. Monitoring, log redaction và runbook session revocation/data repair nếu login CSRF được phát hiện.

## 19. Checklist bảo mật

- [ ] CSRF protection cho login POST và logout POST hoạt động đúng.
- [ ] Pre-session CSRF token gắn browser; authenticated session có ID mới và clean user data.
- [ ] Callback OIDC không có pending authorization request phải bị từ chối.
- [ ] `state` ngẫu nhiên, có TTL, chỉ dùng một lần, gắn session/browser; kiểm duplicate parameters.
- [ ] OIDC nonce và PKCE được dùng/kiểm đúng profile và RFC 9700.
- [ ] Multiple providers có issuer mix-up defense trước khi exchange code.
- [ ] ID Token signature, issuer, audience, exp, nonce và required claims được validate.
- [ ] Không dùng token endpoint/client registration/redirectUri chọn từ query chưa xác minh.
- [ ] Login start GET không tự là user intent để link/switch account.
- [ ] SAML SP-init có AuthnRequest repository, InResponseTo correlation và browser binding.
- [ ] SAML assertion signature, issuer, audience, recipient, destination, conditions và replay được kiểm.
- [ ] IdP-initiated SAML chỉ mở theo policy, không silently replace current user.
- [ ] RelayState/returnUrl không tạo open redirect hoặc tự chứng minh SP-init.
- [ ] CAS Service Ticket đúng service, không reuse; app vẫn xét login/session policy.
- [ ] SPNEGO/proxy identity changes không giữ principal/roles cũ.
- [ ] Current user Alice không bị Mallory callback tự thay nếu không có consent/reauth.
- [ ] Account linking có transaction, CSRF, reauthentication và trusted identity binding.
- [ ] Local identity key gắn issuer/tenant/stable subject, không chỉ email.
- [ ] Spring SecurityContextRepository/session persistence và invalidation đúng version.
- [ ] Session fixation protection không bị vô hiệu hóa; attrs user cũ không được migrate.
- [ ] Cookies Secure/HttpOnly/SameSite và SAML cross-site POST/OIDC GET callback được test.
- [ ] Multiple tabs/providers/nodes xử lý đồng thời không trộn states.
- [ ] Login/logout/response error không tạo session authenticated trái policy.
- [ ] Logs không chứa state, nonce, code, code_verifier, tokens, assertions, ticket, cookies/password.
- [ ] Regression test đầy đủ login CSRF, response injection, unsolicited SAML, AS mix-up, silent switch, state replay, cross-browser và open redirect.
- [ ] Có cảnh báo login anomalies, session revocation và incident handling.

## 20. Câu hỏi tự kiểm tra

**1. Login CSRF khác chiếm tài khoản nạn nhân thế nào?**

Login CSRF có thể ép **nạn nhân sử dụng tài khoản attacker**, rồi tự đưa dữ liệu vào tài khoản đó. Attacker không cần biết password nạn nhân.

**2. Vì sao login form cần CSRF token dù user chưa authenticated?**

Vì một website khác vẫn có thể ép browser gửi POST credentials của attacker. Pre-session/CSRF token ngăn POST không thuộc browser hợp lệ.

**3. Một `state` ngẫu nhiên trên global cache đã đủ bảo vệ chưa?**

Không nếu không có **browser/session binding**. Response/state của browser attacker có thể được mang sang browser khác và lookup bằng state.

**4. OAuth `state` có chứng minh người dùng chủ ý đăng nhập không?**

Không nhất thiết. Một website có thể dẫn browser đến start GET, RP tạo state hợp lệ. Account switching/linking cần explicit intent/confirmation.

**5. PKCE có thể bảo vệ CSRF không?**

Có theo điều kiện **RFC 9700**, đặc biệt phải bảo đảm AS support/enforce PKCE; không mặc nhiên đúng khi AS bị downgrade.

**6. OIDC nonce khác state thế nào?**

Nonce gắn request với ID Token và được kiểm trong `nonce` claim; state gắn authorization response với browser authorization request.

**7. Vì sao cần kiểm issuer trước token exchange khi nhiều AS?**

Để tránh **mix-up**, ngăn RP gửi code/credentials tới token endpoint sai theo một response bị trộn.

**8. `InResponseTo` trong SAML dùng làm gì?**

Liên kết SAML Response/SubjectConfirmation với AuthnRequest SP đã tạo, giúp xác định response thuộc flow nào.

**9. IdP-initiated SAML có luôn bị cấm không?**

Không. Nhưng thiếu SP AuthnRequest và có rủi ro unsolicited login, nên chỉ cho phép theo chính sách và kiểm chặt.

**10. Một assertion SAML có chữ ký đúng đã đủ đăng nhập chưa?**

Chưa. Cần issuer, audience, recipient, conditions, replay, SP-init correlation hoặc unsolicited policy, local account/session consent.

**11. `SameSite=Lax` gây vấn đề gì cho SAML ACS?**

Browser thường không gửi session cookie trong cross-site POST từ IdP, làm SP mất AuthnRequest đã lưu; không được “sửa” bằng bỏ correlation.

**12. Session fixation khác session swapping?**

Fixation liên quan đến session **ID attacker biết**; swapping liên quan đến **identity/account** bất ngờ. Rotate ID không tự bảo đảm đúng user.

**13. Nếu đang là Alice và callback Mallory hợp lệ đến thì sao?**

Theo policy an toàn mặc định, **không thay Alice âm thầm**. Yêu cầu approved switch và phiên mới sạch hoặc reject.

**14. Vì sao local logout xong user có thể SSO lại?**

Vì IdP session còn, cho một lần login mới. Local session và upstream SSO session có lifecycle riêng.

**15. Có thể link account dựa vào email trùng không?**

Không tự động. Dùng stable issuer+subject/tenant và explicit account linking consent/reauth.

**16. Chỉ kiểm HTTP status ở test callback có đủ không?**

Không. Cần assert principal/session/roles/account linkage và downstream token exchange/issuer; thất bại có thể được redirect 302 đúng.

## 21. Nguồn tham khảo

- OWASP **CSRF Prevention Cheat Sheet**, login forms và pre-session: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- OWASP **Session Management Cheat Sheet**, session fixation/rotation/logout: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP **Authentication Cheat Sheet**: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- Spring Security **CSRF for Servlet**, bảo vệ login/logout: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security **OAuth2 Login Advanced Configuration**, authorization request repository và callback URLs: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- Spring Security **SAML 2.0 AuthnRequests**, HttpSession/Cache request repository và login fixation warning: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security **Session Management**, fixation/newSession/explicit save: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- IETF **RFC 9700 — OAuth 2.0 Security BCP**, state, PKCE, nonce, issuer mix-up, redirect URI: https://www.rfc-editor.org/rfc/rfc9700
- IETF **RFC 9207 — OAuth Authorization Server Issuer Identification**: https://www.rfc-editor.org/rfc/rfc9207
- IETF **RFC 7636 — PKCE**: https://www.rfc-editor.org/rfc/rfc7636
- OpenID Connect **Core 1.0**, nonce, issuer/audience và ID Token validation: https://openid.net/specs/openid-connect-core-1_0.html
- OASIS **SAML 2.0 Core**: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS **SAML 2.0 Profiles**: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
- Spring Security **Servlet Logout**, SecurityContext/session cleanup: https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html

**Ghi nhớ:** **Login CSRF** có thể khiến người dùng **bị đăng nhập vào tài khoản attacker** mà không hề lộ password. Với Spring Security federation, phải tách **CSRF token của form**, **giao dịch redirect SSO được correlation với browser** (`state`/PKCE/nonce hoặc SAML `InResponseTo`), **đúng IdP/issuer**, **kiểm chữ ký và claims**, **account-switch policy** và **session fixation/rotation**. Nếu callback unsolicited, state không có, sai browser, replay, issuer sai, assertion thiếu tương quan cần thiết hoặc cố thay identity ngoài ý muốn: **fail closed**, không tạo authenticated session và không giữ authority/data của tài khoản cũ lẫn sang tài khoản mới.