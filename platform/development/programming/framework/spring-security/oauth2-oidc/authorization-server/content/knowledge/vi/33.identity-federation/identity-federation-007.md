# Phân biệt token của IdP đầu nguồn với token do máy chủ nội bộ phát hành

## Mục tiêu bài học

Trong chương **Liên kết danh tính** của module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, bài học này giải thích cách một hệ thống sử dụng **Spring Security**, **Spring Authorization Server** và **Spring Boot** để liên kết danh tính từ một OpenID Provider (IdP) bên ngoài, sau đó phát hành token riêng cho các ứng dụng và API nội bộ.

Trong mô hình federation, IdP đầu nguồn xác thực người dùng. Máy chủ nội bộ tin cậy kết quả xác thực đó theo một cấu hình issuer đã định trước, ánh xạ danh tính bên ngoài sang tài khoản nội bộ và áp dụng chính sách quyền của tổ chức. Khi ứng dụng nội bộ cần truy cập API, nó sử dụng access token do Authorization Server nội bộ phát hành.

Hai nhóm token này có issuer, audience, chủ thể, mục đích và vòng đời khác nhau. Việc một token là JWT hợp lệ hoặc được ký bởi một IdP đáng tin cậy không có nghĩa token đó có thể dùng ở mọi API.

Sau bài học, bạn có thể:

1. Phân biệt upstream ID Token, upstream access token, internal ID Token và internal access token.
2. Giải thích vai trò của IdP, OAuth2 Client, Authorization Server, Relying Party và Resource Server.
3. Cấu hình Spring Authorization Server sử dụng OIDC social login thông qua Spring Security OAuth2 Client.
4. Ánh xạ danh tính bên ngoài bằng cặp issuer và subject sang một định danh người dùng nội bộ ổn định.
5. Phân biệt OAuth2AuthorizedClientService với OAuth2AuthorizationService.
6. Phát hành internal ID Token và access token với issuer, subject, audience, scope và claims theo policy nội bộ.
7. Sử dụng upstream access token để gọi đúng API của IdP khi có nhu cầu.
8. Hiểu giới hạn của Token Exchange mặc định trong Spring Authorization Server 1.5.8 khi đầu vào là token từ IdP khác.
9. Thiết kế custom token exchange cho trusted external issuer khi thật sự cần.
10. Kiểm thử issuer/audience validation, account linking, token exchange, logout và deprovisioning.

> **Tình huống xuyên suốt:** nhân viên đăng nhập vào hệ thống công ty qua IdP doanh nghiệp. Authorization Server nội bộ xác thực kết quả OIDC, ánh xạ nhân viên sang tài khoản nội bộ, sau đó cấp token cho các ứng dụng như employee-portal và mobile-app. Các API orders, payroll và profile chỉ tin token do issuer nội bộ phát hành.

## 1. Kiến trúc liên kết danh tính

### 1.1. Các vai trò trong mô hình

| Thành phần | Vai trò | Token liên quan |
|---|---|---|
| IdP đầu nguồn / upstream OpenID Provider | Xác thực End-User và cung cấp danh tính bên ngoài. | Upstream ID Token; upstream access token. |
| Internal Authorization Server | Tin cậy IdP theo cấu hình, ánh xạ người dùng, áp dụng policy và phát hành token nội bộ. | Internal ID Token; internal access token; refresh token nếu được phép. |
| Internal OAuth2/OIDC Client (RP) | Đăng nhập người dùng qua internal Authorization Server và xác minh internal ID Token. | Nhận internal ID Token và access token. |
| Internal Resource Server | Bảo vệ API nội bộ bằng access token. | Chỉ chấp nhận token theo trust policy của API. |
| Upstream Resource Server | Cung cấp API của IdP hoặc hệ thống bên ngoài. | Chấp nhận upstream access token theo audience/scope của nó. |

Spring Security cung cấp OAuth2 Client và OAuth2 Login để ứng dụng đóng vai RP đối với IdP đầu nguồn. Spring Authorization Server đóng vai trò OpenID Provider/Authorization Server cho các ứng dụng nội bộ. Hai vai trò có thể chạy trong cùng một ứng dụng, nhưng vẫn là hai protocol relationships khác nhau.

### 1.2. Hai trust boundary

Trong mô hình này có ít nhất hai trust boundary:

- **External trust boundary:** internal Authorization Server tin cậy issuer bên ngoài để xác thực danh tính. Việc tin cậy phải gắn với issuer cụ thể, metadata/JWKS được xác định trước, client registration và các quy tắc xác minh OIDC.
- **Internal trust boundary:** internal Resource Server tin cậy issuer nội bộ để xác định ai được gọi API nào. Token nội bộ được phát hành theo danh tính đã ánh xạ và quyền nội bộ.

Không mở rộng trust chỉ vì hai token có cùng định dạng JWT. Mỗi Resource Server cần xác định issuer, audience, token type và policy được phép chấp nhận.

### 1.3. Luồng đăng nhập liên kết

~~~mermaid
sequenceDiagram
    autonumber
    participant U as Browser / End-User
    participant RP as Internal OIDC Client
    participant IAS as Internal Authorization Server
    participant IDP as Upstream IdP
    participant DB as Local Identity Store
    participant API as Internal Resource Server

    U->>RP: Open internal application
    RP->>IAS: Authorization Request
    IAS->>IDP: Redirect to upstream OIDC login
    IDP->>U: Authenticate user
    U->>IDP: Credentials / MFA
    IDP-->>IAS: Authorization Code
    IAS->>IDP: Token Request
    IDP-->>IAS: Upstream ID Token + Access Token
    IAS->>IAS: Validate upstream OIDC response
    IAS->>DB: Resolve (issuer, subject)
    DB-->>IAS: Local user + local authorities
    IAS-->>RP: Internal Authorization Code
    RP->>IAS: Exchange code at internal Token Endpoint
    IAS-->>RP: Internal ID Token + Internal Access Token
    RP->>API: Authorization: Bearer internal_access_token
    API->>API: Validate internal issuer, audience and scopes
    API-->>RP: Protected resource
~~~

Điểm quan trọng là ứng dụng nội bộ nhận token từ internal Authorization Server. Upstream IdP thực hiện bước xác thực đầu nguồn; internal Authorization Server thực hiện bước phát hành token theo policy nội bộ.

### 1.4. Hai luồng token có thể cùng tồn tại

Một ứng dụng có thể vừa cần:

- Internal access token để gọi API nội bộ.
- Upstream access token để gọi API của IdP hoặc một dịch vụ bên ngoài.

Đây là hai mục đích khác nhau. Spring Security lưu thông tin OAuth2 client đã được authorize trong OAuth2AuthorizedClient. Spring Authorization Server lưu authorization và token do chính nó phát hành trong OAuth2Authorization. Không trộn hai kho này hoặc dùng token của một luồng thay cho luồng còn lại.

## 2. Phân biệt bốn loại token

### 2.1. Bảng so sánh

| Token | Issuer (iss) | Audience (aud) | Mục đích | Nơi sử dụng |
|---|---|---|---|---|
| Upstream ID Token | IdP bên ngoài | Client ID của internal Authorization Server đã đăng ký tại IdP | Bằng chứng xác thực người dùng cho OAuth2/OIDC Client. | Internal Authorization Server trong quá trình OIDC login. |
| Upstream access token | IdP bên ngoài | API/resource được IdP cấp token | Truy cập tài nguyên thuộc upstream provider. | Upstream Resource Server. |
| Internal ID Token | Internal Authorization Server | Client ID của internal RP | Cho internal RP xác minh danh tính người dùng. | Internal OIDC Client. |
| Internal access token | Internal Authorization Server | API/resource nội bộ | Cho phép truy cập API theo scope và policy nội bộ. | Internal Resource Server. |

