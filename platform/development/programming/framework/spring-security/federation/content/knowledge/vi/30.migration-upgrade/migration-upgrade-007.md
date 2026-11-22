# Chuyển ứng dụng từ CAS hoặc SAML sang OIDC thông qua môi giới danh tính

**Module:** Spring Security – federation  
**Chủ đề cha:** Chuyển đổi và nâng cấp  
**Bối cảnh:** ứng dụng Java/Spring cũ đang dùng CAS hoặc SAML2 cần chuyển sang OpenID Connect (OIDC) bằng một **identity broker**, trong khi hệ thống định danh tập trung hoặc các nhà cung cấp danh tính cũ vẫn có thể hoạt động trong giai đoạn quá độ.  
**Công nghệ minh họa:** Java 17+, Spring Boot 3.x, Spring Security 6.x, OAuth2 Login/OIDC, CAS protocol, SAML 2.0 Web Browser SSO, IdP broker như Keycloak hoặc sản phẩm tương đương. Cấu hình URL, tài khoản và chứng chỉ trong bài là **ví dụ giả**, không phải hệ thống đang chạy.

## 1. Mục tiêu của migration

Một cuộc chuyển đổi thành công không chỉ là thay CAS filter hoặc SAML2 login bằng oauth2Login(). Mục tiêu là:

1. **Ứng dụng nói OIDC với broker**, không phải tự triển khai đồng thời nhiều giao thức legacy.
2. **Broker xử lý quan hệ với CAS/SAML upstream** theo đúng adapter/trust configuration; app chỉ tin **OIDC issuer** của broker.
3. **Người dùng giữ đúng tài khoản, quyền nghiệp vụ và tenant** khi đăng nhập qua upstream cũ và qua broker mới; không auto-link nhầm bằng email.
4. **OIDC Authorization Code flow** bảo vệ state, nonce, PKCE (khi được triển khai theo client/profile), redirect URI, token signature/claims và browser session.
5. **Đăng xuất, timeout, reauthentication, MFA/LoA và revocation** có semantics rõ: không hứa rằng logout một tầng sẽ tự chấm dứt toàn bộ các phiên ở mọi tầng.
6. Có **rollout theo cohort, quan sát và rollback** mà không làm hỏng dữ liệu account linking hoặc quyền tài nguyên.
7. Có test SSO positive/negative cho cả hai phía trust boundary và giữ được bảo mật khi broker/IdP/proxy lỗi.

**Ranh giới:** Đây là migration của **authentication federation giữa web app và hệ thống IdP**. OIDC ID Token dùng để xác thực người dùng với client; nó **không** tự thay thế OAuth2 access token để bảo vệ API, và broker không tự xác định quyền business trong database.

## 2. CAS, SAML2 và OIDC khác gì?

| Thuộc tính | CAS protocol | SAML 2.0 | OIDC |
| --- | --- | --- | --- |
| Luồng web phổ biến | Browser nhận **service ticket** (ST); service xác minh qua CAS server | Browser chuyển SAMLResponse XML tới ACS | Browser chuyển **authorization code** về redirect URI; client đổi code lấy tokens |
| Chứng cứ xác thực đến ứng dụng | Kết quả xác minh ticket một lần, gắn với **service URL** | Signed Response/Assertion với Issuer, Audience, Conditions | ID Token/JWT + kết quả code flow, issuer và audience |
| Metadata/trust | CAS endpoint, TLS, registered service; ticket validation | IdP entityID, SAML metadata, trusted X.509 signing keys | OIDC Discovery issuer, JWKS, client registration/secret hoặc client auth |
| Dữ liệu user | cas:user và attributes từ validation response | NameID, AttributeStatements, AuthnContext | iss, sub, auth_time, acr/amr, profile/email/groups khi được phát |
| Principal ổn định | CAS user ID tùy deployment | NameID format + IdP entityID, có thể transient | **(iss, sub)** trong ngữ cảnh OP; pairwise sub phụ thuộc client/sector |
| Phiên tại app | App session + CAS TGC/SSO session | App session + IdP session | App session + broker OP session + upstream IdP session |
| Logout | CAS logout / Single Logout (tùy triển khai) | SAML SLO có thể front/back channel | RP-Initiated Logout, front/back-channel logout nếu OP/RP hỗ trợ |
| Vai trò | Không mặc định cấp quyền app | Attribute/Groups không mặc định là role app | Claims/scopes không tự là quyền tài nguyên |

**CAS service ticket không phải OIDC authorization code.** Không được tự đổi tên parameter ticket thành code hoặc chuyển thẳng một ticket sang API rồi coi là OAuth token. CAS ST thường chỉ dùng một lần và gắn đúng service; phải được CAS server xác minh qua kênh tin cậy.

**SAMLResponse XML không phải ID Token.** Broker cần verify SAML Issuer/chữ ký/audience/đích/thời gian/subject/replay ở phía upstream **trước khi** phát OIDC ID Token xuống ứng dụng.

**OIDC khác OAuth2 thuần:** Khi client yêu cầu scope openid và triển khai OIDC, ứng dụng mới nhận ID Token để xác thực danh tính. OAuth2 access token có audience/scope dành cho resource server; không lấy ID Token làm Bearer API credential tùy tiện.

## 3. Kiến trúc trước và sau

### Trước chuyển đổi

~~~text
                    +----------------------+
Browser ----------> | Spring Application   |
                    | CAS client filter    | ---> CAS Server /serviceValidate
                    | hoặc SAML2 ACS       | ---> SAML IdP (metadata, signing cert)
                    | business authorization|
                    +----------------------+
~~~

Ứng dụng thường có:

- CAS client filter, CAS service URL, /login CAS, /serviceValidate, possibly CAS proxy tickets.
- Hoặc Spring Security SAML2 configuration, RelyingPartyRegistration, /saml2/authenticate/{registrationId}, /login/saml2/sso/{registrationId}.
- Logic riêng chuyển CAS username/SAML NameID/groups thành user, authorities và session.
- Logout hook hoặc Single Logout endpoint của legacy protocol.
- Existing business database (users/permissions/tenant/ownership), không được mất khi thay login protocol.

### Sau chuyển đổi: broker ở giữa

~~~text
  Browser / Session
         |
         v
  Spring Boot application (OIDC Relying Party / OAuth2 Client)
         |
         | Authorization Code (+ PKCE when configured)
         | OIDC ID Token verified from broker; iss+sub
         v
  Identity Broker (downstream OIDC OpenID Provider)
         |
         +------ Upstream SAML2 SP <------ Legacy SAML IdP
         |
         +------ Supported CAS connector <-- Legacy CAS server
         |        OR upstream OIDC/SAML capability of CAS
         |
         +------ optional enterprise OIDC/Social IdPs
         |
         v
  Broker subject mapping + upstream identity links
         |
         v
  App local user ID + app DB roles/resource authorization
~~~

**Broker có hai vai trò khác nhau:**

