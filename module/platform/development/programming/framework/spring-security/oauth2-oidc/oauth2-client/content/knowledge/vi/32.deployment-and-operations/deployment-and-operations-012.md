# 32.12. Quy trình thay đổi provider hoặc cấu hình client an toàn

## 1. Bối cảnh: một thay đổi cấu hình nhỏ có thể thay đổi ranh giới tin cậy

Trong **Spring Security OAuth 2.0 OIDC Client**, cấu hình `ClientRegistration` và OpenID Provider (OP) xác định ứng dụng **tin ai để xác thực người dùng**, **chấp nhận token nào**, **điểm callback nào hợp lệ**, **quyền API nào được xin** và **danh tính nào được gắn với tài khoản nội bộ**.

Một yêu cầu “đổi provider SSO”, “rotate client secret”, “cập nhật issuer URI”, “thêm scope” hay “đổi callback domain” có vẻ đơn giản. Nhưng nếu triển khai thiếu kế hoạch, ứng dụng có thể:

- Gặp `invalid_client` hàng loạt do secret mới chưa được OP kích hoạt hoặc một số pods còn dùng secret cũ.
- Không hoàn tất callback do `redirect_uri_mismatch`, mất session `state` hoặc PKCE verifier.
- Từ chối ID Token khi OP thay JWKS signing key, issuer hoặc client audience.
- Tự tạo tài khoản trùng khi issuer/`sub` thay đổi, hoặc gộp nhầm hai users có cùng email.
- Gọi API bằng token sai audience/scope, sinh `401 invalid_token` hoặc `403 insufficient_scope`.
- Làm các Refresh Tokens cũ không còn dùng được sau khi thay client ID.
- Vô tình xóa authorized clients của provider khác khi dọn dữ liệu migration.
- Gây login loop, logout không hoàn tất hoặc đánh mất một phần phiên trong lúc rolling deployment.

Ví dụ cấu hình cũ:

~~~text
registrationId = corporate
issuer         = https://id-old.example.net/realms/workforce
clientId       = portal-web
redirectUri    = https://portal.example.net/login/oauth2/code/corporate
~~~

Yêu cầu mới:

~~~text
issuer         = https://id-new.example.net/realms/workforce
clientId       = portal-web-v2
redirectUri    = https://portal.example.net/login/oauth2/code/corporate-v2
~~~

**Không nên chỉ thay ba chuỗi rồi deploy tất cả instances.** Việc thay issuer và client ID có thể là một **identity/authorization migration**, không chỉ là thay domain.

### Mục tiêu bài học

Sau bài này, bạn có thể:

1. Phân loại thay đổi `issuer`, client registration, secrets/keys, endpoints, redirects, scopes, claims, UserInfo, token store và logout.
2. Xác định phạm vi ảnh hưởng và các **security invariants** phải được giữ.
3. Lập kế hoạch chuẩn bị, kiểm thử, canary, cutover, rollback và hậu kiểm.
4. Sử dụng **dual ClientRegistration** khi cần chuyển provider hoặc client ID mà không làm hỏng các phiên cũ.
5. Đổi Client Secret, private key, mTLS certificate và JWKS signing keys đúng thứ tự.
6. Giữ đúng `state`/PKCE/nonce, session, token lifecycle, tenant và account-linking boundaries.
7. Vận hành an toàn trong cả Spring Security Servlet và WebFlux/Reactive.

> **Phạm vi:** ví dụ sử dụng Spring Boot/Spring Security OAuth2 Client/OIDC Login với Authorization Code + PKCE, Refresh Token và Client Credentials khi phù hợp. Những APIs và starter names có thể khác giữa Spring Boot 3.x/4.x và Spring Security 6.x/7.x; cần đối chiếu BOM, OP contract và môi trường triển khai. Các URL, IDs và secret names là placeholders.

## 2. Bản đồ ranh giới chịu ảnh hưởng

~~~mermaid
flowchart TD
    A["Browser / RP application"] --> B["Spring Security OAuth2 Login"]
    B --> C["Trusted ClientRegistration"]
    C --> D["Issuer + OIDC Discovery"]
    D --> E["Authorization redirect + state + PKCE"]
    E --> F["Token Endpoint"]
    F --> G["ID Token: signature + iss + aud + nonce + exp"]
    G --> H["External identity: issuer + subject"]
    H --> I["Internal account + tenant membership"]
    F --> J["Access + Refresh Tokens"]
    J --> K["Authorized Client Store"]
    K --> L["Resource Server audience + scopes"]
    B --> M["RP session / OP logout / revocation"]
~~~

### 2.1. Những bất biến bảo mật

| Mã | Invariant | Không được làm |
| --- | --- | --- |
| S1 | Issuer được tin cậy | Tự tải issuer/JWKS từ URL do browser nhập |
| S2 | ID Token validation | Bỏ chữ ký, `iss`, `aud`, `exp` hoặc `nonce` khi cần |
| S3 | Request correlation | Bỏ `state`/PKCE để callback “dễ chạy” |
| S4 | Identity separation | Dùng email/raw `sub` làm global user ID |
| S5 | Token isolation | Gửi token của registration A sang provider/API B |
| S6 | Least privilege | Tự nâng scope, dùng machine admin token thay user token |
| S7 | Tenant integrity | Coi OP claim là membership mà không kiểm tra policy |
| S8 | Secret handling | Log client secret, Access/Refresh Token, code, private key |
| S9 | Recoverability | Revoke secret cũ trước khi xác minh rollback/forward-fix |
| S10 | Change evidence | Đóng thay đổi sau một lần HTTP 200 mà không test negative paths |

Nếu một ranh giới phải thay đổi có chủ ý — chẳng hạn chuyển issuer — cần **migration plan được phê duyệt**, không “tạm nới” validator.

## 3. Phân loại thay đổi theo mức rủi ro

| Loại thay đổi | Tác động chính | Chiến lược thường phù hợp |
| --- | --- | --- |
| Rotate `client-secret`, client ID giữ nguyên | Token Endpoint client authentication | Overlap secrets nếu OP hỗ trợ |
| Rotate `private_key_jwt` key | Client assertion signature, JWK registration | Overlap keys và staged rollout |
| Rotate mTLS certificate/key | Client authentication, token binding | Certificate overlap, trust validation |
| Rotate OP signing keys/JWKS | ID Token verification | Provider-controlled JWKS rollover |
| Đổi `client-id` | ID Token audience, consent, Refresh Token binding | New registration + reauthorization |
| Đổi `issuer-uri` | Trust boundary và external identity namespace | Migration + explicit identity mapping |
| Đổi Authorization/Token Endpoint | Browser/token routing, TLS, network | Verify trusted metadata + canary |
| Đổi `redirect-uri`/public domain | Callback, cookie, state/PKCE | Dual callback transition |
| Thêm/bớt scopes | Consent, token scope, API permissions | User/admin consent workflow |
| Đổi claims/role mapper | Internal authorization, tenant rights | Claim schema + negative tests |
| Đổi UserInfo Endpoint | Profile claims, `sub` equality | Metadata + UserInfo validation |
| Đổi logout endpoints | RP/OP sessions, back-channel registry | OP capability + session tests |
| Đổi token/session store | Persistence, refresh, multi-node behavior | Data compatibility/migration |
| Nâng Spring Security | Defaults, filter chain, managers/handlers | Compatibility + integration tests |

**Lưu ý:** thay đổi chỉ liên quan secret của cùng client có thể ít ảnh hưởng đến user sessions hơn đổi issuer, nhưng nếu secret đã lộ, đó là **security incident** chứ không chỉ maintenance.

