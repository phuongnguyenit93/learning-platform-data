# Thực hiện SSO giữa nhiều client dùng chung Authorization Server

> **Chương: Tích hợp ứng dụng.** Bài thuộc module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, hướng dẫn thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong Spring Boot. Trọng tâm là triển khai Single Sign-On (SSO) cho nhiều ứng dụng OAuth2/OIDC client cùng tin cậy một Authorization Server, quản lý browser session, xử lý consent và logout đúng ranh giới.

## 1. SSO trong mô hình nhiều client

Giả sử một tổ chức có nhiều ứng dụng:

| Ứng dụng | Client ID | Người dùng sử dụng |
|---|---|---|
| Cổng nhân viên | employee-portal | Nhân viên |
| Hệ thống đơn hàng | orders-web | Nhân viên bán hàng |
| Quản lý hóa đơn | billing-web | Kế toán |
| Dashboard quản trị | admin-console | Quản trị viên |

Tất cả ứng dụng đều đăng ký với cùng Authorization Server:

~~~text
https://login.example.vn
~~~

Khi người dùng đăng nhập vào Cổng nhân viên, Authorization Server tạo một phiên đăng nhập tại domain của nó. Sau đó người dùng mở Hệ thống đơn hàng. Ứng dụng này vẫn phải gửi authorization request tới Authorization Server, nhưng browser gửi kèm session cookie của login.example.vn. Authorization Server nhận ra phiên đăng nhập hiện tại và có thể tiếp tục flow mà không yêu cầu người dùng nhập lại mật khẩu.

Đây là SSO dựa trên **phiên đăng nhập tại Authorization Server**:

- Mỗi client có client_id, redirect URI, scopes, client authentication method và policy riêng.
- Người dùng xác thực tại Authorization Server một lần trong browser session.
- Những authorization request tiếp theo từ client khác có thể dùng lại phiên đăng nhập đó.
- Mỗi client vẫn nhận authorization code và token của chính client đó.
- Consent và quyền truy cập vẫn được đánh giá theo client, principal, scope và policy.

SSO không phải là chia sẻ access token giữa các ứng dụng. Nó giúp tái sử dụng trạng thái xác thực của người dùng tại Authorization Server.

SSO trong bài này là user SSO qua browser. Luồng client_credentials dùng cho workload/service-to-service không có người dùng tương tác và không dựa trên browser session; việc hai service dùng chung Authorization Server không tự tạo user SSO.

## 2. Phân biệt các loại session và credential

Trong kiến trúc này có nhiều trạng thái độc lập:

| Thành phần | Ai quản lý | Phạm vi |
|---|---|---|
| Authorization Server browser session | Spring Security tại Authorization Server | Nhận diện người dùng đã đăng nhập tại OP |
| Client A application session | Client A | Giữ trạng thái đăng nhập cục bộ tại ứng dụng A |
| Client B application session | Client B | Giữ trạng thái đăng nhập cục bộ tại ứng dụng B |
| Authorization code | Authorization Server | Một authorization transaction, dùng một lần |
| Access token | Authorization Server | Quyền truy cập API theo scope/audience/lifetime |
| ID Token | OpenID Provider | Bằng chứng authentication dành cho OIDC client |
| Refresh token (nếu policy cho phép) | Authorization Server | Cấp access token mới theo policy của client |

Một browser session tại Authorization Server có thể phục vụ nhiều client. Tuy nhiên, phiên local tại Client A không tự động tạo phiên local tại Client B. Client B cần hoàn tất callback và tạo session riêng sau khi nhận kết quả authorization.

Access token của Client A cũng không trở thành token của Client B. Mỗi client phải dùng token được cấp trong flow của nó và Resource Server phải kiểm tra issuer, audience, scope, expiry cùng policy tương ứng.

## 3. Luồng SSO khi người dùng chuyển từ client A sang client B

~~~mermaid
sequenceDiagram
    autonumber
    participant U as User Browser
    participant A as Client A
    participant B as Client B
    participant AS as Shared Authorization Server
    participant API as Resource Server

    U->>A: Mở Cổng nhân viên
    A->>U: Redirect tới AS /authorize (client A)
    U->>AS: Authorization Request A
    AS->>AS: Chưa có authenticated session
    AS-->>U: Hiển thị login page
    U->>AS: Đăng nhập thành công
    AS->>AS: Lưu SecurityContext vào HTTP session
    AS-->>U: Redirect callback A với authorization code
    U->>A: Callback A
    A->>AS: Token Request A
    AS-->>A: Token dành cho client A
    A->>U: Tạo local session A

    U->>B: Mở Hệ thống đơn hàng
    B->>U: Redirect tới AS /authorize (client B)
    U->>AS: Authorization Request B + AS session cookie
    AS->>AS: Khôi phục SecurityContext hiện có
    AS->>AS: Kiểm tra client B, redirect, scope và consent
    AS-->>U: Redirect callback B với authorization code
    U->>B: Callback B
    B->>AS: Token Request B
    AS-->>B: Token dành cho client B
    B->>U: Tạo local session B
    B->>API: Gọi API bằng access token B
    API-->>B: Resource response
