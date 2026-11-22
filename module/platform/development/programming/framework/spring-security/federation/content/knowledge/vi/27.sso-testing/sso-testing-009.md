# Kiểm thử liên kết tài khoản, thiếu quyền nội bộ và người dùng đã bị khóa trong SSO

> **Module:** Spring Security – federation · **Nhóm:** Kiểm thử SSO. Bài Knowledge tập trung vào ba lỗi nghiệp vụ/bảo mật thường chỉ xuất hiện **sau khi xác minh SSO thành công**: (1) gắn định danh từ IdP vào **sai tài khoản nội bộ**, (2) người dùng có SAML Assertion/OIDC ID Token hợp lệ nhưng **không có quyền nội bộ** để truy cập chức năng, và (3) tài khoản đã **locked/disabled/suspended** ở RP vẫn được login do lập trình viên chỉ tin vào trạng thái IdP. Hướng dẫn mô hình danh tính, policy, các lớp kiểm thử, mã Java 17 độc lập, ví dụ Spring Security và ma trận trường hợp âm tính. Tất cả định danh, email, URI và tài khoản đều là dữ liệu thử nghiệm.

## 1. Bài toán: SSO thành công không đồng nghĩa được cấp tài khoản hoặc quyền

Giả sử một doanh nghiệp có IdP `https://idp.example.org` và ứng dụng báo cáo `https://reports.example.org`. Ứng dụng đã xác minh chữ ký và token SSO:

```text
SAML IdP / OIDC Provider
          |
          | signed assertion / validated ID Token
          v
Spring Security federation login
          |
          v
External identity:
  issuer  = https://idp.example.org
  subject = opaque-sub-92df
  email   = an@example.org
          |
          v
Local account resolver / link registry
          |
          +--> Local user ID: user-17
          +--> Local status: LOCKED
          +--> Local roles: []
          |
          v
Policy gate: reject even though IdP authentication succeeded
```

Một số anti-pattern:

- **Tự động nối theo email:** thấy `email=an@example.org` trong token rồi link ngay vào local account có cùng email. Người tấn công ở provider khác hoặc email được tái sử dụng có thể chiếm local account.
- **Mặc định thêm quyền:** người đăng nhập SSO chưa có record `LocalRole` thì tự cấp `ROLE_USER` hoặc `ROLE_ADMIN` để “không bị 403”.
- **Bỏ qua lock nội bộ:** IdP nói user đã authenticated, ứng dụng không kiểm `isAccountNonLocked`/`enabled` trong local store hoặc stale session tiếp tục truy cập.
- **JIT tạo trùng account:** không tìm thấy link ⇒ tạo local account mới dù một tài khoản đã disabled/locked hoặc tồn tại subject mapping khác.
- **Đọc email làm khóa:** email thay đổi, chưa verify, alias hoặc có thể bị tái sử dụng; gây duplicate/mislink.
- **Dùng OIDC mock rồi coi như full SSO đã được test:** `oidcLogin()` tạo principal giả và có thể bỏ qua link service nếu đường login thật chưa được gọi.

**Mục tiêu:** xác thực **ai do IdP khẳng định**, liên kết **đúng local identity**, kiểm tra **trạng thái local account**, rồi cấp đúng **local authority**. Nếu thiếu bằng chứng liên kết/quyền/trạng thái, áp dụng **deny by default**.

### 1.1. Kết quả học tập

Sau bài học, bạn sẽ:

1. Phân biệt external identity, local account, account linking, JIT provisioning, authentication và authorization.
2. Thiết kế khóa liên kết đúng cho OIDC `(iss, sub)` và SAML `(assertingPartyEntityId, persistent NameID và qualifiers cần thiết)`.
3. Hiểu vì sao `email_verified`, tên, phone hoặc một email trùng không đủ để liên kết một tài khoản đã có.
4. Mô tả luồng **link/unlink có reauthentication**, session binding, state/nonce/CSRF, ownership checks và uniqueness constraint.
5. Từ chối đăng nhập hoặc ít nhất từ chối protected action nếu thiếu **role/entitlement nội bộ**, tùy policy chức năng.
6. Từ chối account `LOCKED`, `DISABLED`, `SUSPENDED`/`DELETED` dù SAML/OIDC hợp chữ ký.
7. Tránh giả định `UserDetailsService` và `DaoAuthenticationProvider` tự động áp local account status lên federated login.
8. Viết kiểm thử unit, repository/transaction, MockMvc Security và full SSO callback, bao gồm active sessions sau lock.
9. Dùng Java 17 chạy độc lập mô phỏng login/link/role/status rules và kết quả stdout xác định.
10. Xây dựng telemetry, runbook và checklist không rò PII hoặc tài khoản tồn tại qua error response.

## 2. Phân biệt 5 khái niệm hay bị trộn

| Khái niệm | Ý nghĩa | Ai quyết định? |
| --- | --- | --- |
| **External authentication** | IdP xác thực danh tính và gửi signed assertion/ID Token | IdP, SP/RP phải validate |
| **External subject** | `sub` trong OIDC hoặc `NameID` trong SAML với issuer/context | IdP cung cấp, RP verify trước khi dùng |
| **Local account linking** | Ràng buộc external subject vào một local account ID | **RP**, dựa trên policy và bằng chứng sở hữu |
| **Local account status** | ACTIVE, LOCKED, DISABLED, CLOSED, PENDING | RP/user directory/HR với quyền quản trị |
| **Local authorization** | `REPORT_VIEWER`, `REPORT_ADMIN`, quyền trên project/tenant | App policy và trusted entitlement source |

**Authentication ≠ Account linking ≠ Authorization.** IdP có thể cấp bằng chứng người dùng là `opaque-sub-92df`, nhưng không có quyền tự quyết ID đó tương ứng local `finance-admin`, và càng không có quyền tự cho phép truy cập mọi báo cáo.

### 2.1. Bốn quyết định liên tiếp

```text
1. VERIFY FEDERATED ASSERTION
   Is token/assertion from trusted issuer for our RP?
          |
          +-- no --> reject, no local account mutation
          v
2. RESOLVE LOCAL ACCOUNT
   Is (issuer, subject) linked to a local account?
          |
          +-- no --> controlled JIT onboarding or reject
          v
3. CHECK LOCAL ACCOUNT STATE
   Is local account ACTIVE, not locked/disabled/expired?
          |
          +-- no --> reject and revoke/avoid authenticated session
          v
4. CHECK LOCAL ROLE / RESOURCE PERMISSION
   Does the account have verified RP-specific rights?
          |
          +-- no --> deny protected action, optionally deny login
          v
ALLOW only the authorized function
```

Trong mọi bước reject, **không tạo local authenticated session mới**, không ghi account-link trái phép, không auto grant role; bảo vệ CSRF/session cookies, và log reason code được sanitize.

### 2.2. Kiểm tra trước hay sau auth session?

Trong ứng dụng nghiêm ngặt, status `LOCKED` có thể khiến **federated login callback bị reject** trước khi `Authentication` được ghi vào `SecurityContext`. Với “thiếu role”, một ứng dụng có thể:

- **Strict login policy:** không có bất kỳ app role hợp lệ ⇒ reject login/không tạo authenticated app session.
- **Login allowed, feature denied:** tạo một session với **không có protected authorities**, cho phép trang onboarding không nhạy cảm; protected routes vẫn trả 403.

Cả hai có thể hợp lý nếu được mô tả rõ. **Không được biến user thiếu role thành admin hoặc cho phép protected data**. Bài demo Java chọn chính sách strict đối với tài nguyên `REPORT_VIEW` để dễ test.

## 3. Định danh liên kết phải ổn định và có nguồn phát hành

### 3.1. OIDC: dùng `issuer + subject`

Theo OIDC Core, `sub` là subject identifier trong phạm vi issuer; một `sub` string từ OP A không đồng nghĩa `sub` cùng text từ OP B là cùng người.

Khóa thường dùng:

```text
OIDC external identity key:
  protocol = OIDC
  issuer   = https://idp.example.org
  subject  = opaque-7f89c2

NOT:
  email = an@example.org
```

Issuer phải là **issuer trong ID Token đã xác minh**, không lấy tùy tiện từ query string/browser cookie. Kiểm `aud`, `exp`, `nbf`, `nonce`/`state` và signatures theo OIDC flow. Nếu app đa tenant, lưu tenant/provider registration đáng tin trong liên kết khi cần, không để subject từ tenant khác map cùng account.

### 3.2. Pairwise subject và account recovery

Một OP có thể phát pairwise `sub` khác nhau theo sector identifier. Nếu app được chuyển client registration hoặc sector, `sub` có thể đổi theo chính sách provider. Không tự ghép cặp dựa email khi migration; cần migration do admin/IdP xác thực hoặc user re-link có bảo vệ.

`email_verified=true` cho biết OP khẳng định email đã được verify theo quy trình của họ, **không** chứng minh user là chủ local account lịch sử của RP có cùng email. Email có thể được phân phối lại trong doanh nghiệp, đổi họ tên, thay domain, là shared mailbox hoặc có provider-specific semantics.

### 3.3. SAML: IdP entityID + NameID context

SAML Assertion chứa:

```xml
<saml:Subject xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:NameID
      Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
      NameQualifier="https://idp.example.org/saml"
      SPNameQualifier="https://reports.example.org/sp">
    opaque-saml-sub-77
  </saml:NameID>
</saml:Subject>
```

Đây là XML **đoạn minh họa** chưa có `Response`, chữ ký và bearer confirmation; không dùng đăng nhập thực. SAML link key cần gắn trusted asserting party entityID, NameID format và qualifiers phù hợp IdP contract. `NameID` có thể là transient, persistent, emailAddress hoặc format riêng; **transient NameID không phù hợp làm khóa local account bền vững** nếu giá trị thay mỗi lần.

Một rule thực tiễn:

```text
account_link(
  protocol,
  trusted_idp_entity_id,
  name_id_format,
  name_qualifier,
  sp_name_qualifier,
  stable_name_id_value
) -> immutable local_account_id
```

Không giả định bất kỳ `NameID` nào mang format `emailAddress` đều có quyền auto-link vào local account có email đó. Bản sắc bên ngoài phải đến từ **assertion đã được verified đúng chữ ký/issuer/audience/recipient/time/InResponseTo/replay**.