## 4. Quy trình tổng thể từ đề xuất đến đóng thay đổi

~~~mermaid
flowchart TD
    A["Create change request"] --> B["Inventory + risk assessment"]
    B --> C{"Issuer/client ID/identity change?"}
    C -->|Yes| D["Dual registration + account migration design"]
    C -->|No| E["Credential/config rotation design"]
    D --> F["Staging + mock OP + provider sandbox tests"]
    E --> F
    F --> G{"Security and integration tests pass?"}
    G -->|No| H["Fix design; do not deploy"]
    H --> F
    G -->|Yes| I["Approval + canary + rollback plan"]
    I --> J["Progressive release"]
    J --> K["Observe authentication, token, API, logout"]
    K --> L{"SLOs and invariants hold?"}
    L -->|No| M["Stop; rollback or forward-fix/contain"]
    L -->|Yes| N["Expand cohort and cutover"]
    N --> O["Retire old registrations/credentials safely"]
    O --> P["Post-change verification and audit"]
~~~

Các pha vận hành:

1. **Prepare:** xác định chủ thể, loại thay đổi, môi trường và blast radius.
2. **Design:** chọn in-place rotation, dual registration hoặc migration issuer/account.
3. **Validate:** chạy test protocol, browser, API, session và authorization.
4. **Stage:** chuẩn bị OP configuration/secret manager, giữ khả năng hỗ trợ flows cũ.
5. **Canary:** bật với users/tenants được cho phép, giám sát baseline.
6. **Cutover:** tăng traffic có kiểm soát.
7. **Finalize:** chỉ revoke secrets cũ, bỏ routes/issuer trust cũ khi đã đủ điều kiện.
8. **Post-change:** lưu bằng chứng, khôi phục logging baseline và cập nhật runbook.

## 5. Change request cần đầy đủ những gì?

Ví dụ một yêu cầu vận hành **không chứa bí mật**:

~~~yaml
change_id: OIDC-CHANGE-EXAMPLE
application: portal
environment: production
owner_team: identity-platform
change_type: client-secret-rotation
affected_registration_ids:
  - corporate
old_provider_alias: corporate-op
new_provider_alias: corporate-op
issuer_change: false
client_id_change: false
overlap_supported: pending_confirmation
expected_user_action: none_if_provider_contract_allows
rollback_condition: invalid_client_above_baseline
secret_material_in_ticket: false
~~~

Đây chỉ là template minh họa, không phải file cần tạo trong bước viết Markdown.

### 5.1. Vai trò

| Vai trò | Trách nhiệm |
| --- | --- |
| Application owner | Luồng login/authorization/tenant |
| IAM/Identity team | OP client registration, scopes, secrets/keys, consent |
| Security | Trust boundary, compromised credentials, approvals |
| Platform/SRE | Deployment, proxy/TLS, session/cache, monitoring |
| Data/Account team | External identity linking, schema và migration |
| Product/Support | Thông báo re-login, consent và ảnh hưởng users |
| Provider support | Xác nhận rotation, issuer, endpoints, outage semantics |

Không cần mọi thay đổi đều dùng quy trình phê duyệt giống nhau, nhưng **đổi issuer, client ID hoặc identity mapping** là thay đổi rủi ro cao phải có ownership rõ ràng.

## 6. Kiểm kê mọi dependency trước khi thay đổi

Không chỉ tìm trong `application.yml`. Cấu hình có thể đến từ Java beans, secret manager, dynamic registration database, API gateway hoặc custom provider adapters.

### 6.1. Inventory

| Thành phần | Cần ghi nhận |
| --- | --- |
| `ClientRegistrationRepository` | Danh sách registration IDs, issuer/client IDs |
| OP metadata | Authorization/Token/JWKS/UserInfo/logout/revocation endpoints |
| Secret manager | Secret/key version và consumers |
| Callback routes | Registered URIs, public hosts, proxy prefixes |
| Security chains | Servlet/Reactive matchers, login callbacks |
| `OidcUserService` | Custom UserInfo/claim enrichment |
| `GrantedAuthoritiesMapper` | Trusted issuer/role/group mapping |
| Identity DB | Unique key issuer+sub, pairwise sub semantics |
| Token store | JDBC/Redis/session, encryption và retention |
| Refresh jobs | Non-request manager, system principal, concurrency |
| Resource Servers | Trusted issuers, audiences và API scopes |
| RP/OP Logout | End-session endpoint, Back-Channel session registry |
| Session store | Redis/JDBC, cookie, TTL, cross-node compatibility |
| Monitoring | Login, token, API, logout và incident dashboards |
| Rollback plan | Old secret/endpoint còn hợp lệ hay không? |

### 6.2. Baseline trước deploy

Cần có số liệu trước thay đổi theo từng provider/registration:

- Login success/fail và thời gian authorization callback.
- `redirect_uri_mismatch`, `state` mismatch/login loop.
- Token Endpoint `invalid_client`, `invalid_grant`, 429/503.
- ID Token `iss`/`aud`/signature/`kid` failures.
- UserInfo 401/403 và `sub` mismatch.
- Authorized client refresh failures/races.
- Resource Server `401 invalid_token` và `403 insufficient_scope`.
- OIDC logout failures, session invalidation.
- Provider latency/rate limits và authentication SLO.

Ngưỡng go/no-go nên dựa trên **baseline và SLO thực tế**, không dùng một con số tùy tiện cho mọi hệ thống.

## 7. Xác minh Discovery metadata và trust contract của provider

Một OIDC OP có thể công bố:

~~~json
{
  "issuer": "https://id.example.net",
  "authorization_endpoint": "https://id.example.net/authorize",
  "token_endpoint": "https://id.example.net/token",
  "jwks_uri": "https://id.example.net/jwks",
  "userinfo_endpoint": "https://id.example.net/userinfo",
  "end_session_endpoint": "https://id.example.net/connect/endsession",
  "scopes_supported": ["openid", "profile", "email"]
}
~~~

Các URL minh họa; trong thực tế một số metadata fields là tùy chọn. Không tự tạo `/logout`, `/userinfo` hay `/revoke` bằng cách nối đường dẫn khi OP không công bố hoặc chưa có contract.

| Trường | Ý nghĩa thay đổi |
| --- | --- |
| `issuer` | Ranh giới trust của ID Token và external identity |
| `authorization_endpoint` | Browser login redirect |
| `token_endpoint` | Code/refresh exchange và client authentication |
| `jwks_uri` | OP signing keys dùng verify ID Token |
| `userinfo_endpoint` | UserInfo claims và subject binding |
| `token_endpoint_auth_methods_supported` | Basic/Post/private_key_jwt/mTLS |
| `scopes_supported` | Những scopes OP quảng bá, không bảo đảm granted |
| `code_challenge_methods_supported` | PKCE S256 và compatibility |
| `end_session_endpoint` | RP-Initiated Logout khi có |
| `revocation_endpoint` | RFC 7009 token revocation khi có |
| `backchannel_logout_supported` | Back-Channel Logout capability |

### 7.1. Endpoint đổi nhưng issuer không đổi

Provider có thể thay Token Endpoint host mà giữ issuer. Đây không nhất thiết là identity migration, nhưng cần xác minh metadata được lấy từ **trusted issuer** và endpoint mới thuộc domain/certificate được phép. Không cho operator/client input tùy ý chỉ định Token Endpoint, vì Access/Refresh Tokens có thể bị gửi sang host attacker.

