# Chống chiếm tài khoản khi liên kết chỉ dựa trên email trùng nhau

> **Module:** Spring Security – federation · **Chủ đề cha:** Thư mục và tài khoản. Bài Knowledge này giải thích vì sao đăng nhập từ IdP thành công **không** chứng minh người dùng bên ngoài sở hữu một tài khoản nội bộ có cùng địa chỉ email; cách ngăn chiếm tài khoản (account takeover) khi liên kết OIDC/SAML/Kerberos/directory/SCIM; và cách thiết kế liên kết có bằng chứng, tính nguyên tử, quyền hạn cùng cơ chế thu hồi.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt ba quyết định: **IdP xác thực external principal**, **ứng dụng liên kết external principal với local account**, và **ứng dụng phân quyền trên dữ liệu nội bộ**.
2. Nêu rõ lý do `email`, `email_verified`, `preferred_username`, `name`, `upn`, `mail` và SAML email NameID không đủ làm khóa liên kết.
3. Sử dụng OIDC `(iss, sub)` của **ID Token đã được kiểm chứng** và hiểu caveat pairwise subject theo client/sector identifier.
4. Trong Microsoft Entra, phân biệt `oid + tid` và `iss + sub`; biết vì sao email/UPN thay đổi hoặc có thể tái cấp.
5. Trong SAML2, hiểu `persistent NameID` kèm issuer/SP scope và qualifiers, khác `emailAddress` và `transient NameID`.
6. Trong SCIM, phân biệt `id` từ service provider và `externalId` scoped theo provisioning client; không dùng `emails.value` làm khóa để nối vào account cũ.
7. Phân tích pre-hijacking, mailbox recycling, guest account, cross-tenant confusion, alias normalization, IdP migration, SCIM race và đồng thời ghi liên kết.
8. Xây model `local_user_id` độc lập với email và bảng external identity links có khóa duy nhất theo nguồn/scope.
9. Thiết kế **explicit account linking** với existing local authenticated session, recent reauthentication/MFA, một luồng IdP authentication mới, CSRF/state/nonce/PKCE, LinkIntent một lần và database transaction.
10. Chạy Java 17 demo có stdout xác định để thấy lỗi auto-link theo email và kết quả an toàn khi dùng issuer+subject.
11. Tích hợp Spring Security `OidcUserService` sao cho không có đường fallback `findByEmail` và quyền local được nạp sau exact match.
12. Xử lý không có link, email đổi, tài khoản bị khóa, SCIM deprovision, thay IdP, migration và khôi phục tài khoản.
13. Thực hành test, audit và runbook cho sự cố liên kết sai, thu hồi token/session sau account takeover.

**Phạm vi:** Liên kết tài khoản trong một ứng dụng Java/Spring Security federation. Các ví dụ OIDC là trọng tâm; SAML2, Kerberos, Entra và SCIM được so sánh theo identity contract. Java 17 demo là mô phỏng; Spring Boot 3.3.x/Spring Security 6.3.x sample cần IdP thực để kiểm tra liên thông. Bảo vệ này **khác** việc chỉ xác minh chữ ký token.

## 2. Vấn đề: một email, hai con người và một tài khoản có quyền

Giả sử Orders Portal có account cũ:

~~~text
local_user_id = user-104
tenant_id     = company-A
email         = alice@example.org
authorities   = APP_ORDER_APPROVE
enabled       = true
~~~

Người dùng đăng nhập bằng OIDC tới IdP được phê duyệt, nhận:

~~~json
{
  "iss": "https://idp.partner.example/realms/workforce",
  "sub": "external-999",
  "email": "alice@example.org",
  "email_verified": true
}
~~~

ID Token có thể hoàn toàn hợp lệ, nhưng **external-999** chưa từng được liên kết với `user-104`. Nếu ứng dụng thực hiện:

~~~java
// SAI: đã thấy email trùng là nhận quyền từ local account cũ.
String email = oidcUser.getEmail();
LocalAccount account = accountRepository.findByEmail(email);
createApplicationSession(account);
~~~

thì người đang điều khiển `external-999` có thể được cấp `APP_ORDER_APPROVE` mà không hề chứng minh mình sở hữu `user-104`. Việc IdP đã ký token chỉ xác nhận **external subject** thuộc issuer ấy, không chứng minh nó có quyền kế thừa lịch sử dữ liệu và role của local account.

### 2.1. Ba ranh giới tin cậy

| Câu hỏi | Ai có thể trả lời? | Điều không được suy ra |
| --- | --- | --- |
| Token/Assertion có hợp lệ? | OIDC/SAML/Kerberos validator với trust anchors. | Không tự chứng minh local account ownership. |
| External principal là local user nào? | Approved link repository, provisioning crosswalk và explicit linking proof. | Không suy chỉ từ email hoặc display name. |
| Local user được làm gì? | Local account state, tenant/resource policy và authorization store. | Không tự lấy quyền admin từ email suffix hay tên nhóm của nguồn không tin. |

**Authentication success ≠ account linking success ≠ authorization success.**

## 3. OIDC `email_verified` và `(iss,sub)`: chính xác đến đâu?

OpenID Connect Core 1.0 `5.7` ghi rằng cặp `iss` và `sub` là cơ sở nhận diện bền vững trong phạm vi issuer. Các claims `email`, `preferred_username`, `name`, `phone_number` không có bảo đảm tương tự về tính duy nhất và không bị tái sử dụng.

### 3.1. `email_verified=true` không phải bằng chứng sở hữu local account

Claim `email_verified` có nghĩa IdP đã có hành động kiểm chứng user kiểm soát email **ở thời điểm kiểm chứng**. Tùy trust framework, IdP có thể kiểm chứng bằng email link/OTP hoặc cơ chế tổ chức khác. Claim không tự chứng minh:

- Email này mãi mãi thuộc cùng một người.
- Người đang có mailbox hiện tại cũng là người sở hữu tài khoản nội bộ đã được tạo nhiều năm trước.
- External subject có quyền vào local tenant hoặc inherit local role.
- Email trong local database chưa từng được chuyển cho người khác.
- Account mới có cùng email đã được HR/directory admin phê duyệt gắn vào account cũ.
- Người dùng đã thực hiện MFA/phishing-resistant authentication cần thiết cho hành động nhạy cảm.
- Email không tồn tại dưới nhiều alias/guest objects ở các realms/tenants.

Do đó:

~~~text
email == local.email                 -> chỉ là gợi ý để hiển thị/review
email_verified == true              -> bằng chứng mailbox verification theo contract
(verified_iss, verified_sub) mapped
    to approved local_user_id       -> cơ sở lookup account
~~~

### 3.2. Email tái cấp làm liên kết sai

~~~text
T0: Alice có sub=A7, email=alice@example.org,
    linked local_user_id=user-104.
T1: Alice nghỉ việc, email được giải phóng.
T2: Bob nhận email=alice@example.org, sub=B9.
T3: Bob đăng nhập, email_verified=true.

