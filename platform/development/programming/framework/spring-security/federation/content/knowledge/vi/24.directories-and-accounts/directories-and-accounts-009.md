# Thu hồi quyền, khóa tài khoản và vô hiệu hóa phiên đang tồn tại

> **Chủ đề:** Spring Security – federation. **Nhóm kiến thức:** Thư mục và tài khoản. Bài Knowledge này giải thích cách xử lý **thu hồi quyền (authorization revocation)**, **khóa/vô hiệu hóa tài khoản (account lock/disable)** và **chấm dứt phiên đăng nhập đã tồn tại (active session invalidation)** trong hệ thống Spring Security tích hợp LDAP/Active Directory và SAML, OIDC, CAS hoặc Kerberos. Điểm trọng tâm: ba thao tác này **không tương đương** và không tự lan truyền giữa directory, IdP, session store, API tokens và dữ liệu nghiệp vụ.

## 1. Mục tiêu học tập

Sau khi hoàn thành bài học, người học có thể:

1. Phân biệt “gỡ nhóm/role”, “khóa đăng nhập tạm thời”, “vô hiệu hóa account” và “thu hồi mọi phiên/tokens” theo đối tượng chịu tác động.
2. Hiểu tại sao một user đã bị disable trong LDAP/AD **vẫn có thể giữ HttpSession, JWT access token hoặc service ticket đã cấp**, nếu ứng dụng không có cơ chế kiểm lại hoặc thu hồi.
3. Xác định **nguồn sự thật** của user status, tenant membership, permissions, app sessions, SSO sessions, refresh tokens và access tokens.
4. Mô hình hóa security lifecycle như **trạng thái account + phiên bản policy + thời hạn + sự kiện thu hồi**; biết fail-closed khi kiểm tra không chắc chắn.
5. Cấu hình Spring Security để áp login-account checks và Spring Session Redis để **tìm/xóa các phiên theo principal**, kể cả triển khai nhiều pods.
6. Không nhầm `SessionRegistry.expireNow()` với xóa trực tiếp session khỏi datastore, và không nhầm `HttpSession.invalidate()` với remote logout trên tất cả ứng dụng.
7. So sánh cách thu hồi **server-side sessions**, **opaque tokens introspection**, **JWT self-contained**, **refresh tokens**, **OIDC Back-Channel Logout**, **SAML SLO**, **CAS logout** và **Kerberos tickets**.
8. Chống lỗi race condition khi vừa revoke vừa login/refresh token/cấp quyền hoặc khi phiên đang thực thi giao dịch nhiều bước.
9. Viết bài kiểm thử Java 17 chạy độc lập minh họa trạng thái account, giảm quyền, tăng authorization version và vô hiệu hóa các session.
10. Lập runbook cho tình huống nhân viên nghỉ việc, nghi ngờ bị lộ account, thu hồi quyền một tenant và buộc user xác thực lại.

**Kết luận xuyên suốt:** **Chặn đăng nhập mới ≠ chặn phiên cũ ≠ thu hồi mọi token ≠ lập tức mất quyền trên dữ liệu**. Hệ thống cần thực thi riêng từng cam kết bảo mật, ở đúng thành phần đang bảo vệ tài nguyên.

## 2. Bốn mục tiêu an ninh khác nhau

Giả sử `alice@corp.example` đang sử dụng ứng dụng quản lý tài chính:

| Hành động | Thay đổi gì? | Tác động mong muốn | Không tự bảo đảm |
| --- | --- | --- | --- |
| **Gỡ quyền `APPROVE_PAYMENT`** | Membership/permission ở hệ phân quyền | Alice không thể phê duyệt giao dịch mới | Đăng xuất khỏi tất cả app; khóa mật khẩu; vô hiệu hóa JWT cũ |
| **Khóa tài khoản (lock)** | `accountNonLocked=false` hoặc directory lockout | Không chấp nhận authentication mới khi lock còn hiệu lực | Session web hiện hữu sẽ bị hủy ngay |
| **Vô hiệu hóa tài khoản (disable)** | `enabled=false` hoặc AD account disabled | Ngăn account tiếp tục đăng nhập và sử dụng dịch vụ theo policy | Tất cả RPs tự động logout; issued access token hết hiệu lực ngay |
| **Vô hiệu hóa phiên đang tồn tại** | Xóa/expire `HttpSession`/session registry và/hoặc revoke token | Session ID cũ không được tiếp tục authentication | Directory account bị disable; quyền ở tenant khác thay đổi |
| **Thu hồi refresh token/grant** | Authorization Server từ chối đổi token mới | Client không tiếp tục xin access token mới từ grant đó | JWT access token đã phát bị RS tự kiểm thấy revoke |
| **Thu hồi access token** | Resource Server có cơ chế nhận diện revoked token | Token cụ thể không truy cập tài nguyên nữa | Mọi local web sessions/IdP sessions đều logout |
| **OIDC/SAML/CAS SSO logout** | IdP/OP/SP và các RPs phối hợp logout | Các phiên đăng nhập tham gia giao thức có thể bị kết thúc | Mọi RPs offline đều nhận, mọi JWT access token tự vô hiệu ngay |
| **Đóng local app session** | Xóa session của ứng dụng hiện tại | User không còn authenticated ở ứng dụng đó | Trình duyệt không còn TGT/TGC hoặc SSO session ở IdP |

**Ví dụ thực tế:** Admin gỡ role `ROLE_FINANCE_APPROVER` khỏi Directory ở 14:00, nhưng Alice đã login lúc 09:00 và `SecurityContext` của local session vẫn chứa authority cũ. Nếu controller chỉ dùng `@PreAuthorize("hasRole('FINANCE_APPROVER')")` dựa trên `GrantedAuthorities` cached từ 09:00, Alice **có thể tiếp tục phê duyệt** cho đến khi app làm mới authorities/invalidates session hoặc kiểm permission từ nguồn hiện hành.

**Chính sách tối thiểu đối với thao tác rủi ro cao:** Kiểm account còn active, membership và quyền trên **đúng tenant + resource + action tại thời điểm commit**. Session hoặc token hợp lệ là điều kiện cần, không phải đủ.

## 3. Ngữ nghĩa lifecycle tài khoản ở Directory

### 3.1. Ba trạng thái phổ biến không được gộp

| Trạng thái | Cách hiểu | Ví dụ |
| --- | --- | --- |
| **ACTIVE** | Account được phép đăng nhập theo chính sách | Nhân viên đang làm việc |
| **LOCKED** | Tạm ngăn xác thực, thường do số lần login sai/rủi ro | Khóa vì brute-force hoặc admin security action |
| **DISABLED** | Account bị vô hiệu hóa theo quy trình, có thể kéo dài | Nhân viên nghỉ việc/thu hồi hợp đồng |
| **EXPIRED** | Account hoặc credential hết thời hạn theo directory policy | Account contractor quá ngày hiệu lực |
| **DELETED** | Directory object bị xóa/đổi; lưu ý ID có thể bị tái sử dụng ở một số hệ thống | Offboarding, cleanup |
| **MISSING/UNKNOWN** | Không tìm thấy account hoặc source directory không đáng tin/cập nhật | Replication lag, outage, mapping sai |

Mỗi trạng thái dẫn đến policy khác:

- `LOCKED` do nhiều lần sai mật khẩu có thể được directory tự mở sau thời gian hoặc admin xác minh; không mặc định nó chính là `DISABLED`.
- `DISABLED` cần được phản ánh vào **nguồn kiểm quyền và session invalidation** của từng ứng dụng. Xóa LDAP user không đồng nghĩa lập tức hủy phiên local.
- `EXPIRED` có thể là account expiration hoặc password expiration; password hết hạn đôi khi cho phép quy trình đổi password theo quy định, nhưng không nên cấp quyền nhạy cảm như một phiên thông thường.
- `MISSING` không được coi là `ACTIVE` vì ứng dụng đã có một cached `UserDetails` từ trước.

### 3.2. Spring Security `UserDetails` checks

Spring Security `UserDetails` có các contract:

```java
boolean isEnabled();
boolean isAccountNonLocked();
boolean isAccountNonExpired();
boolean isCredentialsNonExpired();
```

Với authentication provider dựa trên `AbstractUserDetailsAuthenticationProvider` (ví dụ DAO provider), pre/post checks có thể từ chối account disabled, locked, expired hoặc credentials expired **khi authentication đang diễn ra**.

**Không suy rằng chúng sẽ được tự động gọi trên mỗi request** đã mang `JSESSIONID`: Spring Security có thể lấy `Authentication` đã lưu từ `SecurityContextRepository` và đi thẳng tới authorization, không login lại qua provider. Để đáp ứng “khóa ngay”, cần thêm **request-time account status enforcement**, event-driven invalidation hoặc cơ chế phiên bản policy.

### 3.3. Active Directory account disable và account lockout

Microsoft Active Directory có thuộc tính `userAccountControl` với cờ `ACCOUNTDISABLE` (bit `0x0002`). Một user account bình thường có thể có cờ `NORMAL_ACCOUNT` (bit `0x0200`); nhiều cờ được OR với nhau. Không viết logic “value == 514” cho mọi account vì cờ khác có thể cùng tồn tại.

Ví dụ **đọc hiểu**:

```text
userAccountControl = 512   (0x0200 NORMAL_ACCOUNT, chưa có disable)
userAccountControl = 514   (0x0202 = NORMAL_ACCOUNT | ACCOUNTDISABLE)
```

**Lưu ý:** Đây là ví dụ các tổ hợp thường gặp, **không phải lời khuyên set raw LDAP attribute trực tiếp**. Account lockout khác disable; trong AD hiện đại, trạng thái `LOCKOUT` và một số trạng thái password expiry được thể hiện bằng thuộc tính tính toán `msDS-User-Account-Control-Computed`, với dữ liệu lockout/time/policy tương ứng. `lockoutTime` có thể khác zero ngay cả khi khóa đã hết hạn; cần dùng directory API/trạng thái hiệu lực thay vì chỉ kiểm một attribute thô.

LDAP ngoài AD có schema/policy khác (ví dụ `pwdAccountLockedTime` trong password policy overlay), **không có cờ userAccountControl chuẩn chung cho mọi LDAP**. Dùng adapter phù hợp directory và hợp đồng policy của tổ chức, không copy điều kiện AD sang OpenLDAP rồi coi là đúng.