### 3.4. Không nối theo username/full name

Tên người hiển thị, `preferred_username`, email alias, `upn` hay `sAMAccountName` có thể không duy nhất giữa realms. “Đường dẫn LDAP DN chứa giống user” chưa chứng minh ownership. Nếu user bị đổi tên, linked account cần giữ local ID bất biến, không tạo account thứ hai.

### 3.5. Bảng mapping có constraints

Một schema minh họa:

```sql
CREATE TABLE local_account (
  id               VARCHAR(64) PRIMARY KEY,
  status           VARCHAR(20) NOT NULL,
  version          BIGINT NOT NULL,
  created_at       TIMESTAMP NOT NULL
);

CREATE TABLE external_identity_link (
  id               BIGINT PRIMARY KEY,
  local_account_id VARCHAR(64) NOT NULL,
  protocol         VARCHAR(10) NOT NULL,
  issuer_key       VARCHAR(512) NOT NULL,
  subject_value    VARCHAR(1024) NOT NULL,
  subject_format   VARCHAR(256),
  linked_at        TIMESTAMP NOT NULL,
  UNIQUE (protocol, issuer_key, subject_value),
  FOREIGN KEY (local_account_id) REFERENCES local_account(id)
);

CREATE TABLE local_grant (
  local_account_id VARCHAR(64) NOT NULL,
  role_code        VARCHAR(128) NOT NULL,
  tenant_id        VARCHAR(64) NOT NULL,
  PRIMARY KEY (local_account_id, role_code, tenant_id)
);
```

**Đây là schema thiết kế**, không phải DDL production: DB-specific types, collations, case sensitivity, indices, encryption/retention, nullable subject qualifiers và multi-tenant uniqueness cần hoàn thiện. Đặc biệt **không dùng NULL column như một phần unique key composite** mà không hiểu DB semantics; normalization của SAML qualifiers cần được xử lý bằng key chuẩn hóa hoặc constraint tương ứng.

**Lý do ràng buộc UNIQUE ở DB:** hai callback đăng nhập/linking chạy đồng thời không được gắn cùng external identity sang **hai local accounts**. Kiểm tra `exists()` rồi `insert()` không đủ nếu thiếu transaction isolation/unique constraint.

## 4. Mô hình liên kết tài khoản an toàn

### 4.1. Link không đồng nghĩa login

User đã có local account `user-17` và muốn thêm OIDC account từ IdP B:

1. User đăng nhập **local account hiện hữu** qua phương thức đang được tin cậy.
2. RP yêu cầu **reauthentication gần đây**/step-up cho thao tác nhạy cảm.
3. RP tạo linking transaction server-side với `state`, nonce, expiry, initiating local account, tenant, provider và CSRF/session binding.
4. Browser được chuyển tới **approved IdP** và trải qua flow SSO đúng protocol.
5. RP verify ID Token/SAML Assertion bằng trusted IdP registration, `state/nonce/InResponseTo` và replay controls.
6. Lấy external identity ổn định từ assertion/token **đã verify**.
7. Check local target account vẫn ACTIVE; không locked/disabled, không account takeover.
8. Transactional insert external link, đảm bảo unique external identity; nếu đã link sang account khác, **reject** và yêu cầu quy trình recovery/incident.
9. Rotate/invalidate sensitive session state nếu policy yêu cầu, audit event và notify user qua channel tin cậy.
10. Không cấp thêm local roles chỉ vì link mới; authorization vẫn do RP kiểm soát.

**Không** tạo link chỉ vì browser gửi query `?email=an@example.org` hoặc vì claim email trùng local account.

### 4.2. Tại sao phải có “hai bằng chứng”?

Để link **X (external identity)** vào **A (local account)**, RP phải có bằng chứng **user đang kiểm soát A** và **user vừa xác thực X**. Chỉ một bằng chứng không đủ:

- Chỉ đang login X nhưng không xác minh A ⇒ không được chiếm A theo email.
- Chỉ đang login A nhưng không verify X ⇒ attacker có thể gắn một external ID do họ tự khai.
- Cả hai có nhưng response không bound vào pending link state ⇒ **login CSRF/account-linking CSRF** có thể gắn identity của attacker vào session user.

Reauthentication cần fresh theo risk: thường xác minh local session đủ mới, MFA/step-up nếu sensitive, và code challenge/state không tái sử dụng.

### 4.3. Link initiated vs login initiated

Với OIDC, một callback sau authorization code exchange cần phân biệt mục đích:

```text
pending_flow = LOGIN
  -> resolve external identity to existing local account
  -> if unlinked, JIT/provision/reject by policy

pending_flow = LINK_EXISTING_ACCOUNT
  -> must have authenticated local account + recent reauth
  -> verify external identity + session-bound state
  -> link only to that same local account

NEVER:
  OIDC callback has any email => attach to first local account
```

Dùng một endpoint callback chung có thể được, nhưng **server-side state** phải phân biệt flow. Không coi `state` do browser tự gửi là quyết định được việc tạo link — validate nó với transaction đang lưu ở RP.

### 4.4. Unlink và last-factor lockout

Khi unlink:

- Yêu cầu authenticated local account, recent reauthentication và CSRF protection.
- Kiểm link thuộc account này; không xóa link của người khác bằng ID.
- Nếu đó là **phương thức đăng nhập cuối cùng**, cảnh báo và yêu cầu cấu hình recovery method được duyệt hoặc từ chối unlink theo policy.
- Thu hồi sessions/tokens/federated access gắn với link bị gỡ khi cần.
- Audit/notify; không ghi raw ID Token/SAML Assertion vào audit.
- Sau unlink, **external identity vừa gỡ phải không còn đăng nhập được vào A**.

### 4.5. Migration và merge tài khoản

Sát nhập hai local accounts có dữ liệu nghiệp vụ là một **security-sensitive merge**, không phải thao tác “update foreign key theo email”. Cần xác minh ownership của cả hai, policy xung đột quyền, historical logs, transactional migration và review. Khi untrusted external subject đột ngột xuất hiện với cùng email, **không tự merge**.

## 5. JIT provisioning — lúc nào được tạo account mới?

### 5.1. Không thấy link không có nghĩa luôn được tạo

Just-In-Time (JIT) provisioning có thể hợp lệ cho Portal nhân viên đã có verified enterprise IdP và invitation policy. Nhưng nếu RP chứa tài liệu tài chính/chăm sóc khách hàng, account creation có thể phải dựa invite, group eligibility hoặc administrator approval.

Khi SSO identity chưa linked:

| Điều kiện | Hành động |
| --- | --- |
| RP không cho phép JIT | Reject/login onboarding pending, không tạo account |
| JIT cho phép với expected issuer + tenant + validated entitlement | Có thể tạo local account với **minimum roles** theo policy |
| Email trùng local account đã tồn tại nhưng subject chưa linked | Không auto-link; require explicit verified link/recovery |
| Có local account LOCKED với email tương tự | Không tạo bypass account để vòng qua lock |
| User đã bị deprovisioned nhưng IdP vẫn phát valid token | Deny theo RP/HR authoritative status và policy |
| Subject thuộc external IdP chưa onboarding | Reject; không thêm issuer tự động |
| Invitation hết hạn hoặc đã được dùng | Reject, không tự tạo account |
| Concurrent JIT callbacks | Transaction/unique constraint chống duplicate |

### 5.2. JIT và idempotency

Hai callbacks của cùng external identity đến đồng thời:

```text
Callback A: external key K chưa có link
Callback B: external key K chưa có link

Unsafe:
  both create new account
  both try link K
  one fails, orphan account remains

Safer:
  transaction + unique external key
  upsert/retrieve canonical local account
  handle unique-conflict deterministically
  clean any orphan artifacts
```

Không chạy “if no row then insert” không có DB guard. Test concurrency 10–100 requests trong test DB, assert exactly one mapping and no orphans. Không auto-unlock account cũ khi nhận callback cùng email.

### 5.3. Invitation-based onboarding

Nếu cho phép automatic provisioning, ràng buộc invite tới **expected email/identity** tùy assurance của IdP, single-use, expiry, tenant, purpose và reauthentication. Email match có thể là **tín hiệu kiểm tra bổ sung** nhưng không phải bằng chứng duy nhất để link vào account có quyền cao. Những app quan trọng cần admin approval và verified ownership flow.

## 6. Quyền nội bộ không mặc định đến từ SSO token

### 6.1. IdP xác thực; RP phân quyền

OIDC `scope=openid profile email` là OIDC claim request, không phải `ROLE_REPORT_ADMIN` của ứng dụng. SAML `AttributeStatement` có thể mang groups hoặc roles nhưng RP **không bắt buộc** map toàn bộ thành privileged authorities. Role đáng tin phải được xác định bởi policy của ứng dụng, tenant, entity resource và source trust.

Ví dụ:

```text
IdP authenticated:
  issuer = https://idp.example.org
  subject = employee-tenant-scoped-id

Local account:
  id = user-17
  status = ACTIVE
  grants = []

Protected endpoint:
  GET /reports/financial
  requires REPORT_VIEW

Decision:
  access DENIED (no local grant)
```

Không cấp quyền chỉ vì token có `email_verified=true`, group `Employees` hay profile claim `department=Finance`. Nếu authorization contract chính thức dùng IdP entitlement, cần map rõ: **trusted issuer + audience + entitled value + tenant + freshness**.

### 6.2. Role names trong Spring Security

Spring Security thường dùng `GrantedAuthority` string như `ROLE_REPORT_VIEWER`. `hasRole("REPORT_VIEWER")` kiểm authority `ROLE_REPORT_VIEWER` với default prefix; `hasAuthority("REPORT_VIEW")` dùng đúng string. **Đừng trộn cách đặt tên** khiến test pass/fail sai.

Một user chỉ có `OIDC_USER` hoặc `SCOPE_openid` không tự có `ROLE_REPORT_VIEWER`. `@WithMockUser(roles="ADMIN")` trong unit test tự gán quyền cho mock; nó không chứng minh production mapping có cấp đúng hay không.

### 6.3. “Thiếu role” khác “không có local account”