Auto-link theo email: B9 -> user-104 (SAI)
Lookup theo issuer+sub: B9 chưa linked (ĐÚNG)
~~~

Không cần có lỗ hổng trong chữ ký JWT: **lỗi nằm ở bước mapping**. Đặc biệt nguy hiểm nếu local account cũ chưa được disable do provisioning lỗi.

### 3.3. Cùng email, hai subjects trong một IdP tin cậy

Ngay cả issuer đã được tổ chức tin cậy cũng không có nghĩa mọi subject mang cùng `email` là một người. Có thể tồn tại guest, mailbox reuse, directory drift, email aliases hoặc policy cho phép email tái sử dụng. Nếu `sub` khác, phải coi là external identities khác cho đến khi có chứng cứ liên kết đã được duyệt.

### 3.4. Pairwise subject

OIDC có subject loại `public` và `pairwise`; với `pairwise`, IdP có thể cấp `sub` khác nhau cho những client/sector identifiers khác nhau. Một người thật có thể mang hai `sub` hợp lệ giữa hai applications. Không giải quyết sự khác nhau bằng cách auto-merge theo email; cần trusted migration crosswalk, provisioning anchor hoặc link proof mới.

## 4. Chọn đúng định danh theo từng hệ thống

| Nguồn | Khóa nhận diện phù hợp | Scope/trust cần giữ | Thuộc tính không tự dùng để link |
| --- | --- | --- | --- |
| OIDC | `(iss,sub)` của ID Token đã verify. | Approved issuer/registration; pairwise scope khi migration. | `email`, `name`, `preferred_username`. |
| Microsoft Entra | `iss+sub` theo OIDC; hoặc `tid+oid` theo Entra-specific contract. | Tenant ID, app registration và token trust. | `email`, `upn`, `unique_name`. |
| SAML2 | `persistent NameID` cùng IdP EntityID/SP qualifiers, hoặc immutable directory ID đã ký/phát theo hợp đồng. | IdP, SP, NameID format/qualifiers, tenant. | `emailAddress NameID` và `transient NameID` để nhận diện lâu dài. |
| Kerberos/AD | Approved Kerberos principal+realm; khi liên kết directory, dùng immutable object ID theo contract. | Realm/domain và trust path. | `mail`, UPN, CN, display name. |
| LDAP | objectGUID/immutable anchor theo directory contract. | Directory/forest/source. | DN khi OU move, mail/display name. |
| SCIM | `id` do SCIM service provider cấp; `externalId` do provisioning client cấp. | Provider/connector/provisioning domain/tenant. | `emails.value`, username để tự merge xuyên hệ thống. |
| Local app | `local_user_id` ổn định, không tái cấp. | Tenant, lifecycle, quyền local. | Email làm khóa phân quyền. |

### 4.1. Entra `oid+tid` khác email/UPN

Microsoft giải thích `oid` là object ID của principal trong tenant, `tid` xác định tenant. Email/UPN có thể đổi hoặc tái sử dụng. Cùng người có thể có object khác nhau trong home tenant và resource/guest tenant.

~~~text
(tenant-A, oid-17) = account A
(tenant-B, oid-88) = account B

Same email != same Entra object
Same oid string without tenant scope != approved local user
~~~

Nếu app dùng Entra-specific `(tid,oid)` để correlate nhiều service, đó phải là contract được xây rõ, với issuer/tenant token validation. Với OIDC provider thông thường, ưu tiên `(iss,sub)`.

### 4.2. SAML2 NameID

`persistent NameID` có thể được IdP cấp ổn định trong phạm vi SP/qualifiers khi cấu hình đúng. `transient NameID` không phù hợp làm khóa liên kết lâu dài; `emailAddress NameID` vẫn có vấn đề email đổi/tái cấp.

SAML Assertion được ký hợp lệ vẫn không chứng minh email NameID bằng email local nghĩa là hai account cùng chủ. Bước signature validation **phải xảy ra trước** lookup, nhưng không thay thế link proof.

### 4.3. Kerberos và directory

Principal `alice@EXAMPLE.COM` phải gắn nguồn realm/domain tin cậy. UPN, mail hoặc DN có thể đổi do rename/move. Khi có immutable directory object ID được authoritative source phát và quản trị, dùng nó trong crosswalk tương ứng; hiểu rõ giới hạn khi forest migration, recreate object hoặc rehire.

### 4.4. SCIM `id` và `externalId`

RFC 7643: `id` do SCIM service provider tạo, unique, stable/non-reassignable trong resource set của provider. `externalId` do provisioning client gán, **scoped theo provisioning domain**; không được tự coi là ID toàn cục.

~~~text
connector-A: externalId=hr-1001  -> local-user-A
connector-B: externalId=hr-1001  -> local-user-B

Không dùng externalId=hr-1001 -> một local user chung.
~~~

SCIM `userName`/`emails` có thể dùng cho liên hệ hoặc tìm kiếm theo policy, **không thay thế** authoritative mapping giữa SCIM resource và OIDC `sub`.

## 5. Các kiểu tấn công và lỗi vận hành phổ biến

### 5.1. Pre-hijacking: tạo account trước người thật

Kẻ tấn công có thể tạo local account với email nạn nhân trong một luồng đăng ký yếu, giữ password/session/recovery credential. Khi người thật lần đầu đăng nhập SSO, ứng dụng auto-link theo email vào account đã có. Kẻ tấn công tiếp tục đăng nhập local và truy cập dữ liệu được gắn vào sau này.

**Phòng vệ:** không auto-link local account cũ theo email, không thừa hưởng credential/session của pre-created account và phải có provisioning/reconciliation có proof.

### 5.2. Mailbox tái cấp

Người cũ rời công ty, người mới nhận địa chỉ email, đăng nhập IdP hợp lệ với `email_verified=true`. Nếu local record cũ còn active, email-link cho phép người mới kế thừa dữ liệu/role của người cũ.

**Phòng vệ:** immutable subject/object ID, offboarding disable/revoke, không làm recovery bằng mailbox mới như bằng chứng duy nhất cho quyền lịch sử.

### 5.3. Guest/B2B và nhiều tenants

Một guest object thuộc tenant khác có thể có email của nhân viên. Nếu code chỉ kiểm tra `email.endsWith("@company.example")`, attacker/guest có thể được cấp role. Phải kiểm tra trusted issuer/tenant, immutable principal, local tenant membership; email domain **không chứng minh tenant ownership**.

### 5.4. Chuẩn hóa địa chỉ email quá mức

Đừng bỏ dấu chấm, `+tag` hoặc hạ mọi ký tự của local part theo quy tắc Gmail rồi áp cho mọi domain. Hai địa chỉ khác nhau ở provider khác có thể bị biến thành một. Việc chuẩn hóa domain/canonical email cần quy tắc rõ, nhưng **ngay cả email chuẩn hóa đúng cũng không là account link proof**.

### 5.5. Hai local accounts cùng email

