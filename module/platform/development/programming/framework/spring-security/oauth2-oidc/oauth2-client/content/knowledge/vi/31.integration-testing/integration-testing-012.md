# 31.12. Kiểm thử cô lập provider, tenant và liên kết tài khoản

## 1. Vì sao kiểm thử đăng nhập thành công vẫn chưa đủ?

Một ứng dụng **Spring Security OAuth 2.0 OIDC Client** có thể hỗ trợ đăng nhập bằng tài khoản doanh nghiệp, tài khoản đối tác và nhiều OpenID Providers (OP). Đồng thời, cùng một người có thể thuộc nhiều **tenants** (tổ chức/khách hàng), còn một tài khoản ứng dụng nội bộ có thể được **liên kết với nhiều external identities**.

Kiểm thử “user A đăng nhập bằng provider X và nhận HTTP 200” chỉ chứng minh một nhánh hoạt động. Nó **không chứng minh** rằng:

- Người dùng provider X không thể xem dữ liệu dành riêng cho provider Y.
- Hai providers phát cùng `sub` hoặc email không bị gộp nhầm thành một internal account.
- User của tenant Alpha không thể đoán ID để đọc/bật tính năng của tenant Beta.
- Một callback OAuth2 thành công không bị dùng để **gắn danh tính attacker vào tài khoản victim**.
- Token của provider A không bị nạp nhầm vào authorized-client store của provider B.
- Quyền `admin` từ OP bên ngoài không tự biến thành `ROLE_ADMIN` của ứng dụng.
- Một phiên logout, revoke hay refresh của user A không làm thay đổi connection của user B.
- Hai browser tabs cùng liên kết một identity không thể tạo lỗi race hoặc chuyển quyền sai.

**Mục tiêu của bài:** xây dựng một hệ thống kiểm thử tích hợp có thể chứng minh **cô lập danh tính, cô lập tenant, cô lập token và an toàn của account linking** ở nhiều tầng: database, Spring Security, authorization service, OAuth2/OIDC protocol, HTTP request và các luồng bất đồng bộ.

### 1.1. Ví dụ rủi ro

~~~text
OpenID Provider A
  issuer = https://id.alpha.example.test
  sub    = 12345
  email  = alex@example.test

OpenID Provider B
  issuer = https://id.beta.example.test
  sub    = 12345
  email  = alex@example.test

Ứng dụng lưu:
  external_user_id = "12345"

=> Hai identities không liên quan có thể bị gộp nhầm.
~~~

Nguyên nhân không phải OAuth2 code exchange thất bại, mà là ứng dụng **không giữ ranh giới issuer khi ánh xạ danh tính**.

### 1.2. Sơ đồ tổng thể

~~~mermaid
flowchart TD
    A["Browser / BFF / RP"] --> B["Spring Security OAuth2/OIDC Login"]
    B --> C["ClientRegistration A"]
    B --> D["ClientRegistration B"]
    C --> E["Issuer A, ID Token A"]
    D --> F["Issuer B, ID Token B"]
    E --> G["Trusted identity normalization"]
    F --> G
    G --> H["External identity: issuer + subject"]
    H --> I["Internal account"]
    I --> J["Tenant membership + role policy"]
    J --> K["Tenant-scoped repositories / APIs"]
    B --> L["Authorized Client Store"]
    L --> M["Token scoped by registration + principal"]
    I --> N["Account Linking Workflow"]
    N --> H
~~~

**Chú ý:** không được coi tên email, `preferred_username`, raw `sub` hoặc claim `tid` là bằng chứng toàn cục rằng hai identities thuộc cùng một người.

## 2. Phân biệt bốn ranh giới bảo mật

| Ranh giới | Khóa/phạm vi | Câu hỏi cần kiểm thử |
| --- | --- | --- |
| **Provider/issuer** | OP issuer, client registration, keys | ID Token của issuer A có bị nhận nhầm dưới registration B? |
| **External identity** | `(issuer, subject)` đã xác minh | Hai user có cùng `sub`/email ở hai OP có bị gộp? |
| **Tenant** | Tenant ID và membership nội bộ | User có quyền đúng tenant hiện tại và resource không? |
| **OAuth2 connection** | Registration, principal, client, token audience | Access/Refresh Token có bị dùng, xóa hoặc refresh chéo? |

Một authorization decision đầy đủ có thể cần cả bốn:

~~~text
verified OIDC issuer + subject
             |
             v
internal account
             |
             v
membership in requested tenant
             |
             v
role/permission inside that tenant
             |
             v
resource belongs to that tenant
             |
             v
ALLOW or DENY
~~~

Nếu chỉ kiểm tra `ROLE_REPORT_VIEWER` mà bỏ qua owner tenant của báo cáo, vẫn có thể phát sinh **IDOR/BOLA** (Insecure Direct Object Reference / Broken Object Level Authorization).

### 2.1. Provider khác tenant

Một provider có thể phục vụ nhiều tenants; một tenant có thể cho đăng nhập bằng nhiều providers. Do đó:

~~~text
provider != tenant
registrationId != tenantId
sub != internalAccountId
email != identity key
issuer != authorization scope của API
~~~

Đừng viết policy `"registrationId=company => tenant=company"` nếu sản phẩm không có một mapping tin cậy và được kiểm tra rõ ràng.

## 3. Các bất biến bảo mật cần chứng minh

Trước khi viết test, phát biểu thành các **security invariants**:

1. **I1 — Trusted issuer:** chỉ nhận identity từ đúng OP/registration đã được cấu hình và ID Token được xác minh theo issuer/client.
2. **I2 — Stable identity:** external identity được xác định bởi issuer + subject, không bởi email hoặc raw subject.
3. **I3 — Explicit linking:** account linking cần ý định chủ động, phiên hiện tại đã xác thực và hoàn thành protocol mới; không tự gộp khi email trùng.
4. **I4 — Uniqueness:** một external identity không thể đồng thời liên kết với hai internal accounts nếu nghiệp vụ dùng mô hình một ownership.
5. **I5 — Tenant membership:** requested tenant phải được xác minh server-side với internal account.
6. **I6 — Resource ownership:** resource thuộc tenant mục tiêu; không chỉ dựa vào tenant trên URL/header.
7. **I7 — Authorization least privilege:** role/scope/claim của một OP không tự có giá trị tương đương ở OP khác.
8. **I8 — Token isolation:** một authorized client phải gắn đúng client registration, principal và context lưu trữ.
9. **I9 — Session binding:** callback/link attempt gắn với đúng browser/session, state/nonce/PKCE và không bị replay.
10. **I10 — Fail closed:** issuer mismatch, tenant ambiguity, thiếu membership, link collision hoặc provider error không được biến thành truy cập được phép.
11. **I11 — Atomic updates:** concurrent link/unlink/refresh không tạo mapping trùng hoặc làm mất token mới.
12. **I12 — Audit/privacy:** sự kiện link/unlink/denied được ghi đúng mức, không lộ token/code/session cookie.

Các invariant này nên được thể hiện bằng **positive tests và negative tests**. Một test chỉ mong đợi HTTP 200 sẽ không chứng minh isolation.

## 4. Mức kiểm thử: mỗi công cụ chứng minh điều gì?

| Cấp | Công cụ | Chứng minh được | Chưa chứng minh |
| --- | --- | --- | --- |
| Unit | JUnit + fake repositories | Identity normalization, policy, state machine | OIDC protocol, HTTP filters |
| Spring Security controller | MockMvc + `oidcLogin()` | Route/method security và principal mapping trong app | Chữ ký ID Token, authorization code, OP callback |
| Reactive controller | WebTestClient + `mockOidcLogin()` | WebFlux chain, Reactor context, route authorization | Token Endpoint/JWKS thật |
| Repository integration | Testcontainers PostgreSQL | Unique constraints, transaction, concurrent insert | OIDC state/nonce |
| Mock OP integration | WireMock/MockWebServer/test OIDC server | Discovery, callback, code/PKCE, token validation, UserInfo | Production provider behavior |
| Browser E2E | Playwright/Selenium + test OP | Cookies, redirect, SameSite, state/session binding | Mọi chính sách production tenant |
| Contract sandbox | Provider test tenant/clients | Real OP semantics, supported claims/scopes | Full incident behavior |
| Load/race tests | Controlled parallel requests | Atomic linking, token refresh consistency | Bảo mật khi OP thật bị compromise |

**`oidcLogin()` và `mockOidcLogin()` không phát ID Token qua Token Endpoint thật**. Chúng cung cấp principal giả cho Spring Security tests, rất hữu ích nhưng không thay thế integration test xác minh chữ ký, `iss`/`aud`, PKCE và `state`.

## 5. Thiết lập fixtures có chủ đích tạo xung đột

Để tìm lỗi isolation, **đừng tạo toàn bộ test users với email/sub khác nhau**. Hãy cố tình dùng các giá trị dễ gây nhầm:

| Fixture | Issuer | Subject | Email | Tenant memberships |
| --- | --- | --- | --- | --- |
| Alice-A | issuer A | `shared-100` | `alex@example.test` | Alpha |
| Bob-B | issuer B | `shared-100` | `alex@example.test` | Beta |
| Carol-A | issuer A | `carol-200` | `carol@example.test` | Alpha + Beta |
| Dave-A | issuer A | `dave-300` | `dave@example.test` | Không có |
| Admin-B | issuer B | `admin-400` | `admin@example.test` | Beta admin |
| Duplicate-A | issuer A | `shared-100` | `new-email@example.test` | Cùng identity như Alice |

