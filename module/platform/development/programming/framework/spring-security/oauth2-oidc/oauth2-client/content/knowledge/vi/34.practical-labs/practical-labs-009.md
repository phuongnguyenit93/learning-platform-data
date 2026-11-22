# 34.9. Đăng xuất OIDC và thu hồi dữ liệu authorized client

## 1. Bài toán thực hành

Ứng dụng Spring Boot đóng vai trò **OAuth2/OIDC Client**. Người dùng đăng nhập qua OpenID Provider (OP) bằng Authorization Code Flow; Spring Security duy trì session và lưu <code>OAuth2AuthorizedClient</code> chứa access token/refresh token để gọi API.

Người dùng bấm **Đăng xuất**, Portal không còn hiển thị hồ sơ. Tuy nhiên:

- Bấm đăng nhập lại thì OP lập tức đưa user vào mà không hỏi mật khẩu.
- JDBC token store vẫn giữ <code>OAuth2AuthorizedClient</code> của người dùng.
- Một scheduled job vẫn có thể load refresh token và gọi API.
- Xóa local authorized client nhưng refresh token vẫn có thể được OP chấp nhận.
- User dùng hai provider registrations; logout chỉ dọn một record.
- Test <code>oidcLogin()</code> xanh nhưng không chạy logout flow thật.

Đây không nhất thiết là một bug duy nhất. **Logout local**, **OP SSO logout**, **xóa authorized-client storage** và **token revocation** có ý nghĩa và phạm vi khác nhau.

> **Mục tiêu:** Xây dựng chức năng đăng xuất Servlet có CSRF, cleanup authorized-client data đúng principal, tùy chọn RP-Initiated Logout tại OP và thiết kế kiểm thử đủ để chứng minh từng lớp hành động. Không dùng production accounts/tokens để thực hành.

## 2. Kết quả cần đạt

Sau lab, bạn có thể:

1. Phân biệt <code>SecurityContext</code>, HTTP session, OP SSO session, <code>OAuth2AuthorizedClient</code> và authorization grant.
2. Dùng Spring Security LogoutFilter xử lý POST <code>/logout</code> có CSRF.
3. Cấu hình <code>OidcClientInitiatedLogoutSuccessHandler</code> khi OP hỗ trợ RP-Initiated Logout.
4. Xóa authorized clients qua <code>OAuth2AuthorizedClientService</code> theo trusted registration IDs/principal name.
5. Xác định khi nào dữ liệu nằm trong <code>OAuth2AuthorizedClientRepository</code> gắn HTTP session thay vì service store.
6. Phân biệt local removal và **OAuth2 Token Revocation RFC 7009**.
7. Quản lý <code>post_logout_redirect_uri</code>, OIDC <code>id_token_hint</code> và OP logout metadata.
8. Kiểm thử nhiều registrations, user switching, cluster session, refresh-token rotation.
9. Viết unit/MockMvc/integration tests và troubleshooting checklist.
10. Chọn failure policy, telemetry và bảo vệ dữ liệu credentials.

## 3. Công nghệ và phạm vi

Các ví dụ tập trung vào **Java 17, Spring Boot 3.x, Spring Security 6.x, Spring MVC/Servlet**. Với Spring Security 7.x hoặc OP khác, đối chiếu đúng API/version vì cấu hình logout và test support có thể thay đổi.

| Thành phần | Vai trò |
|---|---|
| Spring Boot Web | HTTP endpoints / session |
| Spring Security OAuth2 Client | OIDC Login, authorized-client management |
| OpenID Provider test | Authorization Code và OP SSO logout |
| OAuth2AuthorizedClientService | Store theo registration ID + principal name |
| OAuth2AuthorizedClientRepository | Store/delegation theo Servlet request |
| MockMvc + Spring Security Test | Test CSRF/session/logout/redirect |
| Browser test | Kiểm tra SSO cookie của OP và callback redirect |
| JDBC/Redis test store | Kiểm tra persistence và cluster |

Trong bài, registration đăng nhập là <code>company</code>. Registration tùy chọn thứ hai tên <code>partner</code> giúp kiểm thử cleanup nhiều integrations.

## 4. Năm lớp trạng thái của một login

| Thành phần | Nơi lưu | Logout local có mặc nhiên dọn? |
|---|---|---|
| <code>SecurityContext</code> | Request/session repository | Thường có |
| HTTP session của Portal | Servlet container/Spring Session | Thường được invalidate |
| <code>OAuth2AuthorizedClient</code> | Session, memory service, JDBC, Redis, custom | **Phụ thuộc cách lưu và cleanup** |
| OP SSO session | Cookie/session tại OP | **Không** |
| OP grant / token validity | Authorization Server | **Không** |

### 4.1. SecurityContext và HttpSession

Sau OIDC Login:

~~~text
Authentication: OAuth2AuthenticationToken
Principal:      OidcUser
Registration:   company
Session:        authenticated browser session
~~~

Spring Security local logout có thể invalidate HTTP session, clear <code>SecurityContext</code> và điều hướng tới trang sau logout. Điều này ngăn browser tiếp tục truy cập protected routes bằng session cũ.

### 4.2. Authorized client là một nguồn credentials riêng

<code>OAuth2AuthorizedClient</code> liên kết:

~~~text
ClientRegistration
Principal name
OAuth2AccessToken
OAuth2RefreshToken (optional)
~~~

Nếu store là JDBC hoặc Redis, việc xóa HTTP session không mặc nhiên xóa record đó. Backend job có thể vẫn load được token nếu không có policy cleanup.

### 4.3. OP SSO session không thuộc Portal

~~~text
portal.example.org  → browser cookie do Portal quản lý
sso.example.org     → SSO cookie do OP quản lý
~~~

Xóa Portal session không xóa cookie ở domain OP. Vì thế login lại có thể xảy ra mà user không nhập mật khẩu.

### 4.4. Token đã phát hành không tự mất hiệu lực

Một JWT access token có thể tiếp tục được Resource Server chấp nhận tới khi <code>exp</code> hoặc một revocation/denylist mechanism phù hợp bắt đầu có hiệu lực. Xóa local token store **không thông báo** cho mọi Resource Server rằng token phải bị từ chối.

### 4.5. Xóa local token và remote revocation khác nhau

~~~text
removeAuthorizedClient(...)
    → xóa bản ghi do Portal giữ

POST revocation_endpoint token=... (nếu OP hỗ trợ)
    → yêu cầu OP thu hồi token/grant theo RFC 7009 và policy
~~~

Không gộp hai thao tác vào một khẳng định “đã revoke hoàn toàn”.

## 5. Sơ đồ luồng đăng xuất nhiều lớp

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Browser
    participant RP as Portal /logout
    participant Store as AuthorizedClientService
    participant OP as OpenID Provider
    U->>B: Chọn đăng xuất
    B->>RP: POST /logout + CSRF + session cookie
    RP->>RP: Xác định authenticated principal
    RP->>Store: Dọn authorized-client records theo policy
    Store-->>RP: Local cleanup result
    RP->>RP: Clear SecurityContext / invalidate session
    RP-->>B: Redirect tới OP end_session_endpoint
    B->>OP: RP-Initiated Logout request
    OP->>OP: Kết thúc OP SSO session theo chính sách
    OP-->>B: Redirect tới post_logout_redirect_uri
    B->>RP: GET /logged-out
    RP-->>B: Public logged-out page
~~~

**Về thứ tự:** Spring Security LogoutFilter gọi các <code>LogoutHandler</code> rồi <code>LogoutSuccessHandler</code>. Thứ tự giữa built-in handler và custom handler có thể ảnh hưởng thao tác phụ thuộc session. Lab này cleanup **service-backed store** bằng <code>Authentication</code> được truyền vào handler, không dựa vào session còn sống sau invalidation.

### 5.1. Một lớp khác: token revocation

Nếu yêu cầu thu hồi refresh token tại OP:

~~~text
Load current authorized client
→ optional server-to-server RFC 7009 revocation
→ remove local record
→ local logout
→ optional RP-Initiated Logout
~~~

Thứ tự, timeout, retry và failure policy phải được xác định theo sản phẩm; không có một giao dịch nguyên tử phân tán tự động.

## 6. Cấu hình lab

### 6.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Khi chuyển sang JDBC storage, cần Spring JDBC + driver phù hợp. Khi dùng Redis/Spring Session, cần dependencies được dự án quản lý. Không thêm database chỉ để chạy unit test cleanup.

### 6.2. application.yml

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: portal-it
            client-secret: ${TEST_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
        provider:
          company:
            issuer-uri: https://sso.test.example/realms/company
~~~

Đây là ví dụ cho **OP test**, không phải issuer hoặc client có sẵn. Thực tế cần OP test, test account, callback URL đăng ký chính xác và HTTPS/trust phù hợp. Client secret đến từ test secret store; không dùng secret production.

### 6.3. Login callback

Nếu public URL của Portal là:

~~~text
https://portal.test.example
~~~

OP phải đăng ký:

~~~text
https://portal.test.example/login/oauth2/code/company
~~~

### 6.4. Post-logout redirect

Một trang đích public:

~~~text
https://portal.test.example/logged-out
~~~

có thể phải được OP cho phép **riêng với login callback**. Không dùng browser parameter tùy ý để xây <code>post_logout_redirect_uri</code>.

## 7. OIDC RP-Initiated Logout

Nếu OP hỗ trợ, metadata OIDC Discovery có thể chứa:

~~~json
{
  "issuer": "https://sso.test.example/realms/company",
  "end_session_endpoint": "https://sso.test.example/realms/company/protocol/openid-connect/logout"
}
~~~

Đây là JSON minh họa; đường dẫn thực phụ thuộc provider. Không tự đoán <code>end_session_endpoint</code> hoặc nhầm nó với Token Revocation Endpoint.

### 7.1. Các tham số thường gặp

~~~text
id_token_hint
post_logout_redirect_uri
state (logout state, nếu dùng)
client_id (theo OP/profile)
~~~

<code>id_token_hint</code> là ID Token có thể chứa PII và metadata authentication. Không log full URL chuyển browser tới OP nếu có <code>id_token_hint</code>. Việc OP xóa session, chọn account hoặc điều hướng sau logout phụ thuộc provider policy.

### 7.2. Login callback khác logout endpoint

~~~text
Authorization initiation: /oauth2/authorization/company
Login callback:            /login/oauth2/code/company
Portal logout action:      POST /logout
OP logout:                 end_session_endpoint
Portal landing page:       /logged-out
~~~

Không cấu hình cùng một route làm tất cả các vai trò.

### 7.3. Spring Security handler

Trong Servlet stack:

~~~java
org.springframework.security.oauth2.client.oidc.web.logout
    .OidcClientInitiatedLogoutSuccessHandler
~~~

Handler dùng <code>ClientRegistrationRepository</code>, thông tin OP và authentication chứa <code>OidcUser</code> để tạo redirect tới OP khi điều kiện phù hợp.

### 7.4. OP logout và local logout không đồng nhất

Nếu browser không theo redirect, OP unavailable hoặc OP không hỗ trợ end-session endpoint, **local logout có thể đã hoàn tất** nhưng OP SSO session vẫn hoạt động. Test và telemetry phải tách hai kết quả.

## 8. CSRF và LogoutFilter

Với browser session, logout là hành động làm thay đổi trạng thái bảo mật. Nên dùng **POST với CSRF protection**:

~~~text
POST /logout
Cookie: session...
CSRF: token theo repository hiện tại
~~~

### 8.1. Form

~~~html
<form th:action="@{/logout}" method="post">
  <input type="hidden"
         th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}">
  <button type="submit">Đăng xuất</button>