Một JWT có thể mang nhiều claim giống nhau nhưng không thể thay thế token khác nếu issuer, audience hoặc mục đích không khớp.

### 2.2. Upstream ID Token

OIDC ID Token là security token mô tả kết quả xác thực End-User tại issuer. Các claim quan trọng gồm:

- **iss:** issuer đã xác thực người dùng.
- **sub:** subject identifier có ý nghĩa trong phạm vi issuer đó.
- **aud:** client hoặc các audience được phép nhận ID Token.
- **exp**, **iat:** thời hạn và thời điểm phát hành.
- **nonce:** ràng buộc Authentication Request với ID Token khi request có nonce.
- **auth_time**, **acr**, **amr:** thông tin thời điểm và ngữ cảnh xác thực nếu được yêu cầu hoặc cung cấp theo policy.

Internal Authorization Server là OIDC Client của upstream IdP. Vì vậy, upstream ID Token có audience là client registration của internal Authorization Server. Nó không được phát hành để các API orders hoặc payroll nội bộ sử dụng.

Bài học này dùng upstream **OIDC Provider** làm ví dụ. Một số social provider chỉ hỗ trợ OAuth2 và trả OAuth2User/UserInfo mà không phát hành ID Token. Khi tích hợp provider như vậy, ứng dụng phải tuân theo contract xác minh danh tính của provider; không gọi response đó là OIDC ID Token và không áp dụng các giả định claim OIDC khi provider không triển khai OIDC.

### 2.3. Upstream access token

Upstream access token cấp quyền truy cập một resource server của IdP hoặc một dịch vụ bên ngoài.

Ví dụ:

~~~http
GET /userinfo HTTP/1.1
Host: idp.example.com
Authorization: Bearer UPSTREAM_ACCESS_TOKEN
~~~

Token này chỉ nên được gửi tới resource server mà issuer đã cấp quyền. Nếu token có audience là API của IdP, internal Resource Server không được chấp nhận nó chỉ vì chữ ký hợp lệ.

Trong Spring Security, OAuth2AuthorizedClient gắn access token và optional refresh token với ClientRegistration và principal người dùng. OAuth2AuthorizedClientManager, OAuth2AuthorizedClientRepository và OAuth2AuthorizedClientService quản lý vòng đời authorized client.

### 2.4. Internal ID Token

Internal ID Token được phát hành trong OIDC flow giữa internal Authorization Server và internal RP.

- **iss** là issuer nội bộ.
- **aud** chứa client ID của RP nội bộ.
- **sub** là subject nội bộ ổn định do tổ chức quản lý.
- Claims phản ánh dữ liệu được phép tiết lộ cho RP nội bộ.

Internal ID Token giúp RP biết người dùng đã được internal OP xác thực. Nó không phải credential để gọi API. Không gửi ID Token trong Authorization header của API thay cho access token.

### 2.5. Internal access token

Internal access token được phát hành để gọi API nội bộ. Nó cần:

- Issuer nội bộ được Resource Server tin cậy.
- Audience/resource phù hợp với API đích.
- Scope/authority được cấp theo policy nội bộ.
- Thời hạn hợp lý và chữ ký/opaque-token validation phù hợp.
- Token lifecycle có introspection/revocation hoặc cơ chế kiểm tra tương ứng.

Ví dụ:

~~~http
GET /api/orders HTTP/1.1
Host: orders.internal.example
Authorization: Bearer INTERNAL_ACCESS_TOKEN
~~~

Internal Resource Server kiểm tra token theo cấu hình issuer và audience của API. Token upstream không tự trở thành internal access token.

## 3. Cấu hình Spring Authorization Server đăng nhập qua upstream IdP

### 3.1. Thêm OAuth2 Client dependency

Spring Authorization Server dùng Spring Security OAuth2 Client để thực hiện upstream login. Với Spring Boot, thêm starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

Internal Authorization Server cần được đăng ký như một OAuth2/OIDC client tại upstream IdP. Tại IdP, đăng ký redirect URI của Spring Security OAuth2 Login, ví dụ:

~~~text
https://auth.internal.example/login/oauth2/code/corporate-idp
~~~

Đây là callback của **internal Authorization Server với upstream IdP**. Nó khác redirect URI mà internal RP đăng ký tại internal Authorization Server.

### 3.2. Cấu hình ClientRegistration

Ví dụ application.yml:

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
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          corporate:
            issuer-uri: https://login.corporate.example
~~~

Spring Security dùng issuer URI để discovery OIDC Provider Configuration. Với provider không hỗ trợ discovery, cần cấu hình các endpoint và JWK Set URI theo tài liệu của provider.

Client secret phải lấy từ secret manager hoặc environment injection. Không commit secret thật vào source control.

Scope **openid** yêu cầu OIDC login. Nếu không có scope này, Spring Security có thể xử lý response theo OAuth2 Login với OAuth2User thay vì OidcUser.

### 3.3. Tách Authorization Server filter chain và login filter chain

Spring Authorization Server xử lý protocol endpoints trong một SecurityFilterChain riêng. OAuth2 Login xử lý quá trình xác thực người dùng trong filter chain dành cho ứng dụng.

Ví dụ cấu hình khung:

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

@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, authorizationServer ->
            authorizationServer.oidc(Customizer.withDefaults()))
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
@Order(2)
SecurityFilterChain defaultSecurityFilterChain(
        HttpSecurity http) throws Exception {

    http.authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated())
        .oauth2Login(Customizer.withDefaults());

    return http.build();
}
~~~

Chain đầu tiên bảo vệ các Authorization Server endpoints và chuyển trình duyệt chưa đăng nhập tới upstream login entry point. Chain thứ hai cấu hình OAuth2 Login và xử lý callback từ IdP.

Trong ứng dụng thực tế, chain mặc định có thể cần thêm custom OidcUserService, authentication success handler, session policy, CSRF rules và login page phù hợp.

### 3.4. Internal Authorization Server vẫn là issuer riêng

Sau khi upstream login thành công, Spring Security tạo Authentication trong SecurityContext. Spring Authorization Server dùng principal đó để xử lý Authorization Request và phát hành code/token nội bộ.

Không thay issuer nội bộ bằng issuer của IdP đầu nguồn. Không để request host header hoặc claim từ upstream quyết định issuer của internal Authorization Server.

Cấu hình issuer nội bộ cần ổn định, ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.internal.example")
            .build();
}
~~~

Internal RP cũng phải được đăng ký riêng tại internal Authorization Server. Ví dụ tối thiểu cho một confidential web client:

~~~java
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;

RegisteredClient employeePortal = RegisteredClient
        .withId("employee-portal-registration")
        .clientId("employee-portal")
        .clientSecret(passwordEncoder.encode(employeePortalSecret))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("https://portal.internal.example/login/oauth2/code/internal")
        .scope(OidcScopes.OPENID)
        .scope(OidcScopes.PROFILE)
        .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .build())
        .build();
~~~

Client ID và secret ở đây thuộc quan hệ giữa employee-portal và **internal** Authorization Server. Chúng độc lập với client ID/secret mà internal Authorization Server dùng để đăng nhập tại upstream IdP.

## 4. Ánh xạ upstream identity sang local user

### 4.1. Khóa danh tính bằng issuer và subject

