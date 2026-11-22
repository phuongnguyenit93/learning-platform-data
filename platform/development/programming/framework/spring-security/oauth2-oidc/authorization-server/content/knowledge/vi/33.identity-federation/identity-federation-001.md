# Authorization Server đồng thời đóng vai trò OAuth2 Client với IdP bên ngoài

> **Chương: Liên kết danh tính.** Bài thuộc module **SPRING_SECURITY_OIDC_AUTHORIZATION_SERVER**, hướng dẫn thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong Spring Boot. Bài học tập trung vào mô hình **federated identity**: Authorization Server nội bộ dùng Spring Security OAuth2 Client để đăng nhập người dùng qua một Identity Provider (IdP) bên ngoài, sau đó tiếp tục đóng vai trò Authorization Server/OpenID Provider cho các ứng dụng downstream.

## 1. Bài toán: một máy chủ giữ hai vai trò OAuth khác nhau

Trong hệ thống liên kết danh tính, một Authorization Server nội bộ có thể vừa là:

- **OAuth2 Client / Relying Party (RP):** chuyển hướng người dùng tới IdP bên ngoài, nhận authorization response, đổi authorization code và xác minh danh tính do IdP cung cấp.
- **OAuth2 Authorization Server / OpenID Provider (OP):** quản lý client nội bộ, xác thực và ủy quyền người dùng theo chính sách của tổ chức, phát access token và ID Token riêng cho ứng dụng downstream.

Ví dụ xuyên suốt:

| Thành phần | Giá trị minh họa | Vai trò |
|---|---|---|
| IdP bên ngoài | `https://identity.partner.example` | Xác thực người dùng và phát upstream ID Token/access token |
| Authorization Server nội bộ | `https://login.example.vn` | Là OAuth2 Client với IdP, đồng thời là AS/OP nội bộ |
| Upstream client registration | `corporate-idp` | Client ID mà AS nội bộ đăng ký tại IdP |
| Ứng dụng downstream | `portal-web` | OAuth2/OIDC client của AS nội bộ |
| Resource Server nội bộ | `https://api.example.vn` | Xác minh access token do AS nội bộ phát hành |
| Local user | `local-user-8472` | Danh tính nội bộ được ánh xạ từ tài khoản upstream |

Luồng điển hình:

1. Người dùng truy cập `portal-web` và bắt đầu đăng nhập qua AS nội bộ.
2. AS nội bộ chưa có phiên đăng nhập, chuyển browser tới IdP bên ngoài.
3. IdP xác thực người dùng và trả authorization code về callback của AS nội bộ.
4. AS nội bộ đổi code lấy token, xác minh OIDC ID Token hoặc lấy UserInfo theo cấu hình provider.
5. Ứng dụng tìm hoặc tạo local user, liên kết với danh tính upstream.
6. AS nội bộ hoàn tất phiên đăng nhập local.
7. `portal-web` tiếp tục Authorization Code Flow với AS nội bộ và nhận **token do AS nội bộ phát hành**.

IdP bên ngoài xác thực người dùng cho AS nội bộ. Các ứng dụng downstream vẫn tin cậy issuer nội bộ và nhận token theo chính sách nội bộ. Federation identity **không đồng nghĩa** với việc chuyển nguyên access token của IdP cho mọi API nội bộ.

## 2. Phân biệt authentication federation và authorization delegation

Hai khái niệm này thường bị trộn lẫn:

| Khía cạnh | Authentication federation | Authorization/delegation |
|---|---|---|
| Câu hỏi | Người dùng là ai theo IdP đã tin cậy? | Người dùng/client được phép làm gì với resource? |
| Bằng chứng | OIDC ID Token hoặc kết quả xác thực OAuth2 UserInfo đã được xác minh | Local roles, permissions, scopes, consent và policy |
| Chủ thể quyết định | IdP xác thực; AS nội bộ kiểm tra và ánh xạ danh tính | AS nội bộ và Resource Server theo chính sách local |
| Kết quả | Local authenticated principal/session | Local authorization và token claims/scopes |
| Vòng đời | Account linking, upstream session, IdP disablement | Local grant, access/refresh token, consent, revocation |

IdP bên ngoài có thể gửi claim như `groups` hoặc `roles`, nhưng AS nội bộ không nên tự động tin và cấp mọi quyền từ các claim đó. Cần mapping policy có allowlist: group nào tương ứng role nào, thuộc tenant nào, có cần phê duyệt hay không.

Ví dụ, IdP trả `groups=["finance-admin"]` không có nghĩa người dùng tự động trở thành admin của mọi tenant nội bộ. AS cần xác minh issuer, subject, tenant context và chính sách cấp quyền trước khi sử dụng claim.

## 3. Luồng liên kết danh tính với hai Authorization Server