~~~

Điểm tạo ra SSO nằm ở lần authorization request thứ hai: browser vẫn có session cookie của Authorization Server. Authorization Server không cần xác thực lại mật khẩu nếu phiên còn hiệu lực và request không yêu cầu re-authentication.

### 3.1. Điều kiện để SSO hoạt động

- Các client phải dùng cùng issuer/Authorization Server có browser session chung.
- Browser phải gửi session cookie tới domain của Authorization Server.
- Các request phải đi qua cùng hệ thống session hoặc session store được chia sẻ giữa các instance.
- SecurityContext phải được persist và khôi phục qua các HTTP request.
- Session chưa hết hạn, chưa bị revoke và user chưa bị disable.
- Chính sách xác thực của authorization request không yêu cầu đăng nhập lại.

Nếu mỗi client dùng một Authorization Server khác domain, cookie session của domain này không được gửi sang domain kia. Khi đó cần một IdP hoặc federation layer chung để các Authorization Server có thể dựa vào cùng một hệ thống SSO.

Nếu một host phục vụ nhiều issuer theo tenant path, cookie host-only có thể được browser gửi tới mọi path trên host đó. Điều này không có nghĩa user session hoặc authorization của tenant A được phép dùng ở tenant B. Phải kiểm tra tenant/issuer context và account membership trong từng authorization transaction; session cookie chỉ chứng minh browser có một phiên với host.

## 4. Đăng ký từng client riêng biệt

SSO không làm mất yêu cầu đăng ký từng ứng dụng. Ví dụ hai web client server-side có thể dùng confidential client authentication:

~~~java
import java.time.Duration;
import java.util.UUID;

import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

RegisteredClient employeePortal = RegisteredClient
        .withId(UUID.randomUUID().toString())
        .clientId("employee-portal")
        .clientName("Employee Portal")
        .clientSecret(passwordEncoder.encode(employeePortalSecret))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("https://portal.example.vn/login/oauth2/code/internal")
        .postLogoutRedirectUri("https://portal.example.vn/logout/callback")
        .scope(OidcScopes.OPENID)
        .scope(OidcScopes.PROFILE)
        .scope("employee.read")
        .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .requireAuthorizationConsent(true)
                .build())
        .tokenSettings(TokenSettings.builder()
                .accessTokenTimeToLive(Duration.ofMinutes(10))
                .build())
        .build();

RegisteredClient ordersWeb = RegisteredClient
        .withId(UUID.randomUUID().toString())
        .clientId("orders-web")
        .clientName("Orders Web")
        .clientSecret(passwordEncoder.encode(ordersWebSecret))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("https://orders.example.vn/login/oauth2/code/internal")
        .postLogoutRedirectUri("https://orders.example.vn/logout/callback")
        .scope(OidcScopes.OPENID)
        .scope(OidcScopes.PROFILE)
        .scope("orders.read")
        .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .requireAuthorizationConsent(true)
                .build())
        .tokenSettings(TokenSettings.builder()
                .accessTokenTimeToLive(Duration.ofMinutes(10))
                .build())
        .build();
~~~

Đây là ví dụ cho hai ứng dụng server-side có khả năng giữ secret. Nếu client là SPA hoặc native app, đăng ký public client với phương thức authentication phù hợp và bắt buộc PKCE; không nhúng client secret vào frontend/mobile binary.

Các thuộc tính phải khác nhau theo ứng dụng:

- client_id và client authentication credential.
- Redirect URI và post-logout redirect URI.
- Allowed grant types, scopes và token settings.
- Consent policy và claims/audience được phép nhận.

Không dùng một client_id chung cho nhiều ứng dụng chỉ để đạt SSO. Việc tách registration giúp revoke, audit, giới hạn scope và xử lý sự cố theo từng ứng dụng.

### 4.1. Lưu registration bền vững

