# Kiểm thử truy cập chéo IdP hoặc tenant và va chạm định danh trong SSO

## 1. Vấn đề: hai người có thể mang cùng một username nhưng không phải cùng một tài khoản

Một ứng dụng Spring Boot hỗ trợ **Single Sign-On (SSO)** cho nhiều doanh nghiệp, chi nhánh, đối tác hoặc nhiều **Identity Provider (IdP)**. Ví dụ:
- Công ty A dùng OIDC issuer `https://idp-a.example.org`.
- Công ty B dùng OIDC issuer `https://idp-b.example.org`.
- Đối tác C dùng SAML IdP entityID `https://saml-c.example.org/metadata`.
- Mỗi công ty là một **tenant** trong cùng ứng dụng.

Hai người hoàn toàn khác nhau có thể cùng có:
- Username `alex`.
- Email `shared-address@example.org`.
- OIDC `sub=12345` dưới **hai issuer khác nhau**.
- SAML `NameID=alex` nhưng IdP entityID khác.
- Nhóm `Admins` hoặc `Finance` ở hai directory độc lập.

Nếu ứng dụng gắn mọi người vào account bằng email, username hoặc `sub` **không kèm issuer**, người đăng nhập từ IdP B có thể trở thành account của A. Nếu ứng dụng chỉ kiểm `ROLE_ADMIN` nhưng không kiểm tenant/resource ownership, admin công ty A có thể truy cập dữ liệu công ty B.

Bài Knowledge này thuộc **Spring Security - federation → Kiểm thử SSO**, chủ đề **“Kiểm thử truy cập chéo IdP hoặc tenant và va chạm định danh”**.

> **Nguyên tắc:** xác thực đúng IdP chưa đủ; sau đó phải liên kết đúng *external identity → app account → tenant membership → quyền trên tài nguyên*. Các đối tượng có cùng chuỗi tên không được tự động hợp nhất.

### Mục tiêu học tập

Sau bài, bạn có thể:
1. Phân biệt **IdP**, **issuer/entityID**, **client/registrationId**, **tenant**, **app-local account** và **resource owner**.
2. Xây định danh OIDC theo cặp **`(iss, sub)`**, không dùng email hoặc `sub` đơn lẻ.
3. Xây binding SAML theo issuer và subject identifier có định dạng/qualifier phù hợp; tránh transient NameID.
4. Kiểm tra trust isolation ở OIDC/SAML, CAS, Kerberos/SPNEGO và proxy pre-auth khi cần.
5. Lập các negative tests cho wrong IdP signer/issuer, wrong OIDC audience, callback mix-up, IdP confusion, nhóm tên trùng và tenant parameter tampering.
6. Thử xung đột email/username/NameID, account linking, JIT provisioning và mời người dùng.
7. Phân biệt **authentication failure** với **authorization failure**; test ở cả hai tầng.
8. Xử lý phiên đăng nhập nhiều tab/nhiều IdP, thay đổi tenant trong UI và account switch.
9. Dùng Spring Security OIDC/SAML configurations đúng ranh giới tin cậy và đối chiếu APIs theo phiên bản.
10. Chạy demo Java 17 độc lập về scoped identity và tenant authorization.
11. Đánh giá cross-tenant leaks ở repository, API, cache, background jobs và file downloads.
12. Xây ma trận QA có bằng chứng cho cả điều kiện bị chặn và đường hợp lệ.

**Bối cảnh minh họa:** Java 17+, Spring Boot 3.x, Spring Security Servlet 6.x/7.x; tenant data isolation có thể là shared database, separate schema hoặc separate database. Tài liệu dùng domain `example.org` và dữ liệu giả; không copy key/token sản xuất vào test.

---

## 2. Phân biệt IdP, tenant và account

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| IdP / OpenID Provider | `https://idp-a.example.org` | Bên xác thực, phát ID Token/SAML Assertion |
| OIDC issuer (`iss`) | `https://idp-a.example.org` | Namespace và source tin cậy của OIDC subject |
| OIDC subject (`sub`) | `12345` | Người dùng trong issuer đó, không unique toàn cầu |
| OIDC clientId/registrationId | `portal-a-client`, `corp-a` | App/client và Spring registration; **không** phải tenant user identity |
| SAML IdP entityID | `https://saml-c.example.org/metadata` | Asserting party được đăng ký |
| SAML NameID | `alex` | Subject identifier theo format/qualifier của IdP |
| App account ID | `acct-abc-01` | Khóa nội bộ bất biến cho quyền sở hữu và audit |
| Tenant ID | `tenant-a` | Biên phân quyền và tài nguyên trong ứng dụng |
| Membership | `acct-abc-01 ∈ tenant-a` | Quyền tham gia tenant, không do user tự tuyên bố |
| Resource owner | `document-007 belongs to tenant-b` | Dữ liệu cần ACL/tenant check riêng |
| Login session | `JSESSIONID` phía browser | Trạng thái login ứng dụng, không tự có quyền vào tenant khác |

**IdP và tenant không nhất thiết tương ứng một-một.** Một IdP doanh nghiệp có thể xác thực users thuộc nhiều tenants của ứng dụng. Một tenant có thể chấp nhận nhiều IdPs theo migration hoặc liên minh. Do vậy:
- Không mặc định `issuer = tenant`.
- Không mặc định `clientRegistrationId = tenantId`.
- Không tự lấy email domain `@company.com` làm tenant authorization.
- Có bảng chính sách **tenant nào tin issuer/registration nào** và **user nào có membership tại tenant đó**.
- Quyền trên tài nguyên phải được kiểm **ngay tại resource boundary**.

### OIDC scope

OpenID Connect Core quy định `sub` unique và không tái cấp trong issuer; **cặp `iss+sub`** là định danh ổn định mà Relying Party có thể dựa vào. Những claim như `email`, `preferred_username`, `name` không được bảo đảm ổn định/duy nhất giữa issuers hoặc qua thời gian.

Ví dụ:

~~~text
(https://idp-a.example.org, sub=12345) -> acct-A
(https://idp-b.example.org, sub=12345) -> acct-B

acct-A != acct-B
~~~

Nếu chỉ query `WHERE sub = '12345'`, kết quả có thể gộp nhầm hai người.

### SAML scope

SAML2 `NameID` phải được hiểu cùng:
- Asserting Party / Response và Assertion `Issuer`;
- `NameID Format` (persistent, transient, emailAddress, unspecified...);
- `NameQualifier/SPNameQualifier` nếu profile sử dụng;
- Quan hệ IdP–SP/RelyingPartyRegistration;
- Trust certificate/metadata phù hợp.

SAML transient NameID không phải một khóa tài khoản dài hạn. Persistent NameID có thể được thiết kế cho quan hệ IdP–SP cụ thể, không phải định danh toàn cầu giữa mọi IdPs/SPs.

## 3. Hai tầng lỗi khác nhau: sai identity và sai permission

Một kịch bản cross-tenant có hai thời điểm từ chối:

**AuthN / federation:** IdP B cố đưa SAML Response vào registration IdP A hoặc OIDC code/token cho client A. Provider phải từ chối khi issuer, signature, trust, audience, recipient, state/nonce hoặc binding sai.

**AuthZ / application:** IdP B xác thực **hoàn toàn hợp lệ** cho người dùng B; người này sau đó yêu cầu `/tenants/tenant-a/reports/42` dù chỉ có membership tại tenant B. Ở đây phải từ chối vì **tenant/resource authorization**, không phải vì chữ ký IdP B sai.

| Đầu vào | AuthN | AuthZ | Kết quả |
| --- | --- | --- | --- |
| User A từ IdP A, báo cáo tenant A, có quyền | Pass | Pass | Allow |
| Token IdP B đưa vào đường xác thực IdP A | Fail | Không đến business | Deny |
| User B từ IdP B, báo cáo tenant A | Pass | Fail | Deny |
| User B có email giống A | Pass cho B | B không có grant tenant A | Deny |
| User A là Admin tenant A, báo cáo tenant B | Pass | Fail | Deny |
| Unknown IdP tự phát claim issuer giống A nhưng ký key lạ | Fail cryptographic trust | Không đến business | Deny |
| User thuộc cả A và B với membership đúng | Pass | Tùy grant trên tenant được chọn | Allow có kiểm soát |
| User A dùng session cũ sau khi bị rút membership | Có thể session còn | Phải refresh/revoke | Deny |

**Không tạo test sai lớp:** nếu muốn kiểm **resource isolation**, cho user B đăng nhập hợp lệ rồi mới gọi resource A. Nếu chỉ gửi token sai chữ ký, test fail ở AuthN và **không chứng minh** repository/controller có tenant ACL.

---

## 4. Luồng login và truy cập tài nguyên được kiểm hai lần

~~~mermaid
sequenceDiagram
    participant U as Browser
    participant SP as Spring SP
    participant IDP as Selected IdP
    participant DB as Identity and membership store
    participant API as Business resource
    U->>SP: Chọn SSO cho tenant B
    SP->>SP: Chỉ chọn registration/IdP được tenant B tin
    SP->>IDP: OIDC auth request hoặc SAML AuthnRequest
    IDP-->>SP: Token hoặc signed SAML Response
    SP->>SP: Verify issuer, signer, audience, state, timing...
    alt Protocol invalid
        SP-->>U: Authentication failure
    else Protocol valid
        SP->>DB: Resolve scoped external identity -> account
        DB-->>SP: Account B và tenant memberships
        SP->>SP: Create local Authentication/session
        U->>API: GET /tenants/tenant-A/documents/42
        API->>DB: Check account B membership and resource tenant
        alt No permission in tenant A
            API-->>U: 403 or deny by app policy
        else Proper A membership and resource grant
            API-->>U: Authorized response
        end
    end
~~~

Một registration route như `/oauth2/authorization/corp-b` hoặc `/saml2/authenticate/corp-b` chỉ xác định cách **bắt đầu** đăng nhập. Nó không được xem là bằng chứng tenant ownership. Request parameter `?tenant=tenant-a`, host header, vanity domain, redirect URL hoặc giá trị trong `RelayState` cũng không tự cấp membership.

## 5. Mô hình data tối thiểu chống va chạm định danh

### 5.1 Tách external identity khỏi account

~~~sql
CREATE TABLE app_accounts (
    account_id UUID PRIMARY KEY,
    status VARCHAR(24) NOT NULL,
    security_epoch BIGINT NOT NULL DEFAULT 1
);

CREATE TABLE external_identities (
    identity_id UUID PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES app_accounts(account_id),
    protocol VARCHAR(24) NOT NULL,
    issuer_namespace VARCHAR(512) NOT NULL,
    subject_value VARCHAR(512) NOT NULL,
    subject_format VARCHAR(255),
    active BOOLEAN NOT NULL,
    UNIQUE (protocol, issuer_namespace, subject_value, subject_format)
);

CREATE TABLE tenant_memberships (
    account_id UUID NOT NULL REFERENCES app_accounts(account_id),
    tenant_id UUID NOT NULL,
    status VARCHAR(24) NOT NULL,
    PRIMARY KEY (account_id, tenant_id)
);

CREATE TABLE tenant_grants (
    account_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    permission VARCHAR(64) NOT NULL,
    PRIMARY KEY (account_id, tenant_id, permission)
);
~~~

DDL là **minh họa**, không phải migration production-ready. Với PostgreSQL, unique constraint chứa nullable `subject_format` cần xử lý NULL semantics để chống duplicate hiệu quả, ví dụ cho format non-null/canonical hoặc dùng index phù hợp. Phải xác định đúng namespace/qualifiers riêng cho SAML, CAS, SCIM, LDAP và tenant policies; không mặc định một generic schema bao quát mọi giao thức.

Quy tắc:
1. Mỗi external identity **đã xác minh** chỉ map đến một app account active.
2. Một app account có thể có nhiều external identities **nếu có quy trình liên kết đủ bằng chứng**.
3. Không tự map bằng email/username/NameID không scoped.
4. Tenant membership không được suy chỉ từ identity issuer.
5. Business resources phải lưu **tenant ID/owner account ID ổn định**, không lưu owner email làm quyền truy cập.

### 5.2 Tài nguyên nên scope tenant

~~~sql
CREATE TABLE documents (
    document_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    owner_account_id UUID NOT NULL REFERENCES app_accounts(account_id),
    title VARCHAR(255) NOT NULL
);
~~~

Khi truy xuất một document, service cần kiểm:
- Account active;
- Tenant đang chọn có membership active;
- Document.tenantId **khớp** tenant hiện hành;
- Permission trên document (role, owner, ACL);
- Nếu có ownership theo team/project, kiểm thêm scope tương ứng.

**Không dùng câu truy vấn chỉ theo document_id rồi dựa vào UI ẩn nút.** Một URL đoán được hoặc GraphQL node ID có thể truy cập cross-tenant nếu service thiếu object-level check.

### 5.3 Tenant selection từ nơi đáng tin

Một người có thể thuộc hai tenants thật. UI cho chọn A/B là hợp lệ, nhưng server phải validate:
- Account hiện có active membership ở tenant được yêu cầu;
- Tenant selection gắn với session/context server-side hoặc mỗi request được revalidate;
- Mọi resource query và grants được scope theo tenant;
- Việc đổi tenant không được giữ cache/role của tenant cũ;
- Bất kỳ tenant header/body parameter nào đều chỉ là **request context**, không phải authorization.

## 6. Ma trận va chạm định danh cần kiểm

| Trùng gì? | Ví dụ | Điều phải đúng |
| --- | --- | --- |
| OIDC `sub` | A và B đều `sub=001` | Scope `iss+sub` nên map hai accounts khác |
| Email | A/B cùng `alex@example.org` | Không auto-merge; B không thấy A |
| `preferred_username` | A/B cùng `alex` | Không làm account lookup key |
| SAML NameID | Hai IdPs đều NameID `alex` | Scope theo IdP/format/qualifiers |
| SAML entityID cấu hình sai | A/B dùng cùng issuer label | Phải phát hiện conflict cấu hình, không dùng trust wildcard |
| AD `sAMAccountName` | Hai domains đều `alex` | Scope directory/domain/immutable object |
| Kerberos principal | `alex@A.REALM` vs `alex@B.REALM` | Không bỏ realm khi map user |
| CAS username | Hai CAS servers đều user `alex` | Scope CAS server/service + stable attr contract |
| Group name | A và B cùng group `Admins` | Role chỉ có hiệu lực đúng tenant |
| Tenant slug | `sales` trong hai tổ chức | Dùng tenant ID đã đăng ký/namespace |
| Invitation email | B nhận email trước thuộc A | Không claim invite A chỉ vì email |
| ExternalId SCIM | Hai provisioning clients đều `externalId=42` | Scope provisioning domain |
| App account alias | Username rename/reuse | Bền vững theo app account ID, không tái cấp |
| Cache key | `cache["report-42"]` | Phải scope tenant/subject/policy version |
| Session principal | Browser đổi IdP A sang B | Không reuse local account/roles của A |

Với những cases này, **giá trị string trùng chính là dữ liệu test chủ đích**; dữ liệu random không trùng khó phát hiện lỗi thiếu scoping.

## 7. OIDC multi-IdP: kiểm issuer, client, state và nonce

OIDC Authorization Code Flow điển hình:
1. Spring chọn `ClientRegistration` từ danh sách cấu hình cho IdP đã phê duyệt.
2. Redirect browser đến Authorization Endpoint cùng `state` và nonce/PKCE theo client/profile.
3. Browser trở về `/login/oauth2/code/{registrationId}` với authorization code.
4. Client sử dụng saved authorization request để đối chiếu callback và đổi code **với đúng token endpoint/client credentials**.
5. Spring OIDC xác minh ID Token signature, `iss`, `aud`, expiry, `nonce` và các điều kiện áp dụng.
6. App map verified `iss+sub` tới app account, rồi kiểm membership/resource.

**Không được tin một JWT chỉ vì Base64 decode ra email và issuer.** Signature, issuer metadata/JWKS, client audience, token type và các điều kiện protocol phải được verifier tin cậy thực thi.

### 7.1 Cùng sub từ hai issuers

~~~json
{
  "iss": "https://idp-a.example.org",
  "sub": "123",
  "aud": "portal-client-a",
  "email": "alex@example.org"
}
~~~

~~~json
{
  "iss": "https://idp-b.example.org",
  "sub": "123",
  "aud": "portal-client-b",
  "email": "alex@example.org"
}
~~~

Đây là **claim bodies minh họa**, không phải token có chữ ký, không phải input tin cậy. Trong test thực phải phát token/authorization response có chữ ký hợp lệ của IdP thử nghiệm và validate theo registration tương ứng.

Kỳ vọng:
- `(idp-a,123)` → `acct-A`.
- `(idp-b,123)` → `acct-B`.
- Không tự gộp vì `sub` hoặc email giống.
- Session B không nhận quyền của A.

### 7.2 Wrong issuer nhưng chữ ký hợp lệ

Một negative test có thể dùng **hai IdP test ký riêng**:
- Login được khởi tạo bằng client A.
- Callback mang response/token của B theo test harness.
- Ứng dụng không được dùng B JWKS để coi token đó hợp lệ cho A.
- Phải deny trước khi tạo app session.

Đừng chỉ sửa chữ `iss` trong JWT đã ký rồi gửi lại. Như thế chữ ký hỏng, chỉ kiểm tampering. Muốn kiểm issuer logic, sinh token có issuer sai **nhưng chữ ký hợp lệ** bằng test key tương ứng rồi assert **mismatch với expected issuer**.

### 7.3 Wrong audience/clientId

IdP A có thể cấp ID Token cho `portal-client-a2`. Token đó không được chấp nhận trong client `portal-client-a1` vì `aud` không đúng. Nếu nhiều audiences, xem `azp` và chính sách OIDC Core áp dụng.

- Test case đúng phải có valid signature, valid issuer và thời hạn, **chỉ audience/client không đúng**.
- Không đem **ID Token** dùng thay **OAuth2 access token** cho API.
- Với JWT access tokens ở resource server, kiểm `aud` dành cho API theo token profile/contract, không coi `aud=frontend-client` đủ để truy cập mọi API.
- Test token của ứng dụng B không được phép truy cập API dành cho ứng dụng A ngay cả khi cùng issuer.

### 7.4 OAuth2 mix-up attack

Khi một client hỗ trợ nhiều Authorization Servers, nó phải giữ đúng mối liên hệ **authorization request → expected issuer/token endpoint/client registration → authorization response**. Nếu nhầm lẫn nguồn code, authorization code có thể bị gửi tới token endpoint không đúng.

RFC 9207 quy định authorization response parameter `iss` dùng để nhận diện Authorization Server và chống **mix-up attack**. Khi server/client hỗ trợ, client kiểm exact expected issuer; ngoài ra có những countermeasures khác do protocol/profile cung cấp.

Kịch bản QA:
1. Khởi tạo đăng nhập qua IdP A.
2. Giữ browser session/saved OAuth2AuthorizationRequest của A.
3. Thử trả callback từ IdP B theo test IdP harness.
4. Đảm bảo không gửi code của A sang token endpoint B, không tạo Authentication nhầm.
5. Khi response có `iss` theo RFC 9207, kiểm nó khớp expected issuer.
6. Không để caller thay `registrationId` hoặc `state` rồi đổi server context.
7. Kiểm đúng state, nonce và PKCE theo flow, đừng tự bypass validator.

**Spring Security xử lý OAuth2 Login theo APIs và flow đang cấu hình**, nhưng test phải chứng minh app không làm mất issuer/registration association khi có custom resolver, login links, dynamic tenant discovery hoặc custom success handler.

## 8. Spring Security OAuth2 Login: hai registrations có cấu hình độc lập

Cấu hình Spring Boot có dạng (giả sử hai providers hỗ trợ discovery và endpoint hợp lệ):

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp-a:
            provider: corp-a
            client-id: portal-client-a
            client-secret: example-secret-from-secret-manager
            authorization-grant-type: authorization_code
            scope: openid,profile,email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
          corp-b:
            provider: corp-b
            client-id: portal-client-b
            client-secret: example-secret-from-secret-manager
            authorization-grant-type: authorization_code
            scope: openid,profile,email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          corp-a:
            issuer-uri: https://idp-a.example.org
          corp-b:
            issuer-uri: https://idp-b.example.org
~~~

**Đây là ví dụ cấu hình minh họa, không phải secret thật hoặc endpoint thực.** Trong production secrets phải lấy từ secret manager/env có kiểm soát, redirect URI phải đăng ký đúng ở từng IdP, issuer discovery phải có nguồn tin cậy, và app không tự cho phép arbitrary issuer URI do user nhập. `registrationId` là identifier của **client registration**, không phải bằng chứng user thuộc tenant.

Login links thường:
- `/oauth2/authorization/corp-a`.
- `/oauth2/authorization/corp-b`.

Callback thường:
- `/login/oauth2/code/corp-a`.
- `/login/oauth2/code/corp-b`.

Nếu `tenant-a` chỉ cho `corp-a`, cần một **server-side allow-list** bảo đảm người dùng chọn tenant-a không tự khởi tạo flow corp-b rồi quay lại account/tenant-a mà thiếu kiểm tra.

### 8.1 Account binding sau OIDC verification

Trong Spring Security Servlet, một app có thể dùng `OidcUserService` tùy chỉnh để kiểm tra local account sau OIDC login.

~~~java
package com.example.sso;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

@Configuration
public class TrustedOidcUserConfig {

    @Bean
    OAuth2UserService<OidcUserRequest, OidcUser> oidcUserService(
            ScopedAccountBindingService bindings) {

        var delegate = new OidcUserService();

        return request -> {
            OidcUser user = delegate.loadUser(request);

            String issuer = user.getIdToken()
                    .getIssuer().toString();
            String subject = user.getIdToken()
                    .getSubject();

            // Custom application service: exact verified (issuer,sub)
            // lookup, account enabled, and approved membership.
            // Must reject missing/disabled/ambiguous identity.
            bindings.requireActiveAccount(issuer, subject);

            return user;
        };
    }
}
~~~

**Giới hạn:** đây là đoạn Spring configuration **không chạy độc lập**; `ScopedAccountBindingService` là service ứng dụng phải tự triển khai, không phải Spring API chuẩn. Nó phải trả/throw phù hợp authentication failure handler khi unmapped. Cần OIDC ClientRegistration, trusted provider verification, dependency `spring-security-oauth2-client`, `SecurityFilterChain` và database.

Gắn vào login:

~~~java
@Bean
SecurityFilterChain security(
        HttpSecurity http,
        OAuth2UserService<OidcUserRequest, OidcUser> oidcUserService)
        throws Exception {

    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/", "/health").permitAll()
                    .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                    .userInfoEndpoint(userInfo -> userInfo
                            .oidcUserService(oidcUserService)))
            .build();
}
~~~

**Snippet này cần imports** `HttpSecurity`, `SecurityFilterChain`, `@Bean` và các types đã dùng; dự án phải có bean bindings và account policy. Nó xử lý account lookup sau authentication, **không** tự giải quyết resource-level tenant authorization hay session role revocation. Với login có nhiều providers, cần kiểm app lấy correct `registrationId` hoặc expected tenant context trước khi cấp account/session.

### 8.2 Đừng tạo account chỉ bằng email

Anti-pattern:

~~~java
// Không dùng làm automatic identity linking:
String email = oidcUser.getEmail();
Account account = repository.findByEmail(email);
~~~

Rủi ro:
- Hai IdPs có cùng email;
- Một issuer trả email chưa verified;
- Email được tái cấp sau nghỉ việc;
- Một user thay email hoặc IdP tenant;
- Một đối tác có email domain công ty nhưng không thuộc tenant đó.

Dùng verified OIDC `iss+sub` và approved onboarding/JIT provisioning. Nếu muốn liên kết hai identities thành **một app account**, yêu cầu verified account linking từ cả hai contexts hoặc authoritative migration mapping; log approval/evidence.

## 9. SAML2 multi-IdP: registration không phải wildcard trust

Spring Security tạo `RelyingPartyRegistration` cho mỗi quan hệ SP–IdP. Mỗi registration có:
- `registrationId` riêng, ví dụ `corp-a`, `partner-c`.
- Asserting Party entityID riêng.
- Trusted verification certificates riêng.
- SingleSignOnServiceLocation/binding tương ứng.
- SP entityId, AssertionConsumerServiceLocation, signing/decryption credentials theo cấu hình.
- Một tập validations cho Response/Assertion/SubjectConfirmation.

Default endpoints thường:
- `/saml2/authenticate/{registrationId}` để bắt đầu SP-initiated login.
- `/login/saml2/sso/{registrationId}` hoặc callback pattern hỗ trợ, để nhận SAMLResponse.

Spring Security docs nêu registrationId giúp resolve RelyingPartyRegistration, còn bộ kiểm chứng phải verify **issuer, signature/trust, destination, audience, recipient và conditions**. **URL registrationId do browser gọi không làm XML từ IdP B trở thành assertion của A.**

### 9.1 Ví dụ cấu hình hai asserting parties

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp-a:
            assertingparty:
              entity-id: https://saml-a.example.org/metadata
              verification:
                credentials:
                  - certificate-location: classpath:saml-a-test.crt
              singlesignon:
                url: https://saml-a.example.org/sso
          partner-c:
            assertingparty:
              entity-id: https://saml-c.example.org/metadata
              verification:
                credentials:
                  - certificate-location: classpath:saml-c-test.crt
              singlesignon:
                url: https://saml-c.example.org/sso
~~~

Đây là **test-oriented skeleton**, cần các registration metadata/ACS/entityID và certificates thật từ môi trường test. Các đường `classpath</BT> không tồn tại sẵn; không chạy ngay nếu chưa có tài nguyên. Với Spring Boot/Security version cụ thể, rà lại property keys tương thích, signature algorithms, request signing và metadata trust. **Không copy cùng một verification cert cho mọi IdP cho tiện**, trừ khi các IdPs thực sự có trust model được phê duyệt và certificate dùng chung là một quyết định có chủ đích.

### 9.2 Negative test chéo IdP có chữ ký hợp lệ

Thiết lập:
1. IdP A và C có keypairs khác nhau, SP trust cert A trong registration A, cert C trong registration C.
2. Test harness tạo signed SAMLResponse từ C, `Issuer=C`, NameID `alex`.
3. POST response đó vào ACS của A với request state phù hợp scenario.
4. **Phải bị từ chối**, không tạo Authentication A hoặc account A.
5. Dù hai tenants đều có username `alex`, identity mapping không bị gộp.
6. Positive control: signed response A vào ACS A với audience/correlation đúng phải login account A.

Test riêng:
- SAMLResponse `Issuer=A` nhưng ký bằng key C (untrusted signer).
- SAMLResponse `Issuer=C`, key C trusted cho C, nhưng gửi vào registration A.
- Signed Response A có `Audience=SP entityId của C`.
- Signed Assertion A có Recipient/ACS của C.
- NameID giống nhau giữa A và C, issuer hợp lệ nhưng local account lookup phải phân biệt.

**Đừng sửa XML sau khi ký khiến mọi negative cases chỉ fail signature.** Nếu muốn kiểm audience hoặc issuer, tạo fixture với trường sai **rồi ký hợp lệ bằng test key**; giữ các điều kiện khác hợp lệ.

### 9.3 IdP-initiated vs SP-initiated

Trong SP-initiated SAML login, AuthnRequest và `InResponseTo` giúp correlate response với flow trước đó. Trong IdP-initiated unsolicited SSO, có thể không có request tương quan; rủi ro login CSRF/account confusion tăng nếu policy cho phép không giới hạn.

QA cần:
- SP-initiated: giữ đúng session/RelayState/Request ID.
- IdP-initiated (nếu hỗ trợ): restrict trusted issuers, audience/recipient/time, tenant/account linking và RelayState redirect policy.
- Không tự tắt correlation của SP-initiated để test response chéo IdP.
- Không coi một untrusted RelayState hoặc query `?tenant=A` là quyền chọn account/tenant.

## 10. SAML NameID collisions và account linking

Ví dụ:
- IdP A phát `NameID=alex` dạng persistent cho SP A.
- IdP C phát `NameID=alex` dạng unspecified.
- Cả hai SAML assertions đều có chữ ký hợp lệ theo registrations **riêng**.

Kết luận đúng: **hai external subjects khác nhau trừ khi có verified linking**.

Một key SAML cần phản ánh hợp đồng federation:
- Protocol `SAML2`;
- Asserting Party issuer/entityID;
- NameID format;
- NameQualifier/SPNameQualifier khi có;
- SP relationship/registration nếu pairwise name identifiers có phạm vi SP;
- Subject value.

Không ép NameID transient thành tài khoản lâu dài và không coi emailAddress-format NameID bất biến. Nếu bên IdP thay persistent NameID sau migration, cần controlled migration/linking flow, không email fallback.

### Quy tắc JIT provisioning

Just-in-time provisioning khi user đăng nhập lần đầu là hợp lệ **nếu thiết kế chặt**:
1. Sau verification crypto/protocol, lấy identity có scope.
2. Kiểm issuer/tenant allow-list.
3. Kiểm user có lời mời, SCIM pre-provisioning record hoặc policy được phép onboard.
4. Tạo app account mới bằng immutable UUID, **không gộp account theo email**.
5. Gắn external identity binding atomically có uniqueness constraints.
6. Cấp grants mặc định tối thiểu, không tự mapping “Admins” sang global admin.
7. Log provisioning event với nguồn IdP và tenant.
8. Nếu hai first-login requests đồng thời, xử lý unique constraint/race an toàn.
9. Nếu account bị disable/tombstone, không tự phục hồi bằng email reuse.
10. Khi nhiều IdPs cùng onboard một người, cần **explicit link flow**.

## 11. CAS, Kerberos và proxy-auth cũng có collisions

Không chỉ OIDC/SAML mới có rủi ro này.

**CAS:**
- CAS Server có service ticket và user identifier theo configuration.
- Hai CAS Server độc lập cùng trả `cas:user=alex` không chứng minh cùng account.
- Xác minh ticket tại đúng CAS server/service URL, scope identity theo issuer/server và stable account mapping contract.
- Không lấy service ticket từ server khác để tự coi login thành công.

**Kerberos/SPNEGO:**
- `alex@REALM-A` và `alex@REALM-B` là hai principal namespaces.
- Đừng cắt phần `@REALM` rồi lookup chỉ `alex`.
- AD domain migration/UPN rename có thể đổi principal string; cần stable directory object binding nếu quy trình yêu cầu.

**LDAP/Active Directory:**
- `uid`, `sAMAccountName`, `cn`, DN có thể trùng/đổi theo directory/domain.
- AD `objectGUID` có phạm vi directory object; scope với directory/domain ID và migration policy.
- Không auto-link account chỉ vì email hoặc userPrincipalName giống.

**Proxy pre-authentication:**
- Header `X-Authenticated-User: alex` không chứa nguồn IdP/tenant tin cậy nếu proxy không tạo scoped assertion.
- Backend chỉ tin proxy đã xác thực qua network/mTLS, và phải nhận canonical identity với issuer/workload provenance.
- Nếu client gọi backend trực tiếp và giả header, đây là Authentication bypass, không đơn thuần là collision.

## 12. Tenant permission isolation: role phải có scope

Sai:

~~~java
// Sai nếu ROLE_ADMIN được dùng chung toàn hệ thống
// khi yêu cầu là admin theo tenant.
@PreAuthorize("hasRole('ADMIN')")
public Document getDocument(String tenant, String id) {
    return repository.findById(id).orElseThrow();
}
~~~

Nếu user là admin A, câu kiểm tra chỉ nhìn role ADMIN có thể vô tình cho phép lấy tài nguyên B vì repository không scope tenant.

Đúng về mặt tư duy:
1. Xác thực user thành công bằng issuer/subject.
2. App xác định immutable account ID.
3. User chọn tenant theo request, nhưng server xác minh **active membership**.
4. Object được truy xuất có `tenantId` phù hợp.
5. Check grant cụ thể trên object/action; tenant-local admin không tự là global admin.
6. Audit tenant, account, resource, action, decision.

Mẫu Spring service **minh họa**:

~~~java
package com.example.sso;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    private final ScopedDocumentRepository repository;
    private final TenantPermissionService permissions;

    public DocumentService(ScopedDocumentRepository repository,
                           TenantPermissionService permissions) {
        this.repository = repository;
        this.permissions = permissions;
    }

    @PreAuthorize("isAuthenticated()")
    public Document readDocument(String tenantId, String documentId) {
        String accountId = permissions.currentAccountId();
        permissions.requireActiveMembership(accountId, tenantId);
        permissions.requireGrant(accountId, tenantId, "DOCUMENT_READ");

        Document document = repository
                .findByTenantIdAndDocumentId(tenantId, documentId)
                .orElseThrow();

        permissions.requireObjectAccess(accountId, document, "READ");
        return document;
    }
}
~~~

Đây là **partial Spring code**, không có standalone `main()`. `ScopedDocumentRepository`, `TenantPermissionService`, `Document` phải do ứng dụng triển khai. Cần bật `@EnableMethodSecurity`, thiết lập authentication principal mapping đúng và bảo đảm transactional authorization phù hợp. Exception có thể map 403/404 theo chính sách để tránh lộ sự tồn tại tài liệu khác tenant.

**Điểm chính:** mọi truy vấn nên scope tenant ở repository/data access, chứ không chỉ fetch toàn bộ rồi filter ở frontend. Khi dùng JPA, cached entities, native SQL, search engine hoặc object storage, vẫn phải giữ tenant scope.

## 13. Header tenant, hostname và đường dẫn chỉ là input

Một API có thể nhận:
- `GET /tenants/tenant-a/documents/123`;
- `X-Tenant-Id: tenant-a`;
- Subdomain `tenant-a.app.example.org`;
- GraphQL argument `organizationId=tenant-a`.

Các giá trị này **không tự có thẩm quyền**. Người dùng có thể sửa chúng. Cần xác minh tenant exists, active membership, grant và resource belongs to that tenant.

### Host/Forwarded header confusion

Nếu reverse proxy có public host A/B nhưng backend tin `Host` hoặc `X-Forwarded-Host` do browser tự gửi, request có thể bị route về issuer/tenant sai. Biện pháp:
- Edge proxy strip/overwrite `Forwarded`, `X-Forwarded-Host/Proto`;
- Public hostname allow-list;
- RelyingPartyRegistration/ClientRegistration được chọn từ server-side policy/saved authorization request;
- Callback/ACS URI, redirect URI và entity ID đúng per tenant;
- Không chọn trusted issuer/JWK URL chỉ từ raw host/query.

**Không chỉ dựa vào private network** nếu backend có direct access bypass authentication proxy.

## 14. Một IdP có thể phục vụ nhiều tenants: double checks

Tình huống:
- IdP `https://corporate-idp.example.org` dùng chung cho tenant A và B.
- User `sub=123` là một identity duy nhất ở IdP.
- User là member tenant A, không phải B.
- Token có issuer và signature hợp lệ.

Nếu server map `issuer=corporate-idp` thành “được truy cập mọi tenant của IdP” thì xảy ra cross-tenant access.

Thiết kế:
- External identity mapping nhận account ID.
- Tenant membership lookup là **độc lập** với issuer trust.
- Role/grants scoped theo tenant.
- Default tenant được chọn ở UI **không** là quyền được bỏ qua checks.
- Khi membership bị revoke, bump `securityEpoch`, invalidate session/caches/tokens theo SLA.
- Resource owner tenant phải kiểm riêng ở domain/repository.

Test này quan trọng vì **IdP trust hoàn toàn đúng** nhưng dữ liệu vẫn có thể bị rò.

## 15. Một tenant cho phép nhiều IdPs: không merge tự động

Tình huống:
- Tenant A cho employees đăng nhập qua Corporate OIDC A.
- Contractors qua Partner SAML C.
- Hai user có cùng email `alex@company.example.org`.

Lựa chọn đúng:
- Mỗi verified external identity có binding riêng.
- Bảng allow-list chỉ định registrations được tenant A chấp nhận.
- Local account linking qua invite hoặc identity governance khi có bằng chứng.
- Một external identity không được map hai accounts; một account nhiều bindings cần approval.
- Tenant A membership/roles riêng cho từng account.
- Partner C không tự nhận corporate privileges vì email domain/username.

Test:
1. OIDC A login account employee; positive.
2. SAML C login contractor; positive.
3. C dùng cùng email employee; không chiếm account employee.
4. C có nhóm `Admins` ở directory riêng; không thành tenant global admin.
5. Account link chỉ xảy ra qua flow có verified proof và audit; negative khi thiếu proof.
6. Revocation identity C không vô tình revoke A trừ business policy cho liên kết đó.

## 16. Va chạm nhóm/role: “Admins” không phải global admin

Các IdP/tenant có thể phát:
- `groups = ["Admins"]`.
- SAML Attribute `memberOf=Admins`.
- OIDC custom claim `roles=["Admin"]`.

Nếu app map mọi chuỗi `Admins` sang `ROLE_SUPER_ADMIN`, IdP đối tác có thể vô tình cấp đặc quyền toàn hệ thống.

Thiết kế authorities:
- Trusted issuer + registration context phải được xác minh.
- Group identifiers scoped bởi issuer/directory/tenant, ưu tiên immutable group ID.
- Mapping từng tenant: `(tenant-a,group-a-id) → REPORT_ADMIN_A`.
- Distinguish system operator roles do tổ chức vận hành app cấp riêng.
- Không nhầm account global admin với tenant-local admin.
- Không lấy groups của IdP B để authorize resource tenant A khi không có explicit cross-tenant grant.
- Token authorities có thể stale khi user chuyển tenant; cần live checks/revocation.

### Test groups collision

| User | Issuer | Group claim | Đích | Kết quả |
| --- | --- | --- | --- | --- |
| A | IdP A | Admins | Tenant A reports | Allow nếu mapping A cấp |
| A | IdP A | Admins | Tenant B reports | Deny |
| B | IdP B | Admins | Tenant A reports | Deny |
| B | IdP B | Admins | Tenant B reports | Allow nếu mapping B cấp |
| C | Partner C | Admins | System admin API | **Deny** nếu không có system grant |
| A | IdP A | Viewers | Tenant A admin API | Deny |

## 17. JIT provisioning, invitations và SCIM

JIT provision khi user đăng nhập SSO lần đầu thường cần:
1. Verified protocol identity.
2. Tenant–IdP association allow-list.
3. Invite/SCIM preprovisioning hoặc policy cho phép onboarding.
4. Atomic create of app account/external binding.
5. Default least-privilege membership.
6. Audit issuer, stable subject, tenant, source.
7. No auto-link by email.
8. No restore of deleted account solely by email reuse.
9. Collision checks ở DB.
10. Clear failure mode khi cùng external subject có conflicting bindings.

SCIM fields:
- `id` là service-provider-issued trong provider scope.
- `externalId` do provisioning client cấp, scoped provisioning domain.
- `userName/email` có thể đổi.
- SCIM `active=false` không tự revoke mọi session/token.
- Group memberships có thể được đồng bộ theo SCIM Group resource; không coi `department` là authorization proof.

### Email invite collision

Ví dụ:
- Tenant A mời `alex@example.org`.
- Người B từ IdP B đăng nhập với email cùng giá trị.
- Invite được tạo cho một corporate identity cụ thể.

**Không tự gán invite chỉ vì email trùng.** Cần kiểm:
- Invite có liên kết với issuer/directory, hoặc quy trình verified email/proof phù hợp.
- Invite token short-lived, single-use, bound to tenant và target identity nếu áp dụng.
- Không cho người đã dùng email cũ của A claim lịch sử.
- Nếu tự phục vụ với email proof, đánh giá account-takeover/migration risk trước khi thiết kế.

### Concurrency

Hai login attempts tạo JIT account cùng lúc có thể cùng thấy “chưa có account”. Cần unique identity constraints + transaction/retry an toàn, không tạo 2 accounts rồi merge theo email tùy tiện.

## 18. Browser session và account switching

Multi-IdP login thường dùng **cùng một browser**:
- Tab 1 đăng nhập IdP A.
- Tab 2 đăng nhập IdP B.
- Browser giữ cookie phiên Spring.
- Request ở tab 1 gọi resource tenant A sau khi tab 2 hoàn tất login.

Nếu app chỉ có **một HttpSession authentication** trên cùng cookie, login B có thể thay principal hiện tại. Nếu UI tab A vẫn hiển thị dữ liệu cũ, request tiếp theo phải được kiểm dưới **identity hiện tại**, không mặc định tab A vẫn là user A.

Các ca test:
1. Login A rồi B trong cùng browser; xác nhận session current identity theo design.
2. Tab A request sau B login; không tự dùng quyền A stale.
3. Logout A nhưng B session tồn tại hay không? Theo SSO/local-session policy, không ngẫu nhiên kết hợp.
4. IdP B callback đến trong khi state của A đang pending; không cross-bind.
5. Saved requests/RelayState giữa hai login flows không bị lẫn.
6. Session fixation: sau authentication session ID behavior đúng policy.
7. User A/B có cùng email/sub local; không reuse account.
8. Account switch phải clear/rotate security context và tenant-specific caches.
9. “Remember me”/authorized client records phải scoped account/client/issuer.
10. Multiple browser profiles khác nhau vẫn không thể lẫn tenant data.

**Không dùng HttpSession attribute `currentTenant` do client tự set** làm quyền. Mỗi call resource vẫn cần check account, selected tenant, active membership và ACL.

## 19. Token exchange và callback mix-up

Đối với OIDC Authorization Code Flow đa provider:
- State gắn với saved authorization request và expected client registration.
- Redirect URI phải đúng client/authorization server registration.
- Token exchange đến đúng token endpoint với client credentials phù hợp.
- ID Token issuer/audience/nonce được verify theo profile.
- Nếu authorization response có `iss` theo RFC 9207, phải so với expected issuer.
- PKCE bảo vệ code flow theo client requirements nhưng **không thay issuer/client matching**.
- Không dùng unsanitized `Host` hoặc query param để xây token endpoint URL.
- Đổi `registrationId` trong callback không được làm code của A gửi sang B.
- Test failure không leak authorization code/token vào logs hoặc error redirect.

### Test mẫu ở mức giao thức

~~~text
Given:
  Authorization request được khởi tạo cho corp-a
  Expected issuer = https://idp-a.example.org
  Saved state = state-A, nonce-A, client-a

When:
  Browser callback mang response từ corp-b
  hoặc tham số issuer response sai, hoặc state-B

Then:
  Reject
  No account A/B session được tạo từ response sai
  No authorization code được gửi sang token endpoint sai
  Correlation/log có mã sự cố, không lộ code/token
~~~

Đây là **test design**; muốn chạy phải có test IdPs/authorization servers và HTTP/browser harness, không dùng JWT body viết tay làm success token.

## 20. JWT Resource Server multi-issuer: khác OAuth2 Login

Một backend API có thể chấp nhận **Bearer JWT access tokens** từ hai authorization servers. Spring Security hỗ trợ chọn validator theo issuer với `AuthenticationManagerResolver`, chẳng hạn `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(... )` trong version có API đó.

~~~java
// Mảnh cấu hình Spring Security Resource Server,
// không phải OIDC browser login hay chương trình độc lập.
JwtIssuerAuthenticationManagerResolver resolver =
        JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
                "https://idp-a.example.org",
                "https://idp-b.example.org");

