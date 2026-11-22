# Liên kết nhiều danh tính bên ngoài với một tài khoản ứng dụng

**Học phần:** Spring Security – federation → Thư mục và tài khoản.

**Mục tiêu:** xây dựng mô hình **một tài khoản ứng dụng có thể đăng nhập bằng nhiều danh tính bên ngoài** (Google/Entra ID/Keycloak hoặc IdP OIDC khác, SAML2 IdP, CAS/directory doanh nghiệp) mà không tạo tài khoản trùng, không chiếm quyền qua email trùng, không nhầm issuer/tenant, và có thể liên kết, tháo liên kết, chuyển nhà cung cấp danh tính và thu hồi quyền một cách an toàn. Nội dung tập trung vào **khóa định danh đáng tin cậy, quy trình account linking, thiết kế database, Spring Security, giao dịch đồng thời, session/CSRF và kiểm thử**.

**Kết luận trước khi bắt đầu:** **Không tự gộp hai danh tính vì chúng có cùng email hoặc username.** Với OIDC, định danh liên kết bền vững phải dựa trên cặp **`(issuer, subject) = (iss, sub)` sau khi ID Token đã được kiểm chứng**. Một người có thể có hai cặp `(iss,sub)` khác nhau; chỉ nối chúng với **cùng internal account ID** sau quy trình chứng minh quyền kiểm soát tài khoản ứng dụng hiện có **và** danh tính bên ngoài muốn thêm. Email là thuộc tính hồ sơ; `email_verified=true` **không** phải bằng chứng rằng hai IdP mô tả cùng một con người.

Bài hướng tới Java 17+ và Spring Security Servlet/OIDC login. Các đường dẫn và tên IdP `example.com` đều mang tính minh họa. Mã Spring là mảnh cấu hình; Java 17 thuần ở phần thực hành có thể chạy độc lập.

## 1. Bài toán thực tế: một tài khoản, nhiều cách đăng nhập

Một nền tảng nội bộ có hồ sơ nhân viên và dữ liệu công việc:

- **Ứng dụng:** `https://work.example.com`.
- **Tài khoản ứng dụng:** `user_id=U-100`, profile, preferences, lịch sử tài liệu, memberships và permissions nằm trong cơ sở dữ liệu ứng dụng.
- **IdP A:** OIDC issuer `https://login.corp.example/oidc`, `sub=emp-194` (đăng nhập nhân viên).
- **IdP B:** OIDC issuer `https://login.partner.example/oidc`, `sub=account-903` (đăng nhập đối tác).
- **IdP C:** SAML2 issuer `https://sso.legacy.example/idp` với persistent NameID được phê duyệt.

Một cá nhân được phép điều khiển U-100 và muốn đăng nhập bằng A hoặc B. Ứng dụng nên vẫn thấy **một U-100**, giữ nguyên business records, thay vì tạo `U-101` rồi mất lịch sử.

```text
              +--------------------------------+
              | Application account U-100      |
              | name, settings, document ACLs  |
              | tenant memberships, lifecycle  |
              +----------------+---------------+
                               |
                +--------------+----------------+
                |              |                |
                v              v                v
       External link A   External link B   External link C
       OIDC iss+sub      OIDC iss+sub      SAML issuer+NameID
                |              |                |
                v              v                v
          Corporate IdP   Partner IdP       Legacy IdP
```

**Phân tách thực thể:**
1. **Application account (`app_user_id`):** do ứng dụng sở hữu, ổn định khi đổi IdP, là chủ của hồ sơ và dữ liệu.
2. **External identity (`issuer + subject`):** do IdP cấp; là một *cách chứng minh đăng nhập*, không tự là business account.
3. **Authentication event/session:** IdP vừa xác thực user qua OIDC/SAML/CAS; có ngữ cảnh assurance, timestamp và session riêng.
4. **Authorization/membership:** quyền đối với tenant, phòng ban, report hay dữ liệu; cần authority độc lập, không suy từ việc đăng nhập thành công.

**Liên kết tài khoản không giống merge dữ liệu:** linking cho phép nhiều credentials/IdPs vào **cùng một app account**; còn *merge* U-100/U-101 là nghiệp vụ chuyển ownership, hóa đơn, quyền và audit riêng, rủi ro cao hơn. Không thực hiện data merge ngầm khi login hoặc khi email trùng.

## 2. Định danh bên ngoài phải có namespace

### 2.1. OIDC: `iss` và `sub` là cặp định danh

OpenID Connect Core `5.7` nêu `iss` và `sub` kết hợp là định danh có thể dựa vào để phân biệt end-user. Ví dụ:

| Issuer đã xác minh | Subject | Email hiển thị | Kết luận |
| --- | --- | --- | --- |
| `https://idp-a.example/oidc` | `42` | `an@example.com` | Danh tính A |
| `https://idp-b.example/oidc` | `42` | `an@example.com` | **Danh tính B khác A** |
| `https://idp-a.example/oidc` | `43` | `an@example.com` | **Danh tính A khác**, dù email trùng |
| `https://idp-a.example/oidc` | `42` | `an-new@example.com` | **Cùng danh tính A** nếu `iss+sub` không đổi |

OIDC `sub` ổn định **trong namespace của issuer**, không tự duy nhất trên toàn Internet. `sub` và issuer URL phải đối chiếu đúng chữ hoa/thường và ý nghĩa do provider định nghĩa; không tự lowercase giá trị `sub` hoặc sửa issuer path. Một issuer có thể phát **pairwise `sub`** khác nhau theo từng sector/client: cùng user đăng nhập vào hai RP có thể nhận hai subject khác nhau. Nếu đổi client registration/sector, **đừng dựa email để nối tự động**; dùng migration/account-linking được duyệt.

```json
{
  "iss": "https://idp-a.example/oidc",
  "sub": "employee-194",
  "aud": "work-app-client",
  "exp": 2000000000,
  "iat": 1999999700,
  "email": "an@example.com",
  "email_verified": true
}
```

Đây là **payload ID Token minh họa**, không phải JWT được ký. Ứng dụng chỉ lấy `iss/sub` **sau** khi Spring Security/OIDC client đã xác minh token cho đúng issuer/client ID, chữ ký, nonce/state/timestamp. `email_verified=true` là phát biểu của **issuer đó** về email, không là một khẳng định cross-provider identity equivalence.

### 2.2. `registrationId` của Spring không thay cho issuer

Spring Security phân biệt:
- `registrationId`: khóa cấu hình cục bộ như `corp` hoặc `partner`.
- `issuer-uri`: nguồn phát OIDC token thật, dùng discovery/signature và validation.
- `OidcIdToken.getIssuer()` / `OidcIdToken.getSubject()`: dữ liệu identity **sau verification**.

Nếu rename `registrationId` từ `corp` thành `enterprise`, không nên thay đổi identity key bền vững. Ngược lại, hai registrations trỏ tới **cùng issuer** có thể nhận pairwise `sub` khác nhau; đừng tự giả sử chúng cùng account vì tên provider giống nhau.

### 2.3. SAML2, CAS, LDAP và Kerberos không có cùng kiểu khóa

| Giao thức/nguồn | Định danh ngoài nên cân nhắc | Cảnh báo |
| --- | --- | --- |
| **OIDC** | `(trusted iss, sub)` | Phải verify JWT và subject; pairwise `sub` có thể khác theo client/sector |
| **SAML2** | `(trusted IdP entityID/Issuer, persistent NameID, NameID Format/qualifiers/SP scope khi cần)` | Transient NameID thường **không dùng làm khóa lâu dài** |
| **CAS** | `(trusted CAS server/service namespace, principal stable ID)` | CAS `cas:user` có thể là username bị đổi/tái sử dụng, cần contract hoặc mapping directory ID |
| **LDAP/AD** | `(directory authority, immutable entry identity như objectGUID/entryUUID)` | DN, email, `sAMAccountName` có thể đổi/reuse; AD objectSID có lifecycle riêng |
| **Kerberos** | `(trusted realm/principal và mapping directory ID)` | Kerberos principal name có thể đổi/reassign theo policy; không tự là app ID bất biến |
| **SCIM** | SCIM resource `id` trong authority cung cấp, hoặc `externalId` theo contract có namespace | `externalId` thường do client cấp, **không tự là global user ID đáng tin** |

