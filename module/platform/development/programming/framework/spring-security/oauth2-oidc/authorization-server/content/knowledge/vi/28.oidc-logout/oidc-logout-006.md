# Kết thúc phiên Authorization Server và dọn SecurityContext

> **Chương:** OIDC Logout  
> **Module:** `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`  
> **Mục tiêu module:** Học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot.  
> **Phạm vi:** Spring Boot 3.x, Spring Security 6.x và Spring Authorization Server 1.5.x trên Servlet stack. Nội dung tập trung vào phiên đăng nhập tại OpenID Provider/Authorization Server (OP/AS), OIDC RP-Initiated Logout và vòng đời `SecurityContext`. Đối chiếu API theo patch version thực tế.

## 1. Bối cảnh và mục tiêu

Một hệ thống OIDC thường có nhiều trạng thái đăng nhập cùng tồn tại. Người dùng có thể có SSO session tại Authorization Server, local session tại từng Relying Party (RP), cùng access token và refresh token đã được phát hành.

Ví dụ, người dùng đăng nhập vào Portal thông qua Authorization Server. Portal tạo local session; Authorization Server cũng tạo SSO session. Người dùng mở Admin Console và được đăng nhập tự động vì SSO session vẫn còn. Khi người dùng nhấn Logout tại Portal, nếu Portal chỉ xóa cookie và local session thì SSO session tại Authorization Server vẫn tồn tại. Lần sau người dùng mở Portal hoặc RP khác, OP có thể tiếp tục SSO mà không yêu cầu đăng nhập lại.

Bên trong Authorization Server, logout còn phải xử lý trạng thái xác thực của Spring Security. Chỉ gọi `SecurityContextHolder.clearContext()` ở một controller có thể chưa đủ nếu Authentication vẫn được lưu trong `SecurityContextRepository`. Ngược lại, chỉ invalidate `HttpSession` cũng chưa dọn mọi reference tới context đang được request sử dụng.

Sau bài học, bạn có thể:

1. Phân biệt local RP session, OP/AS session, `SecurityContext` và OAuth2 token state.
2. Mô tả RP-Initiated Logout và vai trò của `end_session_endpoint`.
3. Hiểu cách OIDC Logout Endpoint của Spring Authorization Server xác minh request và tìm session.
4. Phân biệt `LogoutFilter`, `LogoutHandler`, `LogoutSuccessHandler` và OIDC logout filter/provider.
5. Giải thích vòng đời `SecurityContextHolder` và `SecurityContextRepository`.
6. Dùng `SecurityContextLogoutHandler` để invalidate session, clear Authentication và lưu context rỗng.
7. Cấu hình cùng một repository cho filter chain và logout handler khi dùng custom repository.
8. Tích hợp `SessionRegistry`, `HttpSessionEventPublisher` và distributed session.
9. Xử lý remember-me, CSRF, cookie, concurrent request và async task.
10. Kiểm thử để chứng minh request sau logout không khôi phục Authentication cũ.

**Nguyên tắc chính:** Logout hoàn chỉnh tại Authorization Server phải kết thúc đúng HTTP session, dọn Authentication khỏi context hiện tại và xóa trạng thái đã lưu trong repository. OIDC logout, local logout, logout notification và token revocation là những cơ chế liên quan nhưng có phạm vi khác nhau.

## 2. Những trạng thái cần phân biệt

| Thành phần | Vai trò | Nơi quản lý phổ biến | Logout cần làm gì? |
| --- | --- | --- | --- |
| RP local session | Duy trì đăng nhập tại từng ứng dụng | RP, Servlet session hoặc application session | RP tự kết thúc session của mình |
| OP/AS SSO session | Cho phép user tiếp tục SSO tại Authorization Server | HttpSession/session store của OP | OP kết thúc session qua logout flow |
| SecurityContext hiện tại | Cung cấp Authentication cho request/thread | SecurityContextHolder | Clear holder và Authentication phù hợp |
| SecurityContext đã lưu | Khôi phục Authentication ở request sau | SecurityContextRepository | Lưu trạng thái rỗng hoặc xóa context |
| SessionRegistry entry | Liên kết principal/session để tìm session | SessionRegistry | Cập nhật/xóa theo session lifecycle |
| Access token | Credential gọi Resource Server | Authorization Server và Resource Server | Revocation/denylist/introspection/expiry theo policy |
| Refresh token | Xin access token mới | Authorization Server | Revoke nếu cần chặn cấp token mới |
| OAuth2 authorization/consent | Trạng thái grant và consent | Authorization/consent service | Có policy riêng; không tự mất khi browser logout |
| Session tại RP khác | Duy trì local login ở ứng dụng khác | Từng RP | Cần logout notification hoặc flow riêng |

Một thao tác logout không tự động kết thúc tất cả trạng thái trên. Xóa cookie Portal không kết thúc SSO session tại OP; kết thúc OP session không tự xóa local session của Admin Console; clear SecurityContext trong một request stateless không làm JWT đã phát hành mất hiệu lực.

### 2.1. Local logout và OP logout

**Local logout** kết thúc phiên của một ứng dụng. Người dùng không còn authenticated tại RP đó, nhưng OP session có thể vẫn còn.

**RP-Initiated Logout** cho phép RP điều hướng browser tới Logout Endpoint của OP để yêu cầu kết thúc phiên End-User. OP xác minh request, xử lý session và có thể điều hướng browser trở lại RP.

### 2.2. Logout session khác revoke token

JWT access token đã phát hành có thể tiếp tục được Resource Server chấp nhận đến `exp` nếu Resource Server chỉ xác minh chữ ký và claims cục bộ. Refresh token có thể tiếp tục xin token mới nếu chưa bị thu hồi.

Nếu policy yêu cầu ngăn API access sớm, cần token revocation, introspection, denylist, event propagation hoặc access token TTL ngắn. Không mô tả logout browser là “đã vô hiệu hóa mọi token” nếu hệ thống chưa thực hiện các bước đó.

## 3. RP-Initiated Logout tại Authorization Server

OpenID Connect RP-Initiated Logout 1.0 mô tả cách RP yêu cầu OP đăng xuất End-User thông qua User Agent (thường là browser).

RP lấy URL Logout Endpoint từ OpenID Provider Configuration qua metadata field `end_session_endpoint`:

~~~json
{
  "issuer": "https://auth.example.test",
  "end_session_endpoint": "https://auth.example.test/connect/logout"
}
~~~

URL chỉ là ví dụ. SAS thường dùng `/connect/logout`, nhưng có thể thay đổi qua `AuthorizationServerSettings`. RP nên đọc `end_session_endpoint` từ metadata của issuer đã xác minh thay vì tự ghép path.