### 3.4. Thu hồi quyền Directory Group

Một user có thể thuộc:

```text
cn=Finance-Approvers,ou=Groups,dc=corp,dc=example
cn=Finance-Readers,ou=Groups,dc=corp,dc=example
```

Gỡ membership `Finance-Approvers` có thể làm quyền phê duyệt mất tại IdP/directory, nhưng ứng dụng cần xác định:

- Có group nesting/transitive membership không? `memberOf` trên AD/LDAP không tự thể hiện mọi nested groups trong mọi query/driver.
- Nhóm đã đồng bộ vào local DB, session hoặc JWT claims ở thời điểm nào?
- Identity Provider OIDC/SAML có phát group claim mới không, và RP có kiểm lại claim mới hay vẫn dùng session?
- Quyền có được cấp trực tiếp tại app bằng một role khác hoặc qua tenant-level grant không?
- User có tài khoản liên kết khác/other federation issuer để vào lại không?

Vì vậy một workflow thu hồi quyền phải tính **effective permissions**, không chỉ thao tác xóa một dòng membership ở Directory.

## 4. Các ranh giới giữa Directory, IdP, app session và API tokens

```text
                 Directory / Identity Source
              account status, groups, affiliations
                          |
              LDAP/AD sync or event
                          v
                 IdP / OP / CAS / KDC
           auth sessions, login policy, TGT/tokens
                 |              |
          SAML/OIDC/CAS       Kerberos
                 |              |
                 +-------+------+
                         v
              Spring Security Web App
               SecurityContext + HttpSession
                         |
             +-----------+------------+
             |                        |
           Spring Session        API Resource Server
           Redis/JDBC            JWT or opaque token
             |                        |
             +-----------+------------+
                         v
               Authoritative local
           account/tenant/permission policy
                         |
                         v
               Business data mutation
```

Từ sơ đồ, **bốn kho khác nhau** có thể cần thu hồi độc lập:

1. **Directory/account database**: trạng thái account, roles, membership, entitlements.
2. **IdP/OP**: SSO session, sign-in sessions, refresh tokens và federation credentials.
3. **Application web**: `HttpSession`/`SecurityContext`/remember-me cookies/Spring Session records.
4. **Resource Server và API**: access tokens/JWT, token introspection caches, API keys/service credentials.

**Chỉ khóa ở kho 1** không tự xóa kho 3/4. **Chỉ logout khỏi kho 3** không tự ngăn IdP tại kho 2 phát authorization code/token mới, nếu Directory chưa cập nhật hoặc OP vẫn có SSO session.

### 4.1. “Tính tức thời” cần định nghĩa được

Đừng viết policy mơ hồ “quyền bị thu hồi ngay” khi hệ thống có cache/event bus/distributed nodes. Cần một **revocation propagation SLA** rõ:

- `T0`: admin action được ghi thành công ở authoritative store.
- `T1`: event/outbox commit, các consumers nhận version mới.
- `T2`: web session store xóa sessions liên quan và cache permissions được invalidate.
- `T3`: IdP/grants/refresh tokens được revoke nếu policy yêu cầu.
- `T4`: mọi request/action mới của app/resource server bị chặn, **được xác nhận bằng test**.

Với nghiệp vụ nhạy cảm, mục tiêu thường là **không có action commit sau T0 với permission đã mất**, ngay cả khi event xóa session tới T2 chưa hoàn tất. Đạt điều này bằng authoritative authorization check, transaction semantics hoặc security epoch fence; không chỉ dựa vào eventual event delivery.

## 5. Vì sao khóa tài khoản không tự làm mất phiên cũ?

Một flow web điển hình:

```text
09:00 User login SAML/OIDC/LDAP
      -> Spring builds Authentication with ROLE_APPROVER
      -> Stores SecurityContext in HttpSession id S-123

14:00 Directory disables Alice
      -> New LDAP login may fail
      -> BUT session S-123 still exists in Redis

14:01 Browser sends Cookie: SESSION=S-123
      -> Spring loads old Authentication
      -> Controller checks cached ROLE_APPROVER
      -> Operation may still succeed unless extra enforcement exists
```

Các lý do:

- `SecurityContextRepository` có thể lưu `Authentication` ở session local; không tự đi LDAP mỗi lần.
- `UserDetails.isEnabled()` thường được provider kiểm khi login, **không tự được gọi lại** ở mỗi request đã có authenticated context.
- Session timeout không biết user bị disable ở Directory giữa chừng.
- Application có thể cache group membership, authority mapping hoặc token claim nhiều phút/giờ.
- Một JWT chứa scopes/roles tự mang (self-contained), còn ký và chưa hết hạn, vẫn verify chữ ký đúng; không có thông tin revocation mới nếu resource server không hỏi nguồn state.
- Với browser SSO, khi app session bị xóa nhưng IdP vẫn có SSO session, browser có thể ngay lập tức login lại mà không nhập mật khẩu; phải xử lý OP/IdP session theo policy.

**Sai:** “Đã disable user tại AD nên chắc mọi tab đang mở bị kick out.” **Đúng:** “Đã disable tại AD; hệ thống phải chứng minh các web sessions/tokens không còn được dùng để làm action bị cấm.”

## 6. Chọn chiến lược theo mức độ nguy cấp

Không có một biện pháp duy nhất phù hợp mọi hành động:

| Sự kiện | Phạm vi hợp lý | Cơ chế ưu tiên | Vì sao? |
| --- | --- | --- | --- |
| Gỡ quyền đọc 1 project | Project/resource | Kiểm quyền live + tăng entitlement version; invalidate cache | Không nhất thiết logout toàn bộ user |
| Gỡ `ROLE_APPROVER` ở tenant A | Tenant A | Kiểm DB policy ở commit + bump version, có thể revoke sessions liên quan | Không vô hiệu quyền hợp lệ tenant B |
| Account locked vì brute force | Account/login | Chặn login mới, đánh giá có cần hủy current sessions không | Lockout policy có thể chỉ nhắm credential attempts |
| Admin khóa account vì nghi lộ | Toàn account | Disable/lock, revoke tất cả local sessions, grants/tokens, OP session | Ưu tiên containment |
| Nhân viên nghỉ việc | Toàn tổ chức | Disable IdP/Directory, deprovision apps, revoke sessions/tokens/devices | Không cho tái đăng nhập qua federation |
| Thay email/display name | Hồ sơ | Update attributes, không tự logout trừ rủi ro | Không phải mọi thay đổi profile là security event |
| Đổi mật khẩu | Theo security policy | Có thể revoke refresh tokens/sessions khác, step-up | Phải có chính sách rõ, không tự assume |
| Phát hiện refresh token bị lộ | Client/grant/device hoặc toàn account theo risk | Revoke refresh token family/grant, resource token defense | Chặn token issuance tiếp |
| Phát hiện user vừa thực hiện action rủi ro | Giao dịch/session | Step-up + fresh auth và recheck permissions | Session còn tồn tại không chứng minh assurance đủ |

Phân biệt **“mọi phiên toàn account”** với **“một phiên thiết bị”**, **“các phiên của một RP”** và **“mọi phiên của một tenant”**. Một API quản lý phải chỉ rõ scope thay vì gọi chung `logoutUser()`.

## 7. Thiết kế trạng thái bảo mật authoritative và policy version

Đề xuất có một nguồn dữ liệu cấp ứng dụng (account-access service hoặc database transaction) xác định tình trạng hiệu lực và quyền:

```text
AccountAccessState
  accountKey           = immutable internal account ID
  sourceIdentity       = (issuer/realm, immutable external subject)
  enabled              = true | false
  accountNonLocked     = true | false
  accountExpired       = true | false
  entitlementVersion   = monotonic integer
  sessionsValidAfter   = timestamp or monotonically increasing epoch
  tenantMemberships    = tenantId -> role/permission set
  updatedAt            = UTC timestamp
  updatedBy            = authorized admin or source event
  reasonCode           = ROLE_REVOKED | LOCKED | DISABLED | INCIDENT
  policyVersion        = version of security rules
```

Một `SessionEvidence` hoặc authenticated principal nên giữ:

```text
sessionId            = opaque session key from server
accountKey           = stable local ID
federatedSource      = verified issuer/realm/registration
externalSubject      = verified sub/NameID/directory ID
authenticatedAt      = instant of authentication when available
entitlementVersion   = version at last trusted authorization refresh
sessionEpoch         = epoch when issued (not a mutable browser header)
tenantContext        = resolved and authorized tenant, not user-supplied grant
```

**Chính sách:**

1. Khi account bị `disabled`/`locked`, request mới phải bị từ chối theo active-state check.
2. Khi `entitlementVersion` tăng, session chứa authorities cũ **không được sử dụng để tiếp tục action nhạy cảm**; refresh authoritative permissions hoặc yêu cầu reauth/chặn cho tới đồng bộ.
3. Khi `sessionsValidAfter` tăng, mọi phiên có thời điểm/epoch cũ hơn bị coi là không hợp lệ dù Redis deletion event chưa chạy.
4. Một `tenantId` do browser gửi chỉ là **tenant intent**, không phải bằng chứng membership.
5. Khi nguồn state không truy cập được, policy fail-closed cho hành động nhạy cảm; có thể có chế độ read-only low-risk đã đánh giá, nhưng không tự dùng cached ADMIN để commit.
6. Không reset entitlementVersion về số nhỏ khi account được re-enable; dùng monotonic generation hoặc event ordering.
7. Định danh account và issuer phải ổn định; **email có thể đổi hoặc tái sử dụng**, không dùng làm khóa revoke chung cho các issuer.

### 7.1. Vì sao cần cả xóa session và kiểm epoch?

Chỉ xóa session trong Redis tạo ra một **cửa sổ đua**:

```text
T0: Request A đã load session vào JVM pod-1
T1: Admin revoke; worker xóa key session khỏi Redis
T2: Request A vẫn giữ Authentication cũ trong thread
T3: Request A commit nghiệp vụ
```

Nếu transaction ở T3 chỉ dựa trên authorities cached từ T0, người dùng vẫn làm xong action sau revoke. **Xóa Redis key không thể quay ngược một request đang chạy**. Vì vậy hành động có rủi ro cao cần kiểm entitlement version/state ở thời điểm business commit hoặc dưới transaction boundary đồng bộ với authority state.