| Trạng thái | Quyết định dự kiến |
| --- | --- |
| Unlinked subject | Deny hoặc controlled onboarding |
| Linked account ACTIVE nhưng grant set trống | Deny protected routes; có thể cho vào trang onboarding nếu policy |
| ACTIVE với ROLE_VIEWER nhưng endpoint cần ROLE_ADMIN | Authenticated, **403** cho admin feature |
| ACTIVE với role đúng nhưng grant của tenant khác | Deny access resource thuộc tenant hiện tại |
| Role expired/revoked | Deny/refresh, không dùng stale session indefinitely |
| IdP token claim “admin” nhưng local policy không phê duyệt | Không auto grant |
| IdP không gửi group claim optional | Không mặc định full access; xử lý fail closed |
| Role sync service timeout | Không tạo role admin tạm; chọn deny hoặc least-privileged grace theo approved policy |

### 6.4. Login reject hay 403?

Có hai acceptance criteria cần tách:

1. **SSO Login Policy:** nếu RP yêu cầu user có ít nhất một application entitlement, callback phải reject nếu không có role.
2. **Resource Authorization Policy:** callback có thể tạo session minimal, nhưng endpoint `/reports/**` vẫn phải deny nếu thiếu `REPORT_VIEWER`.

Khi test hãy ghi rõ đã chọn chính sách nào. Không gọi login success là lỗi nếu app cố ý chỉ cho onboarding, và không gọi protected endpoint 403 là SSO signature failure.

### 6.5. Freshness/role revocation

Role thay đổi giữa thời điểm SSO login và request sau. Một cached `SecurityContext` với granted authorities cũ có thể còn trong session. Với chức năng rủi ro cao, thiết kế:

- Re-read authoritative grants hoặc short authorization TTL.
- Revocation event cache invalidation.
- Session/token invalidation khi người dùng bị revoke.
- Method-level và object-level authorization, không chỉ path.
- Không mang raw LDAP groups sang browser/token nếu RP chỉ cần entitlement.

**Không tự đồng bộ quyền IdP mỗi request bằng cách bỏ cache hoàn toàn** khi availability không cho phép; thiết kế consistency risk và test window rõ.

## 7. Tài khoản bị khóa: trạng thái local phải thắng SSO success

### 7.1. Các trạng thái khác nhau

| Local status | Ý nghĩa ví dụ | Login/access policy |
| --- | --- | --- |
| `ACTIVE` | Có quyền dùng app nếu grants phù hợp | Evaluate roles/tenant |
| `LOCKED` | Bị khóa do admin/risk/abuse | Reject login và protected access |
| `DISABLED` | HR/IT tắt tài khoản | Reject |
| `SUSPENDED` | Tạm đình chỉ hoặc chờ review | Reject hoặc restrict theo policy được duyệt |
| `PENDING` | Chưa duyệt/onboarding chưa xong | Chỉ cho restricted onboarding |
| `CLOSED/DELETED` | Không còn được phép | Reject; không tự JIT tạo lại |

**Local lock khác IdP lock.** IdP có thể đang cho user đăng nhập các hệ thống khác; RP vẫn phải tuân status local. Ngược lại IdP account bị khóa nhưng user đã có session RP cũ, nếu chưa revoke thì có thể còn truy cập; cần policy cross-system logout/deprovision.

### 7.2. UserDetailsService có tự bảo vệ SAML/OIDC không?

**Không tự động.** Spring Security `UserDetailsService` được `DaoAuthenticationProvider` dùng phổ biến cho username/password authentication. Các phương thức `UserDetails.isEnabled()`, `isAccountNonLocked()`, `isAccountNonExpired()` liên quan **account-status checks ở flow/provider có sử dụng chúng**.

Một `Saml2Authentication` hoặc `OAuth2AuthenticationToken` có thể được tạo thành công **mà không gọi local UserDetailsService**, nếu ứng dụng không chủ động thực hiện local lookup/check. Do đó:

- Không chỉ bật `@Bean UserDetailsService` rồi cho rằng SAML/OIDC callback đã kiểm `locked`.
- Không tự dùng `Authentication.isAuthenticated()` làm dấu “local account active”.
- Cần **local account policy gate** ở đúng chỗ trước khi cấp full authenticated app session/authorities.
- Khi dùng `AuthenticationProvider` custom hoặc OIDC `OidcUserService`, preserve signature/issuer/audience/state/nonce validators của framework.
- Với SAML, chỉ xử lý principal **sau OpenSAML validation**, không tự parse raw XML/NameID.

### 7.3. SSO lockout khác chống đoán mật khẩu

Một user đăng nhập SSO không dùng local password, nên “sai mật khẩu local 5 lần” có thể không liên quan. Nhưng status lock vì security incident/HR termination hoặc admin rule **vẫn có hiệu lực** ở RP. Test đừng tự mở khóa khi nhận token SSO hợp lệ. Unlock phải qua authorized local workflow, audited và có revalidation.

### 7.4. Người dùng đã có session trước lúc khóa

Giả sử user login SSO lúc 09:00. Admin khóa account lúc 09:15. Nếu `HttpSession` đã giữ `ROLE_REPORT_VIEWER` và request lúc 09:16 không re-check local status, user có thể vẫn đọc dữ liệu.

Thiết kế tùy mức rủi ro:
- Khi lock: invalidate active sessions hoặc publish revocation event đến các nodes/regions.
- Với API stateless/JWT: token revocation/short TTL/introspection hoặc authorization gate kiểm trạng thái backend.
- Check account status ở sensitive endpoint hoặc cache status với TTL nhỏ.
- Phân tách **login-time denial** và **active-session revocation** trong test; một cái không thay cái kia.
- Không hứa `session.invalidate()` một node sẽ lập tức thu hồi mọi distributed sessions nếu kiến trúc không hỗ trợ.

### 7.5. SecurityContext và session fixation

Một callback SSO thành công không được tái sử dụng session attacker-controlled sau link state thay đổi. Spring Security session fixation protection có cấu hình riêng; test tạo session mới theo policy và bảo vệ cookies. Nếu login bị từ chối vì locked, không lưu `Authentication`, không render protected data ở request tiếp theo với same cookie; cần clear stale context.

## 8. Thứ tự quyết định local gate

Một policy minh họa cho ứng dụng báo cáo có thể là:

```text
external auth verified?                  NO -> DENY_UNTRUSTED_SSO
trusted issuer + subject present?        NO -> DENY_BAD_SUBJECT
link exists?                             NO -> DENY_UNLINKED
linked local account exists?             NO -> DENY_ORPHAN_LINK
status ACTIVE?                           NO -> DENY_LOCKED/DISABLED
role REPORT_VIEWER for current tenant?   NO -> DENY_MISSING_ROLE
resource-level access permitted?         NO -> DENY_RESOURCE
all checks pass?                        YES -> ALLOW
```

**Không được** để branch JIT chạy sau `DENY_LOCKED` theo hướng tạo account khác để vòng qua khóa. Một IdP identity đã link tới locked user không được phép tạo một local account mới vì “login không thành công”.

### 8.1. Mã lỗi chỉ dành nội bộ

Ví dụ reason codes:

```text
SSO_INVALID_ASSERTION
SSO_UNLINKED_EXTERNAL_SUBJECT
LOCAL_ACCOUNT_LOCKED
LOCAL_ACCOUNT_DISABLED
LOCAL_GRANT_MISSING
LOCAL_TENANT_MISMATCH
LINKING_PROOF_MISSING
LINKING_ALREADY_BOUND
SESSION_REVOKED
```

Bên ngoài, trả thông báo chung như “Không thể đăng nhập hoặc truy cập. Liên hệ quản trị viên nếu cần”, không tiết lộ email có tồn tại, account bị lock hay user đã có role nào. OWASP Authentication Cheat Sheet khuyến nghị **generic authentication errors** để hạn chế account enumeration. Logs nội bộ có thể giữ reason code/correlation ID, nhưng không raw JWT/SAMLResponse/email.

### 8.2. Kiểm tra trạng thái trước role

Một account LOCKED có thể vẫn còn role trong DB. Nếu code chỉ kiểm role và cho access khi `ROLE_REPORT_ADMIN` có, nó đã bỏ qua lock. Do đó thứ tự logical phải bảo đảm **status gate** áp dụng cho mọi allowed action; trên tầng authorization, revalidate status khi cần, không coi role là bằng chứng account đang active.

## 9. Spring Security OIDC: điểm gắn local policy có kiểm soát

### 9.1. Spring OIDC login component

Một OIDC login Spring Security dùng `OidcUserService` để tải/diễn giải user claims sau khi token validation do framework thực hiện. Tài liệu Spring Security cho phép delegate `OidcUserService` và map granted authorities. Có thể kết hợp một service riêng `LocalIdentityGate`, nhưng **không được thay thế việc verify ID Token bằng một parser tự viết**.

Fragment:

```java
import org.springframework.security.oauth2.client.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;

// Fragment: localIdentityGate là bean/adapter của RP.
// Mã này cần được nối vào SecurityFilterChain ở application.
OAuth2UserService<OidcUserRequest, OidcUser> gatedOidcService(
        LocalIdentityGate localIdentityGate) {

    OidcUserService delegate = new OidcUserService();

    return userRequest -> {
        OidcUser verifiedUser = delegate.loadUser(userRequest);
        String issuer =
            verifiedUser.getIdToken().getIssuer().toString();
        String subject = verifiedUser.getIdToken().getSubject();

        boolean allowed = localIdentityGate.isActiveAndEntitled(
            issuer, subject, "REPORT_VIEWER");

        if (!allowed) {
            throw new OAuth2AuthenticationException(
                new OAuth2Error("access_denied",
                    "Local account policy denied login", null));
        }
        return verifiedUser;
    };
}
```

**Đây là fragment minh họa**, không phải chương trình tự chạy: phải tự định nghĩa `LocalIdentityGate`, repo, entity/tenant policy và wiring. Trên đường login thật, token validation bao gồm issuer, audience, nonce/state, signing key, expiry và các controls do OIDC provider/client đảm trách. Không coi `isActiveAndEntitled` là phần của JWT signature verification.

### 9.2. Gắn service vào SecurityFilterChain