RegisteredClientRepository cần lưu registration ổn định giữa các lần restart. Development có thể dùng InMemoryRegisteredClientRepository; production nên dùng JDBC hoặc persistence implementation phù hợp.

Mỗi redirect URI phải được đăng ký chính xác. postLogoutRedirectUri cũng phải thuộc registration của client để Authorization Server xác minh trước khi redirect sau logout.

## 5. Cấu hình OAuth2/OIDC Login ở từng client

Mỗi ứng dụng Spring Security OAuth2 Client đăng ký cùng issuer nhưng có client-id, secret và redirect URI riêng.

Ví dụ cấu hình tại Client A:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          internal:
            provider: company-as
            client-id: employee-portal
            client-secret: ${EMPLOYEE_PORTAL_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - employee.read
        provider:
          company-as:
            issuer-uri: https://login.example.vn
~~~

Client B có registration tương tự nhưng dùng client-id, secret, redirect URI và scopes của orders-web.

Khi user chưa có session local tại Client B, Spring Security khởi động OAuth2 Login. Browser được chuyển tới Authorization Server. Nếu AS session còn hiệu lực, người dùng có thể quay về Client B mà không nhập lại credential.

### 5.1. Không chia sẻ ClientRegistration hoặc AuthorizedClient giữa các ứng dụng

ClientRegistration là cấu hình OAuth client. OAuth2AuthorizedClient gắn với registration ID, principal và token được cấp cho client đó. Không sao chép authorized client của Client A sang Client B.

Nếu hai ứng dụng dùng chung một database để lưu authorized client, key và access policy vẫn phải phân biệt application/registration/principal. Không để ứng dụng A đọc refresh token của ứng dụng B.

## 6. Cấu hình session và SecurityContext tại Authorization Server

Spring Security mặc định persist SecurityContext vào HTTP session để khôi phục Authentication trong các request tiếp theo. Đây là cơ chế nền tảng cho browser-based SSO.

Authorization Server xử lý protocol endpoints và application login có thể nằm ở các SecurityFilterChain riêng. Các chain phải dùng session-based security context phù hợp; không cấu hình Authorization Server browser flow thành stateless nếu muốn giữ SSO.

Ví dụ cấu hình rút gọn:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.LoginUrlAuthenticationEntryPoint;
import org.springframework.security.web.util.matcher.MediaTypeRequestMatcher;
import org.springframework.security.config.http.SessionCreationPolicy;

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
            .exceptionHandling(exceptions ->
                    exceptions.defaultAuthenticationEntryPointFor(
                            new LoginUrlAuthenticationEntryPoint("/login"),
                            new MediaTypeRequestMatcher(MediaType.TEXT_HTML)))
            .sessionManagement(session ->
                    session.sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED));

    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain loginAndApplicationChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(authorize ->
                    authorize
                            .requestMatchers("/login", "/assets/**").permitAll()
                            .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .sessionManagement(session ->
                    session.sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
                            .sessionFixation(fixation -> fixation.changeSessionId()));

    return http.build();
}
~~~

Ví dụ minh họa cấu trúc filter chain. Ứng dụng cần bổ sung các bean và policy khác của Authorization Server như RegisteredClientRepository, authorization service, consent service, JWKSource và user authentication.

Các điểm cần nhớ:

- IF_REQUIRED cho phép tạo session khi browser login/authorization flow cần.
- Không đặt SessionCreationPolicy.STATELESS cho browser authorization flow nếu kỳ vọng SSO qua HTTP session.
- Spring Security bảo vệ session fixation bằng cách thay session ID khi xác thực thành công.
- Nếu controller/filter tự tạo Authentication, phải persist SecurityContext qua SecurityContextRepository; không chỉ set SecurityContextHolder rồi cho rằng request sau sẽ tự nhận được session.

## 7. Session cookie và domain của Authorization Server

Các client không cần đọc session cookie của Authorization Server. Khi browser redirect tới login.example.vn, browser tự gửi cookie thuộc domain này. Cookie nên được giới hạn ở Authorization Server.

Ví dụ Spring Boot:

~~~yaml
server:
  servlet:
    session:
      cookie:
        name: __Host-ASSESSION
        path: /
        http-only: true
        secure: true
        same-site: lax
~~~

Với cookie prefix __Host-, cần HTTPS, Path=/ và không khai báo Domain. Đây là lựa chọn phù hợp để cookie host-only chỉ được gửi tới login.example.vn.

Không cần đặt Domain=.example.vn chỉ vì portal và orders dùng subdomain khác nhau. Browser không cần gửi cookie AS tới các client; chúng chỉ cần browser điều hướng tới AS để cookie được gửi cho đúng host.