Ngược lại, nếu chỉ dùng check version mà không xóa sessions, app có thể liên tục reject old contexts nhưng session rác vẫn tồn tại, nhớ các credentials/attributes không cần thiết và IdP có thể tái đăng nhập. Dùng **cả active enforcement và session cleanup**.

## 8. Workflow thu hồi quyền có tính tin cậy

### 8.1. Sự kiện admin được ghi ở authoritative store

```text
Admin (MFA + authorized) revokes role:
  target = acct-42, tenant-A, APPROVE_PAYMENT
                 |
                 v
Transaction:
  UPDATE entitlement / account access state
  INCREMENT entitlementVersion
  INSERT durable outbox security event
                 |
                 v
COMMIT (T0)
                 |
                 +--> API authorization checks current version
                 |
                 +--> Outbox worker publishes AccountAccessChanged
                                |
                 +--------------+----------------+
                 v              v                v
           Session Revoker   Token/Grant Revoker  Cache Invalidation
                 |              |                |
                 v              v                v
           Redis/DB session  OP authorization    permission caches
           index delete      server / IdP        at pods/APIs
                 |
                 v
          Readback/verification/audit
```

**Tính đúng về thứ tự:** Security event chỉ được phát **sau khi** authoritative transaction commit, bằng transactional outbox/durable queue, tránh tình trạng nhận “revoke” rồi DB rollback quyền vẫn tồn tại. Consumers phải idempotent, chấp nhận duplicate/out-of-order events bằng monotonic version. Không dùng fire-and-forget thread trong controller làm cách duy nhất thu hồi phiên.

### 8.2. Pseudocode transaction minh họa (không phải migration SQL hoàn chỉnh)

```sql
BEGIN;

UPDATE account_tenant_permissions
SET permission_granted = FALSE
WHERE account_id = :account_id
  AND tenant_id = :tenant_id
  AND permission_code = 'APPROVE_PAYMENT';

UPDATE account_access_state
SET entitlement_version = entitlement_version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE account_id = :account_id;

INSERT INTO security_outbox
    (event_id, event_type, account_id, tenant_id,
     reason_code, occurred_at)
VALUES
    (:event_id, 'ENTITLEMENT_REVOKED', :account_id,
     :tenant_id, 'ADMIN_REVOKE', CURRENT_TIMESTAMP);

COMMIT;
```

Đây là **pseudocode SQL**: tên bảng/column, duplicate suppression, version handling và transaction isolation phụ thuộc hệ quản trị CSDL. Production phải kiểm số hàng UPDATE, idempotency key, đối tượng/tenant có tồn tại, admin authorization và audit. Không cho user gửi raw SQL hoặc tự đặt event reason để thu hồi người khác.

### 8.3. “Role removed” có thể không cần logout toàn hệ thống

Nếu user chỉ mất quyền `APPROVE_PAYMENT` ở tenant A, có thể tiếp tục đọc báo cáo ở tenant B theo chính sách. Hướng ưu tiên:

- Ghi quyền đã mất ở authoritative store.
- Tăng `entitlementVersion` và clear cached permissions.
- Mọi action protected kiểm effective authorization mới.
- Nếu app chỉ tin role snapshot trong `Authentication` và chưa có live authorization, **bắt buộc invalidate sessions hoặc regenerate authentication** để tránh grant cũ.
- Nếu có nghi vấn lộ account, incident policy có thể revoke **mọi** sessions/tokens cho an toàn.

Tách scope chính xác giúp giảm tác động vận hành nhưng không được giữ quyền đã bị thu hồi.

## 9. Spring Security: session, SecurityContext và login checks

### 9.1. Những thành phần cần biết

| Thành phần | Chức năng | Hạn chế với revocation |
| --- | --- | --- |
| `AuthenticationProvider` | Xác minh credentials khi đăng nhập | Không tự kiểm directory mỗi request |
| `UserDetails` | `enabled/locked/expired` và authorities | Cached Authentication có thể mang trạng thái cũ |
| `SecurityContextHolder` | Authentication trong request thread | Clear context hiện tại không xóa mọi sessions |
| `SecurityContextRepository` | Lưu/đọc context qua requests | Không tự cập nhật quyền Directory |
| `HttpSession` | Phiên browser của app | `invalidate()` chỉ tác động phiên được gọi, không mọi device |
| `SessionRegistry` | Theo dõi phiên trong Spring Security | Tùy implementation, có thể chỉ ở JVM |
| `SessionInformation.expireNow()` | Mark session expired | Thường được `ConcurrentSessionFilter` áp dụng ở request sau, **không phải xóa Redis key tức thì** |
| `Spring Session` | Dùng Redis/JDBC/khác để lưu session | Cần index đúng principal để tìm theo user |
| `FindByIndexNameSessionRepository` | API tìm sessions theo principal index | Nếu không có index/sai principal, kết quả rỗng dù sessions tồn tại |
| `AuthorizationManager` / `@PreAuthorize` | Kiểm permissions | Nếu chỉ dùng cached `GrantedAuthorities`, vẫn có thể bị stale |

### 9.2. Local logout không phải global revocation

```java
// Đây là Spring Security DSL (fragment), không phải app hoàn chỉnh.
http.logout(logout -> logout
    .logoutUrl("/logout")
    .invalidateHttpSession(true)
    .clearAuthentication(true));
```

Thông thường, khi user thực hiện logout trên một browser session, Spring loại `Authentication` và hủy local `HttpSession`. Nhưng:

- Đây không phải lệnh revoke mọi sessions của user trên mọi thiết bị.
- Không mặc nhiên xóa SSO session ở IdP, CAS TGT hoặc AD/KDC tickets.
- Không tự revoke refresh tokens hoặc issued JWT access tokens ở Authorization Server.
- Với CSRF enabled, local logout nên dùng **POST có CSRF token** để tránh logout CSRF.
- Bị xóa session không có nghĩa browser không lập session mới nhờ IdP SSO còn sống.

## 10. Spring Session Redis: xóa các phiên theo principal trong cluster

Với ứng dụng server-side Spring Security có nhiều pods, **Spring Session Redis Indexed** là một lựa chọn để các pods cùng thấy phiên. Chức năng xóa sessions phải gắn với **principal name đang được Spring Session thực sự index**.

### 10.1. Dependency và Redis configuration

Trong project Spring Boot 3.x/Java 17, có parent/BOM phù hợp, thêm fragment `pom.xml`:

```xml
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
    <groupId>org.springframework.session</groupId>
    <artifactId>spring-session-data-redis</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
  </dependency>
</dependencies>
```

Mẫu `src/main/resources/application.yml`:

```yaml
spring:
  data:
    redis:
      host: redis.internal.example.org
      port: 6379
      ssl:
        enabled: true
  session:
    timeout: 30m
    redis:
      repository-type: indexed
      namespace: "security:portal:sessions"

server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
```

**Đây là ví dụ topology**, phải thay DNS/credentials/secret manager và bảo vệ Redis qua TLS, auth, ACL, network policy. `repository-type: indexed` chọn `RedisIndexedSessionRepository` (cần kiểm Spring Boot/Spring Session version), thay cho repository Redis cơ bản vốn **không** hỗ trợ tìm session theo principal một cách tự nhiên. Namespace tách sessions giữa nhiều app dùng cùng Redis.

Nếu chỉ dùng `RedisSessionRepository` (default trong một số Spring Boot config) hoặc custom store không có principal index, `FindByIndexNameSessionRepository` có thể không được cung cấp. **Đừng ép kiểu/fallback quét Redis `KEYS *`** trong production để tự tìm sessions vì tốn tài nguyên, dễ đụng dữ liệu ứng dụng khác và không an toàn.

### 10.2. Xác định giá trị principal đúng

Spring Session có chỉ mục `FindByIndexNameSessionRepository.PRINCIPAL_NAME_INDEX_NAME`. Nó có thể xác định principal từ `SPRING_SECURITY_CONTEXT` của session nếu integration/indexing được cấu hình đúng; Spring Session API cũng cho phép quản lý index data rõ ràng theo chiến lược của app.

**Rủi ro phổ biến:** Từ OIDC, `Authentication#getName()` có thể là `sub` chứ không phải local `accountId`. Từ SAML nó có thể là NameID; từ LDAP username có thể là `sAMAccountName`. Hai issuer khác nhau có thể cấp cùng `sub` hoặc cùng `alice`. Vì vậy:

- Xác định **đúng index value thực tế** từ những sessions được Spring Session lưu.
- Ưu tiên đặt principal name đã được map thành **internal stable account key** trong `Authentication` cho ứng dụng đó, hoặc duy trì mapping session index riêng bằng accountKey.
- Nếu auth principal vẫn là external name, tra mapping **issuer+subject→accountKey** đã xác minh rồi tìm đúng index values; không bao giờ xóa sessions của user khác trùng email.
- Nếu cần revoke theo tenant, phải có custom session index/metadata và xác minh scope, hoặc revoke account sessions rộng hơn với policy rõ; không giả định `findByPrincipalName` đã phân biệt tenant.

**Kiểm thử bắt buộc:** Login bằng hai browser, kiểm lookup trả đúng hai session IDs cho principal test; kiểm logout một browser không xóa của user khác; kiểm revoke across pods.

### 10.3. Service xóa sessions bằng index, Java 17+ Spring

File `src/main/java/com/example/security/AccountSessionRevoker.java`:

```java
package com.example.security;

import java.util.Map;

import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;
import org.springframework.stereotype.Service;

@Service
public final class AccountSessionRevoker {

    private final FindByIndexNameSessionRepository<? extends Session> sessions;

    public AccountSessionRevoker(
            FindByIndexNameSessionRepository<? extends Session> sessions) {
        this.sessions = sessions;
    }

    /**
     * principalIndexValue là giá trị principal được lưu THỰC SỰ
     * trong Spring Session index, không phải raw email từ browser.
     *
     * Chỉ gọi sau khi security-admin authorization và
     * accountKey -> principalIndexValue đã được xác minh.
     */
    public int deleteAllIndexedSessions(String principalIndexValue) {
        if (principalIndexValue == null ||
                principalIndexValue.isBlank()) {
            throw new IllegalArgumentException(
                "A verified principal index value is required");
        }

        Map<String, ? extends Session> found =
            sessions.findByPrincipalName(principalIndexValue);

        for (String sessionId : found.keySet()) {
            sessions.deleteById(sessionId);
        }
        return found.size();
    }
}
```

