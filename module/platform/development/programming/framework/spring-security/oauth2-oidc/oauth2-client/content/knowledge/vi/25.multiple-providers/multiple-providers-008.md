# 25.8. Khác biệt scopes, claims, UserInfo và logout giữa các provider

## 1. Một ứng dụng đăng nhập qua nhiều OpenID Providers

Trong **Spring Security OAuth 2.0 OIDC Client**, ứng dụng có thể cho người dùng đăng nhập qua nhiều **OpenID Providers (OP)**: SSO doanh nghiệp, một provider dành cho đối tác, Google Identity hoặc Microsoft Entra ID. Mỗi nút “Đăng nhập” thoạt nhìn giống nhau, nhưng mỗi OP có thể khác nhau về **scope**, **claim**, **UserInfo**, **định danh người dùng** và **logout**.

~~~text
                          Spring Boot OIDC Client
                                  |
            +---------------------+---------------------+
            |                     |                     |
       Corporate OP           Partner OP           Workforce OP
       issuer A                issuer B             issuer C
       scope set A             scope set B          scope set C
       ID Token A              ID Token B           ID Token C
       UserInfo A              UserInfo B           UserInfo C
       logout A                logout B             logout C
            |                     |                     |
            +---------------------+---------------------+
                                  |
                     Claims normalization + policy
                                  |
                       Internal account / session
~~~

Một lỗi thiết kế phổ biến là dùng các claims của provider A làm chuẩn tuyệt đối:

~~~java
// PHẢN VÍ DỤ: email và role claim không đồng nhất giữa providers.
String localUserId = oidcUser.getEmail();
boolean isAdmin = oidcUser.getClaimAsStringList("roles")
    .contains("admin");
~~~

Code này có thể gây **account collision**, **NullPointerException**, **wrong role assignment** hoặc vô tình gộp danh tính của hai người khác nhau.

### Mục tiêu của bài

Sau khi học, bạn có thể:

1. Phân biệt **OIDC Core standards** và **provider-specific behavior**.
2. Hiểu yêu cầu scope khác scope thực tế được cấp; claim khác quyền ứng dụng.
3. Nhận diện claim nằm trong ID Token hay UserInfo, đặc biệt quy tắc so khớp `sub`.
4. Chuẩn hóa danh tính theo **issuer + subject**, có tính đến pairwise subject.
5. Cấu hình nhiều `ClientRegistration` và adapter provider-specific trong Spring Security.
6. Chọn chính sách logout đúng khả năng của từng OP.
7. Thiết kế ma trận integration tests cho provider claims, scopes và phiên đăng nhập.

> **Phạm vi:** ví dụ sử dụng Spring Security Servlet/MVC, có đối chiếu WebFlux. Các ví dụ về Google, Microsoft Entra ID hoặc Keycloak không khẳng định mọi tenant/provider version đều trả các claims ấy. Phải đối chiếu metadata và hợp đồng của mỗi deployment.

## 2. Các lớp dữ liệu cần tách rõ

| Thành phần | Vai trò |
| --- | --- |
| `ClientRegistration` | Cấu hình client ID, issuer/provider, endpoints, grant, scopes, redirect URI |
| `OAuth2AuthorizedClient` | Authorization result, chứa Access Token/Refresh Token của registration và principal |
| `OidcIdToken` | ID Token được OP phát, dùng trong OIDC authentication |
| `OidcUserInfo` | Claims bổ sung từ UserInfo Endpoint |
| `OidcUser` | OIDC principal do Spring Security xây dựng |
| `OAuth2AuthenticationToken` | Authentication và registration ID của lần OAuth2/OIDC Login |
| `GrantedAuthority` | Quyền ứng dụng chấp nhận theo policy |
| `HttpSession` / `WebSession` | Phiên của Relying Party (RP) |
| OP SSO session | Phiên của nhà cung cấp danh tính |

ID Token, Access Token và Refresh Token không có cùng mục đích:

~~~text
Authorization Code -> Token Endpoint
    ID Token      : xác thực OIDC user cho client
    Access Token  : gọi UserInfo hoặc Resource Server
    Refresh Token : xin Access Token mới khi được cấp
~~~

**Không dùng ID Token làm Bearer Token cho API nghiệp vụ** chỉ vì nó là JWT, và không coi JWT Access Token dành cho một Resource Server là ID Token hợp lệ cho login.

## 3. ClientRegistration là ranh giới provider

Ví dụ:

~~~text
registrationId = corporate
clientId       = portal-corporate
issuer         = https://sso.corp.example.net/realms/main

registrationId = partner
clientId       = portal-partner
issuer         = https://login.partner.example.org
~~~

`registrationId` là khóa trong Spring Security, **không** phải OAuth2 scope, JWT `aud`, OP user ID hoặc provider ID. Một provider có thể có nhiều client registrations với client IDs, scopes hoặc redirect URIs khác nhau.

### 3.1. Cấu hình có thể thay đổi theo provider

| Thuộc tính | Tác dụng |
| --- | --- |
| `issuer-uri` | Định nghĩa trust boundary, hỗ trợ Discovery |
| `authorization-uri` | Authorization Endpoint |
| `token-uri` | Token Endpoint |
| `jwk-set-uri` | Nguồn public keys để xác minh chữ ký |
| `user-info-uri` | UserInfo Endpoint nếu được cung cấp |
| `client-id` / `client-secret` | Danh tính/credential client |
| `scope` | Scopes xin trong authorization flow |
| `redirect-uri` | Callback phải đăng ký với OP |
| Provider metadata | Khả năng logout, supported scopes, claims, algorithms |

Đừng sao chép cấu hình của provider A sang B chỉ bằng cách thay issuer. Provider B có thể dùng client authentication method khác, thiếu UserInfo Endpoint hoặc yêu cầu một redirect URI khác.

## 4. Scope là yêu cầu, không phải bảo đảm có quyền

Ví dụ request:

~~~http
GET /authorize?response_type=code&
  client_id=portal-corporate&
  scope=openid%20profile%20email&
  redirect_uri=https%3A%2F%2Fportal.example.net%2Flogin%2Foauth2%2Fcode%2Fcorporate&
  state=RANDOM_STATE&
  code_challenge=RANDOM_CHALLENGE&
  code_challenge_method=S256
~~~

Scope ở đây là **requested scopes**. OP có thể chấp thuận, áp dụng consent, từ chối hoặc cấp một tập con theo chính sách.

### 4.1. OIDC standard scopes

| Scope | Ý nghĩa | Không được suy diễn |
| --- | --- | --- |
| `openid` | Bắt đầu OIDC authentication | Không phải quyền gọi API nghiệp vụ |
| `profile` | Yêu cầu profile claims | Không bảo đảm trả đủ dữ liệu |
| `email` | Yêu cầu `email`, `email_verified` | Không biến email thành unique user ID |
| `address` | Yêu cầu address claim | Không bảo đảm có dữ liệu |
| `phone` | Yêu cầu phone claims | Không bảo đảm số điện thoại verified |
| `offline_access` | Yêu cầu quyền truy cập offline | Không bảo đảm OP cấp Refresh Token |