Một dữ liệu legacy có thể có trùng email ở hai tenants hoặc do quá trình migration. Auto-link theo email buộc một kết quả không có bằng chứng, có thể trả user đầu tiên hoặc làm user enumeration. Cách đúng là `LINK_REQUIRED` và review, không tự merge.

### 5.6. IdP đổi issuer/sub khi migration

Chuyển SAML2 → OIDC, thay client/sector hay chuyển tenant có thể đổi immutable identifiers ở phía client. Một script nối bằng email có thể link nhầm hàng loạt. Cần trusted crosswalk theo immutable directory anchor, signed/admin-approved migration manifest, dry-run collision review và audit; nếu thiếu proof thì re-link hoặc manual recovery.

### 5.7. SCIM provisioning race

OIDC login có thể tới trước SCIM Create, hoặc SCIM update email tới trước link. Nếu “chưa thấy link” khiến app fallback tìm email, account takeover xuất hiện đúng lúc distributed systems bị lệch thời gian. Hãy trả `PROVISIONING_PENDING/LINK_REQUIRED`, chờ authoritative mapping, không dùng email làm đường tắt.

## 6. Quy tắc đăng nhập an toàn

**Đầu tiên phải validate protocol**, sau đó lookup exact identity link; không bao giờ lấy email làm fallback tự động.

~~~text
Browser -> OIDC authorization code callback
                |
                v
Spring validates state/nonce, code/token,
iss/aud/signature/expiry, registered client
                |
                v
IdentityKey = (validated issuer, validated subject)
                |
                +--> link exists and active?
                |            |
                |            +--> local account enabled + tenant allowed?
                |                       |
                |                       +--> yes -> issue local Authentication
                |                       +--> no  -> DENY
                |
                +--> no link -> LINK_REQUIRED /
                                  approved new-account provisioning
                |
                +--> conflict -> DENY + manual review
~~~

| Case | Xử lý |
| --- | --- |
| ID Token chưa verify/issuer không tin | REJECT. |
| `iss+sub` có link active tới local account active | Login có thể tiếp tục; kiểm tra quyền. |
| Link trỏ user disabled | DENY; không dùng email tìm user khác. |
| Email trùng local account nhưng `sub` chưa linked | LINK_REQUIRED, không tạo authentication cho account cũ. |
| Subject đã linked user A, callback đòi user B | CONFLICT; không tự chuyển owner. |
| Không có local account và onboarding được duyệt | Có thể tạo **account mới**, ID mới, quyền tối thiểu; khác hoàn toàn link account cũ. |
| Email đổi nhưng `iss+sub` cũ | Giữ linked local user, cập nhật contact qua workflow khác. |
| User deprovisioned | Suspend/revoke local account và session theo policy. |

**Không gọi** `findByEmail(oidcUser.getEmail())` trong OIDC success handler; không thay bằng `findByEmail` sau khi kiểm tra `email_verified=true`.

## 7. Explicit account linking: hai bằng chứng độc lập

Muốn gắn external identity mới tới **local account hiện có**, cần chứng minh người thực hiện kiểm soát **local account ấy** và **external identity được gắn**.

### 7.1. State machine

1. Người dùng đăng nhập vào local account hiện có qua phương thức đủ assurance; server có `local_user_id` trong SecurityContext/session.
2. Người dùng chọn “Liên kết nhà cung cấp danh tính”. Với thay đổi nhạy cảm, yêu cầu **recent reauthentication/step-up MFA** trên local account, không chỉ cookie cũ.
3. Server tạo `LinkIntent` ngẫu nhiên, ngắn hạn, một lần, chứa local ID, session generation, approved provider registration, tenant, anti-CSRF/state, expiry. Không nhận local ID từ HTTP query.
4. Khởi động OIDC Authorization Code + PKCE/state/nonce với IdP từ allowlist, HTTPS redirect URI cố định.
5. Spring/IdP hoàn tất auth; application chỉ dùng issuer/subject từ ID Token **đã verify**, không đọc claim do browser tự truyền.
6. Kiểm tra LinkIntent chưa dùng, chưa hết TTL, đúng provider, đúng local session, đúng tenant và recent reauth còn hiệu lực.
7. Kiểm tra external identity `iss+sub` chưa linked với một local user khác, local account đang ACTIVE.
8. Insert link, consume intent và ghi audit **nguyên tử** trong database; nếu race/unique violation thì rollback/deny.
9. Thông báo chủ local account qua kênh đã được xác minh và có lịch sử audit/rollback policy; rotate session ID theo chính sách.
10. Không tự cấp thêm `APP_ADMIN_EXPORT` hay đổi tenant membership chỉ nhờ tạo link.

~~~text
Existing local session + recent MFA
              |
              v
   Create one-time LinkIntent
              |
              v
Approved IdP login (state/nonce/PKCE)
              |
              v
Verified (issuer, subject)
              |
              +-- wrong session/expired/used -> DENY
              +-- already linked to another -> CONFLICT
              +-- local account disabled  -> DENY
              |
              v
     Atomic INSERT link + consume intent
              |
              v
  Audit + notify + preserve local authorization
~~~

### 7.2. Vì sao email OTP chưa đủ?

Email OTP xác minh quyền kiểm soát mailbox **hiện tại**. Khi mailbox được tái cấp, người mới nhận OTP nhưng không sở hữu account lịch sử của người cũ. OTP có thể hỗ trợ recovery tùy mức rủi ro, nhưng **không phải bằng chứng duy nhất để merge account có quyền**. Nếu người dùng mất local login, phải đi qua quy trình recovery có kiểm chứng directory/HR immutable identity/approval.

### 7.3. Replay, CSRF, account switching

- LinkIntent phải random, đủ entropy, TTL ngắn và one-time.
- Không cho callback đăng nhập OIDC của user khác thay local principal trong session cũ mà vẫn giữ quyền cũ.
- `state`/`nonce` của OIDC và intent binding có trách nhiệm khác nhau, không bỏ một cái chỉ vì có cái kia.
- Khi reauthentication step-up xong, kiểm tra cùng local user ID, không chỉ email.
- Session fixation protection và CSRF vẫn cần cho browser.
- Các hoạt động unlink/relink cũng là nhạy cảm, cần reauth/audit/revocation.

## 8. Thiết kế model dữ liệu và ràng buộc giao dịch

### 8.1. Local user ID không phụ thuộc email