Cần Spring Session indexed repository bean thực sự. `deleteById` xóa session record; session cookies cũ có thể còn trên browser nhưng **không còn tìm thấy session hợp lệ** ở shared store. API phía browser sẽ thấy unauthenticated/401 hoặc redirect login tùy cấu hình ứng dụng.

**Các giới hạn bắt buộc:**

1. Số trả về là số session IDs **tìm thấy trong lần snapshot**, không phải chứng chỉ tất cả sessions/tokens trên toàn hệ thống đã revoke.
2. Nếu principal index bị thiếu/sai, map rỗng không chứng minh user không có phiên.
3. Nếu user đồng thời tạo session mới, lookup rồi delete có race. **Đặt authoritative revoked/disabled flag hoặc tăng security epoch trước**, chặn new auth/session reuse và dùng cleanup làm bước thứ hai.
4. Nếu một request đã load context trước khi `deleteById`, nó có thể tiếp tục cho tới trước lần kiểm policy tiếp theo; cần fence ở business action.
5. Với Redis Cluster, Spring Session tài liệu lưu ý session indexes/cleanup events có các trường hợp liên quan keyspace events và cluster node; kiểm version/topology chứ không coi index luôn hoàn hảo.
6. Nếu `RedisIndexedSessionRepository` dùng TTL thấp hoặc session vừa expired, map snapshot và số thực tế có thể khác; test semantics/idempotency.
7. Không expose method này thành `GET /admin/revoke?principal=...` cho browser tùy ý. Admin API phải có phishing-resistant MFA, scope authorization, CSRF/anti-replay, audit và verification.
8. Không xóa sessions của các RPs/apps khác bằng cách chạy `FLUSHDB`/wildcard delete; dùng namespace/index của app.
9. Nếu app có WebSocket/scheduled jobs giữ identity hoặc offline tokens, xóa web session **không** đóng chúng tự động; cần control plane riêng.
10. Nếu event retry, `deleteById` không nên gây cấp lại quyền; thao tác revoke phải idempotent và trạng thái account là source of truth.

### 10.4. Ví dụ SecurityFilterChain cho session web

File `src/main/java/com/example/security/WebSecurityConfig.java`:

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain web(
            HttpSecurity http,
            AccountAccessLookup accountAccess) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutUrl("/logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true));

        // Kiểm account status SAU các authentication filters,
        // TRƯỚC AuthorizationFilter. Không thay authorization
        // tenant/resource và không phải credential validation.
        http.addFilterBefore(
            new AccountStatusFilter(accountAccess),
            AuthorizationFilter.class);

        return http.build();
    }
}
```

**Đây là cấu hình minh họa cho login web**. Cần provider/UserDetailsService thật, session persistence, CSRF/HTTPS, Redis và implement `AccountAccessLookup` được bảo vệ; không phải một ứng dụng hoàn chỉnh tự chạy chỉ bằng class này. Với federation `oauth2Login`, `saml2Login` hoặc CAS/SPNEGO, thay nguồn authentication theo hệ thống, **không** tự cho rằng `formLogin` là bắt buộc trong SSO.

## 11. Chặn session cũ khi account bị khóa: check trên từng request

Việc xóa session sau event là cần, nhưng trong cửa sổ propagation, một **account-status gate** ở request path giúp ngăn user disabled tiếp tục hoạt động.

### 11.1. Contract lookup authoritative

File `src/main/java/com/example/security/AccountAccessLookup.java`:

```java
package com.example.security;

public interface AccountAccessLookup {

    /**
     * Trả true CHỈ KHI account được phép dùng app.
     * Fail-closed khi user không tồn tại, locked, disabled
     * hoặc authoritative state không thể xác minh.
     *
     * accountKey phải là stable internal ID của Authentication;
     * không dùng header / email browser chưa được xác minh.
     */
    boolean isActive(String accountKey);
}
```

Một production implementation có thể đọc account-access DB có cache TTL ngắn và event invalidation đã kiểm thử, hoặc một dedicated authorization service. Đối với tác vụ rủi ro cao, phải kiểm quyền ở transaction boundary; chỉ `isActive` là chưa đủ để biết action/tenant entitlement.

### 11.2. Filter chỉ xử lý trạng thái account, không tự phong quyền

File `src/main/java/com/example/security/AccountStatusFilter.java`:

```java
package com.example.security;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public final class AccountStatusFilter extends OncePerRequestFilter {

    private final AccountAccessLookup accounts;

    public AccountStatusFilter(AccountAccessLookup accounts) {
        this.accounts = accounts;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        boolean userAuthenticated = authentication != null
            && authentication.isAuthenticated()
            && !(authentication instanceof AnonymousAuthenticationToken);

        if (userAuthenticated) {
            // Chỉ đúng khi Authentication#getName() đã là
            // stable internal account key trong hệ thống này.
            String accountKey = authentication.getName();

            if (!accounts.isActive(accountKey)) {
                SecurityContextHolder.clearContext();

                HttpSession session = request.getSession(false);
                if (session != null) {
                    session.invalidate();
                }

                response.sendError(
                    HttpServletResponse.SC_UNAUTHORIZED,
                    "Authentication no longer valid");
                return;
            }
        }

        chain.doFilter(request, response);
    }
}
```

**Hạn chế/cảnh báo:**

- `Authentication#getName()` **không mặc định là internal account ID** với OIDC/SAML. Trước khi dùng, auth mapper phải chuyển external identity `(issuer,sub)` hoặc qualified NameID thành stable local ID, hoặc filter phải dùng principal adapter được kiểm chứng.
- `isActive` nên fail closed nếu directory/account state unavailable theo chính sách; phương thức trả boolean demo che việc phân biệt database outage, account missing, lock hay disable, nên production có typed decision/audit.
- Filter được tạo trong `SecurityFilterChain`, **không** đánh dấu `@Component` khi không muốn Spring Boot auto-register một servlet filter riêng ngoài security chain.
- `SecurityContextHolder.clearContext()` chỉ clear thread hiện tại; `session.invalidate()` hủy current app session, không hủy các sessions khác. `AccountSessionRevoker` xử lý phần other sessions ở shared store.
- `401` thích hợp với tài nguyên yêu cầu tái xác thực; browser MVC có thể cần login redirect/error UX riêng. Account bị disabled **không được tự retry login SSO vô hạn**.
- Filter hoạt động khi request qua chain. Một **request đã vượt qua filter** hoặc một job/background task vẫn có thể tiếp tục; các action nhạy cảm cần authoritative authorization ở commit.
- Với cached roles, filter chỉ kiểm trạng thái active; **không** làm mới `GrantedAuthorities` khi group bị gỡ. Cần security epoch/entitlement version hoặc live AuthorizationManager/method security.
- Với WebSocket/long-lived streams, scheduled tasks, message consumers, gRPC và APIs ở security chains khác, phải thêm enforcement tương đương hoặc hủy kết nối/tác vụ theo policy.
- Không tắt CSRF chỉ vì muốn đơn giản hóa filter; POST/PUT/PATCH/DELETE với cookie vẫn cần CSRF.
- Đây là **fragment Spring Boot** cần project, beans và provider thực, khác với chương trình Java thuần mục 16.

### 11.3. Đừng đặt chặn ở “login success handler” duy nhất

Nếu chỉ kiểm tại `AuthenticationSuccessHandler`, session đã tồn tại không chạy success handler lại. Nếu chỉ kiểm tại LDAP provider, federated sessions có thể bypass LDAP. Một thiết kế đầy đủ gồm:

```text
LOGIN:     validate credentials + directory/IdP account status
SESSION:   request-time state/epoch checks + current session invalidation
ACTION:    live tenant/resource authorization at commit
EVENT:     durable revocation event + delete indexed sessions + token revocation
```

## 12. `SessionRegistry.expireNow()` và `maximumSessions` không phải remote delete

Spring Security concurrent-session management có `SessionRegistry` và `SessionInformation`. Ví dụ:

```java
// Fragment, dùng khi SessionRegistry đã theo dõi đúng principal.
for (var information :
        sessionRegistry.getAllSessions(principal, false)) {
    information.expireNow();
}
```

**Ý nghĩa:** `expireNow()` đánh dấu `SessionInformation` là đã expired. `ConcurrentSessionFilter` có thể phát hiện điều đó ở **request tiếp theo** và thực hiện logout/invalidation tương ứng. Không nên tuyên bố `expireNow()` luôn xóa key session trong Redis ngay lập tức, hoặc giúp những requests đã chạy bị dừng tức thì.

`maximumSessions(1)` giải quyết **số lượng phiên đồng thời**: khi người dùng login thứ hai, hành vi mặc định có thể expire phiên cũ. Nó **không tự chạy khi admin gỡ role hoặc disable account**.

### 12.1. Môi trường cluster

`SessionRegistryImpl` mặc định trong Spring Security theo dõi state **trong memory của node**. Nếu nhiều pods, một node không nhất thiết biết phiên do pod khác tạo. Spring Session có `SpringSessionBackedSessionRegistry` để tích hợp indexed repository với concurrent-session control:

```java
// Fragment khi đã có FindByIndexNameSessionRepository<S>
// và bean SessionRegistry/SessionRepository phù hợp:
SessionRegistry registry =
    new SpringSessionBackedSessionRegistry<>(indexedSessionRepository);
```

**Phân biệt:**

- `getAllSessions`/`expireNow` phục vụ một mô hình expiry.
- `findByPrincipalName`/`deleteById` làm việc với session repository để xóa records.
- Cả hai đều cần principal mapping/index chính xác và race/fail-closed handling.
- Không tạo riêng một `SessionRegistryImpl` ở mỗi pod rồi kết luận đã “global logout”.

Spring Session Redis Indexed hỗ trợ lookups, nhưng Redis Cluster keyspace notifications/index cleanup có giới hạn theo topology/version; kiểm tài liệu và integration test khi vận hành HA. Nếu index sai, phải sửa cách lập index trước khi tin số session tìm được.

## 13. Thu hồi JWT, opaque access token và refresh token

### 13.1. JWT access token: signature hợp lệ không nói rằng account còn active

Một JWT access token có thể chứa:

```json
{
  "iss": "https://op.example.org",
  "sub": "user-42",
  "aud": ["api://finance"],
  "scope": "reports:read payments:approve",
  "iat": 1901613600,
  "exp": 1901617200,
  "jti": "jwt-identifier-example"
}
```

Khi Spring Resource Server chỉ xác minh chữ ký, `iss/aud/exp` và scopes, token vẫn có thể hợp lệ về mặt protocol **sau khi user đã bị disabled hoặc gỡ role**. Vậy nên một JWT tự xác minh **không tự có revocation online**.

Các chiến lược:

1. **Access token TTL ngắn** + refresh token có rotation/revocation. Giảm cửa sổ rủi ro, nhưng không bảo đảm **immediate stop** đối với access token còn hạn.
2. **Introspection/active check** tại Resource Server nếu Authorization Server và token architecture hỗ trợ; `active=false` phải bị từ chối. Với JWT, có thể bổ sung kiểm account security epoch/denylist, hoặc dùng opaque tokens để kiểm tập trung.
3. **Denylist theo `jti`/token hash** tới khi `exp`, với DB/cache có HA và fail-closed; không lưu raw bearer token trong logs/cache keys dễ đọc.
4. **Account/token version**: token có generation; Resource Server kiểm với authoritative state hoặc cache có consistency/SLA, từ chối generation cũ.
5. **Scope/tenant authorization online**: không coi claim `payments:approve` từ token cũ là quyền mới nhất khi giao dịch nguy hiểm.
6. **Sender-constrained tokens** như mTLS-bound hoặc DPoP giúp giảm khả năng dùng token bị đánh cắp nhưng **không thay revocation**.
7. **Emergency key rotation** có thể vô hiệu hóa rất nhiều tokens cùng key, tác động diện rộng; dùng như biện pháp sự cố có policy, không phải thủ thuật thường xuyên cho một user.

Một hệ thống chọn JWT offline vì latency cần định nghĩa **maximum revocation delay** và rủi ro cho từng action. Không hứa “disable account là JWT invalid ngay” nếu RS không có kênh nhận trạng thái mới.

### 13.2. RFC 7009 token revocation không tự vô hiệu mọi JWT ở Resource Server

OAuth 2.0 Token Revocation (RFC 7009) cung cấp endpoint để client yêu cầu Authorization Server thu hồi token. Chuẩn yêu cầu hỗ trợ revoke **refresh tokens** và khuyến nghị hỗ trợ access tokens theo điều kiện triển khai. Khi refresh token bị revoke, Authorization Server sẽ không phát token mới dựa trên token/grant đó; issued JWT access token tự kiểm tại RS có thể tiếp tục được chấp nhận nếu RS không có revocation state/denylist/introspection.

Một request **minh họa**, không chứa secret thực:

```http
POST /oauth2/revoke HTTP/1.1
Host: op.example.org
Content-Type: application/x-www-form-urlencoded

token=REDACTED_REFRESH_TOKEN&token_type_hint=refresh_token
```

- Revocation endpoint thực phải lấy từ trusted Authorization Server metadata/config, dùng HTTPS và client authentication phù hợp.
- `token_type_hint` chỉ là gợi ý; không phải bằng chứng token type.
- Không log raw refresh/access token trong URL, body, tracing hoặc CI output.
- Theo RFC, server có thể trả 200 dù token không tồn tại để tránh token enumeration; **HTTP 200 không tự chứng minh tất cả downstream APIs đã ngừng chấp nhận issued access tokens**.
- Không tự gửi token của issuer A sang revocation endpoint issuer B.

### 13.3. Opaque tokens và introspection

RFC 7662 cho phép Resource Server hỏi Authorization Server liệu token còn `active` không.

```text
API receives opaque token
     |
     v
TLS authenticated introspection
  (RS client credentials, trusted AS)
     |
     +-- active=false -> reject
     |
     +-- active=true + aud/scope/expiry/account checks -> evaluate action
```

Cần chú ý cache introspection: nếu cache kết quả `active=true` trong 10 phút, một token vừa revoke có thể vẫn được RS coi active trong cache. Chính sách cache TTL/invalidation là một phần của **revocation SLA**; không tuyên bố introspection tức thời khi thực tế dùng stale cache.

### 13.4. Refresh-token rotation và token families

Khi nghi compromise, revoke refresh token hiện tại, **token family/grant liên quan** và những devices/sessions khác theo risk. Rotation giúp phát hiện reuse, nhưng triển khai cụ thể của OP quyết định token family behavior; đừng dựa vào việc “đổi password” mà bỏ bước explicit revoke grant khi policy yêu cầu.

Không lưu refresh tokens plaintext trong Redis session chỉ để dễ debug. Dùng secure token store, encryption/key rotation, audit, expiry và data minimization.

## 14. Federated SSO: logout ở OP/IdP khác local session cleanup

### 14.1. OIDC: RP-Initiated Logout và Back-Channel Logout

OpenID Connect có nhiều khả năng logout:

- **Local logout**: chỉ hủy phiên ở ứng dụng RP.
- **RP-Initiated Logout**: RP hướng user agent đến OP `end_session_endpoint` để kết thúc OP SSO, tùy OP hỗ trợ/parameters.
- **Back-Channel Logout**: OP gửi **Logout Token đã ký** tới RP bằng request server-to-server, RP xác minh rồi tìm và logout sessions tương ứng `sid` hoặc `sub`.
- **Front-channel logout**: dựa vào user agent/redirect/iframe tùy spec và hỗ trợ; có hạn chế khi browser không còn hoạt động hoặc cookie policy chặn.

Spring Security hiện có `oidcLogout(...backChannel(...))` cho Servlet OIDC RP trong các phiên bản hỗ trợ. Theo reference hiện hành, endpoint mặc định dạng:

```text
POST /logout/connect/back-channel/{registrationId}
```

Với OIDC Back-Channel Logout, Logout Token phải được xác minh theo spec: signature, `iss`, `aud`, `iat/exp`, `jti` và `events`, có `sid` hoặc `sub`, và không có `nonce`. Khi có `sid`, scope nhắm provider session tương ứng; khi chỉ có `sub`, RP tìm các sessions cho user đó trong issuer/client scope. **Không** tiếp nhận `GET /logout?sub=alice` từ browser như một global logout đáng tin.

Ví dụ **fragment Spring Security Servlet phiên bản hỗ trợ OIDC back-channel**:

```java
http
    .oauth2Login(Customizer.withDefaults())
    .oidcLogout(logout -> logout
        .backChannel(Customizer.withDefaults()));
```

**Không ghép fragment này vào formLogin-only app**. Cần `oauth2Login`, đúng ClientRegistration và OP metadata/support. Spring Security có lưu ý về tên session cookie `JSESSIONID` mặc định so với `SESSION` của Spring Session; cần cấu hình `OidcBackChannelLogoutHandler` tương ứng, sự kiện session và session registry phù hợp cluster. API chính xác thay đổi theo Spring Security version (6.x/7.x); đối chiếu reference đúng dependency.

**Quan trọng:** OIDC Back-Channel Logout **không tự revoke mọi OAuth2 access tokens ở tất cả Resource Servers**. Làm logout web RPs và token/grant revocation là hai hoạt động khác nhau cần phối hợp.

### 14.2. SAML 2.0 Single Logout

SAML cho phép:

- **SP/RP-Initiated SLO**: ứng dụng gửi `<saml2:LogoutRequest>` tới IdP, và xử lý `LogoutResponse`.
- **IdP/AP-Initiated SLO**: IdP gửi `LogoutRequest` tới SP, SP xác minh signature/issuer/destination/correlation theo profile rồi hủy local session.
- **`SessionIndex`** từ `AuthnStatement` giúp định danh SAML session phía IdP/SP, nhưng không phải ID `HttpSession` trong browser.
- SLO có thể là **partial** nếu một RP offline, browser flow không hoàn tất hoặc đối tác không hỗ trợ metadata `SingleLogoutService`.

Spring Security có `saml2Logout` hỗ trợ khi `RelyingPartyRegistration` có signing credentials và cấu hình SLO/IdP metadata phù hợp. Đừng tự nhận bất kỳ XML LogoutRequest unsigned nào để xóa session người khác, vì đó là logout CSRF/DoS. Đồng thời, **SLO không tự xóa stateless JWT** đã được cấp bởi hệ thống khác.

### 14.3. CAS Global Logout

CAS local logout trong App A không mặc nhiên xóa CAS TGT/TGC. CAS Server có khả năng Single Logout/service notifications theo protocol/config, nhưng mỗi application phải có CAS SLO integration, session correlation và failure handling phù hợp. Một `Service Ticket` đã dùng không phải session id; không thể “revoke tất cả phiên bằng cách xóa ST đã được validate”.

Khi account bị disable tại Directory, có thể CAS SSO session/TGT còn tồn tại tùy policy và cache; cần phối hợp CAS session invalidation và kiểm user status lúc cấp ST mới.

### 14.4. Kerberos/Active Directory

TGT và Service Ticket được KDC cấp có thời hạn. Disable AD user hoặc đổi group membership không đảm bảo **mọi ticket đã cấp hoặc Spring local web session lập tức hết hiệu lực**. KDC có thể từ chối cấp ticket mới theo domain policy, nhưng service app có thể chấp nhận service ticket còn hợp lệ theo GSS/JAAS/keytab mà không hỏi AD mỗi request. Phải quản lý ticket lifetime, account lookup/revocation và local app sessions, đặc biệt khi user disable do incident.

**Không tự xoay keytab của HTTP service account để “kick một user”**: service key rotation có phạm vi tới mọi users sử dụng SPN, không phải user-specific revoke.

## 15. Concurrency: giải quyết race và ngăn phiên hồi sinh

### 15.1. Race 1 — login đồng thời với revoke

```text
T0 Auth thread reads enabled=true
T1 Admin disables user; commits authoritative state, epoch=2
T2 Auth thread creates HttpSession under old epoch=1
T3 Revocation worker queries sessions that existed at T1 only
T4 New session created at T2 not found in snapshot
```

**Bảo vệ:** Gắn session epoch khi authentication thành công; ngay trước cấp session/first business action kiểm epoch/account state mới; event worker có thể delete sessions tìm được, nhưng authoritative gate từ chối epoch 1 sau T1.

### 15.2. Race 2 — request đang thực hiện nghiệp vụ