### 5.1. Test tenants

~~~text
Tenant Alpha: tenant_id = t-alpha
  report_id = report-001
  provider registrations allowed = corp-alpha, partner

Tenant Beta: tenant_id = t-beta
  report_id = report-002
  provider registrations allowed = corp-beta, partner

Internal account alice:
  external identity (issuer A, shared-100)
  membership Alpha, role REPORT_VIEWER

Internal account bob:
  external identity (issuer B, shared-100)
  membership Beta, role REPORT_VIEWER
~~~

Nếu có collision, bài test có thể phát hiện Alice truy cập nhầm nội dung của Bob hoặc mapping account bị thay đổi.

### 5.2. Hai issuers có client IDs và signing keys riêng

~~~text
OP A issuer    = https://id-a.example.test
OP A client_id = portal-a
OP A JWKS      = key-a

OP B issuer    = https://id-b.example.test
OP B client_id = portal-b
OP B JWKS      = key-b
~~~

Khi kiểm thử bằng mock OP, tạo **hai keypairs test riêng**, không dùng cùng signing key để che các lỗi chọn nhầm issuer/JWKS.

## 6. Cấu hình Spring Boot nhiều registrations

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp-alpha:
            provider: op-alpha
            client-id: ${ALPHA_OIDC_CLIENT_ID}
            client-secret: ${ALPHA_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
          corp-beta:
            provider: op-beta
            client-id: ${BETA_OIDC_CLIENT_ID}
            client-secret: ${BETA_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
        provider:
          op-alpha:
            issuer-uri: https://id-a.example.test
          op-beta:
            issuer-uri: https://id-b.example.test
~~~

Các URIs và environment variables chỉ là **ví dụ**, không phải OP thực. Mỗi client cần đúng redirect URI, client authentication method và scope đã đăng ký.

### 6.1. Những điểm kiểm thử config

- `/oauth2/authorization/corp-alpha` chỉ dùng config của issuer A.
- `/oauth2/authorization/corp-beta` chỉ dùng config của issuer B.
- Callback `/login/oauth2/code/corp-alpha` không được xử lý bằng registration B.
- OP issuer A không được cấu hình cùng JWKS URL của OP B ngoài ý định.
- Sai client ID hoặc secret của registration A không ảnh hưởng flow B nếu hạ tầng độc lập.
- Registration ID do server allowlist, không từ arbitrary `issuer` query parameter.

## 7. Thiết kế external identity key chính xác

Một model đơn giản bằng Java:

~~~java
package com.example.identity;

import java.util.Objects;

public record ExternalIdentityKey(
        String issuer,
        String subject) {

    public ExternalIdentityKey {
        Objects.requireNonNull(issuer, "issuer");
        Objects.requireNonNull(subject, "subject");
        if (issuer.isBlank() || subject.isBlank()) {
            throw new IllegalArgumentException("Empty OIDC identity key");
        }
    }
}
~~~

`issuer` phải lấy từ **ID Token đã được verify**, ví dụ `oidcUser.getIdToken().getIssuer()`, và `subject` là `sub` do OP phát cho RP. Không dùng header `X-User-Id` hoặc query parameter do browser tự điền.

### 7.1. Positive/negative unit tests

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class ExternalIdentityKeyTest {

    @Test
    void sameSubjectDifferentIssuerMustRemainDifferent() {
        ExternalIdentityKey a =
            new ExternalIdentityKey("https://id-a.example.test", "shared-100");
        ExternalIdentityKey b =
            new ExternalIdentityKey("https://id-b.example.test", "shared-100");

        assertNotEquals(a, b);
    }

    @Test
    void sameIssuerAndSubjectStaySameWhenEmailChanges() {
        ExternalIdentityKey first =
            new ExternalIdentityKey("https://id-a.example.test", "shared-100");
        ExternalIdentityKey second =
            new ExternalIdentityKey("https://id-a.example.test", "shared-100");

        assertEquals(first, second);
    }
}
~~~

Đây là unit tests cho **key semantics**, chưa có bằng chứng rằng issuer đã được xác minh. Để test trust, cần integration test với Token Endpoint/JWKS.

### 7.2. Pairwise subject

Một OP có thể phát `sub` khác nhau cho cùng con người ở các client/sector khác nhau:

~~~text
Portal client: issuer A, sub pairwise-123
Mobile client: issuer A, sub pairwise-789
~~~

Không tự gộp theo email. Khi sản phẩm cần cross-client identity linking, phải dùng workflow và provider-approved identifier/correlation. Test cả hai hướng: **không auto-merge**, nhưng user hợp lệ có thể **explicitly link** khi đã chứng minh quyền sở hữu cả hai identities.

## 8. Database schema: unique identity, account và tenant riêng

Một thiết kế dữ liệu minh họa:

~~~sql
CREATE TABLE internal_account (
    id UUID PRIMARY KEY,
    status VARCHAR(20) NOT NULL
);

CREATE TABLE external_identity (
    id UUID PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES internal_account(id),
    issuer VARCHAR(512) NOT NULL,
    subject VARCHAR(512) NOT NULL,
    registration_id VARCHAR(100) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uq_external_identity UNIQUE (issuer, subject)
);

CREATE TABLE tenant_membership (
    account_id UUID NOT NULL REFERENCES internal_account(id),
    tenant_id UUID NOT NULL,
    role VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (account_id, tenant_id)
);

CREATE TABLE report (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    title VARCHAR(200) NOT NULL
);
~~~

Đây là PostgreSQL-oriented schema minh họa, chưa bao gồm migration/versioning/indexes/audit/soft-delete. Nếu sản phẩm chủ ý cho một external identity thuộc nhiều internal accounts hoặc tách account theo tenant, **phải thiết kế invariant/unique constraint khác** một cách rõ ràng; không bỏ constraint mà không thay bằng business rule tương đương.

### 8.1. Tại sao không unique theo email?

~~~sql
-- PHẢN VÍ DỤ cho multi-issuer identity:
CREATE UNIQUE INDEX uq_external_email
ON external_identity(email);
~~~

Email có thể thay đổi, tái sử dụng, chưa được xác minh hoặc trùng giữa issuers. Không dùng email làm khóa định danh toàn cục của OIDC.

### 8.2. Test constraint ở database thật

~~~java
@Test
void identicalIssuerAndSubjectCannotLinkToTwoAccounts() {
    identityRepository.insert(
        accountAlice, "https://id-a.example.test", "shared-100");

    assertThrows(DataIntegrityViolationException.class,
        () -> identityRepository.insert(
            accountBob, "https://id-a.example.test", "shared-100"));
}
~~~

Đây là **test fragment**: giả định repository đã triển khai bằng database thực và lỗi unique constraint được translate thành `DataIntegrityViolationException`. Test với Testcontainers PostgreSQL/JDBC/R2DBC thực tế phù hợp, không chỉ với in-memory fake.

### 8.3. Multiple tenants là membership, không phải đổi user ID

Một internal account có thể là member của Alpha và Beta với role khác nhau. Khóa identity không cần đổi khi chọn tenant:

~~~text
identity (issuer A, sub carol-200)
    -> internal account Carol
         -> membership Alpha (REPORT_VIEWER)
         -> membership Beta  (BILLING_READER)
~~~

Đổi active tenant phải làm **authorization check lại**, không dùng cached role của Alpha để cấp quyền ở Beta.

## 9. Thiết kế TenantContext từ nguồn tin cậy

Ứng dụng có thể nhận tenant từ path:

~~~http
GET /tenants/t-beta/reports/report-002
~~~

`t-beta` ở URL chỉ là **requested tenant**, không chứng minh caller được phép truy cập tenant đó.

### 9.1. Authorization rule

~~~text
Authentication đã verify
        |
        v
Resolve internal account theo issuer + subject
        |
        v
Verify tenant membership/account status
        |
        v
Verify required role inside requested tenant
        |
        v
Verify report.tenant_id == requested tenant
        |
        v
Return report
~~~

### 9.2. Interface policy minh họa

~~~java
package com.example.security;

import java.util.UUID;
import reactor.core.publisher.Mono;

public interface TenantAuthorization {

    Mono<Void> requireMembership(
        UUID internalAccountId, UUID tenantId);

    Mono<Void> requireRole(
        UUID internalAccountId, UUID tenantId, String role);
}
~~~

`Mono<Void>` **complete** khi hợp lệ, phát `AccessDeniedException` khi bị từ chối. Nếu service trả `Mono<Boolean>`, caller phải kiểm tra true/false rõ ràng trước khi tiếp tục.

### 9.3. Không tin header `X-Tenant-Id` một cách mù quáng

Nếu gateway/trusted reverse proxy thêm tenant header, backend phải có trust boundary và kiểm tra identity/membership. Header do Internet caller tự đặt không trở thành bằng chứng truy cập.

## 10. Kiểm thử Object-Level Authorization, không chỉ tenant-level

Một service minh họa:

~~~java
package com.example.report;

import java.util.UUID;
import reactor.core.publisher.Mono;

public class ReportService {
    private final TenantAuthorization authorization;
    private final ReactiveReportRepository reports;

    public Mono<Report> getReport(
            UUID accountId, UUID requestedTenant, UUID reportId) {

        return authorization
            .requireRole(accountId, requestedTenant, "REPORT_VIEWER")
            .then(reports.findByIdAndTenantId(reportId, requestedTenant))
            .switchIfEmpty(Mono.error(
                new org.springframework.security.access.AccessDeniedException(
                    "Report unavailable")));
    }
}
~~~

Fragment giả định `Report`, `ReactiveReportRepository` và constructor dependencies được cung cấp. Phần quan trọng là query repository theo **report ID và tenant ID**, không chỉ `findById(reportId)` rồi dựa vào việc frontend ẩn button.

### 10.1. Tests cần có

| Case | Membership | Report owner | Kết quả |
| --- | --- | --- | --- |
| Alice xem Alpha report | Alpha | Alpha | 200, khi có role |
| Alice xem Beta report | Alpha | Beta | 403 hoặc 404 theo policy |
| Carol chọn Beta đúng role | Alpha + Beta | Beta | 200 |
| Carol chọn Beta nhưng dùng role Alpha | Chỉ role Alpha | Beta | Deny |
| Dave có token valid nhưng không membership | Không có | Alpha | Deny |
| User đổi path tenant còn report ID của tenant cũ | Alpha | Beta | Deny |

### 10.2. Repository spy/probe

Với Reactive, có thể dùng `PublisherProbe` xác nhận khi membership bị từ chối thì publisher đọc report **không được subscribe**:

~~~java
PublisherProbe<Report> probe =
    PublisherProbe.of(Mono.just(testReport));

Mono<Report> result =
    Mono.<Void>error(new AccessDeniedException("No tenant access"))
        .then(probe.mono());

StepVerifier.create(result)
    .expectError(AccessDeniedException.class)
    .verify();

probe.assertWasNotSubscribed();
~~~

Test này chứng minh **sequencing** của pipeline mẫu. Với controller thực, cần áp cùng ý tưởng vào repository/gateway mock hoặc quan sát query count.

## 11. Account linking là một giao dịch bảo mật riêng

Giả sử Alice đã đăng nhập bằng Corporate và muốn liên kết tài khoản Partner:

~~~mermaid
sequenceDiagram
    autonumber
    actor User
    participant RP as Spring Security RP
    participant DB as Identity Store
    participant OP as Partner OP
    User->>RP: POST /account/links/partner (CSRF protected)
    RP->>RP: Verify current account/session + step-up policy
    RP->>DB: Create expiring link intent bound to account/session/provider
    RP-->>User: Redirect Authorization Code + state + PKCE
    User->>OP: Authenticate as Partner identity
    OP-->>User: Authorization code + state
    User->>RP: OAuth callback
    RP->>RP: Validate state/PKCE/ID Token issuer + aud + nonce
    RP->>DB: Atomically claim unused link intent
    RP->>DB: Check external identity uniqueness
    RP->>DB: Link verified issuer + sub to intended account
    DB-->>RP: Committed or conflict
    RP-->>User: Linking result
~~~

Không biến mọi lần đăng nhập thành “liên kết tài khoản tự động”. Liên kết chỉ diễn ra sau **link intent** hợp lệ.

### 11.1. Link intent cần gì?

Một bản ghi server-side:

~~~text
attempt_id = random opaque identifier
target_internal_account_id = Alice
initiator_session_binding = one browser/session
expected_registration_id = partner
expected_issuer = https://id-b.example.test
created_at / expires_at
consumed_at = null
step_up_satisfied = true/false
status = PENDING
~~~

`attempt_id` không nên lộ dưới dạng đoán được. Cần phân biệt **link intent ID** với OAuth2 `state`/`nonce`; framework vẫn phải kiểm tra state/PKCE/nonce đúng flow. Trong multi-instance, pending link intent phải dùng shared store hoặc session architecture phù hợp.

### 11.2. Không lấy account mục tiêu từ callback query

Phản ví dụ:

~~~http
GET /login/oauth2/code/partner?code=...&state=...&targetUserId=victim-id
~~~

Nếu backend dùng `targetUserId` do browser tự điền để link identity mới, attacker có thể tìm cách liên kết danh tính của mình với victim. **Target account** phải lấy từ server-side link intent được tạo khi initiator đã authenticated, đã qua CSRF/session/step-up policy.

### 11.3. Không link bằng email

~~~text
Provider A: iss=A, sub=alice-a, email=shared@example.test
Provider B: iss=B, sub=bob-b, email=shared@example.test

=> Không chứng minh cùng người.
~~~

Kể cả cả hai trả `email_verified=true`, auto-link bằng email vẫn nguy hiểm khi email được tái cấp, alias hoặc user có nhiều danh tính không chủ ý liên kết.

## 12. Trạng thái linking và kết quả mong đợi

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> AUTHENTICATED_EXTERNAL: OP callback hợp lệ
    PENDING --> EXPIRED: Hết TTL
    PENDING --> CANCELLED: User hủy
    AUTHENTICATED_EXTERNAL --> LINKED: Transaction + uniqueness pass
    AUTHENTICATED_EXTERNAL --> CONFLICT: Identity đã thuộc account khác
    AUTHENTICATED_EXTERNAL --> DENIED: Sai session/account/provider/tenant
    LINKED --> [*]
    CONFLICT --> [*]
    DENIED --> [*]
    EXPIRED --> [*]
    CANCELLED --> [*]
~~~

Các invariants:

- Một attempt **chỉ được consume một lần**.
- `expires_at` ở quá khứ → reject dù callback token hợp lệ.
- Session/account đã logout hoặc đổi user → reject.
- Registration/issuer không khớp intent → reject.
- Identity đã link cùng account → có thể idempotent success theo policy.
- Identity đã link **account khác** → conflict; không tự chuyển ownership.
- Attempt bị cancel → callback muộn không được link.
- Database update và marking attempt consumed phải atomic.

### 12.1. Workflow phải có reauthentication policy

Với thay đổi nhạy cảm như gắn thêm phương thức đăng nhập, có thể cần **step-up/recent authentication**. Chỉ kiểm tra session tồn tại có thể không đủ nếu cookie bị đánh cắp hoặc session kéo dài nhiều ngày.

### 12.2. Đăng nhập bằng identity mới có thể đổi SecurityContext

Trong một số thiết kế, OAuth2 Login callback tạo principal mới và thay browser Authentication hiện tại. Nếu link intent chỉ dựa vào **Authentication sau callback**, target account có thể đổi từ Alice sang Bob. Hãy lưu binding với initiating account/session trước redirect, xác minh account identity và link operation theo transaction đã thiết kế, không lấy `currentAuthentication.getName()` sau callback làm target một cách mù quáng.

## 13. Bài test account-linking quan trọng nhất

| Test ID | Tình huống | Kỳ vọng |
| --- | --- | --- |
| LINK-01 | Alice link identity B chưa tồn tại | Thành công, external key gắn Alice |
| LINK-02 | B có email giống Alice nhưng chưa explicit link | Không auto-link |
| LINK-03 | Identity B đã liên kết Bob | Conflict, không chuyển sang Alice |
| LINK-04 | Attempt của Alice, callback trong session Bob | Reject |
| LINK-05 | Attempt expected issuer B, callback issuer A | Reject |
| LINK-06 | Callback `state` sai | Reject trước linking |
| LINK-07 | PKCE verifier sai hoặc code reuse | Reject |
| LINK-08 | Intent hết hạn | Reject, no DB mutation |
| LINK-09 | Attempt dùng lại lần thứ hai | Idempotent read-only hoặc reject |
| LINK-10 | Hai requests link same identity vào hai accounts | Chỉ một transaction thành công |
| LINK-11 | Alice logout trước callback | Reject theo session policy |
| LINK-12 | Session fixation/CSRF attempt | Không tạo link intent trái phép |
| LINK-13 | Unlink identity cuối cùng khi account không có recovery | Block hoặc thêm recovery theo policy |
| LINK-14 | Unlink của Bob do Alice yêu cầu | Deny |
| LINK-15 | External identity email đổi | Identity key và link không đổi |
| LINK-16 | Pairwise `sub` khác theo client | Không tự link chỉ theo email |
| LINK-17 | OP từ chối consent | Không tạo link |
| LINK-18 | OP timeout/invalid ID Token | Không tạo link, có recovery UX |

Không chỉ assert response status. Cần đọc **database state sau mỗi test** để chứng minh không xuất hiện identity mới, không đổi owner, không mất membership/role và link attempt được consume/đánh dấu đúng.

## 14. Transaction và unique constraint bảo vệ concurrent links

Hai browser sessions có thể cùng hoàn thành callback:

~~~text
Request A: Alice muốn link (issuer B, sub shared-100)
Request B: Bob   muốn link (issuer B, sub shared-100)

T1: SELECT không thấy identity
T2: SELECT không thấy identity
T1: INSERT identity -> Alice
T2: INSERT identity -> Bob
~~~

Nếu thiếu database uniqueness, cả hai inserts có thể thành công trong race. Chỉ kiểm tra `existsByIssuerAndSubject` ở application **không đủ**.

### 14.1. Chiến lược

- `UNIQUE (issuer, subject)` tại database.
- Transaction atomically consume link intent và insert mapping.
- Handle unique violation thành **conflict**, không tự retry rồi chuyển mapping.
- Lock/compare-and-swap theo link attempt hoặc identity key nếu cần.
- Log conflict với safe metadata, không log raw ID Token.

### 14.2. Pseudocode transaction

~~~java
@Transactional
public LinkResult completeLink(
        UUID attemptId, VerifiedOidcIdentity identity) {

    LinkAttempt attempt = linkAttempts.lockPending(attemptId);
    requireNotExpired(attempt);
    requireCorrectSessionAndInitiator(attempt);
    requireExpectedRegistrationAndIssuer(attempt, identity);

    ExternalIdentityKey key = new ExternalIdentityKey(
        identity.issuer(), identity.subject());

    // Database UNIQUE(issuer, subject) là hàng rào cuối cùng.
    identities.insert(key, attempt.internalAccountId());
    linkAttempts.markConsumed(attemptId);
    return LinkResult.LINKED;
}
~~~

Đây là **pseudocode API nghiệp vụ**, không phải một đoạn compile độc lập. `VerifiedOidcIdentity` phải được tạo từ OIDC principal đã xác minh hoặc proof tương đương; không chấp nhận object từ JSON request tự do.

### 14.3. Concurrent test cần barrier thực sự

Một test chỉ chạy hai futures sau nhau không kiểm tra race. Dùng synchronization barrier/latch để hai transactions thật chạm DB gần đồng thời và assert:

~~~text
Success count = 1
Conflict count = 1
Number of external_identity rows for (iss,sub) = 1
Owner account = exactly one legitimate winner
Both link attempts have valid terminal status
~~~

Không dùng SQLite/in-memory behavior rồi giả định PostgreSQL/JDBC isolation luôn giống nhau. Test database production-like với Testcontainers.

## 15. Testcontainers PostgreSQL cho repository integration

Gradle dependencies ví dụ (phiên bản theo BOM dự án):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}
~~~

Một skeleton:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class ExternalIdentityDatabaseTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @Test
    void duplicateExternalIdentityIsRejectedByDatabase() {
        // Setup datasource với container, chạy migration,
        // insert cùng (issuer, sub) vào 2 internal accounts.
        // Assert UNIQUE violation và chỉ một owner tồn tại.
    }
}
~~~

