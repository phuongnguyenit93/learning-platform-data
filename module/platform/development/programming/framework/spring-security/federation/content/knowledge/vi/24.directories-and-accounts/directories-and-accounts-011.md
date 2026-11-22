# Phối hợp quy trình thêm người dùng, đổi vai trò và ngừng quyền truy cập

## Mục tiêu học tập

Sau bài học này, bạn có thể:

1. Mô tả quy trình **Joiner–Mover–Leaver (JML)**: thêm người dùng, đổi chức danh/nhóm/quyền và ngừng quyền truy cập trong hệ thống có thư mục LDAP/Active Directory, IdP/SSO, ứng dụng Spring Security và các API/tokens/sessions.
2. Phân biệt **HR/nguồn quyết định nhân sự**, **Identity Governance (IGA/IAM)**, **Directory/IdP**, **SCIM provisioning**, **identity linking** và **authorization của ứng dụng**. Hiểu vì sao SSO thành công không có nghĩa một người được phép dùng dữ liệu trong ứng dụng.
3. Thiết kế dữ liệu bền vững: ID nội bộ bất biến, cặp `(trusted issuer, stable subject)`, SCIM `id` và `externalId`, tenant membership, role/permission grant, approver, expiry, revision và audit.
4. Thiết kế quy trình onboarding không tự gán quyền admin; xử lý phê duyệt, provisioning, account linking, MFA, test quyền tối thiểu và thời điểm kích hoạt.
5. Thiết kế chuyển vai trò với **remove old privileges, then grant approved new privileges**, tách quyền cũ/mới, kiểm xung đột Separation of Duties (SoD) và ngăn privilege accumulation.
6. Thiết kế leaver/offboarding theo mức độ khẩn: khóa đăng nhập mới, vô hiệu tài khoản/link, thu hồi sessions/tokens/API keys/grants, xử lý phiên ở những service khác và bảo toàn nhật ký theo chính sách.
7. Hiểu ví dụ SCIM 2.0 theo **RFC 7643/7644** để tạo user, cập nhật `active` và sửa `Groups.members`, dùng ETag/`If-Match` khi hỗ trợ; phân biệt đồng bộ tài khoản với xác thực và thu hồi phiên.
8. Áp dụng Spring Boot 3/Spring Security 6 với `@EnableMethodSecurity`, `@PreAuthorize` và policy đọc lại account/permissions từ nguồn đáng tin; biết vai trò của `UserDetailsService`, `LdapAuthoritiesPopulator` và `GrantedAuthoritiesMapper` tùy authentication mechanism.
9. Xây consumer sự kiện lifecycle **idempotent, chống version cũ ghi đè** và có đối chiếu định kỳ; chạy một chương trình **Java 17+ độc lập** minh họa thêm user, chuyển quyền, vô hiệu và reactivation có kiểm soát.
10. Kiểm thử các tình huống thất bại: event trễ/đảo thứ tự, cùng email nhưng khác user, cache/HttpSession chứa authorities cũ, access token chưa hết hạn, session trên nhiều nodes và partner/tenant bị ngừng.

## 1. Tại sao xác thực liên kết cần quy trình quản trị người dùng?

Trong kiến trúc federation, một nhân viên có thể đăng nhập bằng Active Directory/Kerberos, CAS, SAML2, OIDC hoặc một proxy đã xác thực. **Identity Provider (IdP)** trả lời “ai đang đăng nhập?”, còn ứng dụng trả lời “người này có được phép làm gì với tài nguyên nào?”. **Directory và account lifecycle** cung cấp đầu vào quan trọng cho cả hai lớp.

Ví dụ ứng dụng B2B:

- HR có hồ sơ nhân viên với `employeeId=E-103`, trạng thái làm việc và đơn vị.
- IAM/IGA quản lý yêu cầu quyền, phê duyệt và chính sách xung đột.
- AD/LDAP lưu user directory, groups hoặc trạng thái account.
- IdP phát OIDC `(iss, sub)` hoặc SAML2 identity sau authentication.
- Provisioning (có thể qua SCIM) tạo/cập nhật/tắt local account trong Portal.
- Portal lưu `internalAccountId`, tenant memberships và các quyền cụ thể như `REPORT_READ`, `REPORT_APPROVE`.
- Spring Security tạo `Authentication` cho người dùng đăng nhập; method/resource authorization kiểm quyền có hiệu lực.

**Một thay đổi ở HR hoặc AD không tự động sửa mọi Spring Security session/tokens.** Cần phối hợp lifecycle, dữ liệu quyền và cơ chế thu hồi đã thiết kế.

### 1.1. Ba tình huống phải phối hợp

| Tình huống | Sự kiện nghiệp vụ | Mục tiêu an ninh | Các hệ thống cần tham gia |
| --- | --- | --- | --- |
| **Joiner** – Thêm người dùng | Nhân viên/đối tác gia nhập, có nhu cầu truy cập | Chỉ tạo account và quyền đã duyệt, không auto-admin | HR/owner → IGA → Directory/IdP → provisioning → app |
| **Mover** – Đổi vai trò | Chuyển bộ phận, dự án, tenant hoặc cấp bậc | Gỡ quyền không còn phù hợp, cấp đúng quyền mới, kiểm SoD | HR/manager → IGA → groups/SCIM → local grants → sessions |
| **Leaver** – Ngừng truy cập | Nghỉ việc, hợp đồng hết hạn, account compromised | Ngừng login mới **và** quyền/phiên/tokens đang còn | HR/SOC → IdP/Directory → apps → session/token stores → audit |

**Chuyển vai trò không chỉ là “thêm group mới”**. Nếu người dùng được cộng dồn quyền mà không bỏ quyền cũ, sau nhiều lần thuyên chuyển có thể sở hữu quyền của nhiều bộ phận không còn cần thiết (privilege creep).

**Ngừng quyền không chỉ là “disable account trong AD”**. Một ứng dụng đã xác thực user có thể giữ phiên `HttpSession` hay bearer token chưa hết hạn; nó không kiểm lại AD/IdP ở mỗi request nếu không được thiết kế như vậy.

## 2. Sơ đồ trách nhiệm và nguồn dữ liệu có thẩm quyền

```mermaid
flowchart LR
    HR["HR / Contract / Partner owner"] --> IGA["IAM / IGA approvals & SoD"]
    IGA --> Dir["Directory / AD / LDAP"]
    IGA --> Prov["Provisioning / SCIM / events"]
    Dir --> IdP["Trusted IdP / SSO"]
    IdP --> Login["Spring Security authentication"]
    Prov --> Account["Application account + tenant grants"]
    Login --> Link["Issuer+subject → internal account"]
    Link --> Account
    Account --> Authz["Request / method / resource authorization"]
    IGA --> Revoke["Sessions & tokens revocation"]
    Revoke --> Authz
    Account --> Audit["Audit, revision, reconciliation"]
    Revoke --> Audit
```

### 2.1. Ai quyết định điều gì?

| Thành phần | Nguồn sự thật chủ yếu | Không tự làm |
| --- | --- | --- |
| **HR/Contract System** | Ngày bắt đầu/kết thúc, trạng thái quan hệ lao động/đối tác, đơn vị | Không tự định nghĩa Java `GrantedAuthority` |
| **Business owner/manager** | Nhu cầu quyền theo nhiệm vụ/tenant/project | Không tự bypass Security/IAM với admin role |
| **IAM/IGA** | Quy trình yêu cầu/phê duyệt quyền, SoD, recertification | Không đảm bảo mọi phiên ứng dụng đã bị thu hồi nếu không có integration |
| **Directory / AD / LDAP** | Directory object, group, account status, principal/UPN | Không tự cấp quyền object-level của mỗi ứng dụng |
| **IdP / Federation** | User authentication và identity assertion sau trust checks | Không biết mọi local permission và session app |
| **SCIM provisioning client** | Đẩy sự kiện User/Group state sang ứng dụng | Không tự logout app sessions hoặc validate SAML/OIDC |
| **Portal Account Service** | Internal account ID, tenant memberships, role/permission grants, revision | Không kiểm chứng SSO ticket khi dùng riêng |
| **Spring Security** | `Authentication`, `GrantedAuthority` và enforcement | Không tự xây HR approvals hay SCIM nếu chưa tích hợp |
| **Session/Token Store** | App sessions, refresh tokens/grants, API token revocation | Không tự biết user đã nghỉ việc nếu không nhận tín hiệu |
| **Security/SOC** | Incident response, emergency deny và audit | Không thay quyền phê duyệt thông thường khi không có incident |

### 2.2. Đồng bộ trạng thái không đồng nghĩa truyền toàn bộ quyền

**Authentication claims** (từ IdP) và **authorization grants** (từ ứng dụng/IAM) có thể có nguồn riêng. Ví dụ OIDC `sub` chỉ chứng minh định danh tại issuer; nó **không tự trở thành ROLE_ADMIN**. Một AD group tên `Administrators` cũng không mặc nhiên có quyền quản lý tenant trên Portal.

Hướng ít rủi ro:

- IdP/Directory xác minh danh tính, nhóm khi cần.
- App có **explicit mapping** giữa group object IDs/approved IAM roles và local permissions theo tenant.
- Local account phải `ACTIVE`, membership đang hiệu lực và grant chưa hết hạn.
- Với action nhạy cảm, authorization service kiểm lại **nguồn quyền hiện hành**, không chỉ relying on group name hay authorities từ lúc đăng nhập nhiều giờ trước.
- Audit nguồn của từng grant: yêu cầu nào, ai duyệt, điều kiện, expiry, hệ thống đích và revision.

## 3. Mô hình dữ liệu chung cho JML trong ứng dụng

### 3.1. Các khóa không được nhầm

| Định danh | Ví dụ | Phạm vi / bất biến |
| --- | --- | --- |
| HR/contract ID | `E-103` hoặc `C-55` | Dùng trong HR/contract; không nhất thiết được gửi tới mọi IdP |
| Directory object GUID/ID | Opaque ID của AD/LDAP | Gắn với directory object; UPN/display name có thể đổi |
| OIDC `iss` + `sub` | `https://login.idp.example` + `opaque-user-001` | Dùng cặp identity đã xác minh, không dùng `sub` trần trên mọi issuers |
| SAML2 issuer + stable subject | IdP entity ID + persistent NameID/profile | Chỉ dùng theo hợp đồng NameID; không dùng email tự động nếu không ổn định |
| SCIM `id` | `b2d3-...` | Do SCIM **service provider** cấp, ổn định/không tái dùng |
| SCIM `externalId` | `hr:E-103` | Do provisioning client cấp, **scoped theo provisioning domain** |
| SCIM `userName` | `a.nguyen@example.org` | Username trong SCIM schema, không nhất thiết là internal PK |
| App `internalAccountId` | `acct-1007` | Khóa bất biến cho local users, sessions, grants và audit |
| Tenant ID | `tenant-finance` | Phạm vi quyền; không lấy từ query/header chưa xác thực |
| Role ID | `TENANT_ANALYST` | Chính sách/tập quyền được app/IGA quản lý |
| Permission | `REPORT_APPROVE` | Hành động cụ thể đối với tài nguyên phù hợp |
| Session/token ID | Opaque ID | Dùng revocation, không phải identity link |