**Mọi identity key phải có authority namespace rõ ràng.** Với LDAP nhiều forests, dùng `objectGUID` **kèm directory ID**, không dùng GUID/DN/email tách rời. Với SAML, kết hợp `NameQualifier`/`SPNameQualifier`, Format và assertion context theo policy; chỉ sử dụng NameID stable nếu IdP cam kết và SP verify message đúng.

Đặc biệt, **một IdP bị xâm nhập không nên có quyền tự gán user của tenant khác** chỉ bằng tên/email/claim. Broker/application phải quản lý trusted provider registrations, tenant onboarding, mapping và authorization riêng.

## 3. Identity linking khác identity lookup, provisioning và account merge

| Thao tác | Mục tiêu | Điều kiện quan trọng |
| --- | --- | --- |
| **Login bằng external identity đã link** | Tìm U-100 từ khóa ngoài, tạo phiên | External authentication verified, link đang active, account/tenant được phép |
| **Link identity B vào U-100** | Bổ sung cách đăng nhập thứ hai | Đang có phiên U-100 mạnh + xác thực B mới + linking intent ràng buộc phiên |
| **Unlink identity B** | Gỡ khả năng B đăng nhập U-100 | Reauthentication, CSRF, không tự khóa tài khoản không có recovery |
| **Just-In-Time (JIT) create** | Tạo app account mới sau first login | Provisioning/tenant policy cho phép, không tự gộp tài khoản cũ vì email |
| **SCIM/pre-provision** | Tạo/cập nhật user/attrs từ authority quản lý | Contract và uniqueness, không bypass proof-of-possession cho tài khoản khác |
| **Data account merge** | Hợp nhất U-100/U-101 và lịch sử | Quy trình nghiệp vụ riêng, consent/admin review, không diễn ra tự động trong OAuth callback |
| **Rebinding/migration IdP** | Thay external identity cũ bằng mới | Proof/migration mapping, trạng thái phiên, audit, rollback, không chỉ matching email |

Điều nhiều sản phẩm gọi là “sign in with Google/Microsoft” là **federated authentication**; nó **chưa tự chứng minh cùng người** với account ứng dụng đang tồn tại. Linking là một hành động account management nhạy cảm, giống thêm authenticator mới. NIST SP 800-63C-4 mục `3.8.1` yêu cầu linking functions dựa trên phiên xác thực của app account và có thông báo khi identifier liên kết được thêm/gỡ.

## 4. Luồng đăng nhập bình thường bằng danh tính đã liên kết

Giả sử DB đã có:
- External `(issuer A, sub emp-194) → U-100`.
- External `(issuer B, sub account-903) → U-100`.

```mermaid
sequenceDiagram
    actor User as Người dùng
    participant App as Spring App / RP
    participant IdP as OIDC IdP B
    participant Links as Identity Link Store
    User->>App: GET /private
    App-->>User: Redirect /oauth2/authorization/partner
    User->>IdP: Authorization Code + PKCE / login
    IdP-->>User: Authorization code trở về app callback
    User->>App: code + state
    App->>IdP: Redeem code tại token endpoint B
    IdP-->>App: ID Token đã ký
    App->>App: Verify iss/aud/signature/nonce/exp/state
    App->>Links: Lookup (trusted issuer B, sub account-903)
    Links-->>App: app_user_id U-100
    App->>App: Kiểm ACTIVE/memberships, tạo app session U-100
    App-->>User: Cho truy cập resource theo quyền
```

**Quyết định tài khoản ứng dụng chỉ diễn ra sau xác minh external login.** Nếu IdP B trả username/email trùng nhưng `sub` khác, không dùng `findByEmail` rồi đăng nhập U-100. Nếu chưa có mapping, chuyển sang first-login/onboarding hoặc một flow “Liên kết danh tính” được khởi tạo an toàn, không chấp nhận ngầm.

### 4.1. Identity key nên lưu gì?

Một bản ghi link tối thiểu có:
- `app_user_id` – UUID/nội bộ, khóa ngoại đến account.
- `protocol` và `issuer_or_authority` – OIDC issuer URI, SAML entityID, directory authority.
- `subject_type`/`subject_value` – OIDC `sub` hoặc stable principal/NameID phù hợp.
- `scope/qualifiers` – chỉ khi giao thức cần phân biệt namespace.
- `state` – ACTIVE/REVOKED/PENDING theo lifecycle.
- `created_at`, `last_verified_at`, `linked_by`, `linked_via`, audit reference.
- Optional `provider_registration_id` để vận hành, **không dùng một mình như identity key**.
- Email/display name như **metadata** ở bảng profile tách biệt; không vào unique constraint identity.

**Không cần lưu raw ID Token lâu dài** để nhận diện user nếu đã có issuer/subject; token có thể chứa PII và hết hạn. Chỉ lưu tối thiểu các claims/identifier theo privacy policy, audit phải che token và bí mật.

## 5. Quy trình liên kết B vào U-100 phải chứng minh hai phía

### 5.1. Hai bằng chứng cần thiết

1. **Quyền kiểm soát U-100:** user đang có app session authenticated với U-100; thao tác linking nhạy cảm có thể yêu cầu **reauthentication/MFA/step-up** theo policy. Một browser cookie cũ hoặc email trùng **không đủ** cho liên kết rủi ro cao.
2. **Quyền kiểm soát external B:** app chủ động bắt đầu OIDC/SAML authentication mới với B; nhận và verify assertion/token mới, state/nonce/PKCE/request correlation. Không cho user tự nhập `sub` hay `email` để “gắn” B.

Khi cả hai bằng chứng đạt, app mới ghi `(B issuer, B sub) → U-100` trong transaction, với uniqueness và kiểm tra external B chưa gắn account khác.

### 5.2. Luồng linking bằng OIDC

```mermaid
sequenceDiagram
    actor User as Người dùng
    participant App as Spring App
    participant Pending as Server-side LinkIntent
    participant IdP as IdP B
    participant DB as Link DB
    User->>App: POST /settings/identities/link/partner (CSRF)
    App->>App: Verify current U-100, fresh auth/MFA
    App->>Pending: Create nonce + one-time intent for U-100/session/provider B
    App-->>User: Redirect tới OIDC /authorize của B
    User->>IdP: Xác thực bằng danh tính B
    IdP-->>User: Redirect code + state về callback
    User->>App: code + state cho link attempt
    App->>App: Verify state/PKCE/nonce/issuer/audience/signature/exp
    App->>Pending: Consume one-time intent, verify session U-100
    App->>DB: Transaction: check (issuer B, sub B) uniqueness
    DB-->>App: Không linked elsewhere; commit B -> U-100
    App->>App: Audit, notify user, rotate/revalidate session if policy
    App-->>User: Liên kết B thành công
```

**Một `OAuth2LoginAuthenticationFilter` mặc định có thể tạo hoặc thay `Authentication` khi callback trở về.** Nếu dùng nó cho account linking, không được **vô tình đổi principal từ U-100 sang B** trước khi xác định user U-100 ban đầu. Hãy dùng **separate link transaction/handler** hoặc broker account-linking API có tính ràng buộc phiên. Lưu `target_app_user_id` trong server-side intent trước redirect, xác minh đúng **original authenticated session**, và chỉ link sau khi đã có validated OIDC principal từ B.

### 5.3. LinkIntent server-side nên chứa gì?