```text
T0 Alice loads approval page
T1 Alice sends POST /payments/123/approve
T2 Application checks cached ROLE_APPROVER
T3 Admin revokes role at authoritative store
T4 Application commits approval
```

Nếu nghiệp vụ yêu cầu không có commit sau revoke T3, phải **đặt quyền truy cập và nghiệp vụ trong cùng ranh giới giao dịch phù hợp**, hoặc dùng compare-and-set version/fencing token ở commit:

```text
Transaction APPROVE:
  load current AccountAccessState (authorized source)
  assert enabled && nonLocked
  assert tenant membership, effective permission for payment 123
  assert entitlementVersion/current policy at commit boundary
  assert resource state, amount, payee and optimistic lock
  commit approval only if all conditions still hold
```

Khi directory/permissions ở service khác database, cần một policy store/cache có consistency contract đủ mạnh hoặc giao thức commit theo rủi ro. **Chỉ gọi một LDAP query trước khi làm việc kéo dài nhiều giây không tạo atomic guarantee**.

### 15.3. Race 3 — cache/Redis events bị bỏ lỡ

- Worker outbox down: account state ở DB đã disable nhưng sessions vẫn trong Redis.
- Một pod mất event: caches giữ authority cũ.
- Redis Cluster keyspace notifications thiếu sự kiện: stale principal index.
- Mobile app offline: refresh grant revoked nhưng access token cũ còn hạn.
- IdP back-channel logout tới RP bị timeout: RP local session chưa bị xóa.

**Biện pháp:** Idempotent durable retries, monotonic version, bounded cache TTL, authoritative request/action checks, periodic reconciliation và measurable SLA. Không dùng một event bus kiểu best-effort mà không có cơ chế kiểm lại.

### 15.4. Race 4 — cùng email ở hai issuer

```text
Issuer A: (https://op-a.example.org, sub=alice)
Issuer B: (https://op-b.example.org, sub=alice)
```

Nếu xóa sessions theo string `alice` mà app index không phân biệt issuer, có thể xóa nhầm phiên của account khác. Thiết kế cần map identity verified → stable internal `accountKey`; nếu một người có hai identities legitimately linked, thu hồi theo accountKey khi policy nhắm tất cả; nếu chỉ revoke một federation credential thì scope issuer/connection chính xác.

## 16. Java 17 chạy độc lập: trạng thái account, quyền tenant và session version

Để chứng minh logic mà không cần LDAP/IdP/Spring Session thật, tạo chương trình **Java 17 console**. Mọi account/session trong ví dụ nằm trong bộ nhớ test, **không xác minh mật khẩu, JWT, SAML, Kerberos hay Redis**. Chương trình thể hiện **ba kết quả khác nhau**: role bị thu hồi, account bị khóa/disable, và session ID bị xóa.

### 16.1. Policy của ví dụ

- Account `acct-42` active, có quyền `approve` ở tenant `red`.
- Phiên `s1` lưu `entitlementVersion=1`.
- Gỡ role làm version thành 2. Phiên cũ được xem **stale** và không thể approve.
- Session mới version 2 vẫn tồn tại nhưng không có quyền approve.
- Khóa account chặn request cho dù session ID còn tồn tại.
- Thu hồi sessions loại `s1`/`s2`; browser giữ cookie cũ cũng không được xác thực.
- Mở khóa không tự khôi phục role đã mất.
- Disable account lần sau chặn cả session mới.
- Xóa sessions lặp lại phải có kết quả idempotent.

File `AccessRevocationDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

public final class AccessRevocationDemo {

    enum Decision {
        ALLOW,
        DENY_NO_SESSION,
        DENY_ACCOUNT_DISABLED,
        DENY_ACCOUNT_LOCKED,
        DENY_STALE_AUTHORITY,
        DENY_PERMISSION
    }

    record Account(
        boolean enabled,
        boolean locked,
        long entitlementVersion,
        Set<String> permissions
    ) { }

    record SessionEvidence(
        String sessionId,
        String accountId,
        long entitlementVersion
    ) { }

    private static final String ACCOUNT = "acct-42";

    private static final Map<String, Account> accounts =
        new HashMap<>();

    private static final Map<String, SessionEvidence> sessions =
        new HashMap<>();

    static Decision evaluate(
            String sessionId, String tenant, String action) {

        SessionEvidence session = sessions.get(sessionId);
        if (session == null) {
            return Decision.DENY_NO_SESSION;
        }

        Account account = accounts.get(session.accountId());
        if (account == null || !account.enabled()) {
            return Decision.DENY_ACCOUNT_DISABLED;
        }

        if (account.locked()) {
            return Decision.DENY_ACCOUNT_LOCKED;
        }

        if (session.entitlementVersion() !=
                account.entitlementVersion()) {
            return Decision.DENY_STALE_AUTHORITY;
        }

        String permission = tenant + ":" + action;
        if (!account.permissions().contains(permission)) {
            return Decision.DENY_PERMISSION;
        }

        return Decision.ALLOW;
    }

    static int revokeAllSessions(String accountId) {
        int before = sessions.size();
        sessions.entrySet().removeIf(
            e -> e.getValue().accountId().equals(accountId));
        return before - sessions.size();
    }

    public static void main(String[] args) {
        accounts.put(ACCOUNT,
            new Account(true, false, 1,
                Set.of("red:approve", "red:view")));

        sessions.put("s1",
            new SessionEvidence("s1", ACCOUNT, 1));

        System.out.println("before=" +
            evaluate("s1", "red", "approve"));
        System.out.println("crossTenant=" +
            evaluate("s1", "blue", "approve"));

        // Admin gỡ APPROVE: tăng entitlementVersion.
        accounts.put(ACCOUNT,
            new Account(true, false, 2,
                Set.of("red:view")));

        System.out.println("oldAuthority=" +
            evaluate("s1", "red", "approve"));

        sessions.put("s2",
            new SessionEvidence("s2", ACCOUNT, 2));

        System.out.println("freshNoRole=" +
            evaluate("s2", "red", "approve"));

        // Admin khóa tài khoản, session ID chưa bị xóa.
        accounts.put(ACCOUNT,
            new Account(true, true, 3,
                Set.of("red:view")));

        System.out.println("locked=" +
            evaluate("s2", "red", "view"));

        System.out.println("invalidated=" +
            revokeAllSessions(ACCOUNT));

        System.out.println("oldSession=" +
            evaluate("s1", "red", "view"));

        // Mở khóa không khôi phục quyền phê duyệt.
        accounts.put(ACCOUNT,
            new Account(true, false, 4,
                Set.of("red:view")));

        sessions.put("s3",
            new SessionEvidence("s3", ACCOUNT, 4));

        System.out.println("unlockedViewer=" +
            evaluate("s3", "red", "view"));

        // Disable account: dù s3 còn trong store cũng bị từ chối.
        accounts.put(ACCOUNT,
            new Account(false, false, 5,
                Set.of("red:view")));

        System.out.println("disabled=" +
            evaluate("s3", "red", "view"));

        System.out.println("disabledRevoke=" +
            revokeAllSessions(ACCOUNT));
        System.out.println("repeatRevoke=" +
            revokeAllSessions(ACCOUNT));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 AccessRevocationDemo.java
java AccessRevocationDemo
```

Stdout xác định:

```text
before=ALLOW
crossTenant=DENY_PERMISSION
oldAuthority=DENY_STALE_AUTHORITY
freshNoRole=DENY_PERMISSION
locked=DENY_ACCOUNT_LOCKED
invalidated=2
oldSession=DENY_NO_SESSION
unlockedViewer=ALLOW
disabled=DENY_ACCOUNT_DISABLED
disabledRevoke=1
repeatRevoke=0
```

**Giải thích:**

- `before=ALLOW`: phiên và account cùng entitlementVersion, có quyền approve tenant red.
- `crossTenant=DENY_PERMISSION`: cùng user nhưng không có quyền ở tenant blue.
- `oldAuthority=DENY_STALE_AUTHORITY`: đã gỡ role và tăng version; không tiếp tục dùng cached authority version 1.
- `freshNoRole=DENY_PERMISSION`: phiên mới version 2 không có quyền approve, nên vẫn bị từ chối.
- `locked=DENY_ACCOUNT_LOCKED`: không cần đợi session bị xóa mới chặn.
- `invalidated=2`: hai session IDs của account đã bị xóa khỏi store demo.
- `oldSession=DENY_NO_SESSION`: cookie/session ID cũ không còn có thể dùng.
- `unlockedViewer=ALLOW`: admin mở khóa, user vẫn chỉ có quyền view.
- `disabled=DENY_ACCOUNT_DISABLED`: session tồn tại nhưng account disabled.
- `disabledRevoke=1` và `repeatRevoke=0`: cleanup session idempotent ở mô phỏng.

**Giới hạn cực kỳ quan trọng:** Bản demo dùng `HashMap` và không an toàn cho nhiều threads/nodes hoặc transaction; `entitlementVersion` là mô phỏng. Production cần atomic DB commits, Spring Session Redis/JDBC, durable outbox, issuer-scoped identities, clock/epoch policy, account lookup và authorization thực sự. **Không dùng các boolean trong demo do browser gửi làm bằng chứng account active hoặc phiên hợp lệ**.

## 17. Test matrix: thu hồi quyền, khóa account và session invalidation

Kiểm thử trong staging với **ít nhất hai browsers/thiết bị, hai pods, hai tenants và một client API**. Mỗi test phải phân biệt rõ account source, local session, IdP session, access/refresh tokens và authorization.