### 7.1. SameSite và redirect

SameSite=Lax thường phù hợp với authorization code flow dùng top-level browser navigation và GET callback. Nếu triển khai response_mode=form_post, iframe hoặc một flow cross-site POST khác, cần kiểm tra hành vi cookie thực tế; có thể phải điều chỉnh SameSite theo yêu cầu, đồng thời giữ CSRF/state validation và Secure.

Không chuyển sang SameSite=None một cách mặc định. Cookie None phải có Secure và làm tăng phạm vi gửi cookie trong ngữ cảnh cross-site.

### 7.2. SSO trong nhiều browser profile

SSO chỉ tái sử dụng session trong browser context có cookie tương ứng:

- Cùng browser profile và các tab thông thường thường dùng chung cookie jar.
- Incognito/private window thường có cookie jar riêng.
- Browser khác có cookie jar riêng.
- Xóa cookie hoặc hết hạn session sẽ yêu cầu xác thực lại.
- Native app có thể dùng system browser và chia sẻ SSO tùy nền tảng; embedded WebView thường có cookie/session tách biệt và không nên dùng làm user-agent đăng nhập OAuth.

## 8. Session store khi chạy nhiều instance

Trong production, Authorization Server thường có nhiều application instance. Nếu request đầu tiên tạo session ở node A nhưng request tiếp theo đến node B, node B phải khôi phục được cùng session và SecurityContext.

| Mô hình | Cách hoạt động | Điều cần bảo đảm |
|---|---|---|
| Sticky session | Load balancer ưu tiên cùng node | Node còn sống và session không mất khi failover |
| Shared session store | Nhiều node dùng cùng session repository | Session ID, SecurityContext và expiry được chia sẻ |
| Distributed cache/session | Dùng Redis hoặc store tương đương | Serialization, TTL, eviction và availability được cấu hình đúng |

Với Spring Session, có thể lưu HTTP session trong Redis hoặc database. Mọi node cần cùng namespace/cookie configuration, session serializer tương thích và clock policy phù hợp.

Nếu OIDC logout hoặc concurrent session control dùng SessionRegistry, phải kiểm tra cách registry được đồng bộ giữa các node. Một SessionRegistry chỉ nằm trong RAM của từng node không đủ để node A nhìn thấy session được tạo ở node B. Dùng event publisher và shared/distributed session tracking phù hợp với deployment.

Không lưu session ID vào log hoặc metric label. Không dùng session ID làm user ID hay correlation ID công khai.

## 9. Consent vẫn được xét riêng cho từng client

SSO chỉ giúp Authorization Server nhận ra user đã đăng nhập. Nó không có nghĩa user đã chấp thuận mọi quyền của mọi ứng dụng.

Ví dụ:

- Client A yêu cầu openid profile employee.read.
- Client B yêu cầu openid profile orders.read orders.write.

Người dùng có thể đã consent employee.read cho Client A nhưng chưa từng consent orders.write cho Client B. Authorization Server vẫn cần áp dụng consent policy cho Client B.

Spring Authorization Server lưu consent thông qua OAuth2AuthorizationConsentService, gắn với RegisteredClient và principal. Consent của một client không tự động trở thành consent của client khác. Trong multi-tenant hoặc multi-issuer, consent store còn phải được cô lập theo tenant/issuer.

### 9.1. Consent và silent authorization

Nếu client đã có consent phù hợp, AS có thể tiếp tục authorization mà không hiển thị consent page, tùy policy. Nếu scopes mới hoặc nhạy cảm xuất hiện, cần yêu cầu consent bổ sung hoặc re-consent.

Không tắt consent toàn cục chỉ để làm SSO trông liền mạch. SSO là giảm thao tác đăng nhập lặp lại; consent vẫn là quyết định riêng về quyền truy cập.

## 10. Kiểm soát yêu cầu đăng nhập lại bằng OIDC parameters

OIDC Authorization Request có các tham số ảnh hưởng đến tương tác người dùng:

| Parameter | Ý nghĩa |
|---|---|
| prompt=none | Yêu cầu không hiển thị UI; nếu cần tương tác thì trả lỗi phù hợp |
| prompt=login | Yêu cầu xác thực lại, không chỉ dựa vào session hiện tại |
| prompt=consent | Yêu cầu hiển thị consent |
| prompt=select_account | Yêu cầu người dùng chọn account |
| max_age | Giới hạn tuổi tối đa của lần xác thực; nếu quá cũ phải re-authenticate |