| Field | Ý nghĩa |
| --- | --- |
| `intent_id` ngẫu nhiên, khó đoán | Mã workflow riêng, dùng một lần |
| `original_app_user_id` | U-100 của phiên app trước khi bắt đầu |
| `original_session_binding` | Hash/correlation của session hiện tại; không nhét raw session ID vào URL |
| `expected_provider_registration/issuer` | Chỉ B được phép hoàn tất intent này |
| `state`/`nonce`/PKCE transaction reference | Ràng buộc callback với authorization request |
| `created_at/expires_at` | TTL ngắn, cleanup |
| `csrf/re_auth_evidence` | Bằng chứng request được user hiện tại khởi tạo và thỏa freshness |
| `status` | PENDING → CONSUMED/EXPIRED/CANCELLED, xử lý atomic |
| `initiating_ip/device context` | Tín hiệu risk-based, không là identity key duy nhất |

Không để browser chọn `app_user_id` đích qua query như `?linkTo=U-100`. Nếu cần lưu URL đích sau linking, chỉ dùng safe local path/allowlist, tránh open redirect. IdP B/issuer phải được preconfigured allowlist; browser không được tùy ý cung cấp `issuer-uri`/`jwks_uri`/`token_endpoint`.

### 5.4. Chống login CSRF, code injection và mix-up

- `state` phải ngẫu nhiên, ràng buộc browser/session và **một lần xử lý**; callback thiếu/sai state → reject.
- Dùng **Authorization Code + PKCE**; exact redirect URIs, HTTPS.
- OIDC `nonce` khi áp dụng phải khớp request, cùng token signature/issuer/audience/exp.
- Khi app là OAuth client của **nhiều authorization servers**, ràng buộc expected issuer với request. RFC 9700 mô tả **authorization server mix-up**; RFC 9207 issuer identification ở authorization response hỗ trợ phòng vệ khi provider hỗ trợ.
- Không redeem code ở token endpoint do callback/query gợi ý; dùng **registration/issuer đã lưu** khi bắt đầu giao dịch.
- Không tự động xử lý **IdP-initiated / unsolicited SAML assertion** như thao tác linking vì thiếu sự khởi tạo/binding với app user đang xác thực; nếu business buộc hỗ trợ, phải có một protocol-specific secure proof flow.
- Chặn session swapping: một người bắt đầu link khi đang U-100 nhưng callback về lúc browser chuyển sang U-999 → reject, không gắn B cho tài khoản sai.

## 6. Điều gì không đủ làm bằng chứng linking?

| Tín hiệu | Có giá trị gì? | Có đủ link không? |
| --- | --- | --- |
| `email` giống nhau | Gợi ý UI/onboarding hoặc liên hệ | **Không** |
| `email_verified=true` ở cả A và B | Mỗi IdP tuyên bố kiểm email theo policy riêng | **Không** |
| `preferred_username` giống | Display/login hint | **Không** |
| Cùng số điện thoại | Profile; có thể đổi/tái cấp | **Không** |
| `sub` giống nhưng issuer khác | String trùng ở hai namespace | **Không** |
| Cùng tên/ảnh đại diện | Tín hiệu UI | **Không** |
| Có session app U-100 | Chứng minh current app account | **Chưa đủ** nếu chưa authenticate B |
| Có B ID Token hợp lệ | Chứng minh external B | **Chưa đủ** nếu chưa có quyền gắn vào U-100 |
| Fresh app U-100 session + fresh B login + bound one-time intent | Đủ bằng chứng để **xét link**, nếu policy cho phép | **Có, sau collision/authorization checks** |
| Admin import CSV email mappings | Hỗ trợ migration review | Không tự động; cần authority/proof/audit cụ thể |

**Tình huống account takeover:** Alice có U-100, từng dùng `alice@company.example`; email đó được cấp lại cho Bob ở IdP B. Nếu app auto-link khi `email_verified=true`, Bob có thể đăng nhập U-100 của Alice và truy cập dữ liệu cũ. **Email ownership hiện tại không chứng minh ownership lịch sử của tài khoản ứng dụng.**

Các IdP khác nhau có thể dùng policies xác minh email không tương đương. Không đặt cấu hình “Trust Email”/automatic email linking ở broker mà chưa có threat model; Keycloak First Broker Login hỗ trợ nhiều chiến lược linking, cần chọn reauthentication/verification phù hợp.

## 7. Thiết kế database 1:N và unique key

### 7.1. Schema PostgreSQL gợi ý

```sql
CREATE TABLE app_accounts (
    id UUID PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'DISABLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE external_identity_links (
    id UUID PRIMARY KEY,
    app_account_id UUID NOT NULL
        REFERENCES app_accounts(id) ON DELETE CASCADE,
    protocol TEXT NOT NULL,
    issuer_or_authority TEXT NOT NULL,
    subject_kind TEXT NOT NULL,
    subject_value TEXT NOT NULL,
    name_qualifier TEXT NOT NULL DEFAULT '',
    sp_name_qualifier TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'REVOKED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_verified_at TIMESTAMPTZ,
    UNIQUE (protocol, issuer_or_authority,
            subject_kind, subject_value,
            name_qualifier, sp_name_qualifier)
);

CREATE INDEX idx_links_by_account
    ON external_identity_links(app_account_id);

CREATE TABLE account_tenant_memberships (
    app_account_id UUID NOT NULL
        REFERENCES app_accounts(id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL,
    role TEXT NOT NULL,
    PRIMARY KEY (app_account_id, tenant_id, role)
);

CREATE TABLE identity_link_events (
    id UUID PRIMARY KEY,
    app_account_id UUID NOT NULL REFERENCES app_accounts(id),
    action TEXT NOT NULL,
    identity_link_id UUID,
    event_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor_account_id UUID,
    correlation_id TEXT NOT NULL
);
```

Đây là **lược đồ minh họa cho thiết kế**, không phải migration đầy đủ. Cần quyết định retention/soft delete/status history, mã hóa PII, index, audit immutability, customer tenant model, uniqueness dành cho linked/retired identities và GDPR/luật dữ liệu tương ứng. Khi revoke identity, unique constraint trên bảng giữ lịch sử sẽ **ngăn tái sử dụng khóa** đến khi có workflow reactivation/relink có kiểm soát; không tự xóa record để vượt uniqueness. Có thể tách bảng link hiện tại và lịch sử nếu lifecycle phức tạp.

**Quy tắc uniqueness mạnh:** một `(issuer,subject)` đã xác minh không được gắn đồng thời cho **hai app accounts** trong cùng namespace trust. Nếu hệ thống có tenant isolation đặc biệt, phải định nghĩa rõ scoped identity semantics, chứ không thêm `tenant_id` tùy tiện vào unique key để cho cùng external credential chiếm nhiều accounts theo tenant mà không kiểm soát.

### 7.2. Phân biệt identity table và business table

```text
app_accounts.id = U-100
  |-- document_owners.owner_account_id = U-100
  |-- preferences.account_id = U-100
  |-- memberships.account_id = U-100
  |-- external_identity_links:
          (OIDC, issuer A, sub 194)
          (OIDC, issuer B, sub 903)
          (SAML, issuer C, persistent NameID X)
```

**Không dùng `external_sub` làm khóa chính của hồ sơ/hóa đơn/tài liệu**; khi IdP đổi hoặc được unlink, business ownership phải còn thuộc U-100. Ưu tiên internal UUID bất biến, tránh buộc người dùng mất dữ liệu khi thay nhà cung cấp danh tính.

### 7.3. Normalization và sự nhầm lẫn thường gặp

- **`issuer`:** lưu canonical issuer từ **trusted configuration** và match token `iss` chính xác. Không xóa path, bỏ `https`, đổi `www`, hay tự redirect discovery vì trông “tương đương”.
- **OIDC `sub`:** là string case-sensitive; không lowercase/trim/convert sang số.
- **SAML NameID:** cùng text có thể khác theo `Format`/NameQualifier/SPNameQualifier và Issuer. Chỉ dùng persistent identity theo contract; không biến transient ID thành permanent key.
- **Directory `DN`:** có thể đổi khi move/rename; muốn stable external ID phải dùng authority-specific immutable ID và quản lý deletion/recreation.
- **`email`:** không đặt unique identity-link chỉ vì người dùng muốn login email; profile email unique là bài toán khác.
- **`client_id`:** không thay thế issuer. Với pairwise OIDC `sub`, client/sector context có thể ảnh hưởng định danh; hãy quản lý migration khi đổi registration.
- **`app_account_id`:** dùng UUID do ứng dụng phát; không gửi từ callback như input chưa kiểm chứng.