Các scope như:

~~~text
reports.read
calendar.events.read
api://resource-id/report.read
https://api.example.net/auth/reports.read
~~~

là **provider/resource-specific API scopes**. Không xem hai chuỗi `read` ở hai Authorization Servers là cùng permission.

### 4.2. Requested vs granted scopes

~~~text
Authorization request:
  openid profile email calendar.read

Granted scopes:
  openid profile email

=> Client KHÔNG được kết luận có calendar.read.
~~~

Khi cần, Spring Security cho phép đọc `OAuth2AuthorizedClient.getAccessToken().getScopes()`. Tuy nhiên, **Resource Server vẫn là nơi kiểm tra scope/audience/policy cuối cùng**.

### 4.3. Scope không phải local role

`ROLE_ADMIN` của Portal không tạo `reports.write` scope ở Access Token. Ngược lại, Access Token có `reports.read` không chứng minh user là admin của Portal. Hai mô hình phải có authorization policy riêng.

## 5. OIDC scopes yêu cầu những claims nào?

| Scope | Một số claims tiêu chuẩn có thể yêu cầu |
| --- | --- |
| `profile` | `name`, `given_name`, `family_name`, `middle_name`, `nickname`, `preferred_username`, `profile`, `picture`, `website`, `gender`, `birthdate`, `zoneinfo`, `locale`, `updated_at` |
| `email` | `email`, `email_verified` |
| `address` | `address` |
| `phone` | `phone_number`, `phone_number_verified` |

Theo OpenID Connect Core, **OP được phép không trả một số claims đã yêu cầu** vì privacy hoặc không có dữ liệu. Không tự xem thiếu `email` là lỗi giao thức trong mọi trường hợp.

Ví dụ:

~~~json
{
  "sub": "user-123",
  "name": "Demo User",
  "email": "user@example.net",
  "email_verified": true
}
~~~

và:

~~~json
{
  "sub": "person-890",
  "preferred_username": "person890"
}
~~~

đều có thể xuất hiện trong các hợp đồng khác nhau. Nếu email là yêu cầu bắt buộc của sản phẩm, ứng dụng phải **yêu cầu bổ sung/xác minh** hoặc từ chối onboarding theo policy; không đặt `email_verified=true` khi claim vắng mặt.

### 5.1. `claims` request parameter

OIDC còn hỗ trợ yêu cầu claims cụ thể:

~~~json
{
  "userinfo": {
    "given_name": null,
    "email": {"essential": true}
  },
  "id_token": {
    "auth_time": {"essential": true}
  }
}
~~~

Không phải provider nào cũng hỗ trợ `claims` parameter. Discovery `claims_parameter_supported` giúp đánh giá. Kể cả khi OP hỗ trợ, app vẫn cần business policy cho trường hợp claim thiết yếu không xuất hiện.

## 6. So sánh các provider thường gặp

| Kiểu provider | Claims có thể gặp | Lưu ý |
| --- | --- | --- |
| Generic OIDC | `iss`, `sub`, `aud`, profile/email nếu cấp | Identity theo issuer + subject |
| Google Identity | `sub`, `email`, `email_verified`, `hd` khi phù hợp | Dùng sub làm ID, hd hỗ trợ Workspace policy |
| Microsoft Entra ID | `sub`, `tid`, `oid`, `preferred_username`, optional `roles`/`groups` | Tenant isolation, pairwise sub, group overage |
| Keycloak | OIDC claims và custom mapper roles/groups | Claim placement tùy protocol mapper |
| Partner OIDC | Custom `employee_id`, `org_id`, `entitlements` | Cần schema/trust policy rõ ràng |
| OAuth2-only provider | User endpoint `id`/`login` nhưng không có ID Token | Không ép vào OIDC flow |

### 6.1. Google: email không phải stable identifier

Google khuyến cáo dùng `sub` làm account identifier thay vì email, vì email có thể thay đổi. Nếu muốn giới hạn Google Workspace domain, không chỉ so suffix `@company.example` mà cần kiểm tra hosted-domain claim `hd` và membership policy phù hợp theo tài liệu provider.

### 6.2. Microsoft Entra: `tid`, `oid`, `sub` khác nhau

- `tid`: tenant ID, không phải ID người dùng.
- `oid`: object ID của người dùng trong tenant, khi có claim.
- `sub`: subject, có thể là **pairwise identifier** theo client/application.
- `preferred_username`: tiện để hiển thị, có thể thay đổi.
- `groups`: có thể vắng mặt vì **group overage**; khi cần có thể phải truy vấn Microsoft Graph theo quyền được cấp.

Không áp `tid`/`oid` lên các OP khác: đây không phải OIDC Core mandatory claims.

### 6.3. Keycloak: role shape không đồng nhất

Ví dụ một realm có thể trả:

~~~json
{
  "realm_access": {
    "roles": ["report-reader"]
  },
  "resource_access": {
    "portal-client": {
      "roles": ["team-editor"]
    }
  }
}
~~~

Nhưng claim có thể được đưa vào **Access Token** chứ không nằm trong **ID Token** hoặc UserInfo. Realm/client scope/protocol mapper quyết định điều đó. Không dùng Access Token dành cho API khác như một OIDC principal mà không có contract/validation thích hợp.

### 6.4. Partner custom claim

~~~json
{
  "sub": "partner-481",
  "employee_id": "E-102",
  "org_id": "partner-a",
  "entitlements": ["purchase-orders.read"]
}
~~~

Với claim không tiêu chuẩn cần định nghĩa rõ: phát ở đâu, kiểu dữ liệu, độ ổn định, ai kiểm soát, privacy impact và business authorization mapping. Không dùng `employee_id` làm global ID nếu chưa namespace theo issuer.

## 7. ID Token phải được xác minh theo đúng ClientRegistration

OIDC authentication thường cần kiểm tra:

- Chữ ký và thuật toán ký được phép; không chấp nhận `alg=none`.
- `iss` đúng issuer đã cấu hình.
- `aud` chứa đúng client ID; xử lý `azp` nếu điều kiện protocol yêu cầu.
- `exp`, `iat`, clock skew và các điều kiện thời gian.
- `nonce` theo flow/authorization request khi cần.
- `auth_time`, `at_hash`/`c_hash` khi áp dụng theo flow/policy.

Phản ví dụ:

~~~java
// KHÔNG DÙNG: decode payload không đồng nghĩa xác minh token.
Map<String, Object> claims = decodeJwtWithoutVerification(rawJwt);
String userId = claims.get("sub").toString();
createAuthenticatedSession(userId);
~~~

**Provider adapter phải chạy sau bước ID Token validation**, không được sửa issuer hoặc subject cho khớp một giá trị “trông giống”.

### 7.1. ID Token khác Access Token

Access Token có thể là opaque string hoặc JWT có `sub` và `scope`, nhưng dành cho Resource Server. Không dùng JWT Access Token như ID Token chỉ vì cùng chứa user ID.

## 8. Stable user identity = issuer + subject

Ví dụ:

~~~text
Provider A:
  iss = https://sso.corp.example.net
  sub = 42