Ví dụ client yêu cầu silent authentication:

~~~text
GET /oauth2/authorize
    ?response_type=code
    &client_id=employee-portal
    &redirect_uri=https%3A%2F%2Fportal.example.vn%2Flogin%2Foauth2%2Fcode%2Finternal
    &scope=openid%20profile
    &prompt=none
    &state=STATE_VALUE
    &nonce=NONCE_VALUE
~~~

Nếu không có session đăng nhập phù hợp, hoặc policy yêu cầu consent/MFA/re-authentication, Authorization Server không được âm thầm hiển thị login page khi prompt=none; phải trả lỗi OIDC phù hợp như login_required, consent_required hoặc interaction_required.

prompt=login yêu cầu re-authentication. Nếu Authorization Server chỉ thấy session cũ và vẫn tiếp tục mà không xác thực lại, server chưa đáp ứng ý nghĩa của request. Với max_age, OP cần kiểm tra thời điểm xác thực và phát auth_time khi OIDC yêu cầu.

Các giá trị prompt là contract của OIDC. Cần kiểm tra behavior của phiên bản Spring Authorization Server đang dùng; nếu provider chưa thực thi đầy đủ, bổ sung authorization request validation/interaction policy và integration tests. Không giả định chỉ gửi parameter là framework tự động thực hiện mọi semantics.

## 11. Logout: local logout và SSO logout

Logout có nhiều phạm vi khác nhau:

| Hành động | Điều bị kết thúc | Điều không tự động kết thúc |
|---|---|---|
| Logout tại Client A | Session local của A | AS session, Client B session và token đã phát |
| Logout tại Authorization Server | Browser SSO session tại AS | Session local của mọi client và mọi access token |
| RP-Initiated Logout | Client yêu cầu OP kết thúc session của user tại AS | Không mặc nhiên đảm bảo mọi RP khác đã xóa session |
| Back-channel/front-channel logout | Thông báo tới client/RP theo giao thức đã triển khai | Không tự động revoke mọi token nếu không có policy tương ứng |
| Token revocation | Token được revoke theo token store/introspection policy | Không tự động xóa browser session |

Nếu user chỉ logout tại Client A, lần sau mở Client B, browser có thể vẫn có AS session và đăng nhập tiếp mà không hỏi mật khẩu. Đây là hành vi bình thường của SSO.

Nếu muốn logout SSO, Client A cần khởi tạo OIDC RP-Initiated Logout tới end-session endpoint của Authorization Server. AS xác minh request, id_token_hint, client và post_logout_redirect_uri rồi kết thúc session tương ứng theo cấu hình.

### 11.1. Bật OIDC logout tại Authorization Server

Spring Authorization Server cấu hình OIDC bằng:

~~~java
OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

http.securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server ->
                server.oidc(Customizer.withDefaults()));
~~~

OIDC configurer bật các OIDC endpoints, trong đó có RP-Initiated Logout endpoint. OidcLogoutAuthenticationProvider sử dụng SessionRegistry để tìm session của End-User. Kiểm tra discovery metadata để client lấy đúng end_session_endpoint.

Client registration cần khai báo post-logout redirect URI được phép:

~~~java
RegisteredClient employeePortal = RegisteredClient
        .withId("registered-client-employee-portal")
        .clientId("employee-portal")
        // Các client settings và grant types khác
        .postLogoutRedirectUri("https://portal.example.vn/logout/callback")
        .build();
~~~

Chỉ cho phép URI đã đăng ký. Không redirect tới URL tùy ý do client gửi.

### 11.2. Client khởi tạo RP-Initiated Logout bằng Spring Security

Với Spring Security OAuth2 Client, có thể dùng OidcClientInitiatedLogoutSuccessHandler:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.oidc.web.logout.OidcClientInitiatedLogoutSuccessHandler;
import org.springframework.security.web.authentication.logout.LogoutSuccessHandler;

@Bean
LogoutSuccessHandler oidcLogoutSuccessHandler(
        ClientRegistrationRepository registrations) {

    OidcClientInitiatedLogoutSuccessHandler handler =
            new OidcClientInitiatedLogoutSuccessHandler(registrations);

    handler.setPostLogoutRedirectUri("{baseUrl}/logout/callback");
    return handler;
}
~~~

Gắn handler vào filter chain của client:

~~~java
http.logout(logout ->
        logout.logoutSuccessHandler(oidcLogoutSuccessHandler));
~~~