## 8. Ghi link trong transaction: tránh race và double attach

Khi hai tabs/requests cùng cố link external B:
1. Bắt đầu transaction, xác minh app account U-100 đang ACTIVE.
2. Confirm linking intent **chưa consume** và current app session/reauth evidence vẫn hợp lệ.
3. Đọc hoặc INSERT identity key duy nhất, dùng **database UNIQUE constraint** chống cross-node race.
4. Nếu identity key đã gắn U-100, trả trạng thái **already linked** không tăng quyền; tùy policy có thể coi idempotent.
5. Nếu đã gắn U-999, **không chuyển sang U-100** chỉ vì email hoặc user request. Báo lỗi chung, mở recovery/admin review.
6. Nếu chưa gắn, INSERT `external_identity_links(B→U-100)`.
7. Mark linking intent `CONSUMED` atomically, commit.
8. Audit/notify qua transactional outbox hoặc cơ chế đảm bảo, **không publish “link succeeded” trước commit**.

Pseudo-SQL ý tưởng (không phải migration/transaction đầy đủ):

```sql
BEGIN;
-- Khóa tài khoản app hiện tại để tuần tự hóa thay đổi nhạy cảm.
SELECT id, status
FROM app_accounts
WHERE id = :current_account_id
FOR UPDATE;

-- Client code đã xác minh LinkIntent, IdP token và namespace.
INSERT INTO external_identity_links (
    id, app_account_id, protocol,
    issuer_or_authority, subject_kind, subject_value)
VALUES (
    :link_id, :current_account_id, 'OIDC',
    :trusted_issuer, 'sub', :verified_sub);

-- UNIQUE constraint ngăn link này bị gắn vào một account khác.
-- Conflict phải được xử lý có chủ đích; không "DO UPDATE app_account_id".
COMMIT;
```

**Không được dùng `INSERT ... ON CONFLICT DO UPDATE SET app_account_id = :current_account_id`**: nó có thể âm thầm **chuyển một external identity từ U-999 sang U-100**, tạo đường chiếm tài khoản. Nếu dùng `ON CONFLICT DO NOTHING`, phải đọc lại owner sau conflict và phân biệt “đã link U-100” với “đã link U-999”.

**TOCTOU:** application-level `if (!exists) insert` không đủ vì hai node có thể cùng thấy “not exists”. Uniqueness ở DB mới là bảo vệ cross-instance. Lệnh insert và consume intent phải trong cùng transaction (hoặc có fencing/idempotency đầy đủ khi store phân tán).

## 9. Unlink và bảo vệ không khóa người dùng

Gỡ `(issuer B,sub B)` khỏi U-100 là một thao tác bảo mật. Khi hoàn thành:
- Login mới bằng B **không còn** được map về U-100.
- Không gỡ identity mà request không sở hữu (`WHERE app_account_id = currentUserId`).
- Cần app session authenticated, fresh reauthentication/step-up, CSRF và confirmation cho hành động nhạy cảm.
- Khi unlink identity cuối cùng mà account không có mật khẩu/passkey/khác IdP/recovery, **phải có policy tránh lockout**: block unlink hoặc xác minh đường recovery trước.
- Gửi notification qua một channel đã được xác minh; kiểm tra events khi unlink không do user chủ động.
- Rà soát **active sessions, refresh tokens, long-lived authorizations** đã phát từ identity bị gỡ: unlink không tự hủy mọi session hiện hữu. Policy có thể yêu cầu revoke các session có provenance từ B hoặc tất cả sessions của U-100.
- Việc xóa liên kết không tự xóa business account/data; account deletion là lifecycle riêng.

NIST SP 800-63C-4 quy định RP nên có chính sách khi account không còn phương thức truy cập/recovery; một account không còn federated identifiers phải được xử lý theo documented account lifecycle, không để tồn tại quyền truy cập không rõ ràng.

### 9.1. “Không thể unlink vì đó là đăng nhập duy nhất” có luôn đúng?

Không hoàn toàn: một tài khoản còn **passkey/local authenticator/recovery method** đủ mạnh vẫn có đường truy cập, có thể unlink identity cuối. Hệ thống phải dựa vào **actual active and trusted sign-in methods**, không chỉ đếm số row identity links. Ngược lại, có hai external identities nhưng cả hai thuộc một IdP bị ngừng hoạt động cũng không bảo đảm recovery.

## 10. JIT provisioning và kiểm soát tài khoản trùng

Khi một external identity mới đăng nhập và chưa tìm thấy link:
- **JIT create**: chỉ tạo **app account mới** khi tenant/service policy cho phép và user có invitation/provisioning proof cần thiết.
- **Existing-account link**: nếu user đã có app account và muốn dùng IdP mới, phải bắt đầu **link workflow từ authenticated account** hoặc cơ chế broker được kiểm chứng.
- **Account resolution**: ở một số hệ thống enterprise, directory/SCIM mapping có authority đủ mạnh để giải quyết user; cần hợp đồng trust và migration chứng minh, không gọi việc match email là authoritative resolution.
- **Deny**: nếu user chưa được onboarded hoặc IdP không được allowed, trả lỗi hỗ trợ không lộ dữ liệu “email nào đã có account”.

**Đừng tạo hai app accounts U-100/U-101 rồi tự “merge” chỉ vì cùng email.** Nếu đã phát sinh duplicate, xử lý bằng quy trình account reconciliation/merge được phê duyệt, có transaction cho dữ liệu business, kiểm tra authorization và rollback.

### 10.1. Phân biệt confirmation bằng email và chứng minh external identity

Một email confirmation link có thể chứng minh người dùng **đang nhận thư tại địa chỉ** theo policy của mail system. Nó không chứng minh họ sở hữu **tài khoản ứng dụng hiện hữu** hoặc email chưa bị reassigned. Để thêm IdP B vào U-100 cần chứng minh cả U-100 và B; nếu mất quyền với U-100, dùng **account recovery** tách biệt có bằng chứng mạnh hơn, không dùng shortcut “tôi biết email cũ”.

## 11. Liên kết trong hệ thống multi-tenant

Một người có thể là nhân viên A đồng thời đối tác B. Cả hai external identities đều hợp lệ để login U-100, nhưng **quyền trên mỗi tenant không tự hợp nhất**.

```text
App user U-100
  external links:
    OIDC corporate A (iss A, sub 194)
    OIDC partner B   (iss B, sub 903)
  memberships:
    tenant CORP    role READER
    tenant PARTNER role EDITOR
  enforcement:
    GET /corp/report  -> check CORP membership + resource
    GET /partner/doc  -> check PARTNER membership + resource
```

Các điều kiện:
1. Linking một B identity không tự tạo `tenant=PARTNER, role=ADMIN`.
2. External `groups` hay `roles` chỉ được mapping qua allowlist theo **issuer + tenant**, không nhận “admin” toàn hệ thống.
3. Một ứng dụng có thể yêu cầu **step-up** bằng IdP corporate A cho thao tác quản trị, dù user đang có phiên app U-100 được tạo từ B.
4. Phân biệt **identity of person** với **authority of organization**: chỉ vì cùng người không có nghĩa các tổ chức ủy quyền lẫn nhau.
5. Nếu IdP B bị deprovisioned, kiểm tra session và quyền gắn với provenance B; đừng giữ quyền nhạy cảm chỉ vì A vẫn đang linked.

**Thiết kế thêm trường `authenticated_via_link_id`/`auth_time` trong app session hoặc audit context** khi cần quyết định chính sách theo nguồn xác thực. Thông tin này không thay app_user_id, nhưng giúp đánh giá assurance/step-up và phản ứng deprovision.

## 12. SAML2, CAS và thư mục: trường hợp thực tế đặc biệt

### 12.1. SAML NameID và qualifiers