**Email, tên hiển thị, username rút gọn và group display name không phải khóa federation bền vững.** Chúng có thể đổi, trùng hoặc được tái sử dụng.

### 3.2. Bảng dữ liệu gợi ý

```text
account
  account_id            -- opaque, immutable local PK
  lifecycle_status      -- PENDING, ACTIVE, SUSPENDED, DISABLED
  account_revision      -- monotonic version
  approved_at
  disabled_at
  disabled_reason_code

external_identity_link
  link_id
  account_id
  source_type           -- OIDC, SAML2, KERBEROS, PROXY...
  trusted_issuer        -- exact approved namespace
  external_subject      -- stable opaque subject
  link_status
  linked_at, unlinked_at
  UNIQUE(source_type, trusted_issuer, external_subject)

tenant_membership
  account_id, tenant_id
  status, valid_from, valid_until
  approved_by, approved_at

role_grant
  grant_id
  account_id, tenant_id, role_id
  source_request_id
  approved_by, approved_at
  valid_from, valid_until
  revoked_at
  UNIQUE(account_id, tenant_id, role_id, active_revision)

permission_policy
  role_id, permission, resource_scope, policy_version

lifecycle_event
  event_id              -- idempotency identity
  account_id
  source_system
  source_revision
  event_type
  received_at, applied_at
  outcome, reason
```

Đây là **mô hình kiến trúc**, không phải DDL SQL có thể chạy nguyên khối. Các khóa unique/transaction/snapshot consistency và partial indexes phải được thiết kế cho PostgreSQL/MySQL/DB cụ thể. Nếu lưu quyền bằng `role_grant`, không nên “thực thi” `UNIQUE(...,active_revision)` như constraint tự đủ trong mọi DB; còn cần ràng buộc **không có hai grant đang active trùng** theo chính sách thực tế.

### 3.3. Quy tắc liên kết danh tính

1. Một cặp `(issuer, stable subject)` đang ACTIVE chỉ link đến **đúng một** account nội bộ tại một thời điểm.
2. Có thể có nhiều federation identities cho cùng account (ví dụ chuyển IdP) **chỉ sau quy trình chứng minh và duyệt linking**.
3. Không auto-link dựa trên email giống nhau hoặc local part trước `@`.
4. External subject thay đổi do IdP migration cần review, không thực hiện `toLowerCase`/loại realm để “gộp lại”.
5. Account bị disable không thể được phục hồi chỉ bởi một SCIM event “add group” hoặc login OIDC thành công.
6. Account reactivation phải là **một workflow có phê duyệt rõ**, kiểm lại grants thay vì phục hồi quyền cũ mặc định.
7. Không tái sử dụng internalAccountId của nhân viên cũ cho người mới dù username/email được tái sử dụng.
8. Các quyền nhạy cảm có thời hạn, owner và recertification; tránh “grants tồn tại vĩnh viễn” do group lạc nguồn.

## 4. State machine: thêm, đổi vai trò, khóa và nghỉ việc

```mermaid
stateDiagram-v2
    [*] --> PENDING: HR/owner tạo yêu cầu
    PENDING --> APPROVED: IAM/manager/Security duyệt
    APPROVED --> ACTIVE: Provision + identity link + test
    PENDING --> REJECTED: Không đạt policy
    APPROVED --> REJECTED: Không triển khai được
    ACTIVE --> ACTIVE: Mover: revoke old + grant approved new
    ACTIVE --> SUSPENDED: Incident / tạm đình chỉ
    SUSPENDED --> ACTIVE: Review + approval
    ACTIVE --> DISABLED: Nghỉ việc / offboard
    SUSPENDED --> DISABLED: Chấm dứt hợp đồng
    DISABLED --> REHIRE_REVIEW: Có yêu cầu tái gia nhập
    REHIRE_REVIEW --> ACTIVE: Reverify + new approval
    REHIRE_REVIEW --> DISABLED: Từ chối
    DISABLED --> [*]: Retention/anonymization theo policy
```

**State có tính nghiệp vụ, không phải API Spring Security mặc định.** Để chạy, phải có service lập transaction, chuyển trạng thái có điều kiện, ghi `accountRevision` và phát sự kiện thu hồi.

### 4.1. Bảng quyết định truy cập

| Account state | Cho login mới? | Existing session access | Cho grant role mới? |
| --- | --- | --- | --- |
| `PENDING` | Không | Không | Chỉ dự thảo; chưa effective |
| `APPROVED` nhưng chưa provision | Không | Không | Chờ activation |
| `ACTIVE` | Có nếu IdP/account/tenant policy đạt | Có theo authorization + session policy | Theo workflow phê duyệt |
| `SUSPENDED` | Không | Phải deny/revoke theo phạm vi | Không |
| `DISABLED` | Không | Phải deny/revoke | Không |
| `REHIRE_REVIEW` | Không trước approval | Không | Không cho khôi phục grants cũ tự động |

**Quan trọng:** `ACTIVE` của directory **không tự là tất cả quyền**. Một account ACTIVE nhưng không có membership tenant Alpha vẫn phải bị từ chối khi truy cập dữ liệu tenant Alpha.

### 4.2. State transitions cần kiểm đồng thời

Với mỗi transition nên ghi:

- Subject/internal account ID và identity link namespace.
- Nguồn/loại event, source revision, event ID, expected current revision.
- Người/tổ chức yêu cầu, approver độc lập với requester khi policy yêu cầu.
- Trạng thái trước/sau, roles/memberships trước/sau và hiệu lực từ/đến.
- Các hệ đích đã nhận/ACK, còn lỗi/chờ retry.
- Session/token revocation outcome và mốc kiểm chứng.
- Audit không ghi secrets, raw SAMLResponse/OIDC tokens/session cookies.

Không đánh dấu workflow hoàn tất chỉ vì directory đã ghi `enabled=false` mà bỏ qua ứng dụng/tokens còn hoạt động.

## 5. Joiner – quy trình thêm người dùng có kiểm soát

### 5.1. Trước khi tạo account

Bắt đầu từ **quyết định nghiệp vụ đáng tin**: hợp đồng lao động/đối tác hiệu lực, owner, tenant, loại account, vị trí và công việc. Xác định:

1. Start date/validity, manager, cost center, đội hỗ trợ, contract end date.
2. External identity source được phép: AD/Kerberos realm, OIDC issuer, SAML2 IdP hoặc partner gateway.
3. Stable subject/Directory object ID mà người dùng sẽ được gắn trong ứng dụng.
4. Tenant(s) và resource scopes cần truy cập, role bundle **ít quyền nhất** theo chức năng.
5. Quyền nhạy cảm cần phê duyệt bổ sung, MFA/step-up, SoD conflicts.
6. Có tài khoản cũ cùng email/username hay không; nếu có, **không auto-merge**, cần kiểm identity proof và lịch sử.
7. Thời hạn mặc định của grant, recertification và offboarding owner.

### 5.2. Joiner flow chuẩn

```mermaid
sequenceDiagram
    participant HR as HR / Partner Owner
    participant IAM as IGA / Approvers
    participant DIR as Directory / IdP
    participant SCIM as Provisioning
    participant APP as Portal Account Service
    participant AUD as Audit
    HR->>IAM: Create approved joiner request (stable person ID, start date)
    IAM->>IAM: Check manager approval, MFA/SoD/least privilege
    IAM->>DIR: Create/enable directory identity as appropriate
    DIR-->>IAM: Stable external identity references
    IAM->>SCIM: Create/upsert app user + approved memberships
    SCIM->>APP: Versioned provisioning event / SCIM request
    APP->>APP: Link identity, create local account, grant approved roles
    APP-->>SCIM: Success + resource ID/version
    APP->>AUD: Record event, approver, snapshot/revision
    IAM->>APP: Go-live readiness check
    APP-->>IAM: Active only after policy tests
```

**Không provision bằng user-facing login callback ngay từ đầu** nếu chưa có policy Joiner/JIT provisioning rõ. JIT creation có thể hợp lệ nhưng phải có allowlist issuer/tenant, account anti-collision, approval và role defaults giới hạn; không cho lần đăng nhập đầu tiên tự nhận `ROLE_ADMIN`.

### 5.3. Trình tự an toàn

1. HR/owner gửi yêu cầu với **immutable person/account reference** và start date.
2. IAM/IGA kiểm owner, scope, legal basis và SoD.
3. Directory/IdP tạo identity, cấp nhóm **phục vụ authentication** theo policy, không suy rằng group là mọi local role.
4. App tạo local account `PENDING` rồi link đúng `(issuer, subject)` sau khi nguồn được xác minh.
5. Provision memberships và grants đã được duyệt; đặt hiệu lực đúng thời gian, không cấp trước ngày bắt đầu nếu policy không cho.
6. Kiểm local `enabled`, roles, tenant, account ownership, MFA requirement và negative tests.
7. Chỉ chuyển `ACTIVE` sau khi audit/required services đều ready; không để status `ACTIVE` nhưng identity link sai.
8. Gửi thông báo onboarding không chứa temporary credentials trong email/chat không bảo mật; hướng dẫn sử dụng SSO.
9. Đặt chu kỳ review và auto-expiry cho contractor/time-bound grants.

### 5.4. Tách thời điểm account tồn tại và thời điểm có quyền

Một người có thể có directory object và SCIM User record **trước** ngày bắt đầu, nhưng chưa được phép truy cập dữ liệu. Vì vậy:

```text
T-7 ngày: HR đã duyệt hợp đồng, App account PENDING
T-2 ngày: SCIM User được tạo với active=false hoặc app status PENDING
T0:       Manager+IAM approval, MFA readiness; app account ACTIVE
T0+:      Tenant memberships + roles hiệu lực đúng scope
T+n:      Role expiry/review theo chính sách
```