Client cần discovery issuer để lấy end_session_endpoint, gửi ID Token hint theo hỗ trợ của handler/provider và dùng post-logout redirect URI đã đăng ký tại OP.

### 11.3. Logout tất cả ứng dụng và token

Kết thúc AS session chỉ ngăn các authorization request tiếp theo tái sử dụng browser SSO session. Các ứng dụng có thể vẫn giữ local session cho tới khi tự logout hoặc nhận thông báo logout.

Nếu yêu cầu global sign-out, cần thiết kế thêm:

- RP-Initiated Logout từ ứng dụng khởi tạo tới OP.
- OIDC Back-Channel Logout hoặc Front-Channel Logout nếu OP/RP hỗ trợ.
- Theo dõi sid/sub và session mapping theo OIDC logout contract.
- Revoke refresh token/authorization khi policy yêu cầu.
- Resource Server dùng introspection, denylist hoặc access token TTL ngắn nếu cần phản ánh revocation nhanh.
- Logout mọi thiết bị/browser session theo một workflow có kiểm soát.

Không suy ra access token đã phát sẽ mất hiệu lực chỉ vì browser session tại Authorization Server đã bị xóa. Với JWT access token được xác minh offline, Resource Server có thể tiếp tục chấp nhận token đến khi hết hạn nếu không có cơ chế revocation bổ sung.

## 12. Bảo mật SSO và vận hành

### 12.1. Bảo vệ session

- Dùng HTTPS toàn bộ luồng đăng nhập và callback.
- Cookie session có Secure, HttpOnly, SameSite phù hợp và host-only nếu có thể.
- Giữ session fixation protection.
- Đặt idle timeout và absolute session lifetime theo mức rủi ro.
- Có chính sách re-authentication cho thao tác nhạy cảm.
- Không đặt session cookie vào domain rộng chỉ để tạo SSO giữa subdomain.
- Không đưa session ID vào URL, log, analytics hoặc client-side storage.

### 12.2. Bảo vệ authorization request

- Mỗi client có redirect URI exact-match và registration riêng.
- Dùng Authorization Code Flow; yêu cầu PKCE cho public clients và cân nhắc PKCE cho confidential clients.
- Kiểm tra state, nonce, issuer, audience và callback transaction.
- Không bỏ qua consent hoặc MFA chỉ vì user đã có AS session.
- Không chấp nhận post_logout_redirect_uri chưa đăng ký.
- Kiểm soát prompt, max_age và re-authentication policy theo OIDC.

### 12.3. Session và account lifecycle

- Khi user bị disable, ngăn authorization mới và xử lý session đang tồn tại theo SLA.
- Khi password/MFA credential bị reset do nghi ngờ compromise, cân nhắc terminate các session hiện hành.
- Theo dõi concurrent sessions và thiết bị đã đăng nhập.
- Có quy trình revoke refresh token/authorization khi account bị khóa hoặc user rời tổ chức.
- Đồng bộ session registry giữa các node nếu dùng cluster.
- Audit login, re-authentication, consent, logout và session termination; không log credential hoặc token.

## 13. Ma trận kiểm thử SSO nhiều client

