# 29.10. Kiểm thử success handler, failure handler và saved request

## 1. Bài toán: đăng nhập OIDC thành công nhưng người dùng bị đưa sai trang

Một cổng thông tin dùng **Spring Security OAuth 2.0/OIDC Client trên Servlet stack**. Khi chưa đăng nhập, người dùng mở:

~~~text
GET /reports/quarterly?year=2026
~~~

Spring Security lưu yêu cầu này, redirect tới trang đăng nhập, rồi khởi tạo OAuth2 Authorization Code Flow tại OpenID Provider (OP). Sau khi người dùng xác thực thành công, mong muốn của sản phẩm là đưa họ về đúng báo cáo đã mở.

Nhưng một thay đổi <code>AuthenticationSuccessHandler</code> khiến toàn bộ người dùng luôn về <code>/home</code>. Người khác cố sửa bằng cách đọc <code>next</code> từ query rồi redirect thẳng, tạo nguy cơ **open redirect**. Trong khi đó một test dùng <code>mockMvc.perform(get("/home").with(oidcLogin()))</code> vẫn xanh, làm nhóm phát triển tưởng success handler đã được kiểm tra.

Một vấn đề khác: OP trả lỗi <code>access_denied</code> hoặc callback có state sai. Ứng dụng phải chạy **authentication failure handler**, không được tạo authenticated session, không phản chiếu <code>error_description</code> chưa được kiểm soát và không sử dụng nhầm saved request cũ để đưa user vào trang của tài khoản khác.

Để kiểm thử đúng, cần chia rõ ba thứ:

1. **Authentication success handler** quyết định hành vi sau khi xác thực thành công, đặc biệt redirect.
2. **Authentication failure handler** quyết định hành vi khi xác thực thất bại, ví dụ đưa về trang login với thông báo an toàn.
3. **RequestCache/SavedRequest** ghi nhớ URL người dùng đã cố truy cập **trước khi** được chuyển sang login.

> **Điểm quan trọng:** <code>SecurityMockMvcRequestPostProcessors.oidcLogin()</code> hoặc <code>oauth2Login()</code> gắn một authentication giả lập vào **request đang kiểm thử**. Chúng hữu ích khi kiểm thử authorization của controller nhưng **không chạy Authorization Code callback và không tự gọi OAuth2 Login success/failure handler**.

## 2. Mục tiêu bài học

Sau bài này, bạn có thể:

1. Mô tả vòng đời unauthenticated protected request → request cache → OAuth2 Login → success handler → original URL.
2. Phân biệt <code>SavedRequest</code>, <code>RequestCache</code>, <code>OAuth2AuthorizationRequestRepository</code> và <code>SecurityContext</code>.
3. Sử dụng <code>SavedRequestAwareAuthenticationSuccessHandler</code>, <code>SimpleUrlAuthenticationSuccessHandler</code> và custom success handler có chủ đích.
4. Kiểm thử <code>SimpleUrlAuthenticationFailureHandler</code> hoặc custom <code>AuthenticationFailureHandler</code> không làm rò rỉ thông tin từ OP.
5. Viết unit tests cho handlers bằng <code>MockHttpServletRequest</code>, <code>MockHttpServletResponse</code> và <code>MockHttpSession</code>.
6. Dùng <code>MockMvc</code> để xác minh protected URL được lưu vào <code>HttpSessionRequestCache</code> khi user chưa đăng nhập.
7. Hiểu giới hạn của <code>oauth2Login()</code>, <code>oidcLogin()</code> và cách thiết kế integration test đi qua OAuth2 Login filter thật.
8. Kiểm thử các nhánh: saved request có/không có, default target, always-use-default, target parameter, account switching và logout.
9. Kiểm soát redirect URL, query parameters, state, session fixation, nhiều tab và nhiều instance.
10. Chẩn đoán các lỗi như <code>authorization_request_not_found</code>, redirect loop, stale saved request và HTTP 403 không thuộc success handler.

## 3. Sơ đồ luồng end-to-end

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Browser
    participant R as Reports Controller / Spring MVC
    participant S as Spring Security Filter Chain
    participant C as RequestCache
    participant OP as OpenID Provider

    U->>B: Mở /reports/quarterly?year=2026
    B->>S: GET /reports/quarterly?year=2026
    S->>S: Chưa Authentication hợp lệ
    S->>C: Save original protected request
    S-->>B: Redirect /login
    B->>S: GET /oauth2/authorization/company
    S->>S: Create state/nonce/PKCE; save authorization request
    S-->>B: Redirect OP Authorization Endpoint
    B->>OP: Authorization request
    OP->>U: Authentication/consent
    OP-->>B: Authorization response code + state
    B->>S: GET /login/oauth2/code/company?code=...&state=...
    S->>S: Correlate state, exchange code, validate OIDC identity
    S->>S: Save SecurityContext / authorized client
    S->>C: Lookup original SavedRequest
    S-->>B: SuccessHandler redirects to /reports/quarterly?year=2026
    B->>S: GET /reports/quarterly?year=2026
    S->>R: Authenticated request
    R-->>B: Report response
~~~

Nếu OP từ chối hoặc callback validation thất bại:

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Browser
    participant OP as OpenID Provider
    participant F as OAuth2LoginAuthenticationFilter
    participant H as AuthenticationFailureHandler
    U->>OP: Deny consent
    OP-->>B: Redirect error=access_denied&state=...
    B->>F: GET /login/oauth2/code/company
    F->>F: Xử lý lỗi callback / correlation
    F->>H: AuthenticationException
    H-->>B: Redirect /login?error=oauth2
    Note over B: Không tạo authenticated session mới
~~~

Một ứng dụng nên có **bộ test riêng** cho request cache, success handler, failure handler và giao thức OIDC; không nhầm một mock user đã login với toàn bộ sequence trên.

## 4. Các thành phần cần phân biệt

| Thành phần | Kiểu/implementation thường gặp | Được lưu hoặc thực thi ở đâu? | Mục đích |
|---|---|---|---|
| <code>RequestCache</code> | <code>HttpSessionRequestCache</code> | Spring Security web infrastructure | Lưu protected request ban đầu |
| <code>SavedRequest</code> | <code>DefaultSavedRequest</code> | HTTP session qua RequestCache | Chứa redirect URL và snapshot request phù hợp |
| <code>OAuth2AuthorizationRequestRepository</code> | <code>HttpSessionOAuth2AuthorizationRequestRepository</code> | OAuth2 Login initiation/callback | Lưu authorization request + state/PKCE correlation |
| <code>SecurityContextRepository</code> | Loại phụ thuộc cấu hình/version | Sau authentication | Lưu SecurityContext/Authentication |
| <code>OAuth2AuthorizedClientRepository</code> | Session-backed hoặc custom | Token/authorized-client lifecycle | Lưu access/refresh token của registration/principal |
| <code>AuthenticationSuccessHandler</code> | <code>SavedRequestAwareAuthenticationSuccessHandler</code> | Sau authentication thành công | Điều hướng và xử lý success |
| <code>AuthenticationFailureHandler</code> | <code>SimpleUrlAuthenticationFailureHandler</code> hoặc custom | Authentication failure | Điều hướng và xử lý lỗi |

### 4.1. SavedRequest không phải authorization request

Sau khi truy cập protected URL:

~~~text
HttpSessionRequestCache
    SavedRequest:
       /reports/quarterly?year=2026
~~~

Sau khi bấm Login:

~~~text
HttpSessionOAuth2AuthorizationRequestRepository
    OAuth2AuthorizationRequest:
       clientRegistrationId = company
       state = random-state
       redirectUri = /login/oauth2/code/company
       nonce/PKCE attributes khi áp dụng
~~~

Hai objects có **vòng đời khác nhau**.

- SavedRequest giúp **trở về trang cần xem**.
- AuthorizationRequest giúp **kiểm tra kết quả login có thuộc request OAuth2 ban đầu hay không**.

Không dùng saved URL để thay state. Không dùng state làm return URL trực tiếp, càng không dùng redirect query do browser tự cung cấp thay vì SavedRequest được lưu từ protected request.

### 4.2. SavedRequest không phải SecurityContext

SavedRequest có thể được lưu trước khi user authenticated. Nó **không chứng minh user có quyền** truy cập URL đó. Sau login, khi browser truy cập lại URL, Spring Security **phải đánh giá authorization một lần nữa** với principal vừa được xác thực.

Ví dụ user B sau login không có quyền mở <code>/reports/finance</code>: redirect đến route đó có thể xảy ra, nhưng backend vẫn phải trả 403 nếu B thiếu quyền.

### 4.3. Request cache khác saved-request-aware handler

<code>HttpSessionRequestCache</code> chịu trách nhiệm lưu/tìm request; <code>SavedRequestAwareAuthenticationSuccessHandler</code> chọn target URL phù hợp sau login.

Nếu chỉ cấu hình handler mà không có RequestCache lưu request, handler có thể dùng default target. Nếu chỉ có RequestCache nhưng custom handler luôn redirect <code>/home</code>, saved request không được sử dụng như mong muốn.

## 5. Cơ chế mặc định của Spring Security OAuth2 Login

Spring Security Servlet thường có:

~~~text
ExceptionTranslationFilter
    ↳ xử lý unauthenticated protected request
    ↳ RequestCache.saveRequest(...)
    ↳ AuthenticationEntryPoint → login page / OAuth2 authorization initiation

OAuth2AuthorizationRequestRedirectFilter
    ↳ /oauth2/authorization/{registrationId}
    ↳ tạo request có state và redirect OP

OAuth2LoginAuthenticationFilter
    ↳ /login/oauth2/code/{registrationId}
    ↳ nhận authorization response
    ↳ authentication success / failure

RequestCacheAwareFilter
    ↳ khớp request sau redirect với saved request, theo RequestCache policy
~~~

Đây là sơ đồ vai trò, **không phải mô tả thứ tự tuyệt đối của tất cả filters** trên mọi Spring Security version hoặc SecurityFilterChain.

### 5.1. URL và vai trò

| URL | Ai gọi | Ý nghĩa |
|---|---|---|
| <code>GET /reports/quarterly</code> | Browser | Protected resource; có thể được cache |
| <code>GET /login</code> | Browser | Trang chọn provider nếu ứng dụng tự tạo |
| <code>GET /oauth2/authorization/company</code> | Browser | Initiation cho registration <code>company</code> |
| <code>GET /login/oauth2/code/company</code> | OP redirect qua browser | Callback code + state |
| <code>GET /reports/quarterly</code> sau success | Browser | Request mới đến protected resource |

<code>/oauth2/authorization/company</code> **không phải** URL cần lưu làm original protected request khi user đang xem report. Nếu request cache bị ghi đè bởi login/authorization URLs, người dùng có thể bị redirect loop.

### 5.2. SuccessHandler không thực hiện OIDC validation

Success handler được gọi **sau khi authentication infrastructure đã chấp nhận đăng nhập**. Nó không thay thế:

- Xác minh OAuth2 state.
- Trao đổi code tại đúng Token Endpoint.
- Kiểm tra PKCE/nonce khi áp dụng.
- Kiểm tra chữ ký/issuer/audience/expiration của ID Token.
- Lưu authorized client và SecurityContext theo policy.

Không tự gọi success handler với một Authentication giả rồi tuyên bố đã kiểm thử giao thức OIDC.

## 6. SavedRequestAwareAuthenticationSuccessHandler

Class:

~~~java
org.springframework.security.web.authentication.SavedRequestAwareAuthenticationSuccessHandler
~~~

Đây là handler dựa trên <code>RequestCache</code> để chuyển người dùng về URL họ yêu cầu trước login.

### 6.1. Quy tắc chọn target URL

Các lựa chọn thường thấy:

1. Khi cấu hình **alwaysUseDefaultTargetUrl=true**, handler ưu tiên default target; saved request có thể bị remove.
2. Khi cấu hình **targetUrlParameter** và request có parameter hợp lệ theo handler, target parameter có thể được ưu tiên.
3. Nếu còn <code>SavedRequest</code>, dùng <code>SavedRequest.getRedirectUrl()</code>.
4. Nếu không có saved request/override, dùng default target.

Chi tiết cleanup, matching và redirect strategy phụ thuộc version, nhưng thứ tự ưu tiên trên là điểm cốt lõi cần test.

### 6.2. Cấu hình an toàn

~~~java
import org.springframework.security.web.authentication
    .SavedRequestAwareAuthenticationSuccessHandler;
import org.springframework.security.web.savedrequest.RequestCache;

SavedRequestAwareAuthenticationSuccessHandler handler =
    new SavedRequestAwareAuthenticationSuccessHandler();

handler.setRequestCache(requestCache);
handler.setDefaultTargetUrl("/home");
handler.setAlwaysUseDefaultTargetUrl(false);
~~~

Trong snippet, <code>requestCache</code> là bean hoặc dependency đã được cung cấp.

Khi có SavedRequest:

~~~text
GET /reports/quarterly?year=2026
    ↓
Login success
    ↓
Redirect /reports/quarterly?year=2026
~~~

Khi user mở trực tiếp trang login:

~~~text
GET /login
    ↓
Login success, không có SavedRequest
    ↓
Redirect /home
~~~

### 6.3. Vì sao không nên đặt targetUrlParameter tùy tiện?

Một configuration như:

~~~java
handler.setTargetUrlParameter("next");
~~~

có thể khiến handler xem <code>next</code> từ request là redirect target, tùy cấu hình/version. Nếu browser hoặc attacker kiểm soát một absolute URL không được validate, nguy cơ **open redirect** xuất hiện.

Đừng coi <code>next=https://attacker.example</code> là đích hợp lệ chỉ vì có trong query. Nếu cần returnTo, dùng allowlist internal routes, relative URL validation, transaction state được bảo vệ và kiểm tra authorization sau login.

### 6.4. Khi luôn muốn về /home

~~~java
handler.setAlwaysUseDefaultTargetUrl(true);
handler.setDefaultTargetUrl("/home");
~~~

Policy này hợp lý với một số hệ thống phải đưa user qua dashboard sau login, nhưng **không phù hợp** nếu yêu cầu là resume protected URL. Test phải phản ánh quyết định sản phẩm.

## 7. AuthenticationFailureHandler và các loại lỗi

Interface:

~~~java
org.springframework.security.web.authentication.AuthenticationFailureHandler
~~~

Một implementation thường gặp:

~~~java
org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler
~~~

### 7.1. Failure handler làm gì?

Khi authentication thất bại, handler có thể:

- Redirect về trang login với error marker ổn định.
- Forward hoặc trả HTTP error theo contract.
- Ghi metric/log category đã lọc.
- Dọn thông tin tạm của flow hoặc không, theo policy.
- Tuyệt đối **không tạo authenticated session** từ token chưa được xác minh.

### 7.2. Đừng lộ raw OAuth2Error

OP có thể trả:

~~~text
error=access_denied
error_description=Policy details from OP
error_uri=https://op.example.org/help
~~~

Không đưa thẳng description hoặc URI lên browser:

~~~text
/login?error_description=<untrusted upstream text>
~~~

URL có thể vào browser history, Referer, access logs. Description có thể lộ thông tin policy hoặc trở thành reflected XSS nếu render không encode.

### 7.3. Phân biệt user denied, state mismatch và outage

| Lỗi | Bản chất | Hướng xử lý |
|---|---|---|
| <code>access_denied</code> | User/OP từ chối authorization | Thông báo an toàn, cho chọn lại |
| State mismatch | Callback không gắn được với authorization request | Từ chối, không bỏ state validation |
| <code>invalid_grant</code> code exchange | Code hết hạn/dùng lại, PKCE/redirect sai | Investigate OP integration, không retry code vô hạn |
| ID Token signature/issuer sai | Authentication proof không tin cậy | Fail closed, cảnh báo khi bất thường |
| OP network timeout/5xx | Upstream tạm unavailable | Retry policy bên integration, thông báo trung tính |

Failure handler không nên mapping mọi lỗi thành “User nhập sai mật khẩu”, vì OAuth2 Client không trực tiếp xử lý password của OP.

## 8. Cấu hình ứng dụng Servlet dùng để minh họa

Giả sử Java 17, Spring Boot 3.x, Spring Security 6.x với MVC/Servlet stack. API có thể khác ở 7.x; sử dụng reference của đúng version dự án.

### 8.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Không cần thêm WebFlux chỉ để kiểm thử Servlet OAuth2 Login. Nếu muốn kiểm thử WebClient downstream trong cùng ứng dụng, dependencies/stack sẽ được lựa chọn riêng.