**Đây là skeleton, chưa đầy đủ datasource wiring/`@DynamicPropertySource` hoặc Boot `@ServiceConnection`**, vì cách khai báo phụ thuộc Spring Boot version. Dùng migration SQL thật và DB transaction semantics thật khi thực hiện.

### 15.1. Test rollback không che việc commit

Một số Spring tests mặc định chạy trong transaction và rollback sau method, có thể làm concurrency behavior không giống production. Với concurrent link tests, các transactions/threads phải commit hoặc observe isolation như thật; không chỉ kiểm tra state trong cùng một transaction của test.

## 16. MockMvc với `oidcLogin()` để kiểm thử tenant authorization

Spring Security Test cung cấp `SecurityMockMvcRequestPostProcessors.oidcLogin()` để tạo `OidcUser` giả trong HTTP test.

~~~java
package com.example.integration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class TenantIsolationMvcTest {

    @Autowired MockMvc mvc;

    @Test
    void memberOfAlphaCannotReadBetaReport() throws Exception {
        mvc.perform(get("/tenants/t-beta/reports/report-002")
            .with(oidcLogin().idToken(token -> token
                .claim("iss", "https://id-a.example.test")
                .claim("sub", "shared-100")
                .claim("email", "alex@example.test"))))
            .andExpect(status().isForbidden());
    }
}
~~~