~~~mermaid
sequenceDiagram
    autonumber
    participant U as User Browser
    participant RP as portal-web
    participant AS as Local Authorization Server / OP
    participant IDP as External IdP
    participant DB as Local Identity Store
    participant API as Internal Resource Server

    U->>RP: Mở ứng dụng
    RP->>AS: Authorization Request (client nội bộ)
    AS->>AS: Chưa có local session
    AS-->>U: Redirect /oauth2/authorization/corporate-idp
    U->>IDP: Authorization Request (AS nội bộ là OAuth Client)
    IDP->>U: Login / MFA / consent
    U-->>IDP: Authentication thành công
    IDP-->>U: Redirect callback với authorization code
    U->>AS: /login/oauth2/code/corporate-idp?code=...
    AS->>IDP: Token Request + client authentication
    IDP-->>AS: Upstream ID Token / access token
    AS->>AS: Verify issuer, signature, audience, expiry, nonce
    AS->>DB: Resolve hoặc provision (issuer, sub)
    DB-->>AS: Local user + local authorities
    AS->>AS: Tạo local authenticated session
    AS-->>U: Tiếp tục Authorization Request ban đầu
    AS-->>RP: Local authorization code
    RP->>AS: Đổi code tại local token endpoint
    AS-->>RP: Local access_token + local id_token
    RP->>API: Gọi API bằng local access_token
    API-->>RP: Response theo local audience/scope
~~~

Trong sơ đồ có **hai OAuth client relationship** khác nhau:

- AS nội bộ là client của IdP, với client ID riêng do IdP cấp.
- `portal-web` là client của AS nội bộ, có registration và credential riêng.

Hai registration không dùng chung client ID, secret, redirect URI hoặc authorization grant. Mỗi bên có issuer, audience, consent và token lifecycle riêng.

## 4. Đăng ký AS nội bộ tại IdP bên ngoài

Trước khi cấu hình Spring, cần tạo một OAuth/OIDC client application tại IdP.

| Thuộc tính | Ví dụ | Cách sử dụng |
|---|---|---|
| Issuer | `https://identity.partner.example` | Discovery và kiểm tra issuer |
| Client ID | `local-as-client-123` | Định danh AS nội bộ tại IdP |
| Client Secret | Secret do IdP cấp | Client authentication ở upstream token endpoint |
| Authorization endpoint | Lấy từ OIDC Discovery | Browser redirect để đăng nhập |
| Token endpoint | Lấy từ OIDC Discovery | Đổi authorization code |
| JWK Set URI | Lấy từ metadata | Xác minh chữ ký upstream ID Token |
| UserInfo endpoint | Lấy từ metadata | Lấy claims bổ sung nếu cần |
| Redirect URI | `https://login.example.vn/login/oauth2/code/corporate-idp` | Callback chính xác của Spring Security |

Redirect URI phải được đăng ký chính xác tại IdP. Spring Security dùng template mặc định:

~~~text
{baseUrl}/login/oauth2/code/{registrationId}
~~~

Với registration ID `corporate-idp`, callback public là:

~~~text
https://login.example.vn/login/oauth2/code/corporate-idp
~~~

Nếu AS chạy sau reverse proxy, phải cấu hình forwarded headers và public base URL đúng để Spring tạo redirect URI khớp với URI đã đăng ký. Không dùng wildcard rộng hoặc open redirect để giải quyết khác biệt URL.

## 5. Cấu hình Spring Security OAuth2 Client

Spring Security OAuth2 Client quản lý upstream IdP thông qua `ClientRegistration`. Mỗi registration chứa client ID/secret, grant type, redirect URI, scopes và thông tin provider.

Ứng dụng cần dependency `spring-boot-starter-oauth2-client` bên cạnh dependency Spring Authorization Server đang dùng:

~~~gradle
implementation("org.springframework.boot:spring-boot-starter-oauth2-client")
~~~