~~~sql
CREATE TABLE app_user (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    email_contact VARCHAR(320),
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE external_identity_link (
    id UUID PRIMARY KEY,
    local_user_id UUID NOT NULL REFERENCES app_user(id),
    tenant_id UUID NOT NULL,
    provider_registration VARCHAR(128) NOT NULL,
    source_issuer VARCHAR(512) NOT NULL,
    external_subject VARCHAR(512) NOT NULL,
    proof_kind VARCHAR(64) NOT NULL,
    status VARCHAR(16) NOT NULL CHECK (
        status IN ('ACTIVE','SUSPENDED','REVOKED')
    ),
    linked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revoked_at TIMESTAMPTZ,
    UNIQUE (
        tenant_id, provider_registration,
        source_issuer, external_subject
    )
);

CREATE INDEX external_link_by_local_user
    ON external_identity_link(local_user_id);
~~~

Bảng dùng PostgreSQL minh họa. Cần thêm:
- Ràng buộc `tenant_id` của link khớp account (composite foreign key/trigger hoặc kiểm tra atomic trong service); không nhận tenant từ client.
- Chính sách unique toàn cục hoặc tenant-scoped rõ khi **một external subject không được phép** gắn nhiều accounts ở tenants khác nhau.
- Không reassign `external_subject` khi status=REVOKED; re-link sau revocation cần approval/audit riêng.
- Không lowercase/canonicalize subject tùy ý; subject ID và issuer phải theo exact comparison của provider contract.
- `provider_registration` là trust configuration ID, không phải label do browser gửi.
- Không dùng email làm PK hoặc key kiểm tra quyền; có thể index email để hỗ trợ tìm kiếm **không tạo linkage**.

### 8.2. Giao dịch tạo link

~~~sql
BEGIN;

SELECT tenant_id, enabled
FROM app_user
WHERE id = :authenticated_local_user_id
FOR UPDATE;

-- Server phải xác nhận account active, tenant đúng;
-- LinkIntent đã chứng minh recent local reauth + OIDC callback.
-- Consume LinkIntent atomically và insert link trong cùng
-- transaction khi cả hai cùng nằm trong database.

INSERT INTO external_identity_link (
    id, local_user_id, tenant_id, provider_registration,
    source_issuer, external_subject, proof_kind, status
) VALUES (
    :link_id, :authenticated_local_user_id, :approved_tenant,
    :approved_registration, :validated_issuer, :validated_sub,
    'RECENT_LOCAL_REAUTH_PLUS_OIDC', 'ACTIVE'
);

COMMIT;
~~~

Nếu gặp UNIQUE violation, **không** dùng `ON CONFLICT DO UPDATE local_user_id=:new_user`. Hãy rollback, ghi conflict, review. Với intent ở Redis và link ở SQL, cần thiết kế atomic consumption/outbox/compensation phù hợp; một transaction SQL không làm hai stores trở thành exactly-once.

### 8.3. Directory và SCIM crosswalk

~~~text
(approved_scim_connector, externalId)
              |
              | administrative verified mapping
              v
         local_user_id
              ^
              | approved identity link
(validated_oidc_issuer, validated_oidc_sub)
~~~

Không tự suy `externalId == sub`, hoặc `SCIM.email == IDToken.email` là bằng chứng. Cần authoritative mapping contract từ directory/IdP và kiểm tra lifecycle `active=false`, reassignment, rehire.

## 9. Java 17 độc lập: chứng minh lỗ hổng và giải pháp

Mã sau **chạy offline**, có một local account Alice và hai OIDC subjects cùng email. Chương trình cố ý mô phỏng một hàm **không an toàn** để cho thấy takeover, rồi triển khai lookup bằng issuer+subject và liên kết có proof. Các boolean `validated`/`recentReauth` là fixture trong chương trình; **không được lấy từ HTTP request trong production**.

### 9.1. `AccountLinkingSafetyDemo.java`

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public final class AccountLinkingSafetyDemo {

    record ExternalKey(String issuer, String subject) {}
    record ExternalUser(
        String issuer, String subject, String email,
        boolean emailVerified, boolean tokenValidated) {}
    record Account(String id, String email, boolean active) {}
    record LinkProof(
        String localId, boolean recentReauth,
        boolean secondIdpVerified, boolean sessionAndStateBound,
        long expiresAt, String nonce) {}

    static final class Service {
        private final String approvedIssuer =
            "https://idp.partner.example/realms/workforce";
        private final Map<String, Account> accounts = new HashMap<>();
        private final Map<ExternalKey, String> links = new HashMap<>();
        private final Set<String> usedProofs = new HashSet<>();

        void add(Account a) { accounts.put(a.id(), a); }

        // LỖ HỔNG, chỉ dùng để minh họa tại sao không làm thế.
        String unsafeByEmail(ExternalUser x) {
            for (Account a : accounts.values()) {
                if (a.email().equalsIgnoreCase(x.email())) {
                    return "AUTH:" + a.id();
                }
            }
            return "NO_MATCH";
        }

        String safeLogin(ExternalUser x) {
            if (!x.tokenValidated()) return "REJECT_UNVERIFIED";
            if (!approvedIssuer.equals(x.issuer()))
                return "REJECT_UNTRUSTED";
            String localId = links.get(
                new ExternalKey(x.issuer(), x.subject()));
            if (localId == null) return "LINK_REQUIRED";
            Account account = accounts.get(localId);
            if (account == null || !account.active())
                return "DENY_DISABLED";
            return "AUTH:" + account.id();
        }

        String link(ExternalUser x, LinkProof p, long now) {
            if (!x.tokenValidated()
                    || !approvedIssuer.equals(x.issuer()))
                return "REJECT_UNTRUSTED";
            if (!p.recentReauth() || !p.secondIdpVerified()
                    || !p.sessionAndStateBound()
                    || now >= p.expiresAt()
                    || usedProofs.contains(p.nonce()))
                return "PROOF_REQUIRED";
            Account account = accounts.get(p.localId());
            if (account == null || !account.active())
                return "DENY_DISABLED";
            ExternalKey key = new ExternalKey(x.issuer(), x.subject());
            String owner = links.get(key);
            if (owner != null && !owner.equals(p.localId()))
                return "LINK_CONFLICT";

            usedProofs.add(p.nonce());
            if (owner != null) return "ALREADY_LINKED";
            links.put(key, p.localId());
            return "LINKED";
        }
    }

    public static void main(String[] args) {
        Service s = new Service();
        s.add(new Account("u-104", "alice@example.org", true));
        s.add(new Account("u-205", "bob@example.org", true));

        String issuer = "https://idp.partner.example/realms/workforce";
        ExternalUser alice = new ExternalUser(
            issuer, "subject-A7", "alice@example.org", true, true);
        ExternalUser attacker = new ExternalUser(
            issuer, "subject-B9", "alice@example.org", true, true);

        System.out.println("unsafeAttacker=" +
            s.unsafeByEmail(attacker));
        System.out.println("safeAttacker=" +
            s.safeLogin(attacker));

        LinkProof weak = new LinkProof(
            "u-104", false, true, true, 200, "nonce-one");
        System.out.println("weakProof=" +
            s.link(alice, weak, 100));

        LinkProof approved = new LinkProof(
            "u-104", true, true, true, 200, "nonce-two");
        System.out.println("linkAlice=" +
            s.link(alice, approved, 100));
        System.out.println("loginAlice=" +
            s.safeLogin(alice));

        ExternalUser renamed = new ExternalUser(
            issuer, "subject-A7", "alice.new@example.org",
            true, true);
        System.out.println("emailChange=" +
            s.safeLogin(renamed));
        System.out.println("attackerStillUnlinked=" +
            s.safeLogin(attacker));

        LinkProof otherOwner = new LinkProof(
            "u-205", true, true, true, 200, "nonce-three");
        System.out.println("linkOtherOwner=" +
            s.link(alice, otherOwner, 100));
        System.out.println("proofReplay=" +
            s.link(attacker, approved, 100));

        ExternalUser unverified = new ExternalUser(
            issuer, "subject-fake", "alice@example.org",
            true, false);
        System.out.println("invalidToken=" +
            s.safeLogin(unverified));
    }
}
~~~

### 9.2. Lệnh chạy

~~~bash
javac --release 17 AccountLinkingSafetyDemo.java
java AccountLinkingSafetyDemo
~~~

**Stdout dự kiến chính xác:**

~~~text
unsafeAttacker=AUTH:u-104
safeAttacker=LINK_REQUIRED
weakProof=PROOF_REQUIRED
linkAlice=LINKED
loginAlice=AUTH:u-104
emailChange=AUTH:u-104
attackerStillUnlinked=LINK_REQUIRED
linkOtherOwner=LINK_CONFLICT
proofReplay=PROOF_REQUIRED
invalidToken=REJECT_UNVERIFIED
~~~

**Giải thích:**

- `unsafeAttacker`: một attacker subject có email trùng nhận quyền account Alice nếu app auto-link theo email.
- `safeAttacker`: không có link `issuer+sub` ⇒ không thể đăng nhập dưới local account cũ.
- `weakProof`: thiếu recent reauth local ⇒ không tạo link.
- `linkAlice`: chỉ tạo link khi có proof về local account và external subject.
- `emailChange`: địa chỉ đổi nhưng `issuer+subject` không đổi ⇒ local account vẫn giống.
- `linkOtherOwner`: subject đã thuộc Alice không được chuyển sang Bob.
- `proofReplay`: nonce đã dùng không thể tái sử dụng để liên kết attacker.
- `invalidToken`: token chưa xác minh không bao giờ đủ để lookup/link.

**Giới hạn nghiêm trọng:** Đây là mô phỏng, không dùng cho production. Trong code không có HTTPS, OIDC token verification thật, tenant, database transaction hay distributed nonce store. `HashMap` và `HashSet` không chống race giữa nhiều nodes. Các cờ proof phải do server xác định qua validated sessions/callbacks, tuyệt đối không do browser tự khai.

## 10. Spring Security OIDC: từ chối tài khoản chưa liên kết

Một Spring Boot sample có thể cấu hình `OidcUserService` để nạp user từ IdP đã xác minh, sau đó chỉ cho phép exact-match `iss+sub` trong một store liên kết. Demo dưới đây dùng **một linked subject đã được admin cấu hình** để không ngụ ý tự link theo email. Với production, thay cấu hình tĩnh bằng repository DB chứa local account active, tenant, approved identity links và roles.

### 10.1. Cấu trúc project

~~~text
safe-oidc-link/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/safelink/
    │   ├── SafeLinkApplication.java
    │   ├── SafeLinkSecurityConfig.java
    │   └── MeController.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'safe-oidc-link'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

`src/main/java/com/example/safelink/SafeLinkApplication.java`:

~~~java
package com.example.safelink;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SafeLinkApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafeLinkApplication.class, args);
    }
}
~~~