Provider B:
  iss = https://login.partner.example.org
  sub = 42
~~~

Hai `sub=42` **không tự là cùng người**. OIDC subject là ID trong phạm vi issuer. Khóa external identity nên dựa trên:

~~~text
(issuer, subject)
~~~

Một schema logic:

~~~text
user_account
  id = internal-user-100
  status = ACTIVE

external_identity
  internal_user_id = internal-user-100
  issuer = https://sso.corp.example.net
  subject = corp-55
  registration_id = corporate

external_identity
  internal_user_id = internal-user-100
  issuer = https://login.partner.example.org
  subject = partner-992
  registration_id = partner
~~~

Hai external identities chỉ được liên kết vào cùng internal account khi **account linking workflow đã được xác minh**.

### 8.1. Không auto-link bằng email

Email có thể đổi, bị tái sử dụng, chưa verified hoặc thuộc nhiều providers. Ngay cả khi cả hai providers trả `email_verified=true`, điều đó không chứng minh người dùng đã đồng ý liên kết hai tài khoản vào một.

### 8.2. Pairwise subject

Một OP có thể phát:

~~~text
Same OP, same human:
  Portal client -> sub = pairwise-123
  Mobile client -> sub = pairwise-789
~~~

Không tự merge bằng email. Nếu cần account correlation giữa các client IDs, dùng cơ chế approved identity linking hoặc provider-specific stable identifiers theo contract.

### 8.3. Registration context

Tổ hợp issuer + sub thường là nền tảng OIDC identity. Khi dùng pairwise subject, multi-tenant, nhiều client IDs hoặc account linking phức tạp, có thể cần lưu thêm registration/client context. Chọn uniqueness constraint theo privacy/identity semantics của OP.

## 9. UserInfo Endpoint là gì?

UserInfo là endpoint OIDC được bảo vệ, RP dùng **Access Token** để lấy thêm claims nếu provider hỗ trợ.

~~~mermaid
sequenceDiagram
    autonumber
    actor Browser
    participant RP as Spring Security Client
    participant OP as OpenID Provider
    participant UI as UserInfo Endpoint
    Browser->>RP: Bắt đầu OIDC Login
    RP-->>Browser: Authorization redirect
    Browser->>OP: Authenticate và consent
    OP-->>Browser: code + state
    Browser->>RP: OAuth2 callback
    RP->>OP: Token request
    OP-->>RP: ID Token + Access Token
    RP->>RP: Validate ID Token
    opt UserInfo được gọi theo cấu hình
        RP->>UI: Bearer Access Token
        UI-->>RP: UserInfo claims
        RP->>RP: Kiểm tra sub UserInfo == sub ID Token
    end
    RP->>RP: Xây OidcUser và áp dụng local policy
    RP-->>Browser: Local session + redirect
~~~

### 9.1. ID Token và UserInfo khác nhau

| | ID Token | UserInfo |
| --- | --- | --- |
| Nguồn | Token Endpoint | UserInfo Endpoint |
| Mục đích | OIDC authentication | Claims bổ sung |
| Dạng | JWT ký, có thể mã hóa | Thường JSON, có thể signed/encrypted JWT |
| Credentials | Token exchange | Access Token gửi tới UserInfo |
| `sub` | Subject đã xác minh | Bắt buộc, phải khớp ID Token |
| Freshness | Khi token phát hành | Khi UserInfo response được trả |

### 9.2. Quy tắc `sub` là bắt buộc

OIDC Core yêu cầu `sub` trong UserInfo **MUST khớp chính xác** với `sub` trong ID Token. Nếu khác, **không sử dụng các giá trị UserInfo**:

~~~text
ID Token:  sub = alice-123
UserInfo:  sub = bob-456, email = bob@example.org

=> Reject/discard UserInfo data.
~~~

HTTP 200 và JSON có vẻ hợp lệ không chứng minh UserInfo thuộc cùng end-user. Đây là biện pháp chống **token substitution**.

### 9.3. UserInfo thiếu requested claim không mặc định là lỗi

Provider có thể chỉ trả:

~~~json
{
  "sub": "person-890",
  "name": "Demo User"
}
~~~

dù app yêu cầu `email`. Nếu email bắt buộc, app phải yêu cầu bổ sung và xác minh riêng hoặc từ chối workflow theo policy; không tự tạo địa chỉ giả.

### 9.4. UserInfo không phải Directory API

Provider có thể không trả groups/roles trong UserInfo. Dữ liệu đó có thể đến từ Directory/Graph API, cần Access Token đúng audience/scope, consent và rate limits. Không gọi API admin bằng Client Credentials rộng chỉ để lấp missing claim mà chưa có authorization policy.

## 10. Discovery metadata: tra cứu khả năng thực tế

Ví dụ metadata:

~~~json
{
  "issuer": "https://id.example.net",
  "authorization_endpoint": "https://id.example.net/authorize",
  "token_endpoint": "https://id.example.net/token",
  "jwks_uri": "https://id.example.net/jwks",
  "userinfo_endpoint": "https://id.example.net/userinfo",
  "scopes_supported": ["openid", "profile", "email"],
  "claims_supported": ["sub", "name", "email"],
  "end_session_endpoint": "https://id.example.net/connect/endsession"
}
~~~

Đây là **giá trị minh họa**, không phải endpoint để gọi thực tế.

| Metadata | Ý nghĩa |
| --- | --- |
| `issuer` | Issuer phải khớp ID Token |
| `authorization_endpoint` | Nơi browser bắt đầu authorize |
| `token_endpoint` | Nơi đổi code/refresh token |
| `jwks_uri` | Signing keys của issuer |
| `userinfo_endpoint` | UserInfo nếu có |
| `scopes_supported` | Các scopes được quảng bá |
| `claims_supported` | Claims OP có thể cấp, không bảo đảm có cho mọi user |
| `claims_parameter_supported` | Có hỗ trợ claims parameter hay không |
| `end_session_endpoint` | RP-Initiated Logout capability |
| `backchannel_logout_supported` | Back-Channel Logout capability |
| `backchannel_logout_session_supported` | OP có thể hỗ trợ `sid` |

**Không tự tạo UserInfo/logout URL bằng cách nối issuer với `/userinfo` hoặc `/logout`** nếu OP không công bố hoặc không có provider-specific contract đáng tin.

## 11. Cấu hình nhiều provider trong Spring Boot