### 7.2. Không tin issuer từ URL do user gửi

~~~text
POST /connect?issuer=https://attacker.example
  -> App tải Discovery/JWKS do attacker vận hành
  -> App chấp nhận ID Token attacker tự ký
~~~

Đây là trust-confusion/SSRF risk. Production providers phải thuộc allowlist/approved onboarding, không tự động tin arbitrary OIDC endpoint.

## 8. Lựa chọn chiến lược: cập nhật tại chỗ hay dual registration?

### 8.1. In-place

Thường hợp lý nếu:

- Issuer, client ID, identity semantics, callback route **không đổi**.
- Chỉ credential version thay, OP cho overlap/rotation theo contract.
- Có rollback dùng credential còn hợp lệ.
- Không làm sai phiên login đang in-flight.

### 8.2. Dual registration

Nên cân nhắc khi:

- Đổi issuer, client ID hoặc redirect URI.
- Cần canary theo tenant/user.
- Consent hoặc Refresh Token của client cũ không dùng được với client mới.
- Có callback cũ đang chạy dở.
- Cần secure identity migration/account linking.

~~~text
Old registration:
  corporate-old -> issuer A, client portal-v1

New registration:
  corporate-new -> issuer B, client portal-v2

Transition:
  old flows vẫn được phép hoàn tất theo policy
  canary cohort dùng new registration
  identity account mapping được xác minh tường minh
~~~

**Đừng hiểu dual registration là được gộp `(issuerA, subX)` và `(issuerB, subX)`.** Ranh giới issuer vẫn tách biệt.

## 9. Ví dụ cấu hình Spring Boot cho hai registrations

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate-old:
            provider: old-oidc
            client-id: ${OLD_OIDC_CLIENT_ID}
            client-secret: ${OLD_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
          corporate-new:
            provider: new-oidc
            client-id: ${NEW_OIDC_CLIENT_ID}
            client-secret: ${NEW_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
        provider:
          old-oidc:
            issuer-uri: https://id-old.example.net/realms/workforce
          new-oidc:
            issuer-uri: https://id-new.example.net/realms/workforce
~~~

Đây là cấu hình minh họa cho **issuer/client migration**, không phải hướng dẫn nhân đôi registrations cho mọi lần rotate secret. Client secrets lấy từ secret manager/environment được bảo vệ, **không commit production secrets trong source**.

### 9.1. Đường dẫn login/callback

~~~text
/oauth2/authorization/corporate-old
/oauth2/authorization/corporate-new

/login/oauth2/code/corporate-old
/login/oauth2/code/corporate-new
~~~

OP phải đăng ký exact callback tương ứng từng client ID. Các phiên đang đăng nhập với old registration phải được xử lý bằng cấu hình và state/PKCE của old flow.

### 9.2. Servlet SecurityFilterChain

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcWebSecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error")
                    .permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .loginPage("/login"))
            .build();
    }
}
~~~

Đây là một cấu hình **độc lập** trong Servlet. Custom `/login` phải được triển khai. Nếu có nhiều `SecurityFilterChain`, phải kiểm tra matchers/order, tránh một chain mới vô tình không xử lý callback hoặc bypass protected routes.

### 9.3. Quy tắc chọn registration server-side

~~~java
package com.example.identity;

import java.util.Set;

public final class ApprovedLoginRegistrationPolicy {
    private static final Set<String> APPROVED =
        Set.of("corporate-old", "corporate-new");

    public String chooseForApprovedCohort(boolean canary) {
        return canary ? "corporate-new" : "corporate-old";
    }

    public boolean isApproved(String registrationId) {
        return APPROVED.contains(registrationId);
    }
}
~~~

`canary` ở đây tượng trưng cho quyết định **trusted server-side rollout flag**, không phải `?canary=true` do user tự gửi. Không đưa machine Client Credentials registration lên UI interactive login để caller tùy ý chọn.

## 10. Đổi issuer là một identity migration

OIDC external identity cơ bản:

~~~text
(issuer, subject)
~~~

Hai records:

~~~text
(https://id-a.example.net, sub=42)
(https://id-b.example.net, sub=42)
~~~

**không tự chỉ cùng một người**. Ngay cả khi email giống nhau và cả hai OP nói `email_verified=true`, điều đó không chứng minh user muốn gộp hai accounts.

### 10.1. External identity schema

~~~sql
CREATE TABLE external_identity (
    id UUID PRIMARY KEY,
    internal_account_id UUID NOT NULL,
    issuer VARCHAR(512) NOT NULL,
    subject VARCHAR(512) NOT NULL,
    registration_id VARCHAR(100) NOT NULL,
    verified_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uq_external_identity UNIQUE (issuer, subject)
);
~~~

Lược đồ minh họa. Với pairwise subjects, multiple client IDs hoặc multi-tenant semantics, có thể cần thêm client/sector context theo contract. Không dùng email làm unique global key của identity.

### 10.2. Pairwise subject khi đổi client ID

Ngay cả **issuer giữ nguyên**, cùng người có thể nhận:

~~~text
clientId = portal-web-old -> sub = pairwise-123
clientId = portal-web-new -> sub = pairwise-789
~~~

Không tự merge `pairwise-123` và `pairwise-789` chỉ vì email giống. Nếu cần liên kết, sử dụng provider-approved correlation hoặc secure account linking workflow.

### 10.3. Quy trình liên kết tài khoản khi migration

1. User đã xác thực với old identity tạo **migration intent** được lưu server-side.
2. Gắn intent với internal account, initiating session, expected new registration/issuer và TTL.
3. User đăng nhập lại qua OP mới bằng Authorization Code + state/PKCE/nonce đúng flow.
4. RP verify ID Token signature/issuer/audience/nonce và lấy subject mới.
5. Xác minh intent còn hiệu lực, đúng session/account/provider; thực hiện step-up nếu policy yêu cầu.
6. Database transaction kiểm tra identity mới chưa thuộc account khác, bảo vệ `UNIQUE(issuer, subject)`.
7. Link identity mới vào internal account và audit.
8. Đánh giá tenant roles, authorized clients và recovery method trước khi retire identity cũ.

Không chạy SQL thay hàng loạt `issuer` hoặc `sub` mà không xác minh ownership của mỗi identity.

### 10.4. Hai callbacks song song không được tạo link nhầm

Nếu user mở tab A bắt đầu old login rồi tab B bắt đầu new provider linking, callback A/B đến ngược thứ tự vẫn phải match đúng `state`, session và intent. Đừng dùng biến global “last selected provider” làm nguồn xác thực.

## 11. Client Secret rotation: đúng thứ tự, có kế hoạch dự phòng

### 11.1. Khi OP hỗ trợ secret overlap

~~~mermaid
sequenceDiagram
    autonumber
    participant IAM as Identity Admin
    participant SM as Secret Manager
    participant RP as Spring Boot Pods
    participant OP as Token Endpoint
    IAM->>OP: Register new secret; old remains valid
    IAM->>SM: Store new secret version
    SM-->>RP: Rollout canary new secret
    RP->>OP: Token exchange with new secret
    OP-->>RP: Success
    IAM->>RP: Progressive rollout all consumers
    RP->>OP: Login/refresh with new secret
    OP-->>RP: Success
    IAM->>OP: Revoke old secret after verification
~~~

Trình tự:

1. Kiểm kê mọi workloads dùng client secret: web, scheduled jobs, workers, emergency tools.
2. Xác minh OP **thật sự hỗ trợ nhiều secrets đồng thời**.
3. Tạo secret mới ở OP và lưu trong secret manager với quyền truy cập phù hợp.
4. Test staging và canary Token Endpoint authentication.
5. Progressive rollout mọi instances, theo dõi `invalid_client` và refresh failure.
6. Chỉ revoke old secret khi xác nhận không còn consumer dùng nó, hoặc đã chấp nhận rủi ro rollback.
7. Retire old secret reference theo retention; phát hiện attempts còn dùng credential cũ.

### 11.2. OP không hỗ trợ overlap

Không thể hứa zero downtime. Cần lựa chọn: maintenance window ngắn, đăng ký new client ID chạy song song, provider-specific atomic rotation hoặc degraded mode có communication. Đặc biệt với Refresh Token rotation, phải tránh hai phiên bản app cùng ghi token trái contract.

### 11.3. Public client không giữ được secret

Không nhúng confidential client secret vào SPA/mobile source. Với public clients, dùng Authorization Code + PKCE và redirect/platform protections phù hợp. Đổi “secret” của ứng dụng public không làm nó trở thành confidential client.

## 12. Rotate private_key_jwt, mTLS và DPoP

| Method | Credential | Những bước cần kiểm tra |
| --- | --- | --- |
| `client_secret_basic` / `post` | Client Secret | OP auth method, secret version |
| `private_key_jwt` | Private signing key | Registered JWKs, `kid`, assertion claims/expiry |
| mTLS | Certificate/private key | TLS trust, client binding, expiry |
| DPoP sender-constraining | DPoP key/proof | Key continuity, `htu`/`htm`, nonce/replay |

### 12.1. private_key_jwt key rotation

Trước khi client ký bằng key mới, OP cần biết public key/JWK mới theo cơ chế đăng ký. Kiểm tra `kid`, `aud` (Token Endpoint theo provider contract), assertion expiration/clock, private-key storage và key retirement. Không log private key hoặc raw signed assertions.

### 12.2. mTLS

Đổi mTLS certificate có thể ảnh hưởng **client authentication** và **certificate-bound Access Tokens** nếu dùng RFC 8705. Không chỉ thay ingress TLS certificate rồi cho rằng outbound Token Endpoint mTLS đã thay.

### 12.3. DPoP

DPoP (RFC 9449) yêu cầu client, OP và Resource Server thực hiện proof/token binding đúng. Thay key có thể làm tokens cũ bound với key cũ không dùng được. Không chỉ gắn một DPoP header tự tạo rồi coi token đã sender-constrained.

### 12.4. Credential compromise

Nếu key/secret bị lộ, ưu tiên containment, rotate/revoke tại OP, đánh giá issued tokens/grants và phối hợp incident response. Xóa secret trong commit mới không vô hiệu các bản đã lộ.

## 13. OP signing key/JWKS rotation khác client credential rotation

~~~text
Client secret / private_key_jwt:
  RP authenticates itself to Authorization Server

OP signing key / JWKS:
  RP validates ID Token produced by OpenID Provider
~~~

### 13.1. Normal JWKS rollover

Provider có thể publish public signing key mới, bắt đầu ký token bằng `kid` mới, giữ key cũ qua giai đoạn overlap rồi retire. RP cần JWKS cache refresh đúng trust policy, không hard-code vĩnh viễn một key.

### 13.2. Khi `kid` mới chưa có

Kiểm tra trusted issuer, JWKS URL, HTTPS/TLS, proxy, cache TTL, key rotation status, node consistency. Không chấp nhận `alg=none`, không bỏ chữ ký/issuer/audience validation, không tải key từ arbitrary JWT `jku`/`x5u` do attacker chỉ ra.

### 13.3. Signing key compromise

Đây là incident, không phải hoạt động rollover bình thường. Cached compromised keys có thể không an toàn; làm theo provider advisory, đánh giá sessions/tokens đã phát và phối hợp revoke/deny strategy.

## 14. Thay scopes: consent và Resource Server phải cùng được xem xét

~~~text
Before: openid profile email
After:  openid profile email reports.read
~~~

Thêm `reports.read` không bảo đảm tất cả users lập tức được cấp scope. Có thể cần new consent/admin consent, client permission update hoặc authorization request mới.

### 14.1. Cần phân biệt ba thứ

| Thành phần | Không đồng nhất với |
| --- | --- |
| OIDC scopes (`openid`, `profile`, `email`) | Local application roles |
| OAuth2 API scope (`reports.read`) | Quyền admin Portal |
| `ROLE_REPORT_VIEWER` của tenant Alpha | Quyền vào tenant Beta hoặc API khác |

### 14.2. Đổi client ID và offline access

Refresh Token có thể được ràng buộc với old client. `offline_access` scope cũng không bảo đảm OP phát Refresh Token. Sau client ID migration, test reauthorization/refresh theo provider behavior thực, không copy Refresh Token bytes sang new authorized-client record.

### 14.3. Giảm scopes cũng cần lifecycle

Giảm requested scope trong YAML không tự revoke Access Tokens đã phát với quyền rộng. Có thể cần grant revocation, token TTL/introspection strategy và cleanup authorized clients theo policy.

## 15. Redirect URI, domain, reverse proxy và cookie

Spring Security thường sử dụng redirect URI template:

~~~text
{baseUrl}/login/oauth2/code/{registrationId}
~~~

Ví dụ:

~~~text
Browser public URL:
  https://portal.example.net

Proxy:
  HTTPS public -> http://app:8080 internal

Correct redirect:
  https://portal.example.net/login/oauth2/code/corporate-new
~~~

Nếu RP gửi `http://app:8080/login/oauth2/code/...`, OP có thể từ chối.

### 15.1. Forwarded headers

Một lựa chọn Spring Boot trong topology proxy đáng tin:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

Phải **chỉ tin** `Forwarded`/`X-Forwarded-*` từ trusted proxies, strip headers giả mạo do client tự gửi. Tin `X-Forwarded-Host` không kiểm soát có thể tạo redirect confusion/open redirect.

### 15.2. Phải đăng ký callback trước khi chuyển traffic

Đăng ký exact HTTPS callback URI tại OP, test cả path, domain, port, trailing slash. Không sử dụng wildcard redirect rộng chỉ vì muốn triển khai nhanh.

### 15.3. In-flight login

Browser có thể đã bắt đầu OAuth2 Login với registration cũ, sau MFA mới callback về. Trong rolling deployment, giữ callback/authorization request repository tương thích cho old flow khi policy/OP cho phép; không ép state/PKCE cũ qua new client.

### 15.4. Cookies và SameSite

Đổi domain/callback response mode có thể làm session cookie không được gửi, gây `state` mismatch. Kiểm tra `Secure`, `SameSite`, `Domain`, `Path`, HTTPS, browser cookie exclusion reason và session TTL. `query` vs `form_post` callback có thể khác cookie behavior.

## 16. Giữ an toàn phiên đang chạy khi rolling deployment

~~~mermaid
sequenceDiagram
    actor Browser
    participant RP1 as Old Pod
    participant OP as OP
    participant RP2 as New Pod
    Browser->>RP1: Start old login
    RP1-->>Browser: Redirect with state/PKCE
    Browser->>OP: MFA/consent
    Note over RP1,RP2: Rollout begins
    OP-->>Browser: Old callback code/state
    Browser->>RP2: Callback after rollout
    RP2->>RP2: Load compatible old authorization request
    RP2-->>Browser: Safe success or controlled failure
~~~

Những thành phần cần xác minh:

- Authorization request storage và `state`/nonce/PKCE verifier.
- Registration ID vẫn tồn tại cho flows cũ.
- Callback SecurityFilterChain match.
- HttpSession/WebSession serialization compatible.
- Cookies/CSRF/session fixation behavior không đổi ngoài ý định.
- Authorized client persistence old/new versions.
- Multi-node Redis/JDBC session store và cache consistency.

Một RP session từ old issuer không tự trở thành Authentication từ new issuer sau config switch; cần reauthentication/migration theo chính sách.

## 17. OAuth2AuthorizedClient và token lifecycle

Một authorized client thường có:

~~~text
(ClientRegistration, principalName)
  -> Access Token
  -> Refresh Token (optional)
~~~

Servlet có `OAuth2AuthorizedClientService` và `OAuth2AuthorizedClientRepository`; Reactive có `ReactiveOAuth2AuthorizedClientService` và `ServerOAuth2AuthorizedClientRepository`.

### 17.1. In-place secret rotation cùng client

Refresh grants hiện có **có thể** tiếp tục hoạt động nếu OP cho phép client authenticate bằng new secret. Nhưng không có bảo đảm cho mọi provider; test login/refresh thật trong sandbox.

### 17.2. New client ID/issuer

Không mặc định Access/Refresh Tokens của old client có thể dùng với new client. Reauthorize với đúng provider/registration, không chỉ đổi database record's `registrationId`.

### 17.3. Xóa local khác revoke remote

~~~java
authorizedClientService.removeAuthorizedClient(
    registrationId, principalName);
~~~

Chỉ xóa record trong store local tương ứng. Token revocation tại Authorization Server cần request/protocol khác (RFC 7009, nếu OP hỗ trợ). HTTP 200 từ revocation endpoint cũng được trả nếu token vốn đã invalid; 503 nghĩa là chưa xác nhận revoke.

### 17.4. Scope cleanup đúng mức

~~~text
AuthorizedClient(A, Alice) -> invalid_grant
AuthorizedClient(B, Alice) -> vẫn có thể hợp lệ
AuthorizedClient(A, Bob)   -> vẫn có thể hợp lệ
~~~

Không xóa toàn bộ authorized clients vì lỗi của A/Alice. Đặc biệt kiểm tra custom success/failure handlers của `OAuth2AuthorizedClientManager` và WebClient OAuth2 filters.

### 17.5. Concurrent refresh rotation

~~~text
Pod A: load R1 -> refresh success -> save R2
Pod B: load R1 -> invalid_grant -> deletes R2
~~~

Khi thay token store/manager, test optimistic locking/CAS hoặc single-flight refresh. `invalid_grant` có thể do revoke hoặc refresh race, không chứng minh chắc token theft. Không retry cùng invalid token vô hạn.

## 18. Claims, UserInfo và GrantedAuthorities sau đổi OP

| Claim | Rủi ro khi migration |
| --- | --- |
| `iss` | Exact trust namespace khác |
| `sub` | Có thể thay hoặc pairwise theo client |
| `email` | Missing/change/reassignment, không là global ID |
| `email_verified` | Không mặc định true khi thiếu |
| `preferred_username` | Display name không ổn định |
| `groups`/`roles` | Claim placement/schema/provider policy |
| `tid`/`oid` (Entra) | Provider-specific identifiers |
| `hd` (Google) | Hosted-domain context khi policy yêu cầu |

OIDC Core yêu cầu `sub` trong UserInfo response **phải khớp chính xác** `sub` của ID Token. Nếu khác, không sử dụng UserInfo claims. Không map raw `admin` của OP mới thành `ROLE_ADMIN` chỉ vì name giống; role mapping phải dựa trusted issuer/schema/tenant policy.

Một provider có thể trả groups qua Directory/Graph API thay vì UserInfo; cần API audience/scope/consent riêng và policy fail-closed nếu phụ thuộc groups để cấp quyền.

## 19. Resource Server phải tương thích độc lập với RP Login

RP login success không chứng minh Reports API đã chấp nhận Access Token mới:

~~~text
RP (OIDC Client)
  -> new issuer Access Token
      -> Reports API (Resource Server)
          verify trusted issuer, audience, expiration,
          scopes, tenant membership and object ownership
~~~

### 19.1. Nếu Resource Server chỉ tin old issuer

Token của new OP có thể trả 401. Thêm issuer mới vào allowlist API là một security change riêng: xác minh signing keys, audience, scopes và subject/tenant mapping. **Không tắt issuer/audience validation** để giảm lỗi.

### 19.2. Chuẩn bị Resource Server trước canary RP

Khi cần, deploy API support/trust đúng new token format trước khi chuyển users, kiểm tra cả negative tokens sai issuer/audience, sau đó bật RP new registration. Thời gian API tin đồng thời old/new issuers phải giới hạn và có tiêu chí retire old issuer.

### 19.3. Không tăng quyền bằng fallback token

Nếu delegated user token mới có `403 insufficient_scope`, không tự dùng admin Client Credentials để “sửa”. Phải xử lý API consent/role/tenant policy hợp lệ.

## 20. Logout khi thay đổi OP

| Mechanism | Phạm vi | Điều phải test |
| --- | --- | --- |
| Local RP logout | HttpSession/WebSession | Browser session invalid, no state leak |
| RP-Initiated Logout | OP SSO session nếu hỗ trợ | `end_session_endpoint`, registered post-logout URI |
| Front-Channel Logout | Browser notification | SameSite/iframe/browser restrictions |
| Back-Channel Logout | Signed server-to-server Logout Token | Issuer/audience/`sid`/`sub`/session registry |
| Token revocation | Authorization Server tokens | Correct client/auth endpoint, response handling |

Spring Security Servlet có `OidcClientInitiatedLogoutSuccessHandler`; Reactive có `OidcClientInitiatedServerLogoutSuccessHandler`. Không gửi `id_token_hint` của OP A tới logout endpoint OP B.

`sid` từ OP không phải local `JSESSIONID`. Back-Channel Logout cần mapping OP session/subject với RP session registry, đặc biệt trong multi-node environment.

Local logout không tự revoke Access Token JWT đã phát. Nếu sản phẩm hứa “logout mọi nơi”, phải có thiết kế/token revocation/session propagation đã được kiểm chứng.

## 21. Servlet và Reactive/WebFlux có các điểm vận hành khác

| Thành phần | Servlet | Reactive |
| --- | --- | --- |
| Security DSL | `HttpSecurity` | `ServerHttpSecurity` |
| Security chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Session | `HttpSession` | `WebSession` |
| Client repository | `OAuth2AuthorizedClientRepository` | `ServerOAuth2AuthorizedClientRepository` |
| Client service | `OAuth2AuthorizedClientService` | `ReactiveOAuth2AuthorizedClientService` |
| Request manager | `DefaultOAuth2AuthorizedClientManager` | `DefaultReactiveOAuth2AuthorizedClientManager` |
| Background manager | `AuthorizedClientServiceOAuth2AuthorizedClientManager` | `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` |

### 21.1. Reactive SecurityWebFilterChain

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveOidcConfig {

    @Bean
    SecurityWebFilterChain webFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/", "/login", "/error").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

Ví dụ này **thay thế** Servlet chain, không trộn DSLs. Với custom reactive token/user services, không gọi JDBC/RestTemplate đồng bộ trên event loop. Ưu tiên reactive I/O, hoặc cô lập blocking operation trên `Schedulers.boundedElastic()` nếu chưa thể thay, với concurrency/timeout limits.

### 21.2. Không tự subscribe trong Reactive cleanup

~~~java
// PHẢN VÍ DỤ:
reactiveAuthorizedClientService
    .removeAuthorizedClient(id, principal)
    .subscribe();
return Mono.empty();

// ĐÚNG HƠN: trả publisher vào request/handler pipeline.
return reactiveAuthorizedClientService
    .removeAuthorizedClient(id, principal);
~~~

Code fragment minh họa, chưa có enclosing class. Tự `subscribe()` tách error/cancellation/SecurityContext khỏi request và có thể trả response trước khi persistence hoàn tất.

## 22. Immutable config, secret references và rolling deployment

Một release nên xác định:

~~~text
application-build-id
configuration-version
client-registration-version
secret-manager-reference/version (không chứa secret)
trusted-issuer-alias
schema-migration-version
feature-flag-cohort
rollback-artifact
~~~

Không chỉnh thủ công một pod production rồi để các pods khác giữ config cũ mà không kiểm soát. Secrets phải được quản lý trong secret manager/environment có phân quyền và audit.

### 22.1. Hot reload có thể tạo snapshot không nhất quán

Nếu dynamic `ClientRegistrationRepository` đổi `client-id` hoặc Token Endpoint khi một authorization request đang in-flight, callback có thể dùng config mới nhưng code/PKCE/redirect của config cũ. Cần immutable registration snapshots/versioned compatibility hoặc rolling deploy với dual IDs.

### 22.2. Không fallback secret hard-code

Nếu KMS/secret manager không khả dụng, component phù hợp nên fail closed/degraded theo policy và alert, không dùng emergency admin secret trong source.

### 22.3. Secrets không xuất hiện trong logs

Không log values của `client-secret`, private keys, Authorization headers, Access/Refresh/ID Tokens, authorization code, PKCE verifier, `state` hoặc session cookies. Cấu hình DEBUG/TLS/wiretap/CI cần redaction và retention chặt chẽ.

## 23. Staging test matrix trước khi canary

| Nhóm | Positive case | Negative case |
| --- | --- | --- |
| Registration | Old/new được resolve đúng | Unknown registration ID |
| Authorization | Redirect đúng OP/URI/scope/state/PKCE | Wrong redirect, invalid scope |
| Callback | Code/state/session match | Wrong state, session lost, cross-provider callback |
| Client auth | Token Endpoint chấp nhận new secret | Old/revoked secret, wrong method |
| ID Token | Signature/iss/aud/nonce/time đúng | Wrong issuer, audience, JWKS key |
| UserInfo | `sub` match ID Token | `sub` mismatch, missing optional claims |
| Account identity | Verified identity map đúng | Same email/sub cross-issuer collision |
| Tenant/roles | Membership đúng | Role leakage/provider admin confusion |
| API | Token đúng issuer/aud/scope | 401 invalid_token, 403 insufficient_scope |
| Token store | Save/load/refresh đúng | Wrong registration/principal, rotation race |
| Browser/session | Cookie/callback cross-node | SameSite/session timeout |
| Logout | Local/OP/back-channel đúng | Missing endpoint, wrong issuer logout token |
| Rollback | Old config/secret còn valid | Old secret đã revoke |
| Outage | Retry bounded, state preserved | Provider 503 gây xóa mọi token |

### 23.1. Mock OIDC principal không thay protocol integration

`oidcLogin()` trong MockMvc và `mockOidcLogin()` trong WebTestClient giúp test app authorization nhưng **không thực hiện thật Authorization Code exchange, PKCE, Token Endpoint, JWKS/ID Token signature verification**.

### 23.2. Protocol test cần ít nhất hai OPs

Để phát hiện cross-provider confusion, dùng mock/test OP A và B với issuers/client IDs/signing keys khác nhau:

~~~text
OP A:
  issuer A, client A, key A, JWKS A

OP B:
  issuer B, client B, key B, JWKS B

Test negative:
  ID Token signed B in OP A flow
  ID Token aud=client B in A flow
  UserInfo sub different from ID Token
  Callback state/code/PKCE of one OP on other route
~~~

Không lưu client secret production hoặc user tokens thật trong test fixtures/CI artifacts.

## 24. Canary rollout: lựa chọn cohort và dừng đúng lúc

### 24.1. Rollout phases

1. Nội bộ/test accounts với OP test/live sandbox theo policy.
2. Một cohort users/tenants đã phê duyệt.
3. Mở rộng có kiểm soát khi authentication, API, token, session và logout metrics đạt baseline.
4. Giữ old registration cho flows/users chưa migrated nếu còn hợp lệ.
5. Dừng và rollback/forward-fix ngay khi phát hiện boundary violation.

### 24.2. Metrics có ích

| Metric gợi ý | Tại sao |
| --- | --- |
| `oauth2_login_success_total` per registration | Đăng nhập thực hoạt động |
| `oauth2_token_invalid_client_total` | Secret/method rollout sai |
| `oauth2_invalid_grant_total` | Code, PKCE, Refresh Token |
| `oauth2_issuer_audience_fail_total` | Trust mismatch |
| `oauth2_jwks_failure_total` | Signing key/cache |
| `oauth2_state_mismatch_total` | Cookie/session/multi-node |
| `oauth2_userinfo_subject_mismatch_total` | Token substitution/mix-up |
| `oauth2_api_invalid_token_total` | Resource Server trust |
| `oauth2_api_insufficient_scope_total` | Granted scope/consent |
| `oauth2_refresh_failure_total` | Authorized client lifecycle |
| `oauth2_account_link_conflict_total` | Identity migration risk |
| `oauth2_logout_failure_total` | OP/RP logout contract |

Không dùng raw email, `sub`, token, `state`, session ID hoặc full claim payload làm metric labels.

### 24.3. Stop-the-line

Dừng rollout ngay nếu có:

- ID Token sai issuer/audience được chấp nhận.
- Hai accounts bị gộp tự động chỉ vì trùng email/raw sub.
- Cross-tenant data leak hoặc quyền tăng ngoài policy.
- Token bị gửi sang provider/Resource Server host sai.
- Credentials xuất hiện trong log/trace/CI artifact.

Lỗi availability như 503/`invalid_client` tăng cũng có thể yêu cầu pause theo SLO, nhưng cần phân biệt provider outage với security incident.

## 25. Rollback phải được lập trước cutover

| Thao tác đã làm | Có rollback bằng YAML cũ? | Lý do |
| --- | --- | --- |
| New secret đã tạo, old còn valid | Thường có thể | Old pods vẫn authenticate được |
| Old secret đã revoke | **Không đơn giản** | Old build không còn credential |
| New client ID đã cấp consent | Không chuyển ngược tự động | Tokens/grants gắn client |
| Issuer migration đã link identities | Không tự đổi mapping | Identity ownership đã được xác minh |
| OP đã retire signing key | Không nên khôi phục compromised key | Security trust |
| Old callback URI bị xóa | In-flight flows fail | Cần OP re-register nếu cho phép |
| Destructive DB schema migration | Có thể không | Rollback code không khôi phục data |
| Refresh Token đã rotate | Không dùng lại R1 | Token family đã thay |
| User đã login new OP | Không tự đóng new SSO session | OP logout/session khác RP |

### 25.1. Expand-contract schema migrations

1. **Expand** schema/columns giữ old app tương thích.
2. **Backfill/verify** identity mapping và record versions.
3. **Switch** readers/writers sang schema mới qua canary.
4. **Observe** duplicates, nulls, stale records và account-link conflicts.
5. **Contract** bỏ old fields chỉ khi rollback window và data migration đã hoàn tất.

### 25.2. Forward-fix có khi an toàn hơn rollback

Nếu secret cũ đã revoke hoặc endpoint cũ đã đóng, rollback artifact không giải quyết lỗi. Cần **forward-fix**: phát credential mới, sửa endpoint/config new version, điều chỉnh token/API trust theo approval. Kế hoạch phải nêu điều kiện chọn rollback hay forward-fix.

### 25.3. Sau rollback vẫn phải xác minh security

Không chỉ ping `/login`. Kiểm tra issuer/audience signature validation, callback state/PKCE, account mapping, tenant permissions, authorized-client store, API calls, logout và background jobs.

## 26. Điều kiện hoàn tất cutover và dọn registration cũ

Chỉ retire `corporate-old` khi:

- Users/tenants được yêu cầu đã migration hoặc có recovery path.
- Callback old flows không còn cần xử lý theo window/policy.
- Old tokens/grants đã hết hạn/revoked hoặc có kế hoạch disconnect.
- Không còn scheduled jobs dùng old client secret/registration.
- Old OP sessions và Logout Token/session registry được xử lý.
- Resource Servers không còn cần old issuer cho token còn hạn, hoặc có explicit revocation/denylist strategy.
- SLO, security invariants và incident window được phê duyệt đóng.

**Remove old registration là bước cuối**, không phải hành động đầu tiên ngay khi new canary có một lượt HTTP 200.

## 27. Runbook A — Rotate secret gây `invalid_client`

**Triệu chứng:** Token Endpoint từ chối login/refresh, `invalid_client` tăng ngay sau rollout.

**Chẩn đoán:**

1. Đúng client ID/tenant/realm không?
2. New secret đã được OP kích hoạt?
3. Client auth method có đổi không?
4. Canary pods thực sự đọc secret version mới?
5. Jobs/regions nào còn dùng old version?

**Phục hồi:** nếu old secret còn valid, rollback secret reference cho cohort lỗi và kiểm thử. Nếu old secret đã revoke, tạo credential mới/forward-fix; không log secret để debug.

## 28. Runbook B — Đổi issuer nhưng user tạo account mới

**Triệu chứng:** OP mới login thành công, RP không tìm được account cũ hoặc tạo duplicate.

**Chẩn đoán:** so `(oldIssuer, oldSub)` với `(newIssuer, newSub)` đã được verify, kiểm tra pairwise subject và link intent. Không lấy email trùng làm bằng chứng.

**Phục hồi:** tạm dừng migration cohort, giữ old route nếu policy cho phép, thiết kế verified identity linking/transaction với unique constraints. Không trực tiếp UPDATE `issuer`/`sub` hàng loạt.

## 29. Runbook C — Callback lỗi sau đổi domain

**Triệu chứng:** OP báo `redirect_uri_mismatch` hoặc callback `state` mismatch.

**Chẩn đoán:** public scheme/host/path, registered redirect URI, trusted forwarded headers, cookies/`SameSite`/`Secure`, session TTL và multi-node session store.

**Phục hồi:** khôi phục exact redirect route/OP allowlist và compatible old callback cho in-flight flows; không disable state/PKCE checks.

## 30. Runbook D — JWKS key mới gây ID Token validation fail

**Triệu chứng:** ID Token có `kid` mới bị reject, một vài pods hoạt động khác nhau.

**Chẩn đoán:** trusted JWKS URL, cache refresh, OP signing key rotation, TLS/proxy, issuer/audience và clock.

**Phục hồi:** update cache/trust theo OP metadata và policy; không bỏ signature validation. Nếu signing-key compromise, chuyển sang incident response.

## 31. Runbook E — Scope mới nhưng Reports API 403

**Triệu chứng:** login thành công, API trả `insufficient_scope`.

**Chẩn đoán:** requested vs actually granted scopes, user/admin consent, token audience, Resource Server policy, token cũ có được refresh hay không.

**Phục hồi:** reauthorization/consent hợp lệ, cập nhật permissions theo least privilege. Không dùng admin machine token thay user token để bypass.

## 32. Runbook F — Refresh Token rotation race trong rollout

**Triệu chứng:** refresh A thành công R1→R2; request B trả `invalid_grant` và xóa R2.

**Chẩn đoán:** multiple pods dùng cùng store, versioned update/delete, custom success/failure handlers, token family policy của OP.

**Phục hồi:** single-flight refresh hoặc CAS/optimistic locking, giữ record mới; không retry invalid R1 vô hạn.

## 33. Runbook G — Provider 503 giữa lúc canary

**Triệu chứng:** Token Endpoint hoặc UserInfo/JWKS tạm unavailable, login/refresh chậm.

**Chẩn đoán:** endpoint nào bị ảnh hưởng, region/tenant nào, có OP incident không, lỗi có phải transient?

**Phục hồi:** pause rollout, giữ valid credentials, bounded retry với backoff/jitter/`Retry-After` và circuit breaker. Nếu old OP còn usable theo trust policy, giữ old traffic; không tự auto-link identities. Không tắt authentication validation để duy trì uptime.

## 34. Runbook H — Secret/key lộ qua Git hoặc logs

Đây là incident:

1. Ngăn nguồn lộ và hạn chế quyền truy cập artifacts/logs.
2. Khoanh vùng client/tenant/environment/credential type.
3. Rotate/revoke compromised credential tại OP và secret manager.
4. Đánh giá issued tokens/grants có thể bị lạm dụng; revoke khi phù hợp.
5. Quarantine connections/sessions nếu risk yêu cầu.
6. Giám sát attempts dùng credential cũ, xử lý privacy/notification theo chính sách.
7. Hậu kiểm root cause và regression tests redaction.

Không coi việc xóa secret khỏi HEAD Git branch là đủ; nó có thể tồn tại trong history/caches.

## 35. Tests cho rollback và sự cố

| Case | Kỳ vọng |
| --- | --- |
| Old/new registrations cùng tồn tại | Không lẫn issuer/client IDs |
| In-flight old callback sau deploy | State/callback hợp lệ hoặc safe failure |
| New issuer same raw sub/email | Không auto-link |
| Client ID mới phát pairwise sub khác | Explicit proof workflow |
| Old secret còn valid | Rollback có thể được test |
| Old secret revoked | Forward-fix plan thực thi được |
| OP 503 | Không xóa token store hàng loạt |
| JWKS kid mới | Verify đúng trusted key |
| ID Token sai issuer/audience | Reject |
| UserInfo sub mismatch | Không dùng UserInfo claims |
| Scope chưa consent | Không tự cấp API quyền |
| API audience sai | Resource Server 401 |
| Logout OP không hỗ trợ | Local logout fallback đúng phạm vi |
| Refresh race | Không xóa R2 từ pod khác |
| Multi-node session | Callback không mất state |
| Database schema migration | Old/new builds đọc tương thích trong window |

## 36. Checklist một giờ trước production cutover

| Nhóm | Câu hỏi phải trả lời |
| --- | --- |
| Ownership | Có owner/approval/incident contact không? |
| Scope | Registrations, tenants, regions và users nào ảnh hưởng? |
| Issuer | Metadata/JWKS/trust boundary được verified chưa? |
| Credentials | Secret/key version đúng, không log? |
| Callback | Exact URI/proxy/cookie/PKCE/state đúng? |
| ID Token | Issuer, audience, signature, nonce và clock? |
| UserInfo | Subject equality, missing-claim policy? |
| Identity | Pairwise sub/email collision/account-linking? |
| Authorization | Tenant/role scopes không tăng ngoài ý định? |
| Token store | Authorized client persistence/refresh races? |
| Resource Server | Trusted issuer/audience/scopes/API trust? |
| Logout | RP/OP/Back-Channel/session registry? |
| Monitoring | Dashboard, alerts, canary threshold? |
| Rollback | Old credential/endpoint còn dùng được? |
| Forward-fix | Có phương án khi rollback bất khả thi? |
| Testing | Mock OP, provider sandbox, browser/DB tests? |
| UX | Re-consent/re-login/migration communication? |
| Cleanup | Khi nào retire old registration/secrets? |

## 37. Câu hỏi ôn tập

**1. Tại sao đổi `issuer-uri` không chỉ là thay URL?**

Vì issuer là trust boundary của OIDC và namespace cho external identity. Khi issuer đổi, `(iss, sub)` mới cần xác minh/migration, không tự nối với account cũ bằng email.

**2. Vì sao client ID mới có thể làm user `sub` thay đổi dù issuer không đổi?**

Một OP có thể phát pairwise subject theo client/sector. Không auto-merge bằng email; cần verified account linking hoặc provider-approved correlation.

**3. Khi rotate secret có thể revoke secret cũ ngay không?**

Chỉ khi mọi consumers đã chuyển và rollback risk được chấp nhận. Nếu OP không hỗ trợ secret overlap, cần maintenance/dual client/forward-fix plan.

**4. Refresh Token của old client có dùng với new client ID không?**

Không mặc định. Refresh Token thường gắn client/grant; cần reauthorization hoặc provider-supported migration, không copy token bytes.

**5. Khi OP JWKS rotate, có được bỏ signature validation để login tiếp?**

Không. Phải kiểm tra trusted issuer/JWKS cache/key rollout; nếu key compromise cần incident response.

**6. Vì sao thêm `reports.read` không đảm bảo API trả 200?**

User/admin consent có thể chưa cấp scope, Access Token có thể vẫn cũ/sai audience; Resource Server vẫn kiểm tra quyền riêng.

**7. Local logout có tự revoke Access Token JWT không?**

Không. RP session, OP SSO, Access/Refresh Tokens có vòng đời khác nhau; phải có revocation/introspection/denylist policy riêng nếu yêu cầu.

**8. Vì sao một rollback YAML cũ có thể thất bại?**

Secret cũ có thể đã revoke, endpoint cũ đóng, Refresh Token đã rotate hoặc schema đã xóa; đôi khi phải forward-fix.

**9. Có nên tự tạo provider từ `issuer` do user gửi không?**

Không. Không có trust onboarding/allowlist, điều này mở đường cho SSRF hoặc chấp nhận ID Token attacker ký.

**10. Chỉ test `oidcLogin()` trong MockMvc đã đủ để đổi issuer chưa?**

Chưa. Nó mock Authentication và không thực hiện Token Endpoint/JWKS/PKCE thực. Cần mock OP/provider sandbox và browser callback integration tests.

## 38. Tài liệu tham khảo

- Spring Security — Servlet OAuth2 Login: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html
- Spring Security — Advanced OAuth2 Login: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- Spring Security — Servlet OAuth2 Client: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html
- Spring Security — Authorized Clients: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html
- Spring Security — Reactive OAuth2 Login: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html
- Spring Security — Reactive OAuth2 Client: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html
- Spring Security — Servlet OIDC Logout: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html
- Spring Security — Reactive OIDC Logout: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/logout.html
- Spring Security — OAuth2 Login MockMvc Testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html
- Spring Security — Reactive WebTestClient Security Testing: https://docs.spring.io/spring-security/reference/reactive/test/web/index.html
- Spring Boot — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- OpenID Connect Core 1.0: https://openid.net/specs/openid-connect-core-1_0.html
- OpenID Connect Discovery 1.0: https://openid.net/specs/openid-connect-discovery-1_0.html
- OpenID Connect RP-Initiated Logout 1.0: https://openid.net/specs/openid-connect-rpinitiated-1_0.html
- OpenID Connect Back-Channel Logout 1.0: https://openid.net/specs/openid-connect-backchannel-1_0.html
- OAuth 2.0 Authorization Framework — RFC 6749: https://www.rfc-editor.org/rfc/rfc6749
- Proof Key for Code Exchange — RFC 7636: https://www.rfc-editor.org/rfc/rfc7636
- OAuth 2.0 Security Best Current Practice — RFC 9700: https://www.rfc-editor.org/rfc/rfc9700
- OAuth 2.0 Token Revocation — RFC 7009: https://www.rfc-editor.org/rfc/rfc7009
- OAuth 2.0 Bearer Token Usage — RFC 6750: https://www.rfc-editor.org/rfc/rfc6750
- OAuth 2.0 Mutual TLS and Certificate-Bound Tokens — RFC 8705: https://www.rfc-editor.org/rfc/rfc8705
- OAuth 2.0 DPoP — RFC 9449: https://www.rfc-editor.org/rfc/rfc9449
- JWT Best Current Practices — RFC 8725: https://www.rfc-editor.org/rfc/rfc8725
- OWASP Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- OWASP OAuth2 Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html

## 39. Tổng kết: thay đổi OAuth2/OIDC là một security change

~~~text
Change request
    |
    v
Inventory + blast radius + security invariants
    |
    +-- Secret/key rotation?
    |     -> overlap if available -> canary -> retire old
    |
    +-- Client ID/issuer migration?
    |     -> dual registration -> user consent
    |     -> identity linking and token lifecycle
    |
    +-- Endpoint/redirect/scope changes?
    |     -> trusted metadata -> session/PKCE/callback tests
    |     -> Resource Server audience/permissions
    |
    v
Mock OP / provider sandbox / staging tests
    |
    v
Canary + progressive rollout + observability
    |
    +-- Security violation -> STOP + containment
    +-- Availability regression -> pause + rollback/forward-fix
    |
    v
Verified cutover -> retire old safely -> post-change audit
~~~

**Sáu nguyên tắc cốt lõi:**

1. **Không đổi issuer như đổi hostname.** Trust và external identity cần được tái xác minh; client ID mới có thể đổi pairwise subject hoặc consent.
2. **Rotation phải có thứ tự.** Đăng ký secret/key mới, xác minh canary và mọi consumers trước khi revoke credential cũ; nếu không có overlap phải có kế hoạch maintenance/forward-fix.
3. **Giữ nguyên các ràng buộc protocol.** `state`, PKCE, nonce, issuer, audience và JWT signature không được tắt để vượt lỗi triển khai.
4. **Scope, claims, tenant, token và logout là những vòng đời khác nhau.** Mỗi nhóm cần tests và cleanup đúng phạm vi, không dùng quyền của provider khác làm fallback.
5. **Rollback phải được kiểm tra như một tính năng.** Secret đã revoke hoặc identity/schema đã migration có thể không quay lui bằng YAML cũ; cần phương án forward-fix.
6. **Canary và bằng chứng quyết định cutover.** Quan sát errors per registration, API permissions, session continuity, account-link conflicts và bảo vệ secrets trước khi đóng thay đổi.

Quy trình thay đổi an toàn không chỉ bảo đảm người dùng vẫn đăng nhập, mà còn **chứng minh token không đi sai nơi, quyền không tự tăng, danh tính không bị gộp nhầm và đội ngũ có khả năng phục hồi khi cấu hình client hoặc provider thay đổi**.