</form>
~~~

Trong Spring MVC/Thymeleaf có thể có cơ chế tự chèn CSRF hidden input; ví dụ trên chỉ ra cách cung cấp rõ token từ template. Không hardcode token và không tắt CSRF toàn ứng dụng để POST logout trả 200/302.

### 8.2. Vì sao không dùng GET /logout?

Một link GET có side effect:

~~~text
https://portal.example.org/logout?user=alice
~~~

có thể bị kích hoạt bởi crawler hoặc trang khác. Tuyệt đối không lấy <code>user=alice</code> từ query để xóa authorized clients; phải dựa trên server-side authenticated principal.

### 8.3. Logout local thường làm gì?

Spring Security có thể:

- Invalidate HTTP session.
- Clear SecurityContext/Authentication.
- Thực hiện các custom logout handlers.
- Kết thúc bằng logout success handler.

Nó **không mặc định** gọi RFC 7009 revocation endpoint hoặc xóa mọi JDBC authorized-client records.

## 9. OAuth2AuthorizedClientService: interface chủ chốt

~~~java
org.springframework.security.oauth2.client.OAuth2AuthorizedClientService
~~~

Các signatures:

~~~java
OAuth2AuthorizedClient loadAuthorizedClient(
    String clientRegistrationId, String principalName);

void saveAuthorizedClient(
    OAuth2AuthorizedClient authorizedClient,
    Authentication principal);

void removeAuthorizedClient(
    String clientRegistrationId, String principalName);
~~~

### 9.1. PrincipalName lấy từ đâu?

Với OIDC Login:

~~~java
OAuth2AuthenticationToken oauth = ...;
String registrationId = oauth.getAuthorizedClientRegistrationId();
String principalName = oauth.getName();
~~~

<code>getName()</code> phải khớp key mà authorized-client service dùng khi save. Nó có thể là OIDC subject hoặc name attribute do ứng dụng cấu hình, **không mặc định là email**.

### 9.2. Xóa local record

~~~java
service.removeAuthorizedClient("company", principalName);
~~~

Thao tác này xóa entry trong service implementation. Nó không mặc nhiên revoke access/refresh token ở Authorization Server.

### 9.3. OAuth2AuthorizedClientRepository khác service

Repository API gắn với Servlet request:

~~~java
OAuth2AuthorizedClient loadAuthorizedClient(
    String registrationId,
    Authentication authentication,
    HttpServletRequest request);

void removeAuthorizedClient(
    String registrationId,
    Authentication authentication,
    HttpServletRequest request,
    HttpServletResponse response);
~~~

Một repository có thể lưu trong session hoặc delegate tới service. Nếu dữ liệu chỉ ở session, session invalidation có thể dọn nó. Nếu dữ liệu ở JDBC/service riêng, invalidating session chưa đủ.

### 9.4. Source of truth

Ví dụ kiến trúc:

~~~text
AuthenticatedPrincipalOAuth2AuthorizedClientRepository
      |
      v
OAuth2AuthorizedClientService
      |
      v
JDBC or InMemory store
~~~

Trước khi viết logout cleanup, phải biết application **save/load/refresh** authorized client qua store nào. Không tự cho rằng Spring Security mặc định dùng JDBC nếu bạn chưa cấu hình service tương ứng.

## 10. LogoutHandler xóa authorized clients theo principal

Ta xây dựng một <code>LogoutHandler</code> dọn service-backed data theo principal **đã xác thực** và những registration IDs do server cấu hình.

~~~java
package example.security;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.util.List;
import java.util.Objects;

import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.web.authentication.logout.LogoutHandler;

public final class AuthorizedClientCleanupLogoutHandler
        implements LogoutHandler {

    private final OAuth2AuthorizedClientService service;
    private final List<String> registrationIds;

    public AuthorizedClientCleanupLogoutHandler(
            OAuth2AuthorizedClientService service,
            List<String> registrationIds) {
        this.service = Objects.requireNonNull(service);
        this.registrationIds = List.copyOf(registrationIds);
    }

    @Override
    public void logout(
            HttpServletRequest request,
            HttpServletResponse response,
            Authentication authentication) {

        if (!(authentication instanceof OAuth2AuthenticationToken oauth)) {
            return;
        }

        // Identity lấy từ Authentication đã verify.
        String principalName = oauth.getName();

        for (String registrationId : registrationIds) {
            service.removeAuthorizedClient(
                registrationId, principalName);
        }
    }
}
~~~

### 10.1. Vì sao không dùng request parameter?

Sai:

~~~java
String principalName = request.getParameter("user");
service.removeAuthorizedClient("company", principalName);
~~~

Attacker có thể gửi tên user khác để xóa credentials không thuộc mình. Phải lấy principal từ <code>Authentication</code> đã xác minh, và dùng ownership/authorization policy phù hợp.

### 10.2. Danh sách registrations lấy từ đâu?

Trong lab:

~~~java
List.of("company", "partner")
~~~

Danh sách này thuộc cấu hình/registry đáng tin của ứng dụng, không lấy trực tiếp từ <code>?registrationId=...</code>. Một user có thể ủy quyền nhiều clients; tùy policy, logout Portal có thể xóa tất cả, còn **disconnect Partner** chỉ xóa registration <code>partner</code> mà vẫn giữ phiên Portal.

### 10.3. Chỉ xóa registration hiện tại

Nếu chính sách chỉ dọn provider đăng nhập:

~~~java
String registrationId =
    oauth.getAuthorizedClientRegistrationId();

service.removeAuthorizedClient(
    registrationId, oauth.getName());
~~~

Đó không phải full cleanup khi user có nhiều authorized clients. Đừng nói đã “xóa tất cả kết nối” khi chỉ remove một registration.

### 10.4. Không phụ thuộc session còn tồn tại

Spring Security có thể đã gọi <code>SecurityContextLogoutHandler</code> để invalidated HTTP session trước custom handler, tùy thứ tự handlers được cấu hình. Ví dụ ở đây dọn **OAuth2AuthorizedClientService**, dùng <code>Authentication</code> truyền vào, không cần đọc session sau khi invalidation.

Với <code>HttpSessionOAuth2AuthorizedClientRepository</code>, invalidating session thường xóa session-owned records; nếu cần explicit removal hoặc remote revocation dựa trên session token, phải kiểm soát thứ tự **load trước khi invalidate**.

### 10.5. Nếu cleanup storage thất bại

- Không tuyên bố remote tokens đã bị revoked.
- Theo security policy, local logout vẫn cần kết thúc session đúng cách.
- Ghi metric/audit kết quả cleanup không chứa raw credentials.
- Có thể dùng retryable cleanup task an toàn, có TTL và ownership controls nếu cần tính bền vững.
- Không block browser vô hạn do JDBC/Redis outage.

Không nuốt lỗi mà báo “tất cả đã được thu hồi”. Local logout, local-store cleanup và OP revocation là những outcomes riêng.

## 11. Service-backed storage trong lab

### 11.1. InMemory service cho demo

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.InMemoryOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.AuthenticatedPrincipalOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class AuthorizedClientStoreConfig {

    @Bean
    OAuth2AuthorizedClientService authorizedClientService(
            ClientRegistrationRepository registrations) {
        return new InMemoryOAuth2AuthorizedClientService(
            registrations);
    }

    @Bean
    OAuth2AuthorizedClientRepository authorizedClientRepository(
            OAuth2AuthorizedClientService service) {
        return new AuthenticatedPrincipalOAuth2AuthorizedClientRepository(
            service);
    }
}
~~~

<code>AuthenticatedPrincipalOAuth2AuthorizedClientRepository</code> sử dụng service cho authenticated principals theo implementation; với unauthenticated principal, có semantics lưu khác. Đây là cấu hình lab minh họa, không mặc định một cấu hình phù hợp mọi ứng dụng.

### 11.2. In-memory không dùng làm shared cluster store

~~~text
Pod A memory store != Pod B memory store
~~~

Xóa token trên B không xóa token được giữ trong process A. Với multi-instance production, dùng shared persistence và thiết kế cleanup/concurrency phù hợp.

### 11.3. JDBCAuthorizedClientService

Một bean thay thế khi dùng Spring JDBC:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.security.oauth2.client.JdbcOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Bean
OAuth2AuthorizedClientService authorizedClientService(
        JdbcOperations jdbc,
        ClientRegistrationRepository registrations) {
    return new JdbcOAuth2AuthorizedClientService(
        jdbc, registrations);
}
~~~

Không khai báo đồng thời JDBC và InMemory bean trùng tên trong một context; chọn một implementation/qualifiers theo application architecture. Schema migration phải khớp Spring Security version. Token storage cần encryption, restricted DB access và retention policy.

### 11.4. JDBC deletion không phải revocation

Xóa database record làm Portal không thể load credentials từ đó nữa. OP/Resource Server có vòng đời token riêng. Muốn revoke remote token, cần RFC 7009 hoặc OP mechanism được hỗ trợ.

## 12. SecurityFilterChain: local cleanup + OIDC LogoutSuccessHandler

~~~java
package example.security;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.oidc.web.logout.OidcClientInitiatedLogoutSuccessHandler;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.logout.LogoutHandler;

@Configuration
public class PortalSecurityConfig {

    @Bean
    LogoutHandler authorizedClientCleanup(
            OAuth2AuthorizedClientService service) {
        return new AuthorizedClientCleanupLogoutHandler(
            service, List.of("company", "partner"));
    }

    @Bean
    SecurityFilterChain portalChain(
            HttpSecurity http,
            ClientRegistrationRepository registrations,
            LogoutHandler authorizedClientCleanup)
            throws Exception {

        var oidcLogout =
            new OidcClientInitiatedLogoutSuccessHandler(
                registrations);

        oidcLogout.setPostLogoutRedirectUri(
            "{baseUrl}/logged-out");

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/", "/login", "/logged-out",
                    "/error", "/assets/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .addLogoutHandler(authorizedClientCleanup)
                .logoutSuccessHandler(oidcLogout));

        return http.build();
    }
}
~~~

### 12.1. Hai extension points, hai trách nhiệm

~~~text
LogoutHandler:
    AuthorizedClientCleanupLogoutHandler
    → xóa service-backed data local