Ví dụ Spring Boot 3.x và Spring Security 6.x:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate-oidc
            client-id: ${CORPORATE_OIDC_CLIENT_ID}
            client-secret: ${CORPORATE_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
          partner:
            provider: partner-oidc
            client-id: ${PARTNER_OIDC_CLIENT_ID}
            client-secret: ${PARTNER_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
          workforce:
            provider: workforce-oidc
            client-id: ${WORKFORCE_OIDC_CLIENT_ID}
            client-secret: ${WORKFORCE_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
        provider:
          corporate-oidc:
            issuer-uri: https://sso.corp.example.net/realms/main
          partner-oidc:
            issuer-uri: https://login.partner.example.org
          workforce-oidc:
            issuer-uri: https://login.microsoftonline.com/00000000-0000-0000-0000-000000000000/v2.0
~~~

Các URLs, GUIDs, secret names đều là **placeholders**. Mỗi redirect URI phải được đăng ký đúng tại OP; client credentials lấy từ secret manager/environment được bảo vệ, không commit vào source.

### 11.1. Provider ID không phải registration ID

~~~text
registrationId = corporate
providerId = corporate-oidc
clientId = giá trị CORPORATE_OIDC_CLIENT_ID
~~~

Spring Security login initiation endpoints mặc định:

~~~text
/oauth2/authorization/corporate
/oauth2/authorization/partner
/oauth2/authorization/workforce
~~~

Callbacks:

~~~text
/login/oauth2/code/corporate
/login/oauth2/code/partner
/login/oauth2/code/workforce
~~~

### 11.2. Dependencies Servlet

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Spring Boot 4.x có thay đổi module/starter names; dùng BOM đúng version, không trộn Spring Security 6.x và 7.x.

## 12. SecurityFilterChain và trang chọn provider

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MultiProviderSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/signed-out", "/error")
                    .permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .loginPage("/login"))
            .build();
    }
}
~~~

`/login` phải là trang do app triển khai khi tùy biến login page. Các liên kết ví dụ:

~~~text
Đăng nhập Corporate -> /oauth2/authorization/corporate
Đăng nhập Partner   -> /oauth2/authorization/partner
Đăng nhập Workforce -> /oauth2/authorization/workforce
~~~

Không cho user tự đưa arbitrary issuer URL/JWKS URI rồi coi nó là provider đáng tin. Các registrations phải thuộc **server-side allowlist**.

### 12.1. Login CSRF và authorization response mix-up

Khi nhiều providers, Spring Security correlation qua `state`, authorization request repository và các kiểm tra OAuth2/OIDC là đặc biệt quan trọng. Không tự chọn registration theo query parameter callback mà bỏ qua registration gắn với request ban đầu.

## 13. Đọc registration, issuer và subject đã xác minh

~~~java
package com.example.web;

import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/identity")
    public IdentityView identity(
            OAuth2AuthenticationToken authentication) {

        String registrationId =
            authentication.getAuthorizedClientRegistrationId();
        OidcUser user = (OidcUser) authentication.getPrincipal();

        String issuer = user.getIdToken().getIssuer().toString();
        String subject = user.getSubject();

        return new IdentityView(registrationId, issuer, subject);
    }

    public record IdentityView(
            String registrationId, String issuer, String subject) {
    }
}
~~~

Ví dụ giả định endpoint chỉ chấp nhận **OIDC Login**. Nếu ứng dụng còn form login/OAuth2 Login không OIDC, phải kiểm tra Authentication/principal type trước khi cast. Không trả token/claim graph cho browser.

`authentication.getName()` không đủ làm **global account ID** nếu không mang issuer hoặc đã được custom name attribute. Giữ explicit issuer+sub từ ID Token đã verified.

## 14. Chuẩn hóa claims thành ExternalIdentity

~~~text
Verified OidcUser
   |
   v
Provider-specific normalizer
   +-- issuer + subject (bắt buộc)
   +-- email + verified (optional)
   +-- displayName (optional)
   +-- tenant/organization (provider-specific)
   |
   v
ExternalIdentity
   |
   v
Account linking + authorization policy
~~~

~~~java
package com.example.identity;

public record ExternalIdentity(
    String registrationId,
    String issuer,
    String subject,
    String displayName,
    String email,
    boolean emailVerified,
    String providerTenant) {
}
~~~

### 14.1. Normalizer minh họa

~~~java
package com.example.identity;

import java.util.Map;
import java.util.Objects;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

public final class ProviderIdentityNormalizer {

    public ExternalIdentity normalize(
            String registrationId, OidcUser verifiedUser) {

        Objects.requireNonNull(registrationId);
        Objects.requireNonNull(verifiedUser);

        String issuer =
            verifiedUser.getIdToken().getIssuer().toString();
        String subject = verifiedUser.getSubject();

        if (issuer.isBlank()
                || subject == null || subject.isBlank()) {
            throw new IllegalArgumentException(
                "Missing verified OIDC identity");
        }

        Map<String, Object> claims = verifiedUser.getClaims();

        String email = textClaim(claims, "email");
        boolean emailVerified =
            Boolean.TRUE.equals(claims.get("email_verified"));

        String displayName = textClaim(claims, "name");
        if (displayName == null) {
            displayName =
                textClaim(claims, "preferred_username");
        }

        String tenant = switch (registrationId) {
            case "workforce" -> textClaim(claims, "tid");
            case "corporate" -> textClaim(claims, "organization_id");
            default -> null;
        };

        return new ExternalIdentity(
            registrationId, issuer, subject,
            displayName, email, emailVerified, tenant);
    }

    private static String textClaim(
            Map<String, Object> claims, String name) {

        Object value = claims.get(name);
        return value instanceof String text && !text.isBlank()
            ? text : null;
    }
}
~~~

`organization_id` là **custom claim giả định**, chỉ có ý nghĩa khi provider thật phát theo hợp đồng được duyệt. `email_verified` chỉ được coi là true khi kiểu boolean đúng; không tự ép chuỗi `"true"` thành chứng thực nếu thiếu policy rõ ràng.

### 14.2. Identity normalization không tự cấp role

Một normalized profile **không quyết định** user được quản trị tenant hay truy cập tài liệu mật. Các quyền đó phải dựa trên account status, tenant membership, trusted role mapping và authorization service.

## 15. Tùy biến OidcUserService trong Spring Security

Với Servlet/OIDC, có thể dùng `OidcUserService` mặc định rồi áp dụng application policy theo registration:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ProviderAwareOidcConfig {

    @Bean
    OAuth2UserService<OidcUserRequest, OidcUser> providerUserService() {
        OidcUserService delegate = new OidcUserService();

        return request -> {
            OidcUser user = delegate.loadUser(request);
            String registrationId =
                request.getClientRegistration().getRegistrationId();

            if ("workforce".equals(registrationId)) {
                String tenantId = user.getClaimAsString("tid");

                // Production: expected tenant từ trusted configuration.
                if (!"APPROVED_TENANT_ID".equals(tenantId)) {
                    throw new OAuth2AuthenticationException(
                        new OAuth2Error("tenant_not_allowed"));
                }
            }

            return user;
        };
    }

    @Bean
    SecurityFilterChain chain(
            HttpSecurity http,
            OAuth2UserService<OidcUserRequest, OidcUser>
                    providerUserService) throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .userInfoEndpoint(info -> info
                    .oidcUserService(providerUserService)))
            .build();
    }
}
~~~

**Đây là một lựa chọn thay thế cho SecurityFilterChain phần 12**, không thêm cùng lúc hai chains match mọi request mà thiếu matcher/ordering. `"APPROVED_TENANT_ID"` là placeholder, không phải tenant thực; phải lấy từ trusted deployment config.

Không dùng adapter này để tự sửa issuer, subject, bỏ qua ID Token validation hoặc tự gọi arbitrary UserInfo URI.