OIDC xác định subject trong phạm vi issuer. Vì vậy, khóa liên kết danh tính cần ít nhất hai thành phần:

~~~text
(federated_issuer, federated_subject)
~~~

Ví dụ:

| Issuer | Subject | Local subject |
|---|---|---|
| https://login.corporate.example | 00u123abc | usr_8f31... |
| https://login.partner.example | 00u123abc | usr_9a42... |

Hai IdP có thể cùng phát một chuỗi sub nhưng đó là hai danh tính khác nhau. Local subject là định danh ổn định trong miền nội bộ.

Không dùng email làm khóa federation duy nhất. Email có thể đổi, được tái sử dụng, có thể không được xác minh hoặc có quy tắc uniqueness khác nhau giữa các IdP.

### 4.2. Account linking và JIT provisioning

Khi người dùng đăng nhập lần đầu, hệ thống có thể dùng Just-In-Time (JIT) provisioning để tạo local user. Khi một local user liên kết thêm IdP khác, phải có quy trình xác minh và audit.

Các chính sách cần quyết định:

- Chỉ cho phép issuer trong allowlist.
- Tài khoản local đã bị khóa hoặc deprovisioned phải bị từ chối dù upstream login thành công.
- Liên kết tài khoản hiện có cần chứng minh quyền kiểm soát cả hai danh tính.
- Không tự động gộp tài khoản chỉ vì email giống nhau.
- Ghi audit cho create/link/unlink/update identity.
- Có quy trình xử lý đổi issuer, đổi subject và thu hồi quyền ở upstream.
- Lưu mapping với unique constraint trên cặp issuer/subject.

Một cấu trúc dữ liệu minh họa:

~~~sql
CREATE TABLE federated_identity (
    id varchar(100) PRIMARY KEY,
    local_user_id varchar(100) NOT NULL,
    issuer varchar(500) NOT NULL,
    subject varchar(500) NOT NULL,
    linked_at timestamp NOT NULL,
    UNIQUE (issuer, subject)
);
~~~

Đây chỉ là bảng mapping minh họa. Schema thực tế cần thêm foreign key, index, audit columns, collation và kiểu timestamp phù hợp database vendor.

Thao tác JIT provisioning phải idempotent và có transaction. Hai callback login đầu tiên của cùng một cặp issuer/subject có thể chạy đồng thời; unique constraint là hàng rào cuối cùng. Nếu insert gặp duplicate-key, service có thể đọc lại mapping đã được request kia tạo và tiếp tục sau khi xác minh local account vẫn active. Không tạo local user thứ hai hoặc tự động liên kết một identity khác chỉ để né conflict.

### 4.3. Không tin authorities hoặc groups từ IdP một cách trực tiếp

IdP có thể trả groups, roles hoặc custom claims. Các giá trị này chỉ là dữ liệu đầu vào để mapping, không tự trở thành quyền nội bộ.

Ví dụ, upstream group **finance-admin** không nên tự động cấp quyền quản trị tất cả API nội bộ. Local policy cần xác định group nào được phép ánh xạ sang role nào, trong tenant nào và trong phạm vi resource nào.

Tốt nhất, local user directory trả về local authorities đã được kiểm tra. Không sao chép toàn bộ authorities của upstream Authentication.

## 5. Tạo local OidcUser với subject nội bộ

### 5.1. Vì sao cần local principal?

Spring Authorization Server dùng Authentication của người dùng đã đăng nhập làm principal khi xử lý Authorization Request. Định danh principal vì vậy có ảnh hưởng tới subject của internal authorization và ID Token.

Nếu để nguyên principal name mặc định của upstream OidcUser, internal subject có thể vô tình phụ thuộc vào upstream sub. Điều đó làm nội bộ bị phụ thuộc vào cách IdP quản lý subject và gây khó khi một người liên kết nhiều IdP.

Tạo một wrapper OidcUser có getName() trả về local subject. Các claims và ID Token của upstream vẫn có thể được giữ để phục vụ mapping/audit, nhưng không được copy nguyên trạng sang token nội bộ.

### 5.2. LocalFederatedOidcUser

Ví dụ class wrapper:

~~~java
import java.util.Collection;
import java.util.Map;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUserInfo;

public final class LocalFederatedOidcUser implements OidcUser {

    private final OidcUser upstreamUser;
    private final String localSubject;
    private final Collection<? extends GrantedAuthority> localAuthorities;

    public LocalFederatedOidcUser(
            OidcUser upstreamUser,
            String localSubject,
            Collection<? extends GrantedAuthority> localAuthorities) {
        this.upstreamUser = upstreamUser;
        this.localSubject = localSubject;
        this.localAuthorities = localAuthorities;
    }

    @Override
    public String getName() {
        return this.localSubject;
    }

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        return this.localAuthorities;
    }

    @Override
    public Map<String, Object> getAttributes() {
        return this.upstreamUser.getAttributes();
    }

    @Override
    public Map<String, Object> getClaims() {
        return this.upstreamUser.getClaims();
    }

    @Override
    public OidcIdToken getIdToken() {
        return this.upstreamUser.getIdToken();
    }

    @Override
    public OidcUserInfo getUserInfo() {
        return this.upstreamUser.getUserInfo();
    }
}
~~~

Local authorities được truyền từ local user directory. Không dùng authorities của upstreamUser trực tiếp nếu chưa có mapping policy.

Việc giữ upstream ID Token bên trong principal không làm nó trở thành internal ID Token. Đây vẫn là token do upstream issuer phát hành, với audience và semantics của upstream client registration.

Trong wrapper này, `getName()` là local subject để Spring Security và internal Authorization Server dùng làm tên principal. `getIdToken()`, `getClaims()` và `getSubject()` vẫn phản ánh upstream OIDC identity vì wrapper đang delegate các dữ liệu đó. Không đọc `getSubject()` để lấy local subject; hãy dùng `getName()` hoặc một thuộc tính local identity rõ ràng. Internal ID Token phải được customizer đặt `sub` từ local directory như phần sau.

### 5.3. Custom OidcUserService

Spring Security cho phép thay OidcUserService để xử lý user sau khi OIDC response đã được xác minh.

Ví dụ contract của local identity directory:

~~~java
import java.util.Collection;
import java.util.Map;

import org.springframework.security.core.GrantedAuthority;

public interface FederatedIdentityDirectory {

    LocalFederatedAccount resolveOrProvision(
            String issuer,
            String subject,
            Map<String, Object> upstreamClaims);
}

public record LocalFederatedAccount(
        String subject,
        String tenantId,
        Collection<? extends GrantedAuthority> authorities) {
}
~~~

Ví dụ service:

~~~java
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.util.StringUtils;

@Bean
OAuth2UserService<OidcUserRequest, OidcUser> federatedOidcUserService(
        FederatedIdentityDirectory identityDirectory) {

    OidcUserService delegate = new OidcUserService();

    return userRequest -> {
        OidcUser upstreamUser = delegate.loadUser(userRequest);

        String issuer = userRequest.getClientRegistration()
                .getProviderDetails().getIssuerUri();

        if (!StringUtils.hasText(issuer)
                || !StringUtils.hasText(upstreamUser.getSubject())) {
            throw new IllegalStateException(
                    "The upstream OIDC identity is incomplete");
        }

        LocalFederatedAccount localAccount =
                identityDirectory.resolveOrProvision(
                        issuer,
                        upstreamUser.getSubject(),
                        upstreamUser.getClaims());

        if (localAccount == null
                || !StringUtils.hasText(localAccount.subject())
                || !StringUtils.hasText(localAccount.tenantId())
                || localAccount.authorities() == null) {
            throw new IllegalStateException(
                    "The local federated account is incomplete");
        }

        return new LocalFederatedOidcUser(
                upstreamUser,
                localAccount.subject(),
                localAccount.authorities());
    };
}
~~~

