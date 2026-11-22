# Tích hợp đăng nhập OIDC hoặc OAuth2 từ nhà cung cấp danh tính

> **Chương:** Liên kết danh tính  
> **Module:** `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`  
> **Mục tiêu module:** Học cách thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot.  
> **Phạm vi:** Spring Boot 3.x, Spring Security 6.x và Spring Authorization Server 1.5.x trên Servlet stack. Authorization Server đóng vai trò OAuth2/OIDC Client (Relying Party) khi đăng nhập qua IdP upstream, sau đó có thể phát hành token của issuer nội bộ cho các client downstream.

## 1. Bối cảnh và mục tiêu

Một tổ chức có thể đã sử dụng một Identity Provider (IdP) bên ngoài để quản lý nhân viên, khách hàng hoặc đối tác. Khi xây dựng Authorization Server nội bộ, tổ chức thường muốn người dùng đăng nhập bằng danh tính đã có thay vì tạo thêm một hệ thống mật khẩu độc lập.

Ví dụ, doanh nghiệp có IdP tại `https://login.corp.example` và Authorization Server tại `https://auth.platform.example`. Người dùng mở ứng dụng Portal. Portal chuyển người dùng tới Authorization Server. Authorization Server điều hướng browser tới IdP doanh nghiệp để xác thực. Sau khi IdP xác thực thành công, Authorization Server nhận kết quả, ánh xạ danh tính bên ngoài sang tài khoản nội bộ và tạo phiên đăng nhập local. Khi client Portal thực hiện OAuth2 Authorization Code Flow với Authorization Server nội bộ, server phát hành authorization code, access token và ID Token theo issuer nội bộ.

Trong kiến trúc này, Authorization Server đảm nhiệm hai vai trò:

- **Upstream Relying Party (RP):** sử dụng OAuth2/OIDC Client để đăng nhập qua IdP bên ngoài.
- **Downstream OpenID Provider (OP):** cung cấp OAuth2/OIDC cho các ứng dụng và API nội bộ.

Không nên nhầm token do IdP upstream cấp với token do Authorization Server nội bộ cấp. Danh tính upstream là đầu vào để xác lập principal nội bộ; token downstream là credential mới được phát hành theo chính sách, audience, scope và issuer của nền tảng.

Sau bài học, bạn có thể:

1. Phân biệt OAuth2 Login với OpenID Connect Login và hiểu giới hạn xác thực của OAuth2 thuần.
2. Mô tả kiến trúc Authorization Server làm RP với IdP upstream và OP với client downstream.
3. Cấu hình nhiều upstream provider bằng `ClientRegistration` và provider metadata.
4. Dùng issuer discovery để lấy authorization endpoint, token endpoint, JWKS và UserInfo endpoint.
5. Hiểu Authorization Code Flow, redirect URI, state, nonce và PKCE trong đăng nhập liên kết.
6. Xác minh ID Token và tải UserInfo theo OIDC.
7. Xây dựng mapping danh tính bền vững bằng cặp issuer và subject.
8. Provision tài khoản local, xử lý account linking và đồng bộ thuộc tính.
9. Ánh xạ group/role từ IdP thành authority nội bộ theo allowlist.
10. Giữ ranh giới giữa upstream tokens, local SecurityContext và downstream tokens.
11. Kiểm thử login thành công/thất bại, issuer mismatch, account linking, mapping và logout.

**Nguyên tắc chính:** Dùng OIDC khi cần xác thực người dùng liên kết. Lấy danh tính từ issuer đã tin cậy, định danh người dùng bằng cặp `(iss, sub)`, ánh xạ sang principal nội bộ và để Authorization Server phát hành token của chính issuer nội bộ.

## 2. Kiến trúc identity federation

### 2.1. Các vai trò trong hệ thống

| Thành phần | Vai trò |
| --- | --- |
| Upstream IdP | Xác thực End-User và phát hành ID Token/access token |
| Authorization Server nội bộ | OAuth2/OIDC Client đối với IdP; ánh xạ danh tính và tạo local session |
| Downstream RP/client | Đăng nhập bằng Authorization Server nội bộ |
| Resource Server | Xác minh access token do issuer được cấu hình phát hành |
| Identity link store | Ánh xạ external identity sang local user |
| User directory | Lưu tài khoản, trạng thái, tenant, profile và policy nội bộ |

### 2.2. Luồng đăng nhập

~~~mermaid
sequenceDiagram
    autonumber
    participant U as End-User Browser
    participant AS as Internal Authorization Server
    participant IDP as Upstream OIDC IdP
    participant DB as Local Identity Store
    participant RP as Downstream Client

    U->>RP: Mở ứng dụng
    RP->>AS: Authorization Request
    AS-->>U: Redirect tới upstream IdP
    U->>IDP: Authorization Request + state + nonce
    IDP->>U: Login / MFA / consent
    IDP-->>AS: Redirect callback với authorization code
    AS->>IDP: Token Request
    IDP-->>AS: ID Token + Access Token
    AS->>AS: Validate ID Token
    AS->>DB: Resolve (issuer, subject)
    DB-->>AS: Local user / account link
    AS->>AS: Tạo Authentication và local SecurityContext
    AS-->>U: Tiếp tục Authorization Request ban đầu
    AS-->>RP: Authorization Code nội bộ
    RP->>AS: Token Request
    AS-->>RP: Token do issuer nội bộ phát hành
~~~

### 2.3. Hai authorization flow khác nhau

Có hai giao dịch OAuth2/OIDC riêng:

1. **Upstream login:** Authorization Server nội bộ là client của IdP. Giao dịch này xác thực End-User và tạo local session.
2. **Downstream authorization:** Ứng dụng Portal là client của Authorization Server nội bộ. Giao dịch này cấp token theo quyền và scope nội bộ.

Không chuyển nguyên upstream authorization code cho Portal. Không dùng upstream ID Token làm ID Token của issuer nội bộ. Không đưa upstream access token vào response của downstream Token Endpoint như thể nó là access token nội bộ.

### 2.4. Identity federation không đồng nghĩa token federation

Identity federation là việc tin cậy một issuer bên ngoài để xác định người dùng và ánh xạ họ sang danh tính nội bộ. Token federation hoặc token exchange là bài toán riêng về việc chấp nhận/chuyển đổi credential và audience.

Trong mô hình phổ biến:

- IdP xác thực user.
- Authorization Server nội bộ tạo principal local.
- Authorization Server áp dụng policy nội bộ và phát hành token mới.
- Resource Server chỉ tin issuer/audience đã được cấu hình.