Đây là **ví dụ vận hành**, không phải hành vi mặc định của SCIM hay Spring Security. Thuộc tính SCIM `active` có nghĩa trạng thái user ở SCIM resource; ứng dụng phải thực sự ánh xạ nó sang **deny policy** thì mới có hiệu lực bảo mật.

## 6. Mover – đổi vai trò mà không tích lũy quyền cũ

Chuyển nhóm là một **thay đổi policy**, không chỉ cập nhật tên phòng ban trong HR.

Giả sử account `acct-1007` chuyển từ tenant Sales sang Finance:

| Trước | Sau (đã duyệt) |
| --- | --- |
| `tenant-sales: REPORT_READ` | Thu hồi quyền Sales |
| `tenant-sales: CUSTOMER_EXPORT` | Thu hồi export Sales |
| Không có Finance membership | Thêm `tenant-finance` membership |
| Không có Finance grants | Cấp `REPORT_READ` của Finance |
| Không có `PAYMENT_APPROVE` | Vẫn không có nếu chưa được duyệt |

Nếu ứng dụng chỉ thêm Finance mà giữ `CUSTOMER_EXPORT` của Sales, user có thể truy cập dữ liệu hai bộ phận dù không còn nhu cầu.

### 6.1. Quy trình mover an toàn

1. Phát hiện event thay đổi role/team/tenant/manager từ nguồn có thẩm quyền.
2. Lấy **snapshot grants hiện tại** và **target grants đã phê duyệt**, tính `toRemove = old - new` và `toAdd = new - old`.
3. Kiểm **SoD**, tenant separation, admin privileges, grant expiry và owner approvals cho target.
4. Áp dụng thay đổi nhất quán theo transaction/revision. Với role nguy hiểm, **revoke old privileges trước** hoặc áp deny tạm thời trong khi provisioning chưa hoàn tất.
5. Đồng bộ Directory/SCIM Group memberships và local app grants. Với event không atomic xuyên hệ thống, có audit/correlation ID, retry và **deny tại app** nếu tạm thời không xác định quyền.
6. Thu hồi hoặc làm mới sessions/tokens giữ authorities cũ. Kiểm role changes có hiệu lực ở **request tiếp** theo yêu cầu thời gian.
7. Test người dùng có quyền mới đúng và **không còn quyền cũ**. Hai kiểm tra là bắt buộc.
8. Lưu effective date, previous/target grants, approver, revision và rollback policy.

### 6.2. Separation of Duties (SoD)

Ví dụ ứng dụng tài chính không cho cùng một người vừa `PAYMENT_CREATE` vừa `PAYMENT_APPROVE` trên cùng phạm vi. Quy tắc này phải áp với **tổng quyền hiệu lực** sau mọi group mappings, direct grants, inherited roles và temporary elevations.

```text
oldGrants = {PAYMENT_CREATE}
requested = {PAYMENT_APPROVE}

if allowed to remove PAYMENT_CREATE first:
    target = {PAYMENT_APPROVE}
else if both would remain:
    SoD conflict -> DENY / require exception process
```

**Không chỉ kiểm tên role.** Một user có thể được `PAYMENT_APPROVE` qua group A và `PAYMENT_CREATE` qua group B; phải expand permissions để tìm conflict. Với break-glass exception, cần approval, thời hạn ngắn, logging, monitoring và post-review.

### 6.3. Temporary role elevation

Một grant tạm thời cho hỗ trợ khẩn nên có:

- Account ID/tenant/resource rõ ràng.
- Permission tối thiểu và thời hạn kết thúc.
- Reason/ticket, approver độc lập, change record.
- MFA/step-up authentication nếu policy yêu cầu.
- Job tự thu hồi khi hết hạn, recheck ở authorization layer.
- Revocation/cancel sớm và session/token implications.
- Audit cả success và denied attempts.

Không cung cấp role `SUPER_ADMIN` vô thời hạn như cách dễ nhất để “người mới làm được việc”.

## 7. Leaver – ngừng quyền truy cập, không chỉ tắt một tài khoản

### 7.1. Có kế hoạch và khẩn cấp

**Offboarding có kế hoạch:** hợp đồng có ngày kết thúc; trước cutoff chuẩn bị hệ thống, xác nhận owner, chuyển dữ liệu hợp pháp, revoke grants đúng thời điểm và báo cáo hoàn tất.

**Emergency suspension:** nghi ngờ account compromise, insider threat, partner trust lost hoặc kỷ luật. Ưu tiên **chặn access ngay** bằng central deny/revocation, không chờ SCIM queue, directory replication hoặc JWT hết hạn.

Hai luồng khác nhau ở thời gian xử lý/approval, nhưng cùng yêu cầu xóa quyền **ở tất cả bề mặt có hiệu lực**.

### 7.2. Offboarding checklist theo thứ tự

1. Nhận tín hiệu leaver đã được xác minh từ HR/SOC/partner owner.
2. Xác định đúng `internalAccountId`, external identities, tenant memberships và application sessions; **không tìm bằng email duy nhất**.
3. Ghi `DISABLED`/`SUSPENDED` tại local authorization store hoặc central deny gate **trước/đồng thời** gửi sự kiện xuống hệ phụ thuộc; tăng account revision.
4. Disable Directory/IdP credentials/login hoặc revoke federated access theo policy.
5. SCIM cập nhật `User.active=false` (nếu app có SCIM) và bỏ `Groups.members`/local grants phù hợp; kiểm kết quả ack.
6. Thu hồi app `HttpSession` trên mọi node, refresh tokens/grants, API keys, personal access tokens, remember-me cookies và các tokens khác thuộc phạm vi account.
7. Đánh giá **access tokens đã cấp**: self-contained JWT có thể còn hợp lệ tới `exp` nếu resource server chỉ kiểm chữ ký/expiry; cần deny/introspection/token version hoặc TTL theo risk policy.
8. Đối với SAML2/CAS/OIDC SSO, phối hợp IdP logout/revocation; **không giả định** một logout callback luôn đến tất cả SPs và xóa mọi session.
9. Thu hồi roles/tenant memberships, privileged/delegated grants, service accounts/tokens thuộc user, quyền chia sẻ và app-specific workflows.
10. Xử lý transfer ownership của công việc/dữ liệu theo chính sách. Không xóa audit/legal retention tùy tiện.
11. Kiểm negative tests: fresh login fail, existing cookie fail, API token fail, direct app endpoint fail và admin actions fail.
12. Ghi rõ mỗi hệ đã ACK hay chưa, mốc cutoff, người duyệt, sự kiện còn retry và trách nhiệm reconcile.

### 7.3. Bề mặt truy cập cần xem xét

| Bề mặt | Có tự bị thu hồi khi disable AD/IdP? | Cách xử lý |
| --- | --- | --- |
| SSO login mới | Tùy issuer/session/policy | Disable account/trust, kiểm fresh login |
| Spring `HttpSession` đã authenticated | **Không mặc nhiên** | Session index, invalidate/delete/deny + kiểm request mới |
| Spring Security `Authentication` authorities trong session | Không tự refresh | Revoke session hoặc authz version/current-state check |
| OAuth2/OIDC access token dạng JWT | Không tự hết hiệu lực sớm | Short TTL, token status/deny, resource-server current-state policy |
| Refresh token | Tùy issuer/AS policy | Revoke ở authorization server và app token grants |
| CAS/SAML SP session | Không bảo đảm | SLO integration + local session revoke |
| API key / PAT | Không | Revoke in app/secret store |
| Service account do user sở hữu | Không | Review ownership, credentials, delegation |
| LDAP/AD group membership | Có thể được đồng bộ nhưng có delay | Reconcile group & app permissions |
| SCIM User/Group resource | Chỉ theo flow provisioning | PATCH/DELETE/ack và app enforcement |
| Background jobs/WebSockets | Không nhất thiết | Interrupt/reauthorize/connection revoke theo risk |
| Data đã export/download | Không thể “thu hồi” tự động | DLP/legal/audit/process, không hứa cơ chế web giải được |

### 7.4. Không nhầm “không cho login mới” với “không còn truy cập”

Nếu web app lưu quyền vào session lúc 09:00 và HR disable user 09:05, người dùng có thể tiếp tục request 09:06 nếu chỉ dựa vào `session.isAuthenticated` và authorities snapshot.

Một thiết kế nhạy cảm nên kiểm:

```text
authenticated identity
    AND localAccount.status == ACTIVE
    AND tenantMembership.status == ACTIVE
    AND permission currently effective
    AND session/token not revoked
    AND (MFA freshness if policy demands)
```

**Nguồn sự thật authorization** phải có hiệu lực trong toàn cụm (DB/cache version/central policy). Nếu authorization backend outage, hành động nhạy cảm cần **fail closed**, không “tạm cho admin vì đang bảo trì”.

## 8. SCIM 2.0: cơ chế provisioning User và Group

**SCIM** – System for Cross-domain Identity Management – chuẩn hóa các API quản trị identity giữa hệ provisioning client và service provider. Hai chuẩn cốt lõi:

- **RFC 7643:** mô hình dữ liệu `User`, `Group` và thuộc tính (`id`, `externalId`, `userName`, `active`, `members`...).
- **RFC 7644:** HTTP protocol cho `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, filtering, bulk và ETag/version khi hỗ trợ.

**SCIM không phải giao thức đăng nhập browser**. Một `PATCH /Users/{id} active=false` không tự phát logout event cho mọi Spring `HttpSession`, JWT và services. Đích SCIM phải kết nối thay đổi account state tới **authorization/session revocation**.

### 8.1. SCIM `id`, `externalId` và `userName`

| Trường | Ai cấp? | Phạm vi / lưu ý |
| --- | --- | --- |
| `id` | SCIM service provider (app/server nhận provisioning) | Opaque, ổn định, không tái sử dụng; không do client tự chọn trong resource create |
| `externalId` | Provisioning client (IGA/IdP) | Tùy chọn, nằm trong **namespace provisioning domain**, không được mặc định unique toàn thế giới |
| `userName` | SCIM User attribute từ provisioning data | Bắt buộc theo core schema, có thể đổi theo chính sách; không dùng thay immutable ID |
| `active` | Trạng thái hành chính của user | Cần ánh xạ cẩn thận vào local login/authorization deny |
| `groups` | Liên quan group membership | SCIM `groups` trên User thường read-only, membership được quản qua `Group.members` |
| `meta.version` / ETag | SCIM provider khi hỗ trợ versioning | Dùng để tránh lost updates, không thay audit source revision |
| `members` | Danh sách User/Group member refs | Có thể tạo grants gián tiếp qua approved group mapping |

Không tự dùng `externalId="E-103"` làm khóa lookup duy nhất trên nhiều tenants/provisioning domains. Nên có `(provisioningDomain, externalId)` và link sang internalAccountId.

### 8.2. Tạo tài khoản SCIM

Ví dụ request **chỉ dành cho một SCIM endpoint đã bảo vệ**:

```http
POST /scim/v2/Users HTTP/1.1
Host: portal.example.org
Content-Type: application/scim+json
Authorization: Bearer REDACTED_PROVISIONING_TOKEN
```

Body:

```json
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:User"
  ],
  "externalId": "hr:E-103",
  "userName": "a.nguyen@example.org",
  "active": false,
  "name": {
    "givenName": "An",
    "familyName": "Nguyen"
  }
}
```

Lựa chọn `active=false` là **chính sách pre-provision** trong ví dụ: account đã tồn tại nhưng chưa đủ điều kiện truy cập. RFC không bắt mọi tổ chức phải provision inactive trước start date.

SCIM Server trả ID do nó cấp, ví dụ `id="2819c223-7f76-453a-919d-413861904646"`, cùng metadata nếu hỗ trợ. Caller lưu mapping để cập nhật đúng user sau này.

**Authentication của provisioning endpoint:** phải dùng OAuth2 client credentials/scoped token, mTLS hoặc cơ chế machine-to-machine được tổ chức duyệt; không cho browser user tùy ý gọi POST SCIM để tạo account admin. Bảo vệ scopes, rate limits, request sizes, audit và tenant isolation.

### 8.3. Kích hoạt hoặc vô hiệu User qua PATCH

Khi đã duyệt Joiner, ví dụ SCIM PATCH:

```http
PATCH /scim/v2/Users/2819c223-7f76-453a-919d-413861904646 HTTP/1.1
Host: portal.example.org
Content-Type: application/scim+json
Authorization: Bearer REDACTED_PROVISIONING_TOKEN
If-Match: W/"revision-12"
```

Body:

```json
{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:PatchOp"
  ],
  "Operations": [
    {
      "op": "replace",
      "path": "active",
      "value": true
    }
  ]
}
```

Khi leaver:

```json
{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:PatchOp"
  ],
  "Operations": [
    {
      "op": "replace",
      "path": "active",
      "value": false
    }
  ]
}
```

**Các lưu ý không được bỏ:**

- `If-Match` là **tùy chọn của client khi server hỗ trợ resource versioning/ETag**; không coi mọi SCIM server đều bắt buộc cung cấp nó.
- `W/"revision-12"` là **giá trị ví dụ**. Khi dùng thật phải lấy ETag từ response trước đó, không tự bịa revision của server.
- PATCH SCIM là **atomic trên resource được PATCH** theo RFC 7644; **không** cung cấp transaction nguyên tử bao trùm nhiều User/Group resources, app session store và IdP.
- 200/204 thể hiện thao tác SCIM đã hoàn thành ở mức service provider; **không tự là bằng chứng** mọi bearer token và sessions đã bị thu hồi.
- `active=false` chỉ thực sự ngăn truy cập nếu app authorization/login enforcement liên kết trạng thái này với account state.
- Đừng dùng `DELETE` như giải pháp mặc định cho leaver nếu cần giữ lịch sử/audit/account ownership theo policy. Có thể deprovision/disable và tuân thủ retention/erasure đã được phê duyệt.

### 8.4. Thêm/xóa Group member

Ví dụ thêm User ID vào Group theo `Group.members`:

```json
{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:PatchOp"
  ],
  "Operations": [
    {
      "op": "add",
      "path": "members",
      "value": [
        {
          "value": "2819c223-7f76-453a-919d-413861904646"
        }
      ]
    }
  ]
}
```

Để thu hồi membership khi chuyển vai trò/leaver:

```json
{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:PatchOp"
  ],
  "Operations": [
    {
      "op": "remove",
      "path": "members[value eq \"2819c223-7f76-453a-919d-413861904646\"]"
    }
  ]
}
```

Các body trên dùng với `PATCH /scim/v2/Groups/{groupId}` đã xác thực. **Thành viên group không tự luôn là Spring role**: app phải có mapping `(approvedGroupId, tenant, policyVersion) → permission`. Tránh map trực tiếp từ group display name.

Một event “move from Sales to Finance” thường cần **ít nhất hai hành động**: xóa Sales membership/grants và thêm Finance membership/grants, có kiểm SoD và policy xử lý trạng thái trung gian. Nếu có nguy cơ đồng thời sở hữu hai quyền xung đột, đặt deny gate trong khi workflow chưa kết thúc.

### 8.5. ETag, concurrent updates và idempotency

Theo RFC 7644, nếu server hỗ trợ versioning, client có thể gửi `If-Match` để yêu cầu update chỉ khi revision hiện hành vẫn khớp. Nếu nhận conflict/precondition failure, workflow cần **đọc revision mới, đối chiếu và quyết định cập nhật lại**, không retry mù một body có thể ghi đè thay đổi mới.

Các rủi ro:

- Hai provisioning workers cùng thay group members.
- Joiner event trễ tới sau leaver event.
- PATCH một resource thành công nhưng request timeout trước khi nhận HTTP response.
- SCIM POST lặp tạo duplicate account nếu không có idempotency/mapping check.
- Một tenant khác cố dùng `externalId` tương tự để sửa sai user.

Cần `eventId`/source revision, uniqueness constraint, upsert có điều kiện, đối chiếu trạng thái, retry có giới hạn và error queue; **không dựa duy nhất vào HTTP client retries** để đảm bảo một event chỉ có hiệu lực đúng một lần.

## 9. LDAP/Active Directory: tài khoản và role có thể đến từ đâu?

Spring Security có thể xác thực trực tiếp bằng LDAP/AD, hoặc dùng IdP federation đứng trước LDAP/AD. Hai kiến trúc có **cùng nhu cầu lifecycle** nhưng khác điểm lấy authority.

| Kiến trúc | Authentication | Authority loading |
| --- | --- | --- |
| LDAP bind login | Spring Security `LdapAuthenticator`/LDAP bind | `LdapAuthoritiesPopulator` hoặc local DB service |
| AD authentication | AD credentials/ticket/LDAP tùy design | AD groups và app-approved mapping |
| OIDC login từ IdP kết nối AD | Spring Security `oauth2Login`/OIDC | `OidcUserService`/`GrantedAuthoritiesMapper`, local account service |
| SAML2 login từ enterprise IdP | `Saml2AuthenticationProvider` và assertion checks | Mapping authenticated SAML principal/groups sang local permissions |
| CAS login từ LDAP-backed CAS Server | CAS ticket validator → CAS Authentication | Local `UserDetailsService`/approved role mapping |
| Preauthenticated reverse proxy | Proxy verifies identity | `PreAuthenticatedAuthenticationProvider` → internal account/UserDetailsService |

### 9.1. LdapAuthoritiesPopulator làm gì?

Spring Security LDAP hỗ trợ `LdapAuthoritiesPopulator` để tìm `GrantedAuthority` dựa trên directory entry và groups. Trong tình huống app cần quyền nội bộ riêng:

- Có thể viết custom `LdapAuthoritiesPopulator` dùng DAO/JDBC để tải authorized roles thay vì chuyển mọi LDAP group thành Spring role.
- Cần làm rõ user key: directory object ID/full DN/realm và account ID; không tự query `WHERE username = ?` bằng display name/short name nếu có cross-directory collisions.
- Roles được load lúc authentication có thể **cũ ở session** sau khi directory group thay đổi.
- Một user mất AD group không tự bị logout khỏi mọi app nếu `HttpSession` và resource-server JWT vẫn hiệu lực.
- Một AD group lớn/nested groups có thể có đặc thù paging/recursive lookup; cần test theo directory provider và chống role explosion.

### 9.2. Cấu hình xác thực khác với tính hiệu lực của grants

Nếu dùng OIDC federation, Spring Security hỗ trợ `GrantedAuthoritiesMapper` và delegation-based `OidcUserService` để ánh xạ authorities tại **login time**. Một mapping ở login time không tự cập nhật session khi manager bỏ group sau đó.

Nếu dùng LDAP, `DefaultLdapAuthoritiesPopulator` tìm group theo filter; role mapping/SoD vẫn cần business policy. **Không thể thay tất cả yêu cầu JML bằng một câu “cứ đồng bộ AD groups là đủ”.**

## 10. Spring Security 6: enforcement ở request và method boundary

Bài này không tự tạo IdP hay SCIM Server hoàn chỉnh. Đoạn dưới tập trung vào **ứng dụng Portal đã cấu hình OIDC federation** và đọc local account grants khi cần.

### 10.1. Dependencies

Trong dự án Spring Boot 3/Java 17 đã có Boot plugin và dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

**Điều kiện để chạy OIDC thật:** ứng dụng phải có `ClientRegistration`/provider metadata, redirect URI, client credentials qua secret manager, HTTPS callback và issuer trust configuration đúng. Không cho client tự đặt issuer/JWKS URL để thành trusted IdP.

### 10.2. SecurityFilterChain và method security

Tệp `src/main/java/com/example/lifecycle/WebSecurityConfig.java`:

```java
package com.example.lifecycle;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/", "/error").permitAll()
                    .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .build();
    }
}
```

**Không disable CSRF toàn cục cho browser app.** Nếu cung cấp SCIM provisioning endpoints, đặt chúng ở **security chain riêng** có machine-to-machine authentication, scopes/mTLS, request validation và audit; không cho client OIDC browser `ROLE_USER` gọi SCIM mutate APIs.

### 10.3. Tệp `AccountAuthorizationPolicy.java`: lookup quyền hiện hành

Ví dụ **in-memory fixture** giúp nhìn rõ ranh giới, không thay DB trong production:

```java
package com.example.lifecycle;

import java.util.Map;
import java.util.Set;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.stereotype.Component;

@Component("accountPolicy")
public final class AccountAuthorizationPolicy {
    private record ExternalKey(String issuer, String subject) {}
    private record LocalAccount(
            String internalId, boolean active,
            Map<String, Set<String>> tenantGrants) {}