LogoutSuccessHandler:
    OidcClientInitiatedLogoutSuccessHandler
    → redirect browser tới OP end_session_endpoint
~~~

Không dùng <code>AuthenticationSuccessHandler</code> của login làm logout handler. Hai operations thuộc lifecycle khác nhau.

### 12.2. POST logout không có CSRF có thể trả HTTP 403

Nếu CSRF enabled và request thiếu token, Spring Security có thể chặn trước LogoutFilter. Đó là behavior security đúng. Trong MockMvc, test logout hợp lệ bằng <code>.with(csrf())</code>, và có negative test khi thiếu CSRF.

### 12.3. OP không hỗ trợ end-session

Nếu provider không có <code>end_session_endpoint</code> hoặc principal không phải OIDC, logout success handler có thể fallback theo Spring Security version/configuration. Không diễn giải local redirect thành “OP SSO đã kết thúc”.

### 12.4. Nhiều SecurityFilterChains

Đảm bảo POST <code>/logout</code> được chain chứa cleanup handler xử lý, callback OAuth2 Login vẫn thuộc chain thích hợp và <code>/logged-out</code> được permitAll. Một matcher sai có thể tạo logout 302 nhưng không chạy cleanup thật.

## 13. Public logged-out page

~~~java
package example.web;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
public class LogoutPageController {

    @GetMapping("/logged-out")
    @ResponseBody
    String loggedOut() {
        return "Ban da dang xuat khoi Portal.";
    }
}
~~~

Trang này public, không tự bắt đầu login OIDC để tránh redirect loop. UX nên nói “Đã đăng xuất khỏi Portal” trước; chỉ tuyên bố OP logout thành công nếu provider flow thực sự hoàn tất theo khả năng kiểm chứng của hệ thống.

Nếu bấm Login sau local logout và OP tự SSO vào lại, đó **chưa phải bằng chứng** local logout hỏng; OP SSO session có thể còn.

## 14. RFC 7009: token revocation không phải OIDC logout

OAuth2 Token Revocation (RFC 7009) mô tả một endpoint cho phép Client yêu cầu Authorization Server thu hồi token. Tùy provider, endpoint có thể được công bố qua metadata bằng <code>revocation_endpoint</code>.

### 14.1. HTTP request minh họa

~~~http
POST /oauth2/revoke HTTP/1.1
Host: sso.test.example
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_TEST_CLIENT_CREDENTIALS

token=REFRESH_TOKEN_PLACEHOLDER&token_type_hint=refresh_token
~~~

Đây chỉ là mẫu protocol. Revocation endpoint thực, client authentication và token cần được lấy từ **trusted OP configuration**; không đặt production credentials trong tutorial, query string hoặc logs.

### 14.2. Không dùng arbitrary revocation URL

Sai:

~~~text
POST /disconnect?revokeUrl=https://attacker.example
~~~

rồi POST refresh token tới URL browser cung cấp. Đây là nguy cơ **SSRF và credential exfiltration**. Revocation URL phải đến từ allowlisted provider metadata/config, không lấy từ untrusted request.

### 14.3. Client authentication

Confidential Client thường xác thực với revocation endpoint theo method OP cho phép (ví dụ client_secret_basic hoặc private_key_jwt). Không hardcode Authorization Basic cho mọi OP nếu client đã đăng ký phương thức khác.

### 14.4. token_type_hint

Các giá trị thường thấy:

~~~text
refresh_token
access_token
~~~

<code>token_type_hint</code> là gợi ý giúp server xử lý, không phải một yêu cầu OP chỉ xử lý token theo loại được khai báo.

### 14.5. HTTP 200 không chứng minh “token đã tồn tại”

Theo RFC 7009, revocation endpoint có thể trả success ngay cả khi token không tồn tại hoặc đã không hợp lệ, để không trở thành endpoint dò token.

Vì vậy, HTTP 200 không đủ để khẳng định mọi Resource Server đã tức thời vô hiệu hóa access token tự chứa mà OP từng phát hành.

### 14.6. Refresh vs access token revocation

Refresh token có thể tiếp tục cho phép xin access token mới dù access token cũ hết hạn. Với chính sách logout/consent revocation, thường phải xem **refresh token hoặc authorization grant** trước. OP có thể cũng revoke access tokens/entire grant tùy implementation, chứ không có một contract “mọi token mọi device đều vô hiệu ngay” mặc định.

### 14.7. JWT Resource Server còn có thể nhận token cũ

~~~text
Access token issued at 10:00
Token expires at 10:15
Portal logout at 10:02
~~~

Nếu Resource Server chỉ xác minh chữ ký và expiry của một self-contained JWT, nó có thể vẫn chấp nhận token cũ tới 10:15 dù Portal đã remove local record. Muốn immediate global invalidation phải thiết kế OP revocation awareness, introspection/denylist/session version hoặc token lifetime phù hợp.

## 15. Thứ tự revoke token và xóa local storage

Nếu remote revocation cần refresh token, phải đọc token **trước khi** xóa bản sao local.

### 15.1. Workflow tham khảo

~~~text
1. Xác định verified principal + allowed registration IDs.
2. Load OAuth2AuthorizedClient từ trusted token store.
3. Nếu OP hỗ trợ RFC 7009, gọi revocation endpoint với bounded timeout.
4. Ghi normalized remote revocation outcome.
5. Xóa local authorized-client record.
6. Kết thúc SecurityContext và HTTP session.
7. Tùy chính sách, redirect browser tới OP end_session_endpoint.
~~~

Đây là **workflow ứng dụng cần thiết kế**, không phải một class Spring Security thực hiện toàn bộ chuỗi.

### 15.2. Remote revocation trong LogoutHandler có rủi ro

<code>LogoutHandler</code> chạy trong request xử lý logout. Nếu gọi OP rồi chờ không giới hạn, user có thể bị treo khi OP lỗi.

Các phương án:

- Thiết lập connect/read timeouts.
- Bounded retries, không retry mãi một token.
- Local logout vẫn được thực thi theo security policy dù OP unavailable.
- Nếu yêu cầu đảm bảo remote revocation, dùng secure retryable workflow với expiry/visibility/ownership rõ.
- Thông báo trạng thái đúng, không khẳng định hoàn thành tất cả các bước nếu chưa có evidence.

### 15.3. Nếu remove local trước rồi mới revoke

~~~text
service.removeAuthorizedClient(...)
→ không còn refresh token để gửi revocation
~~~

Trong trường hợp cần reliable remote revocation, phải capture token cần thiết trước, giữ trong bộ nhớ tối thiểu hoặc lưu encrypted retry task được bảo vệ. Không đặt raw tokens vào logs, queue không mã hóa hay bug-report attachments.

### 15.4. Remote timeout là kết quả chưa chắc chắn

OP có thể đã nhận revocation request nhưng response bị mất. Một retry có thể được hỗ trợ theo RFC 7009 semantics, nhưng phải tuân thủ rate limit, bounded backoff và provider contract. Không dùng refresh grant retry khi đang thực hiện revocation.

## 16. Đăng xuất một provider hay tất cả providers?

Một user đã đăng nhập Company và kết nối Partner API:

~~~text
company  | principal-123 | access A1 | refresh R1
partner  | principal-123 | access A2 | refresh R2
analytics| principal-123 | access A3 | refresh R3
~~~

### 16.1. Full Portal logout

Theo policy “Đăng xuất khỏi Portal và xóa các kết nối được Portal giữ”:

~~~text
remove company / principal-123
remove partner / principal-123
remove analytics / principal-123
invalidate Portal session
initiate OP logout if supported
~~~

Không quên registrations mà user từng authorize nếu policy yêu cầu dọn toàn bộ. Interface <code>OAuth2AuthorizedClientService</code> không có thao tác tiêu chuẩn để liệt kê mọi registrations của một principal; cần trusted registry/custom lookup nếu số registrations thay đổi động.

### 16.2. Disconnect Partner

Trong khi user vẫn authenticated qua Company, chức năng “Ngắt kết nối Partner” nên:

~~~text
remove/revoke partner authorized client
keep Company login session
keep unrelated registrations unless policy says otherwise
~~~

Đây là một **account management operation**, không phải full logout; dùng POST có CSRF, kiểm tra ownership và một handler/service riêng.

### 16.3. Same email không chứng minh same identity

Hai issuers có thể phát token cho cùng email hoặc thậm chí cùng <code>sub</code> string. Với custom storage, cần identity mapping có issuer/provider/tenant context phù hợp:

~~~text
(issuer, subject, registrationId)
~~~

Trong default service API, key liên quan <code>registrationId</code> + <code>principalName</code>. Nếu custom principal name mapping gây collision, token có nguy cơ bị cross-user/tenant reuse hoặc cleanup nhầm.

## 17. Logout một thiết bị và nhiều thiết bị

<code>OAuth2AuthorizedClientService</code> thường được key bởi:

~~~text
registrationId + principalName
~~~

Một user dùng nhiều browser sessions có thể chia sẻ cùng authorized-client record nếu thiết kế storage như vậy.

| Mong muốn của user | Hành động cần thiết |
|---|---|
| Logout browser A | Invalidate session A |
| Xóa credentials Portal lưu cho user | Remove service-backed authorized clients |
| Disconnect một API provider | Remove/revoke registration tương ứng |
| Kết thúc OP SSO trên browser hiện tại | RP-Initiated Logout |
| Logout all devices | Global session registry/OP sessions/grant policy |

### 17.1. Shared record ảnh hưởng thiết bị còn lại

Nếu A và B cùng dùng <code>company/principal-123</code>, logout trên A rồi remove record có thể khiến B tiếp tục có Authentication trong session nhưng không còn token để gọi downstream API. Đây là một **policy decision** cần test, không phải luôn là lỗi.

### 17.2. Muốn lưu token per-device thì sao?

Cần custom token store key/model gắn device/session, cùng authorized-client manager/repository và cleanup ownership được thiết kế nhất quán. Không tự ý thay <code>principalName</code> bằng một session ID ở nơi save nhưng vẫn load bằng subject ở nơi khác.

### 17.3. “Logout all devices” đòi nhiều hệ thống phối hợp

Không thể suy từ một call <code>removeAuthorizedClient</code> rằng tất cả device sessions đã bị kết thúc. Phải xét Portal session registry, OP SSO/session management, refresh grants và existing JWT access tokens trên Resource Servers.

## 18. Session-backed OAuth2AuthorizedClientRepository

Khi app dùng <code>HttpSessionOAuth2AuthorizedClientRepository</code>, authorized-client data có thể nằm trong HTTP session và bị xóa cùng session invalidation.

### 18.1. Xóa session cookie khác invalidating server session

Chỉ trả:

~~~http
Set-Cookie: JSESSIONID=; Max-Age=0
~~~

không đủ chứng minh server-side session invalidated và resources được cleanup đúng. Dùng logout infrastructure của Spring Security và verify behavior.

### 18.2. Không load session token sau khi đã invalidate