| # | Tình huống | Kết quả mong đợi |
|---|---|---|
| 1 | Client A login lần đầu | AS hiển thị login, xác thực user và tạo AS session |
| 2 | Client A đổi authorization code | A nhận token của registration A |
| 3 | Client B mở trong cùng browser profile | AS nhận session cookie và không yêu cầu nhập lại mật khẩu nếu policy cho phép |
| 4 | Client B dùng client ID riêng | Authorization request được xử lý theo registration B |
| 5 | Client B dùng redirect URI của A | AS từ chối redirect URI |
| 6 | Client B yêu cầu scope riêng | Scope được kiểm tra theo registration B |
| 7 | Client A đã consent, Client B chưa consent | Consent B vẫn được xử lý riêng |
| 8 | Client B yêu cầu scope mới | Hiển thị consent bổ sung hoặc áp dụng policy tương ứng |
| 9 | User mở browser profile khác | Không dùng lại session cookie của profile đầu |
| 10 | User dùng incognito | Không mặc định có AS session của browser thường |
| 11 | AS session hết idle timeout | Authorization request tiếp theo yêu cầu đăng nhập lại |
| 12 | AS session hết absolute lifetime | Re-authentication theo policy |
| 13 | Client A local logout | Session A kết thúc; AS session có thể còn |
| 14 | Mở Client B sau local logout A | B có thể SSO nếu AS session còn |
| 15 | Client A RP-Initiated Logout | OP xử lý end-session request và kết thúc AS session phù hợp |
| 16 | post_logout_redirect_uri không đăng ký | OP từ chối redirect |
| 17 | Client B sau global OP logout | B không được tái sử dụng AS session đã kết thúc |
| 18 | Client B local session còn sau OP logout | Hành vi theo front/back-channel logout policy đã cấu hình |
| 19 | Access token JWT cũ sau AS logout | Vẫn hợp lệ tới expiry nếu không có revocation mechanism |
| 20 | Refresh token bị revoke | Token endpoint từ chối refresh theo policy |
| 21 | prompt=none với AS session hợp lệ | Không hiển thị UI nếu không cần interaction |
| 22 | prompt=none khi chưa login | Trả login_required, không hiện login UI |
| 23 | prompt=none khi cần consent | Trả lỗi tương ứng, không tự hiện consent |
| 24 | prompt=login khi session đang active | Thực hiện re-authentication theo policy |
| 25 | prompt=consent | Yêu cầu consent theo OIDC behavior |
| 26 | max_age đã vượt ngưỡng | Re-authenticate và cung cấp auth_time khi cần |
| 27 | Hai client login đồng thời | Authorization transaction không ghi đè state của nhau |
| 28 | Hai AS instance xử lý cùng browser session | Cùng khôi phục SecurityContext từ shared session |
| 29 | Node chứa session bị dừng | Node khác tiếp tục được nếu session store có failover |
| 30 | SessionRegistry chỉ nằm trong RAM từng node | Test phát hiện logout/session tracking không đồng bộ |
| 31 | Cookie bị đổi Domain/path | Browser behavior được kiểm tra, không rò cookie sang host không cần thiết |
| 32 | SameSite=Lax với top-level GET redirect | Cookie được gửi theo browser behavior dự kiến |
| 33 | response_mode=form_post | Kiểm tra cookie/SameSite và CSRF behavior riêng |
| 34 | User bị disable trong khi AS session còn | Authorization mới bị từ chối theo account policy |
| 35 | Client A cố dùng token của Client B | Resource Server/client policy từ chối sai audience/scope |
| 36 | Logout redirect URL chứa host tùy ý | Không redirect ngoài allowlist |
| 37 | Log bật debug trong authorization flow | Không ghi session ID, authorization code hoặc token |
| 38 | Nhiều ứng dụng cùng issuer nhưng khác client ID | Mỗi ứng dụng nhận token/consent theo registration của nó |

### 13.1. Integration test end-to-end

Một bài test SSO nên thực hiện trong cùng browser context:

1. Mở Client A và hoàn tất login tại Authorization Server.
2. Kiểm tra browser nhận session cookie của AS với thuộc tính Secure/HttpOnly/SameSite đúng.
3. Đổi code và tạo local session tại Client A.
4. Mở Client B trong cùng browser profile.
5. Xác nhận browser gửi cookie tới cùng AS host và AS không yêu cầu nhập lại mật khẩu.
6. Kiểm tra Client B vẫn được xác thực bằng client registration, redirect URI, scope và consent riêng.
7. Đổi code tại token endpoint bằng credential của Client B.
8. Xác minh token A và token B không bị hoán đổi.
9. Logout local A rồi mở B để xác minh SSO behavior.
10. Thực hiện RP-Initiated Logout và xác minh AS session kết thúc.
11. Kiểm tra local session B và access token cũ theo logout/revocation policy đã công bố.
12. Lặp lại test khi request được xử lý bởi các AS nodes khác nhau.

## 14. Troubleshooting và checklist production

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Client B luôn hiện login dù Client A đã login | AS session không được persist hoặc browser không gửi cookie | Kiểm tra SecurityContextRepository, cookie host/path/SameSite |
| Login A thành công nhưng request B tới node khác bị hỏi login | Session chỉ lưu local trong node | Dùng shared session store hoặc sticky session có failover |
| Client B nhận token sai client | Dùng chung client registration hoặc token/authorized client bị chia sẻ sai | Tách RegisteredClient và kiểm tra audience |
| Client B không có session local dù AS SSO thành công | Callback hoặc local authentication persistence lỗi | Kiểm tra OAuth2 Login callback và session của B |
| Client A logout nhưng B vẫn đăng nhập | Chỉ logout local client A | Dùng RP-Initiated Logout nếu muốn kết thúc AS session |
| AS logout nhưng access token vẫn gọi API được | JWT access token còn hiệu lực và API validate offline | Dùng TTL ngắn hoặc revocation/introspection policy |
| prompt=none lại hiện login page | Provider không xử lý silent request đúng contract | Trả lỗi OIDC thay vì tương tác |
| prompt=login vẫn dùng session cũ | Chưa enforce re-authentication | Thêm interaction policy và kiểm thử |
| Post-logout redirect bị từ chối | URI chưa nằm trong RegisteredClient | Đăng ký postLogoutRedirectUri chính xác |
| Logout không tìm thấy session ở node khác | SessionRegistry không chia sẻ | Cấu hình distributed session tracking |
| Cookie không được gửi trong form_post | SameSite policy không phù hợp cross-site POST | Kiểm tra response mode, cookie và CSRF |
| Incognito yêu cầu login lại | Cookie jar độc lập | Đây là behavior bình thường |