Với IdP hỗ trợ OIDC Discovery, có thể cấu hình bằng `issuer-uri`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate-idp:
            provider: corporate
            client-id: ${CORPORATE_IDP_CLIENT_ID}
            client-secret: ${CORPORATE_IDP_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          corporate:
            issuer-uri: https://identity.partner.example
~~~

Spring Boot/Spring Security có thể dùng issuer để discovery Provider Configuration và lấy authorization endpoint, token endpoint, JWK Set URI, UserInfo endpoint cùng metadata liên quan. Nếu provider không hỗ trợ OIDC Discovery, cần cấu hình endpoint và UserInfo mapping rõ ràng.

Client secret phải được inject từ secret manager hoặc environment; không commit giá trị thật vào source code, YAML hoặc container image.

### 5.1. Provider chỉ hỗ trợ OAuth 2.0, không có OIDC

Một số provider cung cấp OAuth 2.0 authorization code và UserInfo API nhưng không phát ID Token. Khi đó có thể cấu hình endpoint tường minh:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          legacy-idp:
            provider: legacy
            client-id: ${LEGACY_IDP_CLIENT_ID}
            client-secret: ${LEGACY_IDP_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - user.read
        provider:
          legacy:
            authorization-uri: https://legacy.example.net/oauth/authorize
            token-uri: https://legacy.example.net/oauth/token
            user-info-uri: https://legacy.example.net/api/me
            user-info-authentication-method: header
            user-name-attribute: id
~~~

Trong trường hợp này, principal thường là `OAuth2User` chứ không phải `OidcUser`. `user-name-attribute` phải trỏ tới thuộc tính định danh ổn định, duy nhất và được provider cam kết. Không dùng display name hoặc email làm khóa tài khoản nếu provider có immutable subject/user ID.

OIDC Discovery và ID Token validation cung cấp contract danh tính chuẩn hóa tốt hơn. Nếu chỉ có OAuth2 UserInfo, cần đánh giá độ tin cậy, TLS, API contract, uniqueness và vòng đời identifier của provider.

## 6. Cấu hình SecurityFilterChain: AS nội bộ và OAuth2 Login

Spring Authorization Server có một filter chain cho protocol endpoints của AS. Spring Security OAuth2 Login được cấu hình trong chain ứng dụng để AS nội bộ có thể xác thực người dùng qua IdP.

Ví dụ Servlet stack với Spring Authorization Server 1.5.x:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.LoginUrlAuthenticationEntryPoint;
import org.springframework.security.web.util.matcher.MediaTypeRequestMatcher;

@Configuration(proxyBeanMethods = false)
class FederatedAuthorizationServerSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerChain(HttpSecurity http)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
                OAuth2AuthorizationServerConfigurer.authorizationServer();

        http.securityMatcher(authorizationServer.getEndpointsMatcher())
                .with(authorizationServer, server ->
                        server.oidc(Customizer.withDefaults()))
                .authorizeHttpRequests(authorize ->
                        authorize.anyRequest().authenticated())
                .exceptionHandling(exceptions ->
                        exceptions.defaultAuthenticationEntryPointFor(
                                new LoginUrlAuthenticationEntryPoint(
                                        "/oauth2/authorization/corporate-idp"),
                                new MediaTypeRequestMatcher(MediaType.TEXT_HTML)));

        return http.build();
    }

    @Bean
    FederatedLoginSuccessHandler federatedLoginSuccessHandler(
            ClientRegistrationRepository registrations,
            FederatedIdentityService identities) {
        return new FederatedLoginSuccessHandler(registrations, identities);
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationChain(
            HttpSecurity http,
            FederatedLoginSuccessHandler successHandler) throws Exception {

        http.authorizeHttpRequests(authorize ->
                        authorize.anyRequest().authenticated())
                .oauth2Login(oauth2 ->
                        oauth2.successHandler(successHandler));

        return http.build();
    }
}
~~~

Ý nghĩa cấu hình:

- Chain thứ nhất xử lý OAuth2/OIDC protocol endpoints của AS nội bộ.
- OIDC được bật để AS nội bộ phát hành ID Token và cung cấp Provider Configuration/UserInfo theo cấu hình.
- Browser request tới authorization endpoint cần user authentication sẽ được chuyển tới `/oauth2/authorization/corporate-idp`.
- Chain thứ hai bật `oauth2Login()` để Spring Security thực hiện authorization code flow với IdP.
- Success handler là nơi ứng dụng resolve/provision local identity sau khi upstream authentication thành công.

Ví dụ này chọn một IdP cố định. Nếu có nhiều IdP, nên hiển thị login page cho người dùng chọn provider hoặc chọn theo tenant policy đã xác thực. Không tự động chuyển tới IdP dựa trên một URL tùy ý do người dùng gửi.

Không tắt CSRF protection tổng quát chỉ để xử lý callback. Dùng filter, authorization request repository và cơ chế state của Spring Security; nếu tùy chỉnh callback hoặc session storage, phải giữ ràng buộc giao dịch và kiểm thử CSRF.

## 7. Upstream login thành công: resolve hoặc provision local user

Khi Spring Security xử lý callback thành công, ứng dụng nhận principal từ upstream provider. Với OIDC, principal thường là `OidcUser` và chứa ID Token đã được Spring Security xác minh. Đây là thời điểm thích hợp để tìm hoặc tạo local identity.

### 7.1. Khóa định danh federation phải là issuer và subject

Với OIDC, khóa ngoài nên là cặp:

~~~text
(external_issuer, external_sub)
~~~

Ví dụ:

| External issuer | External subject | Local user |
|---|---|---|
| `https://identity.partner.example` | `00u8x91abc` | `local-user-8472` |
| `https://accounts.vendor.example` | `00u8x91abc` | `local-user-9921` |

Dù hai provider cùng trả `sub=00u8x91abc`, đó là hai subject thuộc hai issuer khác nhau. Không được dùng riêng `sub` làm global key.

OIDC Core định nghĩa `sub` là subject identifier duy nhất trong phạm vi issuer và không được tái cấp cho người khác. Vì vậy cặp `(iss, sub)` là khóa thích hợp để liên kết identity upstream. Email, username, display name và số điện thoại có thể đổi, trùng hoặc được tái sử dụng.

### 7.2. Just-in-time provisioning

Nếu local user chưa tồn tại, hệ thống có thể tạo account khi đăng nhập lần đầu (JIT provisioning). Quy trình cần:

1. Xác minh upstream identity đã thành công.
2. Lấy issuer đã cấu hình/tin cậy và subject đã xác minh.
3. Tìm external identity theo unique key `(issuer, sub)`.
4. Nếu có, tải local user và kiểm tra trạng thái enabled/locked/deprovisioned.
5. Nếu chưa có, kiểm tra domain, tenant, invitation, allowlist hoặc policy onboarding.
6. Tạo local user với local subject không đổi trong suốt vòng đời.
7. Tạo external identity link với unique constraint để tránh race khi hai login đồng thời.
8. Chỉ đồng bộ các profile fields được phép; lưu provenance và thời điểm cập nhật.

Không tự động cấp quyền quản trị chỉ vì IdP trả một group/role. Local authorities phải được ánh xạ bằng policy riêng.

### 7.3. Ví dụ success handler

Ví dụ dưới đây chỉ xử lý OIDC provider đã cấu hình issuer discovery. Service `FederatedIdentityService` là thành phần nghiệp vụ do ứng dụng triển khai.

~~~java
import java.io.IOException;

import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
import org.springframework.security.web.authentication.SavedRequestAwareAuthenticationSuccessHandler;

final class FederatedLoginSuccessHandler
        implements AuthenticationSuccessHandler {

    private final ClientRegistrationRepository registrations;
    private final FederatedIdentityService identities;
    private final AuthenticationSuccessHandler delegate =
            new SavedRequestAwareAuthenticationSuccessHandler();

    FederatedLoginSuccessHandler(
            ClientRegistrationRepository registrations,
            FederatedIdentityService identities) {
        this.registrations = registrations;
        this.identities = identities;
    }

    @Override
    public void onAuthenticationSuccess(
            HttpServletRequest request,
            HttpServletResponse response,
            Authentication authentication)
            throws IOException, ServletException {

        if (!(authentication instanceof OAuth2AuthenticationToken oauth2)
                || !(oauth2.getPrincipal() instanceof OidcUser oidcUser)) {
            throw new ServletException(
                    "This federation handler requires an OIDC provider");
        }

        ClientRegistration registration =
                registrations.findByRegistrationId(
                        oauth2.getAuthorizedClientRegistrationId());

        if (registration == null
                || registration.getProviderDetails().getIssuerUri() == null) {
            throw new ServletException("Trusted OIDC issuer is not configured");
        }

        String issuer = registration.getProviderDetails().getIssuerUri();
        String subject = oidcUser.getSubject();

        // Resolve or provision local identity using the verified (issuer, sub).
        identities.resolveOrProvision(
                issuer, subject, FederatedProfile.from(oidcUser));

        delegate.onAuthenticationSuccess(request, response, authentication);
    }
}
~~~

`FederatedProfile` là projection do ứng dụng định nghĩa, chỉ chứa các profile attributes được allowlist; không chuyển toàn bộ claims upstream vào local store. Service nghiệp vụ phải đảm bảo unique constraint trên issuer + subject, xử lý race và kiểm tra local user status. Chỉ nhận issuer từ ClientRegistration đã cấu hình; không lấy issuer tùy tiện từ request parameter. Với provider OAuth2 không phải OIDC, cần handler riêng dùng immutable provider-specific user ID đã được xác minh.

### 7.4. Account linking phải có bằng chứng kiểm soát tài khoản

Nếu người dùng đã có local account và muốn liên kết thêm IdP:

- Yêu cầu người dùng đã đăng nhập local và xác thực lại khi rủi ro cao.
- Bắt đầu federation transaction từ session local đã xác thực, bảo vệ CSRF/state.
- Sau callback, xác minh cặp issuer + subject.
- Hiển thị xác nhận provider/account đang liên kết.
- Áp unique constraint để một external identity không bị link vào hai local accounts.
- Ghi audit actor, provider, subject reference đã bảo vệ và thời điểm link/unlink.

Không tự động link local account theo email trùng. Email có thể chưa verified, đổi chủ hoặc được tái sử dụng; ngay cả email verified cũng không thay thế bằng chứng người dùng kiểm soát local account hiện tại.

## 8. Ánh xạ claims upstream thành local identity và ID Token

IdP bên ngoài có thể trả claims như `name`, `email`, `email_verified`, `groups`, `locale` và các thuộc tính riêng. AS nội bộ cần quyết định claim nào được lưu trong local profile, claim nào được đưa vào local ID Token, claim nào được ánh xạ thành local authorities và claim nào cần loại bỏ.

### 8.1. Không copy toàn bộ claims từ IdP

Không dùng thao tác copy tất cả upstream claims mà không lọc. Upstream có thể có claims trùng tên chuẩn, giá trị sai kiểu, thông tin nội bộ hoặc role không phù hợp với local policy.

Không cho upstream ghi đè các claim do local OP quản lý như:

- `iss` — issuer của **AS nội bộ**.
- `sub` — local subject identifier theo contract của OP nội bộ.
- `aud` — client ID downstream.
- `iat`, `exp` — thời gian do local AS phát hành.
- `nonce`, `auth_time`, `acr`, `amr` — claims xác thực do local OP quản lý theo policy.
- `azp`, `at_hash`, `c_hash` — claims do local OIDC flow quyết định khi áp dụng.

Upstream ID Token là chứng cứ để AS nội bộ xác minh đăng nhập; không phải bản ID Token nội bộ cần phát lại nguyên văn.

### 8.2. Local subject khác external subject

Local OP nên duy trì local subject ổn định. Ví dụ:

~~~text
Upstream identity:
  issuer  = https://identity.partner.example
  subject = 00u8x91abc

Local identity:
  local_subject = local-user-8472
~~~

ID Token nội bộ có `iss=https://login.example.vn` và `sub=local-user-8472`. RP downstream chỉ cần biết danh tính trong miền issuer nội bộ. AS nội bộ giữ mapping upstream/local trong identity store.

Nếu business yêu cầu pairwise subject identifier, local OP có thể phát subject khác nhau theo client/sector theo quy tắc ổn định, không tái cấp và được quản lý như một phần của OIDC subject policy.

### 8.3. Ví dụ OAuth2TokenCustomizer

Spring Authorization Server cung cấp `OAuth2TokenCustomizer<JwtEncodingContext>` để tùy chỉnh claims khi phát JWT. Ví dụ dưới đây giả định `FederatedIdentityResolver` trả local identity đã được xác minh và chuẩn hóa từ principal của authorization flow:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.core.oidc.endpoint.OidcParameterNames;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Bean
OAuth2TokenCustomizer<JwtEncodingContext> federatedIdTokenCustomizer(
        FederatedIdentityResolver identityResolver) {

    return context -> {
        if (!OidcParameterNames.ID_TOKEN.equals(
                context.getTokenType().getValue())) {
            return;
        }

        FederatedIdentity identity =
                identityResolver.resolve(context.getPrincipal());

        // Local OP owns the subject; never copy upstream "sub".
        context.getClaims().subject(identity.localSubject());

        if (context.getAuthorizedScopes().contains(OidcScopes.PROFILE)) {
            context.getClaims().claim("name", identity.displayName());
            context.getClaims().claim("preferred_username",
                    identity.localUsername());
        }

        if (context.getAuthorizedScopes().contains(OidcScopes.EMAIL)
                && identity.emailVerified()) {
            context.getClaims().claim("email", identity.email());
            context.getClaims().claim("email_verified", true);
        }
    };
}
~~~

Đây là customizer skeleton; `FederatedIdentityResolver` và `FederatedIdentity` là kiểu nghiệp vụ do ứng dụng định nghĩa. Resolver phải ánh xạ principal đã xác thực sang local user; không tin trực tiếp claim email/roles từ browser. Chỉ thêm claims được yêu cầu/cho phép bởi scope và consent. Không ghi đè các claim chuẩn khác do Spring Authorization Server đã tạo.

Spring Authorization Server có hướng dẫn riêng về social login, lưu local users và map claims sang ID Token. Cần áp dụng allowlist và local identity mapping phù hợp với chính sách tổ chức.

## 9. Quản lý upstream tokens và local tokens

Trong mô hình federation, có thể tồn tại đồng thời hai nhóm token:

| Token | Issuer | Audience/consumer | Mục đích |
|---|---|---|---|
| Upstream ID Token | IdP bên ngoài | AS nội bộ (OAuth2 Client/RP) | Chứng minh authentication từ IdP |
| Upstream access token | IdP bên ngoài | API/resource của IdP | Truy cập resource upstream nếu được cấp |
| Local ID Token | AS nội bộ | Downstream OIDC client | Chứng minh local OP đã xác thực local subject |
| Local access token | AS nội bộ | Resource Server nội bộ | Truy cập API nội bộ theo local scope/audience |
| Local refresh token | AS nội bộ | Local token endpoint | Gia hạn local access token theo policy |

### 9.1. Không chuyển upstream access token thành local access token

Không lấy upstream access token rồi trả thẳng cho `portal-web` hoặc Resource Server nội bộ với kỳ vọng nó đại diện cho local authorization. Token upstream có issuer, audience, scope, signing key và lifecycle riêng.

Local AS phải phát token riêng sau khi:

1. Xác thực external identity.
2. Resolve local user và trạng thái account.
3. Xác định client downstream và authorization request.
4. Áp consent, local roles, tenant, scope và audience.
5. Phát local access token/ID Token theo issuer nội bộ.

Resource Server nội bộ chỉ tin issuer và key đã cấu hình. Không thêm IdP ngoài vào trust list của mọi API nếu API không có use case trực tiếp để chấp nhận token upstream.

### 9.2. Khi cần gọi API của IdP hoặc upstream provider

Nếu AS nội bộ cần gọi API upstream thay mặt người dùng, có thể giữ authorized client/token theo thiết kế bằng `OAuth2AuthorizedClientService` hoặc `OAuth2AuthorizedClientRepository`. Việc lưu token phải có encryption at rest, access control, expiry/revocation handling và cleanup.

Dùng `OAuth2AuthorizedClientManager` để quản lý authorized client và thực hiện authorized API call. Không copy refresh token upstream vào local refresh token response.

Nếu cần delegation giữa hai security domain, hãy thiết kế token exchange hoặc một delegation contract riêng, xác định actor, subject, audience, scope và trust relationship. Token exchange không tự động xuất hiện chỉ vì đã bật `oauth2Login()`; cần support ở cả issuer, client và resource server.

## 10. Nhiều IdP, tenant và chống mix-up

Một AS nội bộ có thể cấu hình nhiều IdP: corporate directory, partner IdP hoặc social provider. Mỗi IdP phải là một `ClientRegistration` độc lập với registration ID, issuer, client credentials, endpoints và redirect URI tương ứng.

### 10.1. Không tin IdP do caller tự chọn

Nếu cho phép người dùng chọn provider, UI chỉ được gửi một registration ID nằm trong allowlist cấu hình. Không nhận authorization endpoint, token endpoint hoặc issuer URL tùy ý từ query string. Nếu lấy discovery URL tùy ý, server có thể bị SSRF hoặc gửi client credential tới endpoint của attacker.

Với multi-tenant, map tenant đã xác thực sang issuer/provider allowlist. Không dùng email domain chưa xác minh để tự động quyết định trust domain.

### 10.2. Mix-up attack khi client tương tác nhiều issuer

Khi một OAuth2 Client có thể tương tác với nhiều Authorization Server, cần chống mix-up attack. RFC 9700 khuyến nghị kiểm tra issuer của authorization response, ví dụ response parameter `iss` theo RFC 9207 hoặc cơ chế tương đương dựa trên issuer trong ID Token. Nếu không có, có thể dùng redirect URI riêng cho từng issuer theo yêu cầu của RFC 9700.

Với nhiều registration trong Spring Security:

- Dùng registration ID duy nhất cho từng provider.
- Đăng ký redirect URI cụ thể cho từng provider, ví dụ `/login/oauth2/code/corporate-idp` và `/login/oauth2/code/partner-idp`.
- Kiểm tra issuer/discovery metadata của từng provider và chỉ dùng token/JWK endpoint của provider đã khởi tạo transaction.
- Xác minh authorization response thuộc đúng registration/issuer; kiểm tra khả năng hỗ trợ RFC 9207 theo phiên bản và provider.
- Không tự viết callback handler bỏ qua state/issuer validation của Spring Security.
- Nếu provider không hỗ trợ issuer identification, dùng biện pháp redirect URI riêng và transaction binding đúng RFC; không xem riêng tên registration là đủ nếu ứng dụng tùy biến flow.

### 10.3. Tenant isolation

Identity federation không tự giải quyết tenant isolation. Cần lưu tenant/local account mapping rõ ràng:

| Thuộc tính | Quy tắc |
|---|---|
| External issuer | Thuộc allowlist của tenant hoặc trust domain |
| External subject | Unique trong issuer; không unique toàn hệ thống |
| Local user ID | Định danh nội bộ ổn định |
| Tenant membership | Được cấp theo local policy |
| External groups | Map qua allowlist/namespace, không tự cấp global roles |
| Client downstream | Chỉ được dùng scope/audience đã đăng ký và được consent |

Nếu cùng một external identity được phép tham gia nhiều tenant, cần model membership riêng và xác định tenant context trong từng authorization transaction.

## 11. Logout, unlink và deprovisioning

Logout ở một hệ thống federation có nhiều session/token lifecycle:

- Session của ứng dụng downstream.
- Session local tại AS nội bộ.
- Session SSO tại IdP bên ngoài.
- Local refresh/access tokens.
- Upstream authorized client tokens.

Một logout local không tự động logout tại IdP. Ngược lại, IdP session kết thúc cũng không bảo đảm local access token đã phát bị vô hiệu hóa tức thì.

### 11.1. Logout local

Khi user logout local:

1. Kết thúc local web session.
2. Xóa authorized client/token upstream nếu ứng dụng không còn cần.
3. Thu hồi local refresh token/authorization theo policy.
4. Xem xét local access token đã phát và cách Resource Server nhận revocation.
5. Nếu dùng OIDC logout, xử lý session/client notifications theo cấu hình riêng.

### 11.2. Unlink account

Unlink external identity cần yêu cầu local user có bằng chứng xác thực và phải đảm bảo vẫn còn phương thức đăng nhập hợp lệ. Không cho phép unlink identity cuối cùng khiến tài khoản bị khóa ngoài ý muốn nếu policy không cho phép.

Sau unlink:

- Xóa hoặc đánh dấu external identity link inactive.
- Revoke upstream authorized client nếu còn giữ token và provider hỗ trợ.
- Audit thao tác.
- Xác định local session hiện tại có cần re-authentication hay không.
- Không xóa local account nếu user còn dữ liệu/quyền cần giữ.

### 11.3. Deprovisioning từ IdP

Khi nhân viên bị disable ở IdP, local AS có thể không biết ngay nếu chỉ dùng local session và JWT offline. Tổ chức cần chọn cơ chế: session TTL ngắn, re-authentication định kỳ, back-channel event/SCIM hoặc admin synchronization, local account disablement, token revocation và Resource Server introspection/denylist.

Không suy rằng upstream ID Token hết hạn sẽ tự vô hiệu local access token đã phát.

## 12. Bảo mật vận hành và các ranh giới tin cậy

### 12.1. Upstream IdP

- Pin issuer theo cấu hình đã duyệt; xác minh ID Token signature, issuer, audience, expiry và nonce theo OIDC.
- Discovery/JWK Set chỉ lấy qua HTTPS từ issuer tin cậy.
- Theo dõi signing key rotation và cache JWKS.
- Dùng client secret hoặc private key theo phương thức đăng ký; quản lý trong secret manager.
- Chỉ yêu cầu scopes upstream thật sự cần.
- Không ghi authorization code, access token, refresh token, ID Token hoặc client secret vào log.

### 12.2. Local AS

- Duy trì issuer nội bộ ổn định.
- Local subject không tái cấp cho user khác.
- Kiểm tra account enabled/locked và tenant policy ở mỗi lần federation login.
- Áp dụng local consent, scope, audience và authorization; không sao chép quyền upstream một cách mù quáng.
- Dùng PKCE S256, state và nonce transaction-specific; redirect URI exact match.
- Bảo vệ session cookie, CSRF, SameSite và reverse proxy forwarded headers.
- Không cho callback hoặc post-login redirect chuyển tới URL tùy ý.
- Tách log/audit local và upstream; redact token/PII.

### 12.3. Token storage và authorized clients

Nếu lưu upstream authorized client tokens:

- Chỉ lưu khi có use case cần gọi upstream resource.
- Encrypt token/refresh token at rest và giới hạn ai có thể decrypt.
- Liên kết record với local principal, registration ID và tenant.
- Xử lý token expiry, refresh, revocation, user unlink và deprovisioning.
- Có retention/cleanup và không lưu raw token trong metric labels.

### 12.4. Account linking và claim mapping

- Dùng cặp issuer + subject làm external identity key.
- Email chỉ là profile attribute, không phải khóa liên kết mặc định.
- Không tự động link theo username/display name.
- Chỉ map claims được allowlist; giữ provenance của từng thuộc tính.
- Không tin group/role upstream nếu chưa có mapping policy.
- Ghi audit link/unlink/provisioning và thay đổi local authority.

## 13. Ma trận kiểm thử identity federation

| # | Tình huống | Kết quả mong đợi |
|---|---|---|
| 1 | Login với OIDC IdP hợp lệ | Spring OAuth2 Login hoàn tất và tạo local identity/session |
| 2 | IdP issuer khác allowlist | Không bắt đầu hoặc từ chối federation |
| 3 | ID Token signature sai | Authentication thất bại |
| 4 | ID Token issuer không khớp | Authentication thất bại |
| 5 | ID Token audience không chứa client ID local AS | Authentication thất bại |
| 6 | ID Token expired | Authentication thất bại |
| 7 | Nonce không khớp transaction | Authentication thất bại |
| 8 | Authorization response state sai/mất | Callback bị từ chối |
| 9 | Authorization code replay | Token exchange thất bại |
| 10 | Redirect URI khác URI đăng ký tại IdP | IdP từ chối hoặc flow bị abort |
| 11 | Upstream client secret sai | Token endpoint upstream từ chối |
| 12 | IdP không khả dụng | Login thất bại có kiểm soát; không fallback sang issuer khác |
| 13 | JWK signing key được rotate | Cache/refresh hoạt động và xác minh theo key mới |
| 14 | External issuer + sub đã tồn tại | Resolve đúng local user cũ |
| 15 | Cùng sub nhưng issuer khác | Tạo/liên kết identity riêng, không trộn user |
| 16 | External identity mới, tenant allowlist hợp lệ | JIT provisioning theo policy |
| 17 | External identity mới, tenant không được phép | Từ chối provisioning |
| 18 | Hai callback đồng thời cho cùng identity | Unique constraint không tạo hai local links |
| 19 | Email trùng local user nhưng chưa có account-link proof | Không tự động liên kết |
| 20 | Email thay đổi tại IdP | Local subject vẫn ổn định; profile sync theo policy |
| 21 | UserInfo không có stable ID | Từ chối hoặc yêu cầu provider-specific mapping đáng tin |
| 22 | Upstream group chứa role ngoài allowlist | Không cấp local role |
| 23 | Local user bị disable nhưng upstream login thành công | Local AS vẫn từ chối authorization |
| 24 | Downstream client đăng nhập sau federation | Nhận local authorization code và local tokens |
| 25 | Local access token có issuer/audience nội bộ | Resource Server nội bộ xác minh đúng local issuer |
| 26 | Upstream access token được gửi tới API nội bộ | Bị từ chối nếu API không trust issuer upstream |
| 27 | Local ID Token bị gửi tới API | API từ chối do sai token type/audience |
| 28 | Multi-IdP callback bị tráo issuer/registration | Mix-up defense abort transaction |
| 29 | Provider URL từ query string trỏ host lạ | Không thực hiện discovery/request (chống SSRF) |
| 30 | Logout local | Local session kết thúc; upstream session/token xử lý theo policy riêng |
| 31 | Unlink identity cuối cùng | Chặn nếu user không còn phương thức login hợp lệ |
| 32 | IdP deprovision user | Local disable/re-auth/revocation theo SLA |
| 33 | Upstream token refresh thất bại | Không ảnh hưởng sai local token; xử lý authorized client theo policy |
| 34 | Logging bật ở gateway/AS | Không lộ code, ID Token, access token, refresh token hay secret |
| 35 | Reverse proxy thay đổi host/proto | Redirect URI public vẫn chính xác và không tin header không xác thực |

### 13.1. Các assertion quan trọng

Integration test nên xác minh đồng thời:

- Authentication upstream được xác minh bằng đúng issuer/JWK/client registration.
- Local identity lookup dùng `(issuer, sub)`, không dùng email làm khóa.
- Local user được kiểm tra enabled/tenant/authority policy.
- Authorization request downstream được tiếp tục sau khi local login thành công.
- Local access token có issuer/audience/scope nội bộ.
- Upstream token không bị trả nhầm cho downstream client.
- ID Token nội bộ có local subject và claims được allowlist.
- Multi-provider callback không bị mix-up.
- Logout, unlink và deprovisioning có behavior được tài liệu hóa.

## 14. Troubleshooting, checklist production và tự đánh giá

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `/oauth2/authorization/corporate-idp` trả 404 | Thiếu OAuth2 Client dependency hoặc ClientRegistration | Kiểm tra starter, registration ID và auto-configuration |
| Callback trả 404 | Redirect URI không khớp filter callback pattern | Kiểm tra redirect-uri và proxy |
| IdP báo redirect_uri mismatch | URI đăng ký khác URI Spring gửi | Đồng bộ scheme/host/path và exact match |
| invalid_client tại upstream token endpoint | Client ID/secret/auth method sai | Kiểm tra credential và method tại IdP |
| Discovery không tải được | Issuer sai, TLS, metadata hoặc network | Kiểm tra issuer HTTPS và OIDC metadata |
| ID Token signature fail | JWK Set URI/key rotation/issuer sai | Kiểm tra discovery, kid và cache |
| Local user bị tạo trùng | Thiếu unique constraint (issuer, sub) | Bổ sung constraint và xử lý transaction race |
| Hai IdP cùng email bị gộp nhầm | Dùng email làm identity key | Dùng issuer + subject và account-link flow |
| Local token mang external sub | Không có local subject mapping | Map qua local identity resolver trước khi phát ID Token |
| Downstream API từ chối token | Client gửi upstream token hoặc ID Token | Dùng local access token đúng audience |
| Người dùng mất quyền nhưng vẫn gọi API | Local token/JWT còn hiệu lực | Disable local user, revoke/denylist/introspection theo SLA |
| Chỉ một IdP bị lỗi | Registration/provider endpoint/secret riêng bị sai | Kiểm tra từng ClientRegistration và trust config |

### 14.1. Checklist production

- [ ] AS nội bộ được đăng ký thành OAuth2 Client riêng tại từng upstream IdP.
- [ ] Dùng OIDC Discovery khi provider hỗ trợ; issuer được pin/allowlist.
- [ ] Redirect URI exact match và phản ánh public URL sau reverse proxy.
- [ ] OAuth2 Login được cấu hình trong application SecurityFilterChain riêng.
- [ ] Authorization Server chain và OIDC endpoints vẫn được cấu hình độc lập.
- [ ] State, nonce, PKCE S256 và callback transaction binding được bảo vệ.
- [ ] Client secret/private key upstream nằm trong secret manager.
- [ ] External identity được khóa bằng (issuer, sub); local subject ổn định.
- [ ] Account linking yêu cầu bằng chứng kiểm soát local account.
- [ ] JIT provisioning kiểm tra tenant, invitation, enabled/locked và policy.
- [ ] External groups/roles chỉ được map qua allowlist.
- [ ] Local ID Token không copy mù claims hoặc reserved claims của upstream.
- [ ] Local access token có local issuer/audience/scope.
- [ ] Upstream access token không bị forward cho downstream API ngoài contract delegation.
- [ ] Upstream authorized client tokens chỉ lưu khi cần, có encryption/retention/cleanup.
- [ ] Multi-IdP mix-up defense và issuer validation được kiểm thử.
- [ ] Logout, unlink và deprovisioning được thiết kế riêng.
- [ ] Metrics/audit không chứa token, secret hoặc PII không cần thiết.
- [ ] Có test cho key rotation, IdP outage, duplicate identity và cross-tenant isolation.

**Câu hỏi tự đánh giá**

1. Vì sao một Authorization Server có thể đồng thời là OAuth2 Client với IdP và OP cho client nội bộ?
2. Hai client registration trong mô hình federation khác nhau như thế nào?
3. Vì sao upstream ID Token chỉ là bằng chứng xác thực cho local AS, không phải ID Token nội bộ để phát lại?
4. Tại sao external identity cần khóa (issuer, sub) thay vì chỉ sub hoặc email?
5. JIT provisioning cần kiểm tra những policy nào trước khi tạo local user?
6. Vì sao account linking theo email trùng có thể dẫn tới account takeover?
7. oauth2Login() được cấu hình ở filter chain nào khi AS nội bộ dùng Spring Authorization Server?
8. OIDC provider và OAuth2 provider không có ID Token khác nhau thế nào về principal và validation?
9. Vì sao local ID Token nên có local iss và local sub?
10. Khi map claims upstream, những claim nào không được để upstream ghi đè?
11. Khác nhau giữa authentication federation và authorization delegation là gì?
12. Vì sao không chuyển upstream access token cho Resource Server nội bộ như local access token?
13. Khi có nhiều IdP, mix-up attack xảy ra thế nào và cần phòng vệ gì?
14. Logout local có tự kết thúc session tại IdP không?
15. Nếu IdP deprovision user, làm thế nào để local access token đang còn hiệu lực bị xử lý theo SLA?
16. Khi cần gọi API của IdP thay mặt user, nên quản lý authorized client token ra sao?

## Tài liệu tham khảo

- [Spring Authorization Server 1.5.8 — How-to: Authenticate using Social Login](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-social-login.html): OAuth2 Login, cấu hình IdP, capture local users và map claims vào ID Token.
- [Spring Security — OAuth2 Login Core Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): ClientRegistration, issuer discovery, redirect URI, UserInfo và OAuth2 Login.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): ClientRegistrationRepository, OAuth2AuthorizedClientService và quản lý authorized client.
- [Spring Boot — OAuth2 Client Configuration](https://docs.spring.io/spring-boot/reference/security/oauth2.html): nhiều registration/provider, issuer-uri và custom provider endpoints.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, issuer, subject, audience, nonce và validation.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): Provider Configuration, issuer và JWK Set metadata.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): PKCE, redirect URI, CSRF và mix-up attack defense khi client tương tác với nhiều issuer.
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207.html): tham số iss trong authorization response để client nhận diện đúng issuer.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693.html): delegation/token exchange giữa các miền tin cậy; không tự động được bật bởi OAuth2 Login.