http.oauth2ResourceServer(oauth2 ->
        oauth2.authenticationManagerResolver(resolver));
~~~

**Điều kiện:** cần dependencies Resource Server + JOSE, trusted issuer config, `SecurityFilterChain`, correct audience/token type validation. Danh sách issuers này phải **cố định/được quản lý**; không tạo decoder từ issuer URL do attacker tùy ý đưa vào.

### Tại sao trusted issuers thôi chưa đủ?

Một token có thể:
- Có issuer A hợp lệ, nhưng `aud` dành cho API X chứ không phải Y.
- Có scope `reports.read` nhưng user không có membership tenant B.
- Thuộc resource owner khác, chỉ token user đúng không đủ.
- Chứa tenant claim A nhưng user hiện đã bị revoke A.
- Có group `Admins` nhưng chỉ mang nghĩa local ở IdP A.

Resource server cần:
1. Verify JWT signature theo issuer trust.
2. Verify `iss`, `exp/nbf` theo profile và `aud` đúng API.
3. Validate scopes/custom claims tin cậy.
4. Resolve issuer+subject, account active.
5. Check membership/ACL tại resource boundary.
6. Không dùng `tenant` từ request để override verified entitlement.

**Không dùng ID Token của browser làm bearer API access token.** ID Token audience thường là OIDC client; API access token cần contract riêng.