~~~mermaid
sequenceDiagram
    autonumber
    participant U as End-User / Browser
    participant RP as Relying Party
    participant OP as OpenID Provider / AS
    participant REG as SessionRegistry

    U->>RP: Bấm Logout
    RP->>RP: Kết thúc local session nếu policy yêu cầu
    RP-->>U: Redirect tới end_session_endpoint
    U->>OP: Logout Request
    OP->>OP: Xác minh id_token_hint, client và redirect
    OP->>REG: Tra SessionInformation
    REG-->>OP: Session liên quan
    OP->>OP: Kết thúc OP session
    OP-->>U: Redirect về post-logout URI nếu hợp lệ
    U->>RP: Callback kèm state
    RP->>RP: Xác minh state và hiển thị kết quả
~~~

### 3.1. Các tham số logout request

| Tham số | Mức yêu cầu | Mục đích |
| --- | --- | --- |
| `id_token_hint` | RECOMMENDED | ID Token OP đã cấp, giúp nhận diện user/client/session |
| `client_id` | OPTIONAL | Xác định client; nếu đi cùng id_token_hint thì phải khớp client đã nhận ID Token |
| `post_logout_redirect_uri` | OPTIONAL | URI RP muốn browser quay về sau logout |
| `state` | OPTIONAL | Giá trị opaque RP dùng tương quan request và callback |
| `logout_hint` | OPTIONAL | Gợi ý định danh End-User khi RP không có ID Token hint |

OIDC RP-Initiated Logout yêu cầu OP hỗ trợ cả HTTP GET và POST. RP có thể gửi query parameters hoặc form-urlencoded body. Không gửi client secret trong Logout Request.

### 3.2. id_token_hint và session

`id_token_hint` phải là ID Token do chính OP phát hành. OP phải xác minh token thuộc issuer của mình và kiểm tra quan hệ với client/session liên quan. Không dùng access token, refresh token, authorization code hoặc JWT tự ký bởi RP thay cho ID Token hint.

OP **SHOULD** chấp nhận ID Token hint đã hết hạn nếu OP vẫn có thể xác định RP qua `aud` và/hoặc session qua `sid` là session hiện tại hoặc gần đây. Người dùng có thể logout sau khi ID Token hết hạn trong khi OP session vẫn còn. Quy tắc này chỉ dành cho logout hint; không có nghĩa access token hết hạn vẫn được dùng để gọi API.

Nếu request có cả `client_id` và `id_token_hint`, OP **MUST** xác minh client ID khớp client đã dùng khi phát hành ID Token. Nếu không có hint, OP có thể dùng client/identifier khác theo policy, nhưng không được suy ra session user chỉ từ một chuỗi client ID.

### 3.3. post_logout_redirect_uri

Nếu RP gửi `post_logout_redirect_uri`, OP phải xác minh URI khớp chính xác một URI đã đăng ký cho client tương ứng. Không dùng wildcard, prefix match hoặc substring match.

Ví dụ URI đã đăng ký:

~~~text
https://app.example.test/logout/callback
~~~

Các giá trị sau không tự động được coi là khớp:

~~~text
https://app.example.test/logout/callback/
https://app.example.test/logout/callback?next=/admin
https://app.example.test.evil.test/logout/callback
http://app.example.test/logout/callback
~~~

Nếu không có `id_token_hint`, OP **MUST NOT** redirect về URI yêu cầu trừ khi có phương tiện khác xác nhận tính hợp pháp của redirect target. Không redirect tới URL tùy ý do browser gửi.

SAS lưu các URI này trong RegisteredClient bằng `postLogoutRedirectUri(...)`. Đây là registration riêng, không dùng `redirectUri(...)` của Authorization Code Flow để thay thế.

~~~java
RegisteredClient portalClient = RegisteredClient
    .withId("portal-client-registration")
    .clientId("portal-client")
    .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
    .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
    .redirectUri("https://portal.example.test/login/oauth2/code/portal")
    .postLogoutRedirectUri("https://portal.example.test/logout/callback")
    .scope(OidcScopes.OPENID)
    .clientSettings(ClientSettings.builder()
        .requireProofKey(true)
        .build())
    .build();
~~~

Đây là fragment public client dùng Authorization Code + PKCE. Confidential client cần client authentication method và credential riêng. Registration phải được lưu trong repository bền vững khi chạy production.

### 3.4. state và confirmation

RP tạo `state` ngẫu nhiên, lưu gắn với browser session/transaction và gửi trong Logout Request. Khi OP redirect về callback, RP so sánh chính xác state nhận được với state đang chờ rồi consume giá trị đó. Dùng state riêng cho logout, TTL ngắn, one-time use; không đưa access token, refresh token, client secret hoặc URL tùy ý vào state.

OP echo lại state theo protocol nhưng không xác minh thay RP. RP vẫn phải tự kiểm tra state.

OP **SHOULD** hỏi End-User có muốn logout khỏi OP hay không và **MUST** hỏi trong các trường hợp được RP-Initiated Logout quy định, bao gồm khi không có ID Token hint hoặc hint không gắn với session hiện tại tương ứng. Nếu user từ chối, RP local session có thể đã được kết thúc trước đó, nhưng không được tuyên bố OP session đã logout.

### 3.5. Ví dụ Logout Request

GET:

~~~http
GET /connect/logout?id_token_hint=ID_TOKEN_VALUE&client_id=portal-client&post_logout_redirect_uri=https%3A%2F%2Fportal.example.test%2Flogout%2Fcallback&state=RANDOM_STATE HTTP/1.1
Host: auth.example.test
~~~

POST:

~~~http
POST /connect/logout HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded

id_token_hint=ID_TOKEN_VALUE&client_id=portal-client&post_logout_redirect_uri=https%3A%2F%2Fportal.example.test%2Flogout%2Fcallback&state=RANDOM_STATE
~~~

GET đơn giản nhưng query string có thể xuất hiện trong browser history, proxy/access log hoặc APM. POST đặt tham số trong form body nhưng vẫn cần redaction tại proxy/APM. Không log raw ID Token hint hoặc state.

## 4. OIDC Logout Endpoint trong Spring Authorization Server

### 4.1. Bật OIDC

Spring Authorization Server không bật OIDC mặc định. Trong SAS 1.5.x, bật OIDC trên Authorization Server configurer:

~~~java
@Configuration(proxyBeanMethods = false)
class AuthorizationServerSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(
            HttpSecurity http) throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, as ->
                as.oidc(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Đây là fragment cho Authorization Server endpoints. Ứng dụng đầy đủ còn cần RegisteredClientRepository, OAuth2AuthorizationService, issuer/JWK configuration và application SecurityFilterChain phục vụ user login.

Có thể cấu hình path bằng `AuthorizationServerSettings`:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://auth.example.test")
        .oidcLogoutEndpoint("/connect/logout")
        .build();
}
~~~

Nếu đổi path, OIDC Provider Configuration phải công bố `end_session_endpoint` mới và reverse proxy phải route đúng.

### 4.2. Pipeline xử lý logout