**Giả định:** ứng dụng có endpoint/path và fixtures Alice→Alpha, report-002→Beta, policy trả 403 khi denied. Nếu policy cố ý trả 404 để tránh information disclosure, assert 404. Test trên **chỉ xác minh application authorization nếu endpoint dùng identity/membership thật**; không validate chữ ký ID Token do `oidcLogin()` là mock.

### 16.1. Đừng hard-code kết quả mà không kiểm tra dữ liệu

Một test `.andExpect(status().isForbidden())` có thể vẫn xanh nếu endpoint ném 403 vì **thiếu CSRF**, **không có route đúng** hoặc user chưa qua Authentication, chứ không phải tenant authorization. Với GET sẽ không có CSRF trong cấu hình thường gặp, nhưng vẫn nên:

- Confirm đúng handler/route được gọi.
- Kiểm tra response/error category.
- Assert authorized Alpha request được 200.
- Assert Beta data không bị load.
- Dùng repository spy/metrics khi cần.

### 16.2. Registration ID cũng cần kiểm thử

`oidcLogin()` có thể cho custom `ClientRegistration` hoặc authenticated principal theo registration. Test rằng cùng issuer/sub với registration không được phép không nhận policy của registration khác. Đừng chỉ test claims khi registry lookup thực tế còn phụ thuộc registration ID.

## 17. MockMvc test provider collision

Sử dụng hai Test Principals:

~~~text
Principal A:
  iss=https://id-a.example.test
  sub=shared-100
  email=alex@example.test

Principal B:
  iss=https://id-b.example.test
  sub=shared-100
  email=alex@example.test
~~~

Assertions cần có:

1. A được resolve thành **internal account Alice**.
2. B được resolve thành **internal account Bob**.
3. `Alice.id != Bob.id`.
4. A không có Beta membership; B không có Alpha membership.
5. Logging/audit có đúng provider alias.
6. Khi email B đổi, external identity vẫn thuộc Bob.
7. Nếu registration B dùng claim khác, không tự fallback sang key của A.

Một service test minh họa:

~~~java
@Test
void sameRawSubAndEmailAcrossIssuersStaySeparate() {
    ExternalIdentityKey a =
        new ExternalIdentityKey("https://id-a.example.test", "shared-100");
    ExternalIdentityKey b =
        new ExternalIdentityKey("https://id-b.example.test", "shared-100");

    UUID aliceId = identityService.resolveAccountId(a);
    UUID bobId = identityService.resolveAccountId(b);

    assertNotEquals(aliceId, bobId);
}
~~~

Giả định service/repository và fixtures đã được tạo. Test chính là không có cross-issuer account collision, **không phải** giá trị string cụ thể.

## 18. Test OIDC protocol thật: hai mock OpenID Providers

MockMvc/`oidcLogin()` không tự gọi Authorization Endpoint, Token Endpoint hay JWKS. Để kiểm tra **provider isolation ở protocol layer**, tạo **hai mock OPs độc lập**.

~~~text
Mock OP A:
  issuer = https://id-a.test.example
  client_id = portal-a
  signing key = key-A
  authorization endpoint A
  token endpoint A
  JWKS endpoint A
  UserInfo endpoint A

Mock OP B:
  issuer = https://id-b.test.example
  client_id = portal-b
  signing key = key-B
  authorization endpoint B
  token endpoint B
  JWKS endpoint B
  UserInfo endpoint B
~~~

Các host test/example chỉ là **minh họa**. Trong CI, dùng test server có HTTPS hoặc explicit loopback test configuration theo ranh giới được phê duyệt.

### 18.1. Những response cần giả lập

| Endpoint | Positive case | Negative case |
| --- | --- | --- |
| Discovery A | Issuer/endpoints A | Trả issuer B hoặc JWKS URL sai |
| Authorization A | Code + correct state | Error, state mismatch |
| Token A | Signed ID Token A, Access Token A | `invalid_client`, `invalid_grant` |
| JWKS A | Public key A | Chỉ có key B, `kid` unknown |
| UserInfo A | `sub` bằng ID Token A | `sub` khác |
| Authorization B | Correct client and redirect | Nhận nhầm callback A |
| Token B | Signed ID Token B | Token dùng `aud=portal-a` |
| JWKS B | Key B | Signing key A |

### 18.2. Test issuer mismatch

Scenario:

~~~text
1. Browser bắt đầu /oauth2/authorization/corp-alpha.
2. OP A cấp authorization code bình thường.
3. Test OP trả ID Token có iss = issuer B.
4. RP phải reject authentication.
5. Không tạo internal account, không link, không save authorized client.
~~~

### 18.3. Test audience mismatch

~~~text
Expected clientId=portal-a
Returned ID Token aud=portal-b

=> Reject.
~~~

Audience của ID Token gắn với **OAuth client ID**, không phải tên Spring `registrationId`.

### 18.4. Test signing-key mix-up

ID Token khai `iss=A` nhưng được ký bằng key B (hoặc JOSE header dùng `kid` chỉ tồn tại trong JWKS B). Client A không được tìm key từ arbitrary URL do JWT header yêu cầu rồi chấp nhận token. Test phải giữ trusted issuer→JWKS mapping.

### 18.5. Test UserInfo subject mismatch

~~~text
ID Token A sub = user-101
UserInfo A sub = user-999

=> Không sử dụng UserInfo claims.
~~~

Quy tắc `UserInfo sub == ID Token sub` là yêu cầu của OpenID Connect Core. Không tự sửa bằng email match.

## 19. State, nonce, PKCE và issuer mix-up trong callback

Trong Authorization Code + OIDC:

- `state` liên kết callback với authorization request ban đầu.
- PKCE `code_verifier` phải khớp `code_challenge` của authorization request.
- `nonce` liên kết ID Token với OIDC request khi flow sử dụng.
- `issuer`/`aud` validation xác định token thuộc đúng OP/client.
- `registrationId`/client registration dùng để route token exchange chính xác.

### 19.1. Thử callback chéo

~~~text
Session 1 starts login with OP A
  -> state A, PKCE verifier A, nonce A

Session 2 starts login with OP B
  -> state B, PKCE verifier B, nonce B