    // DEMO ONLY: production phải dùng DB/permission service,
    // có version, event updates và transaction consistency.
    private final Map<ExternalKey, LocalAccount> accounts = Map.of(
        new ExternalKey("https://idp.example.org/realms/company", "sub-alice"),
        new LocalAccount("acct-1007", true,
            Map.of("tenant-finance", Set.of("REPORT_READ"))),
        new ExternalKey("https://idp.example.org/realms/company", "sub-bob"),
        new LocalAccount("acct-2004", false,
            Map.of("tenant-finance", Set.of("REPORT_READ")))
    );

    public boolean canRead(
            Authentication authentication, String tenantId) {
        if (authentication == null || !authentication.isAuthenticated()
                || !(authentication.getPrincipal() instanceof OidcUser user)) {
            return false;
        }

        String issuer = user.getIdToken().getIssuer().toString();
        String subject = user.getIdToken().getSubject();
        LocalAccount local = accounts.get(new ExternalKey(issuer, subject));

        return local != null
                && local.active()
                && local.tenantGrants()
                        .getOrDefault(tenantId, Set.of())
                        .contains("REPORT_READ");
    }
}
```

**Giải thích:**

- Spring Security xác thực OIDC login với IdP đã cấu hình và tạo `OidcUser`. Code trên **không tự xác minh ID token từ browser body**; nó chỉ sử dụng principal mà security filter chain đã xác thực.
- Cặp `issuer + subject` dùng làm identity key; `email` hoặc `preferred_username` không đủ.
- Local account **không ACTIVE** thì `canRead` trả false dù user có OIDC SSO session.
- Grant phải đúng `tenantId` và permission. User không được tự chọn một tenant khác và dùng `REPORT_READ` của tenant cũ.
- Trong production, map phải thay bằng **authoritative DB/policy store** được cập nhật bởi JML workflow; cache nếu có phải có TTL/invalidation và deny gate.
- Một account disabled có thể vẫn còn OIDC session cũ. Method policy đọc current state giúp chặn action ngay khi local data đã cập nhật; session/token revocation vẫn phải làm riêng theo yêu cầu.
- Đây là policy cho một action; các permissions khác cần method guard/attribute-based checks tương ứng.
- Không gọi `OidcUser.getIdToken().getSubject()` với principal đến từ SAML/CAS/Kerberos rồi cast bừa; cần adapter identity type riêng cho mỗi federation mechanism.

### 10.4. Tệp `ReportService.java`: quyền gắn với tenant

```java
package com.example.lifecycle;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @PreAuthorize("@accountPolicy.canRead(authentication, #p0)")
    public String readReport(String tenantId) {
        return "Report for " + tenantId;
    }
}
```

Tệp `AppController.java`:

```java
package com.example.lifecycle;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AppController {
    private final ReportService reports;

    public AppController(ReportService reports) {
        this.reports = reports;
    }

    @GetMapping("/")
    public String publicHome() {
        return "Portal";
    }

    @GetMapping("/tenants/{tenantId}/reports")
    public String report(@PathVariable String tenantId) {
        return reports.readReport(tenantId);
    }
}
```

**Behavior có điều kiện:**

- OIDC user `sub-alice` từ đúng issuer, tenant `tenant-finance` → có thể nhận `Report for tenant-finance`.
- Cùng user hỏi `/tenants/tenant-sales/reports` → 403.
- OIDC user `sub-bob` đang disabled → 403 kể cả ID token hợp lệ.
- Anonymous vào route protected → Spring Security yêu cầu login.
- Các kết quả trên cần IdP/OIDC client configuration đúng, một Spring Boot main class và các beans đã nêu. **Đây là mã Spring Boot cần dự án/dependencies**, không phải một file Java thuần tự chạy với `javac`.

### 10.5. Cách đưa JML vào local account service

`AccountAuthorizationPolicy` in-memory chỉ là tài liệu học tập. Production nên có:

- Identity link repository unique trên `(issuer, subject)`.
- Account status và revision (ACTIVE/DISABLED).
- Tenant membership + role/permission grant repository có validFrom/validUntil.
- Một **trusted lifecycle processor** nhận SCIM/IGA events đã xác thực, validate approvals, ghi DB transaction và tăng revision.
- Event/outbox để revoke sessions và invalidate permission cache.
- Authorization guard đọc trạng thái **có hiệu lực** trên request nhạy cảm; không chỉ copy authorities một lần lúc login.
- Session index theo account ID hoặc token version cho emergency revoke.
- Retry/reconciliation và audit khi downstream provisioning cập nhật chưa thành công.

**Không đưa `@PostMapping("/users/{id}/disable")` public không xác thực** vào ứng dụng. Endpoints thay đổi lifecycle phải dùng machine-to-machine identity, scopes/roles chuyên biệt, signed/audited events, rate limiting và SoD approval.

## 11. Java 17+ độc lập: mô phỏng event JML, revision và offboarding

Chương trình sau **chạy độc lập bằng JDK 17+**, không dùng Spring, DB, CAS, SAML hoặc OIDC. Nó minh họa **state machine**, explicit approvals, không dùng role default, duplicate events, stale event và ngừng quyền. Không phải production provisioning engine; caller `approved=true` trong demo là fixture, **không chứng minh chữ ký/approval**.

Tệp `UserLifecycleDemo.java`:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public final class UserLifecycleDemo {
    enum State { ACTIVE, DISABLED }
    enum Kind { CREATE, GRANT, REVOKE, DISABLE, REACTIVATE }

    record Event(
            String id,
            String accountId,
            long revision,
            Kind kind,
            String permission,
            boolean approved) {}

    record Account(
            long revision,
            State state,
            Set<String> permissions) {}

    static final class Registry {
        private final Map<String, Account> accounts = new HashMap<>();
        private final Set<String> appliedEvents = new HashSet<>();

        String apply(Event event) {
            if (appliedEvents.contains(event.id())) {
                return "DUPLICATE";
            }

            Account before = accounts.get(event.accountId());
            if (before != null
                    && event.revision() <= before.revision()) {
                return "STALE";
            }

            if (before == null) {
                if (event.kind() != Kind.CREATE || !event.approved()) {
                    return "DENIED";
                }
                accounts.put(event.accountId(),
                        new Account(event.revision(),
                                State.ACTIVE, Set.of()));
                appliedEvents.add(event.id());
                return "CREATED";
            }

            Account after;
            String outcome;
            switch (event.kind()) {
                case CREATE -> {
                    return "DENIED";
                }
                case GRANT -> {
                    if (!event.approved()
                            || before.state() != State.ACTIVE
                            || event.permission() == null
                            || event.permission().isBlank()) {
                        return "DENIED";
                    }
                    Set<String> roles =
                            new HashSet<>(before.permissions());
                    roles.add(event.permission());
                    after = new Account(event.revision(),
                            State.ACTIVE, Set.copyOf(roles));
                    outcome = "GRANTED";
                }
                case REVOKE -> {
                    Set<String> roles =
                            new HashSet<>(before.permissions());
                    roles.remove(event.permission());
                    after = new Account(event.revision(),
                            before.state(), Set.copyOf(roles));
                    outcome = "REVOKED";
                }
                case DISABLE -> {
                    after = new Account(event.revision(),
                            State.DISABLED, Set.of());
                    outcome = "DISABLED";
                }
                case REACTIVATE -> {
                    if (!event.approved()) {
                        return "DENIED";
                    }
                    // Rehire không tự khôi phục grants trước khi nghỉ.
                    after = new Account(event.revision(),
                            State.ACTIVE, Set.of());
                    outcome = "REACTIVATED";
                }
                default -> throw new IllegalStateException(
                        "Unknown event");
            }

            accounts.put(event.accountId(), after);
            appliedEvents.add(event.id());
            return outcome;
        }

        boolean can(String accountId, String permission) {
            Account a = accounts.get(accountId);
            return a != null
                    && a.state() == State.ACTIVE
                    && a.permissions().contains(permission);
        }
    }

    public static void main(String[] args) {
        Registry r = new Registry();
        String id = "acct-7";

        System.out.println(r.apply(new Event(
                "e1", id, 1, Kind.CREATE, "", true)));
        System.out.println(r.apply(new Event(
                "e2", id, 2, Kind.GRANT, "REPORT_READ", true)));
        System.out.println("Read before mover: "
                + r.can(id, "REPORT_READ"));

        System.out.println(r.apply(new Event(
                "e3", id, 3, Kind.REVOKE, "REPORT_READ", true)));
        System.out.println("Read after revoke: "
                + r.can(id, "REPORT_READ"));
        System.out.println(r.apply(new Event(
                "e4", id, 4, Kind.GRANT, "REPORT_EXPORT", true)));

        System.out.println(r.apply(new Event(
                "e5", id, 5, Kind.DISABLE, "", true)));
        System.out.println("Export after disable: "
                + r.can(id, "REPORT_EXPORT"));
        System.out.println(r.apply(new Event(
                "e4", id, 4, Kind.GRANT, "REPORT_EXPORT", true)));
        System.out.println(r.apply(new Event(
                "e6", id, 6, Kind.GRANT, "TENANT_ADMIN", true)));
        System.out.println(r.apply(new Event(
                "e7", id, 3, Kind.REVOKE, "REPORT_EXPORT", true)));
        System.out.println(r.apply(new Event(
                "e8", id, 7, Kind.REACTIVATE, "", false)));
        System.out.println(r.apply(new Event(
                "e9", id, 8, Kind.REACTIVATE, "", true)));
        System.out.println("Old role after rehire: "
                + r.can(id, "REPORT_EXPORT"));
    }
}
```

Biên dịch và chạy:

```bash
javac UserLifecycleDemo.java
java UserLifecycleDemo
```

**Stdout chính xác:**

```text
CREATED
GRANTED
Read before mover: true
REVOKED
Read after revoke: false
GRANTED
DISABLED
Export after disable: false
DUPLICATE
DENIED
STALE
DENIED
REACTIVATED
Old role after rehire: false
```

**Đọc kết quả:**