### 15.1. OIDC UserService khác OAuth2 UserService

| Use case | Service |
| --- | --- |
| OIDC Login có ID Token | `OidcUserService` |
| OAuth2 Login thuần không có ID Token | `DefaultOAuth2UserService` |
| Reactive OIDC Login | Reactive OIDC UserService tương ứng |
| Provider Directory/Graph API | API adapter riêng với Access Token/permissions đúng |

Nếu provider không hỗ trợ OIDC thực sự, không ép vào `OidcUserService` bằng cách thêm `openid` tùy tiện.

## 16. Roles và GrantedAuthorities cần mapping theo provider

Ví dụ ba claim shapes:

~~~json
{"groups": ["finance-reporters"]}
~~~

~~~json
{"roles": ["Report.View"]}
~~~

~~~json
{"realm_access": {"roles": ["read-reports"]}}
~~~

Ba chuỗi không tự có cùng ý nghĩa. Cần mapping được duyệt:

~~~text
(issuer A, group finance-reporters) -> ROLE_REPORT_VIEWER
(issuer B, app role Report.View)     -> ROLE_REPORT_VIEWER
(issuer C, realm role read-reports)  -> ROLE_REPORT_VIEWER
~~~

### 16.1. Không tự chuyển raw claim thành ROLE_ADMIN

~~~java
// PHẢN VÍ DỤ nếu không kiểm tra trusted issuer/schema.
new SimpleGrantedAuthority("ROLE_" + rawRole);
~~~

Một `admin` role ở provider có thể chỉ quản trị một dịch vụ khác; không đồng nghĩa admin Portal.

### 16.2. GrantedAuthoritiesMapper minh họa

~~~java
package com.example.security;

import java.util.HashSet;
import java.util.Set;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.authority.mapping.GrantedAuthoritiesMapper;
import org.springframework.security.oauth2.core.oidc.user.OidcUserAuthority;

@Configuration
public class RoleMappingConfig {

    @Bean
    GrantedAuthoritiesMapper providerRoles() {
        return authorities -> {
            Set<GrantedAuthority> mapped = new HashSet<>(authorities);

            for (GrantedAuthority authority : authorities) {
                if (!(authority instanceof OidcUserAuthority oidc)) {
                    continue;
                }

                String issuer =
                    oidc.getIdToken().getIssuer().toString();
                Object raw = oidc.getAttributes().get("app_roles");

                if ("https://sso.corp.example.net/realms/main"
                        .equals(issuer)
                        && raw instanceof java.util.Collection<?> roles
                        && roles.contains("report-reader")) {
                    mapped.add(new SimpleGrantedAuthority(
                        "ROLE_REPORT_VIEWER"));
                }
            }
            return mapped;
        };
    }
}
~~~

`app_roles` là **custom claim minh họa** của một corporate OP. Gắn mapper vào OAuth2 Login DSL:

~~~java
.oauth2Login(oauth2 -> oauth2
    .userInfoEndpoint(info -> info
        .userAuthoritiesMapper(providerRoles)))
~~~

Đây là DSL fragment, cần injection `providerRoles` đúng bean và tránh trùng SecurityFilterChain. Không mặc định vai trò luôn có trong OIDC principal nếu OP chỉ phát ở Access Token hoặc một API khác.

### 16.3. Group overage và role freshness

Một số OP như Microsoft Entra có thể không nhúng toàn bộ group IDs trong token. **Không có `groups` claim không chắc nghĩa là user không thuộc nhóm nào.** Nếu quyền phụ thuộc group memberships, phải có API query/caching/retry/fail-closed policy được duyệt.

## 17. Phân loại claim theo mục đích

| Claim | Hiển thị | Identity key | Authorization |
| --- | --- | --- | --- |
| `iss` | Ít khi | **Có, cùng sub** | Trusted issuer boundary |
| `sub` | Ít khi | **Có, cùng issuer** | Theo internal account mapping |
| `email` | Có | **Không** | Không mặc định |
| `email_verified` | Có thể | Không | Không thay role/MFA |
| `name` | Có | Không | Không |
| `preferred_username` | Có | Không | Không |
| `tid` (Entra) | Có thể | Tenant context | Tenant allowlist |
| `oid` (Entra) | Ít khi | Provider-specific stable identifier | Enterprise policy |
| `hd` (Google) | Có thể | Không | Có thể hỗ trợ Workspace domain policy |
| `groups`/`roles` | Có thể | Không | Chỉ theo trusted issuer/schema/map |
| `sid` | Không | Không | Session correlation/logout |

Không lưu mọi claims vì “phòng khi cần”; chúng có thể chứa PII hoặc security-sensitive group memberships. Áp dụng data minimization và retention policy.

## 18. Logout: một từ, nhiều phiên khác nhau

~~~text
Browser
  +-- Portal local session
  +-- Corporate OP SSO session
  +-- Partner OP SSO session
  +-- Workforce OP SSO session
  +-- OAuth2 Authorized Client tokens
~~~

Logout ở Portal **không mặc nhiên** kết thúc các trạng thái khác.

| Cơ chế | Ai khởi tạo | Kết quả |
| --- | --- | --- |
| Local Logout | Browser/RP | Invalidate RP local session |
| RP-Initiated Logout | RP chuyển browser đến OP | Yêu cầu OP kết thúc SSO session |
| Front-Channel Logout | OP qua browser/iframe/redirect | OP thông báo các RPs qua user agent |
| Back-Channel Logout | OP server-to-server | Signed Logout Token để RP kết thúc sessions |

### 18.1. Local logout không bảo đảm hỏi mật khẩu khi login lại

~~~text
Portal local logout -> RP session bị hủy
OP SSO cookie vẫn còn
User bấm Login -> OP có thể tự SSO đăng nhập lại
~~~

Đây có thể là hành vi hợp lệ. Nếu sản phẩm yêu cầu re-authentication, phải dùng policy như `max_age`, `prompt=login`, `auth_time` theo khả năng OP, không chỉ xóa Portal cookie.

## 19. RP-Initiated Logout và end_session_endpoint

OP có thể công bố:

~~~json
{
  "issuer": "https://id.example.net",
  "end_session_endpoint": "https://id.example.net/connect/endsession"
}
~~~

Không tự đoán endpoint bằng cách thêm `/logout` vào issuer. URL thực tế phải đến từ Discovery hoặc provider-specific contract tin cậy.

### 19.1. Tham số thường gặp

| Tham số | Vai trò |
| --- | --- |
| `id_token_hint` | ID Token trước đó, gợi ý client/user session cho OP |
| `post_logout_redirect_uri` | Nơi yêu cầu browser quay về, thường phải đăng ký |
| `state` | Correlation khi quay về RP sau logout |
| `logout_hint` | Gợi ý provider-specific |
| `client_id` | Có thể cần theo điều kiện OP/spec |

Không dùng Access Token thay ID Token hint, không gửi Client Secret trong logout URL.

### 19.2. Open redirect

Không chuyển trực tiếp browser input:

~~~text
/logout?returnUrl=https://attacker.example/collect
~~~