Attack: send OP B callback/code into OP A callback path
  -> Must reject; no account link or session swap.
~~~

### 19.2. Test replay

Một authorization code hợp lệ thường **chỉ được dùng một lần**. Callback bị replay không được tạo link thứ hai, không đổi user session và không xoay liên kết sang account khác.

### 19.3. Test nhiều tabs

- Tab 1 khởi tạo link Partner.
- Tab 2 khởi tạo login Corporate.
- Callback Tab 1 đến sau callback Tab 2.

Nếu logic chỉ dùng “last provider selected” trong session mà không correlation theo request, có thể link sai. Test phải bảo đảm callback A chỉ tương ứng request A, và link intent/session binding được kiểm tra.

### 19.4. Không lộ code/state trong test artifacts

Browser HAR có thể chứa `code`, `state`, cookies, client secret và token response. Không đính kèm HAR thô vào CI artifact hoặc ticket. Redact before sharing.

## 20. Tính đúng của authorized-client store trong multi-provider

Spring Security lưu authorized clients theo những thành phần như:

~~~text
ClientRegistration + principalName
  -> Access Token
  -> Refresh Token (nếu có)
~~~

Ở Servlet:

~~~text
OAuth2AuthorizedClientService
OAuth2AuthorizedClientRepository
~~~

Ở WebFlux:

~~~text
ReactiveOAuth2AuthorizedClientService
ServerOAuth2AuthorizedClientRepository
~~~

### 20.1. Những lỗi cách ly thường gặp

- Store chỉ dùng `principalName=email`, bất chấp issuer.
- Hai registrations có cùng email và custom service dùng email làm khóa **không kèm registration**.
- Một token manager của background job load token user khác.
- Provider A bị `invalid_grant`, handler xóa mọi connections của cùng user, gồm B.
- Cache WebClient gắn default authorized client B vào API A.
- Refresh Token của registration A bị gửi tới Token Endpoint B.
- Dữ liệu tenant Alpha dùng token của tenant Beta hoặc ngược lại.

### 20.2. Test matrix authorized clients

| Case | Kỳ vọng |
| --- | --- |
| Save token A, load A | Lấy đúng token A |
| Save token B cùng principal alias, load B | Lấy token B, không ghi đè A |
| Load registration C chưa được cấp | Không trả token A/B |
| Refresh A thành công | Update A, B unchanged |
| A trả `invalid_grant` | Cleanup A theo policy, B unchanged |
| A timeout/503 | Không xóa A/B hàng loạt |
| Logout từ A | Không revoke B ngoài policy |
| User B cùng email với A | Không dùng token của A |
| Tenant switched | Không reuse token ngoài đúng account/resource scope |

### 20.3. Đừng tin `principalName` tự namespace issuer

Một số default implementations sử dụng tên principal theo OIDC `sub` hoặc customization. Khi triển khai custom store, cần thiết kế namespace theo identity/account/registration chính xác. Nếu app hỗ trợ pairwise subjects và multiple client IDs, key cần phản ánh chính sách đó.

### 20.4. Không log raw token trong test

Assert registration ID, client identity, expiration/opaque token hashes test-only, scopes, store record count và owner; tránh đưa raw ID/Access/Refresh Tokens vào report/log.

## 21. API scopes, authorities và tenant permissions là ba thứ khác nhau

~~~text
OIDC Login:
  User authenticated at OP

App role:
  ROLE_REPORT_VIEWER within tenant Alpha

OAuth2 Access Token:
  scopes: reports.read
  audience: reports-api

Resource Server:
  validates issuer, audience, expiration,
  scope and object-level access
~~~

Một `roles=["admin"]` claim trong OP B không chứng minh user là admin của tenant Alpha.

### 21.1. Test role mapping allowlist

| Claim input | Trusted source? | Kỳ vọng |
| --- | --- | --- |
| Issuer A: `app_roles=["report-reader"]` | A đã verify | Map theo policy A |
| Issuer B: `app_roles=["report-reader"]` | B đã verify nhưng khác contract | Không dùng mapping A tự động |
| Issuer B: `app_roles=["admin"]` | B, unknown role | Không tạo ROLE_ADMIN |
| Issuer A: wrong claim type string/object | A nhưng schema sai | Fail closed |
| Issuer A: claim thiếu | Không rõ quyền | Không tự cấp |
| Entra: `tid` ngoài allowlist | Tenant không chấp thuận | Từ chối |
| Google: email suffix đúng nhưng `hd` không chứng minh Workspace | Claim chưa đủ | Không tự cấp membership |

### 21.2. `GrantedAuthoritiesMapper` không tự đọc Access Token

OIDC principal authorities thường dựa ID Token/UserInfo và cấu hình Spring Security. Nếu provider chỉ phát `roles` trong Access Token của API khác, đừng âm thầm lấy Access Token JWT chưa kiểm tra như OIDC principal. Test rõ **nguồn claim**, issuer, token audience và mapper.

### 21.3. Kiểm tra revoked memberships

Nếu tenant admin xóa membership của Alice khi phiên OIDC vẫn còn:

~~~text
Authentication tại OP vẫn có thể còn hợp lệ.
Tenant membership tại Portal đã bị thu hồi.
=> Requests tiếp theo phải tuân theo membership policy mới.
~~~

Kiểm thử cache invalidation, session/authority freshness, token expiration và business policy. Không coi local roles cached vĩnh viễn là nguồn chân lý nếu membership đã thay đổi.

## 22. Test truy cập chéo bằng resource ID có thể đoán

Một nhóm test quan trọng là **object-level authorization**:

~~~http
GET /tenants/t-alpha/reports/report-alpha-1
GET /tenants/t-alpha/reports/report-beta-1
GET /tenants/t-beta/reports/report-beta-1
~~~

Với Alice chỉ có quyền Alpha:

- Request 1 được phép nếu đúng role.
- Request 2 bị từ chối vì report thuộc Beta dù URL nói Alpha.
- Request 3 bị từ chối vì không có Beta membership.

### 22.1. BOLA không chỉ là GET

Test cả:

~~~text
GET     /reports/{id}
PATCH   /reports/{id}
DELETE  /reports/{id}
POST    /tenants/{tenantId}/reports
POST    /tenants/{tenantId}/members
POST    /tenants/{tenantId}/invitations
POST    /accounts/{id}/links
DELETE  /accounts/{id}/links/{linkId}
~~~

Đối với state-changing requests cần CSRF khi dùng cookie-auth browser app. Nếu dùng JSON API bearer tokens, authorization policy vẫn phải kiểm tra owner tenant và role.

### 22.2. Error không được tiết lộ dữ liệu tenant khác

Khi denied, response body không chứa report name/owner email/organization metadata của Beta. Test cả **body**, headers, redirects và exception messages; không chỉ status 403.

## 23. Lựa chọn tenant trên UI không phải authorization

Một UI có dropdown chọn tenant:

~~~text
Active tenant: Alpha
User changes to Beta
~~~

Kết quả phải phụ thuộc **membership hiện tại của user trong Beta**, không chỉ client-side state. Nếu Beta không được phép, backend phải từ chối dù frontend gửi header/path/query đúng cú pháp.

### 23.1. Session active tenant

Nếu application lưu `activeTenantId` trong session, hãy kiểm tra:

1. Khi user đổi tenant, backend verify membership.
2. Session chỉ lưu tenant sau khi verified.
3. Khi account switched, old tenant context không được giữ.
4. Nếu membership bị thu hồi, cached active tenant không bypass policy.
5. Multi-tab tenant switch không làm request dùng quyền sai tenant.

### 23.2. Hostname/subdomain routing

Một ứng dụng có thể dùng `alpha.portal.example.test` và `beta.portal.example.test`. Browser-supplied Host/X-Forwarded-Host cần trusted proxy validation. Không dùng hostname do caller tự khai báo làm bằng chứng member của tenant.

### 23.3. Service-to-service calls

Machine client credentials không có nghĩa service được phép truy cập mọi tenant. Test downstream API luôn có tenant authorization riêng và không tự dùng machine admin token để vượt delegated user permissions.

## 24. Account linking qua provider mới: anti-login-CSRF

Một cuộc tấn công **login CSRF/account linking confusion** có thể diễn ra khi attacker bắt đầu OAuth flow cho danh tính của mình rồi khiến victim browser hoàn tất callback để liên kết attacker identity với victim account.

### 24.1. Biện pháp cần kiểm thử

- Link initiation là state-changing action có CSRF protection phù hợp.
- Server lưu link intent gắn với victim's authenticated account/session.
- Authorization request lưu `state` và PKCE verifier an toàn.
- Callback phải thuộc cùng flow, đúng issuer/registration và không bị replay.
- User phải xác nhận link trong phiên hợp lệ theo risk policy.
- Có thể yêu cầu recent authentication/step-up.
- Dữ liệu link target không lấy từ URL/header caller tự sửa.
- Callback không bao giờ auto-link chỉ từ email giống nhau.

### 24.2. Negative test: callback từ session khác

~~~text
Session S1 (Alice):
  create link intent to Partner

Session S2 (Attacker):
  authenticate with Partner user attacker-p

Attack:
  try completing S1 link intent from S2 callback

Expected:
  link rejected
  Alice external identities unchanged
  Attacker identity remains under its own account/unlinked
~~~

### 24.3. Negative test: old link intent

Nếu intent hết hạn, bị cancel hoặc đã consume, callback hợp lệ về protocol **vẫn không được tạo link**. Test việc application xử lý idempotency/status rõ ràng.