Trong SAS 1.5.x, `OidcLogoutEndpointConfigurer` cấu hình `OidcLogoutEndpointFilter`. Filter mặc định sử dụng:

- `OidcLogoutAuthenticationConverter` để chuyển HTTP request thành `OidcLogoutAuthenticationToken`.
- `AuthenticationManager` chứa `OidcLogoutAuthenticationProvider` để xác minh request.
- `OidcLogoutAuthenticationSuccessHandler` để thực hiện logout và xử lý response.
- Failure handler trả OAuth2 error khi validation thất bại.

`OidcLogoutAuthenticationProvider` sử dụng `SessionRegistry` để tra `SessionInformation` liên quan tới End-User. Default validator kiểm tra các tham số logout, bao gồm `post_logout_redirect_uri`. Nếu tùy biến validator, phải ném `OAuth2AuthenticationException` khi validation thất bại.

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant F as OidcLogoutEndpointFilter
    participant C as OidcLogoutAuthenticationConverter
    participant P as OidcLogoutAuthenticationProvider
    participant R as SessionRegistry
    participant H as OidcLogoutAuthenticationSuccessHandler
    participant L as LogoutHandler

    B->>F: GET/POST /connect/logout
    F->>C: Convert HTTP request
    C-->>F: OidcLogoutAuthenticationToken
    F->>P: authenticate(token)
    P->>P: Validate ID Token/client/redirect
    P->>R: Find SessionInformation
    R-->>P: Session information
    P-->>F: Authenticated logout token
    F->>H: Authentication success
    H->>L: Perform logout
    L->>L: Invalidate session and clear context
    H-->>B: OIDC logout response/redirect
~~~

### 4.3. Tùy biến OIDC logout success handler

SAS cung cấp `OidcLogoutAuthenticationSuccessHandler` và setter `setLogoutHandler(...)`. Nếu cần kiểm soát repository hoặc thêm cleanup, có thể cấu hình handler này:

~~~java
@Bean
OidcLogoutAuthenticationSuccessHandler oidcLogoutSuccessHandler(
        SecurityContextRepository repository) {

    SecurityContextLogoutHandler contextLogoutHandler =
        new SecurityContextLogoutHandler();

    contextLogoutHandler.setSecurityContextRepository(repository);

    OidcLogoutAuthenticationSuccessHandler successHandler =
        new OidcLogoutAuthenticationSuccessHandler();

    successHandler.setLogoutHandler(contextLogoutHandler);
    return successHandler;
}
~~~

Sau đó gắn handler vào OIDC configurer:

~~~java
authorizationServer.oidc(oidc ->
    oidc.logoutEndpoint(logout ->
        logout.logoutResponseHandler(oidcLogoutSuccessHandler)
    )
);
~~~

Đây là fragment tích hợp vào cấu hình AS. Nếu thay success handler mặc định, phải bảo đảm handler mới vẫn thực hiện cleanup session/context và giữ response/redirect behavior của OIDC. Không thay bằng lambda chỉ redirect browser.

## 5. Local logout trong Spring Security

### 5.1. LogoutFilter, LogoutHandler và LogoutSuccessHandler

Local logout của Spring Security được điều phối bởi `LogoutFilter`:

| Thành phần | Trách nhiệm |
| --- | --- |
| `LogoutFilter` | Nhận request logout và điều phối chuỗi handler |
| `LogoutHandler` | Thực hiện cleanup session, context, remember-me, CSRF hoặc state khác |
| `SecurityContextLogoutHandler` | Invalidate HttpSession, clear holder, Authentication và repository |
| `CsrfLogoutHandler` | Xóa CSRF token |
| `LogoutSuccessEventPublishingLogoutHandler` | Phát LogoutSuccessEvent |
| `LogoutSuccessHandler` | Redirect hoặc tạo response sau cleanup |

Khi CSRF protection được bật (mặc định với cấu hình browser/session), Spring Security yêu cầu POST `/logout` có CSRF token. GET `/logout` hiển thị trang xác nhận logout và có thể cung cấp form chứa CSRF token; nó không trực tiếp thực hiện logout trong cấu hình mặc định có CSRF.

~~~java
@Bean
SecurityFilterChain applicationSecurityFilterChain(HttpSecurity http)
        throws Exception {

    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/logged-out").permitAll()
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .logout(logout -> logout
            .logoutUrl("/logout")
            .invalidateHttpSession(true)
            .clearAuthentication(true)
            .deleteCookies("JSESSIONID")
            .logoutSuccessUrl("/logged-out"));

    return http.build();
}
~~~

Đây là local logout của ứng dụng browser. Nếu cùng application có Authorization Server chain với `/connect/logout`, cần bảo đảm từng SecurityFilterChain match đúng endpoint.

Không tắt CSRF chỉ để cho phép GET logout. Một trang bên ngoài có thể khiến browser gửi GET request và logout user ngoài ý muốn.

### 5.2. Thứ tự xử lý

Với cấu hình mặc định, `LogoutFilter` gọi các `LogoutHandler` trước khi gọi `LogoutSuccessHandler`. Các thao tác thường gồm:

1. Invalidate HTTP session.
2. Clear SecurityContextHolder.
3. Clear SecurityContextRepository.
4. Dọn remember-me authentication.
5. Xóa CSRF token.
6. Phát logout event.
7. Gọi success handler.

Thứ tự chi tiết có thể thay đổi theo handler được thêm vào, nhưng cleanup bắt buộc phải hoàn tất trước khi response báo logout thành công.

### 5.3. Không tạo custom controller chỉ redirect

Ví dụ không đủ:

~~~java
@PostMapping("/my/logout")
String logout() {
    return "redirect:/logged-out";
}
~~~

Đoạn code chỉ redirect; nó không invalidate session hoặc xóa context khỏi repository. Nếu thật sự cần custom endpoint, gọi `SecurityContextLogoutHandler`:

~~~java
@Controller
class CustomLogoutController {

    private final SecurityContextLogoutHandler logoutHandler;

    CustomLogoutController(SecurityContextLogoutHandler logoutHandler) {
        this.logoutHandler = logoutHandler;
    }

    @PostMapping("/my/logout")
    String logout(
            Authentication authentication,
            HttpServletRequest request,
            HttpServletResponse response) {

        logoutHandler.logout(request, response, authentication);
        return "redirect:/logged-out";
    }
}
~~~

Endpoint custom phải được bảo vệ CSRF và authorization phù hợp. Nếu không có yêu cầu đặc biệt, dùng Logout DSL thay vì tự viết controller.

## 6. Vòng đời SecurityContext

### 6.1. SecurityContextHolder

`SecurityContextHolder` là facade để code truy cập `SecurityContext` hiện tại:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
~~~

Với Servlet application, strategy mặc định thường dùng ThreadLocal để giữ context theo request thread. Strategy có thể được thay đổi; không nên giả định mọi ứng dụng đều dùng cùng một strategy.