Ví dụ wiring trong một ứng dụng Spring Boot:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
SecurityFilterChain filterChain(
        HttpSecurity http,
        LocalIdentityGate localIdentityGate) throws Exception {

    return http
        .authorizeHttpRequests(a -> a
            .requestMatchers("/reports/**").hasRole("REPORT_VIEWER")
            .anyRequest().authenticated())
        .oauth2Login(o -> o
            .userInfoEndpoint(u -> u
                .oidcUserService(
                    gatedOidcService(localIdentityGate))))
        .build();
}
```

**Cần thêm local authority mapping thực**: fragment trên reject user không đủ local entitlement nhưng trả lại `verifiedUser` với authorities default của IdP/Spring, thường không có `ROLE_REPORT_VIEWER`. Để protected endpoint `hasRole("REPORT_VIEWER")` chạy đúng, implementation phải map **local grants đã kiểm** thành `GrantedAuthority("ROLE_REPORT_VIEWER")` của final Authentication (qua custom OidcUser/GrantedAuthoritiesMapper), không tự tin scopes hoặc roles từ IdP. Nếu không map, test có thể thấy login pass nhưng endpoint 403. Đây là lỗi cấu hình cần test, không phải cách “sửa” bằng cách mở `permitAll`.

### 9.3. Có cần custom OidcUser không?

Có thể dùng `GrantedAuthoritiesMapper` để map OIDC authorities, hoặc delegation-based OAuth2UserService để tải local grants rồi tạo `DefaultOidcUser` với authorities phù hợp. Tùy version Spring, `DefaultOidcUser` cần ID Token và UserInfo để tạo principal. Phải giữ trusted protocol claims/subject và chỉ cấp local authorities từ lookup đã kiểm status/tenant. Không copy raw `groups=admin` sang local ROLE_ADMIN nếu contract không duyệt.

### 9.4. Phải kiểm local lock trước khi trả principal

Nếu `localIdentityGate` phát hiện locked/disabled, ném `OAuth2AuthenticationException` phù hợp vào flow để failure handler xử lý, tránh tạo authenticated session. Nếu chỉ ở controller sau login hiển thị “locked” nhưng `SecurityContext` vẫn authenticated thì endpoints khác có thể cho access.

### 9.5. UserDetailsService không tự áp lên OIDC

Đặt một local `UserDetailsService` không bảo đảm `OAuth2LoginAuthenticationProvider` gọi nó. Đây là lý do cần test thực callback: `OidcUserService`/custom mapping hoặc local auth gate được gọi và failure được propagated **trước session establishment**.

## 10. Spring Security SAML2: sau validation vẫn phải kiểm local account

### 10.1. Không đọc raw NameID

Trong Spring Security Servlet SAML2, `OpenSaml5AuthenticationProvider`/tương đương ở release đang dùng verify Response/Assertion bằng trusted RelyingPartyRegistration. Sau khi validate, principal là `Saml2AuthenticatedPrincipal`.

Ví dụ **fragment controller chỉ đọc thông tin sau authentication**:

```java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication
        .Saml2AuthenticatedPrincipal;

public String viewName(
        @AuthenticationPrincipal Saml2AuthenticatedPrincipal user) {
    // Only after SAML authentication provider has validated assertion.
    return user.getName();
}
```

`getName()` không tự chứng minh đây là **persistent stable account key**. Cần liên kết cùng trusted asserting party entityID và NameID format/qualifiers theo registration. Một người có thể gửi NameID giống người khác ở issuer khác.

### 10.2. Chọn chỗ enforce

Tùy Spring Security release, có thể dùng **validated response authentication converter**, một wrapper provider sau OpenSAML validation hoặc service mapping trước khi publish final Authentication. Cần giữ nguyên signature, issuer, audience, Conditions, SubjectConfirmation, InResponseTo và replay validation. Nếu policy strict login, local status/role gate phải reject **trước khi authenticated session được lưu**.

Nếu kiến trúc chỉ kiểm status qua `AuthenticationSuccessHandler` sau khi provider đã tạo Authentication, cần bảo đảm failure path **clear SecurityContext/invalidate session** và không lộ protected resource trong callback; tốt hơn gắn kiểm soát tại conversion/provider boundary có thử nghiệm phù hợp.

### 10.3. Multi-tenant SAML

Nếu RP chấp nhận IdP A và IdP B, NameID string `employee-123` từ hai IdP không tự map chung local account. Map key theo approved `registrationId/entityID` + stable subject. Test IdP B signed assertion có cùng email/NameID với local admin A và chắc chắn **không** login thành A.

### 10.4. Mã SAML test cần signed fixtures

Một test SAML full callback cần:

- IdP test trusted signing certificate.
- RelyingPartyRegistration entityID/ACS/Recipient đúng.
- Valid signed Response/Assertion, `Conditions` và `SubjectConfirmationData` còn hạn.
- `InResponseTo` khớp pending AuthnRequest trong SP-initiated flow.
- Assertion/Response unique IDs, không replay, correct audience.
- Fake local account data với status/roles theo test case.
- Verify callback creates/does not create SecurityContext đúng policy.

**Không** sửa XML của signed fixture để đổi email/NameID/status rồi không ký lại. Failure lúc đó có thể do signature invalid, không chứng minh account linking gate hoạt động.

## 11. Spring Security test helpers: đúng công dụng, đúng giới hạn

### 11.1. MockMvc `oidcLogin()` chỉ là mock principal

Tài liệu Spring Security Test cung cấp:

```java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oidcLogin;

// Fragment trong Spring MVC Test có MockMvc.
mvc.perform(get("/reports/home").with(oidcLogin()));
```

`oidcLogin()` đưa một OIDC principal/test authentication vào request. Nó rất hữu ích để thử **controller/method/authorization** nhưng thường **không chạy full OAuth2 authorization code callback, token signature, user service linking và account gate**. Một test dùng `oidcLogin()` và `hasRole` pass không chứng minh disabled local user bị reject ở real login.

### 11.2. MockMvc authorities cần tường minh

Ví dụ:

```java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oidcLogin;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

// Fragment; không phải một JUnit test class độc lập.
mvc.perform(get("/reports/private")
    .with(oidcLogin()
        .authorities(new SimpleGrantedAuthority("ROLE_REPORT_VIEWER"))))
    .andExpect(status().isOk());

mvc.perform(get("/reports/private")
    .with(oidcLogin().authorities(
        new SimpleGrantedAuthority("OIDC_USER"))))
    .andExpect(status().isForbidden());