Một SAML assertion có thể phát:
- Transient NameID cho privacy; không nên làm identity link lâu dài.
- Persistent NameID được phát theo một định danh ổn định giữa IdP/SP, phù hợp identity linking nếu trust contract cho phép.
- Email Address NameID (không nhất thiết ổn định/duy nhất khi email thay đổi).

Ứng dụng phải kiểm tra SAML XML Signature của **đúng Response/Assertion**, trusted IdP entityID, `AudienceRestriction`, `Recipient/Destination`, `InResponseTo`, time conditions và replay. Chỉ khi assertion đã verify mới trích NameID/qualifiers để lookup link. Một SAML Response dành cho SP A không tự phù hợp SP B, dù cùng IdP ký.

### 12.2. CAS principal và LDAP backing user

CAS `cas:user=alice` có thể là login name chứ không phải immutable ID. Nếu directory đổi `alice` thành `an.nguyen` hoặc tái cấp username cho người khác, linking theo text này có nguy cơ sai. Cần:
- Xác định directory-backed immutable identity được CAS release đáng tin (ví dụ AD `objectGUID` với directory ID).
- CAS service registration cho phép release attribute đủ tin cậy/ổn định.
- Kiểm CAS ticket một lần và đúng `service` trước khi tin user/attribute.
- Map CAS authority + stable subject sang app_user_id.
- Xử lý lifecycle directory object deletion/recreation hoặc cross-forest migration.

### 12.3. LDAP DN, GUID, SID và SCIM

- **LDAP distinguished name (DN)** có thể đổi khi user chuyển OU/rename; tránh dùng làm primary identity link nếu directory ID ổn định có sẵn.
- **AD objectGUID** tồn tại gắn với object, nhưng khi object bị xóa rồi tạo lại, GUID mới; không tự map bằng email.
- **objectSID** mang ý nghĩa AD security identity và có lifecycle/trust/migration riêng, không tự so sánh qua forests.
- **SCIM `id`** là server-assigned resource ID trong SCIM provider scope; `externalId` có thể do provisioning client gán để đồng bộ, phải xác định authority/namespace. Chỉ provisioning không tự chứng minh browser user đang kiểm soát account đang link.

## 13. Identity broker hay liên kết trực tiếp tại ứng dụng?

Có hai kiến trúc thường gặp:

| Kiến trúc | Nơi lưu liên kết | Ứng dụng thấy gì? | Khi phù hợp |
| --- | --- | --- | --- |
| App tích hợp nhiều IdPs trực tiếp qua `oauth2Login` | App DB có external links | Token từ mỗi issuer; app map về U-100 | Ít ứng dụng, yêu cầu business mapping riêng |
| **Identity broker** như Keycloak/IAM | Broker lưu federated links và broker user | App chỉ tin một broker issuer/sub | Nhiều ứng dụng/tổ chức; central federation |
| Directory/SCIM pre-provision + SSO | Directory/IAM quản lý lifecycle; app mapping | Trusted stable user ID và groups từ authority | Enterprise provisioning có owner rõ |
| App và broker cùng mapping | Cả broker mapping và app mapping | Hai tầng identity | Cần xác định canonical user ID và chống link divergence |

**Broker cũng phải chứng minh account linking.** Một broker có thể cung cấp First Broker Login, account linking APIs và user federation, nhưng bật “Trust Email”/auto-merge không phải mặc định an toàn. Khi broker đã phát **stable broker subject**, app downstream có thể chỉ cần map broker `(iss,sub)` sang app account; không tự cố lookup upstream `sub` từ raw claims, vì upstream identity thuộc trust boundary khác.

Một broker có thể link A/B vào cùng broker user nhưng ứng dụng vẫn có **business app_user_id** riêng. Đừng nhầm broker user ID là app data primary key nếu ứng dụng cần di chuyển broker/realms.

## 14. Tích hợp Spring Security: xác thực hai OIDC providers

### 14.1. Client registrations chỉ là điểm khởi đầu