### 14.1. Checklist production

- [ ] Tất cả client dùng đúng issuer/Authorization Server chung.
- [ ] Mỗi ứng dụng có RegisteredClient, client ID, redirect URI và credential riêng.
- [ ] Web confidential clients giữ secret phía server; public clients dùng PKCE và không nhúng secret.
- [ ] Authorization Server dùng session-based SecurityContext cho browser login.
- [ ] Không đặt browser authorization flow thành STATELESS.
- [ ] Session fixation protection được bật.
- [ ] Session cookie có Secure, HttpOnly, SameSite và host-only phù hợp.
- [ ] Không cần mở rộng cookie Domain để chia sẻ SSO giữa các client.
- [ ] Session store được chia sẻ giữa AS nodes hoặc có failover rõ ràng.
- [ ] SessionRegistry/concurrent session tracking được đồng bộ nếu cần.
- [ ] Consent được xét theo từng client và principal.
- [ ] prompt, max_age, MFA và re-authentication có policy rõ.
- [ ] RP-Initiated Logout được bật nếu cần SSO logout.
- [ ] Post-logout redirect URI được đăng ký và validate.
- [ ] Back-channel/front-channel logout được thiết kế nếu cần terminate local session của các RP khác.
- [ ] Token revocation/expiry được tách khỏi browser session logout.
- [ ] Account disablement/compromise có workflow terminate session và revoke authorization.
- [ ] Có integration tests qua nhiều client, browser profile, AS node và logout path.
- [ ] Audit không ghi session ID, authorization code, access token, refresh token hoặc ID Token.

**Câu hỏi tự đánh giá**

1. SSO trong mô hình nhiều client dùng chung Authorization Server dựa trên trạng thái nào?
2. Vì sao mỗi client vẫn cần một RegisteredClient riêng dù dùng chung issuer?
3. Khác nhau giữa AS browser session và application session của từng client là gì?
4. Vì sao access token của Client A không được dùng thay cho token của Client B?
5. Spring Security persist SecurityContext vào đâu theo mặc định?
6. Vì sao SessionCreationPolicy.STATELESS không phù hợp với browser-based SSO?
7. Cookie của Authorization Server có cần chia sẻ cho các subdomain client không?
8. Vì sao cookie host-only có thể vẫn hỗ trợ SSO giữa nhiều client?
9. Khi chạy nhiều AS nodes, cần làm gì để khôi phục cùng session?
10. Consent của Client A có tự động áp dụng cho Client B không?
11. prompt=none phải xử lý thế nào khi user chưa có session?
12. prompt=login và max_age tác động tới session hiện tại ra sao?
13. Local logout tại Client A có tự kết thúc AS session không?
14. RP-Initiated Logout khác local logout như thế nào?
15. Vì sao kết thúc AS session không tự động revoke JWT access token đã phát?
16. Khi nào cần Back-Channel Logout hoặc Front-Channel Logout?
17. Làm thế nào kiểm thử SSO giữa hai client và nhiều AS instances?

## Tài liệu tham khảo

- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): OIDC endpoints, RP-Initiated Logout endpoint và SessionRegistry.
- [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): RegisteredClient, authorization, consent và token model.
- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): SecurityContextRepository, HTTP session, session fixation, session policy và logout.
- [Spring Security — Persisting Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html): cách SecurityContext được lưu và khôi phục qua request.
- [Spring Security — OIDC Logout](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html): local logout, RP-Initiated Logout và Back-Channel Logout ở OAuth2/OIDC client.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): Authorization Request, prompt, max_age, auth_time và authentication semantics.
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html): end_session_endpoint, id_token_hint, post_logout_redirect_uri và state.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): session, redirect, token và client security considerations.