Đây là khung tích hợp. Trong production, directory cần phân biệt lỗi IdP, user không tồn tại, user bị khóa, tenant không hợp lệ và lỗi hạ tầng. Không tự động provision tài khoản chỉ vì upstream trả HTTP 200; cần kiểm tra issuer allowlist, claim policy và điều kiện được phép đăng nhập.

### 5.4. Gắn custom OidcUserService vào login chain

~~~java
.oauth2Login(login -> login
    .userInfoEndpoint(userInfo -> userInfo
        .oidcUserService(federatedOidcUserService)
    )
)
~~~

Đặt cấu hình này trong SecurityFilterChain xử lý OAuth2 Login. Kiểm thử rằng Authentication sau login có principal là LocalFederatedOidcUser và getName() trả local subject.

## 6. Phát hành internal ID Token và access token

### 6.1. Internal ID Token được tạo bởi internal OP

Khi internal RP yêu cầu OIDC bằng scope openid và hoàn tất Authorization Code Flow, Spring Authorization Server phát hành internal ID Token.

Internal ID Token phải có:
- Issuer nội bộ.
- Audience là internal client ID.
- Subject là local subject.
- Thời hạn và chữ ký do internal Authorization Server kiểm soát.
- Nonce của internal Authentication Request nếu request đó có nonce.
- Các claims bổ sung đã được local policy cho phép.

Không sao chép các claim protocol của upstream ID Token sang internal ID Token. Các claim iss, sub, aud, exp, iat, nonce và azp của internal token phải mô tả giao dịch giữa internal OP và internal RP. Các giá trị tương tự trong upstream ID Token thuộc giao dịch khác.

### 6.2. Thêm local claims bằng OAuth2TokenCustomizer

SAS cung cấp OAuth2TokenCustomizer<JwtEncodingContext> để tùy chỉnh JWT. Ví dụ dưới đây lấy dữ liệu từ local user directory theo principal name đã được ánh xạ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.oidc.endpoint.OidcParameterNames;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Bean
OAuth2TokenCustomizer<JwtEncodingContext> internalTokenCustomizer(
        LocalUserDirectory localUserDirectory,
        ResourceAudiencePolicy resourceAudiencePolicy) {

    return context -> {
        boolean idToken = OidcParameterNames.ID_TOKEN.equals(
                context.getTokenType().getValue());
        boolean accessToken = OAuth2TokenType.ACCESS_TOKEN.equals(
                context.getTokenType());

        if (!idToken && !accessToken) {
            return;
        }

        LocalUser user = localUserDirectory
                .findActive(context.getPrincipal().getName())
                .orElse(null);

        // client_credentials and other workload principals may not be local users.
        if (user == null) {
            if (idToken) {
                throw new IllegalStateException(
                        "An internal OIDC ID Token requires an active local user");
            }
            return;
        }

        if (idToken) {
            context.getClaims().subject(user.subject());
            context.getClaims().claim("tenant_id", user.tenantId());
            context.getClaims().claim("display_name", user.displayName());
        }

        if (accessToken) {
            context.getClaims().claim("tenant_id", user.tenantId());
            context.getClaims().audience(
                    resourceAudiencePolicy.audiencesFor(
                            context.getRegisteredClient(),
                            context.getAuthorizedScopes()));
        }
    };
}
~~~

Ví dụ chỉ thêm claims được chọn từ local directory. Không đưa email, groups, roles hoặc profile của upstream vào mọi token theo mặc định. Mỗi client và resource server có nhu cầu khác nhau; nên phát tối thiểu claims cần thiết.

Trong ví dụ, ResourceAudiencePolicy là policy của ứng dụng để trả về audience đã được cho phép cho client và scope hiện tại. Không dùng trực tiếp một audience tùy ý do request gửi lên. Đoạn customizer áp dụng cho JWT; nếu dùng opaque access token, cần cấu hình thông tin tương ứng trong token/introspection path. Với client_credentials, principal thường là client chứ không phải local user nên ví dụ bỏ qua local user claims cho grant đó.

Nếu cần thêm role vào access token, chỉ thêm local authorities sau khi policy đã kiểm tra tenant, resource, client và consent. Không dùng upstream groups trực tiếp làm quyền API.

### 6.3. Audience và scope của internal access token

Audience phải phản ánh resource server đích. Ví dụ:

| API | Audience | Scope minh họa |
|---|---|---|
| Orders API | https://orders.internal.example | orders.read, orders.write |
| Payroll API | https://payroll.internal.example | payroll.read |
| Profile API | https://profile.internal.example | profile.read, profile.update |

Không phát một token có audience quá rộng chỉ để client gọi được nhiều API. Nếu client cần nhiều resource, hãy đánh giá resource indicators, token exchange hoặc các token có audience riêng.

Internal Resource Server phải kiểm tra issuer nội bộ và audience của chính API. Nếu dùng JWT, cấu hình JwtDecoder/issuer validation và audience validator phù hợp. Nếu dùng opaque token, introspection phải trỏ tới internal Authorization Server và client resource server phải được xác thực.

Ví dụ cho Orders API dùng JWT:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Bean
NimbusJwtDecoder ordersJwtDecoder() {
    String issuer = "https://auth.internal.example";
    String audience = "https://orders.internal.example";

    NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(issuer).build();

    OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
        if (jwt.getAudience().contains(audience)) {
            return OAuth2TokenValidatorResult.success();
        }
        return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                        "invalid_token",
                        "The token is not intended for Orders API",
                        null));
    };

    decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                    JwtValidators.createDefaultWithIssuer(issuer),
                    audienceValidator));
    return decoder;
}
~~~

Ví dụ này cố định issuer và audience theo API. Nếu API phục vụ nhiều issuer, dùng resolver có allowlist và validator riêng cho từng issuer; không tạo decoder từ một iss tùy ý trong token. Sau khi xác minh token, API tiếp tục kiểm tra scope/authority như `SCOPE_orders.read`.

### 6.4. Không nhầm ID Token và access token

| Hành động | Token phù hợp |
|---|---|
| Internal RP xác minh người dùng đã đăng nhập | Internal ID Token hoặc session được tạo sau OIDC login. |
| Internal RP gọi Orders API | Internal access token có audience và scope orders phù hợp. |
| Internal Authorization Server gọi upstream UserInfo/API | Upstream access token, nếu scope/audience cho phép. |
| Internal Resource Server xác thực request API | Internal access token theo issuer/audience policy. |
| Internal RP gọi API với ID Token | Sai mục đích; không dùng ID Token làm Bearer access token. |

## 7. Hai kho token có trách nhiệm khác nhau

### 7.1. OAuth2AuthorizedClientService

Spring Security OAuth2 Client sử dụng OAuth2AuthorizedClient để gắn token với ClientRegistration và principal.

Dữ liệu này đại diện cho quyền của internal Authorization Server (hoặc ứng dụng broker) khi truy cập upstream provider:
- Client registration ID.
- Principal name.
- Upstream access token.
- Upstream refresh token nếu provider cấp.
- Thời hạn và metadata liên quan.

OAuth2AuthorizedClientRepository lưu authorized client qua web requests; OAuth2AuthorizedClientService quản lý ở cấp ứng dụng. Có thể dùng JdbcOAuth2AuthorizedClientService để lưu bền vững.