Context thường chứa Authentication/principal đã xác thực, authorities/roles và authentication details nếu có. Khi request kết thúc, filter lifecycle dọn context khỏi holder để tránh rò rỉ Authentication sang request khác dùng lại thread. Việc dọn holder ở cuối request không tự xóa context đã lưu trong session.

Không lưu SecurityContext trong static field, singleton mutable field hoặc cache dùng chung cho nhiều user.

### 6.2. SecurityContextRepository

`SecurityContextRepository` quyết định nơi Spring Security nạp/lưu context giữa các request.

| Implementation | Hành vi |
| --- | --- |
| `HttpSessionSecurityContextRepository` | Lưu context trong HttpSession |
| `RequestAttributeSecurityContextRepository` | Giữ context trong request attributes cho cùng request/dispatch |
| `DelegatingSecurityContextRepository` | Kết hợp nhiều repository |
| `NullSecurityContextRepository` | Không lưu context để tái sử dụng ở request sau |

Ứng dụng browser login stateful thường lưu context trong HttpSession. Ứng dụng stateless API có thể dùng NullSecurityContextRepository hoặc cơ chế khác.

### 6.3. Spring Security 6 và explicit save

Trong Spring Security 6, `SecurityContextHolderFilter` mặc định đọc context từ repository và đặt vào holder; nó không tự động lưu mọi thay đổi của context. Authentication mechanism muốn giữ context qua request sau phải gọi `SecurityContextRepository.saveContext(...)` khi cần.

~~~java
SecurityContext context =
    SecurityContextHolder.createEmptyContext();

context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);

securityContextRepository.saveContext(context, request, response);
~~~

Logout cũng phải cập nhật repository. Nếu chỉ gọi `SecurityContextHolder.clearContext()` mà không xóa context đã lưu, request sau có thể tải lại Authentication cũ.

## 7. SecurityContextLogoutHandler

### 7.1. Hành vi mặc định

`SecurityContextLogoutHandler` là implementation của `LogoutHandler` để kết thúc HTTP session và dọn SecurityContext.

| Cấu hình | Mặc định | Tác dụng |
| --- | --- | --- |
| `invalidateHttpSession` | `true` | Invalidate session nếu tồn tại |
| `clearAuthentication` | `true` | Xóa Authentication khỏi context cũ |
| `SecurityContextHolderStrategy` | Strategy từ SecurityContextHolder | Clear context hiện tại |
| `SecurityContextRepository` | HttpSessionSecurityContextRepository | Lưu empty context |

Logic chính có thể tóm lược:

~~~java
public void logout(
        HttpServletRequest request,
        HttpServletResponse response,
        Authentication authentication) {

    if (invalidateHttpSession) {
        HttpSession session = request.getSession(false);
        if (session != null) {
            session.invalidate();
        }
    }

    SecurityContext context = securityContextHolderStrategy.getContext();
    securityContextHolderStrategy.clearContext();

    if (clearAuthentication) {
        context.setAuthentication(null);
    }

    SecurityContext emptyContext =
        securityContextHolderStrategy.createEmptyContext();

    securityContextRepository.saveContext(
        emptyContext, request, response);
}
~~~

Đây là bản rút gọn để giải thích hành vi, không phải bản sao đầy đủ của framework.

Handler dùng `request.getSession(false)` để tránh tạo session mới trong quá trình logout. Nó invalidate session nếu cấu hình cho phép, clear holder, xóa Authentication khỏi context cũ và lưu empty context qua repository của handler.

### 7.2. Vì sao clearAuthentication quan trọng?

Một request đồng thời có thể còn giữ reference tới cùng SecurityContext object. Mặc định `clearAuthentication=true` xóa Authentication khỏi context cũ để giảm nguy cơ request khác tiếp tục dùng reference này.

Tuy nhiên logout không tự hủy mọi request hoặc business transaction đã bắt đầu. Các thao tác nhạy cảm cần kiểm tra quyền/session/token state tại thời điểm thực thi.

### 7.3. Dùng cùng SecurityContextRepository

Nếu ứng dụng dùng custom repository, logout handler phải lưu trạng thái rỗng vào repository phù hợp với filter chain. Ví dụ repository kết hợp request attribute và session:

~~~java
@Bean
SecurityContextRepository securityContextRepository() {
    return new DelegatingSecurityContextRepository(
        new RequestAttributeSecurityContextRepository(),
        new HttpSessionSecurityContextRepository());
}
~~~

Gắn repository vào filter chain:

~~~java
http.securityContext(securityContext ->
    securityContext.securityContextRepository(repository));
~~~

Và dùng cùng instance cho logout handler:

~~~java
SecurityContextLogoutHandler logoutHandler =
    new SecurityContextLogoutHandler();

logoutHandler.setSecurityContextRepository(repository);
~~~

`SecurityContextLogoutHandler` mặc định dùng `HttpSessionSecurityContextRepository`. Nếu filter chain dùng repository khác, hãy cấu hình rõ để tránh trường hợp handler xóa ở nơi này nhưng request sau lại đọc context cũ từ nơi khác.

Với `NullSecurityContextRepository` hoặc stateless authentication, xác định rõ có HTTP session nào cần invalidate và token nào cần revoke; không thêm session state chỉ để thực hiện logout.

## 8. SessionRegistry và OIDC logout

### 8.1. Vai trò của SessionRegistry

Khi OIDC được bật, Spring Authorization Server dùng `SessionRegistry` để theo dõi các session đã authenticated. `OidcLogoutAuthenticationProvider` sử dụng registry để tìm `SessionInformation` gắn với End-User đang yêu cầu logout.

`SessionRegistry` không tự thay thế thao tác invalidate HttpSession hoặc clear SecurityContext. Registry giúp tìm session; success handler và LogoutHandler thực hiện cleanup.

Nếu ứng dụng không đăng ký `SessionRegistry` bean, SAS dùng `SessionRegistryImpl` mặc định. Nếu ứng dụng đăng ký `SessionRegistryImpl` riêng, nên đăng ký `HttpSessionEventPublisher` để registry nhận session lifecycle events, ví dụ `SessionDestroyedEvent`, và loại bỏ SessionInformation tương ứng.

~~~java
@Configuration
class SessionRegistryConfiguration {

    @Bean
    SessionRegistry sessionRegistry() {
        return new SessionRegistryImpl();
    }

    @Bean
    HttpSessionEventPublisher httpSessionEventPublisher() {
        return new HttpSessionEventPublisher();
    }
}
~~~

### 8.2. Session registration

Default `SessionAuthenticationStrategy` gắn với Authorization Endpoint của SAS đăng ký session đã xác thực. Nếu ứng dụng thay custom authentication flow hoặc session strategy, phải bảo đảm session vẫn được đăng ký vào registry mà OIDC Logout provider sử dụng.