### 8.2. OIDC ClientRegistration

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: portal-web
            client-secret: ${COMPANY_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
        provider:
          company:
            issuer-uri: https://idp.example.org/realms/company
~~~

Trong integration tests, nên dùng OP test/stub có issuer, keys và endpoints riêng; không dùng client secret/ID Token của production. Các URL phía trên minh họa cấu hình, không phải OP thật.

### 8.3. SecurityFilterChain có RequestCache và handlers

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;
import org.springframework.security.web.authentication
    .SavedRequestAwareAuthenticationSuccessHandler;
import org.springframework.security.web.authentication
    .SimpleUrlAuthenticationFailureHandler;
import org.springframework.security.web.savedrequest.HttpSessionRequestCache;
import org.springframework.security.web.savedrequest.RequestCache;

@Configuration
public class WebSecurityConfig {

    @Bean
    RequestCache requestCache() {
        return new HttpSessionRequestCache();
    }

    @Bean
    AuthenticationSuccessHandler oauth2SuccessHandler(
            RequestCache requestCache) {

        var handler = new SavedRequestAwareAuthenticationSuccessHandler();
        handler.setRequestCache(requestCache);
        handler.setDefaultTargetUrl("/home");
        handler.setAlwaysUseDefaultTargetUrl(false);
        return handler;
    }

    @Bean
    AuthenticationFailureHandler oauth2FailureHandler() {
        return new SimpleUrlAuthenticationFailureHandler(
            "/login?error=oauth2");
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            RequestCache requestCache,
            AuthenticationSuccessHandler oauth2SuccessHandler,
            AuthenticationFailureHandler oauth2FailureHandler)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/", "/login", "/home", "/error", "/assets/**")
                    .permitAll()
                .requestMatchers("/reports/**").authenticated()
                .anyRequest().authenticated())
            .requestCache(cache ->
                cache.requestCache(requestCache))
            .oauth2Login(oauth2 -> oauth2
                .loginPage("/login")
                .successHandler(oauth2SuccessHandler)
                .failureHandler(oauth2FailureHandler))
            .csrf(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Lưu ý:** Đây là một SecurityFilterChain minh họa. Nếu bạn dùng nhiều chains, phải bảo đảm protected resource, login initiation và OAuth2 callback đều được xử lý bởi đúng chain. <code>.requestMatchers("/reports/**").authenticated()</code> trong phần authorization **không tương đương** <code>securityMatcher(...)</code> chọn chain.

### 8.4. Trang login và controller mẫu

~~~java
package example.web;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
public class PortalController {

    @GetMapping("/login")
    String login() {
        return "login";
    }

    @GetMapping("/home")
    @ResponseBody
    String home() {
        return "Welcome";
    }

    @GetMapping("/reports/{reportId}")
    @ResponseBody
    String report(
            @PathVariable String reportId,
            @RequestParam(required = false) String year) {
        return "Report " + reportId + ", year=" + year;
    }
}
~~~

Đoạn này giả định có view template <code>login</code> hiển thị:

~~~html
<a href="/oauth2/authorization/company">
  Đăng nhập bằng Company SSO
</a>
~~~

Nếu không dùng template engine, có thể dùng một trang HTML static/controller khác.

## 9. Ba mức kiểm thử nên tách riêng

| Mức | Công cụ | Kiểm thử được | Không tự kiểm thử |
|---|---|---|---|
| **Unit handler** | Mock request/response/session, gọi handler trực tiếp | Redirect target, lỗi, request-cache branch, sanitize | OIDC callback và Token Endpoint |
| **MockMvc filter-chain slice/integration** | MockMvc + Spring Security filters | Unauthenticated request được cache, entry point, session, authorization rules | Không tự chạy OAuth2 callback chỉ vì dùng <code>oidcLogin()</code> |
| **OIDC end-to-end integration** | MockMvc + OP/Token Endpoint test, JWKS/ID Token hợp lệ, session correlation | Authorization initiation, code exchange, state/nonce validation, handler invocation thực | Browser cookies/SameSite nếu chỉ MockMvc |

Không nên dùng một test mức unit để khẳng định toàn bộ luồng OAuth2/OIDC đã đúng. Nhưng cũng không cần khởi chạy OP test chỉ để kiểm tra handler có redirect về SavedRequest hay không.

## 10. Unit test SavedRequestAwareAuthenticationSuccessHandler

Một test handler có thể gọi trực tiếp <code>onAuthenticationSuccess(...)</code> với mock servlet objects. Điều này giúp test redirect logic **không cần OP**.

### 10.1. Chuẩn bị test

~~~java
package example.security;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.web.authentication
    .SavedRequestAwareAuthenticationSuccessHandler;
import org.springframework.security.web.savedrequest
    .HttpSessionRequestCache;
import org.springframework.security.web.savedrequest.SavedRequest;

import static org.junit.jupiter.api.Assertions.*;

class SavedRequestSuccessHandlerTest {

    private HttpSessionRequestCache requestCache;
    private SavedRequestAwareAuthenticationSuccessHandler handler;

    @BeforeEach
    void setUp() {
        requestCache = new HttpSessionRequestCache();
        handler = new SavedRequestAwareAuthenticationSuccessHandler();
        handler.setRequestCache(requestCache);
        handler.setDefaultTargetUrl("/home");
    }

    @Test
    void redirectsToOriginalProtectedUrlWhenSavedRequestExists()
            throws Exception {

        var original = new MockHttpServletRequest(
            "GET", "/reports/quarterly");
        original.setScheme("https");
        original.setServerName("portal.example.org");
        original.setServerPort(443);
        original.setQueryString("year=2026");

        // Giả lập Security filter đã lưu protected request.
        requestCache.saveRequest(
            original, new MockHttpServletResponse());

        SavedRequest saved = requestCache.getRequest(
            original, new MockHttpServletResponse());
        assertNotNull(saved);

        var callback = new MockHttpServletRequest(
            "GET", "/login/oauth2/code/company");
        callback.setSession(
            (MockHttpSession) original.getSession(false));
        var response = new MockHttpServletResponse();

        var authenticated = new TestingAuthenticationToken(
            "alice", "ignored", "ROLE_USER");

        handler.onAuthenticationSuccess(
            callback, response, authenticated);

        assertEquals(
            saved.getRedirectUrl(),
            response.getRedirectedUrl());
        assertEquals(302, response.getStatus());
        assertTrue(
            response.getRedirectedUrl()
                .contains("/reports/quarterly"));
        assertTrue(
            response.getRedirectedUrl()
                .contains("year=2026"));
    }
}
~~~

Trong test:

- <code>original</code> mô phỏng GET trước khi login.
- <code>HttpSessionRequestCache</code> lưu protected request.
- <code>callback</code> dùng **cùng MockHttpSession**, để success handler tìm thấy SavedRequest.
- <code>TestingAuthenticationToken</code> chỉ là một authenticated object đủ cho **unit test redirect handler**; test không nói OIDC signature/nonce đã được validate.
- So sánh với <code>SavedRequest.getRedirectUrl()</code> thay vì hardcode scheme/port/query encoding do implementation có thể chuẩn hóa URL.

### 10.2. Vì sao callback phải dùng cùng session?

Nếu <code>callback</code> không chia sẻ session của <code>original</code>:

~~~text
Original request → SavedRequest trong session S1
Callback request → session S2 hoặc không có session
SuccessHandler → không tìm thấy SavedRequest
Redirect → /home
~~~

Trong production, cookie path/domain/SameSite, Spring Session, load balancer và session fixation protection có thể ảnh hưởng correlation. Khi unit test, chúng ta cố ý truyền cùng session để cô lập redirect logic.

### 10.3. Với request không có saved request

Thêm test:

~~~java
@Test
void fallsBackToHomeWithoutSavedRequest() throws Exception {
    var request = new MockHttpServletRequest(
        "GET", "/login/oauth2/code/company");
    var response = new MockHttpServletResponse();
    var authenticated = new TestingAuthenticationToken(
        "alice", "ignored", "ROLE_USER");

    handler.onAuthenticationSuccess(
        request, response, authenticated);

    assertEquals("/home", response.getRedirectedUrl());
}
~~~

Điều này mô phỏng user mở trực tiếp trang đăng nhập, không có protected URL được lưu trước đó.

### 10.4. Kiểm tra alwaysUseDefaultTargetUrl

~~~java
@Test
void alwaysUseDefaultTargetOverridesSavedRequest()
        throws Exception {

    handler.setAlwaysUseDefaultTargetUrl(true);

    var original = new MockHttpServletRequest(
        "GET", "/reports/quarterly");
    requestCache.saveRequest(
        original, new MockHttpServletResponse());

    var callback = new MockHttpServletRequest(
        "GET", "/login/oauth2/code/company");
    callback.setSession(
        (MockHttpSession) original.getSession(false));

    var response = new MockHttpServletResponse();
    handler.onAuthenticationSuccess(
        callback,
        response,
        new TestingAuthenticationToken(
            "alice", "ignored", "ROLE_USER"));

    assertEquals("/home", response.getRedirectedUrl());
    assertNull(requestCache.getRequest(
        callback, new MockHttpServletResponse()));
}
~~~

Test này cần phản ánh behavior của Spring Security version thực tế. <code>SavedRequestAwareAuthenticationSuccessHandler</code> có logic xóa saved request khi always-default branch được chọn.

### 10.5. SavedRequest có được xóa ngay trong mọi nhánh?

Không khẳng định rằng <code>SavedRequest</code> luôn biến mất ngay sau khi success handler redirect. Trong saved-request branch, implementation có thể giữ request cho lượt GET tiếp theo để <code>RequestCacheAwareFilter</code>/<code>RequestCache.getMatchingRequest</code> tái tạo hoặc loại bỏ theo cơ chế đã cấu hình.

Vì vậy test đúng nên quan tâm:

- Target URL được chọn.
- Request tiếp theo được xử lý dưới Authentication mới.
- SavedRequest không bị dùng lại nhiều lần ngoài policy.

Không chỉ assert session attribute đã bị xóa ngay ở thời điểm gọi success handler rồi coi đó là contract áp dụng mọi version.

## 11. Unit test AuthenticationFailureHandler

### 11.1. SimpleUrlAuthenticationFailureHandler

~~~java
package example.security;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.web.authentication
    .SimpleUrlAuthenticationFailureHandler;

import static org.junit.jupiter.api.Assertions.*;

class OAuth2FailureHandlerTest {

    @Test
    void redirectsToFixedLocalLoginErrorUrl() throws Exception {
        var handler = new SimpleUrlAuthenticationFailureHandler(
            "/login?error=oauth2");

        var request = new MockHttpServletRequest(
            "GET", "/login/oauth2/code/company");
        var response = new MockHttpServletResponse();
        var failure = new OAuth2AuthenticationException(
            new OAuth2Error(
                "access_denied",
                "Sensitive upstream explanation",
                "https://other.example/help"));

        handler.onAuthenticationFailure(
            request, response, failure);

        assertEquals(
            "/login?error=oauth2",
            response.getRedirectedUrl());
        assertEquals(302, response.getStatus());
        assertFalse(
            response.getRedirectedUrl()
                .contains("Sensitive"));
        assertFalse(
            response.getRedirectedUrl()
                .contains("other.example"));
    }
}
~~~

Test tập trung vào **redirect URL**, không có nghĩa exception object không còn được lưu trong session. <code>SimpleUrlAuthenticationFailureHandler</code> có thể lưu exception trong session theo implementation/configuration để view sử dụng; trang lỗi **không được hiển thị nguyên văn** message/description chưa qua policy lọc.

### 11.2. Vì sao không test bằng “có 302 là đủ”?

Một redirect tới:

~~~text
https://attacker.example/capture?message=<raw idp error>
~~~

cũng trả 302, nhưng không an toàn.

Nên assert:

1. Đích redirect nằm trong domain/route nội bộ được phép.
2. Có error marker đã giới hạn.
3. Không có raw upstream description/URI.
4. Không có authorization code, access/refresh tokens hoặc session cookie.
5. Không biến failure thành Authentication thành công.

### 11.3. Custom failure handler theo error code

~~~java
package example.security;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;

public final class SafeOidcFailureHandler
        implements AuthenticationFailureHandler {

    private static final Logger log =
        LoggerFactory.getLogger(SafeOidcFailureHandler.class);

    @Override
    public void onAuthenticationFailure(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception) throws IOException {

        String category = "login_failed";

        if (exception instanceof OAuth2AuthenticationException oauth2) {
            String code = oauth2.getError().getErrorCode();
            if ("access_denied".equals(code)) {
                category = "user_denied";
            } else if ("invalid_grant".equals(code)) {
                category = "grant_rejected";
            }
        }

        // Đưa category đã giới hạn vào telemetry, không dùng raw error.
        log.warn("oidc_login_failed category={}", category);

        response.sendRedirect(
            request.getContextPath() + "/login?error=oauth2");
    }
}
~~~

Đây là **phương án thay thế** cho <code>SimpleUrlAuthenticationFailureHandler</code> ở cấu hình mục 8.3. Không khai báo hai failure handlers cạnh tranh cho cùng một chain rồi kỳ vọng chúng tự chạy nối tiếp.

## 12. Unit test success handler có logging/audit

Khi cần custom logic như ghi event “Login thành công”, không nên xóa behavior SavedRequest bằng cách luôn redirect cứng.

### 12.1. Decorator pattern

~~~java
package example.security;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;

import org.springframework.security.core.Authentication;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;

public final class AuditingSuccessHandler
        implements AuthenticationSuccessHandler {

    private final AuthenticationSuccessHandler delegate;
    private final LoginAudit audit;

    public AuditingSuccessHandler(
            AuthenticationSuccessHandler delegate,
            LoginAudit audit) {
        this.delegate = delegate;
        this.audit = audit;
    }

    @Override
    public void onAuthenticationSuccess(
            HttpServletRequest request,
            HttpServletResponse response,
            Authentication authentication) throws IOException {

        audit.recordSuccessfulLogin(authentication);
        delegate.onAuthenticationSuccess(
            request, response, authentication);
    }
}
~~~

<code>LoginAudit</code> là **interface ứng dụng tự định nghĩa** (ví dụ <code>void recordSuccessfulLogin(Authentication authentication)</code>), không phải class built-in của Spring Security.

Nếu audit thất bại, cần quyết định rõ có fail login hay không; đừng để một network call telemetry dài không timeout làm login treo. Audit không nên log raw ID Token, access/refresh tokens hoặc toàn bộ OIDC claims.

### 12.2. Test delegate được gọi

~~~java
import static org.mockito.Mockito.*;

@Test
void auditThenDelegateSuccess() throws Exception {
    AuthenticationSuccessHandler delegate =
        mock(AuthenticationSuccessHandler.class);
    LoginAudit audit = mock(LoginAudit.class);

    var handler = new AuditingSuccessHandler(delegate, audit);
    var request = new MockHttpServletRequest();
    var response = new MockHttpServletResponse();
    var auth = new TestingAuthenticationToken(
        "alice", "ignored", "ROLE_USER");

    handler.onAuthenticationSuccess(request, response, auth);

    var order = inOrder(audit, delegate);
    order.verify(audit).recordSuccessfulLogin(auth);
    order.verify(delegate).onAuthenticationSuccess(
        request, response, auth);
}
~~~

Test trên kiểm tra thứ tự gọi trong decorator, **không phải test OIDC flow**. Kết hợp với SavedRequestAware handler test để đảm bảo redirect không bị thay đổi.

## 13. MockMvc: kiểm tra unauthenticated request được lưu

Mục tiêu của test này: khi user chưa login gọi protected URL, Spring Security lưu original request để success handler có thể dùng sau đó.

### 13.1. @SpringBootTest + @AutoConfigureMockMvc

Giả sử application có cấu hình ở mục 8:

~~~java
package example.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet
    .AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.web.savedrequest.RequestCache;
import org.springframework.security.web.savedrequest.SavedRequest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ProtectedRequestCacheIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    RequestCache requestCache;

    @Test
    void unauthenticatedRequestIsSavedForLaterLogin() throws Exception {
        MvcResult result = mockMvc.perform(
                get("/reports/quarterly")
                    .queryParam("year", "2026"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        var session = (MockHttpSession)
            result.getRequest().getSession(false);
        assertNotNull(session);

        SavedRequest saved = requestCache.getRequest(
            result.getRequest(),
            result.getResponse());

        assertNotNull(saved);
        assertTrue(saved.getRedirectUrl()
            .contains("/reports/quarterly"));
        assertTrue(saved.getRedirectUrl()
            .contains("year=2026"));
    }
}
~~~

**Điều kiện:** Application test context phải có ClientRegistrationRepository hợp lệ hoặc cấu hình OP test phù hợp để khởi tạo OAuth2 Login; nhưng test **không cần gọi Token Endpoint**, vì nó chỉ kiểm tra protected URL được lưu trước authorization flow.

### 13.2. Vì sao phải bật Spring Security filters?

MockMvc có thể chạy không kèm filter chain nếu cấu hình test cố ý tắt filters, ví dụ:

~~~java
@AutoConfigureMockMvc(addFilters = false)
~~~

Khi đó test controller có thể trả 200 hoặc tự redirect nhưng không chạy <code>ExceptionTranslationFilter</code> và <code>RequestCache</code>. Không dùng kiểu test đó để tuyên bố đã kiểm tra saved request của Spring Security.

### 13.3. @WebMvcTest có đủ không?

<code>@WebMvcTest</code> là slice tập trung vào MVC components. Nó có thể không tự mang đầy đủ ClientRegistrationRepository, security beans và token clients như production.

Có thể dùng <code>@WebMvcTest</code> với <code>@Import(TestSecurityConfig.class)</code> và test registration cụ thể để giữ scope nhỏ, nhưng phải **bảo đảm chain và RequestCache thật được load**.

Không dùng <code>@WithMockUser</code> hoặc <code>.with(oidcLogin())</code> trong test protected request này, vì mục tiêu là kiểm tra hành vi khi **chưa authenticated**.

## 14. Vì sao oidcLogin() không test success handler?

Ví dụ:

~~~java
mockMvc.perform(get("/reports/quarterly")
        .with(oidcLogin()))
    .andExpect(status().isOk());
~~~

Với import:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oidcLogin;
~~~

Test này phù hợp để xác minh một route nhận principal OIDC giả, Spring Security authorization policy hoặc controller có thể dùng OIDC claims.

Nhưng nó **không chạy**:

~~~text
/oauth2/authorization/company
  → OP Authorization Endpoint
  → /login/oauth2/code/company?code=...&state=...
  → OAuth2LoginAuthenticationFilter
  → successHandler.onAuthenticationSuccess(...)
~~~

<code>oidcLogin()</code> chỉ chuẩn bị request test với authentication tương ứng. Không có callback và không có filter authentication success event theo flow thật.

### 14.1. oauth2Login() cũng có giới hạn tương tự

~~~java
mockMvc.perform(get("/reports/quarterly")
        .with(oauth2Login()))
    .andExpect(status().isOk());
~~~

Test này cũng **không chứng minh** saved-request-aware redirect đã chạy. Nó chỉ đưa OAuth2AuthenticationToken vào context cho request.

### 14.2. Chọn test đúng mục đích

| Câu hỏi kiểm thử | Nên dùng |
|---|---|
 Controller nhận <code>OidcUser</code> chưa? | <code>oidcLogin()</code> |
 Authorization yêu cầu role/scope có đúng không? | <code>oidcLogin()</code>/<code>oauth2Login()</code> với authorities phù hợp |
 Success handler chọn SavedRequest hay /home? | Gọi handler trực tiếp bằng mock request/session |
 Protected URL được RequestCache lưu? | MockMvc unauthenticated + security filters |
 Callback code/state tạo authenticated session và gọi success handler? | Integration test với OP/Token Endpoint stub |
 OP lỗi access_denied dẫn tới failure handler? | Unit handler + integration callback error |

## 15. Integration test OAuth2 callback thật cần chuẩn bị gì?

Muốn chứng minh Spring Security thật sự gọi success/failure handler sau OAuth2/OIDC Login, cần request đi qua <code>OAuth2LoginAuthenticationFilter</code> và authentication provider.

### 15.1. Các thành phần cần mô phỏng

1. <code>ClientRegistration</code> có issuer, Client ID, authorization/token/JWK endpoints test.
2. Browser session/cookie và saved request đã tạo trước login.
3. <code>OAuth2AuthorizationRequestRepository</code> chứa request với state, redirect URI và PKCE verifier/nonce khi áp dụng.
4. OP test trả authorization response <code>code</code> và <code>state</code>.
5. Token Endpoint test trả access token và ID Token hợp lệ theo đúng client registration.
6. JWK Set test cho phép Spring Security verify chữ ký ID Token.
7. <code>OidcUser</code> được tạo sau validation.
8. Success handler/failure handler được inject thật, có thể là spy.

Không cần dùng production OP. Có thể dùng **WireMock**, **MockWebServer**, test container/mock authorization server hoặc một OP sandbox có thể điều khiển. Điều quan trọng là contract của stub phải khớp flow.

### 15.2. OIDC ID Token test phải hợp lệ

Một JWT tự dựng:

~~~json
{
  "sub": "alice",
  "email": "alice@example.org"
}
~~~

không đủ làm ID Token hợp lệ. Cần ký JWT bằng test key và có claims như:

~~~text
iss = exact test issuer
sub = test subject
aud = test client_id
iat, exp = valid
nonce = expected nonce khi flow yêu cầu
~~~

Ngoài ra response/request phải có state và PKCE/client authentication đúng. Không bỏ signature/issuer/audience/nonce validation để test dễ chạy.

### 15.3. Kiểm tra handler bằng spy

Một integration test với handler bean được spy theo cơ chế test framework có thể xác minh:

~~~java
verify(successHandler, times(1))
    .onAuthenticationSuccess(
        any(HttpServletRequest.class),
        any(HttpServletResponse.class),
        any(Authentication.class));
~~~

Điều này **chỉ có ý nghĩa sau khi** MockMvc thực hiện callback hợp lệ qua filter và bạn chắc chắn spy bọc đúng bean đang gắn vào <code>oauth2Login()</code>. Một test chỉ gọi method handler trực tiếp sẽ làm verify cũng pass, nhưng không chứng minh callback integration.

Với failure callback test:

~~~java
verify(failureHandler, times(1))
    .onAuthenticationFailure(
        any(HttpServletRequest.class),
        any(HttpServletResponse.class),
        any(AuthenticationException.class));
~~~

Đây là **mẫu assertion**, không phải test class hoàn chỉnh. Cần setup OP stub, session và bean spy theo Spring Boot/Spring Security/Mockito versions.

### 15.4. Test callback thất bại không bỏ state

Nếu callback error:

~~~text
/login/oauth2/code/company?error=access_denied&state=S1
~~~

phải có authorization request tương ứng S1 nếu muốn kiểm tra **error response processing hợp lệ**. Với state sai hoặc thiếu request, framework có thể đưa ra error khác; test nên phân biệt:

- User/OP từ chối authorization.
- Callback đến sai session hoặc state không match.

Không tự tạo Authentication hoặc tắt state validation cho test failure path.

## 16. SavedRequest: lưu những gì và khi nào?

<code>DefaultSavedRequest</code> có thể lưu redirect URL, method, query parameters và nhiều thông tin request khác theo implementation. <code>HttpSessionRequestCache</code> mặc định được dùng cho một số request bị yêu cầu authentication.

### 16.1. Protected GET

~~~http
GET /reports/quarterly?year=2026 HTTP/1.1
Host: portal.example.org
~~~

Đây là use case điển hình:

~~~text
Unauthenticated → redirect login → successful login → redirect original GET
~~~

### 16.2. Protected POST không nên được replay mù

Giả sử unauthenticated browser gửi:

~~~http
POST /orders/confirm HTTP/1.1
Content-Type: application/json

{"orderId":"123"}
~~~

Sau login, redirect URL thông thường tạo **request navigation mới**, không bảo đảm replay nguyên body/HTTP method. Việc tự replay POST bằng dữ liệu cũ có thể gây:

- Giao dịch bị thực hiện hai lần.
- Bypass CSRF.
- Stale order state.
- Không kiểm tra lại giá/tenant/ownership.

Với hành động có side effect:

1. Yêu cầu login trước khi người dùng submit hoặc lưu một pending action **server-side** với TTL/ngữ cảnh xác minh.
2. Sau login, đưa người dùng về trang GET để **xem lại/xác nhận**.
3. Gửi POST mới có CSRF token/idempotency key/authorization phù hợp.
4. Không tự động thực thi lại POST chưa được xác nhận.

### 16.3. SavedRequest không cấp quyền

Nếu user vừa login bằng một OIDC account không có quyền với report cũ, redirect vẫn phải được kiểm tra qua Spring Security authorization, method security và business policy.

Một success handler không nên tự:

~~~java
response.getWriter().write(fetchReportForOriginalUser());
~~~

với identity gắn trong saved request chưa được xác minh. Nó chỉ nên điều hướng theo policy; protected route sẽ kiểm tra principal hiện tại.

## 17. Kiểm thử query strings và URL encoding

Saved URL có thể chứa:

~~~text
/reports/quarterly?year=2026&format=csv
~~~

Test không chỉ assert <code>contains("/reports/quarterly")</code>; cần đảm bảo query parameters cần thiết còn nguyên trong redirect.

### 17.1. Một dạng assertion

~~~java
assertTrue(
    response.getRedirectedUrl()
        .contains("year=2026"));
assertTrue(
    response.getRedirectedUrl()
        .contains("format=csv"));
~~~

Nếu query chứa Unicode, dấu cách, <code>&amp;</code> hoặc encoded slash, hãy dùng URI parser/URL encoder theo contract thay vì substring dễ sai. Kiểm tra query không được giải mã hai lần hoặc tạo open redirect.

### 17.2. Tránh lưu URL có credentials

Không thiết kế:

~~~text
/reports/view?access_token=...
~~~

vì URL có thể vào logs, browser history, Referrer và SavedRequest. Đừng sử dụng access token trong query để “nhớ auth” qua login.

### 17.3. Chống open redirect

Nếu app cho phép <code>next</code>:

~~~text
/login?next=https://attacker.example
~~~

không redirect trực tiếp đến absolute URL không tin cậy sau success.

Chính sách phù hợp:

- Ưu tiên SavedRequest phát sinh từ protected request đã được server nhận.
- Chỉ cho return paths nội bộ có allowlist hoặc path normalization.
- Từ chối URLs có scheme/host bất thường, <code>//evil.example</code>, encoded open-redirect bypass.
- Phân quyền URL đích ở request sau login.
- Có default target nếu return path bị loại.

Ngay cả SavedRequest cũng cần đánh giá nếu ứng dụng có các redirect endpoints nội bộ nhận destination tùy ý.

## 18. Failure handler và session còn lại sau lỗi

### 18.1. Có SavedRequest nhưng login thất bại

Ví dụ:

~~~text
GET /reports/quarterly
  → SavedRequest
  → OAuth2 Login
  → OP access_denied
  → /login?error=oauth2
~~~

Tùy policy, SavedRequest có thể còn trong session để người dùng thử lại. Điều này có thể hợp lý khi lỗi là user deny rồi quyết định thử lại. Nhưng nếu user chuyển account hoặc route nhạy cảm có context cũ, giữ saved request vô hạn có thể tạo UX và authorization confusion.

### 18.2. Chính sách xóa cache sau lỗi

Các lựa chọn:

| Policy | Ưu điểm | Rủi ro |
|---|---|---|
| Giữ SavedRequest sau mọi lỗi | User retry login có thể quay về original URL | Stale redirect, nhiều providers/accounts |
| Xóa sau mọi lỗi | Không giữ stale target | User phải điều hướng lại |
| Xóa theo error category/mode | Cân bằng UX/security | Cần custom handler và tests |
| TTL/identity-bound saved target | Kiểm soát request tồn lâu | Phức tạp hơn, cần lưu context an toàn |

Không có policy duy nhất cho mọi sản phẩm. Cần xác định rõ và test theo yêu cầu.

### 18.3. Kiểm thử cleanup qua RequestCache

Custom failure handler có thể inject <code>RequestCache</code> và gọi:

~~~java
requestCache.removeRequest(request, response);
~~~

cho flow cần hủy pending redirect. Đây là thay đổi có chủ đích, không phải behavior cần áp dụng tự động cho mọi OIDC failure.

Khi test, dùng cùng session và assert:

~~~java
assertNull(requestCache.getRequest(
    callback, new MockHttpServletResponse()));
~~~

sau khi handler đã remove. Nếu success handler cần SavedRequest để resume sau retry, không làm cleanup này cho mọi lỗi.

## 19. Session fixation và SavedRequest sau login

Spring Security có session fixation protection khi Authentication thành công; với Servlet 3.1+ thường sử dụng <code>changeSessionId</code> theo default policy của framework.

### 19.1. Session ID thay đổi không có nghĩa session attributes mất

Quá trình:

~~~text
Before authentication:
    HTTP session ID = S1
    SavedRequest = /reports/quarterly

After successful authentication:
    HTTP session ID = S2 (rotated)
    SecurityContext = authenticated user
    SavedRequest = available theo session strategy/policy
~~~

Với cấu hình framework thông thường, session attributes được xử lý theo session fixation strategy, cho phép SavedRequest vẫn phục vụ redirect. Nhưng custom session management hoặc repository có thể thay đổi behavior.

### 19.2. Test ở mức integration

Một test end-to-end hợp lệ cần quan sát:

1. User có session trước login chứa SavedRequest.
2. Callback OIDC thật tạo authentication.
3. Session fixation strategy được áp dụng.
4. SavedRequest vẫn được xử lý đúng.
5. Browser tới original protected URL bằng authenticated session mới.

Không hardcode rằng session ID phải đổi bằng một giá trị nhất định trong mọi deployment; <code>SessionCreationPolicy</code> và fixation configuration có thể khác.

### 19.3. Không tự copy session cookie cũ

Không sửa test để bỏ qua lỗi bằng cách gắn lại cookie phiên cũ vào Authentication đã thay user. Nếu security context/session rotation đang lỗi, phải kiểm tra session strategy, session repository và proxy.

## 20. Nhiều providers và account switching

Ứng dụng có:

~~~text
/oauth2/authorization/company
/oauth2/authorization/partner
~~~

User chưa login mở <code>/reports/company</code>, sau đó chọn Partner. SavedRequest vẫn là một URL của Company.

### 20.1. Không sử dụng SavedRequest để bỏ qua authorization

Nếu Partner principal không có quyền, backend phải từ chối. Success handler chỉ redirect, không cấp role/scope.

### 20.2. Stale SavedRequest khi đổi account

Một user đang login với Alice rồi chọn switch sang Bob. Nếu ứng dụng giữ SavedRequest chứa URL/data của Alice, sau login Bob có thể bị redirect tới route cũ.

Các hướng:

- Xóa SavedRequest khi bắt đầu account switch rõ ràng.
- Redirect về trang trung lập <code>/home</code> sau switch.
- Phân biệt login bình thường và identity switch qua server-side transaction.
- Kiểm tra lại tenant/role/cache khi user mới vào route.

Không dùng <code>alwaysUseDefaultTargetUrl(true)</code> toàn cục nếu cần resume URL trong login bình thường. Có thể chọn policy theo authenticated operation và transaction state.

### 20.3. Linking account khác switching

Nếu user đang login A và muốn **link identity B**, không nên invalidate Authentication A trước callback một cách tùy tiện; linking cần transaction chứng minh user A chủ động yêu cầu gắn B. Đây là security-sensitive flow cần CSRF/step-up và identity validation riêng, không phải SavedRequest redirect đơn giản.

## 21. Nhiều tabs và concurrent login flows

Trong browser:

~~~text
Tab A: GET /reports/a → saved target A
Tab B: GET /reports/b → saved target B
Tab A: login Company
Tab B: login Partner
~~~

Nếu RequestCache giữ một SavedRequest trong session, request mới có thể **ghi đè hoặc thay đổi** target của tab trước. <code>HttpSessionOAuth2AuthorizationRequestRepository</code> dùng state/correlation riêng; nó cũng có concurrency behavior cần kiểm tra.

### 21.1. Không dùng SavedRequest làm OAuth state

State phải có entropy và gắn với authorization request, còn SavedRequest là một navigation target. Khi mở nhiều tabs, không giải quyết lỗi callback bằng:

~~~text
Ignore state, use whichever SavedRequest exists
~~~

Điều này mở ra login CSRF/mix-up vulnerabilities.

### 21.2. Chiến lược UX

- Thông báo khi có concurrent login/switch flows.
- Lưu server-side transaction keyed bằng state hoặc flow ID đã được bảo vệ nếu cần nhiều flows song song.
- Giới hạn thời gian sống và số pending requests.
- Sau callback, chọn target gắn đúng flow nếu nghiệp vụ đòi hỏi.
- Không tự redirect user B tới URL riêng của user A sau account switch.

### 21.3. Test race conditions

1. Tạo hai protected requests cùng session.
2. Quan sát SavedRequest cuối cùng theo repository policy.
3. Tạo hai OAuth2 authorization requests.
4. Callback từng state với OP test.
5. Đảm bảo không bỏ state check, không trộn ClientRegistration.
6. Kiểm tra target cuối phù hợp UX đã định.

Không phải mọi Spring Security RequestCache mặc định đều bảo đảm ghi nhớ độc lập target của từng tab.

## 22. Multi-instance và Spring Session

Hệ thống sau load balancer:

~~~text
Browser
   |
Load Balancer
   |------------------|
Instance A         Instance B
   |------------------|
        Redis
   Spring Session Store
~~~

Protected GET có thể tới A, OAuth2 callback tới B. Nếu SavedRequest hoặc OAuth2AuthorizationRequest chỉ nằm trong memory của A, B không khôi phục được dữ liệu.

### 22.1. Hai nguồn session state

~~~text
Spring Session shared store:
    SavedRequest                → original protected URL
    OAuth2AuthorizationRequest  → state/nonce/PKCE correlation
    SecurityContext             → authenticated principal
~~~

Chia sẻ HTTP session đúng giúp các nodes xử lý những dữ liệu này khi repository dùng session. Nhưng <code>OAuth2AuthorizedClientService</code> hoặc custom token store có thể nằm riêng.

### 22.2. Đặt các test chéo node

1. Protected URL vào instance A.
2. Login initiation vào A hoặc B.
3. Callback code/state vào B.
4. Success handler ở B tìm đúng SavedRequest.
5. Browser redirect đến original URL và được authorize theo principal mới.

Nếu callback báo <code>authorization_request_not_found</code>, đó thường là vấn đề session/cookie/authorization request repository, không phải failure handler không biết redirect.

### 22.3. Không giả định sticky sessions là phương án bền vững duy nhất

Session affinity có thể che vấn đề khi test, nhưng khi node bị thay thế hoặc rolling deploy, callback vẫn có thể đến node khác. Với kiến trúc HA, đánh giá shared session store và session serialization compatibility.

Không bypass OAuth state validation chỉ để callback thành công trên mọi node.

## 23. SavedRequest và CSRF

### 23.1. CSRF token khác saved request

Trong một HTTP session có thể cùng tồn tại:

~~~text
SecurityContext
SavedRequest
OAuth2AuthorizationRequest
CsrfToken
~~~

Từng loại có trách nhiệm riêng:

- CSRF token chứng minh browser form/request state-changing đến từ ngữ cảnh hợp lệ.
- OAuth <code>state</code> correlate authorization response.
- SavedRequest nhớ original protected URL.

Không dùng query <code>state</code> làm CSRF token cho POST business, cũng không dùng SavedRequest làm bằng chứng OAuth callback hợp lệ.

### 23.2. Logout nên dùng POST + CSRF

Sau user logout local, saved target cũ có thể cần xóa. Nhưng local logout phải được xử lý theo CSRF policy của browser:

~~~html
<form action="/logout" method="post">
    <input type="hidden" name="_csrf"
           value="CSRF_TOKEN_FROM_SERVER">
    <button type="submit">Đăng xuất</button>
</form>
~~~

Giá trị CSRF phải do Spring Security/template tạo, không hardcode.

### 23.3. Callback GET không cần CSRF form token

OIDC Authorization Code callback GET được bảo vệ bằng OAuth2 <code>state</code> và giao thức token/ID Token validation. Không yêu cầu <code>_csrf</code> trong callback GET mặc định.

Nếu dùng <code>response_mode=form_post</code>, cần xem hỗ trợ của Spring Security version, session cookie SameSite và ngoại lệ CSRF hẹp cho callback POST. Không tắt CSRF toàn ứng dụng chỉ vì callback hoặc login handler có lỗi 403.

## 24. Những nhánh success handler cần kiểm thử

| Điều kiện | Target kỳ vọng | Test trọng tâm |
|---|---|---|
| Có SavedRequest và không override | Original protected URL | <code>saved.getRedirectUrl()</code> |
| Không có SavedRequest | <code>/home</code> | Default target |
| Always-use-default bật | <code>/home</code> | Saved target không được ưu tiên |
| Target parameter được cho phép theo policy | Internal route đã validate | Không open redirect |
| Saved target bị đánh dấu không hợp lệ | Safe fallback | Không redirect tới external domain |
| User đổi account | Neutral target theo UX | Không dùng stale URL của identity cũ |
| User login sai provider | Authorization vẫn phải kiểm tra | Không lộ protected data |
| Login thành công sau session ID rotation | Original target còn đúng | Session state lifecycle |
| Login thành công trên node khác | Original target còn đúng | Shared session |

### 24.1. Chỉ assert redirect status là chưa đủ

Một test:

~~~java
.andExpect(status().is3xxRedirection());
~~~

không cho biết:

- Redirect đến đâu?
- Có dùng SavedRequest không?
- Có query string đúng không?
- Có open redirect không?
- Principal mới có quyền truy cập target không?

Tốt hơn cần kiểm tra <code>Location</code> hoặc <code>getRedirectedUrl()</code> cùng behavior của request kế tiếp.

### 24.2. Session attribute cleanup

Việc SavedRequest được remove vào thời điểm nào phụ thuộc nhánh handler, RequestCache và next request matching. Test nên nhắm contract thật, không dựa vào một internal session attribute name bất biến trên mọi versions.

## 25. Những nhánh failure handler cần kiểm thử

| Failure | Response/behavior kỳ vọng |
|---|---|
| OP trả <code>access_denied</code> | Trang lỗi login an toàn, không authenticated |
| Callback state mismatch | Từ chối; không bỏ correlation |
| Token Endpoint <code>invalid_grant</code> | Authentication không thành công, không retry code vô hạn |
| OP HTTP 503 | Safe error UX, observability |
| ID Token issuer/signature sai | Fail closed |
| Unknown custom OAuth2Error | Category fallback, không throw khi render |
| <code>error_description</code> chứa HTML | Không reflected XSS |
| <code>error_uri</code> external | Không open redirect |
| Failure có SavedRequest cũ | Giữ/xóa theo policy đã test |
| Account switching thất bại | Không tự phục hồi identity cũ từ browser param |

### 25.1. Không test bằng mock exception không khớp flow rồi suy luận nguyên nhân

Unit test có thể truyền:

~~~java
new OAuth2AuthenticationException(
    new OAuth2Error("access_denied"));
~~~

để đảm bảo failure handler xử lý mã đó. Nhưng nếu muốn chứng minh Spring Security tạo exception đúng khi OP deny consent, phải có **callback integration test** với state/session phù hợp.

### 25.2. Không log raw exception messages tự động

Một OAuth2 failure có thể mang <code>error_description</code> hoặc thông tin callback trong nested cause. Nếu logs/traces ghi <code>exception.getMessage()</code> không kiểm soát, có thể lộ upstream data/PII. Nên log normalized category + correlation ID và restricted diagnostics theo policy.

## 26. Kiểm thử AuthorizationFailure không thuộc login failure

Sau login, request backend cần refresh access token. Token Endpoint trả <code>invalid_grant</code>, gây <code>OAuth2AuthorizationException</code>.

Đây không phải login callback failure; <code>oauth2Login().failureHandler(...)</code> thường **không chạy**.

### 26.1. Unit test authorized-client manager failure

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;
import org.springframework.security.oauth2.core.OAuth2Error;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.*;

class AuthorizedClientFailureTest {

    @Test
    void refreshFailureIsHandledInServiceLayer() {
        OAuth2AuthorizedClientManager manager =
            mock(OAuth2AuthorizedClientManager.class);

        var request = OAuth2AuthorizeRequest
            .withClientRegistrationId("company")
            .principal("user-123")
            .build();

        when(manager.authorize(request))
            .thenThrow(new OAuth2AuthorizationException(
                new OAuth2Error("invalid_grant")));

        var failure = assertThrows(
            OAuth2AuthorizationException.class,
            () -> manager.authorize(request));

        org.junit.jupiter.api.Assertions.assertEquals(
            "invalid_grant",
            failure.getError().getErrorCode());
    }
}
~~~

Test này giả lập manager failure. Nó **không chứng minh** Token Endpoint thật trả lỗi, không chạy success/failure handler của browser login và không kiểm thử persistence. Để test token cleanup, cần mock/fixture storage, failure handler hoặc integration test tương ứng.

### 26.2. Không xóa mọi token khi refresh thất bại

Nếu hai replicas cùng refresh token R0:

~~~text
Node A: refresh R0 thành công → lưu R1
Node B: refresh R0 thất bại → invalid_grant
Node B: removeAuthorizedClient theo principal?
~~~

Delete không có điều kiện ở B có thể xóa R1 vừa được A lưu. Trong cluster, cần coordination, reread state sau lock và CAS/versioned conditional remove nếu yêu cầu độ tin cậy cao.

Không đưa một test MockMvc success handler đơn giản ra làm chứng rằng token refresh race đã được giải quyết.

## 27. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
|---|---|---|
| Sau login luôn về <code>/home</code> | Handler alwaysUseDefault bật hoặc không có SavedRequest | Kiểm tra handler config, RequestCache, session |
| SavedRequest có nhưng vẫn về <code>/home</code> | Handler khác đang được inject, session khác, override priority | Kiểm tra bean wiring, callback session |
| Redirect về URL cũ nhiều lần | SavedRequest cleanup/matching chưa đúng | RequestCacheAwareFilter, cache policy |
| Redirect thiếu query string | Request cache/save request target hoặc URL encoding | Kiểm tra saved.getRedirectUrl |
| Redirect sang website khác | targetUrlParameter/returnTo không validate | Allowlist, relative-path policy |
| Login thành công nhưng protected route 403 | User không có quyền trên target | Kiểm tra authorities/tenant |
| Login lỗi nhưng handler không chạy | Không đi qua OAuth2 Login filter, chain matcher sai | SecurityFilterChain và callback filter |
| MockMvc test <code>oidcLogin()</code> xanh nhưng redirect sai | Mock không thực thi success handler | Unit handler + integration callback test |
| Callback báo <code>authorization_request_not_found</code> | State repository/session/cookie mất | Spring Session, browser, proxy |
| Sau scale-out callback lúc được lúc không | Session local, thiếu shared store | Shared session/affinity |
| Tab A login rồi về saved URL của Tab B | Một SavedRequest bị ghi đè trong session | UX/concurrent request policy |
| Chọn Partner nhưng redirect về Company URL | Stale saved target trong switch flow | Clear cache theo switch policy |
| Failure handler in raw OP error | Unsafe exception rendering | Fixed redirect, sanitized message |
| Fail <code>access_denied</code> bị ghi critical | Chưa phân loại expected user outcome | Category và alert thresholds |
| MockMvc 200 khi unauthenticated | Security filters bị tắt trong test | Bật filter chain thật |
| Callback HTTP 403 | Có thể CSRF/form_post hoặc chain mismatch | Phân biệt với state/nonce error |
| Logout GET làm thay đổi session | Logout CSRF | POST + CSRF |
| SavedRequest bị mất sau session rotation | Custom session strategy/repository | Kiểm tra fixation/session attributes |

### 27.1. Luồng điều tra

~~~text
User đã thử protected URL trước login?
    |
    +-- Không → không có SavedRequest; default target hợp lý
    |
    +-- Có → Filter chain thực sự cache original URL?
                 |
                 +-- Không → RequestCache, entry point, matcher
                 |
                 +-- Có → Authorization initiation và callback cùng session?
                              |
                              +-- Không → cookie, session store, proxy
                              |
                              +-- Có → OAuth2 Login có thành công?
                                           |
                                           +-- Không → state/PKCE/Token/ID Token,
                                           |          failure handler
                                           |
                                           +-- Có → SuccessHandler nào được gắn?
                                                       |
                                                       +-- SavedRequestAware?
                                                       +-- alwaysUseDefault?
                                                       +-- target parameter?
                                                       +-- stale cache?
~~~

Đừng sửa lỗi bằng cách bỏ <code>state</code> validation hoặc cho browser tự cấp target URL tùy ý.

## 28. Logging, metrics và test isolation

### 28.1. Các trường log có ích

~~~text
event=oidc_login_success_redirect
providerAlias=company
redirectKind=saved_request
redirectRoute=/reports/{reportId}
correlationId=...

event=oidc_login_failed
providerAlias=company
category=user_denied
callbackStage=authorization_response
correlationId=...
~~~

Không log:

~~~text
authorization_code
code_verifier
state / nonce thật
id_token / access_token / refresh_token
session cookie / client secret
raw error_description
~~~

### 28.2. Metrics nên có

| Metric | Ý nghĩa |
|---|---|
| <code>oauth2_login_success_total{provider,redirect_kind}</code> | Saved/default/explicit safe target |
| <code>oauth2_login_failure_total{provider,category}</code> | Login failure theo category |
| <code>saved_request_created_total{route_group}</code> | Request được cache |
| <code>saved_request_missing_total{provider}</code> | Login success không tìm được saved request |
| <code>saved_request_rejected_total{reason}</code> | URL bị loại bởi safety policy |
| <code>oauth2_callback_state_failure_total{provider}</code> | Lỗi correlation |
| <code>oauth2_login_redirect_latency_seconds{provider}</code> | Thời gian từ success tới redirect |

Không dùng raw URL có query chứa PII, raw email, session ID hoặc state làm metric labels; dùng route template/category có cardinality giới hạn.

### 28.3. Test isolation

Khi chạy nhiều tests:

- Tạo <code>MockHttpSession</code> mới cho mỗi test độc lập.
- Reset mock handler/spies giữa tests nếu dùng shared context.
- Không dùng production OP hoặc token thật.
- Không hardcode JWT signing private key dùng chung với production.
- Không giả định order của test methods.
- Nếu có database/Redis test container, cleanup đúng test data để không giữ stale saved request/authorized clients.

## 29. Bài tập tự luyện

### Bài 1 — SavedRequest dùng để làm gì?

User chưa login mở <code>/reports/quarterly</code>.

**Đáp án:** RequestCache có thể lưu protected request để sau login success handler redirect user về đúng URL đó. SavedRequest không xác thực user và không cấp quyền xem report.

### Bài 2 — State có phải SavedRequest?

OAuth callback có <code>state=S1</code>.

**Đáp án:** Không. State correlate authorization response với authorization request gốc; SavedRequest ghi nhớ protected URL trước login. Không dùng chúng thay nhau.

### Bài 3 — oidcLogin() có test success handler không?

~~~java
mockMvc.perform(get("/reports/quarterly")
    .with(oidcLogin()));
~~~

**Đáp án:** Không. Test này inject authenticated OIDC principal vào request, không chạy OAuth2 Login callback hoặc gọi success handler như một authentication event.

### Bài 4 — Test SavedRequest có cần OP thật không?

**Đáp án:** Không. Có thể unit test <code>SavedRequestAwareAuthenticationSuccessHandler</code> với MockHttpServletRequest/Response/Session và HttpSessionRequestCache; còn integration callback cần OP test/stub hợp lệ.

### Bài 5 — Không có saved request

User đi thẳng đến <code>/login</code> rồi đăng nhập thành công.

**Đáp án:** Success handler dùng default target <code>/home</code> nếu không có override khác.

### Bài 6 — Always use default

<code>alwaysUseDefaultTargetUrl=true</code> nhưng session có saved target <code>/reports/a</code>.

**Đáp án:** Handler ưu tiên default target, không resume saved target. Test phải phản ánh chủ đích sản phẩm.

### Bài 7 — Open redirect

Frontend đưa <code>next=https://attacker.example</code> cho success handler.

**Đáp án:** Không redirect URL này khi chưa allowlist/validation. Ưu tiên saved request từ protected route và fallback nội bộ.

### Bài 8 — User bấm Deny

OP trả <code>error=access_denied</code>.

**Đáp án:** Authentication không thành công; failure handler trả trang lỗi login an toàn, không log raw description hay tạo Authentication.

### Bài 9 — Login thất bại nhưng SavedRequest vẫn còn

**Đáp án:** Việc giữ/xóa phụ thuộc retry UX và policy. Nên test rõ; account switch nhạy cảm có thể cần clear stale target.

### Bài 10 — Hai tabs

Tab A request /reports/a, Tab B request /reports/b trong cùng session.

**Đáp án:** RequestCache mặc định có thể không giữ riêng target theo tab; test concurrency/UX policy, không bỏ OAuth state validation.

### Bài 11 — Multi-instance

Protected GET đến A, callback đến B; success handler về /home thay vì /reports.

**Đáp án:** Kiểm tra session/cookie/shared RequestCache state, handler wiring và session repository. Không giả định hai nodes tự chia sẻ HttpSession local.

### Bài 12 — Redirect thành công nhưng 403 ở report

**Đáp án:** Đây có thể là hành vi đúng: principal vừa login thiếu quyền report. Success redirect không bypass authorization của protected route.

### Bài 13 — Callback state mismatch

Callback code/state không khớp request gốc.

**Đáp án:** Từ chối authentication. Không gọi success handler để “tiếp tục UX” hoặc bỏ state validation.

### Bài 14 — Protected POST

User chưa login gửi POST thay đổi giao dịch rồi được redirect login.

**Đáp án:** Không tự replay raw POST sau login. Dùng trang review/confirm, CSRF/idempotency và authorization mới.

### Bài 15 — Handler direct test vs filter integration

**Hỏi:** Vì sao test gọi <code>handler.onAuthenticationSuccess()</code> trực tiếp không chứng minh OIDC callback hoạt động?

**Đáp án:** Nó không chạy OAuth2LoginAuthenticationFilter, Token Endpoint, ID Token validation hoặc session strategy; chỉ kiểm tra logic của handler.

### Bài 16 — Failure handler và exception trong session

**Hỏi:** Nếu SimpleUrlAuthenticationFailureHandler lưu AuthenticationException trong session, có an toàn khi view in <code>exception.message</code> trực tiếp không?

**Đáp án:** Không. Message có thể chứa upstream data. Chỉ hiển thị message đã được map/sanitize; không expose raw OAuth2Error description.

### Bài 17 — MockMvc thiếu filter

<code>@AutoConfigureMockMvc(addFilters=false)</code> khiến protected URL trả 200.

**Đáp án:** Test không còn kiểm chứng Spring Security RequestCache/entry point. Bật filters và test unauthenticated request.

### Bài 18 — Test session rotation

**Đề bài:** Thiết kế integration test xác minh session ID được quản lý theo session-fixation strategy và SavedRequest vẫn được dùng sau login.

**Gợi ý:** Khởi tạo protected URL, giữ browser session, thực hiện OAuth2 callback hợp lệ qua OP test, quan sát session/redirect và request sau login; không tự copy session ID từ tài khoản khác.

### Bài 19 — Kiểm thử tổng hợp

Xây một Spring Boot Servlet app có:

1. ClientRegistration OIDC <code>company</code>.
2. Protected route <code>/reports/{reportId}</code>.
3. Custom login page <code>/login</code>.
4. <code>HttpSessionRequestCache</code> cấu hình thành bean.
5. <code>SavedRequestAwareAuthenticationSuccessHandler</code> với <code>/home</code> default.
6. Failure handler không phản chiếu <code>error_description</code>.
7. Unit tests saved request, no saved request, always-use-default, failure redirect.
8. MockMvc test unauthenticated route được cache.
9. Test <code>oidcLogin()</code> cho controller authorization, ghi chú rằng không chạy callback.
10. OP stub integration test callback hợp lệ và callback lỗi.
11. Test nhiều tabs, multi-provider, account switch và multi-instance.
12. Test original URL có query và returnTo ngoài domain bị loại.
13. Test protected route sau redirect vẫn kiểm tra role/tenant.
14. Logs/metrics không chứa token, code, state hoặc session cookie.

Giải thích vì sao **test riêng handler + test RequestCache + test callback thật** là ba lớp bổ sung nhau.

## 30. Tổng kết

- **SavedRequest** là bản ghi của protected URL trước login; **OAuth2AuthorizationRequest** là dữ liệu correlation của OAuth2 state/nonce/PKCE; **SecurityContext** là trạng thái authentication.
- **<code>HttpSessionRequestCache</code>** lưu/tìm request; **<code>SavedRequestAwareAuthenticationSuccessHandler</code>** chọn redirect target sau thành công.
- Success handler có thể ưu tiên SavedRequest, default URL, always-use-default hoặc target parameter theo cấu hình; phải test từng nhánh.
- Failure handler cần xử lý lỗi OAuth2/OIDC Login an toàn, không lộ raw OP description, token hoặc error URI chưa tin cậy.
- **<code>oidcLogin()</code>/<code>oauth2Login()</code> trong MockMvc giả lập authenticated principal cho request**, không tự kích hoạt success/failure handler hoặc code exchange.
- Unit test handler có thể dùng <code>MockHttpServletRequest</code>, <code>MockHttpServletResponse</code>, <code>MockHttpSession</code>, <code>HttpSessionRequestCache</code> mà không cần OP.
- MockMvc với security filters bật giúp kiểm tra unauthenticated protected URL được cache trước khi login.
- Integration test callback thật cần authorization request/state, test Token Endpoint/JWKS và ID Token validation hợp lệ; không bypass OAuth2 state hoặc OIDC validation vì muốn test dễ.
- Redirect về SavedRequest **không cấp quyền**: protected route sau login vẫn phải authorize principal mới.
- SavedRequest không nên được dùng để replay POST có side effect; cần CSRF, idempotency và xác nhận lại.
- Cần bảo vệ tránh open redirect, stale saved URL sau account switch, nhiều tabs và session state thất lạc qua nhiều replicas.
- Session fixation, Spring Session/Redis, cookie/SameSite và nhiều SecurityFilterChains ảnh hưởng việc handler tìm thấy saved request; không bỏ security validations để xử lý lỗi session.
- Logs/metrics nên ghi provider alias, redirect category, failure category và correlation ID; không log raw OAuth2 credentials hoặc sensitive URLs.

### Tài liệu tham khảo

- **Spring Security Reference — Servlet OAuth2 Login:** authorization initiation, callback, success/failure handlers và login flow.
- **Spring Security Reference — Servlet Authentication:** <code>AuthenticationSuccessHandler</code>, <code>AuthenticationFailureHandler</code>, <code>SimpleUrlAuthenticationFailureHandler</code>.
- **Spring Security Java API — SavedRequestAwareAuthenticationSuccessHandler:** ưu tiên default target, target parameter, SavedRequest và RequestCache.
- **Spring Security Java API — HttpSessionRequestCache / DefaultSavedRequest:** save/get/match/remove request, redirect URL.
- **Spring Security Reference — Servlet RequestCache:** <code>ExceptionTranslationFilter</code>, <code>RequestCacheAwareFilter</code>, saved request behavior.
- **Spring Security Reference — Spring Security Test (MockMvc):** <code>oauth2Login()</code>, <code>oidcLogin()</code>, <code>MockMvc</code> request post-processors.
- **Spring Session Reference — Redis HTTP Session:** chia sẻ session attributes và behavior của session store phân tán.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** Authorization Code Flow, state và error responses.
- **RFC 7636 — Proof Key for Code Exchange:** PKCE và authorization code binding.
- **OpenID Connect Core 1.0:** ID Token validation, nonce, issuer, audience, OIDC Login.
- **OWASP Authentication Cheat Sheet / Session Management Cheat Sheet:** redirect safety, session lifecycle và session fixation.
- **OWASP Unvalidated Redirects and Forwards Cheat Sheet:** xác minh redirect target và tránh open redirect.