### 7.2. OAuth2AuthorizationService

Spring Authorization Server sử dụng OAuth2AuthorizationService để lưu authorization được phát hành bởi internal Authorization Server:

- Registered client nội bộ.
- Principal nội bộ.
- Grant type.
- Authorized scopes.
- Internal authorization code.
- Internal access token.
- Internal refresh token.
- Internal OIDC ID Token và metadata.

### 7.3. Bảng phân biệt

| Service | Ai phát hành token được lưu? | Mục đích |
|---|---|---|
| OAuth2AuthorizedClientService | Upstream IdP | Lưu token mà ứng dụng dùng khi gọi API của upstream provider. |
| OAuth2AuthorizationService | Internal Authorization Server | Lưu token/authorization cấp cho internal OAuth2/OIDC clients. |

Hai service có thể cùng dùng một database nhưng phải tách bảng, quyền truy cập và chính sách retention theo vai trò.

Không lưu upstream access token vào OAuth2AuthorizationService như thể token đó do internal AS phát hành. Cũng không dùng OAuth2AuthorizedClientService làm nơi lưu token nội bộ cho RP.

## 8. Khi nào cần dùng upstream access token?

### 8.1. Gọi upstream API trực tiếp

Nếu internal application cần đọc profile, nhóm hoặc dữ liệu từ upstream API, hãy dùng OAuth2AuthorizedClientManager để lấy authorized client và gửi đúng access token tới upstream resource server.

Ví dụ cấu hình RestClient:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.client.OAuth2ClientHttpRequestInterceptor;
import org.springframework.web.client.RestClient;

@Bean
RestClient upstreamRestClient(
        OAuth2AuthorizedClientManager authorizedClientManager) {

    OAuth2ClientHttpRequestInterceptor interceptor =
            new OAuth2ClientHttpRequestInterceptor(
                    authorizedClientManager);

    return RestClient.builder()
            .requestInterceptor(interceptor)
            .build();
}
~~~

Khi gọi, chọn đúng registration ID và principal để manager dùng đúng authorized client. Không bật chế độ tự động gắn upstream token vào mọi outbound request; điều đó có thể làm token bị gửi nhầm host.

Có thể lấy authorized client tường minh trước khi gọi API:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;

OAuth2AuthorizeRequest authorizeRequest =
        OAuth2AuthorizeRequest.withClientRegistrationId("corporate-idp")
                .principal(authentication)
                .build();

OAuth2AuthorizedClient authorizedClient =
        authorizedClientManager.authorize(authorizeRequest);

if (authorizedClient == null) {
    throw new IllegalStateException(
            "The upstream client could not be authorized");
}

String upstreamAccessToken =
        authorizedClient.getAccessToken().getTokenValue();

String profile = upstreamRestClient.get()
        .uri("https://api.corporate.example/v1/profile")
        .headers(headers ->
                headers.setBearerAuth(upstreamAccessToken))
        .retrieve()
        .body(String.class);
~~~

Đoạn code giả định `authentication` là principal hiện tại và `upstreamRestClient` chỉ được dùng cho host upstream đã cấu hình. `OAuth2AuthorizedClientManager` có thể dùng refresh token để lấy access token mới khi provider hỗ trợ. Không nhận URL đích tùy ý từ người dùng rồi gắn bearer token vào request; hãy giới hạn host/path đích bằng cấu hình ứng dụng.

Ví dụ lấy token tường minh ở trên không cần interceptor tự gắn token. Nếu chọn `OAuth2ClientHttpRequestInterceptor` thay thế, hãy truyền registration ID và principal qua request attributes hoặc resolver được cấu hình rõ ràng; không vừa để interceptor gắn token vừa tự đặt một Bearer header khác trong cùng request.

### 8.2. Khi nào không cần upstream access token?

Nếu mục tiêu chỉ là xác thực người dùng rồi cho phép họ dùng API nội bộ, internal Authorization Server có thể hoàn tất OIDC login và phát internal access token. Không cần gửi upstream access token sang API nội bộ.

Cách này giảm coupling giữa internal APIs và upstream IdP. API nội bộ chỉ cần tin internal issuer và policy token của tổ chức.

### 8.3. Không forward upstream access token như internal credential

Ví dụ sai:

~~~http
GET /api/orders HTTP/1.1
Host: orders.internal.example
Authorization: Bearer UPSTREAM_ACCESS_TOKEN
~~~

Nếu Orders API không được thiết kế để tin issuer và audience của upstream IdP, request này phải bị từ chối. Không nới lỏng Resource Server để chấp nhận mọi issuer hoặc token có chữ ký hợp lệ.

## 9. Token Exchange giữa upstream IdP và internal Authorization Server

### 9.1. Token Exchange giải quyết bài toán gì?

RFC 8693 định nghĩa OAuth 2.0 Token Exchange. Một client đã được xác thực gửi subject_token tới Authorization Server để yêu cầu token mới dùng cho một resource hoặc audience khác.

Các tham số quan trọng:
- grant_type: urn:ietf:params:oauth:grant-type:token-exchange.
- subject_token: token đại diện subject.
- subject_token_type: loại token đầu vào.
- actor_token và actor_token_type: danh tính actor nếu có delegation.
- audience hoặc resource: resource server đích.
- scope: quyền mong muốn trên token mới.
- requested_token_type: loại token đầu ra mong muốn.

Token Exchange không phải phép đổi token vô điều kiện. Authorization Server phải xác minh subject/actor token và áp dụng policy cho client, subject, actor, resource, audience và scope.

### 9.2. Spring Authorization Server 1.5.8 có Token Exchange tích hợp

SAS 1.5.8 tích hợp RFC 8693 Token Exchange tại Token Endpoint. Các thành phần mặc định gồm:

- OAuth2TokenExchangeAuthenticationConverter.
- OAuth2TokenExchangeAuthenticationToken.
- OAuth2TokenExchangeAuthenticationProvider.
- OAuth2TokenGenerator.
- OAuth2AuthorizationService.

Client muốn dùng grant này cần được đăng ký AuthorizationGrantType.TOKEN_EXCHANGE. Token Endpoint mặc định đã có converter/provider cho grant type đó; không cần tự viết một converter mới chỉ để xử lý cú pháp RFC 8693.

Ví dụ RegisteredClient:

~~~java
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;

RegisteredClient tokenBroker = RegisteredClient.withId("token-broker-registration")
        .clientId("internal-token-broker")
        .clientSecret(passwordEncoder.encode(tokenBrokerSecret))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.TOKEN_EXCHANGE)
        .scope("orders.read")
        .scope("profile.read")
        .build();
~~~

Cấu hình này chỉ cho phép client dùng grant type. Nó không tự cấp quyền đổi mọi token hoặc mọi audience. Provider vẫn áp dụng validation và authorization policy.

### 9.3. Giới hạn quan trọng của Token Exchange mặc định

Trong SAS 1.5.8, OAuth2TokenExchangeAuthenticationProvider xác minh subject/actor JWT bằng cách tra cứu token trong OAuth2AuthorizationService đã cấu hình.

Điều đó có nghĩa token đầu vào mặc định phải thuộc authorization state mà internal Authorization Server quản lý. Upstream ID Token hoặc access token do IdP bên ngoài phát hành không nằm trong kho authorization nội bộ chỉ vì chúng được ký hợp lệ.