### 10.2. application.yml

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          workforce:
            provider: workforce
            client-id: "${OIDC_CLIENT_ID}"
            client-secret: "${OIDC_CLIENT_SECRET}"
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile,email
        provider:
          workforce:
            issuer-uri: "${OIDC_ISSUER}"

app:
  linked:
    approved-issuer: "${APP_APPROVED_ISSUER:}"
    approved-subject: "${APP_APPROVED_SUBJECT:}"
    local-enabled: "${APP_LOCAL_ENABLED:false}"

server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
~~~

Các biến môi trường phải lấy từ cấu hình **đã được admin phê duyệt**, không đến từ query của client. Demo chỉ cho phép một issuer+subject có local account active do admin cấu hình; nếu cấu hình thiếu thì **deny by default**.

### 10.3. SafeLinkSecurityConfig.java

~~~java
package com.example.safelink;

import java.util.Set;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SafeLinkSecurityConfig {

    @Bean
    OAuth2UserService<OidcUserRequest, OidcUser> linkedOidcUserService(
            @Value("${app.linked.approved-issuer}")
            String approvedIssuer,
            @Value("${app.linked.approved-subject}")
            String approvedSubject,
            @Value("${app.linked.local-enabled}")
            boolean localEnabled) {

        OidcUserService delegate = new OidcUserService();

        return userRequest -> {
            // Spring đã validate OIDC trước khi delegate trả user.
            OidcUser external = delegate.loadUser(userRequest);
            String issuer = external.getIdToken()
                .getClaimAsString("iss");
            String subject = external.getSubject();

            // KHÔNG gọi findByEmail(external.getEmail())!
            if (!localEnabled
                    || approvedIssuer.isBlank()
                    || approvedSubject.isBlank()
                    || !approvedIssuer.equals(issuer)
                    || !approvedSubject.equals(subject)) {
                throw new OAuth2AuthenticationException(
                    new OAuth2Error("identity_not_linked")
                );
            }

            // Role này tượng trưng cho local role đã approve.
            // Không lấy từ email/UPN/displayName do IdP phát.
            Set<GrantedAuthority> localAuthorities = Set.of(
                new SimpleGrantedAuthority("APP_ORDER_READ")
            );

            return new DefaultOidcUser(
                localAuthorities,
                external.getIdToken(),
                external.getUserInfo()
            );
        };
    }

    @Bean
    SecurityFilterChain webSecurity(
            HttpSecurity http,
            OAuth2UserService<OidcUserRequest, OidcUser>
                linkedOidcUserService) throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .requestMatchers("/me").hasAuthority("APP_ORDER_READ")
                .anyRequest().authenticated()
            )
            .oauth2Login(oauth2 -> oauth2
                .userInfoEndpoint(info -> info
                    .oidcUserService(linkedOidcUserService)
                )
            )
            .build();
    }
}
~~~

Giải thích:
- `OidcUserService` lấy principal đã trải qua OIDC protocol validation do Spring client thực hiện, không decode JWT bằng tay.
- `iss` được đọc từ ID Token, `sub` từ `OidcUser`; chỉ khi **cả hai exact-match** và local account active (demo `localEnabled`) thì mới cho login.
- `email` không tham gia lookup. Dù có `email_verified=true`, external subject chưa linked vẫn thất bại.
- Authorities được lấy từ approved local profile (demo hard-coded `APP_ORDER_READ` để minh họa). Production phải query local DB và kiểm tra active/tenant/role thật; **không** hardcode quyền cho tất cả OIDC users.
- `DefaultOidcUser` vẫn có OIDC subject; nếu cần principal name là local user ID cho business logic, hãy tạo lớp principal/mapping có audit riêng, không tự đổi subject thành email rồi coi là local ID.
- Nếu subject đã bị revoke, repository production phải deny và hủy session/token theo policy.
- Bài demo **không có UI liên kết tài khoản**. Thêm UI phải theo explicit linking flow mục 7 chứ không để OIDC callback tự link.
- CSRF, state, nonce, issuer, audience, signature, session fixation và PKCE phải kiểm thử với IdP thật và version đã chọn; không mặc định tắt bảo vệ khi custom user service.