~~~text
SecurityContextLogoutHandler invalidates HttpSession
    ↓
Session-backed authorized client no longer available
    ↓
Custom handler tries repository.loadAuthorizedClient(...)
    ↓
May return null because prior session is gone
~~~

Nếu bắt buộc remote revoke một session-backed token, thiết kế một bước capture/revoke trước invalidation theo orchestration có thứ tự. Chạy dọn service-backed tokens sau default logout là tình huống khác.

### 18.3. Controller tự invalidate session có thể bỏ qua security hooks

Không thay toàn bộ LogoutFilter bằng:

~~~java
request.getSession().invalidate();
return "redirect:/logged-out";
~~~

vì có thể bỏ qua CSRF, SecurityContext cleanup, custom token cleanup và RP-Initiated Logout.

## 19. Logout và refresh token rotation race

Giả sử hai Portal nodes cùng có quyền truy cập persisted authorized client:

~~~mermaid
sequenceDiagram
    autonumber
    participant A as Node A /logout
    participant B as Node B background refresh
    participant DB as Shared token store
    participant OP as OP Token Endpoint
    A->>DB: Read A0/R0
    B->>DB: Read A0/R0
    B->>OP: Refresh R0
    OP-->>B: Access A1, refresh R1
    A->>DB: Delete authorized client for logout
    B->>DB: Save A1/R1 after deletion?
    Note over DB: Nguy cơ token được ghi lại sau logout
~~~

### 19.1. Xóa token một lần có đủ không?

Không chắc. Nếu background job nắm state cũ và save token mới sau logout, record có thể **sống lại** dù logout cleanup ban đầu thành công.

### 19.2. Thiết kế chống token resurrection

Những biện pháp kiến trúc tùy yêu cầu:

1. Mark grant/user authorization as revoked với **generation/version/tombstone** có TTL hoặc retention policy.
2. Stop/suspend background jobs dùng grant đó.
3. Re-check grant status ngay trước khi save token mới.
4. Atomic conditional update/compare-and-set.
5. Use per-key coordination cho refresh và logout.
6. Remote revoke refresh token/grant nếu provider hỗ trợ.
7. Invalidate caches theo version và không phục hồi record từ stale cache.

Đây là vấn đề concurrency **không được Spring Security giải quyết tự động chỉ vì cấu hình logout handler**.

### 19.3. Tombstone cần có vòng đời

Không giữ token-revocation tombstones không thời hạn mà không có retention/expiry policy. Nhưng nếu xóa tombstone quá sớm, một job chậm có thể tạo lại record. Cần cân đối maximum job duration, queue retries và authorization lifetime.

### 19.4. Giao dịch giữa DB và OP không tự nguyên tử

Xóa JDBC record và gọi OP revocation là hai hệ thống khác nhau. Không có distributed transaction mặc định:

~~~text
DB delete succeeds, OP revoke fails
OP revoke succeeds, DB delete fails
Network timeout, outcome unknown
~~~

Thiết kế idempotent cleanup, retries và observable partial failures.

## 20. OIDC Logout từ OP và Back-Channel Logout

Ngoài logout do Portal khởi tạo, OP có thể khởi tạo logout đối với Relying Parties.

### 20.1. RP-Initiated Logout

~~~text
Portal browser user → OP end_session_endpoint
~~~

Đã được cấu hình bằng <code>OidcClientInitiatedLogoutSuccessHandler</code>.

### 20.2. Front-Channel Logout

OP thông báo tới RP qua browser navigation/iframe theo profile. Browser cookie policy, third-party cookie restrictions và session mapping có thể ảnh hưởng.

### 20.3. Back-Channel Logout

OP gửi **signed Logout Token** tới RP back-channel endpoint; RP cần verify issuer, audience, signature, event marker, <code>sid</code>/<code>sub</code> và các requirements khác theo OIDC Back-Channel Logout spec.

Spring Security có hỗ trợ OIDC back-channel logout trong những versions phù hợp; API DSL/configuration và session registry integration phải đối chiếu reference của version dự án. Không suy rằng cấu hình RP-Initiated Logout tự bật back-channel logout.

### 20.4. OP logout nhận được có dọn OAuth2AuthorizedClientService không?

Tùy application setup và mapping. Một OP logout notification chấm dứt Portal sessions có thể **không** xóa persistent tokens nếu application chưa nối lifecycle cleanup đúng.

Khi cần, kết nối back-channel logout event với server-side authorized-client cleanup theo trusted issuer/subject/session mapping. Không lấy <code>sub</code> từ unsigned JSON rồi delete token records.

### 20.5. Không chấp nhận logout request giả

Một attacker gửi:

~~~http
POST /logout/back-channel
Content-Type: application/json

{"sub":"victim"}
~~~

không phải OIDC Back-Channel Logout hợp lệ. Phải verify signed Logout Token và client/audience/issuer/session bindings theo protocol. Không cho bất kỳ client ngoài nào xóa session/token của người khác bằng một <code>sub</code> chưa xác minh.

## 21. Redirect, cookies và môi trường deployment

### 21.1. post_logout_redirect_uri phải chính xác

~~~text
local:
  http://localhost:8080/logged-out

staging:
  https://portal.staging.example.org/logged-out

production:
  https://portal.example.org/logged-out
~~~

OP phải chấp nhận URL theo policy. Không dùng cùng một production client registration cho local/staging nếu có thể tách client và credentials.

### 21.2. Proxy HTTPS có thể làm {baseUrl} sai

Nếu browser dùng:

~~~text
https://portal.example.org
~~~

nhưng Spring Boot thấy:

~~~text
http://portal-service:8080
~~~

thì logout handler có thể tạo post-logout redirect URL sai. Dùng trusted forwarded headers hoặc external base URL mapping thích hợp. Edge proxy phải strip/overwrite spoofed <code>Forwarded</code>/<code>X-Forwarded-*</code>, không tin hostname browser tùy ý.

### 21.3. Cookie scope của OP và Portal

<code>Secure</code>, <code>HttpOnly</code>, <code>SameSite</code>, Domain/Path của Portal cookie chỉ kiểm soát Portal session. OP SSO cookie thuộc domain OP; browser logout redirect phải thực sự được thực hiện nếu muốn OP xử lý phiên của nó.

### 21.4. Một public URL có nhiều tenants

Nếu logout dùng <code>{baseUrl}</code> và Portal phục vụ nhiều tenants/hostnames, phải kiểm tra trusted host allowlist và tenant mapping. Không nhận <code>post_logout_redirect_uri</code> arbitrary từ browser; nguy cơ open redirect và cross-tenant confusion.

## 22. Unit test: dọn đúng principal và registrations

Mục tiêu unit test là chứng minh <code>AuthorizedClientCleanupLogoutHandler</code> xóa đúng records trong <code>OAuth2AuthorizedClientService</code>, không cần OP test.

### 22.1. Tạo hai registrations và ba authorized clients

Ví dụ JUnit 5:

~~~java
package example.security;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.InMemoryOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2RefreshToken;
import org.springframework.security.oauth2.core.user.DefaultOAuth2User;

import static org.junit.jupiter.api.Assertions.*;

class AuthorizedClientCleanupLogoutHandlerTest {

    private ClientRegistration registration(String id) {
        return ClientRegistration.withRegistrationId(id)
            .clientId("portal-test-" + id)
            .clientSecret("test-only")
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri(
                "{baseUrl}/login/oauth2/code/{registrationId}")
            .authorizationUri("https://op.example.test/authorize")
            .tokenUri("https://op.example.test/token")
            .jwkSetUri("https://op.example.test/jwks")
            .scope("openid")
            .clientName(id)
            .build();
    }

    private OAuth2AuthenticationToken auth(
            String subject,
            String registrationId) {
        var user = new DefaultOAuth2User(
            List.of(new SimpleGrantedAuthority("ROLE_USER")),
            Map.of("sub", subject),
            "sub");
        return new OAuth2AuthenticationToken(
            user, user.getAuthorities(), registrationId);
    }

    private OAuth2AuthorizedClient authorizedClient(
            ClientRegistration registration,
            String subject) {

        Instant now = Instant.parse("2026-11-16T10:00:00Z");

        var access = new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            "access-" + registration.getRegistrationId()
                + "-" + subject,
            now, now.plusSeconds(600));

        var refresh = new OAuth2RefreshToken(
            "refresh-" + registration.getRegistrationId()
                + "-" + subject,
            now);

        return new OAuth2AuthorizedClient(
            registration, subject, access, refresh);
    }

    @Test
    void removesAliceClientsButPreservesBob() {
        var company = registration("company");
        var partner = registration("partner");

        var registrations =
            new InMemoryClientRegistrationRepository(
                company, partner);
        var service =
            new InMemoryOAuth2AuthorizedClientService(
                registrations);

        var alice = auth("alice", "company");
        var bob = auth("bob", "company");

        service.saveAuthorizedClient(
            authorizedClient(company, "alice"), alice);
        service.saveAuthorizedClient(
            authorizedClient(partner, "alice"), alice);
        service.saveAuthorizedClient(
            authorizedClient(company, "bob"), bob);

        assertNotNull(service.loadAuthorizedClient(
            "company", "alice"));
        assertNotNull(service.loadAuthorizedClient(
            "partner", "alice"));
        assertNotNull(service.loadAuthorizedClient(
            "company", "bob"));

        var handler = new AuthorizedClientCleanupLogoutHandler(
            service, List.of("company", "partner"));

        handler.logout(
            new MockHttpServletRequest(),
            new MockHttpServletResponse(),
            alice);

        assertNull(service.loadAuthorizedClient(
            "company", "alice"));
        assertNull(service.loadAuthorizedClient(
            "partner", "alice"));
        assertNotNull(service.loadAuthorizedClient(
            "company", "bob"));
    }
}
~~~

### 22.2. Test này chứng minh gì?

1. Authorized clients được lưu theo registration ID + principal name.
2. Handler lấy principal từ <code>OAuth2AuthenticationToken</code>, không lấy query parameter.
3. Cleanup hai registrations của Alice.
4. Record của Bob không bị xóa.

**Không chứng minh** browser session đã invalidated, OP SSO session kết thúc, hay refresh tokens đã bị revoke tại OP. Các mục tiêu đó cần test khác.

### 22.3. Vì sao dùng DefaultOAuth2User trong test OIDC?

Test này chỉ kiểm tra handler chấp nhận <code>OAuth2AuthenticationToken</code> và cách lấy principal name; không xác minh OIDC ID Token. Một <code>OAuth2AuthenticationToken</code> có <code>DefaultOAuth2User</code> là đủ để kiểm thử cleanup logic. Nếu muốn test OIDC logout success handler cần tạo **OidcUser có ID Token phù hợp** hoặc chạy full OP integration.

### 22.4. Test authentication null

~~~java
@Test
void nullAuthenticationDoesNotDeleteAnyRecord() {
    // Chuẩn bị service có record Alice như test trên.
    handler.logout(
        new MockHttpServletRequest(),
        new MockHttpServletResponse(),
        null);

    // Assert Alice record vẫn còn nguyên.
}
~~~