Spring Authorization Server đã ghi nhận yêu cầu hỗ trợ thêm trusted issuers cho Token Exchange provider mặc định; behavior hiện tại vẫn giới hạn ở token được tra cứu trong OAuth2AuthorizationService. Vì vậy, không giả định bật TOKEN_EXCHANGE là đủ để đổi token từ một IdP bên ngoài.

Có hai giới hạn riêng cần phân biệt:

- Token Exchange converter mặc định của SAS 1.5.8 không nhận `subject_token_type=urn:ietf:params:oauth:token-type:id_token`; các token type được hỗ trợ cho subject token là JWT và access token theo các URI chuẩn tương ứng.
- Với subject token type JWT/access token, provider mặc định vẫn tra cứu token trong OAuth2AuthorizationService nội bộ. Một upstream access token không có trong store này vẫn không được chấp nhận.

OAuth2TokenExchangeAuthenticationProvider là class `final`, vì vậy không thể kế thừa để chỉ ghi đè một bước xác minh. Khi cần hỗ trợ external issuer hoặc ID Token, ứng dụng phải cung cấp converter/provider phù hợp và đăng ký qua extension point của Token Endpoint. Giữ nguyên client authentication; không mở endpoint riêng bỏ qua protocol validation.

### 9.4. Request Token Exchange minh họa

Đây là hình dạng request RFC 8693 cho trường hợp client muốn đổi upstream access token thành internal token:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.internal.example
Authorization: Basic BASE64_INTERNAL_BROKER_CREDENTIALS
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=urn:ietf:params:oauth:grant-type:token-exchange
&subject_token=UPSTREAM_ACCESS_TOKEN
&subject_token_type=urn:ietf:params:oauth:token-type:access_token
&audience=https%3A%2F%2Forders.internal.example
&scope=orders.read
~~~

**Lưu ý:** request trên chỉ là protocol shape. Với SAS 1.5.8 provider mặc định, subject token do upstream IdP phát hành sẽ không được chấp nhận nếu không được tìm thấy trong OAuth2AuthorizationService nội bộ. Muốn hỗ trợ external issuer, cần custom trust/validation implementation.

### 9.5. Khi nào cần custom Token Exchange provider?

Chỉ cần custom provider khi có yêu cầu thực sự đổi token giữa các security domains, ví dụ một gateway nhận upstream access token và cần internal token có audience cho API nội bộ.

Custom provider phải:
1. Xác thực OAuth2 client bằng cơ chế client authentication chuẩn.
2. Kiểm tra RegisteredClient được phép dùng token exchange.
3. Chỉ nhận token type được policy cho phép.
4. Chọn issuer từ allowlist cấu hình trước; không tự discovery issuer từ token hoặc request.
5. Xác minh chữ ký bằng key/JWKS được tin cậy hoặc gọi introspection với upstream client credentials nếu token opaque.
6. Kiểm tra issuer, audience, thời hạn, not-before, token purpose và các claim bắt buộc.
7. Ánh xạ upstream identity bằng issuer và subject sang local subject.
8. Xác minh actor token nếu request có delegation.
9. Giới hạn requested resource, audience và scope theo client và local authorization policy.
10. Tạo token mới bằng internal OAuth2TokenGenerator.
11. Lưu internal authorization qua OAuth2AuthorizationService.
12. Trả error theo RFC 8693 mà không tiết lộ chi tiết token hoặc tài khoản.

Không viết một provider chấp nhận mọi JWT. Không tải JWKS từ URL tùy ý trong token. Không coi claim sub là định danh toàn cục khi chưa kiểm tra iss.

### 9.5.1. Đăng ký custom converter/provider

SAS cho phép truy cập danh sách converter và provider mặc định qua OAuth2TokenEndpointConfigurer. Ví dụ khung:

~~~java
authorizationServerConfigurer.tokenEndpoint(tokenEndpoint -> {
    tokenEndpoint.accessTokenRequestConverters(converters ->
            converters.add(0, externalTokenExchangeConverter));

    tokenEndpoint.authenticationProviders(providers ->
            providers.add(0, externalTokenExchangeProvider));
});
~~~

externalTokenExchangeConverter và externalTokenExchangeProvider là component do ứng dụng triển khai. Đặt converter/provider tùy chỉnh trước phần mặc định nếu chúng xử lý cùng grant type. Provider tùy chỉnh cần xác định rõ token nào thuộc external trust policy; với token nội bộ, có thể để provider mặc định xử lý tiếp. Kiểm thử cả hai nhánh để tránh custom provider vô tình chiếm mọi Token Exchange request.

### 9.6. Impersonation và delegation

RFC 8693 phân biệt:

- **Impersonation:** token mới đại diện subject; hệ thống đích xử lý request như subject đang thực hiện hành động trong phạm vi quyền được cấp.
- **Delegation:** actor thực hiện hành động thay mặt subject; token mới cần thể hiện cả subject và actor theo policy.

Ví dụ delegation có thể sử dụng act claim trong JWT. Không tự thêm act chỉ vì client gửi actor_token; Authorization Server phải xác minh actor và quyền được ủy quyền.

### 9.7. Token Exchange không tự liên kết vòng đời hai token

Việc đổi token là một sự kiện riêng. RFC 8693 không mặc định làm subject token hết hiệu lực hoặc tự động truyền mọi sự kiện revocation sang token mới.

Nếu internal token phải mất hiệu lực khi upstream token bị revoke, cần thiết kế cơ chế riêng:
- Token TTL ngắn.
- Revocation event/notification.
- Introspection hoặc authorization state lookup.
- Local session/deprovisioning event.
- Mapping giữa external authorization và internal authorization để revoke theo policy.

Không giả định revoke upstream token sẽ tự động revoke internal token đã được phát hành.

## 10. Claims và quyền nội bộ

### 10.1. Không sao chép toàn bộ upstream claims

Upstream claims có thể gồm:
- email, name, preferred_username.
- groups, roles hoặc department.
- acr, amr, auth_time.
- custom claims riêng của IdP.

Mỗi claim phải được đánh giá:
- Có đáng tin cho mục đích nội bộ không?
- Có cần chuẩn hóa hoặc mapping không?
- Có được phép đưa vào ID Token hay access token không?
- Có thể đổi hoặc bị tái sử dụng không?
- Có nhạy cảm hoặc không cần thiết cho API đích không?

Không sao chép các claim protocol của upstream ID Token như iss, sub, aud, exp, iat, nonce hoặc azp vào internal ID Token. Những giá trị đó mô tả một OIDC transaction khác.

### 10.2. Quyền nội bộ đến từ local policy

Ví dụ upstream IdP trả group CORP_FINANCE. Internal directory có thể ánh xạ nó thành local authority FINANCE_USER sau khi kiểm tra:
- Issuer chính xác.
- Group thuộc namespace được tin cậy.
- User còn active.
- Tenant mapping hợp lệ.
- Client/resource có quyền nhận role đó.

Không ánh xạ group thành ADMIN chỉ dựa vào tên group. Không để upstream IdP quyết định trực tiếp scope của mọi internal API.

### 10.3. Claims phải phù hợp từng token

| Claim | Internal ID Token | Internal access token |
|---|---|---|
| sub | Local subject cho RP. | Local subject hoặc workload principal theo token policy. |
| aud | Internal client ID. | Internal API/resource. |
| tenant_id | Chỉ khi RP cần và được phép. | Khi API cần phân vùng dữ liệu. |
| roles | Có thể cung cấp tối thiểu cho UI/RP nếu policy cho phép. | Chỉ role/scope cần cho authorization của API. |
| email | Chỉ khi cần và consent/policy cho phép. | Thường không cần cho API authorization. |
| upstream_issuer | Chỉ khi có use case audit/interoperability rõ ràng. | Tránh đưa vào nếu API không cần. |