- **Upstream:** broker là **SAML Service Provider** đối với SAML IdP, hoặc là CAS client qua connector phù hợp, hoặc là OIDC Relying Party nếu upstream CAS server cung cấp OIDC.
- **Downstream:** broker là **OpenID Provider (OP)** phát authorization code, ID Token và các tokens cho Spring application.

Không được nhầm hai cặp credentials/trust:

- SAML IdP signing certificate hoặc CAS server trust → **broker** dùng để kiểm upstream login.
- Broker OIDC issuer, client registration, JWKS, TLS → **Spring app** dùng để kiểm token do broker phát.

Nếu một SAML assertion được broker xác minh hợp lệ, Spring app vẫn cần **kiểm tra ID Token broker**; app không tin thẳng vào XML/SAML signing cert upstream khi chạy flow mới.

## 4. Lựa chọn đường chuyển đổi từ CAS

**Không mặc định mọi identity broker có sẵn CAS identity-provider adapter.** Một số sản phẩm chỉ hỗ trợ SAML/OIDC upstream theo mặc định; CAS bridge có thể là extension, custom connector hoặc khả năng phát OIDC/SAML của chính CAS server. Phải kiểm version và security support của **sản phẩm cụ thể**.

Ba phương án thường gặp:

### A. CAS server hỗ trợ OIDC hoặc SAML2 như upstream

Nếu deployment CAS có chức năng làm **OIDC Provider** hoặc **SAML2 IdP**, ưu tiên dùng protocol chuẩn mà broker đã hỗ trợ native:

~~~text
CAS Server (OIDC/SAML endpoint) --> Broker (OIDC RP / SAML SP)
                                       |
                                       v
                                Spring App (OIDC RP)
~~~

Ưu điểm: ít custom protocol adapter. Cần kiểm **thực tế endpoint/version/license/config**; việc sản phẩm CAS có khả năng cung cấp OIDC không có nghĩa deployment hiện tại đã bật hay có issuer/clients/metadata đúng.

### B. Broker hỗ trợ CAS upstream bằng connector được duy trì

~~~text
Legacy CAS Server -- service ticket --> CAS connector tại broker
                                                |
                                                v
                                        Broker OIDC OP
                                                |
                                                v
                                          Spring App
~~~

CAS connector phải:

1. Đăng ký **service URL chính xác** tại CAS.
2. Redirect login đến CAS server qua HTTPS và nhận một service ticket.
3. Validate ticket server-to-server bằng /serviceValidate (hoặc endpoint đúng protocol version).
4. Kiểm TLS/hostname, ticket validity, service binding, ticket reuse/replay và fail closed.
5. Nhận user ID/attributes từ kết quả CAS validation **đã được xác minh**, không từ query/header tự khai.
6. Tạo một upstream identity link có issuer/source ID riêng; không tự nâng cas:user thành local account khi thiếu policy.
7. Có version updates, security review, operational owner; connector cộng đồng không được coi là mặc định “đã an toàn”.

### C. Một translation service được review riêng

Khi không có native connector, có thể cần gateway/adaptor **do tổ chức chịu trách nhiệm bảo trì** để xác minh CAS ticket rồi phát claims vào broker qua trust contract được thiết kế chuẩn. Phương án này có chi phí bảo mật/vận hành cao; không triển khai bằng cách:

- Đưa CAS ST vào claim OIDC mà không validate.
- Tin header như X-User của browser.
- Đổi ST thành authorization code chỉ bằng đổi parameter name.
- Tự ký JWT rồi cho Spring app tin mà thiếu issuer/audience/key management/replay protections.

**Quyết định kiến trúc:** Nếu không có native CAS connector được hỗ trợ, **ưu tiên CAS OIDC/SAML capability hoặc broker migration path tiêu chuẩn**. Không kết luận đã chuyển thành OIDC chỉ vì frontend nhận một token tự tạo.

### CAS Proxy Ticket / PGT và delegation

Nếu ứng dụng cũ dùng **Proxy Granting Ticket (PGT)/Proxy Ticket (PT)** để thay mặt user gọi downstream CAS services, OAuth2/OIDC browser login không tự cung cấp quyền delegation giống CAS. Phải lập bảng downstream APIs và thiết kế thay thế (OAuth2 access token đúng audience/scope, token exchange nếu AS hỗ trợ chuẩn, service-to-service credentials với policy), hoặc giữ CAS proxy path trong giai đoạn riêng.

Chỉ chuyển login UI mà bỏ qua CAS proxy delegation có thể làm ứng dụng vẫn login được nhưng các nghiệp vụ nền bị hỏng.

## 5. Lựa chọn đường chuyển đổi từ SAML2

Đối với SAML IdP, phần lớn broker hỗ trợ cấu hình upstream SAML2 IdP. Broker đóng vai trò SAML SP, cần cấu hình:

- **SAML SP EntityID của broker**, ACS endpoint của broker, metadata SP nếu cần.
- **IdP entityID** expected, SSO endpoints và **IdP signing X.509 verification credentials**.
- Quy tắc signed Response/Assertion theo profile và idp contract.
- **Issuer, AudienceRestriction, Destination, Recipient, InResponseTo, NotBefore, NotOnOrAfter**, SubjectConfirmation, unique IDs và replay protection.
- XML parser hardening (no XXE, no arbitrary external entity/DTD).
- Metadata fetch chỉ từ nguồn đáng tin, key rotation/validUntil/cacheDuration/refresh policy.
- Logout capabilities nếu dùng SAML Single Logout.
- Attribute/NameID mapping với format đúng: persistent NameID hay transient NameID.

**Đừng coi NameID là tương đương OIDC sub.** Một transient NameID có thể đổi mỗi login; email cũng có thể đổi hoặc dùng chung. Broker phải tạo **broker subject ổn định riêng** và lưu mapping upstream identity (IdP entityID + persistent external subject) tới broker account.

### Sơ đồ trust của SAML→OIDC

~~~text
SAML IdP
  signed Assertion (NameID, AttributeStatement, AuthnContext)
       |
       v
Broker SAML validator
  - verify trusted IdP signing key
  - Issuer, Audience, Destination, InResponseTo, time, replay
  - select signed/validated assertion only
       |
       v
Broker account-link policy + OIDC OP
  - assign stable broker sub for downstream client
  - issue ID Token with broker iss, sub, aud, exp, nonce
       |
       v
Spring OAuth2/OIDC Login
  - validate broker issuer/JWKS/signature/claims
  - map (broker iss, sub) -> local user ID
  - enforce app authorization
~~~

**Lỗi cần chặn:** SAML Signature Wrapping (broker kiểm chữ ký Assertion A nhưng đọc attributes từ Assertion B), untrusted KeyInfo/IdP metadata, wrong issuer, mismatched ACS, replay và duplicate IDs. Broker không phải “security bypass”; nó trở thành một trust-critical service mới.

## 6. Thiết kế mô hình định danh để tránh tạo tài khoản trùng