- `CREATE` có approval và revision 1 tạo account ACTIVE nhưng **không có role nào**.
- `GRANT REPORT_READ` được phép khi active; mover thu hồi nó bằng `REVOKE` trước khi cấp `REPORT_EXPORT`.
- `DISABLE` đặt trạng thái DISABLED **và xóa tất cả permissions** trong mô hình demo.
- Event ID `e4` lặp bị chặn là `DUPLICATE`.
- Event `e6` có revision mới nhưng cố cấp `TENANT_ADMIN` khi account DISABLED → `DENIED`, không tái kích hoạt.
- Event `e7` có revision 3 đến muộn sau revision 5 → `STALE`, không ghi đè state.
- Rehire không có approval → `DENIED`; rehire có approval → ACTIVE **với tập grants rỗng**, phải xin cấp lại quyền.
- Không dùng `approved` boolean từ một public JSON payload thật làm nguồn phê duyệt. Production phải kiểm signer/service identity, workflow state, approver và source revision trong DB.
- `HashMap`/`HashSet` không thread-safe; ứng dụng nhiều nodes cần DB transaction/optimistic locking và event idempotency persisted. Không chạy demo này như user management service thật.
- Program không thể thu hồi `HttpSession`/JWT/SCIM groups; đó là các integration riêng.

### 11.1. Giới hạn của revision đơn

Một dòng `Account.revision` trong demo thể hiện một source stream đã **được sắp xếp chung**. Hệ thật có thể nhận events từ HR, IGA, SCIM và app admin, mỗi hệ dùng sequence khác nhau. **Không so revision 42 của HR với revision 12 của SCIM rồi tự kết luận hệ nào mới hơn.**

Production có thể dùng:

- `sourceSystem` + `sourceRevision` cho ordering trong từng nguồn.
- Một canonical `accountRevision` trong DB sau khi policy engine hợp nhất.
- Priority rõ cho **DISABLED / security deny** so với sự kiện cấp quyền chậm.
- Event IDs và inbox deduplication persisted.
- Outbox để gửi revocation sau DB transaction.
- Reconciliation định kỳ để sửa missed events.

**Một leaver đã DISABLED không được tự ACTIVE lại vì một delayed joiner provisioning event** dù timestamp trông mới. Rehire là transition đặc biệt có owner approval, không được suy từ event login.

## 12. Sự kiện bất đồng bộ, idempotency và nhất quán

### 12.1. Một thay đổi có thể đi qua nhiều hàng đợi

```mermaid
sequenceDiagram
    participant HR as HR/IGA
    participant Q as Event Bus
    participant DB as App Account DB
    participant R as Revocation Service
    participant S as Session/Token Store
    participant API as Protected API
    HR->>Q: account DISABLED rev 55
    Q->>DB: Delivery 1
    DB->>DB: Transaction: status disabled + version 55
    DB->>R: Outbox revoke sessions/tokens
    R->>S: Delete/deny active sessions
    R-->>DB: ACK or retry result
    Q->>DB: Duplicate delivery rev 55
    DB-->>Q: Idempotent no-op
    Q->>DB: Late role grant rev 54
    DB-->>Q: Reject stale/blocked
    API->>DB: Current account status?
    DB-->>API: DISABLED
    API-->>API: Deny even if old token present
```

**At-least-once delivery** là lựa chọn thông dụng; đừng giả định event chỉ đến một lần hay theo thứ tự. Nếu một role grant đến sau disable, hệ thống cần áp rule không re-enable/không cấp quyền cho account disabled.

### 12.2. Thiết kế inbox/outbox

**Inbox** ở account service:
- `eventId` unique (dedup).
- Source/tenant/account scope, source revision và event type.
- Validation signature/mTLS/authenticated caller và approved workflow.
- Apply in transaction, optimistic lock.
- Ghi outcome `APPLIED`, `DUPLICATE`, `STALE`, `DENIED` hoặc `RETRYABLE_ERROR`.

**Outbox** cùng transaction với account change:
- Event `ACCOUNT_DISABLED`/`ROLE_REVOKED` với accountId + revision.
- Downstream consumers thu hồi app sessions, caches, refresh grants, API tokens.
- Retry với backoff và dead-letter/alert khi không ACK.
- Cần tránh phát external notification trước khi DB transaction commit, nếu không downstream thấy state không nhất quán.

**Tính nguyên tử:** DB transaction bảo đảm nội bộ account+outbox, nhưng không làm SCIM service, Redis session store và IdP revoke thành **một** transaction phân tán tự động. Cần quản lý tiến độ từng destination và quy tắc fail closed.

### 12.3. Event ordering và precedence

| Chuỗi sự kiện | Hành vi an toàn |
| --- | --- |
| Create rev1 → Grant rev2 | Tạo account, cấp role đã duyệt |
| Grant rev2 đến trước Create rev1 | Không auto-create role; retry/quarantine theo ordering contract |
| Disable rev5 → Grant rev4 đến muộn | Reject stale grant |
| Disable rev5 → Grant rev6 | **Reject** nếu account disabled, dù revision lớn hơn |
| Duplicate Disable rev5 | Idempotent; không phát spam side effects không giới hạn |
| Rehire rev8 có approval | Có thể ACTIVE lại theo policy, **không hồi sinh grants cũ** |
| Role expiry trong khi user có JWT | Authorization deny/current-state/version check hoặc revoke token theo SLA |
| SCIM Group update thành công nhưng app cache cũ | Invalidate/revision update; test actual resource access |
| Một target system không trả ACK | Không báo global complete; retry/alert |
| HR leaver nhưng IGA vẫn có pending joiner ticket | Hold/deny pending grants theo lifecycle precedence |

### 12.4. Reconciliation không thay thế immediate deny

Hàng đợi có thể thất lạc hoặc consumer có bug. Reconciliation nên:
1. Đọc desired state từ HR/IGA policy và actual state của Directory/SCIM/apps.
2. So theo stable account/tenant IDs, không dò bằng email.
3. Tìm discrepancies: account đáng lẽ disabled vẫn active, role orphan, grant expired còn hiệu lực, user bị missing mapping.
4. Phát corrective events/requests có revision và audit, không overwrite mù.
5. Với mismatch có nguy cơ truy cập trái phép, áp **deny ngay** thay vì chờ batch đêm.
6. Cung cấp metrics/SLA theo từng hệ đích và outcome.

**Không bao giờ lấy current state của một app đã compromise làm “nguồn thật” để sửa ngược HR/IGA**. Chọn source-of-truth theo loại thuộc tính.

## 13. Phiên đăng nhập, tokens và thời điểm quyền có hiệu lực

### 13.1. Những gì Spring Security lưu khi login

Spring Security đặt `Authentication` vào `SecurityContext`. Trong browser app stateful, nó có thể được lưu vào `HttpSession` qua `SecurityContextRepository`. Authorities trong token thường phản ánh quyền **ở thời điểm xác thực**, không tự làm mới khi role table thay đổi.

Với Spring Security 6, custom authentication filter/controller có trách nhiệm persist context đúng. Nhưng **save session không tự đặt cơ chế revocation**.

```text
09:00 Login / OIDC, Authentication authorities = [REPORT_READ]
09:05 IAM revokes REPORT_READ
09:06 Browser sends JSESSIONID
       If app trusts stale authorities only -> may still allow
       If app checks current local grants/revision -> deny
```

### 13.2. Các chiến lược permission freshness

| Chiến lược | Lợi ích | Giới hạn |
| --- | --- | --- |
| Load permissions khi login | Nhanh sau login | Roles stale trong session |
| Load permissions mỗi request | Cập nhật gần request time | Tốn DB/network, cần caching/fail policy |
| Read fresh permissions ở method nhạy cảm | Kiểm action ở business boundary | Phải áp đồng nhất mọi routes/resources |
| Account authorization revision/epoch | Phát hiện rights changed nhanh | Cần shared store/invalidation |
| Revoke all account sessions khi mover/leaver | Hạn chế stale app sessions | Cần session index + coverage mọi nodes |
| Short-lived access token + refresh checks | Giảm cửa sổ stale JWT | Không thu hồi tức thì trước `exp` nếu thiếu deny |
| Token introspection/revocation | Có thể kiểm active status tập trung | Độ trễ/availability và token type hỗ trợ |
| IdP/SSO logout | Chấm dứt SSO session | Không bảo đảm app sessions/tokens đã bị xóa |

**Bài học cốt lõi:** thời hạn “quyền thay đổi có hiệu lực” là **SLA an ninh**, không chỉ latency đồng bộ directory. Quyền `TENANT_ADMIN` bị revoke cần chặn nhanh hơn một preference UI vừa thay đổi.

### 13.3. OIDC, SAML2 và CAS có logout khác nhau

- **OIDC/OAuth2:** authorization server có thể hỗ trợ refresh token revocation/end-session/back-channel logout tùy profile; access token JWT ở resource server có thể còn tới expiry. Spring `oauth2Login`/session và resource-server bearer auth là hai layers khác nhau.
- **SAML2:** Single Logout chỉ hoạt động nếu hai bên hỗ trợ/config/test; IdP logout không mặc nhiên invalidate mọi SP sessions.
- **CAS:** CAS Single Logout callback cần tìm đúng app session theo ticket/SessionIndex; khi nhiều nodes, mapping in-memory có thể không đủ, phải kiểm cluster.
- **Kerberos:** TGT/OS ticket cache và app `HttpSession` không cùng vòng đời; disable AD chưa chắc hủy app session.
- **Reverse-proxy preauth:** proxy có thể xóa SSO cookie, nhưng app origin/session vẫn có thể sống nếu không gate mọi request hoặc revoke.

**Không nhầm “user đã logout khỏi IdP” với “mọi hành động trên Portal bị chặn tức thời”.** Kiểm enforcement tại app/resource server.

### 13.4. Revocation trong môi trường nhiều node

Nếu app có nhiều pods:

- Session store cần shared (Spring Session Redis/JDBC) hoặc phải có cluster-aware revocation.
- Có thể dùng session index theo `internalAccountId`, với namespace theo app/tenant.
- Mọi node phải tra cùng status/revision deny gate; không một pod giữ quyền cũ lâu hơn SLA.
- Cache invalidation phải xác nhận, không chỉ publish event rồi tin “đã xong”.
- JWT access token đã phát là vấn đề riêng với HttpSession; xóa Redis session **không làm JWT tự mất hiệu lực**.
- WebSocket/batch jobs/long-running requests có thể đã nạp authentication trước lúc bị revoke; cần policy xử lý active operations nếu rủi ro cao.
- Monitor session_delete_failure, authz_cache_stale, downstream_unacknowledged, request_after_disable và token_replay signals.

## 14. Least privilege, SoD và phê duyệt

### 14.1. Không được xem role của IdP là role của app

Ví dụ IdP assertion có `groups=["Admins"]`. Không viết:

```java
// ANTI-PATTERN: group display name từ bên ngoài thành admin.
if (claims.toString().contains("Admins")) {
    granted.add(new SimpleGrantedAuthority("ROLE_ADMIN"));
}
```