## 11. Logout, revocation và deprovisioning

### 11.1. Internal logout không đồng nghĩa upstream logout

Khi người dùng logout khỏi internal Authorization Server:
- Internal session cần bị kết thúc.
- Internal RP cần xử lý logout theo flow đã cấu hình.
- Internal refresh/access token cần được xử lý theo revocation policy.
- Upstream IdP session có thể vẫn tồn tại.

Nếu yêu cầu single logout xuyên nhiều hệ thống, phải triển khai RP-Initiated Logout, Back-Channel/Front-Channel Logout hoặc cơ chế federation tương ứng. Không giả định logout internal session sẽ logout tài khoản Google, Okta hoặc IdP doanh nghiệp.

### 11.2. Upstream token lifecycle

Upstream access/refresh token được quản lý theo chính sách của upstream provider và Spring OAuth2 Client. Khi user unlink identity hoặc token bị revoke:
- Xóa hoặc revoke authorized client local theo policy.
- Không tiếp tục dùng access token đã hết hạn/revoked.
- Xem xét refresh token rotation và reuse detection theo provider.
- Không ghi token ra log hoặc telemetry.
- Không để token được chia sẻ giữa hai user hoặc hai ClientRegistration.

### 11.3. Deprovisioning phải có hiệu lực nội bộ

Nếu nhân viên bị khóa trong IdP hoặc local HR directory, internal Authorization Server cần xác định nguồn sự thật và thời gian đồng bộ:
- Từ chối login mới.
- Vô hiệu hóa local session.
- Thu hồi refresh token và internal authorization theo policy.
- Cập nhật quyền local.
- Vô hiệu hóa federated identity nếu liên kết bị thu hồi.
- Ghi audit cho quyết định deprovision.

Không chờ tới khi upstream access token hết hạn mới thu hồi quyền nội bộ nếu tổ chức yêu cầu chặn ngay.

## 12. Kiểm thử federation và token boundaries

### 12.1. Kiểm thử upstream OIDC login

- [ ] Issuer URI nằm trong allowlist.
- [ ] Discovery metadata được lấy từ đúng issuer.
- [ ] ID Token signature được xác minh bằng key của issuer.
- [ ] iss khớp chính xác với issuer đã cấu hình.
- [ ] aud chứa client ID của internal Authorization Server.
- [ ] exp, iat, nonce và azp được kiểm tra theo OIDC.
- [ ] UserInfo response sub khớp ID Token sub nếu có gọi UserInfo.
- [ ] Callback URI chính xác và PKCE/state được xử lý đúng.
- [ ] IdP khác có cùng sub không bị nhập nhầm thành cùng một user.

### 12.2. Kiểm thử local identity mapping

- [ ] Cặp issuer + subject được unique.
- [ ] Local subject ổn định qua nhiều lần login.
- [ ] JIT provisioning đồng thời không tạo hai local account cho cùng issuer + subject.
- [ ] Một user có thể liên kết nhiều issuer theo policy.
- [ ] Không tự động link chỉ dựa trên email trùng nhau.
- [ ] User disabled/deprovisioned không thể login.
- [ ] Upstream groups/roles được mapping qua allowlist.
- [ ] Authorities của local principal là quyền nội bộ đã kiểm tra.

### 12.3. Kiểm thử internal tokens

- [ ] Internal ID Token có issuer nội bộ.
- [ ] Internal ID Token có audience là internal client ID.
- [ ] Internal ID Token sub là local subject.
- [ ] Internal access token có audience là API đích.
- [ ] Internal Resource Server từ chối token có issuer nội bộ nhưng audience không dành cho API.
- [ ] Scope và claims không vượt local authorization policy.
- [ ] Internal Resource Server từ chối upstream token nếu issuer/audience không được cấu hình tin cậy.
- [ ] ID Token không được dùng như access token.
- [ ] Không có upstream nonce, iss, aud hoặc exp bị copy nhầm sang internal token.

### 12.4. Kiểm thử Token Exchange

- [ ] Client đã authenticate.
- [ ] RegisteredClient được phép TOKEN_EXCHANGE.
- [ ] Token đầu vào đúng token type và issuer policy.
- [ ] Default converter từ chối ID Token token type; custom converter chỉ hỗ trợ nếu policy đã thiết kế.
- [ ] Token hết hạn, sai audience, sai issuer hoặc bị revoke bị từ chối.
- [ ] Default SAS provider chỉ nhận token mà nó tra cứu được trong OAuth2AuthorizationService.
- [ ] Custom external issuer provider kiểm tra issuer allowlist và JWKS/introspection.
- [ ] Audience/resource và scope đầu ra bị giới hạn.
- [ ] Actor/delegation được kiểm tra nếu có.
- [ ] Internal authorization được lưu.
- [ ] Revocation propagation được kiểm tra nếu deployment yêu cầu.

### 12.5. Kiểm thử logout và deprovisioning

- [ ] Internal logout kết thúc đúng local session.
- [ ] Upstream session được xử lý theo yêu cầu federation.
- [ ] Internal refresh token bị revoke khi local user bị deprovision.
- [ ] OAuth2AuthorizedClient của upstream bị xóa/revoke khi unlink.
- [ ] Logout/revocation trên nhiều application instance hoạt động nhất quán.
- [ ] Audit log không chứa raw token, client secret hoặc PII không cần thiết.

## 13. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Upstream login thành công nhưng internal RP không nhận được code | Authorization Server chưa tạo được local Authentication hoặc session. | Kiểm tra SecurityFilterChain order, oauth2Login callback và session. |
| invalid_issuer | Issuer trong ID Token khác issuer đã discovery/cấu hình. | Kiểm tra issuer URI và cấu hình provider. |
| invalid_audience | Upstream ID Token không dành cho client của internal Authorization Server. | Kiểm tra client registration tại IdP và aud. |
| Hai IdP tạo cùng local user ngoài ý muốn | Mapping chỉ dựa vào email hoặc sub. | Dùng issuer + subject và quy trình account linking. |
| Internal ID Token chứa upstream sub | Principal name chưa được ánh xạ sang local subject. | Dùng local OidcUser wrapper/identity mapping và test claim sub. |
| Internal API nhận upstream token rồi bị 401 | Issuer/audience của token không thuộc API nội bộ. | Dùng internal access token hoặc thiết kế token exchange. |
| Upstream API trả 401 | Dùng internal token hoặc upstream token sai audience/scope. | Chọn OAuth2AuthorizedClient đúng registration và resource. |
| Upstream token lộ qua outbound request | RestClient/WebClient tự động gắn token cho host không mong muốn. | Chỉ chọn authorized client ở request cần thiết, giới hạn host và redact logs. |
| Token Exchange mặc định từ chối upstream token | Token không tồn tại trong internal OAuth2AuthorizationService. | Dùng upstream login flow hoặc custom external-token exchange provider. |
| Token Exchange scope quá rộng | Tin scope request hoặc upstream group mà không có local policy. | Giao scope giữa client, subject, resource và authorization policy. |
| User bị khóa nhưng vẫn gọi API | Internal token/session còn hiệu lực hoặc deprovision chưa đồng bộ. | Revoke local authorization/session, giảm TTL và xử lý event deprovision. |
| Logout nội bộ không logout IdP | Hai session thuộc hai issuer khác nhau. | Triển khai logout federation theo yêu cầu, không giả định tự động. |
| Refresh upstream token thất bại | Token đã revoke, hết hạn hoặc provider thay đổi policy. | Xóa authorized client lỗi, yêu cầu login lại và ghi audit. |