Nếu cần token exchange theo RFC 8693 hoặc downstream API phải gọi bằng upstream token, thiết kế riêng audience, actor, delegation, scope và token validation. Không relay token theo cách tùy tiện.

## 3. OAuth2 Login và OpenID Connect Login

### 3.1. OAuth 2.0 là authorization framework

OAuth 2.0 xác định cách client nhận access token để truy cập resource được bảo vệ. OAuth2 tự thân không định nghĩa một chuẩn identity assertion tương đương ID Token.

Một API UserInfo do provider OAuth2 công bố có thể trả profile user, nhưng ý nghĩa của các thuộc tính, cách định danh và bảo đảm xác thực phụ thuộc provider. Việc nhận được access token không tự chứng minh danh tính theo một chuẩn thống nhất.

### 3.2. OpenID Connect bổ sung lớp authentication

OIDC xây dựng trên OAuth2 và bổ sung ID Token. ID Token là JWT assertion về authentication event, có các claim chuẩn như:

- `iss`: issuer phát hành token.
- `sub`: subject duy nhất trong phạm vi issuer/sector.
- `aud`: client hoặc audience được token hướng tới.
- `exp`: thời điểm hết hạn.
- `iat`: thời điểm phát hành.
- `nonce`: liên kết ID Token với authentication request khi nonce được gửi.
- `auth_time`: thời điểm user được xác thực nếu được phát hành.
- `acr` và `amr`: thông tin authentication context/method nếu provider hỗ trợ.

Với OIDC Login, Spring Security xác minh ID Token và có thể gọi UserInfo Endpoint để lấy thêm claims.

### 3.3. Khi nào dùng OIDC, khi nào dùng OAuth2 provider?

| Nhu cầu | Lựa chọn |
| --- | --- |
| Đăng nhập doanh nghiệp, có issuer và subject chuẩn | OIDC |
| Cần xác minh ID Token, nonce và authentication claims | OIDC |
| Provider chỉ cung cấp OAuth2 + UserInfo API | OAuth2 Login với mapping riêng |
| Chỉ cần gọi API của provider thay mặt user | OAuth2 Client/Authorized Client; không nhất thiết tạo login |
| Provider không có UserInfo hoặc identity contract đáng tin cậy | Không tự suy luận user identity từ access token; cần tích hợp riêng có kiểm soát |

Nếu provider hỗ trợ OIDC, ưu tiên dùng OIDC thay cho tự giải mã access token để lấy username.

### 3.4. Spring Security hỗ trợ cả hai

Spring Security OAuth2 Client cung cấp `oauth2Login()` để tích hợp đăng nhập. Với registration có scope `openid`, framework sử dụng OIDC authentication flow và trả `OidcUser`. Với OAuth2 provider không dùng OIDC, framework dùng `OAuth2UserService` và trả `OAuth2User`.

Hai kiểu principal có API khác nhau. Code ứng dụng nên có adapter/mapping layer để chuẩn hóa chúng thành local principal, thay vì ép mọi upstream provider có cùng schema.

## 4. Đăng ký upstream provider

### 4.1. ClientRegistration

`ClientRegistration` mô tả một OAuth2/OIDC client registration:

| Thành phần | Ý nghĩa |
| --- | --- |
| `registrationId` | Khóa local để phân biệt provider |
| `clientId` | Client ID do IdP cấp |
| `clientSecret` | Credential của confidential client nếu có |
| `clientAuthenticationMethod` | Cách client xác thực tại Token Endpoint |
| `authorizationGrantType` | Thường là Authorization Code |
| `redirectUri` | Callback URL của ứng dụng |
| `scopes` | Scope yêu cầu, OIDC thường có openid/profile/email |
| `providerDetails` | Issuer, authorization/token/UserInfo/JWK endpoints |

`registrationId` là tên local, ví dụ `corp` hoặc `partner`. Nó không nhất thiết bằng issuer URL hoặc client ID.

### 4.2. OIDC Discovery qua issuer-uri