vào `post_logout_redirect_uri`. Chỉ chấp nhận registered redirect URIs được RP/OP kiểm soát.

## 20. Spring Security Servlet: RP-Initiated Logout

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.oidc.web.logout.OidcClientInitiatedLogoutSuccessHandler;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.logout.LogoutSuccessHandler;

@Configuration
public class MultiProviderLogoutConfig {

    @Bean
    LogoutSuccessHandler oidcLogoutSuccessHandler(
            ClientRegistrationRepository registrations) {

        OidcClientInitiatedLogoutSuccessHandler handler =
            new OidcClientInitiatedLogoutSuccessHandler(registrations);
        handler.setPostLogoutRedirectUri("{baseUrl}/signed-out");
        return handler;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            LogoutSuccessHandler oidcLogoutSuccessHandler)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/", "/login", "/signed-out", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .loginPage("/login"))
            .logout(logout -> logout
                .logoutSuccessHandler(oidcLogoutSuccessHandler))
            .build();
    }
}
~~~

**Đây là cấu hình thay thế**, không copy song song với các SecurityFilterChain match tất cả request từ các phần trước. OP phải đăng ký `post_logout_redirect_uri` tương ứng.

### 20.1. Chọn OP của Authentication hiện tại

`OidcClientInitiatedLogoutSuccessHandler` dùng OIDC Authentication và `ClientRegistrationRepository` để chọn OP logout metadata của registration phù hợp. Không cho caller tự chọn provider B để gửi ID Token của provider A đến endpoint khác.

### 20.2. OP không hỗ trợ end-session

Nếu OP thiếu `end_session_endpoint`, cần **local logout fallback** và UX mô tả đúng phạm vi, không tuyên bố OP SSO session đã kết thúc.

### 20.3. CSRF

Local logout ở Servlet browser app thường nên dùng POST và CSRF protection theo config. Không tắt CSRF toàn ứng dụng vì tiện gọi logout bằng GET.

## 21. Reactive/WebFlux logout dùng handler khác

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.oidc.web.server.logout.OidcClientInitiatedServerLogoutSuccessHandler;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.logout.ServerLogoutSuccessHandler;

@Configuration
public class ReactiveLogoutConfig {

    @Bean
    ServerLogoutSuccessHandler oidcServerLogoutSuccessHandler(
            ReactiveClientRegistrationRepository registrations) {

        OidcClientInitiatedServerLogoutSuccessHandler handler =
            new OidcClientInitiatedServerLogoutSuccessHandler(
                registrations);
        handler.setPostLogoutRedirectUri("{baseUrl}/signed-out");
        return handler;
    }

    @Bean
    SecurityWebFilterChain webFilterChain(
            ServerHttpSecurity http,
            ServerLogoutSuccessHandler oidcServerLogoutSuccessHandler) {

        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/", "/signed-out", "/error").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutSuccessHandler(oidcServerLogoutSuccessHandler))
            .build();
    }
}
~~~

Ví dụ Reactive là **alternative application** so với Servlet, không ghép class khác stack vào cùng một SecurityFilterChain. API/WebFlux sử dụng `SecurityWebFilterChain`, `ServerLogoutSuccessHandler`, `ServerWebExchange`/`Mono<Void>`.

## 22. Front-Channel và Back-Channel Logout không giống nhau

### 22.1. Front-Channel

OP sử dụng browser/iframe/redirect để thông báo RP logout. Nó có thể bị ảnh hưởng bởi third-party cookie restrictions, iframe security, SameSite policies và browser chưa mở đúng site. Không mặc định đáng tin trong mọi môi trường.

### 22.2. Back-Channel

OP gửi POST trực tiếp:

~~~http
POST /logout/connect/back-channel/corporate HTTP/1.1
Host: portal.example.net
Content-Type: application/x-www-form-urlencoded

logout_token=SIGNED_LOGOUT_JWT
~~~

Logout Token là JWT sự kiện logout, **không phải ID Token hay Access Token**. RP cần xác minh chữ ký, issuer, audience, thời gian, event marker, `sid`/`sub` và các điều kiện khác trước khi invalidate sessions.

Những phiên bản Spring Security hỗ trợ có DSL `oidcLogout().backChannel(...)`, endpoint mặc định:

~~~text
/logout/connect/back-channel/{registrationId}
~~~

**Có `end_session_endpoint` không chứng minh provider hỗ trợ Back-Channel Logout**. Phải kiểm tra `backchannel_logout_supported` và client registration ở OP.

### 22.3. OP sid không phải RP local session ID

~~~text
OP sid        = op-session-123
RP JSESSIONID = rp-session-987
~~~

RP cần OIDC session registry liên kết issuer/client/sid/sub với local session. Không lấy `sid` trong Logout Token rồi coi nó là cookie `JSESSIONID`.

### 22.4. Ma trận chọn logout

| Provider capability | Hướng xử lý |
| --- | --- |
| Có `end_session_endpoint` + registered post-logout URI | RP-Initiated Logout |
| Không có end-session metadata | Local logout hoặc provider adapter tin cậy |
| Có Back-Channel Logout | Đăng ký endpoint và session registry |
| Có Front-Channel Logout | Kiểm thử browser/cookie constraints |
| Chỉ có proprietary logout API | Tích hợp theo hợp đồng, không giả định là OIDC |
| OAuth2-only provider | Không tự giả định có OIDC SSO/logout |

## 23. Logout local không đồng nghĩa revoke OAuth2 tokens

~~~text
RP local session:
  INVALIDATED

Access Token:
  có thể còn hiệu lực tới exp

Refresh Token:
  có thể còn trong OAuth2AuthorizedClientService
~~~

| Hoạt động | Tác động |
| --- | --- |
| `HttpSession.invalidate()` | Kết thúc RP session |
| RP-Initiated Logout | Yêu cầu OP logout |
| Back-Channel Logout | OP yêu cầu RP invalidate session |
| `removeAuthorizedClient(...)` | Xóa bản ghi token local |
| RFC 7009 Revocation | Yêu cầu Authorization Server thu hồi token |
| Resource Server validation | API quyết định token còn được chấp nhận |

**Không cam kết “đăng xuất khỏi mọi ứng dụng”** nếu chưa thiết kế SSO logout propagation, token expiration/revocation và cách xử lý offline access.

### 23.1. Offline access riêng với browser session

Refresh Token được cấp theo offline access có thể được phép dùng để đồng bộ API ngay cả khi user rời browser. Disconnect OAuth2 connection và browser logout cần policy riêng.

### 23.2. Unlink khác Logout

Logout kết thúc phiên; disconnect thường xóa/revoke token; unlink xóa mối liên hệ external identity với internal account sau kiểm tra quyền. Không xóa mapping vĩnh viễn chỉ vì OP logout event.

## 24. Account linking giữa providers

Một user có thể đăng nhập Corporate, sau đó liên kết Partner:

~~~text
internal-user-100
  +-- Corporate: (issuer A, sub A)
  +-- Partner:   (issuer B, sub B)
~~~

Workflow an toàn:

1. User hiện tại đã được xác thực và có quyền link.
2. User chủ động chọn liên kết OP mới.
3. Thực hiện authorization code + `state`/PKCE + OIDC verification.
4. Lấy `iss + sub` của OP mới đã verify.
5. Kiểm tra identity chưa liên kết với account khác.
6. Thực hiện reauthentication/step-up nếu policy yêu cầu.
7. Ghi mapping atomically, audit chủ thể thực hiện.
8. Không nâng quyền hoặc merge chỉ vì email trùng.

## 25. Multi-tenant provider routing

~~~text
tenant alpha -> corporate-alpha registration
tenant beta  -> corporate-beta registration
partner     -> partner registration
~~~

Tenant/email domain/query parameter có thể giúp đề xuất provider cho UI, nhưng **không tự quyết định trusted issuer/JWKS/role mapping**.

~~~java
enum LoginProvider {
    CORPORATE,
    PARTNER,
    WORKFORCE
}

static String registrationId(LoginProvider provider) {
    return switch (provider) {
        case CORPORATE -> "corporate";
        case PARTNER -> "partner";
        case WORKFORCE -> "workforce";
    };
}
~~~

Đây là fragment đặt trong Java class, mapping server-side. Không cho browser gửi `issuer=https://attacker.example` để backend tự tải signing key rồi chấp nhận JWT attacker ký.

## 26. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Login provider A được, provider B fail | Sai issuer/client ID/redirect URI/client auth | ClientRegistration, metadata |
| `invalid_scope` chỉ ở B | Scope không hỗ trợ hoặc thiếu consent | Scope policy của OP |
| Thiếu email dù yêu cầu `email` | Provider privacy/data policy | Missing-claim handling |
| `email_verified` không có | OP không cấp | Không mặc định true |
| Hai users bị gộp | Dùng email/username làm unique ID | Issuer + sub, account linking |
| Cùng OP nhưng sub khác client | Pairwise subject | Sector/client ID policy |
| UserInfo sub khác ID Token | Token substitution/mismatch | Discard UserInfo data |
| UserInfo trả 401 | Token sai, hết hạn hoặc audience không hợp | UserInfo endpoint và Access Token |
| Keycloak role thiếu trong ID Token | Protocol mapper phát role ở token khác | Claim placement |
| Entra groups vắng | Group overage/optional claims | Provider-specific API policy |
| Login thành công nhưng API 403 | Access Token thiếu scope/audience | Resource Server authorization |
| Logout local, login lại ngay | OP SSO cookie còn | RP-Initiated Logout/reauth policy |
| OP logout redirect 400 | Post-logout URI chưa đăng ký | Exact match URI |
| OP không có end_session_endpoint | Không có RP-Initiated Logout chuẩn | Local fallback |
| Back-channel không invalidate RP session | Registry, cookie, network, security chain | Protocol integration test |
| Token API còn dùng sau logout | Chưa hết hạn/chưa revoke | Token lifecycle policy |
| Logout A xóa token B | Xóa không scope theo issuer/registration | Provider isolation |

### 26.1. Quy trình debug ngắn

~~~text
1. registrationId thực sự được sử dụng?
2. issuer có khớp ID Token iss?
3. Scope được yêu cầu và scope được cấp?
4. Claim nằm trong ID Token, UserInfo hay API riêng?
5. UserInfo sub đã khớp ID Token sub?
6. Type/schema của custom claim đúng?
7. Account linking có dùng email?
8. Role mapping có scope theo trusted issuer/tenant?
9. Lỗi nằm ở login hay downstream API?
10. Logout RP, logout OP và token revocation đã được phân biệt?
~~~

Không cần in raw ID Token, Access Token hoặc UserInfo body để debug; sử dụng metadata đã redacted và correlation ID.

## 27. Kiểm thử scopes/claims/UserInfo theo provider

| Case | Kỳ vọng |
| --- | --- |
| Corporate có sub nhưng thiếu email | Fallback hoặc reject theo product policy |
| Partner `email_verified=false` | Không coi email đã verified |
| Workforce `tid` ngoài allowlist | Không chấp nhận tenant |
| Google `hd` không thuộc allowlist | Không cấp membership quyền công ty |
| Custom roles sai kiểu | Không cấp role |
| Scope requested nhưng không được cấp | Không tự nhận có API permission |
| ID Token issuer/audience sai | Authentication fail |
| UserInfo sub khác ID Token | Reject/discard UserInfo |
| UserInfo thiếu profile claim | Không NullPointerException |
| Provider không có UserInfo | Không tự bịa endpoint |
| Custom claim schema thay đổi | Contract test phát hiện |

### 27.1. Identity linking tests

| Case | Kỳ vọng |
| --- | --- |
| Hai OP cùng email | Không auto-link |
| Hai OP cùng raw sub | Không collide |
| Pairwise sub khác theo client ID | Không auto-merge qua email |
| Identity đã link account khác | Reject hoặc re-link flow an toàn |
| Provider A admin, Provider B user | Không tự giữ ROLE_ADMIN của A |
| Unlink một provider | Không xóa account không liên quan |

### 27.2. Logout tests

| Case | Kỳ vọng |
| --- | --- |
| OP có end_session_endpoint | Redirect đúng OP |
| OP không có end_session_endpoint | Local logout fallback |
| Post-logout URI không đăng ký | Phát hiện lỗi, không open redirect |
| Browser tự chọn provider B khi login A | Không gửi ID Token A sang B |
| Back-channel token ký sai | Không xóa session |
| Back-channel có sid | Chỉ session match bị xóa |
| Back-channel chỉ sub | Scope đúng issuer/client |
| Local logout trong khi OP SSO còn | Login mới có thể được SSO |
| Access Token còn hạn | Không giả định đã revoke |
| Event đến node khác node login | Registry/session store nhất quán |

### 27.3. Các lớp test

~~~text
Unit:
  ProviderClaimsAdapter + role mapping + tenant policy

Spring Security integration:
  registration routing, session, OidcUserService

OIDC protocol integration:
  mock OP, state, PKCE, ID Token, UserInfo sub, nonce

Provider sandbox contract:
  scopes, discovery, claim schema, logout endpoint

Operational monitoring:
  login/logout failure rates per provider
~~~

Mock một OidcUser duy nhất không chứng minh app hoạt động với nhiều providers. Cần cả negative tests cho issuer mismatch, missing claims và logout.

## 28. Tình huống thực hành

### A — Corporate và Partner cùng trả email Alice

Hai OP trả `alice@example.net`, `email_verified=true`.

**Giải pháp:** giữ hai external identities `(iss, sub)` riêng; chỉ link vào một internal account sau flow có kiểm tra quyền.

### B — OP không trả email dù yêu cầu email scope

Application bắt buộc có email để thông báo.

**Giải pháp:** yêu cầu user khai báo và xác minh hoặc dừng onboarding theo policy; không tạo email giả.

### C — UserInfo trả sub khác ID Token

ID Token `sub=alice`, UserInfo `sub=bob` dù HTTP 200.

**Giải pháp:** bỏ UserInfo data; điều tra token substitution/Access Token mismatch.

### D — Provider A phát role, provider B phát group qua Directory API