`application.yml` minh họa:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp
            client-id: ${CORP_OIDC_CLIENT_ID}
            client-secret: ${CORP_OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid,profile,email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
          partner:
            provider: partner
            client-id: ${PARTNER_OIDC_CLIENT_ID}
            client-secret: ${PARTNER_OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid,profile,email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          corp:
            issuer-uri: https://login.corp.example/oidc
          partner:
            issuer-uri: https://login.partner.example/oidc

server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
```

Cấu hình đòi **hai OIDC clients đã đăng ký thật** với correct redirect URIs, HTTPS và credentials trong secret manager. `${...}` là Spring placeholder đọc environment, không phải giá trị bí mật cần hardcode. Với test local HTTP, cookie Secure phải được cấu hình riêng cho môi trường dev; **không tắt HTTPS trong production**.

Spring Security `oauth2Login` thông thường cung cấp:
- `GET /oauth2/authorization/corp` và `/partner` để bắt đầu login.
- `/login/oauth2/code/corp` và `/partner` làm redirect callback.
- OIDC-specific user service khi scope chứa `openid` và provider hỗ trợ OIDC.
- Built-in authorization code state/nonce/token checks theo cơ chế framework, còn **liên kết app account** phải tự thiết kế.

**Hai `ClientRegistration` không tự có account linking.** Framework xác thực external identity; application cần `ExternalIdentityLinkRepository`, app account resolver, pending-link workflow và authorization riêng.

### 14.2. Spring SecurityFilterChain tối thiểu

Đây là **mảnh SecurityFilterChain**, không phải full runnable app. Một app hoàn chỉnh còn cần main class, dependency, OIDC issuers thật, user/tenant repository và linking workflow:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {
    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .requestMatchers("/settings/identities/**")
                    .authenticated()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
```

Không đặt endpoint linking thành `GET /link?provider=...&user=...` rồi ghi DB ngay. Khởi tạo link là **POST có CSRF** và yêu cầu fresh app authentication; sau đó redirect OIDC bằng authorization endpoint được allowlist. Đảm bảo framework không thay đổi U-100 khi login B callback mà vẫn còn pending link.

### 14.3. Lấy external key sau OIDC verification

```java
// MẢNH VÍ DỤ đặt tại bước sau khi OIDC authentication đã verified.
// Không chạy độc lập: cần OIDC user và LinkIntent context.
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import java.net.URL;

public record OidcExternalKey(String issuer, String subject) {
    public static OidcExternalKey fromVerified(OidcUser oidcUser) {
        URL issuerUrl = oidcUser.getIdToken().getIssuer();
        String subject = oidcUser.getIdToken().getSubject();
        if (issuerUrl == null || subject == null || subject.isBlank()) {
            throw new IllegalArgumentException("Missing OIDC issuer/sub");
        }
        return new OidcExternalKey(issuerUrl.toExternalForm(), subject);
    }
}
```

**Chỉ dùng `fromVerified` khi `OidcUser` được tạo từ một OIDC authentication flow đã xác minh theo expected issuer/client registration**. Không nhận một `OidcUser` tự dựng từ JSON browser chưa verify, không lấy `iss` từ user-supplied query để quyết định keyset, và không chuyển sang `getEmail()` làm unique identity.

### 14.4. Ứng dụng tự liên kết bằng thành phần nào?

Tùy thiết kế, có thể dùng:
- Custom `AuthenticationSuccessHandler` hoặc `OAuth2UserService<OidcUserRequest,OidcUser>` sau bước verification để **trích external key**, map account, hoặc xử lý pending intent, **nhưng phải ràng buộc original session**.
- Application `IdentityLinkService` thực hiện DB transaction, uniqueness và audit.
- Separate link callback flow hoặc broker account-linking API để tránh mặc định Spring thay Authentication.
- `SecurityContext` đại diện **app user U-100** chứ không chỉ một external `sub`, dùng custom principal đã được kiểm chứng mapping.
- `OidcUserService` để lấy UserInfo khi cần; OIDC Core yêu cầu `sub` UserInfo khớp ID Token khi gọi. **UserInfo profile không được tự thay `iss+sub` từ ID Token làm identity key**.

Cảnh báo: một `AuthenticationSuccessHandler` không phải giải pháp hoàn chỉnh nếu nó chỉ làm `findByEmailAndAttach`. Linking cần session-bound intent, reauth, external proof, collision checks và cleanup khi callback lỗi/cancel.

### 14.5. Tạo app principal và authority

Sau lookup `ExternalKey → U-100`:
1. Đọc account U-100, bảo đảm `ACTIVE`, không bị suspended/compromised.
2. Map roles/tenant membership từ application authority, không tin provider claims tùy ý.
3. Lưu provenance `authenticated_via_link_id`, IdP/auth_time/assurance nếu policy cần.
4. Tạo `Authentication` trong Spring Security context với principal nội bộ, authorities đã được policy kiểm soát.
5. Rotate/change session ID khi chuyển unauthenticated → authenticated theo Spring session fixation policy; tạo CSRF token/session đúng.
6. Khi logout app, clear session/context, không hứa upstream IdP session cũng bị logout nếu chưa có protocol SLO phù hợp.

Không cần ghi raw access/refresh tokens của IdP vào account links chỉ để login. Nếu cần API delegation, đó là authorized-client storage khác, yêu cầu encryption, scopes, refresh lifecycle và revocation.

## 15. Java 17 chạy độc lập: một app account, nhiều external keys

Chương trình này mô phỏng **chính sách ràng buộc identity**, không cần Spring/Maven/IdP. Nó cho thấy:
- Hai issuer có cùng `sub` **không phải cùng external identity**.
- Khi đã chứng minh cả account và external identity, hai external keys có thể map cùng U-100.
- Một external key **không thể** bị giành từ U-100 bởi U-999.
- Unlink một key không xóa app account hay key khác.

**Giới hạn:** flag `accountReauthenticated` và `externalProofVerified` trong demo là input giả đã được test setup xác nhận; **ứng dụng production không bao giờ nhận hai boolean đó từ client**. Phải lấy bằng chứng từ server-side verified session + OAuth2/OIDC/SAML protocol. Demo `synchronized` chỉ bảo vệ một Java object, **không thay database unique index/transaction đa node**.

Tệp `IdentityLinkDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;

public class IdentityLinkDemo {
    record ExternalKey(String issuer, String subject) {
        ExternalKey {
            if (issuer == null || issuer.isBlank()
                    || subject == null || subject.isBlank()) {
                throw new IllegalArgumentException(
                        "Verified issuer and subject are required");
            }
        }
    }

    static final class Links {
        private final Map<ExternalKey, String> owner = new HashMap<>();

        synchronized boolean link(
                String appAccount,
                ExternalKey verifiedExternal,
                boolean accountReauthenticated,
                boolean externalProofVerified) {
            if (!accountReauthenticated || !externalProofVerified) {
                return false;
            }
            String existing = owner.get(verifiedExternal);
            if (existing != null) {
                return existing.equals(appAccount);
            }
            owner.put(verifiedExternal, appAccount);
            return true;
        }

        synchronized String resolve(ExternalKey key) {
            return owner.get(key);
        }

        synchronized boolean unlink(
                String currentAccount, ExternalKey key,
                boolean reauthenticated) {
            if (!reauthenticated
                    || !currentAccount.equals(owner.get(key))) {
                return false;
            }
            return owner.remove(key, currentAccount);
        }
    }

    public static void main(String[] args) {
        ExternalKey corp =
                new ExternalKey("https://idp-a.example/oidc", "42");
        ExternalKey partner =
                new ExternalKey("https://idp-b.example/oidc", "42");

        Links links = new Links();
        System.out.println("Same sub but different issuer: "
                + !corp.equals(partner));
        System.out.println("Unproven link denied: "
                + !links.link("U-100", corp, false, true));
        System.out.println("First identity linked: "
                + links.link("U-100", corp, true, true));
        System.out.println("Second identity linked: "
                + links.link("U-100", partner, true, true));
        System.out.println("Both resolve to U-100: "
                + "U-100".equals(links.resolve(corp))
                + " / " + "U-100".equals(links.resolve(partner)));
        System.out.println("Takeover by U-999 denied: "
                + !links.link("U-999", corp, true, true));
        System.out.println("Unlink partner succeeded: "
                + links.unlink("U-100", partner, true));
        System.out.println("Partner no longer linked: "
                + (links.resolve(partner) == null));
        System.out.println("Corporate link preserved: "
                + "U-100".equals(links.resolve(corp)));
    }
}
```

Chạy bằng JDK 17+:

```bash
javac IdentityLinkDemo.java
java IdentityLinkDemo
```

**Stdout chính xác:**

```text
Same sub but different issuer: true
Unproven link denied: true
First identity linked: true
Second identity linked: true
Both resolve to U-100: true / true
Takeover by U-999 denied: true
Unlink partner succeeded: true
Partner no longer linked: true
Corporate link preserved: true
```

**Giải thích:** Java `record` so sánh hai thành phần issuer+subject, không trộn namespace. `Map<ExternalKey, appAccount>` mô phỏng UNIQUE external key. Link đã thuộc U-100 không bị một U-999 chuyển owner. Unlink partner vẫn giữ login corporate. Không dùng demo này làm production credential manager: không có OIDC verification, SAML signature, session, PKCE/state/nonce, locking database, audit, expiry hay recovery; những thứ đó phải có ở hệ thống thật.

## 16. Phòng chống account takeover, login swapping và linking CSRF

| Tấn công/sai lầm | Hậu quả | Kiểm soát |
| --- | --- | --- |
| Auto-link khi email trùng | Người mới sở hữu email cũ vào account khác | **Không auto-link bằng email** |
| B chỉ gửi `sub` chưa verify | Attacker gán external identity tùy ý | Validate issuer/signature/aud/nonce/state và trusted registration |
| Linking endpoint nhận `userId=U-100` từ browser | Attacker cố gắn IdP của mình vào victim | App user ID lấy từ authenticated server session |
| Link dựa vào một app session quá cũ | Session hijack đủ để thêm auth method | Fresh reauth/step-up, CSRF, risk checks |
| Callback không khớp initiating session | Login swapping, link vào user khác | One-time session-bound LinkIntent |
| Trùng `sub` giữa IdPs | Cross-issuer collision | Unique key gồm **issuer + sub** |
| Đổi IdP registration/sector sinh `sub` mới | Account duplication | Migration có proof, không email match |
| Identity key đã thuộc account khác | Account hijack hoặc silent merge | UNIQUE index + deny/recovery/admin approval |
| Two simultaneous callbacks | Double insert/owner overwrite | DB transaction, UNIQUE index, consumed intent |
| Issuer mix-up với nhiều IdPs | Redeem code/token tại provider sai | Expected issuer in state, RFC 9207/RFC 9700, exact redirect |
| Attacker tự tạo issuer/JWKS URL | SSRF/key injection | Provider allowlist managed by admin, no dynamic issuer trust |
| Role `admin` từ IdP đối tác | Escalation quyền app | Trust mapping và tenant authorization riêng |
| Unlink last auth method | Lockout | Verify remaining sign-in/recovery method |
| Deprovision IdP nhưng app session còn | Quyền tồn tại sau revoke | Session provenance, TTL/revocation/signals |
| Key/token/session leak qua log | Credential theft | Redact logs, HTTPS, vault/KMS |
| Admin migration bằng CSV email | Sai user/account | Verified immutable IDs, dual approval, rollback |

**Lưu ý riêng về OAuth2 access token:** một access token dành cho API nào đó không tự là chứng cứ “user vừa xác thực để link app account”. Đối với OIDC, dùng đúng RP authorization code flow và ID Token validation. Không dùng token của IdP A có `aud=client-A` để đăng nhập/lấy danh tính cho app client B mà bỏ qua issuer/audience checks.

## 17. Deprovision, account recovery và đổi IdP

### 17.1. Khi một IdP khóa nhân viên

Nếu người dùng còn linked với IdP B, có thể tiếp tục đăng nhập U-100 qua B. Đây có thể là yêu cầu business hợp lệ hoặc **rủi ro**: sau khi nghỉ việc, quyền truy cập công ty không nên tồn tại nhờ một login bên ngoài khác.

Cần tách:
- **Auth method revoked**: chỉ external link A bị vô hiệu.
- **App account disabled**: U-100 không được đăng nhập qua **bất kỳ** IdP nào.
- **Tenant membership revoked**: U-100 vẫn tồn tại nhưng không còn quyền với tenant CORP.
- **Sessions/tokens revoked**: xóa phiên/app refresh access phù hợp để thay đổi có hiệu lực.
- **Business data retention**: có thể giữ tài liệu phục vụ audit theo policy mà không cho user truy cập.

SCIM provisioning, IdP event/webhook, HR status và app ACL updates cần có **owner/source of truth**. Nếu một IdP báo user disabled, policy công ty phải quyết định có khóa toàn account, một link, hoặc chỉ tenant membership. Không tự suy rằng “còn link B” luôn cho quyền corporate.

### 17.2. Account recovery khi mất IdP A

Nếu user mất quyền đăng nhập A mà U-100 vẫn có B đã liên kết, user có thể dùng B theo chính sách (có thể yêu cầu assurance phù hợp). Nếu **chưa link B**, không gắn B vào U-100 chỉ bằng cách gửi email nói “tôi là Alice”. Cần recovery độc lập với xác minh danh tính đủ mạnh, admin approval hoặc identity proofing đúng rủi ro, đầy đủ audit và thông báo.

### 17.3. Đổi nhà cung cấp danh tính toàn doanh nghiệp

Ví dụ IdP A được thay bằng IdP D:
1. Inventory registered clients, realms, old issuer+sub, immutable directory IDs và tenant memberships.
2. Lấy migration mapping được ký/phê duyệt từ authority hiện hữu hoặc dual-auth proof khi người dùng còn access cả hai.
3. Thử trên sandbox users và edge cases: email trùng, renamed user, pairwise sub, deleted/recreated directory object.
4. Tạo new external link D→U-100 bằng transaction, không xóa A trước khi kiểm D thành công.
5. Canary theo tenant, log link outcomes và hỗ trợ rollback.
6. Sau khi đạt xác minh, revoke link A theo chính sách; xử lý sessions và stale tokens.
7. Không thay app user ID trong business database.

**Không giả định `issuer-uri` đổi chỉ là đổi DNS.** OIDC `iss` khác tạo identity namespace khác; cần trust migration. Nếu chỉ issuer key rotation trong cùng issuer, lại là câu chuyện JWKS/trust chứ không tự tạo identity mới.

## 18. Sự khác nhau giữa account linking và MFA

Liên kết tài khoản Google+Entra không có nghĩa user đã bật **MFA**. Nếu một app account có hai cách đăng nhập khác nhau, attacker chỉ cần chiếm **cách yếu nhất** để truy cập account đó.

Do đó:
- Đánh giá assurance của từng IdP/linked identity, không tự gán `AAL2` vì có hai identities.
- Require MFA/step-up cho linking/unlinking nhạy cảm.
- Đối với tài nguyên admin, kiểm freshness, `auth_time`, `acr`/`amr` theo OIDC profile và policy; không copy claim assurance từ IdP chưa được tin cậy.
- Nếu một weaker IdP B liên kết với account admin U-100, không mặc định B login có quyền thực hiện thao tác quản trị.
- Có thể giới hạn `allowed_idp_for_sensitive_action` hoặc cần reauth với corporate IdP.
- Quyết định session lifetime/revocation nhất quán với source of authentication, đặc biệt khi user thay tenant hay bị deprovision.

**Liên kết hai identifiers không bằng hai factors.** MFA là phối hợp nhiều factors theo một authentication event/policy; account linking chỉ mở rộng các đường truy cập vào app account.

## 19. Privacy, audit và minh bạch với người dùng

Danh sách linked identities bản thân là **dữ liệu nhạy cảm** vì có thể tiết lộ nhân viên thuộc tổ chức nào hoặc có tài khoản tại IdP nào. Các nguyên tắc:
- Chỉ hiển thị identities đã liên kết cho account owner/Admin được phép, không leak qua public API.
- Cân nhắc tên hiển thị provider thay vì full issuer+sub; không in raw immutable sub lên UI nếu không cần.
- Thông báo khi link/unlink xảy ra, có kênh cảnh báo nếu thao tác không do user khởi xướng.
- Audit `actor app_user_id`, target link, provider, event type, time, request correlation, assurance và outcome, **không log ID Token/access token/refresh token**.
- Định nghĩa retention/history cho revoked links và sự kiện security; hạn chế truy cập và xóa theo pháp luật/chính sách dữ liệu.
- Khi trả lỗi “identity đã link account khác”, dùng thông điệp không lộ email/ID của người khác.
- Không cho IdP A biết tự động user còn có link IdP B qua notification/cross-IdP signals nếu không có cơ sở pháp lý/thỏa thuận. NIST `63C-4` nhắc RP xử lý account-linking signals theo privacy risk assessment.

### 19.1. UX mẫu cho trang “Phương thức đăng nhập”

```text
Phương thức đăng nhập đã liên kết
  [Corporate SSO]    Liên kết từ 2026-10-10    [Đang sử dụng]
  [Partner SSO]      Liên kết từ 2026-11-01    [Gỡ liên kết]

[Thêm phương thức đăng nhập]

Gỡ Partner SSO?
- Bạn sẽ không thể đăng nhập tài khoản này bằng Partner SSO nữa.
- Phiên và quyền truy cập có thể được thu hồi theo chính sách bảo mật.
[Xác thực lại] [Hủy] [Xác nhận gỡ]
```

UI này chỉ minh họa. Khi user bấm “Thêm”, app cần bước server-side POST/CSRF, reauth và OIDC redirect. Không có chuyện chỉ điền email rồi thêm liên kết.

## 20. Bộ test matrix trước release

| Trường hợp | Kỳ vọng |
| --- | --- |
| OIDC A login với link tồn tại | Map đúng `(iss A, sub A) → U-100` |
| OIDC B login với link tồn tại | Map đúng `(iss B, sub B) → U-100` |
| A/B trùng `sub=42` | Hai external identities khác nhau |
| A/B trùng email, không link | Không tự gộp accounts |
| Email A đổi, `iss+sub` giữ nguyên | Không tạo app account mới |
| `email_verified=true` của B nhưng chưa link | Không dùng để access U-100 |
| OIDC ID Token sai chữ ký | Không authenticate/link |
| ID Token đúng chữ ký nhưng `aud` sai | Reject; không coi là valid for app |
| OIDC `iss` khác registered issuer | Reject |
| `state`/`nonce`/PKCE sai | Reject, pending LinkIntent không được consume thành công |
| Authorization-server mix-up | Callback từ B không được xử lý như A |
| User U-100 đã reauth, xác thực B hợp lệ | Link B → U-100 sau DB uniqueness |
| User chưa login app mở linking callback | Reject; không chọn user từ query |
| Session U-100 đổi thành U-999 trước callback | Reject linking attempt |
| Session U-100 quá cũ theo sensitive action policy | Bắt reauth/step-up |
| Replayed link callback | Intent đã CONSUMED, reject |
| Link intent hết TTL | Reject, cleanup an toàn |
| B identity đã link U-999 | Không chuyển owner sang U-100 |
| Hai requests cùng link B | UNIQUE constraint chặn double attach |
| Nhiều pods xử lý link | Shared DB/session state nhất quán |
| Mất kết nối DB lúc commit | Không thông báo thành công khi chưa commit |
| Unlink B theo U-100 | B không còn dùng để login U-100 |
| Unlink B qua request của U-999 | Reject |
| Unlink last authentication method | Áp chính sách lockout/recovery |
| Unlink thành công nhưng session B còn tồn tại | Revoke/invalidate theo policy |
| IdP B deprovision | App quyết định revoke link/account/tenant đúng policy |
| IdP B bị compromise | Risk response không cho role vượt quyền |
| SAML transient NameID | Không lưu làm identity link bền |
| SAML Assertion sai recipient/audience | Reject |
| SAML XML signature wrapping/replay | Reject |
| CAS username được tái cấp | Không cho chủ mới chiếm U-100 |
| LDAP DN đổi do move OU | Immutable directory ID vẫn map đúng |
| LDAP object bị xóa/tạo mới cùng email | Không tự map vào old account |
| Pairwise OIDC `sub` đổi khi thay sector | Cần migration/link proof, không email auto-merge |
| Account U-100 DISABLED | Mọi linked IdPs đều không cho login U-100 |
| Tenant CORP revoked | B login không giữ quyền CORP |
| IdP B assurance thấp hơn policy admin | Step-up hoặc deny admin action |
| Raw tokens trong audit log | Không được xuất hiện |
| Notification khi link/unlink | User nhận thông báo, không lộ identity khác |
| Restore/backup/migration | Unique links và audit không bị hỏng |

**Các lớp kiểm thử nên có:** unit tests identity key và collision; DB integration tests uniqueness/transaction/outbox; Spring Security integration với OIDC sandbox issuers A/B và session-bound link intent; browser E2E đa tab/SameSite/CSRF; SAML/CAS/LDAP adapter-specific tests; security negative cases cho issuer mix-up, session swapping, account takeover, unlink last method, deprovision và multi-tenant authorization.

`@WithMockUser` **không chứng minh** OIDC/SAML identity đã được verify hay LinkIntent an toàn: nó chỉ tạo một mock authenticated context. Test bắt buộc phải đi qua thật code path token/response validation trong sandbox có trusted provider fixtures.

## 21. Runbook triển khai an toàn

**Chuẩn bị:**
1. Inventory IdPs/realms/client registrations, stable subject claims và trust policies, owner mỗi tenant.
2. Chọn internal app account ID ổn định, lưu business data theo ID đó.
3. Thiết kế external keys chuẩn giao thức, unique DB index và lịch sử link/unlink.
4. Xác định who can link: tài khoản phải ACTIVE, fresh auth, tenant/policy phù hợp.
5. Thiết kế pending LinkIntent server-side, one-time/short TTL, session-bound, expected issuer và CSRF.
6. Định nghĩa behavior khi identity đã link nơi khác, account còn zero methods, IdP disabled, user đổi email và account duplicate.
7. Xây security test suite và audit/notification.

**Trong luồng liên kết:**
1. User đăng nhập U-100 rồi chủ động POST yêu cầu link B.
2. App kiểm fresh session và reauth policy, tạo LinkIntent.
3. Browser redirect đến B OIDC authorize với state/nonce/PKCE; app ghi expected issuer B.
4. Callback được verify đầy đủ tại B client registration.
5. App consume intent với original U-100 session; kiểm account ACTIVE, B không linked nơi khác.
6. Insert DB trong transaction với unique key, ghi audit, commit.
7. Notify user và hiển thị identities đã liên kết, **không tự gộp business accounts**.

**Khi cần gỡ/chuyển IdP:**
1. Require fresh auth/CSRF, kiểm còn đường access hoặc recovery.
2. Verify link thuộc U-100 và tác động lên sessions/provenance, tenant permissions.
3. Revoke/disable link, audit, notify và review active tokens.
4. Chạy migration có proof nếu thay issuer/subject; có rollback và không thay app user ID.

## 22. Câu hỏi tự kiểm tra

**Q1. Vì sao hai ID Token có cùng `sub=42` chưa chắc là một người?**  
Vì `sub` chỉ duy nhất **trong issuer**. Cặp `(iss,sub)` mới xác định external identity của OIDC.

**Q2. Hai IdPs đều trả `email=an@example.com` và `email_verified=true` có tự liên kết được không?**  
Không. Email có thể đổi, tái cấp và được xác minh theo policies khác nhau. Cần chứng minh quyền sở hữu app account và external login mới.

**Q3. Ứng dụng nên lấy ID chính của user từ đâu?**  
Tạo `app_user_id` nội bộ ổn định; map một hoặc nhiều verified external identities sang ID đó. Business records/roles tham chiếu app ID.

**Q4. Khi người dùng thêm IdP B, có thể chỉ yêu cầu đăng nhập B rồi link vào U-100 theo query không?**  
Không. Phải có authenticated app U-100 session, fresh auth, session-bound LinkIntent, verified B login và DB uniqueness.

**Q5. Nếu B identity đã linked U-999 thì app có nên chuyển nó sang U-100 khi email giống không?**  
Không. Đây là conflict, cần deny/recovery/admin-mediated proof và audit; không overwrite ownership.

**Q6. Unlink B có tự kết thúc mọi active sessions không?**  
Không. Cần policy revocation/session invalidation, đặc biệt khi session được tạo từ B.

**Q7. Một tài khoản có hai IdPs có được coi là MFA không?**  
Không. Hai login methods không tương đương hai factors trong cùng authentication event; assurance/step-up phải kiểm tra riêng.

**Q8. Nếu ứng dụng dùng identity broker, có cần tự lưu upstream `iss+sub` không?**  
Không nhất thiết. Nếu broker quản lý links và phát stable broker subject, app có thể map `(broker iss, broker sub)` sang app account. Upstream mapping thuộc broker trust boundary.

## 23. Tài liệu chính thức và chuẩn tham khảo

1. [OpenID Connect Core 1.0 – Claim Stability & Uniqueness `5.7](https://openid.net/specs/openid-connect-core-1_0.html#ClaimStability): `iss` + `sub` là cặp định danh bền vững, email/username không có cùng bảo đảm.
2. [OpenID Connect Core 1.0 – Subject Identifier Types `8](https://openid.net/specs/openid-connect-core-1_0.html#SubjectIDTypes): public/pairwise `sub` và sector identifiers.
3. [NIST SP 800-63C-4 – Federation and Assertions](https://pages.nist.gov/800-63-4/sp800-63c.html): federated identifiers, RP subscriber accounts, account linking `3.8.1`, account resolution, notification và privacy signals.
4. [OWASP Authentication Cheat Sheet – Secure Federated Account Linking](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#secure-federated-account-linking): không auto-link email, yêu cầu existing session và verified new identity.
5. [OWASP OAuth 2.0 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): state, PKCE, CSRF/mix-up và authorization code security.
6. [RFC 9700 – OAuth2 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700.html): PKCE, redirect URI, mix-up defense và bảo vệ flow đa provider.
7. [RFC 9207 – Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207.html): issuer identification trong authorization response.
8. [Spring Security – OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): OAuth2/OIDC login, authorization/redirect endpoints.
9. [Spring Security – OAuth2 Login Advanced](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): `OidcUserService`, custom success/userInfo processing.
10. [Keycloak – Identity Brokering](https://www.keycloak.org/docs/latest/server_admin/#_identity_broker): first broker login, external IdP config và account linking.
11. [Keycloak – Account Linking](https://github.com/keycloak/keycloak/blob/main/docs/documentation/server_development/topics/identity-brokering/account-linking.adoc): link initiation có request binding và trách nhiệm CSRF của application.
12. [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session fixation, lifecycle, logout và protection.
13. [SCIM 2.0 Core Schema – RFC 7643](https://www.rfc-editor.org/rfc/rfc7643.html): `id`, `externalId` và phạm vi định danh SCIM.
14. [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): NameID, NameQualifier, assertions và conditions.

**Tóm tắt cuối:** **Một app account có thể có nhiều external identities**, nhưng chỉ sau khi từng identity đã được xác thực đúng giao thức và được **liên kết có chủ đích, session-bound, với app account đã xác thực**, trong transaction có unique key. Với OIDC, khóa đáng tin là `(iss,sub)`; email/username/phone không phải khóa định danh lâu dài. Spring Security giúp xác thực từng IdP, còn việc quản lý app user ID, linking/unlinking, collision, revocation, quyền tenant và account recovery là trách nhiệm **Identity Link Service/IAM policy** của ứng dụng.