Đây là **đoạn assertion skeleton**, yêu cầu fixture <code>handler</code>/<code>service</code> đã được khởi tạo như test trước. Test cũng nên thử non-OAuth Authentication để tránh xóa nhầm khi anonymous/local-auth logout không thuộc policy.

### 22.5. Test registration chưa tồn tại

Một list registrations chứa ID không có trong store có thể khiến remove thành no-op hoặc custom implementation xử lý khác. Hãy chọn policy khi config chứa registration không hợp lệ và test application startup/cleanup behavior, thay vì chấp nhận một danh sách động không được validate.

## 23. MockMvc: POST logout có CSRF

Muốn kiểm thử Spring Security LogoutFilter, phải **bật security filters** trong MockMvc.

### 23.1. Cấu trúc integration test

~~~java
package example.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PortalLogoutMvcIT {

    @Autowired
    MockMvc mockMvc;

    @Test
    void rejectsLogoutWithoutCsrf() throws Exception {
        mockMvc.perform(
                post("/logout").with(oidcLogin()))
            .andExpect(status().isForbidden());
    }

    @Test
    void acceptsLogoutWithCsrf() throws Exception {
        mockMvc.perform(
                post("/logout")
                    .with(oidcLogin())
                    .with(csrf()))
            .andExpect(status().is3xxRedirection());
    }
}
~~~

**Đây là skeleton integration test cần một Spring context hợp lệ**: ClientRegistrationRepository/OP metadata được cung cấp qua test configuration. <code>oidcLogin()</code> có thể sử dụng một mock test registration không khớp registration thật của app; với <code>OidcClientInitiatedLogoutSuccessHandler</code>, redirect tới OP phụ thuộc ClientRegistration/Issuer/discovery setup. Không hardcode kỳ vọng một OP logout URL cho test này khi chưa cung cấp matching registration và OidcUser.

### 23.2. oidcLogin() kiểm tra được gì?

Trong MockMvc:

~~~java
.with(oidcLogin())
~~~

đưa một OIDC-style authenticated principal vào request, giúp kiểm tra LogoutFilter/CSRF và một số behavior của handler. Nó **không chạy Authorization Code login qua OP**, và không chứng minh OP SSO cookie bị xóa.

### 23.3. @WithMockUser không tương đương OIDC Login

~~~java
@WithMockUser(username = "alice")
~~~

tạo user authentication giả lập thường không phải <code>OAuth2AuthenticationToken</code>. Handler ở mục 10 cố ý chỉ xử lý OAuth2AuthenticationToken, nên một test dùng <code>@WithMockUser</code> có thể cho kết quả logout redirect nhưng không chạy authorized-client cleanup path.

### 23.4. Không tắt filters

Tránh:

~~~java
@AutoConfigureMockMvc(addFilters = false)
~~~

với bài test này. Khi tắt filters, không còn <code>CsrfFilter</code>/<code>LogoutFilter</code> thực để xác minh.

### 23.5. Kiểm tra access sau logout

Sau logout thực, một request protected từ browser **không còn authenticated session** phải bị yêu cầu login/authorization.

Đừng dùng <code>.with(oidcLogin())</code> trong **request sau logout**, vì bạn lại inject Authentication giả và vô hiệu hóa ý nghĩa của test:

~~~java
// Không phải cách test user đã logout:
mockMvc.perform(get("/private").with(oidcLogin()));
~~~

Thay vào đó, dùng session/cookie lifecycle phù hợp với test, hoặc request anonymous thực sự để kiểm tra protected route bị chặn.

## 24. Unit test OIDC LogoutSuccessHandler

<code>OidcClientInitiatedLogoutSuccessHandler</code> quyết định redirect tới OP dựa trên authenticated OIDC principal và provider metadata.

### 24.1. Setup tối thiểu cần có

1. Một <code>ClientRegistration</code> cho registration <code>company</code>.
2. Provider metadata chứa một <code>end_session_endpoint</code> test URL.
3. <code>OidcUser</code> có ID Token test và đúng issuer/client context.
4. <code>OAuth2AuthenticationToken</code> gắn principal/registration.
5. <code>MockHttpServletRequest</code> với public HTTPS origin/forwarded context phù hợp.
6. <code>MockHttpServletResponse</code> để kiểm tra <code>Location</code>.

### 24.2. Assertions phù hợp

~~~text
status = 302
Location host = trusted OP host
Location path = OP end_session_endpoint
post_logout_redirect_uri = registered Portal HTTPS URL
id_token_hint present when applicable
~~~

**Không in toàn bộ Location URL chứa ID Token** vào CI logs. Nếu cần debug, parse query và chỉ assert sự hiện diện/host/target đã lọc.

### 24.3. Các nhánh fallback

Test thêm:

- Authentication null.
- Principal không phải <code>OidcUser</code>.
- ClientRegistration không tìm được.
- OP không công bố <code>end_session_endpoint</code>.
- Post-logout URI không thể được tạo hoặc không thuộc allowlist.

Expected redirect fallback phải lấy từ **đúng Spring Security version**, không tự giả định rằng luôn về <code>/logged-out</code> hoặc luôn gọi OP.

## 25. Browser E2E với OP test

Muốn biết OP SSO session thật sự đã kết thúc, cần browser nhận và thực hiện OP logout redirect.

### 25.1. Bài test cơ bản

~~~text
Given:
    Keycloak/OP test realm available
    Portal registration company configured
    Test user alice.test enabled
    Browser context fresh

When:
    Browser starts /oauth2/authorization/company
    User signs in at OP
    Portal shows authenticated profile
    User POSTs /logout with CSRF
    Browser follows OP end_session_endpoint
    OP returns registered post_logout_redirect_uri

Then:
    Portal no longer has authenticated local session
    Local authorized-client service record is absent
    Browser reaches public logged-out page
    OP SSO behavior matches logout contract
~~~

### 25.2. Vì sao không chỉ xem trang /logged-out?

Một app có thể redirect trực tiếp tới <code>/logged-out</code> mà không bao giờ gọi OP. Browser nhìn thấy trang sau logout chưa chứng minh OP SSO cookie bị xóa.

### 25.3. Kiểm tra OP SSO một cách phù hợp

Để chứng minh OP logout, có thể kiểm tra flow login lại trong browser context cũ **không tự động reuse phiên OP** khi OP logout policy yêu cầu. Một số providers hỗ trợ <code>prompt=none</code> để quan sát có OP session hay không; điều kiện và behavior cần theo provider documentation.

Không dùng <code>prompt=login</code> làm bằng chứng OP session đã logout, vì tham số đó ép hiển thị login dù session trước vẫn còn.

### 25.4. Browser artifacts

Screenshots, HAR và tracing có thể chứa cookies, authorization codes, <code>state</code>, ID Token hints hoặc PII. Cần redact, giới hạn retention và access. Không đăng raw logout Location vào public CI logs.

## 26. Integration test token revocation

Nếu OP hỗ trợ RFC 7009:

1. Login/authorize test account và lấy authorized client từ test store.
2. Gọi trusted revocation endpoint cho refresh token theo provider contract.
3. Xóa local token record.
4. Cố sử dụng refresh token cũ trong **test environment đã cô lập**.
5. Kiểm tra OP từ chối token/grant theo chính sách.
6. Kiểm tra Resource Server behavior đối với access token cũ theo token format/revocation strategy.

### 26.1. Không test revocation bằng production token

Không copy token thật từ browser DevTools/production database sang Postman. Dùng OP/test clients/users riêng với cleanup lifecycle.

### 26.2. Đọc kết quả chính xác

HTTP 200 từ revocation endpoint không chứng minh token đã tồn tại trước đó. Cần thêm token/grant behavior assertions nếu provider cho phép quan sát; không suy rằng JWT cũ lập tức bị reject nếu RS chỉ verify offline.

### 26.3. Fault injection

Giả lập:

~~~text
revocation endpoint HTTP 503
network timeout after OP processes request
unsupported revocation endpoint
invalid_client
storage delete failure
~~~

Mỗi case cần expected policy: local logout có hoàn tất không, cleanup retry task được tạo không, UI thông báo gì, metrics nào tăng. Không để retry vô hạn hoặc leaked token trong queue.

## 27. Integration test concurrency logout vs refresh

Với two-node scenario:

~~~text
Initial DB state: company/alice A0/R0 version=7
Node A: starts logout, intends deletion
Node B: begins refresh R0
OP: issues A1/R1
Node B: attempts save version=8
~~~

### 27.1. Kịch bản cần assert

1. Nếu logout committed trước, refresh save sau đó **không được phục hồi** token record trái policy.
2. Nếu refresh committed trước, logout phải nhìn thấy record version mới và cleanup tương ứng.
3. Không có unconditional delete của một node vô tình xóa state belonging to a different principal.
4. Tokens được mã hóa trong storage và không lọt logs.
5. Distributed lock/transaction/versioning có timeout và failure path.

### 27.2. InMemory service không đủ cho race test

InMemory service per JVM không thể mô phỏng đúng transaction/lock của JDBC/Redis cluster. Dùng shared test database, fault injection và concurrency synchronization trong integration test.

### 27.3. Bài toán idempotency

Nếu browser submit POST /logout hai lần, cleanup nên an toàn khi record đã được xóa. Nhưng khi remote revocation xảy ra, cần policy với unknown outcomes và retry limits. Không dựng logic tạo lại authorized client chỉ vì một lần remove trả null.

## 28. Test Back-Channel Logout

Khi app hỗ trợ OIDC Back-Channel Logout:

~~~text
OP sends signed Logout Token
    ↓
RP validates signature, iss, aud, events, sid/sub and other claims
    ↓
RP maps to local sessions
    ↓
RP terminates affected local sessions
    ↓
Application optionally cleans related persisted authorized clients
~~~

### 28.1. Negative test quan trọng

- Unsigned Logout Token.
- Signature không verify được bằng trusted OP keys.
- Wrong issuer.
- Wrong audience.
- Wrong event claim.
- Wrong <code>sid/sub</code> mapping.
- Replayed Logout Token theo provider/session policy.
- Expired/invalid temporal claims khi áp dụng.

Không nhận một JSON <code>{"sub":"alice"}</code> chưa ký rồi xóa sessions/tokens. Đừng tắt validation chỉ để test dễ tạo Logout Token.

### 28.2. Khác remote token revocation

Back-channel logout là protocol **OP thông báo RP kết thúc sessions**. Nó không mặc nhiên giống Client POST refresh token tới RFC 7009 endpoint. Token cleanup bổ sung phải được thiết kế rõ theo architecture.

### 28.3. Session registry trong cluster

Nếu sessions nằm ở nhiều nodes, RP cần shared session registry/store hoặc cơ chế phân tán để xác định các sessions theo <code>sid</code>/<code>sub</code>. Chỉ terminate một in-memory session trên node nhận webhook có thể bỏ sót các nodes khác.