```

Expected `403` phụ thuộc authentication entry point, filter chain và route policy; với already authenticated user thiếu role thường là 403. **Không** hardcode outcome cho mọi app nếu failure handler redirect/login. Phải có proper imports/JUnit/Test config và test setup.

### 11.3. Kiểm thử custom linking service riêng

Mock principal + call vào `LocalIdentityGate` thật có thể test chính sách if controller dùng nó ở từng request. Nhưng full callback vẫn cần integration test vì **chính linking service có thể đã bị bypass** bởi login success handler, oauth2 user service path hoặc SAML converter.

### 11.4. `@WithMockUser` còn ít liên quan đến SSO hơn

`@WithMockUser(roles="REPORT_VIEWER")` chủ động tạo authenticated user với role được test khai báo. Nó hữu ích cho route authorization, không xác minh issuer, SAML NameID, OIDC sub, local linking, account lock hoặc IDP signature. Không dùng nó làm bằng chứng full federation security.

### 11.5. Full stack vs simulated tests

| Test level | Phần được kiểm | Không chứng minh |
| --- | --- | --- |
| Unit local gate | ExternalKey lookup, status, grants, link policy | SAML/OIDC token verification |
| DB transaction test | Unique constraint, race, rollback/consistency | ACS redirects/nonce |
| MockMvc `oidcLogin()` | Protected MVC route & method authorities | OAuth2 code flow, token parser, account linking callback |
| Test with mocked OidcUserService | Local exception flow/mapping wiring | Real ID Token signature |
| Real OIDC test OP/authorization server | State/nonce/code exchange, validated subject, link | SAML-specific signature validation |
| Real SAML test IdP signed fixtures | XML signature, issuer, InResponseTo, link/status gate | OIDC path |
| Multi-node session integration | Revocation after lock, distributed state | All IDP operational guarantees |
| Security/abuse tests | Enumeration, CSRF/link hijack, stale role | Business approval outside app |

**Một test suite hoàn chỉnh** không nhất thiết chạy full browser cho mọi role combination; unit tests exhaustive + một số E2E critical cases thường là cách hợp lý để vừa nhanh vừa có coverage thực.

## 12. Java 17 độc lập: kiểm thử link, thiếu role và tài khoản khóa

Ví dụ dưới đây mô phỏng **đăng nhập ngoài đã được xác thực** và một local account registry. Nó không chạy IdP/SAML/OIDC thật và **không nên dùng làm authentication provider production**. Mục đích là có một test oracle đơn giản, chạy được với JDK 17, để cho thấy:

- Liên kết chỉ được tạo khi có **local reauthentication + validated external proof + state binding**.
- External identity key gồm **issuer và subject**; email collision không tự link.
- Một external identity không thể link sang hai local accounts.
- Role được lấy từ **local account**, không từ external claims.
- `LOCKED`, `DISABLED` luôn bị từ chối dù đã link.
- Role trống ⇒ deny protected access.
- Khóa account **sau khi link** khiến đăng nhập kế tiếp bị từ chối.
- Unlink làm external identity không còn truy cập được.

Lưu file `SsoAccountLinkPolicyDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class SsoAccountLinkPolicyDemo {

    enum Status {
        ACTIVE, LOCKED, DISABLED
    }

    enum LoginDecision {
        ALLOW,
        DENY_UNLINKED,
        DENY_LOCKED,
        DENY_DISABLED,
        DENY_MISSING_ROLE
    }

    enum LinkDecision {
        LINKED,
        DENY_UNKNOWN_ACCOUNT,
        DENY_LOCAL_ACCOUNT_BLOCKED,
        DENY_NOT_VERIFIED,
        DENY_ALREADY_LINKED
    }

    record ExternalKey(String issuer, String subject) {
        ExternalKey {
            Objects.requireNonNull(issuer, "issuer");
            Objects.requireNonNull(subject, "subject");
            if (issuer.isBlank() || subject.isBlank()) {
                throw new IllegalArgumentException(
                    "issuer and subject must be nonempty");
            }
        }
    }

    record LocalAccount(
            String localId, Status status, Set<String> roles) {
        LocalAccount {
            Objects.requireNonNull(localId, "localId");
            Objects.requireNonNull(status, "status");
            roles = Set.copyOf(roles);
        }

        LocalAccount withStatus(Status next) {
            return new LocalAccount(localId, next, roles);
        }
    }

    static final class AccountGate {
        private final Map<String, LocalAccount> accounts =
                new HashMap<>();
        private final Map<ExternalKey, String> links =
                new HashMap<>();

        void register(LocalAccount account) {
            accounts.put(account.localId(), account);
        }

        void changeStatus(String localId, Status next) {
            LocalAccount account = accounts.get(localId);
            if (account == null) {
                throw new IllegalArgumentException(
                    "Unknown local account");
            }
            accounts.put(localId, account.withStatus(next));
        }

        LinkDecision link(
                String targetLocalId,
                ExternalKey external,
                boolean recentLocalReauth,
                boolean verifiedExternalProof,
                boolean stateBoundToSession) {

            LocalAccount account = accounts.get(targetLocalId);
            if (account == null) {
                return LinkDecision.DENY_UNKNOWN_ACCOUNT;
            }
            if (account.status() != Status.ACTIVE) {
                return LinkDecision.DENY_LOCAL_ACCOUNT_BLOCKED;
            }
            if (!recentLocalReauth || !verifiedExternalProof
                    || !stateBoundToSession) {
                return LinkDecision.DENY_NOT_VERIFIED;
            }

            // Demonstrates policy, NOT a safe concurrent DB transaction.
            if (links.containsKey(external)) {
                return LinkDecision.DENY_ALREADY_LINKED;
            }
            links.put(external, targetLocalId);
            return LinkDecision.LINKED;
        }

        LoginDecision login(
                ExternalKey external, String requiredLocalRole) {
            String localId = links.get(external);
            if (localId == null) {
                return LoginDecision.DENY_UNLINKED;
            }

            LocalAccount account = accounts.get(localId);
            if (account == null) {
                return LoginDecision.DENY_UNLINKED;
            }
            if (account.status() == Status.LOCKED) {
                return LoginDecision.DENY_LOCKED;
            }
            if (account.status() == Status.DISABLED) {
                return LoginDecision.DENY_DISABLED;
            }
            if (!account.roles().contains(requiredLocalRole)) {
                return LoginDecision.DENY_MISSING_ROLE;
            }
            return LoginDecision.ALLOW;
        }

        boolean unlink(
                String localId, ExternalKey external,
                boolean verifiedLocalReauth) {
            return verifiedLocalReauth &&
                    links.remove(external, localId);
        }
    }

    public static void main(String[] args) {
        AccountGate gate = new AccountGate();
        gate.register(new LocalAccount(
            "account-A", Status.ACTIVE, Set.of("REPORT_VIEWER")));
        gate.register(new LocalAccount(
            "account-B", Status.ACTIVE, Set.of()));
        gate.register(new LocalAccount(
            "account-C", Status.ACTIVE, Set.of("REPORT_VIEWER")));
        gate.register(new LocalAccount(
            "account-D", Status.ACTIVE, Set.of("REPORT_VIEWER")));

        ExternalKey a = new ExternalKey(
            "https://idp.example.org", "sub-A");
        ExternalKey b = new ExternalKey(
            "https://idp.example.org", "sub-B");
        ExternalKey c = new ExternalKey(
            "https://idp.example.org", "sub-C");
        ExternalKey d = new ExternalKey(
            "https://idp.example.org", "sub-D");

        // Setup is allowed while accounts are ACTIVE.
        gate.link("account-A", a, true, true, true);
        gate.link("account-B", b, true, true, true);
        gate.link("account-C", c, true, true, true);
        gate.link("account-D", d, true, true, true);
        gate.changeStatus("account-C", Status.LOCKED);
        gate.changeStatus("account-D", Status.DISABLED);

        System.out.println("Linked active account: " +
            gate.login(a, "REPORT_VIEWER"));
        System.out.println("Missing local role: " +
            gate.login(b, "REPORT_VIEWER"));
        System.out.println("Locked local account: " +
            gate.login(c, "REPORT_VIEWER"));
        System.out.println("Disabled local account: " +
            gate.login(d, "REPORT_VIEWER"));

        ExternalKey unknown = new ExternalKey(
            "https://idp.example.org", "sub-unknown");
        System.out.println("Unknown external subject: " +
            gate.login(unknown, "REPORT_VIEWER"));

        ExternalKey wrongIssuer = new ExternalKey(
            "https://other-idp.example.org", "sub-A");
        System.out.println("Same sub from wrong issuer: " +
            gate.login(wrongIssuer, "REPORT_VIEWER"));

        // Even if an email field happened to match account-A,
        // email is intentionally absent from ExternalKey.
        ExternalKey sameEmailDifferentSubject = new ExternalKey(
            "https://idp.example.org", "new-sub-same-email");
        System.out.println("Matching email never auto-links: " +
            gate.login(
                sameEmailDifferentSubject, "REPORT_VIEWER"));

        ExternalKey newIdentity = new ExternalKey(
            "https://second-idp.example.org", "new-sub-5");

        System.out.println("Link without local reauth: " +
            gate.link("account-A", newIdentity,
                false, true, true));
        System.out.println("Link without IdP proof: " +
            gate.link("account-A", newIdentity,
                true, false, true));
        System.out.println("Link without state binding: " +
            gate.link("account-A", newIdentity,
                true, true, false));

        System.out.println("Explicit verified link: " +
            gate.link("account-A", newIdentity,
                true, true, true));
        System.out.println("Duplicate link to other account: " +
            gate.link("account-B", newIdentity,
                true, true, true));
        System.out.println("New link gets only local role: " +
            gate.login(newIdentity, "REPORT_VIEWER"));

        gate.changeStatus("account-A", Status.LOCKED);
        System.out.println("Previously linked, now locked: " +
            gate.login(newIdentity, "REPORT_VIEWER"));

        gate.changeStatus("account-A", Status.ACTIVE);
        System.out.println("Unlink with local proof: " +
            gate.unlink("account-A", newIdentity, true));
        System.out.println("Unlinked identity denied: " +
            gate.login(newIdentity, "REPORT_VIEWER"));
    }
}
```

Biên dịch và chạy:

```bash
javac SsoAccountLinkPolicyDemo.java
java SsoAccountLinkPolicyDemo
```

Stdout **chính xác**:

```text
Linked active account: ALLOW
Missing local role: DENY_MISSING_ROLE
Locked local account: DENY_LOCKED
Disabled local account: DENY_DISABLED
Unknown external subject: DENY_UNLINKED
Same sub from wrong issuer: DENY_UNLINKED
Matching email never auto-links: DENY_UNLINKED
Link without local reauth: DENY_NOT_VERIFIED
Link without IdP proof: DENY_NOT_VERIFIED
Link without state binding: DENY_NOT_VERIFIED
Explicit verified link: LINKED
Duplicate link to other account: DENY_ALREADY_LINKED
New link gets only local role: ALLOW
Previously linked, now locked: DENY_LOCKED
Unlink with local proof: true
Unlinked identity denied: DENY_UNLINKED
```

### 12.1. Vì sao ví dụ chạy cho các kết quả trên?

- `account-A` ACTIVE có `REPORT_VIEWER` và link hợp lệ ⇒ ALLOW.
- `account-B` đã link nhưng set roles trống ⇒ DENY_MISSING_ROLE, không tự thêm role.
- `account-C` và `account-D` được link lúc ACTIVE, sau đó status chuyển LOCKED/DISABLED ⇒ login bị deny dù link vẫn có trong store.
- `sub-unknown` chưa tồn tại ⇒ DENY_UNLINKED, không JIT tạo tự động.
- `sub-A` ở issuer khác không trùng key `(issuer,subject)` của A ⇒ DENY_UNLINKED.
- “Matching email” chỉ là case mô phỏng: external subject khác vẫn deny; chương trình **không đọc email** để link.
- Không đủ local reauth, external proof hoặc state binding ⇒ DENY_NOT_VERIFIED.
- Đủ ba proof và account ACTIVE ⇒ LINKED. Cùng identity muốn link tới B ⇒ DENY_ALREADY_LINKED.
- External link mới vào A chỉ thừa hưởng **local role** của A qua lookup, không tin external groups.
- Sau khi A bị khóa, một linked identity khác cũng bị deny ngay ở lần kiểm status.
- Unlink có local proof xóa mapping; login qua identity đó không còn được phép.

### 12.2. Giới hạn bắt buộc trước production

Chương trình là policy demo, **không phải dịch vụ login thật**. Đặc biệt:

1. `verifiedExternalProof`, `recentLocalReauth` và `stateBoundToSession` chỉ là boolean do test cung cấp. Production **không** nhận booleans từ request body/browser; kết quả phải do trusted provider/session/transaction logic tạo.
2. HashMap không an toàn cho concurrency, không transaction, không uniqueness ở DB; link thật cần **unique index, transaction và conflict recovery**.
3. Không có SAML XML Signature/OIDC JWT verification, token expiry, nonce, state, InResponseTo, CSRF, replay hoặc TLS.
4. Không có tenant key/qualifiers/sector migration; production cần issuer/tenant isolation.
5. Không có account link notifications, freshness timestamp, risk-based step-up hoặc device assurance.
6. Không có active-session revocation sau lock, dù login mới sẽ deny.
7. `login` kiểm role được truyền từ caller; production requiredRole phải đến từ **server-owned authorization policy**, không query param client tự chọn.
8. Local roles chỉ là strings. Production cần authorities có tenant/resource scope, expiration và audit.
9. Enum reasons phục vụ internal tests; production external errors nên chung, không lộ account state.
10. Không có account recovery/unlink last-factor policy, compliance retention hoặc distributed cache invalidation.

## 13. Ma trận kiểm thử liên kết tài khoản

| ID | Tình huống | Kết quả bắt buộc |
| --- | --- | --- |
| LINK-01 | OIDC `(iss, sub)` đã link A, local account ACTIVE | Resolve chính xác A |
| LINK-02 | `sub` giống nhưng issuer khác | Không link A; deny/onboarding |
| LINK-03 | `iss` giống nhưng `sub` khác, email trùng | Không auto link A |
| LINK-04 | SAML NameID khác format/qualifier, cùng value | Không tự coi là cùng identity |
| LINK-05 | SAML transient NameID thay đổi mỗi login | Không tạo persistent link giả |
| LINK-06 | Account A chứng minh local reauth + external token verified + state bound | Link thành công nếu unique |
| LINK-07 | Chỉ xác thực external subject, không có local session proof | Reject |
| LINK-08 | Chỉ local login A, không verify external subject | Reject |
| LINK-09 | `state`/nonce/correlation sai hoặc hết hạn | Reject, không ghi mapping |
| LINK-10 | Link callback đến browser/session khác | Reject login CSRF/link hijack |
| LINK-11 | External subject X đã link A, cố link B | Reject, giữ link A |
| LINK-12 | Hai link callbacks đồng thời cùng X | Exactly one mapping; DB unique |
| LINK-13 | Existing local account LOCKED khi link | Reject; không auto unlock |
| LINK-14 | Email cũ được tái sử dụng cho nhân viên khác | Không chiếm account A |
| LINK-15 | User đổi email hợp pháp | Giữ stable link A, cập nhật optional profile |
| LINK-16 | IdP không có `email_verified` | Không tin email ownership; stable subject vẫn cần verify |
| LINK-17 | Pairwise subject thay sau sector migration | Controlled account migration, không auto merge |
| LINK-18 | Provider/tenant chưa onboarding | Reject, không auto add issuer |
| LINK-19 | Unlink khi thiếu recent local reauth | Reject |
| LINK-20 | Unlink link thuộc account khác | Reject, không xóa người khác |
| LINK-21 | Unlink link cuối cùng khi không có recovery method | Theo policy: reject/step-up |
| LINK-22 | Unlink thành công, old external identity login lại | Deny unless new verified linking flow |
| LINK-23 | Two local accounts with same display name | Không merge |
| LINK-24 | SAML assertion signed by IdP B claim NameID A | Chỉ dùng key of B; no cross-IdP account link |
| LINK-25 | User terminated rồi JIT callback lại | Không tạo bypass account theo email |
| LINK-26 | JIT allowed + invited + correct tenant + proof | Tạo tối đa một account với minimum grants |
| LINK-27 | Invalid SAML signature nhưng valid NameID | Reject trước link lookup/mutation |
| LINK-28 | OIDC ID Token sai `aud`/`iss` nhưng email trùng | Reject trước link |
| LINK-29 | Replay same link callback | Reject duplicate state/nonce/replay |
| LINK-30 | Audit link events | Có metadata tối thiểu, không raw tokens/PII |

### 13.1. Assertion “link đúng” phải kiểm đủ ba chiều

Không chỉ kiểm `login success`. Test cần assert:

1. Bảng `external_identity_link` có **đúng một** entry cho external identity.
2. `local_account_id` đúng đối tượng vừa reauthenticate.
3. Không có duplicate/orphan rows.
4. Local roles **không thay đổi** vì link nếu policy không có provisioning.
5. Session sau link chỉ có authorities của đúng local account.
6. Khi unlink hoặc account bị khóa, các sessions/refresh tokens tương ứng được xử lý theo policy.

## 14. Ma trận kiểm thử thiếu quyền nội bộ

| ID | Trạng thái SSO | Local grants | Tác động |
| --- | --- | --- | --- |
| ROLE-01 | Valid, linked, ACTIVE | `REPORT_VIEWER` | Protected viewer endpoint cho phép |
| ROLE-02 | Valid, linked, ACTIVE | Empty | Deny protected report; không auto role |
| ROLE-03 | Valid, linked, ACTIVE | `REPORT_VIEWER` | Admin endpoint deny |
| ROLE-04 | Valid, linked, ACTIVE | `REPORT_ADMIN` đúng tenant | Allow admin nếu resource policy phù hợp |
| ROLE-05 | Valid, linked, ACTIVE | `REPORT_ADMIN` tenant khác | Deny current tenant |
| ROLE-06 | Valid SAML assertion có `groups=Admins` | Local role absent | Không auto grant admin |
| ROLE-07 | Valid OIDC token có `scope=openid` | Role absent | Không coi scope là local role |
| ROLE-08 | IdP `groups` claim thiếu | Local policy requires group mapping | Deny/least-privileged according to policy |
| ROLE-09 | Local roles service timeout | Unknown | Fail closed cho protected action |
| ROLE-10 | Local role expired | Stale cached session | Revoke/refresh, deny sau TTL/event |
| ROLE-11 | User được thêm role sau khi login | Cache stale | Refresh/re-auth theo approved consistency |
| ROLE-12 | User bị rút role nhưng session còn | Old granted authority | Sensitive endpoint phải deny sau revocation policy |
| ROLE-13 | `hasRole("REPORT_VIEWER")`, authority chỉ có `REPORT_VIEWER` | Prefix mismatch | Test phát hiện sai mapping |
| ROLE-14 | `hasAuthority("REPORT_VIEW")`, chỉ có `ROLE_REPORT_VIEWER` | Name mismatch | Deny và sửa policy, không permitAll |
| ROLE-15 | Authenticated user thiếu quyền gọi REST API | Active but unauthorized | Thường 403, không 500/200 |
| ROLE-16 | Anonymous gọi protected route | No auth | Challenge/redirect, không giả làm authenticated |
| ROLE-17 | Same user multiple providers | One approved local account link | Role từ local ID, không cộng bừa role của providers |
| ROLE-18 | Role claim lạ/unknown | Local mapper unknown value | Ignore/reject, không elevate |
| ROLE-19 | Role chỉ có tên giống admin khác case | `admin` vs `ADMIN` | Không auto normalize thành privileged role |
| ROLE-20 | Role list từ client query | Untrusted | Không dùng làm authority |

**Dấu hiệu PASS:** không có data leakage, không tăng quyền; login policy được mô tả rõ. Một test MockMvc giả ROLE_ADMIN thành công **không** chứng minh real IdP claim đã được mapped; cần ít nhất một integration test dùng local grants thực.

## 15. Ma trận kiểm thử tài khoản khóa/vô hiệu hóa

| ID | IdP authentication | Local status | Kết quả |
| --- | --- | --- | --- |
| STATUS-01 | Valid SAML/OIDC | ACTIVE | Evaluate roles normally |
| STATUS-02 | Valid | LOCKED | Reject new login/protected access |
| STATUS-03 | Valid | DISABLED | Reject |
| STATUS-04 | Valid | SUSPENDED | Reject/restricted per policy |
| STATUS-05 | Valid | CLOSED/DELETED | Reject, no silent JIT recreation |
| STATUS-06 | Valid | ACTIVE but account expired | Reject theo local lifecycle |
| STATUS-07 | Valid with MFA | LOCKED | Vẫn reject; MFA không override lock |
| STATUS-08 | Valid, local role ADMIN | LOCKED | Reject; role không vượt lock |
| STATUS-09 | IdP disabled, existing RP session valid | RP ACTIVE | Deprovision event/session revocation test |
| STATUS-10 | Local locked after login | Old `HttpSession` | Revoke or backend status gate denies |
| STATUS-11 | Local locked on pod A | Session used on pod B | Distributed revocation works |
| STATUS-12 | Local unlock by authorized admin | Valid link, role | New login allowed after policy checks |
| STATUS-13 | SSO callback while admin locks account | Race | Atomic status decision; no newly active session |
| STATUS-14 | Old cached local account object says ACTIVE | DB says LOCKED | Cache invalidation/TTL test |
| STATUS-15 | Lock event arrives after local authorization cache populated | Stale grants | Deny within approved revocation SLA |
| STATUS-16 | Browser retains IdP cookies after lock | Fresh SSO from IdP succeeds | RP still rejects |
| STATUS-17 | Multiple external identities linked to locked local A | All identities | All must be denied |
| STATUS-18 | JIT tries create new local B after A locked with same email | Valid IdP token | No bypass/silent new account |
| STATUS-19 | Failure response exposes “account locked for an@example.org” | Any | Security QA fail (enumeration) |
| STATUS-20 | Audit record has full SAMLResponse/ID Token | Any | Security QA fail |
| STATUS-21 | User switches tenant in session | Status policy scoped | Validate local account + tenant grants |
| STATUS-22 | Lock + return to previous browser tab | Existing cookie | No access to protected resource |
| STATUS-23 | Lock during ongoing background export | Work authorization | Cancel/limit according to high-risk policy |
| STATUS-24 | Local DB fails to resolve account state | Unknown | Fail closed, do not assume ACTIVE |

### 15.1. “Tài khoản đã bị khóa” có nhiều nguồn

- **IdP/Directory lock:** người dùng không được xác thực mới tại IdP, nhưng RP sessions đang tồn tại có thể cần revoke.
- **Local RP lock:** SSO token vẫn valid, nhưng RP từ chối linked account.
- **Tenant-level suspension:** user có thể active trong tenant A nhưng suspended ở tenant B.
- **Risk/abuse flag:** không nhất thiết được lưu ở `UserDetails.isAccountNonLocked`; policy gate phải đọc đúng nguồn.
- **Legal/HR termination:** deprovision account/SCIM active=false và token/session invalidation riêng.

Từng nguồn cần có **precedence rule**. Thường nếu bất kỳ authoritative deny flag nào đang có hiệu lực đối với RP/resource, không được cho access chỉ vì một nguồn khác nói ACTIVE.

## 16. Kiểm thử end-to-end OIDC và SAML2 đúng đường đi

### 16.1. OIDC full callback checklist

1. Dùng **test OIDC Provider** có discovery/JWKS, issuer, client registration và signing key đáng tin.
2. Browser khởi tạo login, RP sinh `state`, `nonce`/PKCE theo flow.
3. IdP trả authorization code, Spring Security exchange tokens và validate ID Token.
4. Test principal có `(iss,sub)` cố định; local repository lưu account/link/grants/status.
5. Test active linked user: callback tạo authenticated session với correct authorities.
6. Test linked account missing role: protected routes deny hoặc strict login fail theo policy.
7. Test linked locked account: callback phải reject, không authenticated session.
8. Test same email from another subject/issuer: không login vào local account cũ.
9. Test explicit link flow: user hiện có local session + recent reauth và verified external proof.
10. Test replayed state, reused code, state from other session, wrong nonce/issuer/aud.
11. Test account lock **sau** successful login và session revocation.
12. Audit không log raw tokens, code, userinfo, link proofs.

### 16.2. SAML2 full ACS checklist

1. Test IdP phát **signed SAML Response/Assertion** bằng key đã đăng ký.
2. `RelyingPartyRegistration` có trusted IdP verification credentials, expected issuer/entityID, ACS và SP entityID.
3. Valid `Conditions`, bearer `SubjectConfirmationData`, `Recipient`, `InResponseTo`, `AudienceRestriction`, unique IDs.
4. Test stable persistent NameID/qualifiers gắn đúng local account.
5. Với NameID cùng text nhưng từ IdP khác, không map sai local account.
6. Với local locked/disabled, verified assertion vẫn dẫn tới fail application login.
7. Với no local role, protected routes deny/strict login reject.
8. Assertion expired/replayed/wrong audience phải bị reject **trước** local link mutation.
9. XML Signature Wrapping không làm app đọc unverified NameID.
10. Mỗi negative fixture được **ký lại hợp lệ sau khi đổi claims** nếu test mục tiêu là link/status; nếu sửa signed XML sau ký thì test chỉ chứng minh signature reject.
11. Revoke sessions khi lock after login; test across pods.
12. Không để raw Assertion XML/NameID/PII trong logs.

### 16.3. Cẩn thận sự phụ thuộc giữa các test

Nếu cùng một identity đã được link ở case trước, case “unlinked” tiếp theo có thể pass sai vì DB fixture không reset. Mỗi test cần transaction rollback/test schema isolation hoặc fresh identifiers:

```text
test-001 -> issuer A, sub unique-test-001
test-002 -> issuer A, sub unique-test-002
test-003 -> issuer B, sub unique-test-003
```

Không dùng production email hoặc person ID. Cleanup external links và active sessions của test environment sau mỗi test. Điều này đặc biệt quan trọng khi test JIT/concurrency vì dữ liệu phụ có thể tồn tại ngoài transaction.

### 16.4. Không tự khởi tạo RequestPostProcessor cho SAML từ raw XML

Spring Security Test có hỗ trợ nhiều loại SecurityContext mocks, nhưng **không đồng nghĩa mọi API của oidcLogin đều có bản SAML tương ứng trong mọi release**. Nếu muốn test full SAML ACS, dựng trusted IdP test và gửi signed fixture qua actual SAML2 filter. Controller unit tests có thể dùng verified principal giả do test harness tạo, nhưng phải ghi rõ **không test XML Signature**.

## 17. Thử bảo vệ session và active account lock

### 17.1. Hai giai đoạn độc lập

**Giai đoạn A — login-time:** RP từ chối callback nếu account đang LOCKED. **Giai đoạn B — after-login:** user đã có app session, sau đó account bị khóa; RP phải không cho tiếp tục dùng quyền nhạy cảm theo revocation SLA.

Ví dụ scenario:

```text
09:00:00  OIDC login of account-A succeeds.
09:00:10  Browser can GET /reports/summary.
09:01:00  Admin locks account-A in local DB.
09:01:01  RP publishes user-session revocation.
09:01:02  Browser reuses old JSESSIONID cookie.
EXPECTED: no confidential report data.
```

Không chỉ assert session cookie mới không sinh; phải thực sự gửi request tới protected route **với old cookie**. Nếu app dùng Spring Session Redis, verify session deletion/event propagation across nodes. Nếu JWT self-contained còn hiệu lực, app cần introspection/status check hoặc bounded expiry; không thể chỉ xóa `HttpSession` trong một node.

### 17.2. Role revoked after SSO

Tương tự: user role `REPORT_VIEWER` bị thu hồi lúc 09:01 nhưng session còn ROLE_REPORT_VIEWER. Nếu app yêu cầu revocation gần real-time, kiểm lại local role on request hoặc invalidate session. Test quyền sau revoke không được leak. Không dùng một test “mở trang login mới bị deny” thay test “session cũ bị thu hồi”.

### 17.3. Cache consistency

Một service có thể cache local status/entitlements. Cần định nghĩa **max stale window**: 0s cho cực kỳ nhạy cảm hoặc bounded TTL phù hợp business. Test:

- Cache mới ACTIVE, DB đổi LOCKED.
- Revocation event nhận ngay vs mất event.
- Expiry TTL vẫn enforce deny.
- Multi-region cache invalidation.
- Failure khi cache backend down: không assume ACTIVE.
- Stale session recover after load-balancer stickiness changed.

## 18. Ranh giới bảo mật của liên kết tài khoản

### 18.1. Account takeover qua email collision

Threat model:

```text
Victim has local account:
  localId = user-17
  email = a@example.org
  role = REPORT_ADMIN