## 14. Bài tập thực hành

**Bối cảnh:** công ty có IdP corporate và internal Authorization Server tại auth.internal.example. Các ứng dụng employee-portal và mobile-app cần đăng nhập bằng corporate IdP. Các API orders và payroll chỉ tin internal issuer.

### Yêu cầu

1. Đăng ký internal Authorization Server thành OIDC client tại corporate IdP.
2. Cấu hình ClientRegistration với issuer-uri, client ID, secret và scope openid.
3. Cấu hình hai SecurityFilterChain: Authorization Server endpoints và OAuth2 Login.
4. Thực hiện login và xác minh upstream ID Token.
5. Tạo FederatedIdentityDirectory với unique key issuer + subject.
6. Ánh xạ upstream identity sang local subject ổn định.
7. Trả LocalFederatedOidcUser với local authorities.
8. Cấu hình employee-portal là internal OIDC client.
9. Thực hiện Authorization Code Flow và xác minh internal ID Token có issuer/audience/sub đúng.
10. Phát internal access token có audience orders API và scope orders.read.
11. Dùng OAuth2AuthorizedClientManager để gọi upstream API bằng upstream access token.
12. Kiểm tra orders API từ chối upstream access token.
13. Đăng ký một client có TOKEN_EXCHANGE và thử exchange token do internal AS phát hành.
14. Thử exchange upstream token và xác nhận giới hạn của provider mặc định SAS 1.5.8.
15. Thiết kế custom provider chỉ chấp nhận issuer ngoài allowlist, kiểm tra JWT/introspection và ánh xạ subject sang local user.
16. Thử unlink account, logout và deprovisioning.
17. Viết runbook cho upstream issuer/key rotation, account linking và revocation.

**Tiêu chí hoàn thành:** internal RP nhận internal ID Token; internal API nhận internal access token; upstream API chỉ nhận upstream access token; mapping identity dùng issuer + subject; các token được lưu trong đúng service; token exchange external chỉ hoạt động khi có custom trust validation.

## 15. Checklist trước khi production

- [ ] Upstream issuer nằm trong allowlist cấu hình.
- [ ] Client registration có redirect URI chính xác.
- [ ] OIDC login dùng scope openid.
- [ ] ID Token upstream được xác minh đầy đủ.
- [ ] Mapping danh tính dùng issuer + subject.
- [ ] Local subject không phụ thuộc email hoặc display name.
- [ ] Account linking có proof và audit.
- [ ] Local authorities được tạo từ policy nội bộ.
- [ ] Internal issuer ổn định và khác upstream issuer.
- [ ] Internal ID Token audience là internal RP.
- [ ] Internal access token audience là internal Resource Server.
- [ ] Upstream access token chỉ gửi tới đúng upstream resource.
- [ ] OAuth2AuthorizedClientService và OAuth2AuthorizationService được dùng đúng vai trò.
- [ ] Không copy upstream protocol claims vào internal token.
- [ ] Internal API không tin upstream issuer ngoài policy đã công bố.
- [ ] Token Exchange client được cấp grant theo least privilege.
- [ ] Hiểu giới hạn subject/actor token lookup của provider mặc định SAS 1.5.8.
- [ ] Custom external-token exchange có issuer allowlist, key/introspection validation và audience/scope policy.
- [ ] Refresh token, logout, revocation và deprovisioning có runbook.
- [ ] Token và client secret không xuất hiện trong log.
- [ ] Có integration tests cho login, token validation, token exchange và multi-IdP mapping.
- [ ] Có audit trail cho account link/unlink và role mapping.
- [ ] Có kế hoạch xử lý upstream IdP outage và signing key rotation.

## Tổng kết

Trong mô hình identity federation, IdP đầu nguồn xác thực người dùng, còn internal Authorization Server chịu trách nhiệm ánh xạ danh tính và phát hành token theo policy nội bộ. Upstream ID Token dành cho internal OAuth2/OIDC Client; upstream access token dành cho API/resource của upstream provider. Internal ID Token dành cho internal RP; internal access token dành cho internal Resource Server.

Spring Authorization Server 1.5.8 có hướng dẫn chính thức để thay form login bằng OAuth2 Login và dùng OIDC social login. Có thể capture người dùng, ánh xạ claims và tạo internal ID Token từ local principal. Định danh nội bộ nên được quản lý độc lập bằng cặp issuer + subject và local subject ổn định.

SAS 1.5.8 cũng tích hợp RFC 8693 Token Exchange, nhưng provider mặc định tra cứu subject/actor JWT trong OAuth2AuthorizationService của chính máy chủ. Vì vậy, token của IdP ngoài không tự động được chấp nhận. Nếu cần đổi token xuyên issuer, phải xây dựng trust validation và authorization policy riêng cho issuer bên ngoài, sau đó phát hành internal token mới có audience và scope giới hạn.

## Tài liệu tham khảo

1. [Spring Authorization Server 1.5.8 — How-to: Authenticate using Social Login](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-social-login.html): cấu hình oauth2Login, hai SecurityFilterChain, capture federated user và map claims vào internal ID Token.
2. [Spring Authorization Server 1.5.8 — Overview](https://docs.spring.io/spring-authorization-server/reference/overview.html): danh sách grant types và Token Exchange support.
3. [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): Token Endpoint converter/provider mặc định và OAuth2TokenExchangeAuthenticationProvider.
4. [Spring Authorization Server 1.5.8 — OAuth2TokenExchangeAuthenticationToken API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2TokenExchangeAuthenticationToken.html): subject token, actor token, audience, resource và scope.
5. [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): OAuth2Authorization và OAuth2AuthorizationService.
6. [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): OAuth2/OIDC login, ClientRegistration và login processing.
7. [Spring Security — Core Interfaces and Classes](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html): ClientRegistration, OAuth2AuthorizedClient, OAuth2AuthorizedClientService và OAuth2AuthorizedClientManager.
8. [Spring Security — Authorized Client Features](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html): sử dụng OAuth2AuthorizedClientManager với RestClient/WebClient.
9. [OpenID Connect Core 1.0 incorporating errata set 2](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, issuer, subject, audience và validation rules.
10. [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693.html): subject_token, actor_token, resource, audience, scope, impersonation và delegation.
11. [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): sử dụng bearer access token và bảo vệ token khi truyền tới resource server.
12. [Spring Authorization Server GitHub issue #1867](https://github.com/spring-projects/spring-authorization-server/issues/1867): giới hạn provider mặc định khi subject/actor token được phát hành bởi trusted external issuer.
13. [Spring Authorization Server 1.5.8 — OAuth2TokenEndpointConfigurer API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2TokenEndpointConfigurer.html): extension point cho access token request converters và authentication providers.
14. [Spring Security 6.5 — OidcUser API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/core/oidc/user/OidcUser.html) và [IdTokenClaimAccessor API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/core/oidc/IdTokenClaimAccessor.html): phân biệt principal name với subject claim của upstream ID Token.
15. [Spring Security 6.5 — Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html) và [NimbusJwtDecoder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html): xác minh issuer, chữ ký, thời hạn và custom audience validator.
16. [Spring Authorization Server GitHub issue #1880](https://github.com/spring-projects/spring-authorization-server/issues/1880): giới hạn token type ID Token trong Token Exchange converter mặc định.