## 29. Thực hành thêm: Disconnect một provider mà không logout Portal

Trong nhiều sản phẩm, user có quyền **ngắt kết nối một API provider** nhưng vẫn tiếp tục dùng Portal. Đây là một operation khác với POST <code>/logout</code>.

### 29.1. Endpoint có ownership checks

~~~java
package example.web;

import java.util.Set;

import org.springframework.http.ResponseEntity;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class DisconnectController {

    private static final Set<String> DISCONNECTABLE =
        Set.of("partner", "analytics");

    private final OAuth2AuthorizedClientService service;

    public DisconnectController(
            OAuth2AuthorizedClientService service) {
        this.service = service;
    }

    @PostMapping("/connections/{registrationId}/disconnect")
    ResponseEntity<Void> disconnect(
            @PathVariable String registrationId,
            Authentication authentication) {

        if (!(authentication instanceof OAuth2AuthenticationToken oauth)) {
            throw new ResponseStatusException(
                HttpStatus.UNAUTHORIZED);
        }

        if (!DISCONNECTABLE.contains(registrationId)) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND);
        }

        // Nếu cần remote revocation, phải load token và
        // thực hiện workflow được kiểm soát trước local removal.
        service.removeAuthorizedClient(
            registrationId, oauth.getName());

        return ResponseEntity.noContent().build();
    }
}
~~~

**Giới hạn:** Code này chỉ **local remove**. Nếu nghiệp vụ yêu cầu thực sự ngắt grant tại OP, thêm revocation workflow đã nói ở mục 14–15. Endpoint cần CSRF nếu browser session, và method security/tenant ownership checks phù hợp nếu ứng dụng có đa tenant hay user can manage other users.

### 29.2. Vì sao allowlist?

Nếu user truyền <code>/connections/company/disconnect</code>, ta không tự cho phép cắt login identity đang active khi UI chỉ dự định disconnect downstream providers. Policy rõ giúp tránh phá auth state.

### 29.3. Multiple providers cùng email

Nếu Partner và Company dùng hai issuers, xác định quyền sở hữu connection bằng principal mapping đáng tin. Không dùng email browser gửi để gọi <code>removeAuthorizedClient</code> trên principal khác.

### 29.4. Concurrent background job

Trước khi disconnect, các background jobs dùng registration đó cần dừng hoặc kiểm tra trạng thái revoked/version. Một record có thể được re-saved sau remove nếu job vẫn đang refresh với stale token.

## 30. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Kiểm tra/sửa |
|---|---|---|
| POST /logout trả 403 | Thiếu CSRF token | Kiểm tra CsrfFilter, form/header |
| GET /logout không thực hiện logout | CSRF-enabled logout mặc định cần POST; có thể có confirmation page | Dùng POST + CSRF |
| Logout trả 302 nhưng user vẫn vào private page | Session chưa clear hoặc request lại được mock authenticated | SecurityFilterChain, session cookie, test setup |
| Logout local xong nhưng OP tự login lại | OP SSO session còn | RP-Initiated Logout/end_session_endpoint |
| Không redirect tới OP logout | Principal không phải OidcUser, thiếu OP metadata, handler wiring | Authentication/ClientRegistration/Discovery |
| OP từ chối post_logout_redirect_uri | URI chưa được allowlist/khác hostname | Exact URI đăng ký, HTTPS, forwarded headers |
| Redirect về http://internal:8080 | Public base URL/proxy metadata sai | Trusted Forwarded headers và ingress |
| Trang /logged-out lại yêu cầu login | Route chưa permitAll | Authorization config |
| JDBC vẫn có refresh token | Logout chỉ invalidated HTTP session | Kiểm tra service-backed cleanup |
| Cleanup gọi nhưng không thấy record bị xóa | Wrong principalName/registrationId/store | So key dùng lúc save/load/remove |
| Xóa Alice làm Bob mất token | User key/tenant isolation sai | Verified Authentication + key design |
| User logout Company nhưng Partner token còn | Chỉ remove current registration | Policy full logout vs disconnect |
| Xóa session rồi không load được token để revoke | Session-backed repo đã invalidated | Load/capture trước invalidation |
| OP revocation HTTP 200 nhưng JWT vẫn dùng được | Self-contained JWT/RS không check revocation | Token TTL/RS revocation awareness |
| OP revocation 503/timeout | Provider/network outage | Bounded retry và partial outcome |
| Token xuất hiện lại sau logout | Background refresh save stale state | Version/tombstone/coordination |
| Logout thất bại chỉ trên node B | Local store/session config khác | Shared DB/Spring Session/instance diagnosis |
| MockMvc test pass nhưng OP cookie còn | oidcLogin mock không chạy browser OP logout | Browser E2E |
| Back-channel logout không dọn JDBC tokens | Session cleanup chưa nối service store | Verified logout event + cleanup integration |
| Browser đổi account nhưng còn token cũ | Account switch không cleanup/partition | Principal key, cache invalidation |
| Local logout không xóa cookie | Wrong cookie path/domain hoặc custom cookie | Session invalidation, Set-Cookie, browser behavior |
| Logout loop khi browser quay về Portal | /logged-out protected hoặc auto-login trigger | Anonymous landing page |
| OP session chỉ kết thúc trên một thiết bị | OP policy/session-scoped logout | Global logout requirements |

### 30.1. Một quy trình chẩn đoán

~~~mermaid
flowchart TD
    A["User bấm Logout"] --> B{"POST /logout có CSRF và đúng chain?"}
    B -->|Không| C["Sửa form, CSRF, matcher, cookies"]
    B -->|Có| D{"Local session/SecurityContext kết thúc?"}
    D -->|Không| E["LogoutFilter, handlers, session repo"]
    D -->|Có| F{"Authorized client record còn trong store?"}
    F -->|Có| G["Xác minh storage/source of truth, principal key, cleanup"]
    F -->|Không| H{"Có yêu cầu remote token revocation?"}
    H -->|Có| I["RFC7009 endpoint, response, failure/retry policy"]
    H -->|Không| J{"Có yêu cầu OP SSO logout?"}
    I --> J
    J -->|Có| K["end_session_endpoint và browser redirects"]
    J -->|Không| L["Local logout outcome đã được xác minh"]
    K --> M["Kiểm tra OP SSO behavior và post_logout_redirect_uri"]
~~~

### 30.2. Không suy diễn chỉ từ một HTTP status

HTTP 302 từ Portal có thể là local logout redirect, không chứng minh OP đã xử lý. HTTP 200 từ RFC 7009 không chứng minh toàn bộ access tokens tức thời vô hiệu. HTTP 204 từ disconnect endpoint chỉ chứng minh application xử lý request theo contract local.

## 31. Logs, metrics và audit không làm lộ credentials

### 31.1. Các sự kiện nên có

~~~text
event=portal_logout_requested
providerAlias=company
logoutScope=current_session
correlationId=example

event=authorized_client_cleanup
providerAlias=partner
operation=remove
outcome=success
correlationId=example

event=oidc_rp_initiated_logout_redirect
providerAlias=company
outcome=redirect_created
correlationId=example

event=oauth2_revocation_requested
providerAlias=partner
tokenKind=refresh_token
outcome=timeout
correlationId=example
~~~

Không log:

~~~text
access_token
refresh_token
id_token
id_token_hint
client_secret
authorization_code
code_verifier
state / nonce thật
session cookie
raw OP error_description
~~~

### 31.2. Metrics gợi ý

| Metric tùy biến | Ý nghĩa |
|---|---|
| <code>portal_logout_total{provider,scope,result}</code> | Local logout events |
| <code>authorized_client_cleanup_total{provider,result}</code> | Kết quả local removal |
| <code>oauth2_revocation_total{provider,token_kind,result}</code> | Remote revocation request outcomes |
| <code>oauth2_revocation_latency_seconds{provider}</code> | Latency gọi OP |
| <code>oidc_logout_redirect_total{provider,result}</code> | Portal tạo OP logout redirect |
| <code>authorized_client_resurrection_detected_total{provider}</code> | Guard phát hiện stale refresh save sau logout |
| <code>backchannel_logout_total{provider,result}</code> | Verified OP logout notifications |

Đây là tên metrics **đề xuất để tự instrument**, không phải Spring Security mặc định phát tất cả.

### 31.3. Điều không nên gắn label

Không dùng email, raw subject, token hash đầy đủ, refresh token ID, session ID hoặc correlation ID làm metric labels có cardinality không kiểm soát. Có thể dùng correlation ID trong restricted logs/traces, nhưng cũng cần retention/access policy.

### 31.4. Redirect-to-OP không chứng minh OP completion

Metric <code>oidc_logout_redirect_total</code> chỉ nói Portal đã tạo redirect. Đừng đặt tên là <code>op_logout_success_total</code> nếu không có signal/contract đáng tin từ OP chứng minh session termination.

## 32. Test matrix cho bài thực hành

| ID | Scenario | Loại test | Kỳ vọng |
|---|---|---|---|
| LOG-01 | Logout không có CSRF | MockMvc | HTTP 403 |
| LOG-02 | Logout có CSRF | MockMvc | LogoutFilter thực thi |
| LOG-03 | Logout anonymous | MockMvc/unit | Không xóa token user bất kỳ |
| LOG-04 | Logout OAuth2 user Alice | Unit | Xóa đúng Alice/company |
| LOG-05 | User Alice có Company + Partner | Unit | Xóa đúng policy |
| LOG-06 | Bob vẫn còn authorized client | Unit | Không xóa Bob |
| LOG-07 | Unknown registration | Unit | No-op/handled theo policy |
| LOG-08 | Service store unavailable | Fault injection | Local logout + cleanup failure handling |
| LOG-09 | HTTP session-backed tokens | Integration | Session invalidation semantics |
| LOG-10 | JDBC persistent authorized clients | Integration | Record được xóa |
| LOG-11 | OP không có end_session_endpoint | Integration | Fallback đúng |
| LOG-12 | OP hỗ trợ RP-Initiated Logout | Browser E2E | Browser đi qua OP logout |
| LOG-13 | post_logout_redirect_uri sai | OP integration | Bị OP từ chối |
| LOG-14 | Local logout nhưng OP SSO cookie còn | Browser E2E | Login lại có thể SSO |
| LOG-15 | OP logout thành công | Browser E2E | Session behavior theo OP |
| LOG-16 | RFC7009 refresh-token revocation | OP integration | Remote revocation policy |
| LOG-17 | Revocation endpoint unknown token | Protocol test | Không suy token từng tồn tại |
| LOG-18 | Revocation HTTP 503 | Fault injection | Bounded failure/retry |
| LOG-19 | Revocation timeout unknown outcome | Fault injection | Không report false success |
| LOG-20 | Access JWT còn hiệu lực sau local deletion | Resource Server | Theo token acceptance policy |
| LOG-21 | Logout cùng lúc refresh | Multi-node | Không resurrect token |
| LOG-22 | Two devices same principal | Integration | Scope logout đúng |
| LOG-23 | Account switching Alice → Bob | Integration | Không reuse Alice tokens |
| LOG-24 | Disconnect Partner | Controller/service | Company session không bị logout |
| LOG-25 | Back-channel Logout Token valid | OIDC integration | Correct sessions terminated |
| LOG-26 | Back-channel Logout Token forged | OIDC integration | Từ chối |
| LOG-27 | Logout public hostname qua proxy | Browser/ingress | HTTPS redirect URI đúng |
| LOG-28 | /logged-out anonymous route | MockMvc | Không login loop |