Cách đúng là mapping explicit:

```text
trusted issuer + immutable group object ID + tenant
      -> approved mapping policy/version
      -> local permission / role
      -> expiration / request approval
```

Các group names có thể trùng giữa tenants và IdPs; khi admin privilege được tạo bởi một external claim, phải thẩm định nguồn claim, group membership, issuer/audience và business owner.

### 14.2. Quyền cao cần phê duyệt kép

Một số grants nên yêu cầu:
- Manager/resource owner.
- Security/IAM owner hoặc người có quyền approve riêng.
- SoD policy validation trên **tổng effective permissions**.
- Time-bound activation, revocation workflow và recertification.
- Không để requester tự approve grant của chính mình.
- Audit đầy đủ ai yêu cầu, duyệt, thực hiện và đã kiểm nghiệm.

Break-glass access cần quy trình khẩn có mục tiêu, MFA, session monitoring, expiry rất ngắn và post-incident review; không tái sử dụng để vượt quy trình thông thường hằng ngày.

### 14.3. Đánh giá hiệu lực grants trong một request

Một guard logic thực tế:

```text
allow(subject, tenantId, resourceId, action, atTime):
    verified = request.Authentication from trusted mechanism
    local = identityLink(verified.issuer, verified.subject)
    require local.account.status == ACTIVE
    require local.account NOT IN revoked/disabled list
    require valid tenantMembership(local.account, tenantId, atTime)
    require grantAllows(local.account, tenantId, action, resourceId, atTime)
    require separationOfDutiesSatisfied(local.account, action)
    require MFA freshness for high-risk action if policy requires
    return ALLOW
otherwise DENY
```

Đây là **pseudocode policy**, không phải built-in Spring Security API. `@PreAuthorize` hoặc `AuthorizationManager` có thể gọi internal service để làm các bước tương ứng. Không chỉ kiểm một `ROLE_USER` để cho truy cập mọi tenant.

## 15. Khả năng phục hồi, lỗi provisioning và audit

### 15.1. Mỗi hệ đích có thể thất bại độc lập

| Tình huống | Rủi ro | Cách xử lý |
| --- | --- | --- |
| HR tạo Joiner nhưng IdP create thất bại | App account có thể orphan hoặc start date lệch | Chưa ACTIVE, retry có idempotency |
| Directory create OK nhưng SCIM POST timeout | Duplicate app users nếu retry tạo bừa | Lưu externalId/client event ID, GET/reconcile trước create lại |
| Role grant event lặp | Quyền/các side effects tăng bất thường | Idempotent event ID + DB unique constraints |
| Leaver event trễ | User truy cập sau cutoff | Local deny gate ngay, ưu tiên security revoke |
| Mover remove role A fail, add B pass | User có quyền A+B xung đột | SoD deny/intermediate inactive state, retry remove |
| SCIM User.active=false OK, Group remove fail | Quyền group vẫn được tính ở app nếu không kiểm active | App kiểm disabled status trước mọi grants |
| Session deletion fail | Stale authenticated sessions | Retry/backoff/alert, authz deny current state |
| Cache invalidation miss ở một node | Node tiếp tục cho role đã revoke | Revision check/readiness/force refresh |
| Account link theo email sau IdP migration | Account takeover/tenant mix-up | Proof-based link, immutable IDs, collision checks |
| IAM/DB outage lúc truy cập admin action | Không kiểm được quyền hiện hành | Fail closed, không cho admin chỉ nhờ stale cache |
| CAS/SAML SLO callback bị thất lạc | SP app session vẫn active | Local session index/revoke, không chỉ tin IdP logout |

### 15.2. Những gì phải audit

- Lifecycle event ID, source, account ID, tenant, prior/current state, revision.
- Requester, approver(s), effective date, lý do nghiệp vụ/incident ở mức cần thiết.
- Granted/revoked permission IDs, resource scope, expiry, role policy version.
- SCIM resource IDs/ETag outcomes, downstream statuses, retry attempts.
- Session/token revoke acknowledgments và mốc negative tests.
- Deny reasons an toàn, không lộ existence của other users ở public API.
- Reconciliation findings, exception approvals và post-mortem.
- **Không log** password, refresh tokens, raw SAMLResponse, ID/access tokens, CAS ST, `JSESSIONID`, private group membership không cần thiết hay PII vượt retention policy.

### 15.3. Tính riêng tư và xóa dữ liệu

Khi leaver, đôi khi cần giữ audit/tài liệu công việc theo retention và legal hold; đôi khi phải xóa/anonymize các dữ liệu cá nhân không còn cần thiết. **Disable account và delete toàn bộ dữ liệu ngay** là hai quyết định riêng. Không xóa accountId/audit trước khi hoàn tất chuyển ownership, lưu trữ bắt buộc và đáp ứng luật/chính sách áp dụng.

## 16. Kiểm thử JML từ dữ liệu nguồn tới quyền thực tế

### 16.1. Ma trận chức năng và an ninh

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Joiner chưa approved | Không được ACTIVE hay có grants |
| Joiner approved, app user chưa provision | Không login app thành công bằng cách tự tạo account |
| Directory user active nhưng local account PENDING | Application deny |
| Provision duplicate `externalId` khác provisioning domain | Không gộp nhầm users |
| OIDC `sub` giống nhau từ hai issuers | Hai external identity keys khác nhau |
| Email giống account cũ | Không auto-link/cấp quyền cũ |
| User được cấp `REPORT_READ` tenant A | Truy cập report A nếu resource policy đạt |
| User A đổi URL sang tenant B | 403 nếu không có membership/grant B |
| Mover Sales→Finance | Quyền Sales bị gỡ, Finance đúng approved |
| Mover chỉ add Finance mà không remove Sales | Test phát hiện privilege creep |
| Mover vi phạm SoD | Reject/exception workflow, không auto-grant |
| SCIM PATCH User `active=false` | Local account disabled và request mới bị deny |
| SCIM Group member remove | Local group mapping/permissions cập nhật đúng |
| SCIM PATCH có stale ETag | Conflict/precondition, không silently overwrite |
| Delayed role grant sau Disable | Không tự tái kích hoạt user |
| Duplicate event ID | Idempotent, không tạo grant/subscription lặp |
| Rehire không approved | Remains disabled |
| Rehire approved | Không tự khôi phục grants trước offboarding |
| Local user disabled nhưng IdP vẫn login được | App 403/deny theo local policy |
| Session đã authenticated trước role revoke | Revoke/guard chặn hành động cũ theo SLA |
| JWT access token chưa hết hạn sau leaver | Resource-server deny hoặc policy window được xác định |
| SCIM server trả 200 nhưng session còn | Test **phát hiện** incomplete offboarding |
| One cluster node cache stale | Không bypass revocation, có alert/readiness |
| SCIM/DB IAM outage | Không tự cấp admin, retry/alert |
| Emergency suspension | Central deny có hiệu lực trước/đồng thời provisioning |
| Long-running/WebSocket action | Có handling theo risk policy |
| App local logout nhưng IdP session còn | SSO có thể login lại; access vẫn kiểm local status |
| No audit for high-risk admin change | Test/alert quy trình không đạt |

### 16.2. Kiểm theo ba tầng

**Tầng provisioning:** HR/IGA approvals, SCIM request, group memberships, account status và revision. Dùng staging identities, bảo vệ provisioning token.

**Tầng authentication:** OIDC/SAML/CAS/Kerberos/proxy identity được xác thực đúng issuer/subject, không tự link email. User disabled ở app phải bị từ chối dù authentication ở IdP có thể thành công.

**Tầng authorization/revocation:** mở tài nguyên bằng **existing session cookie và bearer tokens** đã cấp trước thay đổi. Đây là kiểm tra quan trọng nhất mà happy-path provisioning tests thường bỏ sót.

Không chỉ kiểm “SCIM PATCH trả 204” rồi đánh dấu leaver thành công nếu session app vẫn có thể truy cập.

### 16.3. Bộ kiểm thử hai request để phát hiện quyền cũ

1. Login user với grant `REPORT_EXPORT`, lưu browser cookie/app session và API access token (nếu hệ thống hỗ trợ).
2. Xác nhận export lúc còn approved hoạt động theo tenant policy.
3. Gửi event mover thu hồi `REPORT_EXPORT`, ghi revision và nhận downstream ACK.
4. Dùng **chính session cookie cũ** gửi request export một lần nữa.
5. Expected: 403/deny theo mục tiêu thời gian thu hồi; nếu 200, tìm stale authorities/caches.
6. Dùng access token cũ gửi request tới resource server, kiểm thiết kế revocation/TTL thật.
7. Gửi request read-only còn hợp lệ để tránh đánh đồng “revoke tất cả” với “chỉ revoke export”.
8. Lặp lại khi load balance tới node B, Redis cache stale và IGA event đến trễ.
9. Lặp lại với leaver: old cookie, old token, fresh login và direct-origin request đều phải bị chặn.
10. Ghi bằng chứng không có raw tokens trong logs/test report.

### 16.4. Kiểm thử mã Java 17

Chạy `UserLifecycleDemo.java` như mục 11 và đối chiếu chính xác stdout. Demo minh họa policies logic, **không thay test SCIM thật, OIDC IdP, LDAP/AD, Spring Session hay DB concurrency**.

### 16.5. Build Spring Boot examples

Trong dự án đã có Gradle wrapper:

```bash
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-security-oauth2-client
./gradlew compileJava
./gradlew test
```

Windows dùng `.\gradlew.bat`. Các ví dụ Spring code cần `PortalApplication` main class nếu muốn chạy ứng dụng web thật, OIDC ClientRegistration và issuer client credentials; build compile pass **không chứng minh** SCIM provisioning/IdP/logout end-to-end nếu thiếu hạ tầng đó.