Nếu IdP hỗ trợ OIDC Discovery, cấu hình `issuer-uri` để Spring Boot/Spring Security tìm metadata:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp
            client-id: ${CORP_OIDC_CLIENT_ID}
            client-secret: ${CORP_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          corp:
            issuer-uri: https://login.corp.example
~~~

Framework sử dụng provider configuration để lấy authorization endpoint, token endpoint, JWKS URI, UserInfo endpoint và issuer metadata. Discovery phải được thực hiện qua HTTPS và issuer phải đúng với giá trị tin cậy đã cấu hình.

Không nhập một issuer bất kỳ từ query parameter hoặc do người dùng cung cấp. Dynamic issuer discovery không kiểm soát có thể biến ứng dụng thành SSRF client hoặc khiến server tin cậy IdP do attacker điều khiển.

### 4.3. Cấu hình OAuth2 provider không có OIDC Discovery

Nếu provider chỉ hỗ trợ OAuth2 và UserInfo endpoint riêng, cấu hình endpoint thủ công:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          legacy-partner:
            provider: legacy-partner
            client-id: ${PARTNER_CLIENT_ID}
            client-secret: ${PARTNER_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - profile
              - email
        provider:
          legacy-partner:
            authorization-uri: https://accounts.partner.example/oauth/authorize
            token-uri: https://accounts.partner.example/oauth/token
            user-info-uri: https://accounts.partner.example/api/userinfo
            user-name-attribute: id
            user-info-authentication-method: header
~~~

`user-name-attribute` phải trỏ tới thuộc tính định danh ổn định do provider cam kết. Không dùng email làm khóa liên kết nếu email có thể đổi hoặc tái sử dụng.

Với provider OAuth2-only, cần đánh giá rõ API UserInfo được bảo vệ thế nào, token thuộc provider nào, profile có ổn định không và provider bảo đảm tính duy nhất của identifier ra sao. OAuth2 không cung cấp chuẩn issuer/subject identity giống OIDC.

### 4.4. Redirect URI và môi trường

Redirect URI của registration thường có dạng:

~~~text
https://auth.platform.example/login/oauth2/code/corp
~~~

URI này phải được đăng ký tại IdP và khớp với URL thực tế. Trong production:

- Dùng HTTPS.
- Cấu hình public base URL tin cậy sau reverse proxy.
- Kiểm soát forwarded headers.
- Không để Host header không tin cậy quyết định callback host.
- Tách client registration và secret theo môi trường.
- Không dùng localhost hoặc wildcard callback trong production.

### 4.5. Nhiều upstream provider

Có thể đăng ký nhiều provider cùng lúc:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          workforce:
            provider: workforce
            client-id: ${WORKFORCE_CLIENT_ID}
            client-secret: ${WORKFORCE_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
          customer:
            provider: customer
            client-id: ${CUSTOMER_CLIENT_ID}
            client-secret: ${CUSTOMER_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
        provider:
          workforce:
            issuer-uri: https://sso.workforce.example
          customer:
            issuer-uri: https://identity.customer.example
~~~

Login initiation tương ứng có thể dùng `/oauth2/authorization/workforce` và `/oauth2/authorization/customer`. Mỗi registration cần mapping issuer, local tenant và account-link policy riêng.
## 5. Bật OAuth2 Login trong ứng dụng Authorization Server

### 5.1. Authorization Server và application login là hai filter chain

Spring Authorization Server xử lý các endpoint OAuth2/OIDC như authorization, token, JWK Set và OIDC Provider Configuration. Việc đăng nhập người dùng vào chính Authorization Server thường được xử lý bởi một Spring Security application filter chain riêng.

Ứng dụng cần dependency OAuth2 Client, ví dụ Gradle:

~~~kotlin
implementation("org.springframework.boot:spring-boot-starter-oauth2-client")
~~~

Dependency này cung cấp `ClientRegistration`, OAuth2 Login filters, token client và UserService. Nó bổ sung cho dependency Spring Authorization Server của ứng dụng.

Ví dụ cấu hình hai chain:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerChain(HttpSecurity http)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, as ->
                as.oidc(Customizer.withDefaults()))
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/assets/**", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Đây là cấu hình khung. Authorization Server còn cần RegisteredClientRepository, OAuth2AuthorizationService, AuthorizationServerSettings, JWK source và user directory. Application chain chịu trách nhiệm redirect tới upstream IdP và thiết lập local Authentication sau callback.

### 5.2. Các endpoint của Spring Security OAuth2 Client

Với registration ID `corp`, Spring Security cung cấp các endpoint mặc định:

| Endpoint | Vai trò |
| --- | --- |
| `/oauth2/authorization/corp` | Bắt đầu login với registration corp |
| `/login/oauth2/code/corp` | Nhận authorization response từ IdP |
| Authorization Endpoint của IdP | User login, MFA và consent |
| Token Endpoint của IdP | Đổi authorization code lấy token |
| UserInfo Endpoint | Lấy claims bổ sung nếu flow sử dụng |

Không tự viết controller nhận authorization code rồi đổi token nếu không có yêu cầu đặc biệt. `oauth2Login()` đã kết hợp các filter, authorization request repository, state validation, token client và user service.

### 5.3. Bắt đầu login từ trang đăng nhập

Có thể cung cấp link tới registration:

~~~html
<a href="/oauth2/authorization/corp">Đăng nhập bằng tài khoản doanh nghiệp</a>
<a href="/oauth2/authorization/legacy-partner">Đăng nhập bằng tài khoản đối tác</a>
~~~

Nếu có nhiều provider, chỉ hiển thị provider phù hợp với tenant/ứng dụng. Không để người dùng chọn một issuer bất kỳ qua query parameter rồi server tự discovery.

### 5.4. Client credentials và PKCE

Authorization Code Flow là lựa chọn phù hợp cho browser-based login. Một web application chạy server-side thường là confidential client, giữ client secret ở server và xác thực tại Token Endpoint. Secret phải lấy từ secret manager/environment injection, không commit vào repository hoặc gửi xuống browser.

PKCE bảo vệ authorization code khỏi bị đánh cắp và redeem trái phép. Dùng PKCE khi IdP hỗ trợ, đặc biệt bắt buộc với public client theo OAuth security best current practice. PKCE bổ sung cho client authentication; không thay thế client secret của confidential client.

### 5.5. State, nonce và callback protection

Spring Security tạo và kiểm tra state cho authorization request. Với OIDC, nonce được gửi trong authentication request và được kiểm tra trong ID Token. Hai giá trị giải quyết các vấn đề khác nhau:

- `state` liên kết authorization response với request đang chờ, giảm CSRF/login response injection.
- `nonce` liên kết ID Token với authentication request, giảm replay/substitution ID Token.

Không tự đặt state tĩnh, tái sử dụng state giữa các login hoặc tắt state/nonce validation để sửa lỗi callback. Nếu dùng custom `AuthorizationRequestRepository`, phải giữ one-time correlation, session binding và TTL.

## 6. Xác minh danh tính từ upstream IdP

### 6.1. Kiểm tra ID Token

Với OIDC, Spring Security xử lý xác minh ID Token theo provider metadata và client registration. Các kiểm tra quan trọng gồm:

- Chữ ký được xác minh bằng key phù hợp từ JWKS của issuer.
- `iss` khớp issuer đã cấu hình.
- `aud` chứa client ID của registration.
- `exp` còn hiệu lực, xét clock skew theo policy.
- `iat` và các thời điểm liên quan hợp lệ.
- `nonce` khớp request nếu đã gửi nonce.
- Các quy tắc OIDC khác tùy flow và claims được yêu cầu.

Không chỉ Base64-decode JWT rồi tin payload. Không dùng token từ issuer khác chỉ vì chữ ký có thể được xác minh bằng một key trùng tên.

### 6.2. UserInfo Endpoint

OIDC UserInfo có thể bổ sung profile claims như name, email, preferred_username hoặc locale. ID Token vẫn là identity assertion chính; UserInfo là dữ liệu bổ sung.

Khi dùng UserInfo:

- Gọi endpoint qua HTTPS.
- Dùng Access Token đúng provider/registration.
- Xác minh subject trong UserInfo tương ứng với subject trong ID Token.
- Chỉ yêu cầu scope cần thiết.
- Xử lý thuộc tính thiếu hoặc thay đổi.
- Không coi email hoặc display name là immutable identity key.

### 6.3. OAuth2-only provider

Với OAuth2-only provider, Spring Security gọi UserInfo endpoint thông qua `DefaultOAuth2UserService`. Provider cần cung cấp một thuộc tính tên người dùng được cấu hình bằng `user-name-attribute`.

Ví dụ `id` hoặc `user_id` có thể được dùng nếu provider cam kết tính ổn định và duy nhất. Nếu provider chỉ trả email có thể thay đổi, cần một hợp đồng identity khác hoặc không dùng nó làm external subject key.

### 6.4. Không tự gọi UserInfo bằng upstream token bất kỳ

Upstream Access Token là credential dành cho resource/API của issuer đó. Không gửi nó tới API tùy ý hoặc lưu nó vào log. Chỉ gửi tới UserInfo endpoint được discovery/configuration của đúng registration xác định.

## 7. Chuẩn hóa principal và ánh xạ danh tính

### 7.1. Khóa định danh OIDC là issuer + subject

`sub` chỉ duy nhất trong phạm vi issuer/sector. Vì vậy khóa liên kết bền vững nên gồm:

~~~text
external_identity_key = (issuer, subject)
~~~

Ví dụ:

~~~text
("https://login.corp.example", "00u8a1f2")
("https://identity.partner.example", "00u8a1f2")
~~~

Hai giá trị subject giống nhau từ hai issuer khác nhau là hai external identity khác nhau. Với pairwise subject, cùng một người có thể nhận subject khác nhau ở các client/sector khác nhau; identity mapping phải theo đúng OIDC deployment contract.

Với OAuth2-only provider, dùng namespace provider đã cấu hình cộng với stable user identifier theo hợp đồng của provider. Không giả vờ có `iss` chuẩn nếu provider không cung cấp issuer semantics.

### 7.2. Mô hình bảng liên kết

Ví dụ schema quan hệ:

~~~sql
CREATE TABLE local_user (
    id              uuid PRIMARY KEY,
    tenant_id       varchar(100) NOT NULL,
    status          varchar(30) NOT NULL,
    display_name    varchar(255),
    email           varchar(320),
    created_at      timestamptz NOT NULL
);

CREATE TABLE federated_identity (
    id              uuid PRIMARY KEY,
    local_user_id   uuid NOT NULL REFERENCES local_user(id),
    tenant_id       varchar(100) NOT NULL,
    provider_key    varchar(255) NOT NULL,
    issuer          varchar(512),
    subject         varchar(512) NOT NULL,
    created_at      timestamptz NOT NULL,
    last_login_at   timestamptz,
    UNIQUE (tenant_id, provider_key, issuer, subject)
);

CREATE UNIQUE INDEX uq_federated_identity_oauth2
    ON federated_identity(tenant_id, provider_key, subject)
    WHERE issuer IS NULL;
~~~

Với OIDC, provider key đại diện registration và issuer lưu giá trị canonical. Với OAuth2-only provider, issuer có thể null nhưng provider_key phải là namespace ổn định đã cấu hình; partial unique index bảo đảm không tạo identity trùng trong cùng tenant. Điều chỉnh index theo database và quy tắc tenant thực tế.

### 7.3. Resolve hoặc provision user

Một service có thể thực hiện quy trình:

~~~java
public LocalUser resolveIdentity(
        String providerKey,
        String tenantId,
        String issuer,
        String subject,
        Map<String, Object> claims) {

    return identityRepository
        .findByTenantIdAndProviderKeyAndIssuerAndSubject(
            tenantId, providerKey, issuer, subject)
        .map(this::requireActiveUser)
        .orElseGet(() -> provisionAccordingToPolicy(
            providerKey, tenantId, issuer, subject, claims));
}
~~~

`provisionAccordingToPolicy` là logic của ứng dụng. Có thể tự động tạo tài khoản cho workforce IdP đã được quản trị phê duyệt, nhưng yêu cầu mời hoặc admin approval với đối tác. Không bật Just-In-Time provisioning cho mọi issuer mà không có tenant allowlist và policy.

`TrustedTenantResolver` phải suy ra tenant từ registration/provider policy đã cấu hình và claims được tin cậy. Không lấy tenant trực tiếp từ query parameter hoặc một claim chưa được kiểm tra.

### 7.4. Account linking không dựa riêng vào email

Không tự động liên kết external identity với local account chỉ vì email giống nhau. Email có thể đổi, chưa verified, được tái sử dụng hoặc có quy tắc alias khác nhau giữa provider.

Quy trình linking an toàn thường yêu cầu:

1. User đang đăng nhập local account hiện có.
2. User re-authenticate hoặc thực hiện step-up theo policy.
3. User chủ động liên kết IdP mới.
4. Ứng dụng xác minh callback của IdP mới và issuer/subject.
5. Tạo identity link trong transaction với unique constraint.
6. Ghi audit event và thông báo nếu policy yêu cầu.

Nếu account đã được liên kết với user khác, dừng flow và yêu cầu quy trình hỗ trợ/administrative resolution. Không tự chuyển quyền sở hữu account.

### 7.5. Cập nhật profile và deprovisioning

Profile claims có thể thay đổi theo lần login. Quyết định field nào được đồng bộ:

- Display name và avatar thường là dữ liệu có thể cập nhật.
- Email chỉ cập nhật khi provider bảo đảm verified status và policy cho phép.
- Tenant, employment status và group membership cần nguồn có thẩm quyền.
- Local username/user ID không nên bị thay đổi chỉ vì upstream preferred_username thay đổi.

Khi nhân viên rời tổ chức hoặc IdP thu hồi account, cần deprovisioning policy: disable local user, revoke local sessions/refresh tokens, xử lý downstream authorization và giữ audit theo retention. Một lần login thất bại không tự chứng minh account đã bị xóa tại IdP.
## 8. Tùy biến OIDC UserService và OAuth2 UserService

### 8.1. Mục đích của UserService

Sau khi token response được xử lý, Spring Security dùng UserService để tạo principal cho login. Đây là vị trí phù hợp để đọc subject/claims từ upstream identity đã xác minh, tìm external identity link, provision hoặc tải local user, kiểm tra trạng thái local account, ánh xạ local authorities và trả principal có định danh nội bộ ổn định.

Không đưa logic cấp quyền phức tạp vào controller callback. Đặt logic identity resolution trong service có thể kiểm thử độc lập.

### 8.2. OIDC UserService

`OidcUserService` mặc định tải UserInfo khi provider và scope yêu cầu. Có thể bọc service này để thêm local identity mapping:

~~~java
@Bean
OAuth2UserService<OidcUserRequest, OidcUser> federatedOidcUserService(
        IdentityFederationService identityFederationService,
        TrustedTenantResolver tenantResolver) {

    OidcUserService delegate = new OidcUserService();

    return userRequest -> {
        OidcUser upstreamUser = delegate.loadUser(userRequest);

        String issuer = userRequest.getClientRegistration()
            .getProviderDetails()
            .getIssuerUri();
        String providerKey = userRequest.getClientRegistration()
            .getRegistrationId();
        String tenantId = tenantResolver.resolve(
            providerKey, upstreamUser.getClaims());

        String subject = upstreamUser.getSubject();

        LocalUser localUser = identityFederationService
            .resolveOrProvisionOidcUser(
                providerKey, tenantId, issuer, subject,
                upstreamUser.getClaims());

        Set<GrantedAuthority> authorities =
            new LinkedHashSet<>(upstreamUser.getAuthorities());
        authorities.addAll(identityFederationService.mapAuthorities(
            localUser, upstreamUser.getClaims()));

        return new LocalFederatedOidcUser(
            upstreamUser, localUser.getId().toString(), authorities);
    };
}
~~~

`LocalFederatedOidcUser` là adapter do ứng dụng định nghĩa, implement `OidcUser` và delegate ID Token, UserInfo, claims và attributes sang `upstreamUser`; `getName()` trả local user ID; `getAuthorities()` trả authorities đã được mapping theo policy nội bộ. Nhờ vậy ứng dụng dùng principal nội bộ ổn định mà vẫn giữ OIDC identity details cần thiết.

Không tự tạo ID Token mới trong UserService. ID Token upstream đã được Spring Security xác minh; Authorization Server nội bộ sẽ phát hành token downstream ở protocol flow riêng.

### 8.3. OAuth2 UserService cho provider không dùng OIDC

Với OAuth2-only provider, dùng `DefaultOAuth2UserService` rồi ánh xạ thuộc tính định danh được cấu hình:

~~~java
@Bean
OAuth2UserService<OAuth2UserRequest, OAuth2User> federatedOAuth2UserService(
        IdentityFederationService identityFederationService,
        TrustedTenantResolver tenantResolver) {

    DefaultOAuth2UserService delegate = new DefaultOAuth2UserService();

    return userRequest -> {
        OAuth2User upstreamUser = delegate.loadUser(userRequest);

        ClientRegistration registration =
            userRequest.getClientRegistration();
        String providerKey = registration.getRegistrationId();
        String tenantId = tenantResolver.resolve(
            providerKey, upstreamUser.getAttributes());

        String usernameAttribute = registration.getProviderDetails()
            .getUserInfoEndpoint()
            .getUserNameAttributeName();

        Object externalId =
            upstreamUser.getAttributes().get(usernameAttribute);

        if (externalId == null) {
            throw new OAuth2AuthenticationException(
                new OAuth2Error("invalid_user_info_response"),
                "The configured user identifier is missing");
        }

        LocalUser localUser = identityFederationService
            .resolveOrProvisionOAuth2User(
                providerKey, tenantId,
                externalId.toString(),
                upstreamUser.getAttributes());

        Set<GrantedAuthority> authorities =
            new LinkedHashSet<>(upstreamUser.getAuthorities());
        authorities.addAll(identityFederationService.mapAuthorities(
            localUser, upstreamUser.getAttributes()));

        return new LocalFederatedOAuth2User(
            upstreamUser, localUser.getId().toString(), authorities);
    };
}
~~~

`LocalFederatedOAuth2User` là adapter implement `OAuth2User`, delegate attributes sang upstream principal, trả local user ID từ `getName()` và authorities nội bộ đã được mapping. Với provider OAuth2-only, `providerKey`/registration ID tạo namespace identity; external identifier phải được provider bảo đảm ổn định.

### 8.4. Gắn UserService vào oauth2Login

~~~java
http.oauth2Login(oauth2 -> oauth2
    .userInfoEndpoint(userInfo -> userInfo
        .oidcUserService(federatedOidcUserService)
        .userService(federatedOAuth2UserService)
    )
);
~~~

Nếu chỉ dùng OIDC, có thể cấu hình riêng `oidcUserService`. Nếu chỉ dùng OAuth2-only provider, cấu hình `userService`. Không dùng một service OAuth2 chung để tự xử lý ID Token nếu không giữ đúng OIDC validation.

### 8.5. Principal adapter phải giữ đúng contract

Adapter nên giữ các phương thức cần thiết:

- OIDC: `getIdToken()`, `getUserInfo()`, `getClaims()`, `getAttributes()`.
- OAuth2: `getAttributes()`.
- Cả hai: `getAuthorities()` và `getName()`.

Không trả local user ID bằng cách sửa claim `sub` trong upstream ID Token. `sub` là claim của issuer bên ngoài; local user ID là định danh nội bộ. Giữ chúng ở hai trường riêng để audit và account linking.

Ví dụ khung adapter OIDC:

~~~java
final class LocalFederatedOidcUser implements OidcUser {

    private final OidcUser delegate;
    private final String localUserId;
    private final Collection<? extends GrantedAuthority> authorities;

    LocalFederatedOidcUser(
            OidcUser delegate,
            String localUserId,
            Collection<? extends GrantedAuthority> authorities) {
        this.delegate = delegate;
        this.localUserId = localUserId;
        this.authorities = authorities;
    }

    @Override public String getName() { return localUserId; }
    @Override public Map<String, Object> getAttributes() { return delegate.getAttributes(); }
    @Override public Map<String, Object> getClaims() { return delegate.getClaims(); }
    @Override public OidcIdToken getIdToken() { return delegate.getIdToken(); }
    @Override public OidcUserInfo getUserInfo() { return delegate.getUserInfo(); }
    @Override public Collection<? extends GrantedAuthority> getAuthorities() {
        return authorities;
    }
}
~~~

OAuth2-only adapter làm tương tự với `OAuth2User`: delegate `getAttributes()`, trả local ID từ `getName()` và dùng authorities đã mapping. Đây là class minh họa; bổ sung constructor validation và các method cần thiết theo ứng dụng.

## 9. Ánh xạ group và role thành quyền nội bộ

### 9.1. Không tin trực tiếp role name từ IdP

IdP có thể trả claims như `groups`, `roles`, `entitlements` hoặc `memberOf`. Cấu trúc và ý nghĩa phụ thuộc provider. Không tự động chuyển mọi giá trị thành `ROLE_ADMIN` hoặc authority có quyền cao.

Nên có bảng mapping:

| Upstream provider | External group/claim | Local authority |
| --- | --- | --- |
| workforce | `portal-users` | `ROLE_PORTAL_USER` |
| workforce | `finance-approvers` | `ROLE_PAYMENT_APPROVER` |
| customer | `premium-tier` | `ROLE_PREMIUM_CUSTOMER` |
| partner | `support-agents` | `ROLE_SUPPORT_AGENT` |

Mapping phải gắn với provider và tenant. Cùng một chuỗi group có thể có ý nghĩa khác nhau ở hai IdP.

### 9.2. Chỉ cấp quyền từ mapping được phê duyệt

Ví dụ logic:

~~~java
Set<GrantedAuthority> mapGroups(
        String providerKey,
        String tenantId,
        Collection<String> externalGroups) {

    return externalGroups.stream()
        .map(group -> roleMappingRepository
            .findLocalRole(providerKey, tenantId, group))
        .flatMap(Optional::stream)
        .map(SimpleGrantedAuthority::new)
        .collect(Collectors.toUnmodifiableSet());
}
~~~

Đây là fragment. Nếu group không nằm trong mapping, bỏ qua hoặc ghi audit theo policy. Không dùng chuỗi do IdP trả trực tiếp làm authority.

### 9.3. Authentication assurance

Claims `acr`, `amr` và `auth_time` có thể hỗ trợ policy step-up authentication nếu IdP phát hành theo contract đáng tin cậy. Ví dụ, thao tác thay đổi thông tin thanh toán có thể yêu cầu MFA gần đây.

Không biến một giá trị `amr` thành quyền truy cập lâu dài. Assurance có thời điểm và ngữ cảnh; phải kiểm tra freshness, issuer và mức bảo đảm thực tế của IdP.

### 9.4. Local authorization vẫn là nguồn quyết định

IdP xác thực user; Authorization Server nội bộ quyết định user có được dùng hệ thống nào, tenant nào, scope nào và role nào. Group claims upstream là input cho policy, không thay thế policy nội bộ.

## 10. Từ upstream Authentication đến token nội bộ

### 10.1. Local SecurityContext

Sau khi callback thành công và UserService trả principal, Spring Security tạo Authentication và lưu vào SecurityContext theo cấu hình application chain. Phiên này đại diện cho người dùng đã đăng nhập vào Authorization Server nội bộ.

SAS dùng Authentication đó khi xử lý Authorization Request downstream. Khi user consent và client được phép, AS cấp authorization code rồi token theo RegisteredClient, scope, consent và token policy.

### 10.2. Phát hành claims nội bộ

Nếu muốn đưa tenant hoặc local user ID vào Access Token JWT nội bộ, dùng `OAuth2TokenCustomizer<JwtEncodingContext>`. Ví dụ chỉ thêm claim cho Access Token:

~~~java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> internalAccessTokenCustomizer(
        LocalAuthorizationPolicy localAuthorizationPolicy) {

    return context -> {
        if (!OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
            return;
        }

        String localUserId = context.getPrincipal().getName();

        LocalTokenClaims claims =
            localAuthorizationPolicy.claimsFor(
                localUserId,
                context.getRegisteredClient(),
                context.getAuthorizedScopes());

        context.getClaims()
            .claim("local_user_id", localUserId)
            .claim("tenant_id", claims.tenantId())
            .claim("roles", claims.allowedRoles());
    };
}
~~~

`LocalAuthorizationPolicy` phải tính quyền dựa trên user, client, scope và policy nội bộ. Chỉ đưa claims mà Resource Server thực sự cần; không copy toàn bộ upstream claims vào token downstream.

Customizer phải được gắn vào `JwtGenerator` mà Authorization Server đang dùng. Nếu ứng dụng tự cấu hình `OAuth2TokenGenerator`, hãy gọi `jwtGenerator.setJwtCustomizer(customizer)`; chỉ khai báo bean customizer mà không nối vào generator tự tạo sẽ không thay đổi token được phát hành.

### 10.3. Audience và scope

Upstream token có audience hướng tới API của IdP. Downstream token cần audience và scope phù hợp với Resource Server nội bộ. Không tái sử dụng upstream access token làm access token cho API khác audience.

Nếu một backend cần gọi API upstream thay mặt user, dùng `OAuth2AuthorizedClient` và access token của registration upstream. Nếu cần delegation hoặc token exchange, thiết kế riêng theo RFC 8693 và policy của cả hai issuer.

### 10.4. Hai kho token khác nhau

| Service | Dữ liệu |
| --- | --- |
| `OAuth2AuthorizedClientService` | Access/refresh token do upstream IdP cấp để AS gọi API upstream |
| `OAuth2AuthorizationService` | Authorization và token do AS nội bộ phát hành cho downstream client |
| `RegisteredClientRepository` | Registration của downstream OAuth2/OIDC client |
| `ClientRegistrationRepository` | Registration của upstream OAuth2/OIDC provider |

Không dùng `OAuth2AuthorizationService` để lưu upstream authorized client chỉ vì cả hai đều chứa token. Hai loại token có issuer, audience, owner và lifecycle khác nhau.

## 11. Lưu trữ upstream Authorized Client

Nếu Authorization Server cần gọi UserInfo, directory API hoặc API khác của upstream IdP sau login, cần lưu authorized client theo principal/registration phù hợp.

Spring Boot có thể tự cấu hình `OAuth2AuthorizedClientService` mặc định. Trong production, xem xét:

- Lưu token ở server-side, không đưa refresh token xuống browser.
- Mã hóa token khi lưu persistent store.
- Giới hạn ai có thể truy xuất authorized client.
- Gắn authorized client với local principal và registration ID.
- Xóa/revoke upstream token khi unlink account hoặc deprovision theo policy.
- Xử lý refresh token rotation và refresh failure.
- Không log token value hoặc đưa token vào metric label.

Nếu chỉ cần thông tin identity đã được xác minh ở login time, không giữ upstream access token lâu hơn mức cần thiết. Giảm scope và thời gian lưu trữ theo nguyên tắc least privilege.

## 12. Session, logout và vòng đời liên kết

### 12.1. Local logout

Local logout kết thúc phiên đăng nhập tại Authorization Server nội bộ bằng Spring Security LogoutFilter/LogoutHandler. Việc này dọn local SecurityContext và session theo cấu hình. Nó không nhất thiết kết thúc session tại upstream IdP.

### 12.2. Upstream OP logout

Nếu upstream IdP hỗ trợ RP-Initiated Logout và công bố `end_session_endpoint`, ứng dụng có thể điều hướng browser tới endpoint đó sau local logout bằng flow phù hợp. Phải dùng ID Token hint đúng issuer/client, post-logout redirect URI đã đăng ký và state correlation. Không giả định mọi OAuth2-only provider có OIDC logout endpoint.

### 12.3. Downstream logout

Client downstream có thể gọi OIDC RP-Initiated Logout Endpoint của Authorization Server nội bộ. Khi đó AS kết thúc local OP session. Nếu cần logout lan truyền tới RP khác, triển khai Front-Channel hoặc Back-Channel Logout theo profile và registration tương ứng.

### 12.4. Unlink account khác logout

Unlink external identity là thay đổi account-link relationship. Nó cần authorization, audit và xác nhận phù hợp. Logout chỉ kết thúc phiên hiện tại; nó không tự xóa identity link. Deprovisioning có thể cần disable user và revoke các token/session nội bộ theo policy.

## 13. Bảo mật và các lỗi thường gặp

### 13.1. Trust boundary

- Chỉ tin issuer được cấu hình và xác minh qua metadata/JWKS.
- Dùng HTTPS cho discovery, callback, token và UserInfo endpoints.
- Không chấp nhận issuer tùy ý từ request.
- Không bỏ qua issuer, audience, expiry hoặc nonce validation.
- Giới hạn redirect URI và bảo vệ public base URL.
- Giữ client secret ở server-side secret store.
- Dùng state và PKCE theo đúng flow.
- Không log ID Token, access token, refresh token hoặc authorization code.

### 13.2. Account confusion

Các lỗi phổ biến:

- Dùng email làm primary key liên kết identity.
- Chỉ dùng subject mà bỏ issuer.
- Gộp cùng username giữa hai tenant.
- Tự link account mới vào local user hiện có mà không có proof.
- Chấp nhận IdP do người dùng tự chọn.
- Dùng external group trực tiếp làm local role.
- Giữ local account active sau khi upstream identity đã bị deprovision mà không có policy.

Dùng unique external identity key, issuer/provider allowlist, tenant mapping, explicit account linking và audit.

### 13.3. Login CSRF và account swapping

State ngăn response không gắn với authorization request đang chờ. Trong account linking, ngoài state, cần bảo đảm callback thuộc phiên local account đang yêu cầu linking. Nếu browser đổi account hoặc session giữa lúc bắt đầu và callback, không gắn identity vào user khác.

Với flow nhạy cảm, bind link transaction với local user ID, session ID, registration ID và expiry; consume một lần sau callback thành công.

### 13.4. SSRF và discovery

Không cho phép người dùng gửi URL issuer tùy ý để server truy cập discovery/JWKS/UserInfo. Dùng cấu hình provider được quản trị, hostname allowlist, egress policy và timeout. Discovery metadata là input tin cậy chỉ sau khi issuer đã được xác minh theo cấu hình.

## 14. Kiểm thử identity federation

### 14.1. Kiểm thử OIDC login

Kiểm tra:

- Discovery lấy đúng issuer, authorization/token/JWKS/UserInfo endpoints.
- Redirect URI đúng registration ID và public base URL.
- State mismatch hoặc replay bị từ chối.
- ID Token sai chữ ký, issuer, audience, expiry hoặc nonce bị từ chối.
- UserInfo subject mismatch bị từ chối.
- Thiếu claim subject không tạo local account.
- Provider timeout hoặc JWKS rotation được xử lý đúng.

### 14.2. Kiểm thử account mapping

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Cùng issuer + subject login lại | Resolve đúng local user |
| Cùng subject, issuer khác | Không gộp thành cùng user |
| Subject thay đổi | Không tự động chuyển identity link |
| Email giống local user | Không auto-link |
| Email chưa verified | Không dùng để account linking |
| Identity link đã thuộc user khác | Từ chối và audit |
| Local user disabled | Không cấp local session |
| Provider không nằm allowlist | Không bắt đầu login |
| Tenant mapping không hợp lệ | Không provision user |
| Group không được mapping | Không cấp local authority |
| Concurrent JIT provisioning | Unique constraint ngăn duplicate |

### 14.3. Kiểm thử OAuth2-only provider

- UserInfo endpoint yêu cầu bearer token đúng.
- Thuộc tính `user-name-attribute` tồn tại.
- Identifier ổn định theo provider contract.
- Thiếu hoặc sai attribute bị từ chối.
- Không giả định OAuth2 access token chứa ID Token claims.
- Không gọi UserInfo endpoint khác registration.

### 14.4. Kiểm thử downstream token issuance

Sau khi upstream login thành công:

1. Xác nhận local SecurityContext chứa local principal.
2. Gửi downstream Authorization Request với client đã đăng ký.
3. Xác nhận consent và scope được áp dụng.
4. Đổi authorization code lấy token nội bộ.
5. Xác minh issuer/audience/signature của token nội bộ.
6. Xác nhận claims nội bộ chỉ chứa dữ liệu được policy cho phép.
7. Xác nhận upstream token không bị relay thành downstream access token.

### 14.5. Kiểm thử logout và deprovision

- Local logout kết thúc session AS.
- Upstream OP session còn hay mất đúng theo logout flow đã cấu hình.
- Downstream RP logout không bị nhầm với upstream logout.
- Deprovision user vô hiệu hóa quyền và session/token theo policy.
- Unlink account không tự xóa local user hoặc identity link khác.

## 15. Vận hành và troubleshooting

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| /oauth2/authorization/corp trả 404 | Thiếu ClientRegistration hoặc OAuth2 Client dependency | Boot configuration và dependency |
| Callback state mismatch | Session cookie không được gửi, request replay hoặc custom repository sai | Cookie SameSite, session và state store |
| Invalid issuer | issuer-uri không khớp claim iss | Provider metadata và IdP config |
| Invalid audience | Client ID khác aud | Client registration tại IdP |
| Invalid nonce | Nonce bị mất hoặc ID Token không đúng request | Authorization request repository |
| JWKS signature failure | Key rotation/cache hoặc issuer sai | JWKS URI, kid và cache |
| UserInfo 401 | Access token, scope hoặc auth method không đúng | UserInfo endpoint config |
| UserInfo subject mismatch | Provider trả profile khác identity token | IdP contract và response |
| User login được nhưng local user không tồn tại | Provisioning/mapping chưa chạy | IdentityFederationService |
| Login nhầm tenant | Mapping chỉ dựa username/email | Provider/issuer/tenant key |
| Quyền local quá cao | Copy external groups thành roles | Authority allowlist |
| Callback URL sai host | Forwarded headers/Host header không tin cậy | Proxy và public base URL |
| Login lại vẫn thấy IdP session | Local logout không kết thúc upstream OP session | Upstream logout metadata/flow |
| Downstream token chứa claim upstream cũ | Copy toàn bộ upstream claims hoặc customizer sai | Local claim policy và token customizer |

### 15.1. Logging và metrics

Theo dõi:

- Login attempt/success/failure theo registration ID.
- Discovery/JWKS/UserInfo latency và failure.
- State/nonce/issuer/audience validation failures.
- Identity mapping miss và JIT provisioning result.
- Account linking conflict.
- Disabled user login attempts.
- Authority mapping result.
- Upstream token refresh failures.
- Downstream token issuance success/failure.

Không log raw authorization code, ID Token, access token, refresh token, client secret hoặc session cookie. Dùng correlation ID, registration ID, issuer đã chuẩn hóa, local user ID và error category phù hợp.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** OAuth2 có tự định nghĩa chuẩn authentication user không?

**Đáp án:** Không. OAuth2 là authorization framework. OIDC bổ sung ID Token và các quy tắc authentication.

**Câu 2.** Vì sao identity key OIDC nên gồm issuer và subject?

**Đáp án:** Subject chỉ duy nhất trong phạm vi issuer/sector; hai issuer có thể phát cùng chuỗi sub cho hai người khác nhau.

**Câu 3.** state và nonce khác nhau thế nào?

**Đáp án:** state liên kết authorization response với request đang chờ; nonce liên kết ID Token với OIDC authentication request.

**Câu 4.** Có nên link account chỉ vì email giống nhau?

**Đáp án:** Không. Email có thể thay đổi, chưa verified hoặc được tái sử dụng. Cần proof và quy trình linking rõ ràng.

**Câu 5.** Spring Security dùng endpoint nào để bắt đầu upstream login?

**Đáp án:** `/oauth2/authorization/{registrationId}`.

**Câu 6.** Callback mặc định của OAuth2 Login là gì?

**Đáp án:** `/login/oauth2/code/{registrationId}`.

**Câu 7.** OIDC UserInfo có thay ID Token không?

**Đáp án:** Không. ID Token là identity assertion; UserInfo cung cấp claims bổ sung và subject phải tương ứng.

**Câu 8.** Có thể chuyển upstream ID Token thành downstream ID Token không?

**Đáp án:** Không. Authorization Server nội bộ phải phát hành ID Token của chính issuer nội bộ theo downstream client/audience.

**Câu 9.** Upstream Access Token dùng để làm gì?

**Đáp án:** Gọi resource/API thuộc upstream provider theo audience/scope của token; không mặc định dùng cho Resource Server nội bộ.

**Câu 10.** `OAuth2AuthorizedClientService` và `OAuth2AuthorizationService` khác nhau thế nào?

**Đáp án:** Service thứ nhất lưu authorized client/token upstream; service thứ hai lưu authorization/token do Authorization Server nội bộ phát hành.

**Câu 11.** Có nên copy group claim upstream thành ROLE_ADMIN?

**Đáp án:** Không. Cần mapping allowlist theo provider, tenant và policy nội bộ.

**Câu 12.** Local logout có tự kết thúc upstream IdP session không?

**Đáp án:** Không. Muốn vậy cần upstream RP-Initiated Logout nếu IdP hỗ trợ và ứng dụng cấu hình flow tương ứng.

## 17. Checklist production

- [ ] Ưu tiên OIDC cho đăng nhập liên kết khi IdP hỗ trợ.
- [ ] Provider/issuer được cấu hình và allowlist.
- [ ] Discovery/JWKS/UserInfo dùng HTTPS.
- [ ] Client ID, secret và redirect URI khớp registration tại IdP.
- [ ] Secret lưu trong secret manager, không commit hoặc gửi browser.
- [ ] Authorization Code Flow được sử dụng.
- [ ] PKCE được bật khi phù hợp và bắt buộc với public client theo policy.
- [ ] State được kiểm tra, one-time và session-bound.
- [ ] Nonce được kiểm tra trong OIDC.
- [ ] ID Token signature, iss, aud, exp và nonce được xác minh.
- [ ] UserInfo subject khớp ID Token subject.
- [ ] External identity key dùng issuer + subject.
- [ ] OAuth2-only provider có stable identifier contract và provider namespace.
- [ ] Không auto-link account chỉ dựa email.
- [ ] JIT provisioning có allowlist và tenant policy.
- [ ] Local user disabled không được login.
- [ ] External groups được mapping qua allowlist.
- [ ] Upstream Authentication được chuẩn hóa thành local principal.
- [ ] Downstream token do issuer nội bộ phát hành.
- [ ] Audience/scope của upstream và downstream tách biệt.
- [ ] Upstream authorized client token được lưu và bảo vệ đúng.
- [ ] Logout/deprovision/unlink có lifecycle policy.
- [ ] Có test cho state/nonce/issuer/audience/account linking/tenant/authority mapping.
- [ ] Không log raw token, authorization code, client secret hoặc session cookie.
- [ ] Có metrics cho upstream provider và identity mapping.

## 18. Tài liệu tham khảo và kết luận

Tài liệu chuẩn:

- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [OAuth 2.0 Security Best Current Practice — RFC 9700](https://www.rfc-editor.org/rfc/rfc9700)
- [OAuth 2.0 Authorization Framework — RFC 6749](https://www.rfc-editor.org/rfc/rfc6749)
- [OAuth 2.0 Token Exchange — RFC 8693](https://www.rfc-editor.org/rfc/rfc8693)
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [Spring Security — OAuth2 Client Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html)
- [Spring Security — OAuth2 Client Authorization Grants](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html)
- [Spring Security — OAuth2 Client Authorized Clients](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html)
- [Spring Authorization Server — Core Model](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)

**Kết luận:** Tích hợp đăng nhập từ IdP upstream biến Authorization Server nội bộ thành một OIDC/OAuth2 Client đối với hệ thống danh tính bên ngoài. Với OIDC, Spring Security thực hiện Authorization Code Flow, kiểm tra state/nonce, xác minh ID Token và tải UserInfo theo registration. Ứng dụng cần ánh xạ external identity bằng issuer và subject, provision/link local user theo policy, rồi tạo local principal và SecurityContext. Với OAuth2-only provider, phải có identity contract riêng và stable user identifier; không suy ra authentication chỉ từ access token. Sau upstream login, Authorization Server nội bộ vẫn áp dụng scope, consent, audience và policy của mình để phát hành token downstream. Khi giữ ranh giới này, nền tảng có thể liên kết nhiều IdP mà không làm lẫn danh tính, quyền hạn hoặc credential giữa các issuer.