## 21. Kiểm cache và truy vấn dữ liệu

Một app có thể kiểm permission đúng ở controller nhưng rò dữ liệu vì cache keys không scope tenant.

Sai:

~~~java
@Cacheable("documents")
public Document find(String documentId) {
    return repository.findById(documentId).orElseThrow();
}
~~~

Nếu documentId chỉ unique trong tenant hoặc method bị gọi dưới nhiều tenants, cache có thể trả dữ liệu từ tenant khác. Sửa:
- Key bao gồm `tenantId</BT> và resource ID, hoặc thêm access-scope/user version nếu response phụ thuộc user.
- Vẫn kiểm authorization trước khi trả cached object; cache hit không là lý do bỏ ACL.
- Không đưa user-specific response vào cache global chia mọi người.
- Database query scope tenant và ACL.
- Search index, object storage, CDN caches cũng cần namespace và access checks.
- Asynchronous jobs nhận explicit trusted tenant context và verify service permissions.
- Không tin thread-local tenant còn sót khi thread pool tái sử dụng.

### Các tầng dữ liệu cần test

| Tầng | Cross-tenant test |
| --- | --- |
| Controller/REST | Đổi tenant path/header và request document khác tenant |
| GraphQL | Node ID thuộc tenant khác, nested resolver không leak |
| Repository | Query thiếu tenant filter phải bị unit/integration test phát hiện |
| Caching | A warm cache rồi B cùng resource key không nhận dữ liệu A |
| Export/report | Async export tenant A không tải được bằng tenant B |
| File/object storage | Signed URL và object keys gắn tenant và TTL |
| Event/queue | Consumer xử lý tenant context đúng, không dùng stale ThreadLocal |
| Search index | Search tenant B không trả snippets tenant A |
| Admin APIs | Tenant admin không thành global/system admin |
| Background jobs | Service identity chỉ có rights được ủy quyền |

## 22. Java 17 độc lập: minh họa identity-scoped và tenant-scoped authorization

Chương trình này dùng **chỉ Java Standard Library**, không cần Spring/IdP/DB. Nó mô phỏng:
- `(issuer,subject)` trùng `sub` nhưng không trùng account.
- Email trùng nhưng không tự liên kết.
- Tài khoản A/B chỉ được xem tenant của mình.
- IdP lạ hoặc subject mới có email trùng bị từ chối.
- Session version cũ bị chặn sau khi user chuyển tenant.
- Disable account chặn mọi truy cập.

**Ranh giới quan trọng:** `VerifiedIdentity` trong demo là giả lập **kết quả đã xác minh**. Production phải lấy object tương đương từ OIDC/SAML provider thật, không tạo từ JSON hoặc query/header do client gửi.

Tệp `CrossTenantIdentityDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