Nếu Spring Security Concurrent Session Control cũng được dùng, nên chia sẻ cùng `SessionRegistry` để concurrent session management và OIDC logout nhìn thấy trạng thái nhất quán.

~~~java
http.sessionManagement(session -> session
    .maximumSessions(3)
    .sessionRegistry(sessionRegistry));
~~~

Đây là fragment cho browser login SecurityFilterChain. Không giả định chỉ khai báo một bean SessionRegistry là đủ để mọi custom authentication flow tự đăng ký session.

### 8.3. Principal và tenant mapping

Registry theo dõi principal/session. Nếu ứng dụng dùng pairwise subject, nhiều issuer hoặc multi-tenant, phải thống nhất cách ánh xạ principal giữa Authentication, SessionRegistry và ID Token. Hai tenant có thể có cùng username; không để logout ở tenant này đóng session của tenant khác.

## 9. Cookie, remember-me và CSRF

### 9.1. Invalidate session khác xóa cookie

`HttpSession.invalidate()` kết thúc session server-side. Browser có thể vẫn gửi cookie session cũ trong request sau, nhưng session ID đó không còn ánh xạ tới session hợp lệ.

Xóa cookie `JSESSIONID` là thao tác phía browser. Khi cần, cookie phải được xóa với Path/Domain tương thích cookie ban đầu. Invalidate session server-side vẫn là bước quyết định.

### 9.2. Remember-me

Nếu ứng dụng bật remember-me, phải dọn remember-me cookie/token. Nếu chỉ invalidate HttpSession nhưng giữ remember-me credential, browser có thể được xác thực lại tự động.

Spring Security có handler phù hợp cho `TokenRememberMeServices` hoặc `PersistentTokenBasedRememberMeServices`; dùng Logout DSL để các handler mặc định được phối hợp.

### 9.3. CSRF token

`CsrfLogoutHandler` xóa CSRF token đã lưu. Trang tiếp theo cần lấy token mới theo repository/policy. Không tái sử dụng CSRF token cũ của session đã kết thúc.

### 9.4. Clear-Site-Data

Một số browser application có thể dùng header `Clear-Site-Data` để yêu cầu browser xóa cache/cookies/storage trong phạm vi phù hợp. Đây là lựa chọn có tác động rộng; không xóa storage hoặc cache nếu ứng dụng cần giữ dữ liệu client-side. Header này không thay thế invalidate session hoặc token revocation.

## 10. Concurrent requests, expiration và async tasks

### 10.1. Request đồng thời với logout

Giả sử request A đang đọc dữ liệu trong khi request B thực hiện logout. A có thể đã nạp Authentication vào context và bắt đầu xử lý trước khi B clear context.

`SecurityContextLogoutHandler` mặc định xóa Authentication khỏi context object cũ, giúp giảm một số rủi ro với reference được chia sẻ. Nhưng logout không tự dừng mọi request đang chạy, không rollback transaction đã commit và không hủy business task đã được gửi đi.

Với thao tác nhạy cảm, kiểm tra lại quyền/session/token state ngay trước side effect quan trọng.

### 10.2. expireNow khác invalidate ngay

`SessionInformation.expireNow()` đánh dấu session là expired. `ConcurrentSessionFilter` có thể phát hiện trạng thái đó ở request tiếp theo và chạy logout handling. Việc đánh dấu expired không nhất thiết đồng nghĩa `HttpSession.invalidate()` được gọi đồng bộ ngay tại thời điểm đánh dấu.

Nếu yêu cầu kết thúc session ngay, cần bảo đảm có thao tác invalidation/handler phù hợp. Không giả định OIDC Logout Provider luôn dùng cùng cách xử lý với concurrent session control; kiểm tra provider version và integration test.

### 10.3. SecurityContext được propagate sang executor

Spring Security cung cấp wrapper như `DelegatingSecurityContextRunnable` và `DelegatingSecurityContextExecutor` để propagate context sang task khác. Một task đã được chạy với context được propagate có thể tiếp tục sau khi request logout kết thúc.

Không dùng SecurityContext snapshot làm bằng chứng authorization vô thời hạn. Với background task nhạy cảm, cần cancellation policy hoặc re-check quyền/session/token state tại thời điểm thực thi.

## 11. Multi-instance Authorization Server

`SessionRegistryImpl` mặc định là registry trong bộ nhớ của một application instance. Trong cluster:

- User login vào node A.
- Logout request được route tới node B.
- Registry của B có thể không biết session đăng ký ở A.
- Session store và registry local có thể không đồng bộ.
- Node restart có thể làm mất registry entries trong khi shared session vẫn còn.

~~~mermaid
flowchart LR
    B["Browser"] --> LB["Load Balancer"]
    LB --> A["Authorization Server Node A"]
    LB --> C["Authorization Server Node B"]
    A --> S["Shared Session Store"]
    C --> S
    A --> R["Shared Session Registry"]
    C --> R
~~~

### 11.1. Shared session store

Spring Session với Redis/JDBC hoặc giải pháp distributed session phù hợp giúp nhiều node truy cập cùng session state. Khi một node invalidate session, node khác phải nhìn thấy session đã hết hiệu lực.

`SpringSessionBackedSessionRegistry` có thể được dùng cho concurrent session/session lookup trong các tích hợp Spring Session phù hợp. Cần xác minh version và cách SAS OIDC logout sử dụng registry; shared session store tự nó không biến mọi `SessionRegistryImpl` local thành distributed registry.

### 11.2. Đồng bộ registry và session store

Kiểm tra:

1. Session được đăng ký sau authentication trên mọi node.
2. Session destroy/expire được phản ánh tới registry.
3. OIDC Logout provider dùng đúng registry.
4. Node khác không thể tải SecurityContext từ session đã invalidated.
5. Cache/session metadata không giữ Authentication cũ vượt quá policy.
6. Stale registry entries có TTL/lifecycle cleanup.
7. Logout request ở node khác vẫn tìm đúng user/session/tenant.

Sticky session chỉ giảm khả năng request đi sang node khác; nó không thay thế shared state khi cần failover hoặc rolling deployment.

## 12. Stateless API, JWT và token revocation

Resource Server stateless nhận access token trong mỗi request:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN
~~~

Trong mô hình này, Spring Security tạo SecurityContext cho request sau khi token được xác thực rồi dọn context khi request kết thúc. Không có browser session tại Resource Server để invalidate.

Gọi `SecurityContextHolder.clearContext()` chỉ dọn context hiện tại. Client vẫn có thể gửi lại JWT trong request sau và Resource Server sẽ xác minh lại token.

Nếu cần ngăn token được sử dụng trước expiry, cân nhắc:

- Token Revocation Endpoint theo RFC 7009 nếu token type/implementation hỗ trợ.
- Opaque/reference token và introspection.
- Denylist theo `jti` hoặc token hash, có propagation và cache policy.
- Event invalidation cho các Resource Server.
- Access token TTL ngắn.
- Thu hồi refresh token để chặn cấp access token mới.