Đây thường là phần khó nhất, không phải việc thay cấu hình SecurityFilterChain.

### 6.1. Ba lớp identity tách biệt

1. **Upstream identity:** `(source, upstreamIssuer, upstreamSubject)` — CAS username/ticket validation subject hoặc SAML IdP EntityID + NameID/persistent ID.
2. **Broker identity:** `(brokerIssuer, brokerSubject)` — broker OP phát `iss` và `sub` cho ứng dụng; một broker account có thể link nhiều upstream identities sau proof phù hợp.
3. **Local business identity:** `user_id` bất biến trong DB ứng dụng, chứa roles, tenant, orders, audit, ownership và trạng thái enabled.

Ví dụ:

~~~text
Upstream CAS:
    source=cas-prod
    issuer=https://cas.example.test/cas
    subject=E08142

Upstream SAML:
    source=saml-hr
    issuer=https://idp.example.test/metadata
    subject=persistent-9fb0

Broker:
    iss=https://broker.example.test/realms/enterprise
    sub=broker-user-73a1

Application DB:
    user_id=42
    tenant_id=acme
    role=REPORT_VIEWER
    enabled=true
~~~

Không tự suy `E08142 = persistent-9fb0 = broker-user-73a1` từ việc cùng email. Mối liên kết phải đến từ **định danh đã được xác thực và migration table đã được phê duyệt**, user reauthentication mạnh hoặc bước account linking có proof + approval.

### 6.2. Bảng dữ liệu migration minh họa

~~~sql
CREATE TABLE local_user (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(100) NOT NULL,
    enabled BOOLEAN NOT NULL,
    role_code VARCHAR(100) NOT NULL
);

CREATE TABLE identity_link (
    id BIGINT PRIMARY KEY,
    local_user_id BIGINT NOT NULL REFERENCES local_user(id),
    identity_source VARCHAR(40) NOT NULL,
    issuer VARCHAR(500) NOT NULL,
    subject VARCHAR(500) NOT NULL,
    tenant_id VARCHAR(100) NOT NULL,
    link_status VARCHAR(24) NOT NULL,
    approved_at TIMESTAMP NULL,
    UNIQUE(identity_source, issuer, subject, tenant_id)
);
~~~

**Đây là schema minh họa**, điều chỉnh VARCHAR/constraints theo DB engine. Cần ràng buộc consistency tenant với local_user và chính sách một user có nhiều identity links/identities chia sẻ account theo nghiệp vụ; migration operations phải transactional và audit. Với OIDC broker pairwise subject, `sub` có thể khác theo client hoặc sector identifier, cần kiểm tra trước khi chuyển redirect URI/client registration.

**Không dùng email, displayName, preferred_username làm khóa duy nhất liên kết** vì chúng có thể đổi, chưa được verify hoặc không unique xuyên issuers/tenants.

### 6.3. First-login / account linking policy

Một số brokers có **first broker login / account linking**. Chọn rõ:

- Với enterprise managed users, ưu tiên **pre-provisioned mappings** (IAM/HR authoritative ID) hoặc explicit verified linking.
- Chỉ tạo user mới khi đã qua onboarding policy (invitation/approved tenant, MFA/LoA nếu cần).
- Không tự link sang existing local user chỉ vì email giống nhau; phải có proof of account ownership và tenant match.
- Không gộp tài khoản giữa hai upstream issuers/tenants theo username local-part.
- Từ chối login nếu mapping ambiguous/missing mà policy yêu cầu đã migrate.
- Có audit events: LINK_APPROVED, LINK_REJECTED, LINK_CONFLICT, USER_DISABLED.
- Không xóa legacy mapping trước khi hết rollback window; không lưu raw SAMLResponse/CAS ST trong bảng link.

### 6.4. OIDC subject dạng public và pairwise

Theo OIDC, `sub` ổn định trong phạm vi issuer và có thể có dạng **public** (cùng sub cho nhiều clients) hoặc **pairwise** (sub khác theo sector identifier). Khi đổi broker/client hoặc sector identifier, `sub` có thể đổi. Vì vậy cần:

- Ghi `iss` + `sub` của **broker** thành lookup key ở downstream app.
- Tách `local_user_id` bất biến khỏi `sub`.
- Kiểm client registration/redirect URI rotation tác động pairwise subject trước cutover.
- Khi đổi broker issuer, không “sửa mọi sub tự động”, mà migrate links qua verified mapping.
- Thiết kế giai đoạn dual-read có kiểm soát: lookup cả legacy identity và broker identity **chỉ sau validation riêng từng giao thức**.
- Không cho phép client tự chỉ định issuer/JWKS URL từ request login để tránh issuer mix-up/SSRF.

## 7. Mapping claims, MFA và quyền: những khác biệt không thể bỏ qua

| Legacy source | OIDC broker claim có thể có | Quy tắc migration |
| --- | --- | --- |
| CAS validated username | `sub` broker, `preferred_username` | `sub` của broker là canonical; username chỉ hiển thị |
| CAS attributes | `email`, `name`, custom claims | Release tối thiểu, verify nguồn & mục đích |
| SAML NameID persistent | upstream link -> broker account | Không copy thẳng vào `sub` nếu không kiểm stability |
| SAML transient NameID | Không thích hợp làm key lâu dài | Cần persistent upstream ID được bảo đảm |
| SAML AttributeStatement(groups) | `groups` hoặc custom claim | Allowlist mapping, không tự cấp ROLE_ADMIN |
| SAML AuthnContext | `acr`/`amr` nếu broker map đúng semantics | Có policy đảm bảo mức assurance, không tự suy tương đương |
| CAS renew/forced login semantics | `prompt=login`, `max_age`, `auth_time` tùy OP support | Kiểm sự hỗ trợ và reauthentication thực tế |
| SAML ForceAuthn/RequestedAuthnContext | OIDC prompt/max_age/acr_values | Không giả định equivalence nếu broker không enforce |
| Legacy SLO | OIDC logout/session event | Không có 1:1, thiết kế riêng |
| CAS PT/PGT proxy delegation | OAuth2 access token/token exchange | Cần use-case/API architecture riêng |
| Local DB roles | App-issued GrantedAuthority | App vẫn là nguồn chính cho business authorization |

**Đặc biệt với MFA:** Một broker có thể có session cũ mà không biết authentication upstream mới có đủ yếu tố hay không. Nếu cần step-up, yêu cầu `acr`/`amr`/`auth_time` có semantics được broker tin cậy, thực hiện `max_age`/`prompt` hoặc upstream reauthentication theo policy; **không gán tùy tiện** `acr=mfa` chỉ vì IdP có MFA nói chung.

**Điều quan trọng:** Broker có thể phát `groups` nhưng app không nên map tất cả thành GrantedAuthority. Hãy dùng allowlist và/hoặc local DB policy, tenant isolation, account enabled, role revocation SLA. OIDC scope `openid profile email` không đồng nghĩa quyền REPORT_VIEWER/ADMIN.