Attacker authenticates at another permitted IdP:
  iss = https://other-op.example.org
  sub = attacker-unique
  email = a@example.org

Vulnerable RP:
  find local account by email -> user-17
  auto-link -> attacker becomes REPORT_ADMIN

Hardened RP:
  no existing (iss,sub) link
  email only a profile hint
  explicit link requires victim's local reauth
  otherwise deny/onboarding -> NO takeover
```

Đây là lý do cần link by stable issuer/subject và **không** auto merge theo email, kể cả email trông “verified”.

### 18.2. Login CSRF và forced account linking

Kẻ tấn công có thể khởi tạo OAuth/OIDC login bằng account của họ rồi dụ victim gửi callback/authorization response vào session victim. Nếu RP không bind `state`/nonce/callback đến session/pending link transaction, external identity attacker có thể bị gắn vào local account victim. Sau đó attacker dùng identity của mình đăng nhập vào account victim.

Controls: `state` server-side bound to session, nonce where required, CSRF protection, reauth, single-use linking transaction, expiration, link target local account fixed server-side. Test callback chéo browser/session, replayed state và race.

### 18.3. SAML IdP-initiated login

IdP-initiated SSO có thể thiếu `InResponseTo` theo profile. Không suy rằng thiếu request correlation là đã có đủ bằng chứng **liên kết vào local account hiện hữu**; linking là thao tác nhạy cảm và thường nên dùng SP-initiated flow có pending context. Nếu business bắt buộc IdP-initiated, thiết kế hardening riêng: trusted issuer, audience, recipient, replay, controlled onboarding and explicit account linking.

### 18.4. Local password recovery sau SSO linking

Một account có nhiều methods: local password, passkey, SAML, OIDC. Không bỏ qua lock vì user chuyển login method. Lock/suspension ở **local account ID** phải áp cho mọi linked method. Test user bị lock khi dùng OIDC A rồi dùng SAML B: vẫn deny. Recover/unlock phải qua authorized workflow có audit, không thông qua link mới đơn giản.

## 19. Race conditions và transaction tests

### 19.1. Unique link concurrency

Giả sử hai người cùng cố link same external identity X vào A và B:

```text
T1: see X absent
T2: see X absent
T1: insert X -> A, commit
T2: insert X -> B, attempt commit
EXPECTED: DB unique constraint rejects T2.
         A remains linked; B receives generic failure.