**Giải pháp:** adapter allowlist và API permissions riêng; không tự cấp ROLE_ADMIN khi Directory API không khả dụng.

### E — Google email suffix giống Workspace nhưng không đủ chứng minh thành viên

**Giải pháp:** dùng hosted-domain evidence và organization policy đúng provider; không chỉ so suffix email.

### F — Dùng tid làm user ID trong Entra

Mọi nhân viên cùng tenant có cùng `tid`.

**Giải pháp:** `tid` là tenant, còn user identity dùng `iss + sub` hoặc `tid + oid` theo Entra-specific integration khi được thiết kế.

### G — Logout Portal rồi login không cần mật khẩu

**Giải pháp:** phân biệt local session với OP SSO session; dùng RP-Initiated Logout hoặc reauth policy nếu thực sự cần.

### H — Partner không có end_session_endpoint

**Giải pháp:** không đoán `/logout`; chỉ local logout hoặc proprietary contract tin cậy.

### I — Role Keycloak chỉ nằm trong Access Token

**Giải pháp:** kiểm tra protocol mapper/client scope, không tự coi Access Token của API khác là OIDC principal.

### J — Entra group overage

**Giải pháp:** áp dụng policy và Graph API có quyền phù hợp; không coi groups vắng là membership rỗng.

### K — Logout OP A xóa token OP B

**Giải pháp:** ràng buộc issuer/client/session; token revoke/disconnect theo chính sách riêng.

### L — User đổi preferred_username

**Giải pháp:** cập nhật display profile; giữ internal account link theo issuer + sub.

### M — OAuth2-only provider không có ID Token

**Giải pháp:** dùng OAuth2 Login, không ép OIDC UserService/logout semantics.

### N — Một người có hai pairwise subjects

**Giải pháp:** provider-approved account correlation, không auto-merge bằng email.

## 29. Checklist trước production

| Câu hỏi | Điều cần kiểm tra |
| --- | --- |
| OP thực sự hỗ trợ OIDC? | Discovery và ID Token contract |
| `issuer-uri` đúng? | Exact issuer validation |
| Client IDs/redirect URIs đúng? | OP console, callback tests |
| Scopes được cấp? | Consent và actual granted scopes |
| Claims có thể thiếu? | Null/type handling |
| UserInfo sub khớp ID Token? | Bắt buộc |
| Identity key ổn định? | Issuer + sub, pairwise handling |
| Email verification rõ? | Boolean, missing claim, provider semantics |
| Roles/groups mapping an toàn? | Trusted issuer/schema/allowlist |
| Multi-tenant isolation? | Không arbitrary issuer/JWKS |
| App roles và API scopes tách biệt? | RP/Resource Server tests |
| OP có end_session_endpoint? | Discovery/contract |
| Post logout URI đăng ký? | Exact-match URI |
| Back-channel supported? | Metadata và OP registration |
| Session multi-node nhất quán? | Registry/session store tests |
| Logout khác revocation? | Refresh Token/offline access policy |
| Logs có credentials? | Redaction, retention |
| Provider contract thay đổi? | Tests/monitoring/migration |

## 30. Tài liệu tham khảo

- OpenID Connect Core 1.0, scopes/claims/UserInfo: https://openid.net/specs/openid-connect-core-1_0.html
- OpenID Connect Discovery 1.0: https://openid.net/specs/openid-connect-discovery-1_0.html
- OpenID Connect RP-Initiated Logout: https://openid.net/specs/openid-connect-rpinitiated-1_0.html
- OpenID Connect Front-Channel Logout: https://openid.net/specs/openid-connect-frontchannel-1_0.html
- OpenID Connect Back-Channel Logout: https://openid.net/specs/openid-connect-backchannel-1_0.html
- Spring Security — Servlet OAuth2 Login: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html
- Spring Security — OAuth2 Login Advanced Configuration: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- Spring Security — Servlet OIDC Logout: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html
- Spring Security — Reactive OAuth2 Login: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html
- Spring Security — Reactive OIDC Logout: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/logout.html
- Google — OpenID Connect implementation: https://developers.google.com/identity/openid-connect/openid-connect
- Microsoft — ID Token Claims Reference: https://learn.microsoft.com/en-us/entra/identity-platform/id-token-claims-reference
- Keycloak — Server Administration Guide: https://www.keycloak.org/docs/latest/server_admin/
- RFC 6749 — OAuth 2.0 Authorization Framework: https://www.rfc-editor.org/rfc/rfc6749
- RFC 9700 — OAuth 2.0 Security Best Current Practice: https://www.rfc-editor.org/rfc/rfc9700
- RFC 8725 — JWT Best Current Practices: https://www.rfc-editor.org/rfc/rfc8725
- RFC 7009 — OAuth 2.0 Token Revocation: https://www.rfc-editor.org/rfc/rfc7009

## 31. Tổng kết: chuẩn OIDC không xóa khác biệt giữa providers

~~~text
Spring Security OIDC Client
  |
  +-- registration corporate: issuer A, scopes A, claims A
  +-- registration partner:   issuer B, scopes B, claims B
  +-- registration workforce: issuer C, scopes C, claims C
  |
  v
Validate ID Token theo đúng issuer/client trước
  |
  v
Provider-specific normalization
  +-- Identity = issuer + subject
  +-- Email/display name = optional
  +-- UserInfo sub MUST match ID Token sub
  +-- Roles = allowlist trusted issuer/provider mapping
  |
  v
Internal user account + authorization + session
  |
  +-- Local logout: chỉ RP session
  +-- RP-Initiated Logout: OP endpoint nếu có
  +-- Front/Back-Channel: OP thông báo RP nếu hỗ trợ
  +-- Token revocation: policy riêng
~~~

**Sáu nguyên tắc cốt lõi:**

1. **Scope được yêu cầu không bảo đảm claim hoặc API permission được cấp.** `openid` xác định OIDC Login, còn `profile`/`email` không bắt buộc OP trả mọi trường cho mọi user.
2. **Identity của OIDC gắn với issuer + subject.** Không dùng email, username hay raw sub làm global key giữa providers; cần secure account linking và pairwise subject awareness.
3. **UserInfo không thay ID Token.** Nếu gọi UserInfo, `sub` phải khớp chính xác ID Token `sub`; nếu khác, không được sử dụng UserInfo claims.
4. **Provider adapter chỉ chuẩn hóa trusted principal.** Không bỏ qua signature/issuer/audience hay tự gán ROLE_ADMIN từ arbitrary claim.
5. **Logout có nhiều phạm vi.** Kiểm tra `end_session_endpoint`, Front-/Back-Channel support và session registry; local logout không tự revoke tokens.
6. **Multi-provider yêu cầu contract tests và trust boundaries rõ.** Mỗi registration có scopes, claim schema, UserInfo rules, resource audience và logout capability riêng.

Áp dụng những nguyên tắc này giúp ứng dụng Spring Security hỗ trợ nhiều OIDC Providers mà không nhầm danh tính người dùng, không đánh đồng claims với quyền và không hứa một mức đăng xuất vượt quá khả năng thực tế của provider.