Những tests này có phạm vi khác nhau. Không cố thay thế một browser OP logout test bằng <code>oidcLogin()</code>, hoặc dùng unit removal test để khẳng định JWT access token đã bị revoke toàn hệ thống.

## 33. Checklist thực hành theo từng bước

### Giai đoạn A — Môi trường

1. Dựng OP test realm, user <code>alice.test</code>, client <code>portal-it</code>.
2. Đăng ký chính xác login callback và post-logout redirect URI.
3. Kiểm tra OP Discovery có <code>end_session_endpoint</code> không.
4. Kiểm tra có <code>revocation_endpoint</code> nếu muốn remote revoke.
5. Tạo Spring Boot Servlet OAuth2 Client với session/cookie settings test.
6. Bảo đảm test data, client secrets và signing keys không thuộc production.

### Giai đoạn B — Local logout

1. Tạo form POST <code>/logout</code> có CSRF token.
2. Cấu hình <code>LogoutFilter</code> qua <code>http.logout(...)</code>.
3. Tạo public <code>/logged-out</code> landing route.
4. Xác nhận SecurityContext được clear và HTTP session invalidated.
5. Test request protected sau logout bị yêu cầu authentication.
6. Test logout thiếu CSRF bị từ chối.

### Giai đoạn C — Authorized-client cleanup

1. Chọn service/repository thực sự đang được dùng.
2. Xác định key registration ID và verified principal name.
3. Thêm custom LogoutHandler cho service-backed data.
4. Xác định policy remove current registration hay all connections.
5. Test Alice/Bob và nhiều registrations.
6. Nếu dùng JDBC/Redis, kiểm tra persistence và session invalidation tách biệt.

### Giai đoạn D — OIDC SSO logout

1. Tạo <code>OidcClientInitiatedLogoutSuccessHandler</code>.
2. Thiết lập post-logout redirect URL an toàn.
3. Browser đăng nhập qua OP test.
4. Submit logout POST.
5. Xác minh browser được redirect tới OP end-session endpoint.
6. Quan sát OP session behavior khi login lại trong browser context cũ.
7. Test provider không hỗ trợ logout.

### Giai đoạn E — Optional token revocation

1. Quyết định token/grant nào cần remote revoke.
2. Chỉ dùng trusted provider revocation endpoint.
3. Lấy token trước khi xóa local.
4. Gửi RFC 7009 request với client authentication đúng.
5. Ghi normalized result và xóa local record theo policy.
6. Test unknown token, timeout, 503, invalid_client và partial failure.
7. Test token acceptance ở Resource Server theo format/policy.

### Giai đoạn F — Production hardening

1. Dùng HTTPS, exact redirect URIs, trusted forwarded headers.
2. Có shared sessions/authorized-client store nếu chạy cluster.
3. Chống refresh save sau logout bằng version/coordination khi cần.
4. Quản lý logout per-device vs all-devices rõ ràng.
5. Không log tokens/ID Token hints/authorization codes/session cookies.
6. Cấu hình bounded timeouts/retries và metrics/audit.
7. Viết incident runbook và E2E smoke tests trên staging.

## 34. Những lỗi thiết kế phổ biến

### 34.1. Chỉ xóa SecurityContext rồi tuyên bố token đã bị revoke

Sai vì persistent authorized-client records và issued tokens có lifecycle riêng.

### 34.2. Chỉ gọi OP logout endpoint rồi bỏ qua local session

OP SSO session bị xóa chưa chắc Portal session đã invalidated ngay. Portal vẫn phải xử lý local logout.

### 34.3. Xóa token bằng email từ query

Sai vì user có thể giả mạo email và email không phải verified storage owner key.

### 34.4. Gọi remove sau khi session token không còn

Với session-backed repository, cần hiểu thứ tự handler nếu remote revoke cần access token trước khi invalidation.

### 34.5. Dùng clientCredentials token để “giả làm” user logout

Client Credentials grant là service identity, không phải OIDC browser user session. Không dùng nó chứng minh RP-Initiated Logout hoặc xóa delegated user grants.

### 34.6. Bật GET /logout và bỏ CSRF

Browser logout là state-changing action; nên dùng POST và CSRF phù hợp.

### 34.7. Hardcode external post_logout_redirect_uri

OP có thể từ chối hoặc ứng dụng tạo open redirect. Chỉ dùng registered/trusted HTTPS destinations cho môi trường hiện tại.

### 34.8. Tự POST unsigned JSON làm Back-Channel Logout

OIDC Back-Channel Logout dùng verified Logout Token với security claims; JSON không ký không chứng minh OP gửi.

### 34.9. Giữ refresh token trong queue chưa mã hóa để retry

Retryable cleanup job chứa secrets cần encryption, access controls, expiry/retention và audit.

### 34.10. Không xử lý token resurrection

Background refresh có thể save token mới sau local deletion. Dùng version/tombstone/coordination theo kiến trúc.

## 35. Production hardening: khi local cleanup gặp lỗi

<code>AuthorizedClientCleanupLogoutHandler</code> ở mục 10 cố tình đơn giản để làm rõ service API. Trong production, <code>removeAuthorizedClient</code> có thể throw runtime exception khi JDBC/Redis unavailable.

### 35.1. Không để cleanup exception ngăn local logout

Một policy thực tế có thể là:

~~~text
Local session must end even if persisted cleanup fails
    → local logout = complete
    → cleanup status = failed/pending
    → secure retry if required
    → never claim remote revocation completed without evidence
~~~

Đó là quyết định bảo mật/nghiệp vụ, không bắt buộc mọi sản phẩm phải chọn y hệt. Với yêu cầu remote revocation bắt buộc trước khi hoàn tất, cần xử lý failure/UX khác.

### 35.2. Handler production nên tránh ném exception khỏi logout lifecycle

Một cách triển khai có kiểm soát:

~~~java
for (String registrationId : registrationIds) {
    try {
        service.removeAuthorizedClient(
            registrationId, principalName);
        // Publish sanitized cleanup success event.
    } catch (RuntimeException cleanupFailure) {
        // Publish normalized failure category and provider alias.
        // Enqueue bounded, secure retry if business policy requires.
        // Do not leak raw tokens or credentials to logs.
        // Keep local logout progressing according to security policy.
    }
}
~~~

Với framework <code>LogoutHandler</code>, tránh throw khiến chuỗi logout không hoàn tất. Nhưng đừng âm thầm bỏ qua lỗi: application phải có một nguồn audit/metric và quy trình reconciliation cho dangling token records.

### 35.3. Retry cleanup có thể xóa nhầm grant mới

~~~text
T0: user logout, old authorized client version=7
T1: cleanup retry scheduled
T2: user logs in again, new authorized client version=8
T3: old cleanup retry runs
~~~

Một <code>removeAuthorizedClient(registrationId, principalName)</code> vô điều kiện tại T3 có thể xóa **version 8**, không phải record cũ. Với delayed cleanup, nên dùng generation/version/record identity hoặc tombstone policy để cleanup intent chỉ tác động lên grant cần thu hồi.

### 35.4. OP và database không cùng một ACID transaction

~~~text
DB removal succeeds, OP revoke fails
OP revoke succeeds, DB removal fails
Network timeout, outcome unknown
~~~

Phải hỗ trợ partial outcomes và recovery; không giả định một database transaction bao luôn HTTP revocation tại OP.

### 35.5. Đăng nhập lại trong lúc cleanup đang chạy

Test phải xác minh:

- Grant mới không bị cleanup cũ xóa.
- Refresh job cũ không save token đã revoked sau logout.
- Session mới không nhận authorized client của phiên/tenant khác.
- Metrics phản ánh pending/failed cleanup.

## 36. Bài tập tự luyện

### Bài 1 — Logout local có xóa OP SSO cookie?

User logout khỏi Portal rồi bấm Login, OP đưa vào ngay không hỏi password.

**Đáp án:** Không nhất thiết local logout sai. OP cookie/session có thể còn; dùng RP-Initiated Logout khi muốn chấm dứt OP SSO theo provider policy.

### Bài 2 — Local removal có revoke remote token?

~~~java
service.removeAuthorizedClient("company", principalName);
~~~

**Đáp án:** Chỉ xóa bản ghi authorized client trong local service, không mặc nhiên gọi RFC 7009 endpoint.

### Bài 3 — Vì sao logout cần CSRF?

**Đáp án:** Đây là state-changing browser action; dùng POST với CSRF để tránh yêu cầu logout không mong muốn từ site khác.

### Bài 4 — MockMvc trả HTTP 403

~~~java
mockMvc.perform(post("/logout").with(oidcLogin()));
~~~

**Đáp án:** Nếu CSRF enabled, POST thiếu token nên bị chặn. Trong test hợp lệ thêm <code>.with(csrf())</code>.

### Bài 5 — @WithMockUser có test cleanup OAuth2AuthenticationToken?

**Đáp án:** Không chắc. Handler ở mục 10 chỉ nhận <code>OAuth2AuthenticationToken</code>; <code>@WithMockUser</code> tạo loại Authentication khác nên cleanup branch không chạy.

### Bài 6 — Xóa nhầm Bob

Endpoint dùng <code>request.getParameter("user")</code> làm principal name và Alice gửi <code>user=bob</code>.

**Đáp án:** Lỗ hổng ownership. Phải lấy verified Authentication server-side, không tin tên user browser truyền.

### Bài 7 — Xóa Company nhưng Partner còn

Alice có authorized clients ở Company và Partner, handler chỉ remove Company.

**Đáp án:** Đủ nếu policy “current registration only”, không đủ nếu sản phẩm hứa full cleanup. Cần explicit policy và tests.

### Bài 8 — PrincipalName có luôn bằng email?

**Đáp án:** Không. Key phải khớp lúc authorized client được save; có thể là OIDC subject/custom name và phải tránh cross-issuer/tenant collisions.

### Bài 9 — HTTP session invalidation có xóa JDBC token?

**Đáp án:** Không mặc nhiên. JDBC service-backed token records tồn tại độc lập với session nếu app không cleanup.

### Bài 10 — End-session endpoint có phải revocation endpoint?

**Đáp án:** Không. OIDC end-session phục vụ OP SSO logout; RFC 7009 revocation phục vụ thu hồi token/grant.

### Bài 11 — Revocation trả HTTP 200