OIDC logout cũng không tự động xóa consent hoặc OAuth2 authorization record. Không xóa UserDetails, account hoặc audit records chỉ vì user logout; những dữ liệu này có vòng đời riêng.

## 13. Front-Channel và Back-Channel Logout

RP-Initiated Logout là RP chủ động yêu cầu OP kết thúc session. Front-Channel và Back-Channel Logout là cơ chế OP thông báo cho RP khác khi session kết thúc.

### 13.1. Front-Channel Logout

OP dùng browser để thông báo tới các RP tham gia. Cơ chế này phụ thuộc browser navigation/iframe, cookie policy và trình duyệt có thể chặn third-party cookies. RP phải xác định local session liên quan và cleanup đúng.

### 13.2. Back-Channel Logout

OP gửi Logout Token tới Back-Channel Logout URI đã đăng ký của RP. RP xác minh chữ ký, issuer, audience, event claim và session/subject conditions rồi xóa local session tương ứng.

Logout Token là JWT theo Back-Channel Logout profile; nó không phải access token để gọi API và không phải ID Token được gửi tới UserInfo.

### 13.3. Session correlation

RP cần mapping phù hợp giữa issuer (`iss`), subject (`sub`), session ID (`sid`) nếu profile phát hành, local application session ID và client/tenant context.

Không chỉ dựa vào username/email vì các giá trị này có thể đổi hoặc trùng. Nếu dùng pairwise subject, mapping phải đúng client/sector.

### 13.4. Không suy luận tính năng từ OIDC enablement

Spring Authorization Server cung cấp RP-Initiated Logout Endpoint. Front-Channel và Back-Channel Logout là các profile riêng; không suy ra chúng tự động được bật chỉ vì gọi `oidc(Customizer.withDefaults())`. Kiểm tra tính năng framework, RP support và notification handler thực tế.

## 14. Cấu hình tham khảo kết hợp

Ví dụ sau minh họa cách dùng chung `SecurityContextRepository` giữa Authorization Server chain và OIDC logout handler. Ứng dụng thực tế cần các bean core khác, login chain, issuer/JWK và persistence.

~~~java
@Configuration(proxyBeanMethods = false)
class AuthorizationServerLogoutConfiguration {

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new DelegatingSecurityContextRepository(
            new RequestAttributeSecurityContextRepository(),
            new HttpSessionSecurityContextRepository());
    }

    @Bean
    SessionRegistry sessionRegistry() {
        return new SessionRegistryImpl();
    }

    @Bean
    HttpSessionEventPublisher httpSessionEventPublisher() {
        return new HttpSessionEventPublisher();
    }

    @Bean
    OidcLogoutAuthenticationSuccessHandler oidcLogoutSuccessHandler(
            SecurityContextRepository repository) {

        SecurityContextLogoutHandler logoutHandler =
            new SecurityContextLogoutHandler();

        logoutHandler.setSecurityContextRepository(repository);

        OidcLogoutAuthenticationSuccessHandler successHandler =
            new OidcLogoutAuthenticationSuccessHandler();

        successHandler.setLogoutHandler(logoutHandler);
        return successHandler;
    }

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurity(
            HttpSecurity http,
            SecurityContextRepository repository,
            OidcLogoutAuthenticationSuccessHandler successHandler)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .securityContext(securityContext ->
                securityContext.securityContextRepository(repository))
            .with(authorizationServer, as ->
                as.oidc(oidc ->
                    oidc.logoutEndpoint(logout ->
                        logout.logoutResponseHandler(successHandler))
                ))
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated());

        return http.build();
    }
}
~~~

Các điểm cần kiểm tra khi áp dụng:

- Repository trong AS chain và logout handler là cùng instance.
- SessionRegistry mà OIDC provider dùng là registry đã được cấu hình.
- Nếu dùng concurrent session control, chia sẻ registry.
- Nếu chạy cluster, chọn shared session/registry strategy.
- Nếu default success handler đã đáp ứng yêu cầu, không thay chỉ để lặp lại cleanup.
- Nếu thêm custom handler, không bỏ redirect validation, OIDC response handling hoặc session cleanup.
- Không coi fragment trên là toàn bộ cấu hình Authorization Server.

## 15. Kiểm thử logout và SecurityContext cleanup

### 15.1. Kiểm thử local logout

Với MockMvc, cần xác minh không chỉ redirect mà cả session cũ và request kế tiếp. Một test body minh họa:

~~~java
@Test
void logoutEndsAuthenticatedSession() throws Exception {
    MvcResult loginResult = mockMvc.perform(
            formLogin().user("alice").password("password"))
        .andExpect(authenticated())
        .andReturn();

    MockHttpSession session =
        (MockHttpSession) loginResult.getRequest().getSession(false);

    assertThat(session).isNotNull();

    mockMvc.perform(post("/logout")
            .session(session)
            .with(csrf()))
        .andExpect(status().is3xxRedirection());

    assertThat(session.isInvalid()).isTrue();
}
~~~

Test cần cấu hình form login, user fixture, MockMvc và CSRF. Sau đó gửi request protected bằng cookie/session cũ để xác nhận user không còn authenticated. Chỉ dùng `with(user("alice"))` cho một request không chứng minh context đã lưu trong session được dọn.

### 15.2. Kiểm thử SecurityContextLogoutHandler

~~~java
@Test
void logoutHandlerClearsAuthenticationAndSession() {
    SecurityContext context =
        SecurityContextHolder.createEmptyContext();

    context.setAuthentication(
        new TestingAuthenticationToken("alice", "n/a", "ROLE_USER"));

    SecurityContextHolder.setContext(context);

    MockHttpServletRequest request = new MockHttpServletRequest();
    MockHttpSession session = (MockHttpSession) request.getSession(true);

    SecurityContextLogoutHandler handler =
        new SecurityContextLogoutHandler();

    handler.logout(
        request,
        new MockHttpServletResponse(),
        context.getAuthentication());

    assertThat(SecurityContextHolder.getContext().getAuthentication())
        .isNull();

    assertThat(context.getAuthentication()).isNull();
    assertThat(session.isInvalid()).isTrue();
}
~~~

Đây là test body minh họa. Để xác minh repository persistence, inject cùng `SecurityContextRepository` vào handler rồi kiểm tra trạng thái sau logout; không chỉ assert holder đã clear.

### 15.3. Kiểm thử OIDC Logout Endpoint

Thiết lập:

- OIDC configurer đã bật.
- RegisteredClient có post-logout URI hợp lệ.
- ID Token hint được phát hành bởi đúng OP.
- Session/authorization record tương ứng.
- SessionRegistry được populate.
- OIDC success handler và LogoutHandler được cấu hình.
- SecurityContextRepository được chia sẻ đúng.