```

Dùng DB integration tests với real SQL storage, concurrent transactions và uniqueness assertion. Đừng chỉ test Java HashMap demo; HashMap không multi-thread safe và không thay DB unique constraint.

### 19.2. Link vs lock race

```text
T1: begin link A<-X
T2: admin locks A
T1: commit link and issue authenticated session?
```

Policy mạnh cần xét **account status tại điểm quyết định commit/session creation** với locking/optimistic version/transaction. Nếu A đã locked khi callback hoàn tất, không phát session. Nếu lock đến ngay sau login, phải revoke existing session. Test both orderings; kết quả “T1 lúc bắt đầu thấy ACTIVE” không đủ.

### 19.3. IdP subject reassignment và account merge

Một số legacy IdPs dùng usernames/email có thể bị reassign. Mỗi RP cần ký hợp đồng rằng identifier là stable/non-reassignable trong phạm vi issuer, hoặc dùng opaque internal UUID do IdP bảo đảm. Khi IdP migrate, không tự sử dụng subject string trùng như bằng chứng cùng người nếu trust contract thay đổi.

### 19.4. Transaction partial failure

Test:

- Local account được tạo nhưng link insert fail ⇒ rollback account creation hoặc deterministic cleanup.
- Link insert pass nhưng audit notification fail ⇒ không rollback identity security nếu audit logging có cơ chế durability riêng; bảo đảm recoverable event.
- Link insert pass nhưng session fails ⇒ không tạo duplicate links khi retry.
- Unlink thành công nhưng old refresh token still works ⇒ invalidate/revoke theo policy.
- Role map update partial khiến privileged role còn sót ⇒ transactional update hoặc deny until sync recovers.

## 20. Quan sát, mã lỗi và không lộ dữ liệu cá nhân

Một log an toàn có thể là:

```json
{
  "event": "federated_login_denied",
  "protocol": "oidc",
  "provider_registration": "corporate",
  "reason_code": "LOCAL_ACCOUNT_LOCKED",
  "local_account_ref": "pseudonymous-event-ref",
  "policy_version": "local-gate-v3",
  "correlation_id": "opaque-request-id",
  "result": "rejected"
}
```

Không đưa raw `id_token`, `access_token`, `SAMLResponse`, NameID, real email, passwords, session ID hoặc full group list vào app logs/metrics. Internal event reasons phải được bảo vệ quyền truy cập và retention. User-facing messages chung để tránh enumeration:

```text
Không thể hoàn tất đăng nhập hoặc truy cập.
Vui lòng liên hệ bộ phận hỗ trợ qua kênh đã công bố.
Mã yêu cầu: <opaque-correlation-id>
```

Không nói “email này thuộc admin đang khóa” hay “tài khoản đã tồn tại nhưng chưa link” cho anonymous users. Với authenticated user ở flows có reauth, UI có thể cung cấp feedback phù hợp policy mà không làm lộ account ownership sang attacker.

### 20.1. Metrics hữu ích

- `federation_login_denied_total` theo **reason_code/registration**, không theo email/NameID.
- `account_link_conflict_total` theo provider/tenant, alert spike.
- `local_status_denied_total` theo service/region.
- `local_role_missing_total` theo resource group, không theo user.
- `session_revocation_lag_ms`/cache staleness percentiles.
- `unexpected_jit_creation_total` hoặc count reconciliation.

### 20.2. Alert và response

Spike `LINKING_ALREADY_BOUND` có thể là legitimate migration hoặc attempted takeover; đừng auto merge. Spike `LOCKED` sau SSO provider rollout có thể do stale status/duplicate provisioning. Phân biệt lỗi xác thực protocol trước local gate với lỗi authorization sau verified subject; không nới trust or role policy để “giảm đỏ dashboard”.

## 21. Runbook khi SSO login được ở IdP nhưng ứng dụng từ chối

1. Xác định **federation validation pass hay fail**: invalid signature/issuer/audience/nonce là một nhóm; linked local status/role là nhóm khác.
2. Lấy approved registration/issuer, **pseudonymous** subject reference, local account link key. Không copy JWT/Assertion thật vào chat/log.
3. Kiểm tra user đã có **existing link** cho issuer+subject đúng hay chỉ trùng email.
4. Kiểm tra target local account status từ authoritative store: ACTIVE/LOCKED/DISABLED, reason và audit approval.
5. Kiểm tra required role của protected route, actual granted authorities, tenant/resource scope.
6. Nếu role absent, yêu cầu owner cấp quyền theo workflow; **không tự cấp ROLE_ADMIN** hay bypass route.
7. Nếu account locked, xác minh security/HR cause; **không unlock qua login callback**.
8. Nếu link conflict, không gộp theo email; dùng secure link/recovery flow với cả local và IdP proof.
9. Nếu issue chỉ xảy ra trên một node, kiểm session caches/status drift và version mismatch.
10. Nếu user đã có session trước lock/revoke, kiểm old session vẫn truy cập được không; revoke theo policy.
11. Kiểm logs an toàn, audit events, retry/transaction races, JIT duplicates và deprovision.
12. Sau xử lý, chạy lại positive/negative tests và monitor spike; không chỉ test user đã đăng nhập được.

## 22. Checklist review trước phát hành

- [ ] IdP/OP registrations được quản trị, issuer/entityID tin cậy và đúng tenant.
- [ ] OIDC `(iss, sub)` hoặc SAML stable NameID + issuer/qualifiers dùng làm external link key.
- [ ] Không auto-link theo email, username, display name hay group.
- [ ] Account link có local session proof, recent reauth, external verified proof và state/CSRF binding.
- [ ] Chỉ link khi target local account ACTIVE; không link vào locked/disabled.
- [ ] External identity uniqueness được enforce **ở database** và tested under concurrency.
- [ ] JIT provisioning chỉ khi policy/invitation cho phép, idempotent và no bypass locked old account.
- [ ] Unlink/relink có ownership/re-auth controls, last-login factor safety và revocation.
- [ ] Local status gate nằm trên real SAML/OIDC login path, trước final Authentication/session.
- [ ] Không giả định `UserDetailsService` tự chạy với SAML/OIDC.
- [ ] Missing local role không bị auto-grant; protected routes deny 403 hoặc strict login reject.
- [ ] Role mapping chỉ dùng trusted claims/local policies, có tenant/resource scope.
- [ ] Active-session revocation sau LOCKED/role revoke được kiểm tra trên multi-node.
- [ ] MockMvc `oidcLogin()` chỉ dùng cho route/mapping tests; full callback có integration tests riêng.
- [ ] SAML fixtures được ký hợp lệ sau khi thay NameID/attributes cho link tests.
- [ ] Cross-issuer same sub, cross-sub same email, transient SAML NameID đều có negative tests.
- [ ] Cross-session state/nonce, expired link intent, replay callbacks bị từ chối.
- [ ] No raw token, Assertion, NameID, email hoặc PII trong error/log/metrics.
- [ ] User-facing errors không tiết lộ account existence/locked state.
- [ ] Lock/unlock/role changes được audit, không tự thực hiện bởi SSO callback.
- [ ] Session fixation, CSRF, login flow isolation, deprovisioning và recovery policy có test.
- [ ] Code dùng API Spring Security đúng version, không tự bỏ token/signature validators.
- [ ] Positive control chứng minh linked ACTIVE+role cho phép truy cập thật.
- [ ] Negative controls chứng minh missing link, missing role, locked/disabled đều fail closed.

## 23. Câu hỏi ôn tập

**1. Vì sao signed ID Token không đủ để truy cập local account?**  
Vì token chỉ xác thực external subject; RP còn phải map đúng local ID, kiểm local status/role và resource policy.

**2. Có nên auto-link khi email claim trùng email trong DB?**  
Không. Email có thể đổi/tái sử dụng/alias và không chứng minh quyền sở hữu local account. Dùng verified issuer+subject và explicit secure linking.

**3. `sub` giống nhau từ hai OIDC issuers có tự cùng người không?**  
Không. Link key phải include trusted issuer, và tenant/sector khi kiến trúc cần.

**4. SAML NameID transient có làm persistent account key tốt không?**  
Không nếu IdP thay giá trị mỗi lần. Cần stable identity contract hoặc verified account-link flow.

**5. Một user chỉ có `SCOPE_openid` có tự là REPORT_VIEWER không?**  
Không. OIDC scope không phải local app role.

**6. Missing role có bắt buộc fail login không?**  
Tùy policy: strict app có thể fail login; app có onboarding có thể giữ minimal session nhưng protected resource phải deny.

**7. Đã tạo `UserDetailsService` thì SAML2/OIDC login có tự kiểm `isAccountNonLocked`?**  
Không. DaoAuthenticationProvider password flow dùng UserDetails; federation phải integrate local status gate.

**8. Tại sao account locked ở RP mà IdP vẫn phát token?**  
Vì IdP và RP quản lý trạng thái khác nhau. RP phải tự reject hoặc revoke session theo policy.

**9. Khi user bị lock sau login, chỉ chặn callback tiếp theo đã đủ chưa?**  
Không. Old authenticated sessions/tokens có thể còn quyền; cần revocation/status gate và test old cookies.

**10. Tại sao `oidcLogin()` MockMvc chưa chứng minh SSO callback an toàn?**  
Nó inject mock principal/authorities và không tự chạy real authorization-code exchange, token signature và link service.

**11. Làm sao test SAML NameID mismatch mà không nhận nhầm lỗi chữ ký?**  
Tạo signed fixture mới bằng test IdP key sau khi set NameID, giữ other protocol checks valid.

**12. Vì sao unique external link phải ở database?**  
Hai requests đồng thời có thể vượt `exists()` check. DB constraint/transaction bảo đảm không link X tới hai accounts.

**13. Có thể cấp local ADMIN ngay khi SAML Attribute says “admin”?**  
Không tự động. Chỉ khi RP có allowlisted mapping/trusted issuer/tenant/entitlement contract và policy cấp quyền.

**14. Local account unlock có nên xảy ra sau một SSO login thành công?**  
Không. Unlock phải theo workflow đã phê duyệt, không vì IdP token còn valid.

**15. User đã unlink external identity rồi login lại bằng identity đó?**  
Không được vào local account cũ nếu chưa thực hiện linking lại theo policy.

**16. Account A bị khóa, user thử đăng nhập IdP B đã link A, kết quả?**  
Vẫn reject. Lock áp trên local account bất kể login method.

**17. Nếu local roles service đang mất kết nối thì sao?**  
Không fail open thành admin. Tùy risk policy, deny protected operation hoặc dùng cache bounded đã duyệt với revocation safeguards.

**18. Response lỗi “Account a@example.org locked” có nguy cơ gì?**  
Tiết lộ tài khoản tồn tại/status, giúp enumeration. Dùng generic message bên ngoài và reason code audit nội bộ.

**19. JIT có phải luôn tạo account khi subject chưa linked?**  
Không. JIT chỉ theo approved issuer/tenant/invite/entitlement policy; unlinked có thể phải reject.

**20. Điều gì chứng minh user có local role nhưng không vượt lock?**  
Negative integration test với linked account LOCKED và role `REPORT_ADMIN` vẫn bị từ chối cả login mới và protected requests.

## 24. Tài liệu chính thức và tham khảo

- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): issuer, subject, pairwise identifiers, ID Token validation, nonce/state semantics.
- [NIST SP 800-63C-4 — Federation and Assertions](https://pages.nist.gov/800-63-4/sp800-63c.html): secure account linking, RP/IdP trust agreements và federation security.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): generic failures, account enumeration, secure federated linking và reauthentication.
- [OWASP OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): OAuth state/PKCE, login CSRF và token handling.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session fixation, invalidation, logout và revocation.
- [Spring Security — OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): `OidcUserService` delegation, authority mapping và userInfo endpoint configuration.
- [Spring Security — Testing OAuth2/OIDC Login](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): `oidcLogin()`, `oauth2Login()` và test authorities/claims.
- [Spring Security — SAML2 Authentication](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): `Saml2AuthenticatedPrincipal`, validated assertions và provider customization.
- [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): trusted RelyingPartyRegistration, SAML Response/Assertion checks và ACS flow.
- [Spring Security — UserDetailsService](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details-service.html): role of `UserDetailsService` in `DaoAuthenticationProvider`.
- [Spring Security — UserDetails API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/core/userdetails/UserDetails.html): `isEnabled`, `isAccountNonLocked`, `isAccountNonExpired` và authorities.
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): SecurityContext, Authentication, authorities, session establishment.
- [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): Subject/NameID, Assertion signature/trust và SAML identity semantics.
- [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): secure SAML response validation, trust and replay protection.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): avoiding sensitive authentication data in logs.

**Ghi nhớ:** SAML/OIDC SSO xác thực **external subject**, không chứng minh external subject có quyền sở hữu một **local account** chỉ vì email trùng. Liên kết an toàn cần immutable issuer+subject/NameID-context, local reauthentication, verified external proof, state/CSRF binding và DB uniqueness. Quyền báo cáo/admin là **local authorization**, thiếu role không được auto-grant. Account đã LOCKED/DISABLED phải bị deny ngay cả khi SSO token hợp lệ, và khi lock xảy ra **sau khi login**, cần xử lý sessions/tokens cũ. Để kiểm chứng, kết hợp unit policy tests, DB concurrency, MockMvc route tests **và** full SAML/OIDC callback với local state thật; không để mocked `oidcLogin()` đánh lừa rằng toàn bộ federation đã được kiểm thử.