public final class CrossTenantIdentityDemo {

    record VerifiedIdentity(String issuer, String subject) {}

    record Session(String accountId, long securityEpoch) {}

    static final class Account {
        final String id;
        final String email;
        boolean enabled = true;
        long securityEpoch = 1;
        final Map<String, Set<String>> tenantRoles = new HashMap<>();

        Account(String id, String email, String tenant, Set<String> roles) {
            this.id = id;
            this.email = email;
            this.tenantRoles.put(tenant, Set.copyOf(roles));
        }
    }

    static final class Directory {
        private final Map<VerifiedIdentity, String> bindings =
                new HashMap<>();
        private final Map<String, Account> accounts = new HashMap<>();

        synchronized void register(
                VerifiedIdentity verified,
                Account account) {
            if (bindings.containsKey(verified)
                    || accounts.containsKey(account.id)) {
                throw new IllegalArgumentException("duplicate binding");
            }
            bindings.put(verified, account.id);
            accounts.put(account.id, account);
        }

        synchronized String resolve(VerifiedIdentity verified) {
            return bindings.getOrDefault(verified, "NO_MATCH");
        }

        synchronized Session sessionFor(VerifiedIdentity verified) {
            String id = bindings.get(verified);
            if (id == null || !accounts.get(id).enabled) {
                return null;
            }
            Account account = accounts.get(id);
            return new Session(id, account.securityEpoch);
        }

        synchronized String authorize(
                Session session, String tenant, String role) {
            if (session == null) {
                return "DENY_UNMAPPED";
            }
            Account account = accounts.get(session.accountId());
            if (account == null) {
                return "DENY_UNMAPPED";
            }
            if (!account.enabled) {
                return "DENY_DISABLED";
            }
            if (account.securityEpoch != session.securityEpoch()) {
                return "REAUTH_REQUIRED";
            }
            Set<String> roles = account.tenantRoles.get(tenant);
            if (roles == null) {
                return "DENY_TENANT";
            }
            if (!roles.contains(role)) {
                return "DENY_ROLE";
            }
            return "ALLOW";
        }

        synchronized void move(
                String accountId, String tenant, Set<String> roles) {
            Account account = accounts.get(accountId);
            if (account == null) {
                throw new IllegalArgumentException("unknown account");
            }
            account.tenantRoles.clear();
            account.tenantRoles.put(tenant, Set.copyOf(roles));
            account.securityEpoch++;
        }

        synchronized void disable(String accountId) {
            Account account = accounts.get(accountId);
            if (account == null) {
                throw new IllegalArgumentException("unknown account");
            }
            account.enabled = false;
            account.securityEpoch++;
        }
    }