Kỳ vọng:

1. Request hợp lệ được provider xác minh.
2. Success handler gọi LogoutHandler.
3. HttpSession liên quan bị invalidate.
4. SecurityContextHolder không còn Authentication.
5. Repository không trả lại Authentication cũ.
6. Redirect chỉ tới URI đã đăng ký.
7. Request tiếp theo không được xác thực lại bằng session cũ.

### 15.4. Ma trận kiểm thử

| Tình huống | Kết quả mong đợi |
| --- | --- |
| POST local logout có CSRF | LogoutHandler chạy, session invalidated |
| POST local logout thiếu CSRF | Bị từ chối khi CSRF bật |
| Chỉ gọi clearContext | Test chứng minh repository có thể nạp lại context; không coi là đủ |
| SecurityContextLogoutHandler dùng đúng repository | Empty context được lưu |
| Handler dùng repository khác filter chain | Test phát hiện context cũ còn tồn tại |
| Cookie JSESSIONID cũ được gửi lại | Session không còn hợp lệ |
| Remember-me bật | Token/cookie được dọn |
| OIDC metadata | Có end_session_endpoint khi OIDC logout/discovery được bật |
| ID Token hint sai issuer | OP không xử lý dựa trên token đó |
| Client ID mismatch | Logout request bị từ chối |
| post_logout_redirect_uri không đăng ký | Không redirect tới URI đó |
| State sai hoặc replay | RP từ chối callback |
| SessionRegistry có session | Provider tìm được SessionInformation |
| SessionRegistry thiếu entry | Test phát hiện integration/session strategy thiếu |
| Session invalidated | Registry nhận lifecycle event |
| Login node A, logout node B | Node B nhìn thấy shared session/registry state |
| Hai RP cùng dùng SSO | Local logout ở một RP không tự xóa OP session |
| OP logout thành công | Token state được kiểm tra riêng |
| JWT access token sau logout | Không giả định JWT tự mất hiệu lực |
| Async task đã nhận context | Có policy riêng về cancellation/revalidation |
| Multi-tenant cùng username | Chỉ session đúng issuer/tenant bị kết thúc |

## 16. Troubleshooting và vận hành

### 16.1. Triệu chứng và nguyên nhân

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Logout redirect thành công nhưng user vẫn đăng nhập | Chỉ redirect, chưa invalidate session | Kiểm tra LogoutHandler và success handler |
| Request sau logout vẫn authenticated | Repository còn context cũ | Dùng cùng repository và save empty context |
| Holder đã clear nhưng session còn | Chỉ gọi clearContext | Invalidate HttpSession |
| Session invalid nhưng registry còn entry | Thiếu lifecycle event | Kiểm tra HttpSessionEventPublisher |
| Logout node khác không tìm thấy session | SessionRegistry local | Shared session/registry |
| RP khác vẫn login | Chưa triển khai logout notification | Front-/Back-Channel Logout |
| API vẫn nhận JWT | Token chưa revoke hoặc RS verify offline | Introspection/denylist/TTL/revocation |
| /connect/logout trả 404 | OIDC chưa bật hoặc path khác | OIDC configurer và AuthorizationServerSettings |
| Discovery thiếu end_session_endpoint | OIDC metadata chưa công bố | Kiểm tra Provider Configuration |
| Redirect bị từ chối | URI chưa đăng ký hoặc không exact match | Kiểm tra RegisteredClient |
| Remember-me tự login lại | Cookie/token chưa được dọn | Cấu hình remember-me logout handler |
| Background task vẫn chạy | Task đã nhận context trước logout | Cancellation và authorization re-check |
| Cookie cũ còn ở browser | Path/domain không khớp hoặc cookie chưa xóa | Kiểm tra cookie attributes |

### 16.2. Runbook khi session không kết thúc

1. Xác định request đi vào local `LogoutFilter` hay OIDC `OidcLogoutEndpointFilter`.
2. Kiểm tra filter chain và endpoint matcher.
3. Kiểm tra OIDC provider xác minh request thành công.
4. Kiểm tra success handler thực tế và LogoutHandler có chạy không.
5. Kiểm tra `request.getSession(false)` trước/sau cleanup.
6. Kiểm tra SecurityContextHolder sau logout.
7. Kiểm tra repository được dùng để load context ở request kế tiếp.
8. Kiểm tra SessionRegistry mapping và lifecycle event.
9. Với cluster, kiểm tra session ID/principal có được nhìn thấy trên các node.
10. Nếu API vẫn nhận token, kiểm tra token revocation/introspection/denylist riêng.
11. Nếu RP khác còn login, kiểm tra Front-/Back-Channel Logout và local session mapping.
12. Ghi nhận thời gian từ logout đến khi từng thành phần ngừng chấp nhận trạng thái cũ.

Không khắc phục bằng cách chỉ redirect về login page hoặc xóa một cookie mà không xác minh server-side state.

### 16.3. Metrics và audit

Theo dõi logout success/failure theo client và endpoint, session invalidation latency, SessionRegistry lookup miss/stale entries, số request dùng session ID đã hết hạn, OIDC hint validation failures, tỷ lệ redirect bị từ chối, distributed session propagation delay và thời gian Resource Server ngừng chấp nhận token sau revocation.

Không log ID Token, access token, refresh token, session cookie hoặc toàn bộ Logout Request. Dùng correlation ID, client ID, issuer, mã lỗi và identifier đã được bảo vệ.

## 17. Những sai lầm thiết kế cần tránh

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Chỉ gọi `SecurityContextHolder.clearContext()` | Repository vẫn có thể chứa context cũ | Save empty context |
| Chỉ invalidate session | Reference context hiện tại có thể còn Authentication | Clear holder và Authentication |
| Chỉ xóa cookie | Session server-side vẫn tồn tại | Invalidate HttpSession |
| Custom controller chỉ redirect | User vẫn authenticated | Gọi LogoutHandler hoặc dùng Logout DSL |
| Handler dùng repository khác filter chain | Request sau nạp lại context cũ | Dùng cùng repository |
| Tạo session mới khi logout | Để lại session mới ngoài ý muốn | Dùng getSession(false) |
| Coi SessionRegistry là session store | Không invalidate HttpSession | Kết hợp LogoutHandler |
| Dùng SessionRegistryImpl local trong cluster | Node khác không thấy session | Shared registry/session strategy |
| Không đăng ký HttpSessionEventPublisher khi cần | Registry giữ stale entries | Đăng ký lifecycle publisher |
| Tắt clearAuthentication không có lý do | Request đồng thời có thể giữ Authentication reference | Giữ default và kiểm thử |
| Coi logout OP tự logout mọi RP | Local session RP khác còn tồn tại | Front-/Back-Channel Logout |
| Coi logout OP tự revoke JWT | API vẫn nhận token còn hạn | Token revocation policy |
| Coi clear context là hủy async task | Task đang chạy tiếp tục | Cancellation/re-check authorization |
| Custom success handler chỉ redirect | Không cleanup session/context | Giữ LogoutHandler trong success flow |
| Tắt CSRF local logout | Logout CSRF | Dùng POST + CSRF |