**Đáp án:** HTTP 200 không chứng minh token từng tồn tại hoặc tất cả Resource Servers đã vô hiệu access JWT ngay lập tức.

### Bài 12 — Self-contained JWT sau logout

JWT hết hạn 10:15, Portal logout lúc 10:02, Resource Server chỉ verify signature/expiry.

**Đáp án:** JWT cũ có thể còn được RS nhận tới 10:15 nếu không có dynamic revocation check.

### Bài 13 — OP không hỗ trợ end_session_endpoint

**Đáp án:** Local logout có thể hoàn tất, nhưng không khẳng định OP SSO logout. Cần fallback và UX phản ánh sự thật.

### Bài 14 — Redirect URI bị OP từ chối

<code>post_logout_redirect_uri</code> sai HTTPS host.

**Đáp án:** Kiểm tra exact URI registered tại OP, trusted forwarded headers và <code>{baseUrl}</code> expansion.

### Bài 15 — Browser không theo OP redirect

User đã được đưa khỏi Portal nhưng đóng tab trước khi browser gọi OP end-session endpoint.

**Đáp án:** Local session có thể đã kết thúc; OP session có thể còn. Cần browser E2E và UX phù hợp, không nói OP logout complete dựa vào Portal 302.

### Bài 16 — Session-backed repository

Token chỉ nằm trong HttpSession. Custom handler chạy sau session invalidation nên không load được refresh token để revoke.

**Đáp án:** Muốn remote revocation, cần capture token trước invalidation bằng orchestration rõ thứ tự; còn local cleanup có thể dựa vào session invalidation theo repository semantics.

### Bài 17 — Token resurrection

Node B save A1/R1 sau khi Node A remove authorized-client record khi logout.

**Đáp án:** Dùng grant generation/tombstone, recheck status, CAS và coordination để cấm stale refresh save tái tạo token.

### Bài 18 — Retry cleanup xóa token mới

User logout rồi login lại, cleanup task của session cũ chạy muộn.

**Đáp án:** Không remove current record vô điều kiện; gắn cleanup intent với generation/version của grant cũ để giữ grant mới.

### Bài 19 — Logout một thiết bị

Browser A và B của cùng principal chia sẻ service record.

**Đáp án:** Remove shared record khi A logout có thể ảnh hưởng B. Xác định policy per-device/per-principal; session invalidation và service cleanup là hai scopes khác.

### Bài 20 — Disconnect Partner

User vẫn đăng nhập Company nhưng muốn ngắt Partner.

**Đáp án:** Dùng POST disconnect có CSRF, allowed registration và verified ownership; không nhất thiết invalidate Portal session. Remote revoke nếu policy/provider hỗ trợ.

### Bài 21 — Back-Channel Logout Token giả

Attacker POST unsigned JSON với <code>sub=alice</code> đến back-channel endpoint.

**Đáp án:** Không tin. Phải verify signed Logout Token, <code>iss</code>, <code>aud</code>, <code>events</code>, <code>sid/sub</code> và các yêu cầu theo OIDC profile.

### Bài 22 — Remote revocation timeout

Portal gửi request revoke refresh token nhưng không nhận response.

**Đáp án:** Outcome không chắc chắn. Dùng bounded retry/reconciliation, telemetry và policy local logout; không khẳng định remote revoke đã hoàn thành.

### Bài 23 — OP logout có bằng global logout?

**Đáp án:** Không mặc định. Cần xác minh OP session scope, Portal global session registry, token/grant policies và behavior các devices khác.

### Bài 24 — oidcLogin() có chứng minh OP SSO logout?

**Đáp án:** Không. <code>oidcLogin()</code> giả lập principal trong request test, không thực hiện browser/OP session termination.

### Bài 25 — Lab kiểm thử logout end-to-end

Thiết lập:

~~~text
Keycloak/OP test
Spring Boot OAuth2/OIDC Client
Service-backed JDBC authorized-client store
POST /logout + CSRF
OidcClientInitiatedLogoutSuccessHandler
~~~

**Yêu cầu:** Login Alice; xác minh authorized-client record được lưu; logout; xác minh local session bị invalidated và record được cleanup; kiểm tra browser qua OP logout rồi về <code>/logged-out</code>. Đừng dựa chỉ vào HTTP status 302.

### Bài 26 — Negative tests

Viết tests cho:

~~~text
Missing CSRF
Wrong principal
Wrong registration
OP lacks end_session_endpoint
Revocation HTTP 503
JDBC unavailable
Forged Back-Channel Logout Token
~~~

**Đáp án yêu cầu:** Với mỗi test, ghi rõ expected local session state, token store state, OP outcome và log redaction.

### Bài 27 — Thiết kế policy đa registration

User có Company, Partner và Analytics. UI có ba hành động: logout current device, disconnect Partner, logout Portal và xóa mọi delegated clients.

**Gợi ý:** Lập state-transition table cho từng action, bao gồm Portal session, OAuth2AuthorizedClientService, OP SSO và remote token/grant state. Không dùng một handler cho mọi action khi phạm vi cleanup khác nhau.

### Bài 28 — Bài tích hợp tổng hợp

1. Dựng OP test và client riêng, không dùng production credentials.
2. Cấu hình Authorization Code/OIDC Login.
3. Dùng service-backed authorized-client store.
4. Tạo <code>AuthorizedClientCleanupLogoutHandler</code>.
5. Tạo form POST logout với CSRF.
6. Gắn <code>OidcClientInitiatedLogoutSuccessHandler</code>.
7. Đăng ký chính xác post-logout redirect URI tại OP.
8. Tạo <code>/logged-out</code> public endpoint.
9. Unit test xóa Alice/company và Alice/partner nhưng giữ Bob.
10. MockMvc test thiếu CSRF bị 403, logout hợp lệ được xử lý.
11. Browser E2E test OP SSO logout thực tế.
12. Tùy chọn RFC 7009 revocation test với refresh token test-only.
13. Test Access JWT có thể vẫn hợp lệ sau local deletion theo Resource Server policy.
14. Test two-device logout policy.
15. Test logout vs refresh race trên shared store.
16. Test cleanup retry không xóa reauthorization mới.
17. Test forged Back-Channel Logout Token bị từ chối.
18. Kiểm tra logs không có tokens, session cookies hoặc ID Token hint.
19. Xây runbook khi OP revocation/logout endpoint unavailable.
20. Ghi lại bằng chứng cho từng scope của logout.

**Câu hỏi tổng hợp:** Bạn đã chứng minh độc lập được bốn điều sau chưa: **local session đã kết thúc**, **local authorized-client records đã bị xóa đúng**, **OP SSO session đã kết thúc theo provider policy**, và **remote tokens/grants đã được revoke theo contract của Authorization Server**?

## 37. Tổng kết

- **Local logout**, **OIDC RP-Initiated Logout**, **authorized-client cleanup** và **RFC 7009 revocation** là bốn cơ chế khác nhau.
- Local logout clear <code>SecurityContext</code>/HTTP session. Xóa local session không mặc nhiên xóa tokens ở JDBC/Redis, OP SSO session hoặc issued access tokens.
- <code>OAuth2AuthorizedClientService</code> xóa theo <code>registrationId</code> và <code>principalName</code>; principal phải đến từ authenticated server-side identity, không từ browser input.
- <code>OAuth2AuthorizedClientRepository</code> có thể session-backed hoặc service-backed; phải biết source of truth của save/load/refresh/remove.
- Custom <code>LogoutHandler</code> xử lý local cleanup. <code>OidcClientInitiatedLogoutSuccessHandler</code> khởi tạo OP end-session redirect khi provider hỗ trợ.
- Browser logout nên dùng **POST + CSRF**, và <code>/logged-out</code> phải là public route để tránh redirect loop.
- <code>post_logout_redirect_uri</code> cần được OP cho phép chính xác theo môi trường, dùng public HTTPS base URL đáng tin.
- OIDC OP logout không đồng nghĩa local storage cleanup; RFC 7009 token revocation không đồng nghĩa OP SSO logout.
- Revocation HTTP 200 không chứng minh token từng tồn tại hoặc mọi Resource Server đã vô hiệu JWT ngay lập tức.
- Full logout và disconnect một provider có scopes khác nhau; với nhiều devices, shared service-backed records cần ownership/cleanup policy rõ.
- Refresh-token rotation và background jobs có thể tạo **token resurrection** sau logout. Cleanup retry chậm cũng có thể xóa nhầm authorized client mới. Dùng version/tombstone/conditional writes và coordination khi cần.
- OIDC Back-Channel Logout cần **signed Logout Token** và verified issuer/audience/session mapping; không dùng unsigned JSON để xóa sessions.
- LogoutHandler production nên tránh ném exception cản trở local logout, có metrics và reliable cleanup process phù hợp.
- Unit tests chứng minh service cleanup; MockMvc chứng minh CSRF/LogoutFilter; browser tests chứng minh OP SSO behavior; revocation tests chứng minh OP token/grant contract. Không một loại test nào thay thế hoàn toàn các loại còn lại.
- Logs/metrics chỉ ghi normalized outcomes, provider alias/correlation IDs an toàn, không log raw access/refresh/ID Tokens, <code>id_token_hint</code>, authorization codes, client secrets hoặc session cookies.

### Tài liệu tham khảo

- **Spring Security Reference — Servlet Authentication Logout:** LogoutFilter, LogoutHandler, LogoutSuccessHandler và CSRF logout.
- **Spring Security Reference — OAuth2 Login (Servlet):** ClientRegistration, Authentication và OIDC User.
- **Spring Security Reference — OAuth2 Client:** OAuth2AuthorizedClientService, OAuth2AuthorizedClientRepository và authorized-client persistence.
- **Spring Security Java API — OidcClientInitiatedLogoutSuccessHandler:** RP-Initiated Logout và post-logout redirect URI.
- **Spring Security Java API — InMemoryOAuth2AuthorizedClientService / JdbcOAuth2AuthorizedClientService:** local storage implementations.
- **Spring Security Test Reference — MockMvc:** oidcLogin(), oauth2Login(), csrf() và logout testing.
- **OpenID Connect RP-Initiated Logout 1.0:** end_session_endpoint, id_token_hint, post_logout_redirect_uri và logout state.
- **OpenID Connect Back-Channel Logout 1.0:** Logout Token, issuer/audience/events/sid/sub và OP-initiated session termination.
- **OpenID Connect Core 1.0:** ID Token, authenticated principal, issuer/subject và session semantics.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** authorization grants, access and refresh tokens.
- **RFC 7009 — OAuth 2.0 Token Revocation:** revocation endpoint, token_type_hint và response semantics.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** refresh-token rotation, token replay và credential handling.
- **OWASP Cross-Site Request Forgery Prevention Cheat Sheet:** logout và browser state-changing requests.
- **OWASP Session Management Cheat Sheet:** session invalidation, cookies và session lifecycle.
- **OWASP Logging Cheat Sheet:** không log credentials, tokens, session secrets và PII.