| Trường hợp | Hành động test | Kết quả mong đợi |
| --- | --- | --- |
| **Login ACTIVE** | User active, có quyền, login mới | Success và đúng authorities |
| **Directory LOCKED, login mới** | Lock account trước login | Provider/IdP từ chối theo policy |
| **Directory DISABLED, login mới** | Disable trước login | Không tạo local authenticated session |
| **Directory DISABLED, session cũ** | Login, sau đó disable, request mới | 401/redirect có kiểm soát hoặc deny, session bị cleanup |
| **Directory LOCKED, session cũ** | Lock khi user đang có cookie | Behavior theo policy, nếu require containment thì deny/revoke |
| **Gỡ role, session cũ** | Remove APPROVE, vẫn còn session | Không còn approve; không dựa cached GrantedAuthorities |
| **Gỡ role một tenant** | Revoke tenant A, vẫn có quyền tenant B | A deny; B đúng policy, không leak cross-tenant |
| **Đổi account status trong AD** | ACCOUNTDISABLE flag theo directory API | App nhìn effective state đúng, không giả định raw UAC == 514 |
| **LDAP lockout khác disable** | Trigger lockout tạm thời | Correct behavior theo directory policy, không nhầm permanently disabled |
| **Nested AD group** | Gỡ membership ở group con | Effective role từ nested groups được cập nhật đúng |
| **User renamed/email changed** | Đổi email/UPN | Không revoke account khác do email collision |
| **Cùng username hai issuer** | Users `alice` từ OP A và B | Scope theo issuer+sub; không xóa nhầm |
| **Hai browser sessions** | Login A và B, revoke account | Cả hai sessions không dùng được |
| **Hai pods shared Redis** | Session A tạo pod1, revoke pod2 | Session A bị xóa/denied khi truy cập pod1 |
| **Index principal thiếu** | Session không có principal index | Revoker không coi số 0 là success; sửa index/extra detection |
| **Only current HttpSession invalidation** | Logout browser A | Browser B vẫn tồn tại trừ khi policy revoke all |
| **SessionRegistry.expireNow** | Mark session expired | Bị xử lý ở request sau qua filter/strategy; không tuyên bố immediate hard delete |
| **Race login/revoke** | Login đồng thời admin disable | Session sinh từ epoch cũ vẫn bị chặn |
| **In-flight approve request** | Revoke sau initial check, trước commit | Business commit phải bị deny/rollback nếu policy yêu cầu immediate |
| **Outbox worker down** | Disable commit, event chưa đến worker | Active request gate/epoch vẫn deny |
| **Duplicate/out-of-order events** | Deliver v3 rồi v2 | Không hạ entitlementVersion/khôi phục role |
| **Redis Cluster index cleanup** | Event expiry node khác | Có reconciliation và fail-closed, không mặc định indexes hoàn hảo |
| **OIDC SSO vẫn sống** | Xóa local session, browser login lại | Account state gate/IdP policy không cấp quyền mới |
| **OIDC Back-Channel Logout** | OP gửi signed Logout Token đúng aud/sid/sub | RP revoke đúng sessions của issuer/client |
| **Forged Logout Token** | Sai signature/aud/issuer/events/jti policy | Reject, không logout user khác |
| **SAML SLO signed** | IdP gửi valid LogoutRequest | SP verify và logout đúng session |
| **SAML SLO unsigned/foreign issuer** | Request giả đến SLO endpoint | Reject, không hủy sessions khác |
| **CAS local logout** | App local logout | CAS TGT/TGC có thể còn; test cơ chế SLO riêng |
| **Kerberos ticket cũ** | AD user disabled nhưng đã có service ticket | Không mặc định ticket vô hiệu ngay; app gate/role policy deny |
| **JWT còn hạn** | Disable user, dùng access JWT issued trước | Nếu requirement immediate, RS deny bằng status/epoch/introspection |
| **Refresh token revoked** | Gọi token endpoint bằng revoked refresh token | Không phát access token mới |
| **Opaque token inactive** | Introspection `active=false` | RS trả 401 |
| **Introspection cache stale** | Active cached trước revoke | Bị chặn theo configured SLA/invalidations |
| **WebSocket/long-lived stream** | Lock account giữa connection | Disconnect/recheck theo policy, không chờ web GET |
| **Background job queued** | User queued export trước revoke | Job checks current entitlement trước execute/commit |
| **Audit/on-call** | Admin revoke hàng loạt account | Evidence có event ID, actor, scope, latency và outcomes |
| **Re-enable account** | Unlock sau sự cố | Không tự khôi phục revoked roles/sessions/grants |
| **Loss of state store** | DB unavailable ở action high risk | Fail closed, không dùng old admin authority |
| **Multi-device revocation** | iOS app + browser + API token | Policy coverage rõ cho local sessions, refresh/access tokens |
| **Admin API abuse** | Non-admin tự gọi revoke endpoint | 403, CSRF/MFA/rate limit/audit theo policy |

**Pass criterion:** Không chỉ nhìn thấy trang “Bạn đã bị đăng xuất”. Phải thử **session cookie cũ**, **access token còn hạn**, **refresh token**, **action ở đúng tenant** và **request tới pod khác**. Với role revoke, yêu cầu là business authorization chính xác; logout toàn màn hình có thể là triệu chứng phụ, không đủ chứng minh permissions đã mất.

## 18. Security logging và điều tra sự cố

Đề xuất một security audit record không tiết lộ credential:

```json
{
  "eventId": "evt-example-42",
  "eventType": "ACCOUNT_DISABLED",
  "accountKey": "acct-42",
  "issuerOrRealm": "directory-corp",
  "scope": "ACCOUNT",
  "tenantId": null,
  "actorKey": "sec-admin-17",
  "newEntitlementVersion": 23,
  "effectiveAt": "2030-05-10T08:00:00Z",
  "sessionRevocation": {
    "sessionsDiscovered": 3,
    "sessionsDeleted": 3,
    "verified": true
  },
  "tokenRevocation": {
    "refreshTokenFamiliesRequested": 2,
    "completed": false
  },
  "requestGatePolicy": "deny-if-disabled-or-stale",
  "traceId": "trace-example"
}
```

Dữ liệu trên là **mẫu minh họa**, không phải status của hệ thống thực. Không log raw `SESSION`/`JSESSIONID` cookie, JWT access/refresh token, SAMLResponse, LDAP passwords, CAS TGT, Kerberos keytab hoặc PII không cần thiết.

**Một báo cáo revoke nên nêu rõ:** “account disabled at T0; HTTP sessions deleted at T2; refresh-token families revoked at T3; JWT RS epoch enforcement enabled; SAML/other RPs pending confirmation” thay vì “tất cả đã logout” khi thiếu chứng cứ.

### 18.1. Các chỉ số cần theo dõi

- `revocation_event_lag_seconds`: T0 → event consumer ack, phân bố p95/p99.
- `session_revoke_lookup_count`, `deleted_count`, `index_miss_count`: không coi 0 luôn là success.
- `disabled_account_request_denied` / `stale_authority_denied` theo application/pod (không log IDs nhạy cảm quá mức).
- `refresh_grant_revoke_success/failure` theo issuer/client.
- `jwt_revocation_or_epoch_check_latency` và failures; cache TTL/consistency.
- `oidc_backchannel_logout_valid_invalid`, `saml_slo_signature_failures`, CAS logout failures.
- `cross_tenant_permission_denied` và unexpected success anomalies.
- `outbox_retries/dead_letter_age`, DB/Redis availability.
- `long_lived_connections_disconnected`, queued job cancellation count.
- Unauthorized admin revocation calls và scope violations.

Không quảng cáo một SLA chưa được đo thực tế. Với API nhạy cảm, business stakeholders cần ký duyệt maximum revocation window, và test phải chứng minh dưới tải/cluster/IdP outage.

## 19. Runbook: thu hồi quyền và xử lý compromise

### 19.1. Trường hợp A — gỡ quyền phê duyệt ở một tenant

1. Xác minh actor/admin có quyền quản lý **đúng tenant** với MFA và change approval.
2. Resolve target bằng stable internal account ID và verified source identities, không tìm theo email duy nhất.
3. Cập nhật permission cho tenant A và tăng entitlementVersion trong authoritative transaction; ghi outbox/audit.
4. Clear cached entitlements, áp live authorization check trên `approvePayment` tại transaction commit.
5. Nếu apps vẫn dùng cached role snapshot, revoke relevant sessions hoặc buộc refresh authentication.
6. Kiểm request dùng cookie/token cũ **không thể approve** tenant A; tenant B chỉ tiếp tục nếu còn membership.
7. Kiểm activity log và pending approvals có bị commit sau T0 không.
8. Xác minh event consumers processed đúng version và báo outcome.

### 19.2. Trường hợp B — account locked do rủi ro thấp/tạm thời

1. Xác định lockout là policy chống brute-force hay admin security block.
2. Nếu chỉ khóa authentication mới, ghi policy scope; nếu suspect compromise, nâng lên toàn account containment.
3. Không mở khóa tự động bằng một timer ứng dụng nếu directory account vẫn báo locked.
4. Kiểm authentication mới bị chặn; nếu policy yêu cầu, invalidate active web sessions và grants/tokens liên quan.
5. Có cơ chế recovery/step-up/review trước unlock; không khôi phục role revoked không được phê duyệt.

### 19.3. Trường hợp C — nghi tài khoản bị chiếm quyền hoặc offboarding

Thứ tự containment gợi ý:

1. Ghi incident/ticket và khóa/vô hiệu account ở **authoritative directory/IdP**.
2. Tăng `sessionsValidAfter`/security epoch và policy ban immediate deny ở app/API.
3. Revoke app web sessions trên tất cả pods/RPs được quản lý; xác minh bằng cookie cũ.
4. Revoke refresh tokens/grants và OP sessions, dùng Back-Channel/SAML SLO khi được cấu hình; xác định RPs chưa nhận.
5. Với JWT access tokens còn hạn, áp RS denylist/epoch/introspection theo rủi ro; không chỉ đợi token tự expire nếu SLA không cho phép.
6. Hủy/cô lập WebSocket, long-running jobs, offline access, API keys và device sessions theo inventory.
7. Rà soát permission/tenant actions trong cửa sổ nghi compromise, rotate credentials/secrets liên quan nếu cần.
8. Kiểm account không tái đăng nhập qua liên kết federation khác, alias/guest account hoặc SSO cũ.
9. Ghi bằng chứng time/trace/outcomes và yêu cầu owner các RPs xác nhận.
10. Khi re-enable, cần một quy trình phê duyệt riêng, **không tự khôi phục sessions, refresh tokens và high-risk roles trước đó**.

**Không dùng mass deletion cả Redis database hoặc rotate toàn bộ OIDC signing keys chỉ để khóa một user** khi có phương án scoped account/session/token. Những biện pháp này có blast radius lớn, phải theo incident commander và security policy.

## 20. Câu hỏi ôn tập kèm đáp án

**Câu 1.** Directory đặt `enabled=false` cho Alice, nhưng browser vẫn có Redis `SESSION` được Spring Security xác thực từ sáng. Có phải lỗi của LDAP không?