## 18. Câu hỏi tự kiểm tra

**Câu 1.** `SecurityContextHolder` và `SecurityContextRepository` khác nhau thế nào?

**Đáp án:** Holder cung cấp context cho request/thread hiện tại; repository lưu/nạp context giữa các request.

**Câu 2.** Vì sao chỉ gọi `SecurityContextHolder.clearContext()` chưa đủ?

**Đáp án:** Context cũ có thể vẫn được lưu trong repository/session và được nạp lại ở request sau.

**Câu 3.** `SecurityContextLogoutHandler` mặc định làm gì?

**Đáp án:** Invalidate HttpSession nếu có, clear holder, xóa Authentication khỏi context cũ và lưu empty context qua repository của handler.

**Câu 4.** Vì sao handler cần dùng cùng repository với SecurityFilterChain?

**Đáp án:** Nếu không, handler có thể lưu empty context vào nơi khác trong khi filter vẫn đọc Authentication cũ từ repository ban đầu.

**Câu 5.** Spring Security 6 thay đổi gì về SecurityContext persistence?

**Đáp án:** `SecurityContextHolderFilter` mặc định đọc context; ứng dụng cần explicit save khi muốn lưu thay đổi. Logout cũng phải lưu trạng thái rỗng.

**Câu 6.** `SessionRegistry` có tự invalidate HttpSession không?

**Đáp án:** Không. Registry theo dõi/tra cứu session information; LogoutHandler thực hiện session/context cleanup.

**Câu 7.** Vì sao đăng ký HttpSessionEventPublisher?

**Đáp án:** Để SessionRegistryImpl nhận session lifecycle events như SessionDestroyedEvent và dọn SessionInformation tương ứng.

**Câu 8.** SAS OIDC logout khác `POST /logout` thế nào?

**Đáp án:** OIDC logout dùng OIDC endpoint filter/provider và SessionRegistry để xử lý RP-Initiated Logout; local logout dùng Spring Security LogoutFilter và LogoutHandler chain.

**Câu 9.** Logout có tự thu hồi access token JWT không?

**Đáp án:** Không. JWT có thể vẫn hợp lệ tới expiry nếu Resource Server không có revocation check.

**Câu 10.** Vì sao async task có thể tiếp tục sau logout?

**Đáp án:** Task có thể đã nhận SecurityContext hoặc bắt đầu thực thi; clear context của request không tự hủy task.

**Câu 11.** SessionRegistryImpl có phù hợp cluster nhiều node không?

**Đáp án:** Registry in-memory không tự chia sẻ giữa các node. Cần shared registry/session tracking phù hợp.

**Câu 12.** Cách kiểm thử logout đúng là chỉ assert redirect không?

**Đáp án:** Không. Phải xác minh session invalidated, holder cleared, repository không phục hồi Authentication và request sau không còn được xác thực bằng session cũ.

## 19. Checklist triển khai production

- [ ] Phân biệt RP local session, OP session, HttpSession, SecurityContext và SessionRegistry.
- [ ] OIDC Logout Endpoint được bật và route đúng trong AS SecurityFilterChain.
- [ ] OP công bố end_session_endpoint trong metadata.
- [ ] ID Token hint được xác minh từ đúng issuer/client/session.
- [ ] post_logout_redirect_uri được đăng ký riêng và exact-match.
- [ ] RP tạo, lưu và xác minh state one-time.
- [ ] Local logout dùng LogoutFilter/LogoutHandler chuẩn.
- [ ] Local logout POST giữ CSRF protection.
- [ ] SecurityContextHolder được clear.
- [ ] Authentication được xóa khỏi context cũ khi phù hợp.
- [ ] Empty context được lưu qua đúng SecurityContextRepository.
- [ ] Handler và filter chain dùng cùng custom repository.
- [ ] Không tạo session mới trong quá trình logout.
- [ ] Remember-me, CSRF và cookie được dọn theo policy.
- [ ] SessionRegistry nhận lifecycle events.
- [ ] Concurrent session control chia sẻ registry khi cần.
- [ ] Multi-instance deployment có shared session tracking.
- [ ] Custom success handler không bỏ qua cleanup.
- [ ] Async task có policy cancellation/revalidation riêng.
- [ ] Logout OP được phân biệt với RP notifications và token revocation.
- [ ] Có integration tests xác minh session, holder, repository và request sau logout.
- [ ] Có monitoring cho logout failures, session registry misses và stale sessions.
- [ ] Audit không ghi raw token, cookie hoặc credential.

## 20. Tài liệu tham khảo và kết luận

- [OpenID Connect RP-Initiated Logout 1.0 Final](https://openid.net/specs/openid-connect-rpinitiated-1_0-final.html)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [OpenID Connect Front-Channel Logout 1.0](https://openid.net/specs/openid-connect-frontchannel-1_0.html)
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — Core Model / SessionRegistry](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server 1.5.8 — OidcLogoutAuthenticationProvider API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcLogoutAuthenticationProvider.html)
- [Spring Authorization Server 1.5.8 — OidcLogoutAuthenticationSuccessHandler API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/web/authentication/OidcLogoutAuthenticationSuccessHandler.html)
- [Spring Authorization Server 1.5.8 — OidcLogoutEndpointConfigurer API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OidcLogoutEndpointConfigurer.html)
- [Spring Security 6.5 — Handling Logouts](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html)
- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — SecurityContextLogoutHandler API](https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/web/authentication/logout/SecurityContextLogoutHandler.html)
- [Spring Session — Session Registry integrations](https://docs.spring.io/spring-session/reference/api.html)

**Kết luận:** Kết thúc phiên Authorization Server cần phối hợp HTTP session, `SecurityContextHolder`, `SecurityContextRepository` và `SessionRegistry`. Trong Spring Authorization Server, OIDC Logout Endpoint đi qua converter/provider; provider dùng SessionRegistry để tìm phiên End-User và success handler thực hiện cleanup qua LogoutHandler. `SecurityContextLogoutHandler` giúp invalidate session, clear holder, xóa Authentication khỏi context cũ và lưu empty context. Với Spring Security 6, việc lưu trạng thái rỗng đặc biệt quan trọng vì `SecurityContextHolderFilter` mặc định đọc context mà không tự lưu mọi thay đổi. Production cần giữ repository đồng bộ, cập nhật SessionRegistry, xử lý distributed session và phân biệt OP logout với local RP session, logout notifications và token revocation. Chỉ khi các trạng thái này được kiểm thử cùng nhau, hệ thống mới tránh tình trạng browser đã thấy trang logout nhưng request sau vẫn khôi phục Authentication cũ.