    public static void main(String[] args) {
        Directory directory = new Directory();
        VerifiedIdentity userA = new VerifiedIdentity(
                "https://idp-a.example.org", "123");
        VerifiedIdentity userB = new VerifiedIdentity(
                "https://idp-b.example.org", "123");

        directory.register(userA, new Account(
                "acct-A", "same@example.org",
                "tenant-a", Set.of("REPORT_READ")));
        directory.register(userB, new Account(
                "acct-B", "same@example.org",
                "tenant-b", Set.of("REPORT_READ")));

        Session sessionA = directory.sessionFor(userA);
        Session sessionB = directory.sessionFor(userB);

        System.out.println("A identity: " + directory.resolve(userA));
        System.out.println("B identity: " + directory.resolve(userB));
        System.out.println("A own: " + directory.authorize(
                sessionA, "tenant-a", "REPORT_READ"));
        System.out.println("B own: " + directory.authorize(
                sessionB, "tenant-b", "REPORT_READ"));
        System.out.println("A into B: " + directory.authorize(
                sessionA, "tenant-b", "REPORT_READ"));
        System.out.println("B into A: " + directory.authorize(
                sessionB, "tenant-a", "REPORT_READ"));

        VerifiedIdentity unknownIssuer = new VerifiedIdentity(
                "https://idp-rogue.example.org", "123");
        VerifiedIdentity reusedEmailOwner = new VerifiedIdentity(
                "https://idp-a.example.org", "999");

        System.out.println("Rogue issuer: " + directory.authorize(
                directory.sessionFor(unknownIssuer),
                "tenant-a", "REPORT_READ"));
        System.out.println("Reused email: " + directory.authorize(
                directory.sessionFor(reusedEmailOwner),
                "tenant-a", "REPORT_READ"));

        directory.move("acct-A", "tenant-c",
                Set.of("REPORT_READ"));
        System.out.println("A old session after move: "
                + directory.authorize(
                        sessionA, "tenant-a", "REPORT_READ"));

        Session newSessionA = directory.sessionFor(userA);
        System.out.println("A old tenant after move: "
                + directory.authorize(
                        newSessionA, "tenant-a", "REPORT_READ"));
        System.out.println("A new tenant: "
                + directory.authorize(
                        newSessionA, "tenant-c", "REPORT_READ"));

        directory.disable("acct-B");
        System.out.println("B after disabled: "
                + directory.authorize(
                        sessionB, "tenant-b", "REPORT_READ"));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac CrossTenantIdentityDemo.java
java CrossTenantIdentityDemo
~~~

Stdout **chính xác**:

~~~text
A identity: acct-A
B identity: acct-B
A own: ALLOW
B own: ALLOW
A into B: DENY_TENANT
B into A: DENY_TENANT
Rogue issuer: DENY_UNMAPPED
Reused email: DENY_UNMAPPED
A old session after move: REAUTH_REQUIRED
A old tenant after move: DENY_TENANT
A new tenant: ALLOW
B after disabled: DENY_DISABLED
~~~

### Giải thích

1. A và B có cùng subject text `123` và cùng email, nhưng issuer khác → app accounts khác.
2. User A/B chỉ được xem tài nguyên thuộc tenant có role.
3. User ở unknown issuer hoặc new subject không được tự nhận account A qua email.
4. Chuyển A sang tenant C làm tăng securityEpoch; phiên cũ bị chặn.
5. Sau login mới, tenant A không còn membership, tenant C được phép.
6. Disable B chặn session B, dù session này chưa hết hạn.

### Giới hạn nghiêm ngặt

- Không có cryptographic verification, OAuth2/OIDC/SAML/LDAP hoặc HTTP.
- Input `VerifiedIdentity` được tạo thủ công trong demo; production **chỉ** nhận từ đã-verify protocol.
- Tất cả data nằm trong `HashMap`, không có DB, distributed session, concurrency ở nhiều nodes hoặc audit.
- Không có resource ACL hay URL IDOR: ví dụ chỉ kiểm tenant-role policy.
- Không làm account linking/SCIM migration.
- Không phải cơ chế bảo mật production; đây là mô hình minh họa để viết unit tests.

## 23. Tạo unit tests cho identity binding, không làm giả SSO verifier

Dùng test data có cấu trúc:

~~~text
OIDC:
  A = (issuerA, sub=shared-123), email=shared@example.org
  B = (issuerB, sub=shared-123), email=shared@example.org
  C = (issuerA, sub=other-999), email=shared@example.org

Expected:
  resolve(A) == acct-A
  resolve(B) == acct-B
  resolve(C) == NO_MATCH
~~~

Các asserts này kiểm **binding logic**, không kiểm chứng ID Token đã được ký đúng. Chúng phù hợp unit test nhanh trong Java/JUnit.

Tương tự SAML:

~~~text
SAML IdP A: issuer=entityA, NameID=alex, format=persistent
SAML IdP C: issuer=entityC, NameID=alex, format=persistent
Expected: two scoped identity records, no implicit link
~~~

Sau đó thêm **integration tests** sử dụng real signed SAML fixture hoặc OIDC test server để xác minh rằng ứng dụng chỉ tạo bindings từ **verified claims**, không từ dữ liệu tự khai.

## 24. Test tenant authorization với MockMvc

Test sau minh họa kiểm business endpoint **sau khi có Authentication**:

~~~java
package com.example.sso;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CrossTenantAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    @WithMockUser(username = "acct-A", roles = "TENANT_A_VIEWER")
    void userMustNotReadTenantB() throws Exception {
        mvc.perform(get("/tenants/tenant-b/documents/doc-42"))
                .andExpect(status().isForbidden());
    }
}
~~~

**Giới hạn:** đây là một test trong Spring project, không có main và phụ thuộc controller, local authority naming, tenant/data setup và exception contract. Đường `/tenants/...` cũng chỉ là ví dụ. Test này có thể chứng minh route/ACL chặn tenant B nếu đúng app logic, **không chứng minh OIDC signature/SAML verifier**.

Để kiểm SSO thực:
- Dùng test OIDC IdP cấp ID Token signed của A/B.
- Dùng test SAML IdPs ký responses theo certificates A/C.
- Đi qua actual login filter và provider.
- Assert external identity account mapping chính xác.
- Sau login, gọi tenant resources và assert 403/404 theo policy.

**Một test không đủ cho cả authN và authZ nếu nó chỉ chèn mock Authentication.**

## 25. Test OIDC integration: cặp issuer và audience độc lập

Dùng hai OpenID Providers test với keypairs riêng:
1. A sinh valid token `iss=A, sub=123, aud=client-a`.
2. B sinh valid token `iss=B, sub=123, aud=client-b`.
3. Đăng nhập A → account A, tenant A.
4. Đăng nhập B → account B, tenant B.
5. Token B đưa vào flow client A → reject.
6. Token từ A nhưng `aud=another-client` và signature valid → reject.
7. Unknown issuer/unknown JWKS dù sub/email trùng → reject.
8. Token bị sửa claims sau signing → reject signature.
9. Token còn valid nhưng app account disabled → login/action denied.
10. Test state/nonce/authorization response issuer mix-up trên callback.

**Không chỉ sửa string trong JWT ký sẵn để test wrong issuer/audience**: như vậy signature fail. Muốn test chính validator, sinh lại JWT với fields sai nhưng signature vẫn đúng theo test issuer setup.

Với resource server JWT:
- Test audience dành cho API khác;
- Test token ID vs access token;
- Test issuer allow-list;
- Test tenant membership/permission kể cả token valid;
- Test cache/revocation theo SLA.

## 26. Test SAML integration: signer, issuer, registration, audience

Dùng two test IdPs, separate signing certs và real OpenSAML provider:
- Signed response A vào registration A, đúng audience/recipient/conditions → success.
- Signed response C vào registration C, đúng profile → success.
- Signed response C vào registration A → reject.
- Signed response Issuer=A nhưng ký C key → reject signer/trust.
- Signed response A nhưng Audience=SP C → reject semantic validation.
- Signed response A nhưng Recipient=ACS C → reject.
- Signed response A với NameID trùng C → **không cùng account**.
- Signed response thiếu hoặc sai InResponseTo trong SP-initiated flow → reject theo policy.
- Signed response bị replay → reject theo correlation/replay policy thực.
- IdP-initiated unsolicited response nếu hỗ trợ: kiểm allow-list/trust/tenant mapping và RelayState.

**Bảo đảm negative semantic fixtures vẫn có chữ ký hợp lệ**, nếu không tests có thể chỉ phát hiện signature tampering.

## 27. Cross-tenant test matrix nhiều tầng

| ID | Kịch bản | Tầng | Expected |
| --- | --- | --- | --- |
| T01 | OIDC A sub=123 vào account A | Real OIDC login | ALLOW A |
| T02 | OIDC B sub=123 vào account B | Real OIDC login | ALLOW B |
| T03 | OIDC A/B cùng email | Identity mapping | Không gộp |
| T04 | OIDC A token vào client B | OIDC validator | DENY |
| T05 | OIDC B token chữ ký đúng nhưng wrong audience A | OIDC validator | DENY |
| T06 | Unknown issuer tạo sub/email trùng | AuthN trust | DENY |
| T07 | OAuth code/callback IdP mix-up | OAuth login flow | DENY, không gửi code sai endpoint |
| T08 | Callback state sai hoặc stale | OAuth login flow | DENY |
| T09 | Nonce mismatch | OIDC validation | DENY |
| T10 | IdP A signer key lạ nhưng claims đúng | OIDC signature | DENY |
| T11 | SAML C signed response tới ACS A | SAML provider/ACS | DENY |
| T12 | SAML A signed response Issuer C | SAML provider/issuer | DENY |
| T13 | SAML A wrong Audience, signed valid | SAML semantic validator | DENY |
| T14 | SAML A wrong Recipient, signed valid | SAML semantic validator | DENY |
| T15 | SAML A wrong InResponseTo | SAML correlation | DENY theo flow |
| T16 | SAML A/C cùng NameID | Identity mapping | Không gộp |
| T17 | SAML transient NameID reuse | Account linking | Không tạo persistent collision |
| T18 | CAS servers cùng cas:user | CAS identity scope | Không gộp |
| T19 | Kerberos user@REALM-A/B | Realm scope | Không gộp |
| T20 | A request document B | App/resource ACL | DENY |
| T21 | Admin A request admin API B | Tenant-scoped role | DENY |
| T22 | B đổi `X-Tenant-Id</BT> thành A | API/authorization | DENY |
| T23 | Một issuer phục vụ hai tenants, user chỉ thuộc A | Membership | DENY B |
| T24 | Một tenant cho hai IdPs, users cùng email | Provisioning/account binding | Không auto-link |
| T25 | Recycled email sau offboarding | Rehire/account linking | Không kế thừa dữ liệu |
| T26 | SCIM externalId trùng hai sources | Provisioning | Scoped; không gộp |
| T27 | Cache A warm rồi B request cùng ID | Cache/data access | Không leak A |
| T28 | GraphQL node ID thuộc tenant A từ B | Object-level ACL | DENY |
| T29 | Async export của A tải bằng token B | Download authorization | DENY |
| T30 | Login A rồi B trong cùng browser | Session isolation | Không reuse A privileges |
| T31 | A bị revoke membership khi đang login | Live authZ/epoch | DENY A resource |
| T32 | User có cả A/B memberships hợp pháp | Membership switching | ALLOW đúng resources theo scope |
| T33 | B có group Admins như A | Role mapping | Không global admin |
| T34 | Unknown registrationId trong SAML/OIDC | Routing/trust | DENY |
| T35 | IdP cert rotation khác tenant | Configuration | Không chấp nhận signer lạ |
| T36 | Host/Forwarded headers giả | Proxy/trust boundary | Không chọn issuer/tenant sai |

Đây là một **bộ cases**, không đòi mọi app phải chạy đủ 36 cases khi không có giao thức/kiến trúc tương ứng. Chọn các cases thực tế nhưng **không loại bỏ negative authN+authZ tối thiểu**.

## 28. Các điều kiện để một test phản ánh đúng nguyên nhân

Một test “B không truy cập được A” có thể pass vì:
- ID Token B bị invalid signature;
- App không có account B;
- Resource A không tồn tại;
- Database test trống;
- Session không được tạo;
- Authorization check thực sự từ chối tenant B.

Chỉ trường hợp cuối (với B đã authenticated đúng và resource A tồn tại) mới là bằng chứng mạnh cho **cross-tenant authorization**.

**Để test có giá trị:**
1. Có positive control B đăng nhập thành công bằng provider thật.
2. Resource A tồn tại trong fixture DB và user A có quyền.
3. User B có account và membership B, không có A.
4. User B gọi A resource bằng session/token **hợp lệ của B**.
5. Assert 403/404 theo policy và **không rò data/existence**.
6. Kiểm query logs/audit có decision, không kết luận chỉ từ 404 do row không tồn tại.
7. Thử biến thể role-admin B, group collision, email collision, IdP collision.
8. Thử cache đã warm với dữ liệu A.
9. Khi cần chứng minh block ở DB, thực thi repository query với tenant predicate.
10. Không mock permission service trả false nếu mục tiêu là kiểm permission service thật.

### Với protocol negative tests

Nếu muốn kiểm `aud`, signed wrong-audience fixture phải **hợp lệ ở signature/issuer/time**. Nếu muốn kiểm signed SAML trust, fixture của IdP B phải ký hợp lệ bằng B test key nhưng sai registration A. Đừng tạo một XML/JWT hỏng toàn diện rồi tuyên bố đã test mọi validator.

## 29. Security boundary cho account linking

Một sản phẩm có thể cần link employee OIDC A và contractor SAML C vào **cùng app account** vì là một người thật. Liên kết này có thể hợp lệ, nhưng là operation có rủi ro.

Một flow chặt:
1. Người dùng xác thực lại identity hiện tại A.
2. Bắt đầu linking flow từ app account A có CSRF/anti-session fixation.
3. Chuyển sang IdP C theo trusted registration; xác minh SAML Response/OIDC ID Token.
4. Kiểm C identity chưa map tới app account người khác.
5. Yêu cầu step-up/approval nếu account có role nhạy cảm hoặc cross-tenant.
6. Link C identity vào account A bằng transaction và unique constraint.
7. Ghi actor, phương thức xác minh, source IdP, timestamp, tenant scope, evidence reference.
8. Không tự **union roles** từ A và C; memberships/roles được quản lý riêng.
9. Unlink/revoke flow có kiểm soát và không để orphan privileged bindings.
10. Test concurrency và rollback nếu persistence failure.

### Các ca phải từ chối

- Browser chỉ khai hai email giống nhau.
- IdP C trả unverified email trùng A.
- Người dùng không chứng minh kiểm soát identity A nhưng muốn link C vào A.
- C identity đang link account khác.
- Link được tạo qua callback thiếu state.
- Issuer tự động khám phá theo URL do caller đưa.
- Việc link vô tình cấp admin tenant A cho C principal vì group `Admins` của C.

## 30. Phân biệt authentication errors và authorization denial

Hệ thống nên có error taxonomy:

| Lớp | Ví dụ | Expected handling |
| --- | --- | --- |
| OAuth/OIDC protocol | State/nonce mismatch, invalid signature, issuer/client mismatch | Authentication fail, không session |
| SAML protocol | Untrusted signer, wrong Issuer/Audience/Recipient | Authentication fail, không session |
| Identity binding | Valid IdP subject chưa onboard | Login/onboarding deny hoặc approved invitation flow |
| Account state | Account DISABLED | Deny dù IdP token valid |
| Tenant membership | Account active nhưng không thuộc target tenant | 403/404 theo policy |
| Resource ACL | Member tenant nhưng thiếu quyền object | 403/404 theo policy |
| Cache/serialization | Response A xuất hiện trong session B | Security defect/incident |
| Logout/session | Session A còn roles sau switch/revoke | Revoke/reauth, security event |

Không dùng “401 ở mọi case” để che việc backend từng tạo Authentication A từ B response. **Test phải kiểm SecurityContext/account binding**, không chỉ HTTP status.

### Không tiết lộ dữ liệu qua errors

Một user không thuộc tenant A có thể không cần biết document `doc-42` tồn tại. Trả 404 thay vì 403 theo policy có thể giảm enumeration, nhưng backend vẫn phải **thực sự deny**. Không đưa private tenant names, account emails, group memberships, SAML assertions hoặc raw ID tokens vào error response.

## 31. Multi-node/cache/session và race conditions

Một hệ SSO chạy nhiều pods có thể:
- Node 1 xử lý callback IdP A.
- Node 2 xử lý request tenant B.
- Distributed HttpSession chứa principal/tenant context cũ.
- Permission cache được key theo username thay vì immutable account ID + tenant.
- Provisioning event revoke membership nhưng cache chưa invalidate.
- Hai auth callbacks đồng thời trong browser tạo kết quả cuối bất định.

### Các biện pháp

1. Session security state theo immutable app account ID và verified external issuer binding.
2. Tenant selection được kiểm lại theo current membership, không tin stale session claim.
3. Permission cache key: account ID, tenant ID, policy/security epoch, action khi phù hợp.
4. Session rotation/principal-change policy khi login sang user khác.
5. Không giữ raw tokens/SAML assertion trong cache dùng chung nếu không cần.
6. Event-driven invalidation và TTL phù hợp revocation SLA.
7. Async jobs mang trusted tenant context và service identity, không tin mutable ThreadLocal.
8. Nếu dùng SCIM/HR event, xử lý duplicate/out-of-order không mở lại grants cũ.
9. Test concurrency: two simultaneous login callbacks, account linking, tenant switching, membership revocation.
10. Audit active sessions after IdP/tenant changes.

**Không giả định logout khỏi IdP sẽ hủy ngay mọi local HttpSession/JWT/API key**, dù IdP thực thi SLO/Logout. Khi yêu cầu chặn truy cập ngay, cần app-local account gate và revocation strategy.

## 32. Kiểm tra logs và monitoring mà không lộ token

Event mẫu (đã tối giản):

~~~json
{
  "event": "cross_tenant_access_denied",
  "traceId": "opaque-trace-01",
  "authenticatedIssuerAlias": "corp-b",
  "accountRef": "acct-B",
  "requestedTenant": "tenant-a",
  "decision": "DENY_MEMBERSHIP",
  "resourceType": "document"
}
~~~

Không log raw JWT, authorization code, SAMLResponse, SAML Assertion XML, CAS service ticket, GSS tokens, session ID, email/PII không cần thiết.

Metrics:
- `federation_unknown_issuer_total`.
- `federation_wrong_registration_total`.
- `identity_collision_detected_total`.
- `cross_tenant_denied_total`.
- `account_linking_rejected_total`.
- `invalid_oidc_state_total`.
- `saml_untrusted_signer_total`.
- `tenant_membership_revocation_latency_seconds`.
- `unexpected_resource_tenant_access_total` nếu có detection.
- `cache_tenant_scope_violation_total` nếu hệ thống đo được.

Cảnh báo khi:
1. Login từ issuer chưa phê duyệt tăng đột biến.
2. Một verified identity cố liên kết nhiều app accounts.
3. Same email collision dẫn đến auto-link attempt.
4. Cross-tenant denied events tăng bất thường.
5. External ID thuộc tenant A được dùng ở B sau migration.
6. Tài khoản bị disabled mà vẫn được authorized.
7. Cached response trả resource tenant khác.
8. New IdP certificate/metadata được trust mà chưa có approval.

Không dùng user email/sub/raw assertion IDs làm metric labels có cardinality cao. Dashboard phải được phân quyền và bảo vệ PII.

## 33. Quy trình QA từ thấp đến cao

### A. Unit tests cho key và local ACL

- Tạo subjects trùng nhưng issuers khác.
- Tạo emails/usernames giống nhau.
- Kiểm binding maps tách hai accounts.
- Kiểm role `Admins` A không áp vào B.
- Kiểm tenant membership và resource ACL.
- Kiểm cache key/SCIM externalId namespace.

### B. OIDC/SAML provider tests

- Real OIDC test JWTs với đúng/wrong issuer, audience, signer, exp.
- Real SAML signed fixtures A/C với different keys và registrations.
- Wrong SAML audience/recipient giữ signature hợp lệ.
- Login callbacks sai state/nonce/InResponseTo bị từ chối.
- Không mock verification provider khi kết luận authN trust.

### C. Spring Boot HTTP integration

- `@SpringBootTest` + MockMvc/WebTestClient tùy stack.
- Test filters/callback URL/security context/saved request.
- Đăng nhập A hợp lệ rồi request resources B, verify denial.
- Đăng nhập B hợp lệ với cùng email/sub text.
- Account switching/logout/revoke session cases.
- Data access/GraphQL/cache integration với fixtures thực.

### D. Staging E2E

- Hai IdPs test có metadata/certificates độc lập.
- Browser HTTPS, redirect URI/ACS, cookies và proxies thật.
- IdP A/B login cùng browser/different browser profiles.
- Cross-tenant API calls qua UI/network.
- Concurrent auth flows/multi-node.
- Certificate rotation, disabled users và group changes.
- Download/export/async callbacks.
- Không dùng production keys hoặc PII thật.

**Các tầng bổ sung, không thay thế nhau.** Một unit test `with(user("A"))` không chứng minh JWKS/Signature verification; một signed Response bị từ chối vì signature không chứng minh tenant data isolation.

## 34. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Cách chẩn đoán |
| --- | --- | --- |
| User B đăng nhập thành A | Lookup chỉ theo email/username/sub | Audit external binding key với issuer |
| B bị deny login khi email trùng A | Unique email/JIT policy quá cứng | Tách contact uniqueness và identity binding |
| Hai IdPs login được nhưng cùng authorities | Group mapper không scope issuer/tenant | Kiểm group identity mappings |
| Admin A thấy tài liệu B | ROLE_ADMIN global hoặc repo query thiếu tenant | Kiểm ACL và query predicates |
| OIDC callback A nhận code B | State/registration mix-up | Kiểm saved auth request, issuer, token endpoint |
| JWT của API X vào API Y | Audience validator thiếu | Kiểm `aud` và resource server config |
| SAML B vào ACS A được accepted | RelyingPartyRegistration/trust resolver sai | Kiểm issuer/cert/audience/destination |
| Same NameID từ hai IdPs tạo một account | SAML subject không scoped | Thêm issuer/qualifier/format |
| Partner nhận global Admin vì group Admins | Auto-role mapping theo group name | Cấp quyền theo tenant/directory group ID |
| Tenant A session dùng lại sau login B | SecurityContext/session isolation sai | Test tab switching/rotation |
| Logout không thu hồi token | IdP logout != app revocation | Current account gate/token invalidation |
| Cache A rò sang B | Key thiếu tenant/account scope | Warm-cache cross-tenant test |
| GraphQL node ID cho phép cross tenant | Nested resolver bỏ authorization | Object-level ACL ở từng resolver |
| Host header giả đổi issuer | Dynamic resolver tin header client | Trusted proxy Host/Forwarded sanitization |
| JIT tạo 2 accounts cho một subject | Race và thiếu unique constraint | Transaction + unique identity binding |
| Email recycled khôi phục tài khoản cũ | Auto-link bằng email | Disable fallback, authoritative migration |
| Account chuyển tenant còn quyền cũ | Stale memberships/session roles | securityEpoch và live checks |
| SAML negative case sai audience chỉ fail signature | Fixture bị sửa sau ký | Tạo wrong-audience rồi ký lại |
| Unknown issuer được fetch JWKS tự động | Dynamic issuer không allow-list | Trusted issuer registry |
| SAML/oidc validation pass nhưng user vẫn bị 403 | App account/tenant/resource denied | Phân biệt authN vs authZ |

## 35. Các bài tập tự kiểm tra có đáp án

**Câu 1.** Hai OIDC issuers cùng `sub=007`. Có coi là một account không?

**Đáp án:** không. OIDC identity key là `(iss,sub)`, không dùng `sub` đơn lẻ.

**Câu 2.** User A và B cùng email đã verified ở hai IdPs. Có tự gộp không?

**Đáp án:** không. Email mutable/có thể được tái sử dụng; verified email không chứng minh same historical subject.

**Câu 3.** User B được IdP B xác thực hợp lệ nhưng request tài nguyên tenant A, đây là lỗi AuthN hay AuthZ?

**Đáp án:** AuthZ/membership/resource ACL phải deny; không phải chữ ký B sai.

**Câu 4.** Signed SAML Response của IdP B gửi vào registration A có được accepted không nếu NameID trùng?

**Đáp án:** không. Registration, issuer, signing cert trust, audience và recipient phải phù hợp.

**Câu 5.** SAML wrong Audience test có signature invalid thì chứng minh AudienceRestrictionValidator hoạt động không?

**Đáp án:** không chắc. Cần signed valid fixture với wrong audience để isolate rule.

**Câu 6.** Một IdP phục vụ hai tenants. Issuer valid có đủ để mở mọi tenant không?

**Đáp án:** không. Membership/ACL phải kiểm riêng.

**Câu 7.** Tenant A cho đăng nhập qua IdP A và C. Người từ C cùng email A có tự thành nhân viên A không?

**Đáp án:** không; external identity binding riêng, approved linking nếu cần.

**Câu 8.** IdP B có group `Admins`, user được cấp hệ thống `ROLE_SUPER_ADMIN` có hợp lý không?

**Đáp án:** không mặc định. Group phải scope issuer/tenant, global admin do chính sách riêng.

**Câu 9.** Trong OAuth2 multi-client, callback `registrationId` do browser cung cấp có đủ xác nhận token issuer không?

**Đáp án:** không. Phải correlate với saved authorization request, validate state/nonce/issuer/audience và exact provider endpoints.

**Câu 10.** RFC 9207 giúp chống điều gì?

**Đáp án:** Authorization Server mix-up bằng tham số `iss` trong authorization response, được client so với expected issuer khi áp dụng.

**Câu 11.** JWT issuer A valid nhưng audience dành API khác. Có cho API hiện tại sử dụng không?

**Đáp án:** không. Validate audience/scope/token type/resource server trust.

**Câu 12.** Tenant header do user gửi có thể tự cấp quyền không?

**Đáp án:** không. Nó chỉ là target context; server phải check membership/grants và resource tenant.

**Câu 13.** User A thuộc hai tenants A/B, có được truy cập B không?

**Đáp án:** có thể nếu membership và resource-specific permission ở B hợp lệ; không phải mọi cross-tenant request đều sai.

**Câu 14.** Vì sao cache key chỉ `documentId` có nguy cơ?

**Đáp án:** dữ liệu tenant A có thể được trả ở B nếu không scope account/tenant và thiếu authorization trên cache hit.

**Câu 15.** Đổi email nhưng issuer+subject giữ nguyên, có tạo account mới không?

**Đáp án:** không, cập nhật profile; binding stable vẫn cùng account.

**Câu 16.** IdP-initiated SAML SSO có InResponseTo không?

**Đáp án:** có thể không có vì unsolicited. Nếu bật phải có trust/tenant/RelayState policy riêng; không bỏ correlation của SP-initiated.

**Câu 17.** SAML NameID transient nên được lưu làm account key lâu dài không?

**Đáp án:** không, vì tính ngắn hạn/không ổn định.

**Câu 18.** Browser login A rồi B, tab A có nên tiếp tục sử dụng quyền A cũ không?

**Đáp án:** không tự động; server phải xử lý principal switch và revalidate context/tenant mỗi request.

**Câu 19.** Vì sao test token sai signature không chứng minh cross-tenant ACL?

**Đáp án:** request bị chặn ở AuthN trước khi business authorization chạy. Cần valid B login rồi request A resource tồn tại.

**Câu 20.** Một user C có cùng email với A sau account deletion. Có nên tự phục hồi quyền A không?

**Đáp án:** không. Rehire/migration cần verified account linking và approval, không email fallback.

**Câu 21.** CAS servers khác nhau có thể cùng username không?

**Đáp án:** có, phải scope CAS server/directory namespace và xác minh ticket service đúng.

**Câu 22.** Kerberos user `alex@A.REALM` và `alex@B.REALM` có thể gộp vì cùng alex không?

**Đáp án:** không. Realm là một phần của principal namespace.

**Câu 23.** Tenant admin A và system admin có phải cùng quyền không?

**Đáp án:** không. Tenant-local admin không tự có quyền hệ thống hoặc tenant khác.

**Câu 24.** Nếu người dùng hợp pháp là member cả A/B, hệ thống nên luôn từ chối chọn B vì “cross tenant” không?

**Đáp án:** không. Cần allow theo active membership và per-resource ACL, không hardcode deny mọi chuyển tenant.

**Câu 25.** Đã kiểm frontend ẩn tenant B đối với user A thì backend an toàn chưa?

**Đáp án:** chưa. API, repository và data access phải thực thi authorization, không dựa vào UI.

## 36. Checklist trước release

- [ ] Trust registry có danh sách **IdPs/issuers/entityIDs** được phép.
- [ ] Mỗi OIDC ClientRegistration có issuer, clientId, redirect URI, JWKS/discovery nguồn đáng tin.
- [ ] OIDC ID Token verify signature, issuer, audience, nonce/state và các điều kiện applicable.
- [ ] OIDC account lookup dùng **iss+sub**, không email/username/sub đơn lẻ.
- [ ] Authorization response issuer mix-up được kiểm theo RFC9207 hoặc countermeasure profile được hỗ trợ.
- [ ] Không dùng ID Token như API access token; Resource Server kiểm aud dành đúng API.
- [ ] SAML registrations có independent trusted verification credentials.
- [ ] Signed SAML Responses của IdP khác không được accepted chéo.
- [ ] SAML issuer/audience/destination/recipient/time/InResponseTo được test.
- [ ] SAML NameID được scoped issuer/format/qualifiers; transient không làm stable ID.
- [ ] CAS/Kerberos/LDAP identity namespaces được tách, không bỏ realm/domain.
- [ ] Local app accounts dùng immutable ID, external identities có uniqueness constraints.
- [ ] Không auto-merge qua email/username; linking có verified proof và audit.
- [ ] Tenant membership độc lập với issuer login trust.
- [ ] Permissions scoped theo tenant/resource, không có implicit global ADMIN.
- [ ] API/controller/repository/cache/search/export đều kiểm tenant scope.
- [ ] Tenant input/Host/Forwarded headers không được coi là authority.
- [ ] Browser session/account switching không reuse roles của principal trước.
- [ ] Security epoch/session/token revocation khi membership chuyển/disable.
- [ ] Multi-node, concurrent callbacks, replay và provisioning race đã test nếu áp dụng.
- [ ] Fixtures có intentionally colliding sub/email/NameID/group names.
- [ ] Negative protocol fixtures được ký hợp lệ để isolate issuer/audience checks.
- [ ] Cross-tenant authorization tests sử dụng **valid logged-in user** và resource thực sự tồn tại ở tenant khác.
- [ ] Có positive controls A→A, B→B và dual-membership nếu được cho phép.
- [ ] Không log raw SAMLResponse, JWT, authorization code, session IDs, PII quá mức.
- [ ] Có monitor unknown issuer, identity collisions, cross-tenant denies và permission revocation latency.
- [ ] Staging E2E kiểm nhiều IdPs, browsers, proxy và certificate rotation.
- [ ] QA report ghi rõ AuthN/trust, identity binding, AuthZ/data isolation, session và E2E coverage.

## 37. Kết luận

**SSO đa IdP và đa tenant chỉ an toàn khi ba ranh giới được kiểm chứng độc lập:**

1. **IdP trust boundary:** OIDC token/authorization response hoặc SAML Response phải đến từ **đúng issuer, đúng client/registration, đúng audience/recipient**, ký bởi đúng khóa được tin cậy.
2. **Identity binding boundary:** user được map qua **scoped external identity** tới đúng app account, không dựa email, username, NameID hoặc subject string thiếu phạm vi.
3. **Tenant/data authorization boundary:** account chỉ được xem tenant và resources có membership/grants đang còn hiệu lực; global role, request tenant, UI selection và cache không được thay ACL.

Khi kiểm thử, phải có cả **positive path** (A vào A, B vào B) và **negative path** (B vào A, issuer/signer mix-up, same email/sub collision, group Admins trùng, stale session/cache). Một SSO provider chấp nhận token hợp lệ chưa chứng minh backend không rò dữ liệu giữa tenants. Và một MockMvc test với `@WithMockUser` không chứng minh token/SAML trust validation.

### Tài liệu chuẩn và framework tham khảo

1. OpenID Connect Core 1.0, Claim Stability and Uniqueness — cặp `iss+sub`: https://openid.net/specs/openid-connect-core-1_0.html
2. RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification (mix-up): https://www.rfc-editor.org/rfc/rfc9207.html
3. Spring Security — OAuth2 Login Core Configuration, multiple registrations và redirect URI: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
4. Spring Security — OAuth2 Login Advanced, OidcUserService: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
5. Spring Security — SAML2 Login Overview, RelyingPartyRegistration và trust: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
6. Spring Security — SAML2 Authentication/validation: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
7. Spring Security — OAuth2 Resource Server Multi-tenancy: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html
8. Spring Security — Resource Server JWT, issuer/audience validation: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
9. OASIS SAML 2.0 Core, Issuer, NameID, Audience and SubjectConfirmation: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
10. IETF RFC 7643 — SCIM Core Schema, id/externalId: https://www.rfc-editor.org/rfc/rfc7643.html
11. OWASP — IDOR prevention: https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html
12. OWASP — Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