**Đáp án:** Không nhất thiết; LDAP trạng thái mới không tự hủy local app session. Cần request-time status check và/hoặc delete sessions qua Spring Session, rồi test cookie cũ.

**Câu 2.** Admin gỡ `ROLE_APPROVER` nhưng ứng dụng chỉ kiểm `hasRole('APPROVER')` trên cached `Authentication`. User có thể làm tiếp không?

**Đáp án:** Có thể. Cần refresh authorities/entitlementVersion, invalidates sessions hoặc live permission check ở action/commit.

**Câu 3.** `SessionInformation.expireNow()` có nghĩa Redis key đã bị xóa ngay chưa?

**Đáp án:** Không mặc định. Nó mark expired trong registry; hiệu lực thường được xử lý khi request sau qua `ConcurrentSessionFilter`. Với explicit session delete dùng repository hỗ trợ `deleteById`, vẫn cần xử lý race và pending requests.

**Câu 4.** Ứng dụng lưu sessions vào Redis, có thể gọi `findByPrincipalName("alice")` là chắc chắn xóa mọi session của Alice không?

**Đáp án:** Không. Cần indexed repository và index value đúng, stable internal identity, issuer mapping; sessions trên RPs khác/JWTs không thuộc app có thể vẫn tồn tại.

**Câu 5.** OP đã revoke refresh token. Issued JWT access token còn hạn có chắc chắn bị mọi APIs từ chối không?

**Đáp án:** Không. JWT được RS tự kiểm có thể vẫn pass; cần RS revocation awareness, denylist/epoch/introspection hoặc chấp nhận TTL window theo policy.

**Câu 6.** SAML IdP gửi LogoutRequest không có chữ ký qua browser. Có nên tin và logout nhiều user không?

**Đáp án:** Không. SP phải validate SAML SLO theo IdP issuer, signature, destination/correlation và configured metadata; request giả không được làm DoS logout.

**Câu 7.** OIDC Back-Channel Logout Token chỉ có `sid`, không có `sub`. RP cần làm gì?

**Đáp án:** Nếu token hợp lệ theo spec và client/issuer scope, hủy sessions được correlate với provider session `sid` đó; không đoán hoặc logout user khác. Nếu chỉ có `sub`, scope theo issuer/client để hủy sessions user tương ứng.

**Câu 8.** Một user bị gỡ quyền tenant A, vẫn có quyền ở tenant B. Có cần disable toàn account không?

**Đáp án:** Không nhất thiết. Policy có thể revoke theo tenant và kiểm đúng permissions/epoch. Tuy nhiên incident compromise có thể đòi khóa toàn account.

**Câu 9.** Event revoke được publish nhưng worker Redis tạm down. Có thể cho phép action nhạy cảm bằng cached role cho tới khi queue chạy lại không?

**Đáp án:** Không khi yêu cầu immediate revocation. Dùng authoritative state/version fence tại action hoặc fail closed; event cleanup chỉ là bước hậu thuẫn.

**Câu 10.** User bị disabled ở AD nhưng Service Ticket Kerberos đã cấp còn hạn, Spring app vẫn có session. Có được tự kết luận user bị chặn chưa?

**Đáp án:** Không. Kerberos tickets và app sessions có lifecycle riêng; cần kiểm account status, xóa sessions/credentials và xác minh thực tế.

## 21. Checklist nghiệm thu production

- [ ] Phân biệt rõ **revoke permission**, **lock account**, **disable account**, **local session invalidation**, **IdP logout**, **refresh/access token revocation**.
- [ ] Từng hành động có owner, threat/risk level, scope (account/issuer/tenant/device/session), policy và expected latency/SLA.
- [ ] Directory/AD/LDAP status được đọc theo schema và policy đúng, không so raw `userAccountControl==514` hoặc coi lockout=disabled.
- [ ] Effective directory groups và nested memberships được cập nhật, không chỉ cache `memberOf` đơn giản.
- [ ] Định danh revoke dùng stable internal `accountKey` liên kết với `issuer+subject`/directory immutable ID; không chỉ email/username.
- [ ] `UserDetails.isEnabled/isAccountNonLocked` được áp đúng tại login, nhưng có kiểm stale sessions riêng.
- [ ] User disabled/locked không thể dùng session đang tồn tại để tiếp tục action bị cấm.
- [ ] Role/permission revoke cập nhật entitlementVersion/authoritative authorization, action-time check tại đúng tenant/resource.
- [ ] Có transaction/outbox/idempotent events, monotonic versions, retries và reconciliation khi consumer down.
- [ ] Spring Session Redis/JDBC indexing và `FindByIndexNameSessionRepository` đã verify trên cluster, đúng principal names.
- [ ] Session revoker không chỉ invalidate current `HttpSession`; có cơ chế multi-device/multi-pod nếu scope yêu cầu.
- [ ] `SessionRegistry.expireNow` không bị nhầm với hard delete tức thì.
- [ ] Delete sessions đã có race handling và gate chặn session được tạo sau T0 bằng security epoch.
- [ ] RPs đang xử lý in-flight requests/jobs/WebSockets được fence ở commit hoặc có connection lifecycle policy.
- [ ] OIDC Back-Channel Logout/ RP-Initiated Logout được cấu hình đúng khi OP hỗ trợ; Logout Tokens phải được verify và scope theo issuer/client/sid/sub.
- [ ] SAML SLO có metadata/keys và validate signature/correlation; không hứa logout thành công ở các RPs offline.
- [ ] CAS TGT/TGC và Kerberos tickets được hiểu là khác local app sessions.
- [ ] JWT access tokens còn hạn được xử lý theo bounded TTL hoặc RS revocation/epoch; refresh grants được revoke riêng.
- [ ] Opaque token introspection `active` và cache TTL được tính vào revocation SLA.
- [ ] Không dùng unverified token/header/email làm căn cứ xóa sessions của user khác.
- [ ] Admin revocation API có MFA, authorization theo scope/tenant, CSRF/anti-replay, rate limiting và audit.
- [ ] Không dùng `FLUSHDB`/broad delete Redis keys hoặc global signing key rotation cho one-user issue nếu chưa được duyệt.
- [ ] Session cookies có `Secure`, `HttpOnly`, `SameSite` phù hợp, và app logout là POST CSRF-safe theo mô hình browser.
- [ ] Redis/DB/queue/TLS được bảo vệ, credentials/tokens/session IDs không xuất hiện trong logs.
- [ ] Test multi-device, multi-pod, multi-issuer, multi-tenant và token/grant types, kể cả race login/revoke.
- [ ] Có kết quả negative tests: disabled account old cookie fail, permission revoked old JWT fail theo SLA, stale role không commit.
- [ ] Có alert cho revoke lag, index misses, expired sessions, OP logout failures, stale JWT authorization và outbox backlog.
- [ ] Re-enable account là thao tác có phê duyệt, **không** tự khôi phục roles/grants/sessions revoked.
- [ ] Có runbook offboarding/incident với T0–T4 và acceptance evidence cho tất cả hệ downstream.

**Kết luận:** Trong **Thư mục và tài khoản**, thu hồi quyền, khóa tài khoản và vô hiệu hóa phiên đang tồn tại phải được thiết kế như **một vòng đời an ninh xuyên nhiều hệ thống**. Directory quyết định trạng thái và entitlements; IdP/Authorization Server quản lý SSO sessions và token grants; ứng dụng Spring quản lý `SecurityContext`/`HttpSession`; Resource Server thực thi quyền với JWT/opaque tokens. **Không có thao tác duy nhất tự bảo đảm tất cả các hệ thống đã thu hồi**. Hệ thống an toàn cần authoritative account status, monotonic security/entitlement versions, session/token revocation có phạm vi, business authorization tại commit và bộ kiểm thử đo được thời gian lan truyền.

## 22. Tài liệu tham khảo

1. [Spring Security – Session Management (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): `SecurityContext`, `SessionRegistry`, concurrent sessions và session expiry.
2. [Spring Security – Logout (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): local logout, `SecurityContextLogoutHandler`, session invalidation và CSRF.
3. [Spring Session – Spring Security Integration](https://docs.spring.io/spring-session/reference/spring-security.html): SpringSessionBackedSessionRegistry và indexed session management.
4. [Spring Session – Redis Configurations](https://docs.spring.io/spring-session/reference/configuration/redis.html): `RedisIndexedSessionRepository` vs `RedisSessionRepository`, indexed repository mode, namespace, Redis Cluster caveats.
5. [Spring Session – HttpSession Integration](https://docs.spring.io/spring-session/reference/http-session.html): session repository, events và Spring Security integration.
6. [Spring Session API – FindByIndexNameSessionRepository](https://docs.spring.io/spring-session/docs/current/api/org/springframework/session/FindByIndexNameSessionRepository.html): `findByPrincipalName`/principal index semantics.
7. [Spring Security – UserDetails API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/userdetails/UserDetails.html): `isEnabled`, `isAccountNonLocked`, credentials/account expiry flags.
8. [Microsoft Learn – UserAccountControl property flags](https://learn.microsoft.com/en-us/troubleshoot/windows-server/active-directory/useraccountcontrol-manipulate-account-properties): `ACCOUNTDISABLE`, lockout flags, `msDS-User-Account-Control-Computed`.
9. [Spring Security – OIDC Logout](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html): RP-Initiated Logout, Back-Channel Logout, `sid/sub` session correlation.
10. [OpenID Connect – Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html): signed Logout Tokens, validation, per-RP sessions và security.
11. [Spring Security – SAML 2.0 Single Logout](https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html): SP/AP initiated SLO, signing, metadata và validation.
12. [RFC 7009 – OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): revoke refresh/access tokens và revocation endpoint behavior.
13. [RFC 7662 – OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active` check, RS queries và token metadata.
14. [RFC 9700 – Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): token protection, PKCE, authorization server/resource server security practices.
15. [Spring Security – JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT signature/issuer/claims validation và roles.
16. [Spring Security – Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): token introspection integration.
17. [OWASP – Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny-by-default, least privilege, resource/tenant authorization.
18. [OWASP – Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session invalidation, cookies và lifecycle.
19. [NIST SP 800-63B – Digital Identity Guidelines, Authentication and Lifecycle](https://pages.nist.gov/800-63-4/sp800-63b.html): account/session handling, reauthentication và risk-based requirements.