## 17. Chẩn đoán theo symptom

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| User mới thấy ở AD nhưng Portal không login | App chưa provision/link/ACTIVE, issuer/subject sai | Kiểm identity links, SCIM ACK, state |
| User login OIDC nhưng 403 | Local account chưa approved hoặc thiếu grants/tenant | Kiểm local entitlements, không cấp admin vội |
| User đổi bộ phận vẫn xem dữ liệu cũ | Role cũ chưa revoke, session/cache stale | So desired vs effective grants, revoke/refresh |
| SCIM PATCH active=false trả 204 nhưng user vẫn truy cập | App chưa enforce disabled hoặc session JWT còn | Chặn local status, session/token revoke |
| SCIM PATCH Group.members trả 412 | ETag stale | Fetch latest ETag, reconcile, thử lại có điều kiện |
| SCIM POST retry tạo user trùng | Idempotency/mapping thiếu | Dedup event, externalId/domain, lookup+unique constraint |
| Account bị gộp vì email | Identity linking theo mutable email | Link issuer+stable subject, migration review |
| Spring `hasRole` không nhận role | Prefix `ROLE_`/authority naming mismatch | Kiểm `GrantedAuthority` và `hasRole` vs `hasAuthority` |
| Local grants đã revoke nhưng `@PreAuthorize` không chạy | Chưa `@EnableMethodSecurity`/self-invocation | Enable và gọi qua Spring-managed proxy |
| Một pod vẫn có admin rights | Cache/session/revision mismatch | Distributed invalidation, authorization recheck |
| JWT vẫn active sau disable | Resource server chỉ verify signature/exp | Revocation status/token version/introspection |
| Directory outage gây fail-open | Fallback “temporarily allow” | Fail closed với actions nhạy cảm, alert |
| Leaver rồi rehire tự có admin | Reuse old grants/auto-enable | Explicit approval, no grant resurrection |
| Role group name khác nhưng object ID giống | Display-name based mapping | Stable group object ID + tenant scope |
| SCIM delete làm mất audit/ownership | Sai retention policy | Disable và retention/transfer quy trình |
| Mover event của hệ A ghi đè leaver hệ B | Không có precedence/source revision | Canonical state machine, tombstone/deny |
| Login lại ngay sau local logout | IdP/CAS SSO session còn | Local deny/reauth policies, không nhầm logout tầng |
| Không chứng minh ai phê duyệt role | Thiếu approval/audit store | SoD, approval records, reconciliation |

## 18. Checklist vận hành

### Joiner

- [ ] Nguồn HR/owner đã xác minh identity và start date.
- [ ] Có immutable account reference; không auto-link email.
- [ ] Các issuer/subject và provisioning domains đã approved.
- [ ] Manager/IAM/Security approvals đầy đủ theo role risk.
- [ ] SoD/least privilege/MFA được kiểm.
- [ ] Tạo account PENDING, không tự ACTIVE trước cutoff/approval.
- [ ] SCIM/Directory updates có mapping ID, revision và ACK.
- [ ] Tenant membership/local grants đúng business need, có expiry/review.
- [ ] Test positive/negative login và resource authorization.
- [ ] Audit đầy đủ và có owner chịu trách nhiệm support.

### Mover

- [ ] Tính old/new role differences, gỡ quyền cũ.
- [ ] Kiểm SoD, tenant scopes và temporary elevation expiry.
- [ ] Events có revision/approval, không chấp nhận stale duplicates.
- [ ] Directory groups + SCIM groups + local grants đã đồng bộ.
- [ ] Session/permission cache được cập nhật hoặc revoke.
- [ ] User **không còn** quyền cũ qua old cookie/token.
- [ ] Có audit và rollback plan không khôi phục quyền trái phép.

### Leaver / Emergency suspend

- [ ] Account/local deny state được bật đúng cutoff.
- [ ] IdP/Directory login mới bị chặn hoặc trust đã thu hồi.
- [ ] SCIM active=false/group removal/local grants updated, mọi target ACK hoặc có retry/alert.
- [ ] App HttpSessions toàn cluster bị revoke/deny.
- [ ] Refresh tokens, API keys/PAT, self-contained JWT xử lý theo token policy.
- [ ] Privileged/delegated grants, WebSockets/jobs và service accounts liên quan được xem xét.
- [ ] Fresh login, old cookie, old bearer token, direct route đều qua negative tests.
- [ ] Audit, transfer ownership và data retention/erasure theo policy.
- [ ] Không tuyên bố DONE khi còn target system chưa ACK và old sessions chưa được kiểm.

## 19. Câu hỏi tự kiểm tra

**1. JML nghĩa là gì?**

Joiner là thêm người dùng, Mover là thay đổi vị trí/vai trò và Leaver là ngừng quan hệ/truy cập. Các quy trình đòi phối hợp HR/IGA, directory/IdP, provisioning, local grants và session/token revocation.

**2. Vì sao IdP đăng nhập thành công không đồng nghĩa user được dùng Portal?**

IdP xác thực identity. Portal phải có local account ACTIVE, identity link đúng, tenant membership, permission grant và session/token policy thỏa mãn.

**3. Khi tạo user bằng SCIM, `id` và `externalId` khác thế nào?**

`id` là ID do service provider cấp và duy trì ổn định; `externalId` do provisioning client đặt và scoped theo provisioning domain. Không gộp IDs từ nhiều nguồn chỉ vì string trùng.

**4. Vì sao không nên liên kết user theo email?**

Email có thể đổi, trùng hoặc tái sử dụng. Federation identity phải dựa trên issuer/realm cùng stable subject đã được xác minh.

**5. Vì sao Mover phải kiểm cả quyền bị gỡ, không chỉ quyền được thêm?**

Nếu không gỡ quyền cũ sẽ tích lũy privileges, có thể vi phạm least privilege, tenant isolation và Separation of Duties.

**6. SoD là gì?**

Separation of Duties ngăn một người đồng thời nắm các quyền xung đột (ví dụ tạo và tự duyệt thanh toán). Phải kiểm effective permissions, kể cả quyền thừa kế từ groups.

**7. SCIM `PATCH active=false` có tự logout user trên mọi ứng dụng không?**

Không. SCIM thay user resource tại service provider. App phải enforce account disabled và thu hồi/deny sessions, tokens và quyền theo thiết kế.

**8. Vì sao SCIM `PATCH` atomic không đủ cho toàn bộ offboarding?**

Nó atomic trên **một resource SCIM** theo RFC, không phải transaction nhiều hệ gồm IdP, groups, app DB, Redis sessions, JWT issuer và resource server.

**9. Nếu event Grant đến sau Disable với revision cao hơn, nên xử lý sao?**

Không cấp quyền nếu account DISABLED; việc reactivation phải qua workflow mới được approved, không để event grant tự hồi sinh account.

**10. Vì sao Spring `Authentication.getAuthorities()` có thể cũ?**

Authorities thường được tính ở login time rồi lưu trong `SecurityContext`/HttpSession. Khi quyền đổi, app cần refresh/recheck/revoke theo SLA.

**11. Vì sao xóa một HttpSession không thu hồi JWT access token?**

JWT có thể được resource server chấp nhận độc lập cho tới `exp` nếu chỉ kiểm chữ ký/expiry. Cần token status/introspection/version/deny hoặc short lifetime theo policy.

**12. SCIM Group.members có thể tự thành `ROLE_ADMIN` của Spring không?**

Không mặc nhiên. Cần explicit group object ID + issuer/tenant→permission mapping đã được phê duyệt và kiểm SoD.

**13. Rehire có nên phục hồi các grants cũ?**

Không mặc định. Tái kích hoạt cần xác minh identity, account ownership và approvals; quyền cũ có thể không còn phù hợp.

**14. SCIM PATCH nhận HTTP 204, liệu Leaver đã hoàn thành chưa?**

Chưa chắc. Cần xác nhận local deny, session/token revocation, group grants, toàn bộ downstream ACK và negative tests.

**15. Khi có nhiều provisioning sources, vì sao revision không thể so trực tiếp?**

Mỗi nguồn có sequence riêng. Cần source-specific ordering và canonical account revision/precedence do policy engine duy trì.

**16. Trong Spring Security, vai trò `@EnableMethodSecurity` là gì?**

Bật method authorization như `@PreAuthorize`. Chỉ cấu hình URL matcher trong `SecurityFilterChain` không tự bật mọi method security annotations.

**17. Tests nào quan trọng nhất sau khi revoke một role?**

Gửi lại request bằng **cookie/token đã được cấp trước khi revoke** và xác nhận action cũ bị chặn, kể cả khi route sang node khác.

**18. Nếu Directory/IGA không truy cập được trong khi có yêu cầu admin action, nên làm gì?**

Không tự cho phép dựa trên quyền admin cũ chưa chắc còn hiệu lực; áp dụng fail-closed hoặc policy outage được security duyệt, có logging/alert.

**19. Khi có contractor có end date, điều gì cần tự động?**

Grants/memberships có expiry, scheduled deprovisioning, session/token revoke, owner notification, audit và verification sau cutoff. Không chỉ dựa vào người quản lý nhớ gỡ bằng tay.

**20. Khi nào dùng emergency suspension thay planned offboarding?**

Khi có nghi vấn compromise/rủi ro cấp bách. Chặn app access/deny và thu hồi sessions trước, sau đó hoàn tất provisioning/reconciliation; không chờ queue bình thường để xử lý rủi ro cao.

## Ghi nhớ

**Quy trình Joiner–Mover–Leaver là vòng đời của trust và quyền, không chỉ là đồng bộ danh bạ.**

- **Joiner:** xác minh nguồn và person ID → approvals → directory/IdP identity → SCIM/app provision → identity link → least-privilege grants → ACTIVE và test.
- **Mover:** xác định target permissions → kiểm SoD → gỡ quyền cũ → cấp quyền mới đã duyệt → làm mới session/cache/tokens → test rằng quyền cũ không còn.
- **Leaver:** central deny/local account disable → chặn SSO login mới → SCIM/group/local grants revoke → hủy sessions/tokens trên mọi node → audit/reconcile và kiểm chứng bằng old credentials.

**Bốn ranh giới thiết yếu:** Authentication khác authorization; identity khác username/email; provisioning khác revocation; và một event/HTTP 200 khác kết quả quyền đã hết hiệu lực tại tài nguyên thật.

Với Spring Security, giữ **identity link bằng issuer + stable subject**, nạp quyền từ nguồn nội bộ có phê duyệt và bảo vệ ở request/method/resource boundary. **Không tin authorities cũ không giới hạn thời gian**, nhất là với admin và cross-tenant actions.

### Tài liệu tham khảo

- [RFC 7643 – SCIM Core Schema: User, Group, id, externalId, active](https://www.rfc-editor.org/rfc/rfc7643)
- [RFC 7644 – SCIM Protocol: PATCH, versioning, ETag, group membership](https://www.rfc-editor.org/rfc/rfc7644)
- [Spring Security – LDAP Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html)
- [Spring Security – OAuth2 Login Advanced: Mapping User Authorities](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html)
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security – Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security – Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html)
- [Spring Session – Reference](https://docs.spring.io/spring-session/reference/)
- [OWASP – Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
- [OWASP – Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