### 10.4. MeController.java

~~~java
package com.example.safelink;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {

    @GetMapping("/")
    public Map<String, String> home() {
        return Map.of(
            "signInUrl", "/oauth2/authorization/workforce",
            "status", "Only preapproved issuer+subject may sign in");
    }

    @GetMapping("/me")
    public Map<String, String> me(Authentication authentication) {
        return Map.of(
            "externalSubject", authentication.getName(),
            "permission", "APP_ORDER_READ"
        );
    }
}
~~~

### 10.5. Chạy và thử nghiệm

~~~bash
./gradlew bootRun
~~~

Ví dụ biến môi trường thử nghiệm:

~~~text
OIDC_ISSUER=https://idp.partner.example/realms/workforce
OIDC_CLIENT_ID=approved-client-id
OIDC_CLIENT_SECRET=secret-from-vault
APP_APPROVED_ISSUER=https://idp.partner.example/realms/workforce
APP_APPROVED_SUBJECT=subject-approved-from-real-idp
APP_LOCAL_ENABLED=true
~~~

Các giá trị `.example` là minh họa; phải có IdP thật, metadata OIDC, client registration, HTTPS callback và subject đã được phê duyệt. Code không khởi chạy một IdP. Kết quả `/me` phụ thuộc subject/claims của IdP thật.

Các bước test:
1. Subject approved được đăng nhập, có `APP_ORDER_READ`.
2. Subject khác có cùng email bị lỗi `identity_not_linked`; không được tự nối account.
3. Subject approved đổi email nhưng không đổi `sub`, vẫn đúng link.
4. Tắt `APP_LOCAL_ENABLED`, subject approved cũng bị DENY.
5. Issuer bị đổi/sai registration, framework/lookup từ chối.
6. OIDC state/nonce/signature/audience sai, Spring reject trước khi map local.
7. Tài khoản chưa linked phải được hướng sang onboarding/explicit link ngoài login flow, không tự tạo quyền.

**Lưu ý version:** Các snippet này dựa API Spring Security 6.x; nâng version hoặc thay OIDC client thì phải build/test lại. Bảo mật production còn cần persistent DB linking, audit, role lifecycle, disable user, tenant isolation, session revocation, key rotation và security patching.

## 11. Spring SAML/Kerberos/LDAP/SCIM: áp cùng nguyên tắc

### 11.1. SAML2

Với Spring `saml2Login`:
- Verify Assertion signature, issuer, audience, recipient, InResponseTo và điều kiện thời gian.
- Dùng approved persistent identifier có scope theo IdP/SP; chú ý NameID format và qualifiers.
- Nếu Identity Provider chỉ phát `mail`/email NameID, **không auto-link local user cũ**; yêu cầu immutable directory ID hoặc approved proof flow.
- Không tin email user tự truyền, ngay cả sau khi format XML nhìn có vẻ đúng.
- Quyền từ SAML attributes cần trust contract riêng với local authorization.

### 11.2. Kerberos

Kerberos realm/principal và service ticket xác thực là một nguồn external identity. Khi cần nối tới một local account dùng trước OIDC:
- Không tự gộp theo UPN/email.
- Sử dụng approved directory object anchor và realm/scope.
- Migration Kerberos → OIDC cần crosswalk từ authoritative directory hoặc explicit two-method proof.
- Account disabled, group/tenant membership và local permissions vẫn phải check.

### 11.3. SCIM directory provisioning

SCIM có thể tạo local account mới dựa trên authoritative `externalId` đã scope theo connector. Nếu OIDC login tới trước SCIM link, không tìm email để tự đăng nhập dưới account cũ; trả trạng thái provisioning pending hoặc yêu cầu help desk. Khi SCIM `active=false`, phải revoke local account/session theo chính sách; không chỉ sửa email contact.

### 11.4. Không coi chuyển email là chuyển identity

Một account linked OIDC có thể đổi email liên hệ sau khi xác minh contact. Nó vẫn mang `(iss,sub)` cũ. Trường hợp subject mới và email cũ giống nhau không phải “cập nhật nhỏ” mà là **thay identity binding**, cần explicit link/migration proof.

## 12. Thu hồi, recovery và migration

### 12.1. Unlink

Yêu cầu recent reauthentication, CSRF, xác nhận chủ local account và đánh giá việc người dùng còn phương thức đăng nhập nào khác. Khi unlink, revoke cached sessions/refresh tokens liên quan, audit và thông báo chủ tài khoản. Không cho một session yếu tự xóa mọi recovery method.

### 12.2. Người dùng mất quyền vào phương thức cũ

Mail OTP hiện tại **không đủ** để chứng minh quyền với local account cũ nếu mailbox có thể đã tái cấp. Quy trình manual recovery cần:
1. Nhận yêu cầu có audit; tránh user enumeration.
2. Xác minh authoritative HR/directory immutable ID và chính sách nhân sự.
3. Sử dụng identity proof/step-up/approval theo mức rủi ro.
4. Verify external subject mới qua IdP tin cậy.
5. Review old links, disable stale credentials, revoke sessions/token có thể bị attacker chiếm.
6. Commit link mới với unique constraint, audit và notification.

### 12.3. IdP migration

~~~text
Old SAML: issuer=old-idp, persistent NameID=p-17
New OIDC: iss=new-idp, sub=s-90
Local: user-104
~~~

Chỉ chuyển khi có trusted crosswalk (immutable HR/directory object), quá trình double-auth proof hoặc administrator approval có kiểm chứng. Không chạy migration script join `old.email=new.email` mà thiếu proof.

### 12.4. Email reuse và rehire

Người mới nhận địa chỉ cũ phải có local account **mới** nếu không có bằng chứng đây là cùng identity được tổ chức khôi phục. Người được rehired có thể cần account mới hoặc reactivation theo policy; sự trùng email không tự quyết định. Local account cũ bị disable không được auto-enabled bởi external login.

## 13. Authorization và session sau link

Một link có thể đúng nhưng vẫn phải xét:
- User active/locked/revoked, credentials/session age;
- Local tenant membership và resource tenant isolation;
- GrantedAuthorities từ nguồn được duyệt;
- Object-level authorization (chủ sở hữu của order/report);
- MFA/step-up cho resource nhạy cảm;
- Session fixation/CSRF/SameSite cookies và logout;
- Logout/revocation khi link bị xóa hoặc account bị disabled.