### 24.4. Không tự “khôi phục” link bằng email

Một UX “Chúng tôi thấy email giống nhau; tự động gộp tài khoản cho bạn” có thể gây account takeover. Nếu sản phẩm cung cấp gợi ý linking, người dùng vẫn phải chứng minh quyền kiểm soát identities theo workflow an toàn.

## 25. Unlink, disconnect và logout cần test riêng

| Operation | Đối tượng | Không được hiểu nhầm |
| --- | --- | --- |
| Local logout | RP browser session | Không tự xóa external identity |
| OIDC RP-Initiated Logout | OP SSO session | Không tự revoke mọi Access Tokens |
| Disconnect connection | Authorized client/tokens | Không tự xóa internal account |
| Unlink external identity | Identity→account mapping | Không tự xóa tenant membership nếu không có policy |
| Delete account | Internal account và dữ liệu theo chính sách | Không đồng nghĩa tự revoke mọi provider grants |

### 25.1. Test unlink ownership

- Alice có thể unlink identity của chính Alice nếu đáp ứng reauthentication/recovery policy.
- Alice không thể unlink external identity của Bob bằng cách đoán link ID.
- Unlink một provider không xóa unrelated provider connections.
- Không xóa **identity cuối cùng dùng để login** nếu account không còn recovery path, trừ khi explicit account closure workflow.
- Đang có pending link attempt: unlink có làm invalid attempt theo policy?
- Concurrent unlink/login không tạo stale account ownership.

### 25.2. Test logout isolation

Logout Corporate A không mặc nhiên logout Partner B hoặc mọi tenants. Nếu product hỗ trợ global logout, cần explicit session registry/OP contracts và kiểm thử phạm vi chính xác. Logout một browser session không được hủy session người khác chỉ vì email trùng.

## 26. Spring Security WebFlux: WebTestClient + `mockOidcLogin()`

Với Reactive, có thể dùng `SecurityMockServerConfigurers.mockOidcLogin()`:

~~~java
package com.example.integration;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOidcLogin;

@SpringBootTest
class ReactiveTenantIsolationTest {