## 8. Cấu hình OIDC client Spring Boot 3 / Spring Security 6

### 8.1. Maven dependencies

Trong một Spring Boot project có BOM/parent phù hợp:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
~~~

**Không cần** để lại Spring SAML2 Service Provider hoặc legacy CAS client dependency nếu app đã ngắt hoàn toàn legacy paths; trong thời gian dual-stack có thể giữ riêng theo thiết kế chain tách biệt. Không dùng Spring Security SAML Extension đời cũ như một phần bắt buộc của OIDC login mới.

### 8.2. application.yml

**src/main/resources/application.yml**

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          enterprise-broker:
            provider: enterprise-broker
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile,email
        provider:
          enterprise-broker:
            issuer-uri: https://broker.example.test/realms/enterprise

server:
  forward-headers-strategy: none
~~~

**Đây là cấu hình minh họa cho confidential server-side web client**; client-id/client-secret phải đến từ secrets manager, không commit values vào Git. Domain example.test là ví dụ, phải thay bằng issuer có OIDC Discovery hợp lệ và cấu hình client trên broker.

Một vài điểm:

- **issuer-uri** phải khớp `iss` trong ID Token; Spring OIDC client có thể dùng discovery tới .well-known/openid-configuration để lấy authorization/token/JWKS endpoints.
- `scope` phải có **openid** để dùng OIDC-specific login; thiếu openid sẽ đi theo OAuth2 UserService thay vì OIDC.
- `/oauth2/authorization/enterprise-broker` là URL mặc định để bắt đầu Authorization Code login.
- Callback mặc định `/login/oauth2/code/enterprise-broker` là redirect URI để broker trả authorization code.
- **Redirect URI phải đăng ký chính xác trên broker**; không lấy động từ untrusted Host/X-Forwarded-Host. Nếu public HTTPS URL ở sau proxy, đặt trusted base URL/forwarded headers theo threat model.
- `forward-headers-strategy: none` chỉ là mặc định thận trọng trong minh họa không dựa vào untrusted headers; **không đủ** nếu callback public URL được xây từ internal host. Khi cần NATIVE/FRAMEWORK, edge phải strip/rebuild forwarded headers và giới hạn trusted proxy list.
- Spring Security OIDC client thông thường hỗ trợ state, nonce, signature/claim validation trong configured flow; **kiểm thử phiên bản/provider cụ thể** và bổ sung PKCE theo policy.
- Ứng dụng backend confidential client cũng nên cân nhắc **PKCE S256** nếu broker hỗ trợ, nhất là khi redirect/callback có nguy cơ code injection. Không khẳng định chỉ cần `client_secret` là thay thế mọi chống code interception.

### 8.3. SecurityFilterChain tối thiểu

**src/main/java/com/example/migration/OidcSecurityConfig.java**