**MFA của attacker trên tài khoản attacker không chứng minh hắn sở hữu local account của nạn nhân.** `email_verified=true` và MFA mạnh trên external login vẫn không bù cho thiếu account-link proof.

## 14. Kiểm thử tích hợp

| ID | Tình huống | Kết quả cần có |
| --- | --- | --- |
| I01 | Valid OIDC `iss+sub` đã linked, local active. | Login đúng local user. |
| I02 | Email trùng local, subject khác. | LINK_REQUIRED, không auto-login. |
| I03 | `email_verified=true` nhưng chưa linked. | Vẫn LINK_REQUIRED. |
| I04 | Email đổi nhưng issuer/sub không đổi. | Giữ local identity. |
| I05 | Hai subjects trong cùng issuer dùng một email. | Không tự merge. |
| I06 | Cùng subject string ở hai issuers. | Không map chung. |
| I07 | Nạn nhân nghỉ, mailbox tái cấp. | Chủ mới không kế thừa local account cũ. |
| I08 | Attacker pre-register local account bằng email nạn nhân. | SSO nạn nhân không tự gắn account attacker. |
| I09 | Guest Entra cùng email nhân viên. | Không cross-tenant/guest takeover. |
| I10 | Entra `tid` khác. | Không coi cùng oid-scope. |
| I11 | Pairwise sub đổi do client/sector migration. | Migration có proof, không join email. |
| I12 | SAML `persistent NameID` có approved IdP/SP scope. | Lookup đúng link contract. |
| I13 | SAML emailAddress NameID. | Không dùng như immutable link key. |
| I14 | SAML transient NameID. | Không tạo persistent link từ transient value. |
| I15 | Kerberos UPN/email thay đổi. | Directory immutable ID mapping giữ local account. |
| I16 | LDAP DN đổi do OU move. | Không tự tạo account mới từ DN khác. |
| I17 | Hai SCIM connectors cùng externalId. | Không trộn provisioning domains. |
| I18 | SCIM Create chưa tới, OIDC đã login. | PROVISIONING_PENDING/LINK_REQUIRED, không email fallback. |
| I19 | SCIM active=false. | Disable/revoke theo lifecycle. |
| I20 | Link request chưa reauth local. | PROOF_REQUIRED. |
| I21 | Link intent đã hết TTL. | Reject. |
| I22 | Link callback session generation khác. | Reject, chống account switching. |
| I23 | Replay state/nonce hoặc LinkIntent. | Reject. |
| I24 | External subject đã linked user A; user B xin link. | CONFLICT. |
| I25 | Concurrent linking cùng subject. | Unique constraint và atomic guard; không double-link. |
| I26 | OIDC signature/issuer/audience/nonce sai. | Framework reject trước lookup. |
| I27 | Browser tự đặt `iss/sub/local_user_id` trong query. | Không tin, reject. |
| I28 | IdP trả user có local account disabled. | DENY. |
| I29 | Existing link có local role READ nhưng token claims admin. | Không tự cấp APP_ADMIN_EXPORT. |
| I30 | Tenant A linked user truy cập resource B. | DENY resource ownership. |
| I31 | Alias/dot/plus normalization khiến hai emails khớp. | Không dùng email normalization làm link. |
| I32 | Hai local accounts có email giống nhau. | Không auto chọn account thứ nhất. |
| I33 | Attacker dùng email OTP của mailbox tái cấp để claim local account cũ. | Không cho merge chỉ bằng OTP. |
| I34 | Link được tạo rồi email đổi trong IdP. | Exact `iss+sub` vẫn login đúng. |
| I35 | Migration chưa có trusted crosswalk nhưng email trùng. | Deny/manual recovery. |
| I36 | Migration có trusted immutable ID crosswalk. | Reviewed/atomic link, audit. |
| I37 | Link đã bị revoke nhưng session cũ còn sống. | Session/token revocation theo policy. |
| I38 | Đăng nhập với issuer chưa allowlist, email giống admin. | Reject issuer, không link. |
| I39 | Logs chứa raw ID Token/subject/email trong metrics. | QA fail/redaction. |
| I40 | Provider/client cấu hình thay nhưng link proof chưa duyệt. | Không chuyển account owner im lặng. |

### 14.1. Lab A — chạy Java 17

1. Chạy `AccountLinkingSafetyDemo` và quan sát `unsafeAttacker=AUTH:u-104`.
2. So sánh `safeAttacker=LINK_REQUIRED` và `weakProof=PROOF_REQUIRED`.
3. Kiểm tra `emailChange=AUTH:u-104` dù email khác.
4. Kiểm tra conflict khi gắn subject đã thuộc user khác.
5. Thảo luận vì sao demo chỉ minh họa cơ chế, không được dùng trực tiếp làm auth server.

### 14.2. Lab B — với hai OIDC subjects

1. Cấu hình IdP test có hai accounts cùng email (khi provider cho phép), nhưng `sub` khác.
2. Preapprove link subject A, giữ subject B không linked.
3. Đăng nhập A thành công, B thất bại dù email giống.
4. Đổi email A, xác nhận A vẫn linked chính xác.
5. Disable local account và xác nhận production repo từ chối.
6. Thử replay OIDC callback, link intent expired và concurrent link to test.

### 14.3. Lab C — SCIM, guest và migration

1. Tạo SCIM resources từ hai provisioning clients trùng `externalId`.
2. Thử email reuse, guest Entra tenant và aliases.
3. Tạo migration crosswalk theo immutable IDs với audit/dry-run.
4. Kiểm tra không có email join trong migration SQL.
5. Revoke link và sessions khi incident được phát hiện.

## 15. Monitoring và cảnh báo

Metric gợi ý (không tự động có trong Spring):

~~~text
identity_login_total{provider,result}
identity_link_lookup_total{provider,result}
identity_link_approval_total{provider,result}
identity_link_conflict_total{provider}
identity_link_duplicate_email_total{provider}
identity_link_recovery_total{status}
identity_subject_migration_total{provider,status}
identity_deprovision_total{connector,result}
identity_revocation_total{reason}
~~~

Không sử dụng email, `sub`, user ID hoặc raw token làm metric labels vì rò PII/high cardinality. Audit record chỉ dùng opaque references/hashed subject theo retention policy.

Alert cần ưu tiên: cùng email xuất hiện với nhiều issuers/subjects; link owner bị thay; đột biến link failures; SCIM externalId đổi; account disabled vẫn login; role admin xuất hiện chỉ sau cập nhật email; migration collision.

## 16. Runbook khi phát hiện chiếm tài khoản do email auto-link