    @Autowired ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void authenticatedOidcUserWithoutMembershipIsDenied() {
        client.mutateWith(mockOidcLogin())
            .get().uri("/tenants/t-beta/reports/report-002")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

**Giả định:** ứng dụng đã có route/fixture và principal mặc định của `mockOidcLogin()` không có membership Beta; policy trả 403. Nếu cần issuer/sub cụ thể, dùng configurer/custom OIDC principal phù hợp test fixture.

### 26.1. Kiểm tra Reactor SecurityContext

`ReactiveSecurityContextHolder` sử dụng Reactor Context, không phải `SecurityContextHolder` ThreadLocal như Servlet. Test:

- User A Authentication không bị nhầm user B sau `publishOn`.
- Tác vụ reactive được compose trong request giữ đúng user/tenant.
- Không tự `subscribe()` vào API/audit/authorized client tách subscription.
- Không có Authentication → fail closed.
- Wrong tenant context → deny.

### 26.2. Unauthorized không subscribe downstream

Dùng `PublisherProbe` và `StepVerifier`:

~~~java
PublisherProbe<Report> downstream =
    PublisherProbe.of(Mono.just(testReport));

Mono<Report> result =
    Mono.<Void>error(new AccessDeniedException("No Beta membership"))
        .then(downstream.mono());

StepVerifier.create(result)
    .expectError(AccessDeniedException.class)
    .verify();

downstream.assertWasNotSubscribed();
~~~

Đây là fragment cho sequencing; cần import `reactor.test.*`, Reactor `Mono`, Spring `AccessDeniedException` và định nghĩa `testReport`. Nếu code thực dùng `Mono.when(authCheck, apiCall)`, API có thể đã được subscribe trước khi deny; test probe giúp phát hiện.

## 27. Test requests và response không bị trộn giữa hai users

Trong Reactive hoặc async Servlet apps, các requests của Alice/Bob có thể chạy cùng lúc:

~~~text
Request Alice -> issuer A/sub shared-100 -> tenant Alpha
Request Bob   -> issuer B/sub shared-100 -> tenant Beta

Concurrent:
  user context
  authorized client
  tenant ID
  report selection
  API token forwarding
~~~

**Assert:**

1. Alice response không chứa Beta data.
2. Bob response không chứa Alpha data.
3. Log correlation không in raw tokens.
4. `ReactiveSecurityContextHolder` đúng subscriber.
5. Custom cache key không chỉ dựa `sub`.
6. Database mutations không dùng `tenantId` từ shared mutable singleton field.

### 27.1. Shared mutable state anti-pattern

~~~java
// PHẢN VÍ DỤ: singleton bean lưu tenant của request vào field.
@Service
class UnsafeTenantService {
    private String currentTenant;

    void setTenant(String tenant) {
        this.currentTenant = tenant;
    }
}
~~~

Với concurrent requests, một request có thể ghi đè tenant của request khác. Dùng immutable request-scoped context/explicit tenant parameter, Reactor Context đúng cách hoặc server-validated session context, không field chia sẻ.

## 28. Kiểm thử token refresh và revocation trong multi-provider

Một Client A có Refresh Token R-A và Client B có R-B. Khi A trả `invalid_grant`:

~~~text
AuthorizedClient(A, Alice) -> invalid_grant
AuthorizedClient(B, Alice) -> vẫn hợp lệ
AuthorizedClient(A, Bob)   -> vẫn hợp lệ
~~~

### 28.1. Test `invalid_grant` scope

- Failure handler xóa/mark stale **đúng authorized client A/Alice**, không xóa B hoặc Bob.
- Không tự đánh dấu provider B là bị revoke.
- Reauthorization của A chỉ diễn ra với consent/session hợp lệ.
- Custom `OAuth2AuthorizedClientManager` không dùng token B để gọi API A.

### 28.2. Refresh Token rotation race

~~~text
Request 1 load Refresh R1 -> OP cấp R2 -> save version 2
Request 2 load Refresh R1 -> invalid_grant
Request 2 handler remove stale version 1

Expected:
  không xóa nhầm version 2
~~~

Sử dụng optimistic locking/single-flight refresh hoặc compare-and-swap tùy store. Test với OP mock điều khiển response order, không chỉ một request đơn.

### 28.3. Provider 503 khác revoked grant

Token Endpoint 503 không phải bằng chứng user revoke consent. Test giữ tokens/connections hợp lệ và dùng retry/backoff/circuit breaker theo provider. Không đánh dấu mọi users ở A là `REAUTH_REQUIRED` khi outage.

### 28.4. Token revocation vs local deletion

`removeAuthorizedClient(...)` chỉ xóa local store, không gửi RFC 7009 revoke endpoint. Test riêng HTTP revocation, pending queue và provider response. Cần bảo đảm revoke A không gửi R-B đến A endpoint hoặc ngược lại.

## 29. Multi-tenant delegated API calls: downstream phải enforce

Một Portal có thể gọi Resource Server:

~~~text
Spring OIDC Client RP
  -> Access Token for Reports API
  -> GET /reports/report-002
  -> Resource Server validates issuer/aud/scope/tenant/resource
~~~

Test thêm:

- Token của issuer A bị Resource Server B từ chối nếu không nằm trong trust config.
- Token dành cho UserInfo không được chấp nhận làm token Reports API.
- `aud=reports-api` đúng nhưng user không là member Beta → deny.
- Access Token có `reports.read` không đủ tạo `ROLE_TENANT_ADMIN`.
- Resource Server không tin `X-Role: ADMIN` do caller gửi.
- Machine-to-machine client credentials không tự thay delegated permissions của user.

### 29.1. `issuer + subject` vẫn chưa đủ cho object access

Kể cả đã resolve đúng Alice, authorization vẫn phải xét tenant và resource ownership. Test tầng API tách biệt với RP login, vì user có thể dùng API trực tiếp không qua UI.

### 29.2. Spring Security Resource Server tests

Khi kiểm thử Resource Server, `jwt()` request post processor có thể mock một JWT-authenticated principal và authorities; nó không tự verify chữ ký thật. Full JWT acceptance tests cần JWT decoder/trusted issuer/audience validation với signed test tokens.

## 30. Chẩn đoán provider-specific claims

Mỗi OP có thể phát claims khác nhau:

| Provider kiểu | Có thể có | Điều test bắt buộc |
| --- | --- | --- |
| Generic OIDC | `iss`, `sub`, profile/email | Không giả định email luôn có |
| Google Identity | `sub`, `email`, `hd` nếu phù hợp | Không dùng email suffix thay Workspace validation |
| Microsoft Entra ID | `tid`, `oid`, `sub`, optional groups/roles | Tenant allowlist, pairwise sub, group overage |
| Keycloak | Protocol-mapped realm/client roles | Claim placement và authority mapping theo cấu hình |
| Partner OIDC | `org_id`, `employee_id`, custom entitlements | Type/schema/trust và tenant mapping |

Đây là **những đặc điểm thường gặp**, không khẳng định mọi deployment phát cùng claims. Test theo **actual provider contract**, mock missing/invalid values và kiểm thử policy fail closed.

### 30.1. Entra `tid` không phải user ID

Hai users cùng tenant có cùng `tid`. Một user có thể có `oid` trong tenant, `sub` có thể pairwise. Không viết account lookup chỉ theo `tid`.

### 30.2. Google email `hd`/Workspace

Đuôi email `@company.example` không đủ chứng minh user thuộc Google Workspace company. Khi policy yêu cầu Workspace membership, đánh giá `hd`/provider docs và enforcement hiện tại; thêm negative tests cho email suffix spoof/reassignment.

### 30.3. Keycloak role claims

Nếu realm role nằm trong Access Token mà OIDC principal chỉ dùng ID Token/UserInfo, app không thể giả định `OidcUser` luôn chứa role. Test đúng **token placement** và provider mapper configuration; không tắt token audience validation để lấy claim.

## 31. Negative security test matrix toàn diện

| ID | Input bất lợi | Kỳ vọng |
| --- | --- | --- |
| PROVIDER-01 | ID Token B trong flow A | Reject, không login/link |
| PROVIDER-02 | Token issuer A, signed key B | Reject signature/trust |
| PROVIDER-03 | ID Token A với `aud=client-B` | Reject |
| PROVIDER-04 | Unknown registrationId | Không tạo arbitrary OP |
| PROVIDER-05 | UserInfo `sub` khác ID Token | Không dùng UserInfo data |
| PROVIDER-06 | Same raw `sub` ở issuers A/B | Không collide identities |
| PROVIDER-07 | Same email ở issuers A/B | Không auto-link |
| PROVIDER-08 | Same OP, pairwise `sub` khác clients | Không auto-merge |
| PROVIDER-09 | JWT `iss` malformed/unknown | Reject |
| TENANT-01 | Alpha member request Beta tenant | Deny |
| TENANT-02 | Alpha path + Beta resource ID | Deny |
| TENANT-03 | User claims `tid=Beta` nhưng no membership | Deny |
| TENANT-04 | Header `X-Tenant-Id` giả | Deny |
| TENANT-05 | Member Alpha role admin, Beta role viewer | Không dùng Alpha admin ở Beta |
| TENANT-06 | Membership bị revoke trong session còn sống | Deny theo freshness policy |
| TENANT-07 | Tenant switch ở two tabs | Không cross-apply context |
| LINK-01 | Alice attempts link Bob-owned identity | Conflict |
| LINK-02 | Link attempt từ session khác | Reject |
| LINK-03 | Expired/cancelled/consumed attempt | Reject |
| LINK-04 | Wrong `state`/PKCE/nonce | Reject |
| LINK-05 | Wrong issuer/registration vs intent | Reject |
| LINK-06 | Concurrent inserts same external key | Một owner duy nhất |
| LINK-07 | Email đổi | Mapping issuer+sub không đổi |
| LINK-08 | Unlink link không thuộc account | Deny |
| LINK-09 | Unlink identity cuối cùng trái recovery policy | Block |
| TOKEN-01 | A Refresh Token dùng ở B token endpoint | Reject; không gửi nhầm |
| TOKEN-02 | `invalid_grant` của A | Không xóa B |
| TOKEN-03 | B token trong API A | Không gửi |
| TOKEN-04 | Refresh concurrency R1→R2 | Không xóa R2 |
| TOKEN-05 | A outage 503 | Không auto-revoke B/other users |
| LOGOUT-01 | A local logout | Không xóa B ngoài policy |
| LOGOUT-02 | Logout Token B với session A | Không invalidate A |
| LOGGING-01 | Login/link failure | Không log token/code/session |

Mỗi negative test phải xác nhận **không có side effects trái phép**: identity rows, tenant memberships, authorized clients, audit events và Resource Server calls.

## 32. Các test flows thực tế

### A — Hai providers cùng phát `sub=42`

Alice-A và Bob-B đều có `sub=42`. RP cần tạo hai external keys khác nhau, không login Bob thành Alice hoặc trả Alpha report cho Bob.

**Assert:** 2 distinct identity rows, 2 internal users, memberships riêng, 403/404 cross-tenant.

### B — Email trùng nhưng hai người khác nhau

Corporate user và Partner user cùng `alex@example.test`.

**Assert:** không auto-link, không chia sẻ session/token, linking phải có explicit flow.

### C — Pairwise subject của cùng người

Same OP, Portal nhận `sub=pair-1`, Mobile nhận `sub=pair-2`.

**Assert:** không tự gộp bằng email; nếu user muốn liên kết, dùng workflow với proof/correlation được provider chấp nhận.

### D — Account linking conflict

Alice muốn link Partner identity đã thuộc Bob.

**Assert:** conflict; Bob vẫn owner; Alice không nhận quyền/token của Bob; không tạo duplicate identity row.

### E — Attacker sửa `targetAccountId` ở callback

Link intent thuộc Alice, attacker gửi callback với `targetAccountId=Bob`.

**Assert:** backend bỏ qua caller input; dùng server-side target và xác minh session/protocol; không link sang Bob.

### F — Một session link attempt bị replay

Lần đầu link thành công, browser gửi lại callback.

**Assert:** không tạo mapping thứ hai, không chuyển identity owner; báo duplicate/expired theo policy.

### G — Một user thuộc hai tenants

Carol thuộc Alpha/Beta nhưng roles khác.

**Assert:** switch sang Beta yêu cầu fresh Beta role check, không dùng Alpha admin quyền ở Beta.

### H — Đoán report ID của tenant khác

Alice thử `report-beta-1` qua URL Alpha và Beta.

**Assert:** cả hai denied, response không tiết lộ nội dung resource.

### I — OP B Signing Key bị đưa vào JWKS A

Test OP A trả token ký bằng key B.

**Assert:** ID Token validation reject, không tự trust bất kỳ key từ JWT header.

### J — UserInfo trả subject khác

Token A `sub=alice`, UserInfo A `sub=bob`.

**Assert:** UserInfo discarded/reject theo OIDC Core; không cập nhật Alice email/role từ Bob.

### K — Tenant membership bị thu hồi sau login

Alice login hợp lệ rồi admin thu hồi Alpha membership.

**Assert:** API requests tiếp theo tuân theo freshness/cache invalidation policy, không chỉ nhìn session OIDC còn active.

### L — Provider A refresh lỗi, B vẫn tốt

OP A trả `invalid_grant`, OP B token vẫn hợp lệ.

**Assert:** A connection cần reauthorization, B không bị cleanup; không xóa toàn bộ user authorized clients.

### M — Concurrent linking

Alice và Bob cùng link một external identity trong hai transactions.

**Assert:** database unique constraint giữ một owner, conflict được xử lý, không có lost update.

### N — Logout A khi browser còn B session

Ứng dụng logout một provider.

**Assert:** phạm vi theo product/OP contract; không tự revoke B hoặc account linking không liên quan.

### O — Multi-node callback

Authorization request được tạo ở node A, callback tới node B.

**Assert:** shared session/state store duy trì đúng `state`/PKCE; không link nếu correlation mất.

### P — Reactive Context bị trộn giữa concurrent users

Alice và Bob gửi API requests song song, service dùng global mutable tenant.

**Assert:** dữ liệu không lẫn nhau; thay state bằng immutable/request-scoped data hoặc Reactor Context.

## 33. CI test topology nên thiết kế thế nào?

~~~text
CI job: unit + controller tests
  JUnit, MockMvc, WebTestClient, mockOidcLogin

CI job: repository isolation
  Testcontainers PostgreSQL, migrations thật

CI job: OIDC protocol
  Test OP A + Test OP B
  Signing keys A/B, JWKS, Authorization/Token/UserInfo

CI job: browser flow
  Test browser A/B, SameSite cookies, PKCE/state/nonce

CI job: concurrency/chaos
  Link race, refresh rotation, session multi-node, OP 503

Optional sandbox contract:
  Provider-specific claims/scopes/logout behavior
~~~

### 33.1. Synthetic providers không thay thế provider thực

Mock OP tests chứng minh Spring Security/OIDC behavior trong môi trường kiểm soát. Provider thực có thể khác về claims, issuer tenancy, pairwise subject, scope/consent, JWKS rotation, UserInfo và logout. Nên có provider sandbox contract tests theo client registrations test riêng.

### 33.2. Test data phải ngẫu nhiên nhưng có collision chủ đích

Sử dụng deterministic fixture cho `shared-100`, same email, wrong tenant và two-session attacker scenarios; còn IDs của link attempts, `state`, nonce, token values trong run nên là test values ngẫu nhiên, tránh ghi chúng vào CI logs.

### 33.3. Test chạy song song và dữ liệu riêng

Mỗi test suite nên có schema/database isolation hoặc cleanup an toàn. Nếu các tests dùng chung identity row và chạy parallel, test có thể thất bại giả hoặc che race. Tách test cases nhưng giữ đúng concurrency scenarios có barrier.

### 33.4. Không dùng production credentials

Không ghi client secret production vào YAML test, screenshot, HTTP trace, HAR, WireMock mapping hoặc source repository. Test OP nên dùng signing keys phát riêng trong môi trường test.

## 34. Observability cho các thử nghiệm cô lập

Những event có ích:

~~~text
event=external_identity_link_attempt
provider_alias=partner
initiator_account_alias=internal-100
requested_tenant_alias=alpha
outcome=DENIED_SESSION_MISMATCH
correlation_id=link-test-62
~~~

~~~text
event=tenant_access_denied
provider_alias=corporate
tenant_alias=beta
reason_category=NO_MEMBERSHIP
resource_type=report
correlation_id=api-test-31
~~~

Đây là **formats minh họa**, không phải logs mặc định. Không log raw `sub`, ID/Access/Refresh Token, authorization code, client secret, browser session cookie hoặc toàn bộ ID Token claims.

### 34.1. Metrics

| Metric gợi ý | Ý nghĩa |
| --- | --- |
| `oidc_login_success_total` theo provider | Tỷ lệ thành công |
| `oidc_login_issuer_mismatch_total` | Phát hiện issuer/registration mix-up |
| `oidc_userinfo_subject_mismatch_total` | UserInfo/ID Token mismatch |
| `account_link_conflict_total` | Identity đã thuộc account khác |
| `account_link_expired_total` | Link attempt không hợp lệ theo TTL |
| `tenant_access_denied_total` | Deny theo membership/resource |
| `authorized_client_wrong_registration_total` | Token routing bug |
| `oauth2_refresh_invalid_grant_total` | Revoked grant/rotation race |
| `logout_session_scope_error_total` | Session mapping bất thường |

Metric labels không dùng email/raw subject/token values, tránh PII và high-cardinality. Khi xảy ra anomalous account-link conflicts, có thể cần security incident investigation, không chỉ UX error.

## 35. Checklist triển khai trước production

| Vấn đề | Đã chứng minh bằng test? |
| --- | --- |
| ID Token issuer/audience/signature đúng registration | Mock OP protocol integration |
| A ID Token không được chấp nhận dưới B registration | Negative issuer/JWKS tests |
| Same raw sub ở hai issuers không collide | Identity unit + repository tests |
| Same email không auto-link | App policy + HTTP tests |
| Pairwise sub không bị tự merge | Provider contract/linking tests |
| Account linking cần explicit intent | Session/CSRF/step-up tests |
| Link intent session/issuer/client binding | Two-session attack tests |
| Link attempt TTL/replay/cancel | State machine integration |
| Unique (issuer, sub) enforced tại DB | Testcontainers duplicate/race |
| Unlink ownership và last-login recovery | HTTP + repository |
| Tenant membership server-side | Policy/service tests |
| Resource tenant ownership được enforce | IDOR/BOLA tests |
| Role không leak chéo provider/tenant | Authority mapping tests |
| Claim thiếu/sai type fail closed | Provider-specific contract tests |
| Token store đúng registration/principal | Authorized-client tests |
| Refresh/revoke của A không ảnh hưởng B | Failure handler tests |
| Concurrent refresh không làm mất token mới | Controlled race tests |
| Logout/session của A không xóa B trái policy | Logout tests |
| Multi-node session/callback nhất quán | Browser+cluster integration |
| Reactive context không lẫn user/tenant | WebTestClient + StepVerifier |
| Denied không gọi downstream | PublisherProbe/repository spy |
| Không in credential/PII vào logs | Security logging tests |
| CI có mocks và provider sandbox | Test topology/operational plan |

## 36. Câu hỏi ôn tập

**1. Vì sao `sub` không thể là khóa user toàn cục khi có nhiều providers?**

Vì `sub` chỉ có ý nghĩa trong phạm vi issuer. Hai OP có thể phát cùng raw subject cho hai người khác nhau. Khóa external identity cần gắn issuer đã xác minh.

**2. Nếu hai OP đều trả cùng email verified thì có thể tự gộp accounts?**

Không nên. Email có thể đổi/tái sử dụng; cần user-intended secure account linking và chứng minh kiểm soát identities.

**3. `@WithMockUser`/`oidcLogin()` có chứng minh ID Token được OP ký đúng?**

Không. Đây là mock Authentication; cần test OP phát signed ID Token, JWKS, issuer/audience/nonce validation để kiểm thử protocol.

**4. Một user có `ROLE_REPORT_VIEWER` có thể xem reports của mọi tenant không?**

Không. Phải kiểm tra role **trong tenant mục tiêu**, tenant membership và resource ownership.

**5. Tại sao database unique(issuer, subject) quan trọng với account linking?**

Vì hai concurrent requests có thể cùng thấy “identity chưa tồn tại”. Application pre-check không thay database uniqueness/transaction.

**6. Callback đúng code nhưng link intent đã hết hạn thì sao?**

Không được link. Protocol authentication success không thay thế intent/session binding đã hết hạn.

**7. Khi account-link callback đổi SecurityContext, target account nên lấy ở đâu?**

Từ server-side link intent ràng buộc với initiating account/session, không từ principal mới sau callback hoặc query parameter do caller tự gửi.

**8. `invalid_grant` của provider A có lý do xóa token provider B không?**

Không mặc định. Cleanup phải scoped theo registration/principal/connection và phân biệt revoked grant với provider outage.

**9. Tại sao hai providers nên dùng signing keys test khác nhau?**

Để test có thể phát hiện code nhận nhầm JWKS/issuer. Dùng chung signing key có thể làm negative test không đại diện cho trust boundary thực.

**10. Test 403 cross-tenant đã đủ chứng minh an toàn chưa?**

Chưa. Cần assert đúng reason, không lộ response data, không gọi protected downstream, không phát sinh DB mutation và positive same-tenant test vẫn thành công.

## 37. Tài liệu tham khảo

- OpenID Connect Core 1.0, issuer/subject/ID Token/UserInfo: https://openid.net/specs/openid-connect-core-1_0.html
- OpenID Connect Discovery 1.0: https://openid.net/specs/openid-connect-discovery-1_0.html
- OAuth 2.0 Authorization Framework — RFC 6749: https://www.rfc-editor.org/rfc/rfc6749
- Proof Key for Code Exchange — RFC 7636: https://www.rfc-editor.org/rfc/rfc7636
- OAuth 2.0 Security Best Current Practice — RFC 9700: https://www.rfc-editor.org/rfc/rfc9700
- OAuth 2.0 Bearer Token Usage — RFC 6750: https://www.rfc-editor.org/rfc/rfc6750
- OAuth 2.0 Token Revocation — RFC 7009: https://www.rfc-editor.org/rfc/rfc7009
- JWT Best Current Practices — RFC 8725: https://www.rfc-editor.org/rfc/rfc8725
- Spring Security — OAuth2 Login (Servlet): https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html
- Spring Security — Advanced OAuth2 Login: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- Spring Security — MockMvc OAuth2 Login Tests: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html
- Spring Security — OAuth2 Client Authorized Clients: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html
- Spring Security — Reactive OAuth2 Login: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html
- Spring Security — Reactive OAuth2 Client: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html
- Spring Security — WebTestClient Security Testing: https://docs.spring.io/spring-security/reference/reactive/test/web/index.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security — OIDC Logout Servlet: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html
- Spring Security — OIDC Logout Reactive: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/logout.html
- Spring Framework — WebTestClient: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Testcontainers — PostgreSQL module: https://java.testcontainers.org/modules/databases/postgres/
- WireMock — Documentation: https://wiremock.org/docs/
- OWASP — Broken Access Control: https://owasp.org/Top10/A01_2021-Broken_Access_Control/
- OWASP — Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP — Cross-Site Request Forgery Prevention: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html

## 38. Tổng kết: identity, tenant, account linking và token đều cần kiểm thử cách ly

~~~text
Provider A --ID Token A--> Verify issuer A/signing key A/client A
      |                                     |
      |                                     v
      +-------------------------> (issuer A, subject A)
                                            |
Provider B --ID Token B--> Verify issuer B/signing key B/client B
      |                                     |
      +-------------------------> (issuer B, subject B)
                                            |
                                      Account lookup
                                            |
                        Explicit linking + uniqueness constraints
                                            |
                                      Internal account
                                            |
                                 Tenant membership + role
                                            |
                                  Resource tenant ownership
                                            |
                                 Scoped Access Token/API

Negative tests luôn cần:
  Same email / same raw sub / wrong issuer
  Wrong tenant / wrong resource / wrong role
  Wrong session / wrong state / replay link
  Concurrent link conflict / stale authorized client
  Cross-provider logout / refresh / revocation
~~~

**Sáu nguyên tắc cần nhớ:**

1. **Provider identity phải có issuer.** Raw `sub` hoặc email không đủ định danh người dùng giữa nhiều OP; thêm tests cố tình trùng giá trị.
2. **Tenant isolation cần được thực thi server-side.** Đăng nhập hợp lệ không chứng minh membership; phải kiểm tra đúng tenant role và resource ownership cho từng request.
3. **Account linking là một giao dịch có rủi ro takeover.** Phải có explicit intent, session/CSRF/step-up, state/PKCE, issuer binding và replay protection; không tự merge bằng email.
4. **Database constraints bảo vệ khỏi race.** Unique `(issuer, sub)`, transactions và conditional updates quan trọng không kém kiểm tra ở service.
5. **Authorized clients và tokens phải cách ly theo registration/principal.** Lỗi refresh/logout/revoke của một OP không mặc nhiên ảnh hưởng mọi OP hoặc users khác.
6. **Kiểm thử nhiều tầng mới đủ.** `oidcLogin()`/`mockOidcLogin()` kiểm thử application policy, còn mock OP/JWKS/browsers, Testcontainers và provider sandbox tests mới xác minh ranh giới protocol và lưu trữ.

Một hệ thống đa provider, đa tenant chỉ thực sự an toàn khi **cùng một email, cùng raw subject, cùng browser, concurrent callbacks hoặc lỗi một provider** không thể làm quyền, token hoặc dữ liệu tràn sang account và tenant khác.