~~~java
package com.example.migration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcSecurityConfig {

    @Bean
    SecurityFilterChain security(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error", "/login").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Đây là **một cấu hình Spring Boot fragment**: cần main class, client registration, broker đúng và local authorities mapping. Chưa hề có enterprise broker thật tại example.test. `oauth2Login()` xác thực downstream OIDC nhưng **không tự tìm một local account/tenant/role theo database**.

**Không tự tắt CSRF** toàn ứng dụng chỉ để OIDC callback hoạt động. Browser session cookies cần session fixation protection, Secure/HttpOnly/SameSite, HTTPS và CSRF protection cho các unsafe actions. Logout POST/redirect endpoint phải tuân security policy.

### 8.4. Dùng OidcUser sau validation, không tin dữ liệu tùy ý

Ví dụ controller chỉ hiển thị **masked hoặc pseudonymous identity** sau khi Spring Security đã xác thực:

~~~java
package com.example.migration;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @GetMapping("/api/session")
    public Map<String, String> session(
            @AuthenticationPrincipal OidcUser oidcUser) {
        // Minh họa concept, không log raw tokens.
        return Map.of(
            "provider", "enterprise-broker",
            "authenticated", Boolean.toString(
                oidcUser != null));
    }
}
~~~

**Đừng viết:** lấy `oidcUser.getEmail()` để tìm đúng local account bằng email duy nhất hoặc in `getIdToken().getTokenValue()` trong log. Phần liên kết tài khoản phải dùng verified `iss + sub` cùng tenant policy, không dựa vào string email chưa được kiểm soát.

### 8.5. Tích hợp OIDC claims với local account mapping

Trong Spring Security, các điểm mở rộng gồm **OidcUserService**, `OAuth2UserService<OidcUserRequest, OidcUser>`, `GrantedAuthoritiesMapper` và success handler. Để giữ quyền nghiệp vụ:

1. Spring Security validate authorization code response/ID Token/broker issuer và lấy `OidcUser`.
2. Đọc `oidcUser.getIdToken().getIssuer()` và `oidcUser.getSubject()` **chỉ từ kết quả authentication đã validated**.
3. Lookup mapping `(broker issuer, broker sub, tenant)` đã được phê duyệt trong DB.
4. Kiểm account enabled/locked, tenant policy, approved link status, role revocation.
5. Xây authorities từ app DB/policy engine hoặc trusted claims đã allowlist, **không copy raw groups**.
6. Deny nếu missing/ambiguous link theo migration contract; không auto-create admin.
7. Tạo SecurityContext/session qua framework; đừng tự tạo authenticated token từ request parameter.
8. Trên các request tiếp theo, dùng policy cho role updates/disabled account/session revalidation.

**Fragment xử lý identity key trong callback sau validation:**

~~~java
// Fragment trong OidcUserService wrapper / login success handler.
// oidcUser là kết quả trả từ OIDC login pipeline hợp lệ.
String brokerIssuer =
    oidcUser.getIdToken().getIssuer().toString();
String brokerSub = oidcUser.getSubject();

LocalAccount local = links.findApprovedByBrokerIdentity(
    brokerIssuer, brokerSub, tenantFromTrustedPolicy);

if (local == null || !local.enabled()) {
    throw new OAuth2AuthenticationException(
        new OAuth2Error("account_link_not_approved"));
}

// Map local roles/authorities theo DB.
// Không dùng user-provided email hay X-Role header.
~~~

Đây là **fragment minh họa không tự biên dịch** vì LocalAccount/links/tenantFromTrustedPolicy và imports nằm trong project. Mục đích là chỉ ra trust boundary đúng; dùng exception type phù hợp ở đúng authentication extension hook và failure handler để client không thấy chi tiết PII. `tenantFromTrustedPolicy` phải đến từ broker-validated context hoặc cấu hình registration/local mapping, không từ query tùy ý.

### 8.6. Khi cần bảo vệ API

Spring app dùng `oauth2Login` là **web login client**. Nếu có API được gọi bằng bearer token, thêm **OAuth2 Resource Server** và xác minh **access token** có issuer, audience, signature/algorithm, exp, nbf và scopes/permissions. **ID Token không phải access token** cho API.

Không dùng một access token lấy cho broker UserInfo endpoint để gọi bất kỳ downstream API nào; audience/authorization server/scopes phải đúng target resource.

## 9. Java 17 độc lập: mô phỏng linking đúng và chặn nhầm tài khoản

Bài thực hành này không gọi CAS/SAML/OIDC thật. Nó mô phỏng **kết quả xác thực đã được verify** và ánh xạ hai external identities của cùng user sang một local user ID, đồng thời chặn email collision, wrong issuer, unknown subject và unverified input.

**Tệp: BrokerIdentityMigrationDemo.java**

~~~java
import java.util.Map;

public final class BrokerIdentityMigrationDemo {

    record ExternalIdentity(
        String source, String issuer, String subject) { }

    private static final Map<ExternalIdentity, String>
        APPROVED_LINKS = Map.of(
            new ExternalIdentity(
                "CAS", "https://cas.example.test/cas", "E08142"),
            "LOCAL-42",
            new ExternalIdentity(
                "OIDC",
                "https://broker.example.test/realms/enterprise",
                "broker-user-73a1"),
            "LOCAL-42");

    static String resolve(ExternalIdentity identity,
            boolean cryptographicallyOrProtocolVerified) {
        if (!cryptographicallyOrProtocolVerified) {
            return "DENY_UNVERIFIED";
        }
        String local = APPROVED_LINKS.get(identity);
        if (local == null) {
            return "REVIEW_OR_DENY_UNLINKED";
        }
        return local;
    }

    public static void main(String[] args) {
        ExternalIdentity oldCas = new ExternalIdentity(
            "CAS", "https://cas.example.test/cas", "E08142");
        ExternalIdentity broker = new ExternalIdentity(
            "OIDC",
            "https://broker.example.test/realms/enterprise",
            "broker-user-73a1");
        ExternalIdentity wrongIssuer = new ExternalIdentity(
            "OIDC", "https://evil.example.test",
            "broker-user-73a1");
        ExternalIdentity unknown = new ExternalIdentity(
            "OIDC",
            "https://broker.example.test/realms/enterprise",
            "another-user");

        String oldAccount = resolve(oldCas, true);
        String newAccount = resolve(broker, true);
        System.out.println("legacy=" + oldAccount);
        System.out.println("broker=" + newAccount);
        System.out.println("sameAccount=" +
            oldAccount.equals(newAccount));
        System.out.println("wrongIssuer=" +
            resolve(wrongIssuer, true));
        System.out.println("unknownSubject=" +
            resolve(unknown, true));
        System.out.println("unverifiedToken=" +
            resolve(broker, false));
        System.out.println("emailAutoLink=false");
    }
}
~~~

Biên dịch/chạy bằng **JDK 17**:

~~~bash
javac BrokerIdentityMigrationDemo.java
java BrokerIdentityMigrationDemo
~~~

**Stdout xác định:**

~~~text
legacy=LOCAL-42
broker=LOCAL-42
sameAccount=true
wrongIssuer=REVIEW_OR_DENY_UNLINKED
unknownSubject=REVIEW_OR_DENY_UNLINKED
unverifiedToken=DENY_UNVERIFIED
emailAutoLink=false
~~~

**Điều bài này chứng minh:** hai identities **đã được phê duyệt liên kết** trả về cùng local ID. Wrong issuer/unknown subject không vô tình map sang cùng user. Cờ verified trong demo chỉ là dữ liệu do test harness cung cấp, **không phải** cơ chế xác thực SAML/IDO/CAS; tuyệt đối không để HTTP request tự truyền `verified=true`.

**Điều nó không chứng minh:** verify SAML XML Signature, CAS ST, OIDC JWT/JWKS, TLS, nonce/state/PKCE, broker session hay authorization. Hãy để thư viện chính thức xử lý protocol, rồi áp lookup approved links này lên **kết quả đã validate**, với tenant và account status thật trong DB.

## 10. Migration theo từng giai đoạn, không big-bang

### Giai đoạn 0 – Inventory hiện trạng

Lập danh sách chính xác:

- Mỗi ứng dụng đang dùng **CAS client**, Spring Security SAML2, Spring Security SAML Extension cũ hay custom SAML code?
- CAS server version/protocol, ticket validation endpoint và `service` URL.
- Có dùng CAS **Proxy Granting Ticket/Proxy Ticket** để gọi downstream không?
- SAML IdP entityID, signing certificate, metadata, NameID format, signature policy, ACS/SLO endpoints.
- Danh sách clients, redirects, proxy/ingress Host/Proto, cookie domain, CSP/CORS/SameSite.
- User mapping cũ: username/email/NameID → user_id, roles, disabled/locked status, tenant.
- Session/logout/revocation SLA và MFA/step-up requirements.
- Service accounts, batch jobs/API calls có phụ thuộc CAS/SAML user session không?
- Recovery/rollback owner, support desk, production observability.

**Đầu ra:** migration matrix theo ứng dụng, broker upstream adapter readiness, user link quality, risk và cutover plan. Không triển khai để “OIDC chạy” trước khi biết các đường auth/delegation hiện có.

### Giai đoạn 1 – Chuẩn bị broker và trust

1. Chọn broker/version hỗ trợ OIDC OP ổn định, HA/backup/recovery, audit và key rotation.
2. Với SAML upstream: đăng ký broker SAML SP ở IdP, import metadata/trusted signing keys, kiểm issuer, audience, ACS và SLO policy.
3. Với CAS upstream: chọn **CAS OIDC/SAML upstream** hoặc connector CAS được hỗ trợ/đã review; validate service ticket server-side.
4. Khai báo broker realm/tenant, OIDC issuer URL ổn định, JWKS, signing algorithm policy, signing key lifecycle.
5. Tạo OIDC confidential client cho Spring app; register exact redirect URIs và post-logout redirect URIs nếu hỗ trợ.
6. Cấu hình HTTPS/TLS, proxy trust, egress, time sync, rate limits, secrets storage.
7. Định nghĩa broker identity linking, claims release, MFA/acr/amr semantics, session lifetimes.
8. Tạo test identity/tenant riêng; không dùng secret/key thật trong ví dụ hoặc CI.

**Acceptance:** broker có thể xác thực một user test qua upstream và phát một ID Token hợp lệ với **broker iss**, **stable sub**, **aud=app client**, exp/iat và nonce nếu yêu cầu.

### Giai đoạn 2 – Ánh xạ danh tính và quyền

- Export danh sách legacy identities **theo quy trình bảo mật**, không export credential/tickets.
- Tạo `identity_link` table/mapping approved theo issuer+subject+tenant và local ID.
- Tách số lượng matched, unmatched, conflicting, transient NameID và email collisions.
- Với user trùng email ở nhiều issuers, **không tự merge**; yêu cầu verified linking/approval.
- Đối chiếu local roles/permissions cho từng user; không để broker group phát ROLE_ADMIN ngoài allowlist.
- Test disabled account và tenant isolation.
- Đảm bảo same user giữ ownership/history trong DB; không thay `user_id`.
- Lưu link evidence/approved version và rollout flags cho rollback.

**Acceptance:** cùng user legacy và broker login cho ra **một local user ID**, không tạo bản ghi mới/cấp quyền mới trái policy.

### Giai đoạn 3 – Dual-stack có kiểm soát

Có thể hỗ trợ CAS/SAML và OIDC song song trong một cửa sổ ngắn hoặc bằng blue-green deployment; chỉ khi có thiết kế rõ:

~~~text
Cohort old: browser -> CAS/SAML legacy chain
Cohort new: browser -> OIDC broker chain
Both: validated identity -> approved link -> same local user ID
~~~

**Đừng** cho một request không kiểm chứng chọn chain hay tự switch auth mechanism bằng query/header. Với nhiều SecurityFilterChain, dùng `@Order`, securityMatcher cụ thể, callback routes không trùng nhau, default deny fallback chain, và test từng filter invocation. Một phương án đơn giản hơn là **tách deployments/hostnames** theo cohort, giảm nguy cơ kết hợp sai filters.

Trong dual-stack:

- Session keys/namespace của hai flows tách biệt hoặc có kế hoạch chuyển session.
- Không mặc định nâng CAS session thành OIDC session mà chưa thực hiện broker login.
- Mỗi protocol validation độc lập, không accept raw header NameID/CAS username.
- Có feature flag server-side và rollback route, ghi rõ cohort.
- Mặc định không gửi email hoặc ID Token/JWT trong logs.
- Không gửi callback OIDC tới SAML ACS hoặc ngược lại.

### Giai đoạn 4 – Canary, đo đạc và cutover

Chuyển một cohort nhỏ trước, sau đó tăng dần theo khả năng rollback:

1. Test users và ít ứng dụng không quan trọng.
2. Một tenant/phòng ban được phê duyệt.
3. Tăng số clients/user cohorts sau khi có KPI.
4. Chốt freeze/maintenance window nếu cần.
5. Chuyển default login route sang broker OIDC, giữ legacy endpoint trong deprecation window chỉ theo policy.
6. Tắt legacy auth tại ứng dụng sau khi không còn traffic và đã xử lý downstream proxy use cases.

**KPI không chỉ là login success:**

- Authorization Code callback success/failure, invalid state/nonce/issuer/audience.
- Broker upstream SAML signature/CAS ticket failures và latency.
- Unlinked/ambiguous user count, newly created local accounts, duplicate account incidents.
- Denied admin/tenant requests, role mismatch, account disabled propagation.
- Browser SSO repeat login rate và logout/session anomalies.
- End-to-end p95/p99 latency, broker HA/availability, login loop rate.
- Refresh token lifetime/access-token use nếu có API calls.
- Audit privacy: không raw tokens/NameID/SAMLResponse trong logs.

### Giai đoạn 5 – Hạ legacy và làm sạch

- Gỡ CAS/SAML endpoints/clients khỏi app khi chắc không còn phụ thuộc.
- Thu hồi unused SP signing/decryption keys, CAS service registrations, SAML metadata/cert và secrets theo change control.
- Đóng inbound callbacks cũ hoặc route tới thông báo migration không làm authentication.
- Giữ mappings/audit records theo retention policy, không xóa user business records.
- Cập nhật runbooks, on-call, alert rules, support desk docs và incident response.
- Xác nhận không còn dependency cũ/unsupported library trên classpath.
- Truyền thông re-login và logout UX để user không bị vòng lặp khó hiểu.

## 11. Logout, session và reauthentication: cần một contract mới

Sau migration có ít nhất **ba phiên**:

~~~text
[1] Local HttpSession at Spring app
[2] OIDC broker OP browser session
[3] Upstream CAS TGC session or SAML IdP session
~~~

Một thao tác Spring session.invalidate() chỉ chắc chắn kết thúc **[1]**, không mặc định kết thúc [2]/[3]. Broker logout có thể hết [2], nhưng upstream SSO [3] vẫn còn nên lần login sau có thể tự đăng nhập lại. CAS SLO, SAML SLO và OIDC RP-Initiated Logout **không có semantics đồng nhất**.

### Chính sách logout đề xuất

1. Định nghĩa **local logout**, **broker logout**, và **upstream IdP logout** riêng.
2. Nếu OIDC broker hỗ trợ RP-Initiated Logout và có end_session_endpoint, Spring có thể dùng `OidcClientInitiatedLogoutSuccessHandler` với ClientRegistrationRepository; cấu hình đúng post_logout_redirect_uri/ID Token hint theo broker.
3. Kiểm support của broker với front-channel/back-channel logout, session IDs, upstream propagation; không mặc định tất cả IdPs triển khai SLO.
4. CSRF protection cho logout, SameSite/Secure/HttpOnly cookies và return URL allowlist.
5. Có session idle/absolute timeout, policy re-login, step-up MFA, revoked/disabled account handling.
6. Test trường hợp IdP upstream session còn hoạt động sau broker logout; UX nên giải thích nếu cần “sign out everywhere”.
7. Nếu migration chuyển từ stateful SAML/CAS session sang OIDC, đừng tự sao chép SecurityContext sang phiên mới mà bỏ qua OIDC validation.

**Không có phép chuyển đổi tự động** từ CAS logout token/SAML LogoutRequest thành OIDC logout event mà không có broker adapter và session/link state phù hợp.

## 12. Tránh các lỗ hổng khi chuyển giao thức

| Threat | Sai lầm trong migration | Kiểm soát |
| --- | --- | --- |
| Issuer confusion | App tin `iss` do request tự khai, chọn JWKS động | Issuer allowlist cố định, verify discovery/JWKS và claim issuer |
| ID Token signature invalid | Decode JWT payload bằng Base64 rồi tin | Spring OIDC validation/JWK trust, alg allowlist |
| Wrong audience | ID Token cho client A dùng ở client B | Validate aud và azp khi cần theo OIDC semantics |
| Replay/CSRF login | Thiếu state/nonce/session binding | State/nonce, exact callback, session integrity |
| Authorization code interception | Không có PKCE dù client/profile yêu cầu | PKCE S256 được broker/client hỗ trợ, HTTPS, exact redirect |
| Open redirect | Redirect URI từ Host/Forwarded bất kỳ | Registered exact URLs, trusted proxy config |
| Account takeover | Auto-link theo email trùng | Approved issuer+subject identity linking |
| Privilege escalation | Raw broker groups tự thành ROLE_ADMIN | Local authority policy/allowlist, tenant checks |
| SAML wrapping | Broker verify Assertion A nhưng đọc B | OpenSAML validator dùng đúng signed/validated node |
| CAS ST replay | Validate cùng service ticket nhiều lần hoặc không bind service | CAS server validation one-time + service matching |
| Metadata SSRF | Broker load SAML metadata URL do user nhập | Admin allowlist, egress, TLS, trusted metadata |
| Key rotation abuse | Trust mọi KeyInfo/JWKS URL được payload yêu cầu | Trusted metadata/JWKS, controlled rotation |
| MFA downgrade | `acr=mfa` tự gán dù upstream không đạt | Verified LoA mapping và reauth policy |
| Token leakage | Log code/token/cookie/SAMLResponse | Redacted logging, secrets protection |
| Session confusion | Legacy session tự được dùng qua OIDC | Separate verified flows, explicit session migration |
| Logout gap | Chỉ clear app session rồi coi global SSO ended | Contract từng layer, test upstream persistence |
| Gateway failure | Khi broker unavailable chuyển sang anonymous/legacy header | Fail closed; controlled rollback deployment |
| API misuse | Dùng ID Token như access token | Resource Server và đúng audience/scopes |

**Một identity broker tập trung cũng là high-value target.** Cần HA, backup/restore, DR, MFA cho admin, secret/key rotation, least privilege, audit log, rate limit và incident playbook. Broker bị compromise có thể phát tokens tin cậy cho nhiều apps; kiểm soát vận hành là một phần của security architecture.

## 13. Kiểm thử E2E cho CAS→OIDC và SAML→OIDC

Mỗi test SSO cần **positive baseline** và assertions tại cả broker và app, không chỉ thấy HTTP 302 hoặc 200.

| # | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| 1 | CAS legacy login hợp lệ qua service ticket | Legacy path vẫn đúng trước cutover |
| 2 | SAML legacy Response ký hợp lệ | Legacy path đúng trước cutover |
| 3 | Broker xác thực upstream CAS (connector được hỗ trợ) | Ticket validated, broker session tạo |
| 4 | Broker xác thực upstream SAML | Signed Assertion trusted, correct issuer/audience/time |
| 5 | OIDC Authorization Code broker → Spring | ID Token valid, authenticated session |
| 6 | Legacy và broker identity cùng user | **Cùng local user_id**, giữ dữ liệu |
| 7 | Unmatched broker sub | Review/deny, không auto-link theo email |
| 8 | Email giống nhau từ hai IdPs | Không merge trái policy |
| 9 | Wrong broker issuer | App reject |
| 10 | Wrong ID Token audience | App reject |
| 11 | Expired ID Token | App reject |
| 12 | Invalid JWS/signature | App reject |
| 13 | Unknown/untrusted JWKS key | App reject |
| 14 | Invalid state hoặc nonce | Reject callback/login |
| 15 | Callback redirect_uri khác registered URL | Broker reject |
| 16 | Code replay/duplicate callback | Không tạo phiên khác |
| 17 | PKCE verifier sai khi flow yêu cầu | Token exchange reject |
| 18 | Client secret sai/expired | Token endpoint deny |
| 19 | CAS ticket reused | CAS validation deny |
| 20 | CAS ticket cho service URL khác | CAS validation deny |
| 21 | SAML Issuer/signing cert không tin | Broker deny |
| 22 | SAML Assertion expired | Broker deny |
| 23 | SAML InResponseTo/Audience sai | Broker deny |
| 24 | SAML XML Signature Wrapping | Broker không dùng unsigned assertion |
| 25 | NameID transient đổi giữa logins | Không tạo duplicate account |
| 26 | Pairwise sub đổi do client/sector changes | Migration link review, không tự link email |
| 27 | Local account disabled | Deny business access dù OIDC valid |
| 28 | Group từ broker xin admin trái policy | Không thành ROLE_ADMIN |
| 29 | Tenant A truy cập object tenant B | 403/deny |
| 30 | MFA/LoA không đạt required acr | Step-up/deny |
| 31 | CAS/SAML upstream session hết hạn | Broker reauth theo policy |
| 32 | Spring app logout | Local session ended |
| 33 | Broker OIDC logout | Broker session policy đúng |
| 34 | Upstream CAS/SAML session vẫn còn | UX/re-login hành vi đúng contract |
| 35 | Logout CSRF/open redirect attempt | Bị chặn |
| 36 | Broker unavailable | Fail closed, no auth bypass |
| 37 | Broker key rotation | Old/new keys theo cửa sổ trust |
| 38 | Header X-Forwarded-Host giả | Không thay redirect_uri/issuer |
| 39 | Error response/logging | Không leak tokens/assertions/PII |
| 40 | Blue-green rollback | Legacy login phục hồi, DB/user_id không đổi |
| 41 | Simultaneous legacy and OIDC session | Không identity/session mix-up |
| 42 | CAS PGT/proxy downstream use case | Được thay thế/duy trì có chủ đích |
| 43 | App/API ID Token misuse | Resource server reject ID Token không dành cho API |
| 44 | Broker subject/account link duplicate | Unique constraint/approval policy deny |
| 45 | New broker signing key unapproved | Controlled trust policy, no fail-open |

**Không tính PASS khi chỉ có 500/redirect loop.** Ví dụ wrong issuer test phải giữ các tham số còn lại hợp lệ, signature valid nếu đang test issuer logic. Untrusted key test phải chứng minh token ký hợp lệ bằng key ngoài trust list, còn app vẫn reject. Dùng fresh state, nonce, assertion/request IDs và session riêng.

### Kiểm thử liên kết danh tính trong migration

1. Seed một local user có orders/roles cố định.
2. Login legacy CAS/SAML bằng test account có upstream identity verified.
3. Login broker OIDC từ một browser session mới bằng cùng người.
4. Assert local_user_id bất biến; records/tenant không đổi.
5. Test another upstream issuer/email collision, ensure no auto merge.
6. Disable local account và login lại; policy deny dù broker ID Token hợp lệ.
7. Đổi roles trong local DB, test authorization thay đổi theo revocation/session SLA.
8. Nếu rollback, dùng lại legacy path và assert vẫn cùng local ID.

### Kiểm thử protocol isolation

~~~text
Legacy SAMLResponse POST -> chỉ SAML ACS ở legacy path
CAS ticket -> chỉ được validate bởi CAS client/broker adapter
OIDC code -> chỉ /login/oauth2/code/{registrationId}
OIDC ID Token -> validated by RP, không lấy từ request tự khai
API access token -> Resource Server with audience/scopes
~~~

Không cấu hình `/login/**` blanket permit trong một security chain khác để callback đi thẳng vào business endpoint. Khi triển khai nhiều chains, đặt matching/ordering rõ và thêm negative tests cho mọi alternate route.

## 14. Observability và xử lý sự cố migration

**Log sự kiện an toàn:**

- `BROKER_UPSTREAM_AUTH_FAILED` với source alias và reason enum.
- `OIDC_TOKEN_VALIDATION_FAILED` với broker alias và category (ISSUER, AUDIENCE, SIGNATURE, EXPIRY).
- `ACCOUNT_LINK_NOT_FOUND`, `ACCOUNT_LINK_CONFLICT`, `ACCOUNT_LINK_APPROVED`.
- `LOCAL_USER_DISABLED`, `TENANT_AUTHORIZATION_DENIED`.
- `SSO_LOGIN_SUCCESS`, `LOGIN_LOOP_DETECTED`, `BROKER_UNAVAILABLE`.
- `LOGOUT_LOCAL_SUCCESS`, `BROKER_LOGOUT_STARTED`, `UPSTREAM_LOGOUT_UNSUPPORTED`.

Không log CAS ST, SAMLResponse, Authorization Code, ID/access/refresh tokens, cookies, NameID/attributes raw, secret/client credentials. Dùng generated trace ID và optional pseudonymous userTag **chỉ sau validation**.

**Troubleshooting table:**

| Triệu chứng | Nguyên nhân khả dĩ | Điều nên kiểm |
| --- | --- | --- |
| Login CAS upstream fail | Wrong service URL/ticket validator/TLS | Registered CAS service, ticket one-time, HTTPS |
| SAML broker login fail | Cert/issuer/audience/destination mismatch | IdP metadata/trust anchors, SAML logs đã sanitize |
| OIDC broker login loop | Redirect URI, issuer, proxy host, SameSite/session state | Public URLs, exact callback, cookie/CSRF |
| “Invalid state” | Browser session lost/callback mismatch | OAuth2AuthorizationRequestRepository, cookie domain |
| “Invalid nonce” | State/nonce not matched hoặc token khác | Request correlation, broker token response |
| User bị duplicate | Linking theo email/transient NameID | Stable upstream key → broker key → local user |
| User không còn role | Groups changed hoặc app roles chưa map | Local DB/policy mapping, claim contract |
| MFA bị lặp | acr/amr/reauth translation sai | Broker upstream LoA map, auth_time/max_age |
| Logout rồi vào lại tự login | Upstream IdP session vẫn active | Layered logout policy, UX |
| API 401 sau login | Dùng ID Token thay access token | Resource server audience/scope validation |
| Broker down làm toàn bộ login down | Dependency mới không có HA | Multi-node/DR/health checks, fail closed |
| Chuyển issuer khiến user không tìm thấy | iss+sub đã đổi | Approved mapping/rollback, không email auto-link |

## 15. Checklist production trước khi kết thúc migration

- [ ] Inventory đầy đủ CAS, SAML2, proxy tickets, SLO, keytab/metadata, application sessions và API dependencies.
- [ ] Chọn upstream broker connector **thực sự có hỗ trợ**: CAS qua CAS adapter, hoặc CAS cung cấp OIDC/SAML; SAML qua SP trust rõ.
- [ ] Broker upstream SAML verify signature, Issuer, Audience, Destination, InResponseTo, time, replay, signed node và XML parser safety.
- [ ] Broker upstream CAS validate one-time service ticket với registered service URL qua HTTPS, không tin browser raw username.
- [ ] Broker downstream OIDC issuer/JWKS/clients/redirect URIs/PKCE/state/nonce/keys/secret storage đúng policy.
- [ ] Spring Boot chỉ tin OIDC ID Token của broker qua configured issuer, không tin raw JWT/KeyInfo/JWKS URL do browser chỉ.
- [ ] Giữ `user_id` business bất biến; approved identity_link theo broker iss+sub và tenant.
- [ ] CAS username, SAML NameID, email, preferred_username **không** được tự dùng làm key global/auto-link.
- [ ] Pairwise/public sub behavior và broker/client/sector migrations đã được đánh giá.
- [ ] Mapped groups/acr/amr chỉ qua verified/allowlisted claims, application roles vẫn từ DB/policy.
- [ ] Disabled/locked local user và tenant/resource authorization deny đúng.
- [ ] Access token dành cho API có audience/scopes phù hợp; không gửi ID Token làm API Bearer.
- [ ] OIDC callback/exact redirect URI, proxy Host/Proto, session SameSite, CSRF và logout đã test.
- [ ] CAS/SAML/OIDC session/logout/SLO semantics có contract riêng, không hứa global logout không hỗ trợ.
- [ ] CAS PGT/proxy delegated calls được thay thế bằng cơ chế được phép hoặc giữ có chủ đích.
- [ ] Có positive baseline và isolated negative tests signature/issuer/audience/state/nonce/code replay.
- [ ] Có E2E mapping test: login legacy và broker ra cùng local user ID, không duplicate.
- [ ] Có canary/blue-green/dual-stack cohort control và rollback không làm hỏng user mapping.
- [ ] Broker có HA, backup, recovery, audit, admin MFA, key rotation, alert và DR test.
- [ ] Logging, APM, proxy và SIEM không chứa SAMLResponse, CAS ST, JWT, cookies, NameID hay secrets.
- [ ] Thư viện CAS/SAML cũ đã được loại khỏi classpath và callback URLs đã đóng sau deprecation window.
- [ ] Security review/QA/operation owners ký duyệt trước khi tắt legacy flow.

**Kết luận:** Identity broker giúp **đưa CAS hoặc SAML vào phía upstream**, trong khi Spring app chuyển dần sang **OIDC chuẩn ở phía downstream**. Giá trị lớn nhất là tách ứng dụng khỏi giao thức legacy; rủi ro lớn nhất là **mất ranh giới tin cậy và liên kết nhầm tài khoản**. Luôn verify từng protocol ở đúng hop, giữ `local_user_id` bất biến, dùng `(broker iss, sub)` sau validation, kiểm local roles/tenant, thiết kế logout riêng và rollout có thể rollback. Không tự động tin email, raw headers, ticket, SAML NameID hay ID Token chưa được framework xác minh.

## 16. Tài liệu tham khảo

- [Spring Security – OAuth2 Client / OIDC Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): Authorization Code, OAuth2 Login và OIDC integration.
- [Spring Security – Core OAuth2 Login Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): ClientRegistration, issuer-uri, redirect-uri, scopes.
- [Spring Security – Advanced OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): OidcUserService, authorities, token endpoint configuration.
- [Spring Security – OIDC Logout](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html): OidcClientInitiatedLogoutSuccessHandler và post-logout redirect.
- [Keycloak Server Administration – Identity Brokering](https://www.keycloak.org/docs/latest/server_admin/): upstream IdPs, brokered identities và first-login account linking.
- [Apereo CAS – Protocol Overview](https://apereo.github.io/cas/development/protocol/Protocol-Overview.html): service tickets, CAS, SAML2 và OIDC support theo deployment.
- [Apereo CAS – CAS Protocol Specification](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html): ST one-time validation và service binding.
- [OASIS SAML 2.0 Technical Overview / Core](https://docs.oasis-open.org/security/saml/v2.0/): SAML Assertions, Bindings, Profiles, Metadata.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, iss/sub/aud/nonce, public/pairwise subjects và authentication.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): OP issuer và metadata.
- [RFC 7636 – Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636): PKCE S256.
- [OAuth 2.0 Security Best Current Practice (RFC 9700)](https://www.rfc-editor.org/rfc/rfc9700): redirect, token flow và OAuth security recommendations.
- [OWASP OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): OAuth/OIDC client security.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default và resource authorization.