1. **Khóa đường auto-link** theo email ở login/migration/onboarding; nếu có thể, giữ những đăng nhập qua exact links vốn an toàn.
2. **Xác định phạm vi** qua audit link events và local user IDs, không chỉ truy vấn email.
3. **Thu hồi** sessions, refresh tokens, API keys, OAuth authorizations và suspect external links theo chính sách.
4. **Lưu bằng chứng** (audit, immutable IDs, provisioning history, token metadata đã redacted) phục vụ điều tra.
5. **Xác minh chủ sở hữu** bằng authoritative HR/directory immutable IDs, chứ không chỉ mailbox hiện tại.
6. **Khôi phục** đúng local user/tenant/roles theo quy trình review, rotate secrets và force reauthentication.
7. **Thông báo** cho chủ tài khoản và đội an ninh theo policy, không làm lộ dữ liệu cá nhân.
8. **Rà tất cả liên kết trước đó** được tạo bằng email và mọi migration script có email join.
9. **Sửa hệ thống** bằng exact keys, proof flow, database unique constraints, fail-closed response và regression tests.
10. **Theo dõi hồi quy**: tăng `LINK_REQUIRED` sau khi bỏ auto-link là điều có thể dự kiến; không bật lại auto-link để giảm ticket hỗ trợ.

## 17. Những sai lầm cần tránh

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| “OIDC email_verified true nên đủ.” | Mailbox hiện tại không chứng minh account lịch sử. | Existing link/explicit proof. |
| “Email unique ở local DB nên không có collision.” | Có thể cùng email nhưng hai chủ ở thời điểm khác. | Local ID bất biến. |
| “Chỉ cần token có chữ ký.” | Ký bởi issuer không đồng nghĩa sở hữu local user. | Separate identity linking. |
| “MFA ở IdP tự giúp link admin.” | Attacker MFA tài khoản attacker vẫn chiếm được account. | Recent local reauth + second IdP proof. |
| “SCIM externalId unique mọi nơi.” | Trùng giữa provisioning domains. | Scope theo connector. |
| “SAML email NameID luôn ổn định.” | Email đổi và tái cấp. | Persistent NameID/immutable ID theo contract. |
| “Entra email/UPN là primary key.” | Thay đổi/tái sử dụng dẫn tới takeover. | Entra tid+oid hoặc OIDC iss+sub theo contract. |
| “Nếu không thấy link thì findByEmail.” | Backdoor takeover. | LINK_REQUIRED. |
| “ON CONFLICT đổi local_user_id.” | Auto-transfer account owner. | Unique + rollback/review. |
| “Người có email OTP được nhận lịch sử user cũ.” | Mailbox recycling takeover. | High-assurance recovery và authoritative source. |
| “Đổi email thì đổi account.” | Mất dữ liệu, account mix-up. | Giữ local ID + external key. |
| “Unlink là đủ.” | Attacker có thể vẫn giữ session/token. | Revoke toàn bộ credentials liên quan. |
| “Tài khoản đã linked thì bỏ qua role.” | Privilege escalation. | Local active/tenant/resource authorization. |

## 18. Checklist production

- [ ] Không dùng `findByEmail` để nối một OIDC/SAML login tới local account đã có.
- [ ] Identity key có issuer/realm/connector source và stable subject/immutable ID đã được verify.
- [ ] OIDC `iss+sub`, Entra `tid+oid`, SAML NameID qualifiers và SCIM source-scope được dùng đúng contract.
- [ ] Email/email_verified là contact metadata, không là account ownership proof.
- [ ] OIDC/SAML protocol validators kiểm tra issuer/audience/signature/time/state/nonce trước linking.
- [ ] Local user ID không tái cấp; đổi email không thay local identity.
- [ ] Existing local account bị disable hoặc tenant sai thì DENY, không fallback sang email.
- [ ] Auto-provision new account nếu có phải tách khỏi linking existing account và cấp quyền tối thiểu.
- [ ] Link mới yêu cầu recent local reauthentication, CSRF, external IdP proof và short-lived one-time intent.
- [ ] Database unique constraints/transaction ngăn race và chuyển owner trái phép.
- [ ] Không cho client quyết định local ID/tenant/issuer từ query tùy ý.
- [ ] Unlink/relink/migration có audit, notification, approval và session/token revocation.
- [ ] SCIM `active=false`, mailbox reuse, guest, alias và pairwise sub migration đã test.
- [ ] Recovery account cũ cần authoritative proof, không chỉ email OTP hiện tại.
- [ ] APP_ADMIN_EXPORT và các role cao chỉ đến từ local authorization và step-up policy.
- [ ] Không log token, subject, mailbox và credentials trong hệ thống quan sát chung.
- [ ] Có anomaly monitoring cho duplicate email, cross-tenant link attempts và subject/issuer changes.
- [ ] Chạy tests I01–I40 hoặc coverage tương đương ở staging.
- [ ] Cập nhật Spring/OIDC dependencies theo bản bảo mật còn được duy trì và build/test lại version thực.

## Ghi nhớ

> **Một email giống nhau không phải bằng chứng hai account thuộc cùng người, kể cả `email_verified=true`.** Đăng nhập federation phải dùng **external identity key đã được xác minh và đã có link**, điển hình OIDC `(iss,sub)`. Tạo link mới vào một local account cũ phải có **proof từ chính local account + proof từ external IdP + intent dùng một lần + giao dịch nguyên tử**. Khi email đổi, mailbox tái cấp, IdP migration hoặc provisioning trễ, hãy **fail closed/review**, không tự ghép theo email.

### Tài liệu chính thức và hướng dẫn

- [OpenID Connect Core 1.0 `5.7 — Claim Stability and Uniqueness](https://openid.net/specs/openid-connect-core-1_0.html#ClaimStability): `iss+sub` ổn định trong scope; email không được bảo đảm duy nhất hoặc không tái sử dụng; `email_verified` có nghĩa giới hạn.
- [OpenID Connect Core 1.0 `8 — Subject Identifier Types](https://openid.net/specs/openid-connect-core-1_0.html#SubjectIDTypes): public/pairwise subjects.
- [RFC 7643 — SCIM Core Schema](https://www.rfc-editor.org/rfc/rfc7643.html): `id` stable, `externalId` scoped theo provisioning domain.
- [Microsoft Entra — ID Token Claims Reference](https://learn.microsoft.com/en-us/entra/identity-platform/id-token-claims-reference): `oid`, `tid`, `sub` và các trường email/UPN mutable.
- [Microsoft Entra — Access Token Claims Reference](https://learn.microsoft.com/en-us/azure/active-directory/develop/access-token-claims-reference): nhận diện user/tenant dựa immutable ID, không dùng email/UPN làm authorization key.
- [Spring Security — OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): `OidcUserService`, `DefaultOidcUser` và identity/authority mapping.
- [Spring Security — OAuth2/OIDC Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/index.html): OIDC registration, Authorization Code và callback.
- [OWASP — Email Validation and Verification Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Email_Validation_and_Verification_Cheat_Sheet.html): normalization, email change, account takeover.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): recovery, reauthentication, MFA và authorization boundaries.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): cookies, session lifetime, fixation và revocation.
- [OASIS — SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): SAML NameID formats và qualifiers.
