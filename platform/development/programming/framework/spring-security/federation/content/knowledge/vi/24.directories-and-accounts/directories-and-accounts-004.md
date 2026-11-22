# Cấp phát tài khoản khi đăng nhập lần đầu và mô hình Just-in-Time provisioning

## 1. Vấn đề: IdP đã xác thực nhưng ứng dụng chưa có người dùng

Trong hệ thống **Spring Security - federation**, tổ chức thường dùng OpenID Connect (OIDC), SAML 2.0 hoặc CAS để xác thực tập trung. Sau khi xác thực thành công, ứng dụng Spring Security có thể nhận một danh tính do IdP tin cậy công bố. Tuy nhiên, **danh tính liên kết (federated identity)** khác với **tài khoản cục bộ (local account)**: ứng dụng vẫn cần một account ID để quản lý dữ liệu, trạng thái, tenant, quyền truy cập, hồ sơ và lịch sử audit.

Giả sử nhân viên Lan lần đầu đăng nhập ứng dụng báo cáo bằng OIDC. IdP trả một ID Token hợp lệ với `iss=https://login.corp.example` và `sub=person-742`, nhưng bảng `local_account` chưa có người dùng đó. Ứng dụng có thể từ chối cho đến khi được admin tạo tài khoản hoặc **cấp phát lúc đăng nhập đầu tiên**, gọi là **Just-in-Time provisioning (JIT)**.

**JIT provisioning** là quá trình **tìm hoặc tạo local account và gắn nó với federated identifier đã được xác minh**, theo chính sách của ứng dụng, ngay khi có sự kiện đăng nhập đầu tiên. JIT không thay thế việc xác minh OIDC ID Token/SAML assertion/CAS ticket, không tự động cấp quyền nghiệp vụ và không mặc nhiên giải quyết việc vô hiệu hóa tài khoản khi người dùng nghỉ việc.

> **Nguyên tắc an toàn:** chỉ JIT **sau** protocol authentication thành công; ràng buộc local account với **khóa danh tính ổn định có namespace của IdP**; dùng giao dịch/unique constraint để chống trùng; áp dụng status và quyền tối thiểu; không tự nối vào account có sẵn chỉ vì trùng email.

**Mục tiêu học tập:** hiểu khi nào cần JIT, so sánh với SCIM/pre-provisioning; thiết kế identity key cho OIDC/SAML/CAS; đưa ra chính sách eligibility; viết data model/atomic upsert; cấu hình hook Spring Security; xử lý đăng nhập đồng thời, account linking, deprovisioning, audit, lỗi thường gặp; kiểm chứng bằng chương trình Java 17 tự chạy.

## 2. Phân biệt xác thực, cấp phát, liên kết và phân quyền

| Khâu | Câu hỏi | Bằng chứng / cơ chế |
| --- | --- | --- |
| **Authentication** | IdP có thực sự xác thực người dùng? | Spring OIDC/SAML/CAS validator xác minh chữ ký, issuer, audience, thời hạn và các điều kiện protocol. |
| **Identity mapping** | Khóa federation này tương ứng account nào? | Lookup theo verified issuer + subject; hoặc SAML IdP-qualified identifier theo hợp đồng. |
| **Provisioning** | Nếu chưa có account, có được tạo không? | Chính sách JIT theo issuer, tenant, cohort, risk, approval. |
| **Account linking** | Có được gắn identity mới vào account cũ không? | Phiên account cũ đã xác thực hoặc identity-proofing/admin-approved workflow, không tự nối bằng email. |
| **Authorization** | Người dùng được làm gì tại ứng dụng? | Local entitlements/authorities, tenant, resource ownership và method security. |
| **Lifecycle** | User bị khóa, đổi bộ phận hoặc nghỉ việc thì sao? | SCIM/HR sync, trạng thái local, phiên và token revocation. |

Một ID Token OIDC có chữ ký hợp lệ không có nghĩa tài khoản mới được phép duyệt hóa đơn; một account trong database cũng chưa chứng minh ai đang giữ phiên IdP. **Authentication, provisioning và authorization phải được kiểm tra tuần tự nhưng độc lập.**

### 2.1. Trạng thái đầu vào và đầu ra minh họa

~~~text
Verified OIDC authentication:
  iss = https://login.corp.example
  sub = a7c9b2-pairwise-subject
  email = lan@corp.example
  email_verified = true

Local directory:
  No federated_identity for (iss, sub)

Policy:
  Trusted issuer, tenant=finance-vn, eligible employee
  JIT allowed, manual approval required for business permissions

JIT result:
  local_account id = u-742
  status = PENDING
  federated_identity(iss, sub) -> u-742
  authorities = [app:onboarding]
  business privileges = none
~~~

Ngay cả khi Lan đã qua MFA tại IdP, account `u-742` vẫn có thể PENDING nếu ứng dụng yêu cầu phê duyệt. Ở lần login sau, resolver phải trả **chính u-742**; không tạo tài khoản mới theo email, cookie, session hay timestamp.

## 3. So sánh các mô hình cấp phát tài khoản

| Cơ chế | Khi tạo hoặc cập nhật account? | Điểm mạnh | Giới hạn |
| --- | --- | --- | --- |
| **Manual pre-provisioning** | Admin tạo account trước login. | Kiểm soát chặt, phê duyệt rõ. | Chậm, nhiều thao tác. |
| **HR/batch synchronization** | Job định kỳ đọc directory/HR. | Có account trước khi user truy cập. | Trễ đồng bộ, xử lý dữ liệu sai lệch. |
| **SCIM 2.0** | IdP/IGA chủ động gọi API Users/Groups của ứng dụng. | Hỗ trợ tạo/sửa/disable theo lifecycle và reconciliation. | Cần SCIM service, bảo vệ API, mapping, retry. |
| **JIT provisioning** | Sau lần login đầu tiên với identity đã xác minh. | Tạo đúng khi cần, ít vận hành thủ công. | Người chưa login chưa có record; không tự push disable khi họ nghỉ việc. |
| **Account linking** | Khi một account đã tồn tại được nối với identity mới. | Giữ dữ liệu/quyền lịch sử. | Account takeover nếu ghép chỉ vì email giống. |
| **Login-time profile sync** | Mỗi lần login cập nhật một số claims được phép. | Name/email/department có thể mới hơn. | Không tự thay đổi quyền và trạng thái lifecycle. |

**JIT + SCIM** thường là tổ hợp tốt: SCIM/HR chủ động disable, JIT bổ sung account còn thiếu khi người dùng login. Nhưng khi cả hai cùng ghi database, phải thiết kế **precedence, idempotency và conflict policy**; JIT không được ghi đè `DISABLED` do SCIM ban hành.

Theo NIST SP 800-63C, JIT tạo account tại RP khi nhận verified federated identifier chưa biết, hoặc dùng account resolution theo chính sách; việc cấp phát phải hoàn tất **trước khi thiết lập authenticated session tại RP**. Điều này nhắc chúng ta không được redirect người dùng vào ứng dụng với full business quyền khi transaction tạo account chưa commit.

## 4. OIDC: dùng cặp iss + sub làm khóa định danh

OpenID Connect Core §5.7 xác định cặp **`iss` (issuer) và `sub` (subject)** trong ID Token đã được xác minh là khóa ổn định mà Relying Party có thể dựa vào; `sub` duy nhất theo từng issuer, không được bảo đảm duy nhất toàn cầu.

~~~text
IdP A:
  issuer  = https://login.corp.example
  subject = 00123

IdP B:
  issuer  = https://partner-login.example
  subject = 00123

=> Hai federated identities khác nhau dù subject giống nhau.
~~~

Ngược lại:

~~~text
Login 1:
  iss=https://login.corp.example, sub=00123
  email=lan.old@corp.example

Login 2:
  iss=https://login.corp.example, sub=00123
  email=lan.new@corp.example

=> Cùng federated identity; không tạo account khác chỉ do email đổi.
~~~

**Không dùng các claims `email`, `name`, `preferred_username` hoặc `phone_number` làm khóa account liên kết thay thế.** Chúng có thể thiếu, đổi, trùng, được tái sử dụng hoặc có semantics khác nhau giữa issuers.

### 4.1. email_verified=true có đủ để auto-link không?

**Không.** `email_verified=true` chỉ nói OP đã có bước kiểm chứng quyền kiểm soát địa chỉ email tại thời điểm và theo cách thức của OP. Nó không chứng minh quyền sở hữu **tài khoản local cụ thể**, không chứng minh email là duy nhất ở mọi IdP, và không bảo đảm email chưa từng được cấp lại cho người khác.

Một kịch bản chiếm quyền:

~~~text
Local admin account #admin-7:
  email = finance.manager@corp.example
  permissions = [payments:approve]

Partner IdP assertion:
  iss = https://partner-id.example
  sub = attacker-sub
  email = finance.manager@corp.example
  email_verified = true

Cách làm sai:
  findLocalUserByEmail(email) -> #admin-7
  attach partner identity to #admin-7
  => attacker sở hữu business permissions của admin.
~~~

**Đúng:** resolver chỉ lookup binding theo **verified issuer + subject**. Nếu chưa có binding, tạo account **mới** ít quyền theo policy hoặc yêu cầu account linking với **chứng cứ xác thực độc lập**. Không ghép tự động chỉ vì email bằng nhau.

### 4.2. Public sub và pairwise sub

OIDC có **public subject identifier** và **pairwise subject identifier**. Với pairwise, cùng người có thể nhận các `sub` khác nhau tùy sector identifier của ứng dụng. Khi đổi IdP, client registration hoặc sector identifier:
- Khóa federation có thể đổi dù người dùng là một.
- Không tự migrate bằng email.
- Cần bước **approved identity linking/migration**, có audit, rollback và kiểm chứng sở hữu.
- Tách stable local user ID khỏi external subject key để bảo toàn dữ liệu.

Nếu có nhiều tenants trong cùng issuer, cách xác định tenant phải theo **verified registration và membership policy**, không nhận một `tenant=finance` từ query parameter rồi coi là quyền mặc định.

### 4.3. ID Token và UserInfo

Phân loại:
- **ID Token**: nguồn verified `iss/sub`, audience/client ID và authentication event claims.
- **UserInfo**: có thể cung cấp email/name/picture; nếu dùng phải đảm bảo subject tương ứng ID Token.
- **Groups/custom claims**: chỉ xét làm đầu vào cho approved role mapping; không tự đổi thành `ROLE_ADMIN`.
- **acr/amr/auth_time**: có ích khi policy yêu cầu assurance hoặc xác thực mới; không được tự gán “MFA” từ email_verified.

Không lấy `sub` từ một JSON body do frontend gửi. Toàn bộ JIT phải chạy trong trusted authentication flow của Spring, sau validators.

## 5. SAML 2.0: định danh phải theo hợp đồng IdP/SP

Trong Spring SAML2 Login, thành phần OpenSAML provider xác minh SAMLResponse, sau đó Spring có thể tạo `Saml2Authentication` với `Saml2AuthenticatedPrincipal`. Giá trị `principal.getName()` thường dựa vào NameID, **nhưng NameID không luôn ổn định**.

| Identifier từ SAML | Phù hợp cho binding lâu dài? | Lưu ý |
| --- | --- | --- |
| **Persistent NameID** | Thường có, nếu IdP cam kết tính bất biến/không tái sử dụng theo SP. | Namespace với IdP entityID, format và NameID qualifiers khi cần. |
| **Transient NameID** | Không. | Thay đổi giữa các phiên, JIT có thể tạo account mỗi login. |
| **EmailAddress NameID** | Không mặc nhiên. | Email có thể đổi/tái sử dụng; không auto-link. |
| **Immutable employee/person ID** | Có thể, nếu được IdP authoritative cung cấp và ký/khẳng định trong assertion. | Đảm bảo uniqueness và tenant/issuer namespace. |
| **Multi-valued attributes** | Tùy field. | Không coi phần tử đầu danh sách là unique subject nếu chưa có contract. |

Ví dụ identity binding:

~~~text
IdP entityID:
  https://sso.partner.example/idp

NameID format:
  urn:oasis:names:tc:SAML:2.0:nameid-format:persistent

NameID value:
  opaque-persistent-4f21

Local binding:
  (idp_entityID, NameIDFormat, NameIDValue, relevant qualifiers)
       -> local_account u-924
~~~

**Không chỉ dùng `RelyingPartyRegistrationId` làm danh tính IdP bất biến**: đó là khóa cấu hình ở Spring và có thể đổi theo deployment. Nếu IdP sử dụng transient NameID, cần đàm phán **persistent identifier** hoặc thuộc tính bất biến có hợp đồng, không chữa bằng “email giống thì merge”.

JIT phải chạy **sau** kiểm tra chữ ký, issuer, audience, recipient/destination, InResponseTo, SubjectConfirmation, Conditions/time và replay. **Không tự parse XML SAMLResponse của browser rồi gọi createUser.**

## 6. CAS, Kerberos và proxy pre-auth: khác token nhưng cùng nguyên tắc

- **CAS:** danh tính đến từ `TicketValidator` xác minh service ticket với CAS Server, cần đánh giá tính ổn định/namespace của CAS principal.
- **Kerberos:** principal có realm, ví dụ `alice@CORP.EXAMPLE`; không tự cắt realm khi tổ chức có multi-realm.
- **Pre-auth HTTP header:** chỉ dùng để JIT nếu trusted gateway đã xác thực người dùng, **strip/overwrite mọi client-supplied identity header**, bảo vệ gateway→backend bằng mTLS/network policy và chặn direct backend access.
- **OIDC/SAML:** dùng validators đúng giao thức. Không coi raw JWT/SAML XML hoặc một header tự khai là chứng cứ để JIT.

Nếu cùng username được cấp bởi hai realms/issuers khác nhau, việc gộp vào một local account là **account linking**, không phải ngầm hiểu JIT.

## 7. JIT eligibility: ai được phép tạo tài khoản?

Trước khi INSERT, phải có policy rõ:

1. **Trusted issuer/IdP allowlist**: chỉ nhận kết quả từ IdP đã cấu hình; không dynamic trust theo URL user gửi.
2. **RP registration đúng**: client/audience/redirect URI hoặc SAML entityID/ACS đã được xác minh.
3. **Stable external subject**: không null/rỗng, đúng namespace, tránh identifier tạm/không nhất quán.
4. **Tenant phía server**: dựa vào registration/membership authoritative, không dựa query tự khai.
5. **Cohort được phép**: nhân viên/đối tác/khách hàng có quyền onboarding theo hợp đồng; self-signup của IdP không đồng nghĩa auto-access.
6. **Assurance/freshness** nếu cần: kiểm tra verified `acr/amr/auth_time` hoặc SAML AuthnContext theo policy.
7. **Tombstone/deny state**: user bị khóa, ban hoặc offboard không được tự tái tạo.
8. **Quota và chống lạm dụng**: giới hạn JIT per tenant/issuer, login storms, kiểm soát account creation spikes.
9. **Default privileges tối thiểu**: tài khoản mới PENDING/onboarding hoặc ACTIVE quyền thấp nếu có approval rule.
10. **Attribute minimization và audit**: chỉ lưu fields thực sự cần, không lưu toàn bộ token/assertion.

### 7.1. Trạng thái account

| Status | Ý nghĩa | Hành vi được phép |
| --- | --- | --- |
| **PENDING** | Vừa được tạo, đang chờ hoàn thiện hồ sơ/approval. | Chỉ onboarding (nếu policy cho phép), không business access. |
| **ACTIVE** | Được phê duyệt và có quyền ứng dụng. | Truy cập đúng approved authorities/tenant/resources. |
| **SUSPENDED** | Khóa tạm vì risk/vi phạm. | Không cấp quyền mới, cần review. |
| **DISABLED** | Bị offboard/thu hồi. | Deny login và không auto-reactivate. |
| **DELETED/TOMBSTONED** | Identity từng bị xóa/ban, có đánh dấu chống tạo lại. | Chỉ được khôi phục qua workflow được phê duyệt. |

**Tạo local account PENDING có thể cho phép một phiên onboarding**, nhưng các endpoints business phải kiểm tra entitlement thực tế như `reports:read`, không đơn giản dùng `authenticated()`. Với yêu cầu nghiêm, PENDING không được tạo bất kỳ phiên ứng dụng nào; cần nêu rõ chính sách.

### 7.2. Luồng quyết định

~~~text
Verified OIDC/SAML/CAS Authentication
                  |
                  v
Trusted issuer/tenant/subject?
      No ----------+-------> DENY, no local account
                  |
                 Yes
                  |
                  v
Find federated_identity by stable key
       |                    |
     Found                Missing
       |                    |
       v                    v
Load local account    JIT allowed for cohort?
       |                 No ---> DENY / invitation
       |                    |
       |                   Yes
       |                    |
       |            Atomic create+bind transaction
       |                    |
       +----------+---------+
                  |
                  v
Check local account status
       Disabled/Suspended -> DENY
       Pending -> onboarding-only (if allowed)
       Active -> approved app authorities
                  |
                  v
Create only allowed Authentication / session
                  |
                  v
Check tenant + ownership + permission on each resource
~~~

**Không được nhảy thẳng từ IdP login success đến `ROLE_USER` hoặc `ROLE_ADMIN` nếu local admission/permissions chưa được đánh giá.**

## 8. Mô hình dữ liệu: local account và federated identity

Tách khóa nội bộ khỏi khóa của IdP để không làm thay đổi foreign keys khi issuer/client/subject được di chuyển theo workflow có kiểm chứng.

~~~sql
CREATE TABLE local_account (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL
      CHECK (status IN ('PENDING','ACTIVE','SUSPENDED','DISABLED')),
    email VARCHAR(320),
    display_name VARCHAR(200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_at TIMESTAMPTZ,
    disabled_at TIMESTAMPTZ
);

CREATE TABLE federated_identity (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    account_id BIGINT NOT NULL REFERENCES local_account(id),
    issuer VARCHAR(500) NOT NULL,
    subject VARCHAR(500) NOT NULL,
    protocol VARCHAR(20) NOT NULL,
    bound_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ,
    CONSTRAINT uq_fid_issuer_sub UNIQUE (issuer, subject)
);

CREATE INDEX idx_fid_account
    ON federated_identity (account_id);

CREATE TABLE app_entitlement (
    account_id BIGINT NOT NULL REFERENCES local_account(id),
    tenant_id VARCHAR(100) NOT NULL,
    permission VARCHAR(100) NOT NULL,
    source VARCHAR(100) NOT NULL,
    PRIMARY KEY (account_id, tenant_id, permission)
);
~~~

**Schema này là ví dụ PostgreSQL**, dành cho ứng dụng có một tenant chính per local account và identity mapping toàn cục. Nếu account có nhiều tenants, nên tách membership table. Nếu cùng một external identifier được cố ý ánh xạ tới nhiều account **theo tenant** thì unique key và entity model phải thể hiện chính sách đó minh bạch; không tự thêm tenant vào khóa để bỏ bảo vệ chống identity collisions.

### 8.1. Vì sao UNIQUE(issuer, subject) là cần thiết?

Hai request đăng nhập đầu tiên tới hai pod có thể đồng thời:

~~~text
Pod A: SELECT (iss, sub) -> NOT_FOUND
Pod B: SELECT (iss, sub) -> NOT_FOUND
Pod A: CREATE local_account #101
Pod B: CREATE local_account #102
Pod A: BIND (iss, sub) -> #101
Pod B: BIND (iss, sub) -> #102
~~~

Nếu không có constraint, một federated identity có thể được bind với hai accounts. **App-level SELECT rồi INSERT không đủ** vì race. Unique constraint tại database (cùng với transaction và đúng identity key) ngăn trạng thái không nhất quán; distributed lock chỉ là bổ trợ, không thay DB integrity.

### 8.2. Atomic create + bind

Thuật toán an toàn:

~~~text
resolveOrProvision(verifiedIdentity):
  1. Confirm issuer, subject, tenant and JIT policy.
  2. Look up federated_identity(issuer, subject).
     If exists, load account + check status/tenant, return.
  3. Begin database transaction:
       insert local_account(status=PENDING, tenant)
       insert federated_identity(account_id, issuer, subject)
       commit both records
  4. If UNIQUE conflict:
       rollback WHOLE transaction (including local account insert)
       open a clean transaction/read
       load the winner binding by (issuer, subject)
       check account status and tenant
       return winner
  5. Do not establish business session until binding committed.
~~~

Đặc biệt, khi Spring transaction gặp unique violation, transaction có thể đã được đánh dấu rollback-only hoặc DB transaction đã failed; **đừng catch exception rồi cố commit trong cùng transaction**. Đặt xử lý conflict ở một lớp gọi ngoài transaction, rollback sạch rồi lookup winner qua transaction mới. Nếu lỗi timeout không rõ commit đã thành công hay chưa, reconcile qua natural key sau khi kết nối phục hồi, tránh retry tạo tràn lan.

Không giữ một local user vừa tạo mà không có binding — đó là **orphan account**. Nếu cần gửi event sau commit, dùng transactional outbox/reliable event handling; không coi publish thành công mà DB rollback là account đã được cấp phát.

## 9. Idempotency và multi-node concurrency

Một service JIT phải thỏa:

~~~text
Login (issuer-A, sub-1) lần 1 -> account #42
Login (issuer-A, sub-1) lần 2 -> same account #42
Login (issuer-A, sub-1) từ Pod B đồng thời -> same #42
Login (issuer-B, sub-1) -> different identity
Login (issuer-A, sub-2) có cùng email -> different identity
Login (issuer-A, sub-1) khi #42 DISABLED -> DENY, no new account
~~~

Idempotency key **không phải email, timestamp, nonce, session ID, IP hoặc browser ID**. Dùng external identity ổn định đã được protocol verifier xác minh và namespace theo issuer/app tenancy contract.

### 9.1. Trường hợp đồng bộ SCIM và JIT đồng thời

Có thể xảy ra:
- SCIM đang tạo account theo external identity.
- Người dùng đồng thời login, JIT tìm thấy chưa có account.
- Một quy trình thắng transaction, quy trình kia gặp unique conflict.

Cả hai cần dùng **cùng quy tắc identity binding**, unique constraints và status precedence. Nếu SCIM vừa disable user, JIT không được dựa vào trạng thái cũ để active trở lại; dùng transaction/optimistic version và deny precedence. Không tạo session business chỉ vì callback login trước lúc event disable được xử lý.

### 9.2. Eventual consistency của cache

JIT có thể ghi DB leader nhưng node khác đọc cache cũ `NOT_FOUND`, rồi cố tạo thêm account. DB unique vẫn bảo vệ. Khi status bị đổi DISABLED, một cache stale có thể để login cũ được chấp nhận; phải xác định TTL và revocation SLA, invalidate theo account ID/securityVersion. Với quyền admin/finance có thể cần strong read/central entitlement check tại critical operations.

## 10. Java 17 runnable: hai lần đăng nhập đầu tiên đồng thời

Chương trình Java SE dưới đây mô phỏng **bước sau successful verified federation**. Nó dùng `ConcurrentHashMap.computeIfAbsent` để cho hai threads cùng request một identity nhận đúng một account trong **một JVM**. Nó cũng cho thấy không auto-link theo email, không gộp hai issuers cùng subject và không tự mở lại account DISABLED.

**Đây là mô hình thuật toán**, không có OIDC/SAML validation, TLS, DB, HTTP, Spring hay multi-node. Trong production, cần **database unique constraint + transaction**, không thể chỉ dùng map JVM.

Tệp **`JitProvisioningDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicLong;

public final class JitProvisioningDemo {

    record Key(String issuer, String subject) {}

    record VerifiedIdentity(
            String issuer, String subject, String email, String tenant) {}

    enum Status { PENDING, ACTIVE, DISABLED }

    static final class Account {
        final long id;
        final String tenant;
        final String emailForDisplay;
        volatile Status status = Status.PENDING;
        volatile Set<String> permissions = Set.of("app:onboarding");

        Account(long id, String tenant, String emailForDisplay) {
            this.id = id;
            this.tenant = tenant;
            this.emailForDisplay = emailForDisplay;
        }
    }

    static final class Directory {
        private final ConcurrentHashMap<Key, Account> accounts =
                new ConcurrentHashMap<>();
        private final AtomicLong nextId = new AtomicLong();

        Account resolveOrProvision(VerifiedIdentity assertion) {
            // Chỉ gọi sau khi nguồn OIDC/SAML đã được xác minh.
            if (!Set.of("https://idp-a.example", "https://idp-b.example")
                    .contains(assertion.issuer())) {
                throw new SecurityException("UNTRUSTED_ISSUER");
            }
            if (!"tenant-a".equals(assertion.tenant())) {
                throw new SecurityException("TENANT_NOT_ALLOWED");
            }
            if (assertion.subject() == null ||
                    assertion.subject().isBlank()) {
                throw new SecurityException("BAD_SUBJECT");
            }
            Key key = new Key(assertion.issuer(), assertion.subject());
            Account account = accounts.computeIfAbsent(key,
                    k -> new Account(nextId.incrementAndGet(),
                            assertion.tenant(), assertion.email()));
            if (!account.tenant.equals(assertion.tenant())) {
                throw new SecurityException("TENANT_MISMATCH");
            }
            return account;
        }

        void approve(Key key) {
            Account a = accounts.get(key);
            if (a != null && a.status == Status.PENDING) {
                a.permissions = Set.of("reports:read");
                a.status = Status.ACTIVE;
            }
        }

        void disable(Key key) {
            Account a = accounts.get(key);
            if (a != null) {
                a.permissions = Set.of();
                a.status = Status.DISABLED;
            }
        }

        boolean canReadReports(VerifiedIdentity assertion) {
            Account a = resolveOrProvision(assertion);
            return a.status == Status.ACTIVE
                    && a.permissions.contains("reports:read");
        }

        int size() { return accounts.size(); }
    }

    public static void main(String[] args) throws Exception {
        Directory directory = new Directory();
        VerifiedIdentity alice = new VerifiedIdentity(
                "https://idp-a.example", "subject-001",
                "alice@corp.example", "tenant-a");

        List<Long> ids = Collections.synchronizedList(new ArrayList<>());
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        Runnable login = () -> {
            ready.countDown();
            try {
                start.await();
                ids.add(directory.resolveOrProvision(alice).id);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(e);
            }
        };
        Thread t1 = new Thread(login);
        Thread t2 = new Thread(login);
        t1.start();
        t2.start();
        ready.await();
        start.countDown();
        t1.join();
        t2.join();

        System.out.println("SAME_ACCOUNT=" + ids.get(0).equals(ids.get(1)));
        System.out.println("AFTER_RACE=" + directory.size());
        System.out.println("PENDING_READ=" + directory.canReadReports(alice));

        Key key = new Key(alice.issuer(), alice.subject());
        directory.approve(key);
        System.out.println("ACTIVE_READ=" + directory.canReadReports(alice));

        VerifiedIdentity otherIssuer = new VerifiedIdentity(
                "https://idp-b.example", "subject-001",
                "alice@corp.example", "tenant-a");
        Account b = directory.resolveOrProvision(otherIssuer);
        System.out.println("DIFFERENT_ISSUER_ACCOUNT="
                + (b.id != directory.resolveOrProvision(alice).id));

        VerifiedIdentity otherSubSameEmail = new VerifiedIdentity(
                "https://idp-a.example", "subject-002",
                "alice@corp.example", "tenant-a");
        Account c = directory.resolveOrProvision(otherSubSameEmail);
        System.out.println("SAME_EMAIL_NOT_LINKED="
                + (c.id != directory.resolveOrProvision(alice).id));
        System.out.println("TOTAL_ACCOUNTS=" + directory.size());

        directory.disable(key);
        System.out.println("DISABLED_READ=" + directory.canReadReports(alice));
        System.out.println("STILL_DISABLED="
                + (directory.resolveOrProvision(alice).status
                    == Status.DISABLED));

        try {
            directory.resolveOrProvision(new VerifiedIdentity(
                    "https://evil-idp.example", "subject-999",
                    "unknown@corp.example", "tenant-a"));
            System.out.println("UNKNOWN_ISSUER=ALLOWED");
        } catch (SecurityException e) {
            System.out.println("UNKNOWN_ISSUER=DENIED");
        }

        try {
            directory.resolveOrProvision(new VerifiedIdentity(
                    "https://idp-a.example", "subject-001",
                    "alice@corp.example", "tenant-b"));
            System.out.println("WRONG_TENANT=ALLOWED");
        } catch (SecurityException e) {
            System.out.println("WRONG_TENANT=DENIED");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac JitProvisioningDemo.java
java JitProvisioningDemo
~~~

**Stdout xác định** sau khi cả hai threads đã join:

~~~text
SAME_ACCOUNT=true
AFTER_RACE=1
PENDING_READ=false
ACTIVE_READ=true
DIFFERENT_ISSUER_ACCOUNT=true
SAME_EMAIL_NOT_LINKED=true
TOTAL_ACCOUNTS=3
DISABLED_READ=false
STILL_DISABLED=true
UNKNOWN_ISSUER=DENIED
WRONG_TENANT=DENIED
~~~

Giải thích:
1. Cùng `(issuer, subject)` trong hai thread → cùng account, không duplicate.
2. Trước phê duyệt, PENDING không có `reports:read`; sau approve mới ACTIVE.
3. Cùng subject nhưng hai issuers không bị gộp.
4. Cùng email nhưng khác subject không auto-link.
5. Tài khoản DISABLED không được tạo lại/activate khi login tiếp.
6. Issuer lạ và tenant sai policy bị từ chối.

**Không triển khai `computeIfAbsent` in-memory làm kho JIT production**: nhiều pod có maps riêng; transaction/unique constraint và trạng thái persisted là bắt buộc. Các trường `VerifiedIdentity` trong demo **được giả định đã tin cậy**, không tự xác thực OIDC/SAML. `approve`/`disable` ở đây mô phỏng thao tác admin và không xử lý DB locks, auditing, security sessions hoặc concurrent revoke.

## 11. Tích hợp OIDC Just-in-Time trong Spring Security

Với Servlet-based Spring Security, luồng OIDC Login là:

~~~text
Browser -> /oauth2/authorization/corp
       -> OIDC Authorization Code + state/nonce + PKCE policy
       -> Token endpoint / ID Token validation
       -> OidcUserService / UserInfo
       -> JIT service lookup or create local account
       -> local account status & permission mapping
       -> Spring Authentication / SecurityContext
       -> app authorization
~~~

**Chỉ làm JIT sau bước xác minh ID Token**: signature, issuer, audience/client, expiry, nonce và state/correlation theo thư viện. Không tự decode raw JWT từ browser và tạo account chỉ vì token trông hợp lệ.

### 11.1. Mẫu delegation bằng OidcUserService

Đoạn dưới minh họa cách dùng `OidcUserService` mặc định rồi resolve/bind local account, giữ các validations bình thường của Spring Security và không tự lấy authorities từ untrusted group claims.

~~~java
package example.security;

import java.util.HashSet;
import java.util.Set;
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
public class OidcJitConfig {

    enum Status { PENDING, ACTIVE, DISABLED }

    record LocalUser(Status status, Set<String> approvedPermissions) {}

    interface LocalIdentityService {
        LocalUser resolveOrProvision(
                String registrationId, String issuer, String subject,
                String email, Boolean emailVerified);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http,
            LocalIdentityService local) throws Exception {

        OidcUserService delegate = new OidcUserService();
        OAuth2UserService<OidcUserRequest, OidcUser> service = request -> {
            OidcUser oidc = delegate.loadUser(request);
            String issuer = oidc.getIdToken().getIssuer().toString();
            String subject = oidc.getSubject();
            String registrationId =
                request.getClientRegistration().getRegistrationId();

            // Application: whitelist issuer, tenant, DB UNIQUE,
            // JIT eligibility, approval and DISABLED precedence.
            LocalUser user = local.resolveOrProvision(
                registrationId, issuer, subject,
                oidc.getEmail(), oidc.getEmailVerified());

            if (user.status() == Status.DISABLED) {
                throw new OAuth2AuthenticationException(
                    new OAuth2Error("local_account_disabled"),
                    "Local account disabled");
            }

            Set<GrantedAuthority> authorities = new HashSet<>();
            if (user.status() == Status.PENDING) {
                authorities.add(
                    new SimpleGrantedAuthority("app:onboarding"));
            } else {
                for (String permission : user.approvedPermissions()) {
                    authorities.add(new SimpleGrantedAuthority(permission));
                }
            }

            if (oidc.getUserInfo() == null) {
                return new DefaultOidcUser(authorities, oidc.getIdToken());
            }
            return new DefaultOidcUser(
                authorities, oidc.getIdToken(), oidc.getUserInfo());
        };

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/onboarding/**").authenticated()
                .requestMatchers("/reports/**")
                    .hasAuthority("reports:read")
                .anyRequest().authenticated())
            .oauth2Login(oidc -> oidc
                .userInfoEndpoint(info -> info.oidcUserService(service)));
        return http.build();
    }
}
~~~

**Đây là mảnh cấu hình trong một ứng dụng Spring Boot, không phải Java SE độc lập.** Cần implementation/bean thực của `LocalIdentityService`, repository, transaction, `ClientRegistrationRepository`, TLS, OIDC OP, cấu hình callback, Spring Security dependencies và compilation/integration tests theo version 6.x/7.x. Việc định nghĩa interface trong snippet không có nghĩa Spring tự tạo implementation; cần cung cấp bean.

Điểm chính:
- `OidcUserService` được gọi trong pipeline đã xác minh OIDC, không thay token verifier.
- Application resolver dùng verified issuer/sub và tenant policy.
- PENDING chỉ có `app:onboarding`, business endpoints đòi authority cụ thể.
- DISABLED bị từ chối ngay cả khi IdP vẫn xác thực.
- Authorities đến từ **local approvedPermissions**, không lấy `groups=admins` làm role admin.
- Không được chuyển một ID Token đã validated thành local session nếu transaction tạo identity binding thất bại.

**Lưu ý:** nếu tài khoản còn status khác như SUSPENDED, resolver cần từ chối theo policy; code chỉ minh họa ba trạng thái và ứng dụng production phải mở rộng kiểm soát đầy đủ. Một số IdPs không trả `UserInfo` hoặc `email_verified`; resolver không được đòi email mới có khóa identity, vì issuer/sub đã đủ cho lookup.

### 11.2. Vì sao không cho success handler tạo account rồi redirect bất kể kết quả?

Một số hệ thống dùng `AuthenticationSuccessHandler` để làm JIT. Nhưng success handler có thể được gọi **sau** khi framework đã xử lý một phần `SecurityContext`/session theo cấu hình. Nếu account create thất bại mà handler vẫn redirect, người dùng có thể vào một session authenticated **không có local account hợp lệ**.

Giải pháp:
- Ưu tiên tích hợp **admission + JIT** ở giai đoạn tạo principal/Authentication sau protocol validation.
- Nếu dùng success handler, phải clear/invalidate state và trả failure khi provisioning không commit.
- Không tạo account trong protected business controller sau khi request đã được authorize.
- Không tự đặt Authentication bằng username từ URL/header chưa xác minh.

### 11.3. Quyền có thể cũ khi session đang tồn tại

Sau lần login, authorities được gắn vào `OAuth2AuthenticationToken` và có thể lưu trong Spring `HttpSession`. Khi admin thu hồi quyền ở DB, session đang tồn tại **không tự nạp lại permissions**. Để đáp ứng SLA:
- Đặt session TTL/absolute expiry phù hợp.
- Invalidates sessions khi role/status thay đổi.
- Hoặc recheck entitlements/securityVersion ở thao tác nhạy cảm.
- Nếu API dùng JWT độc lập, cần cơ chế revoke/introspection/token lifetime tương ứng.

JIT xử lý lifecycle tại **login**, không mặc nhiên xử lý mọi request.

## 12. Tích hợp SAML2 JIT đúng chỗ

Sau khi Spring/OpenSAML validate SAMLResponse, Authentication có thể chứa `Saml2AuthenticatedPrincipal`. Ví dụ một handler hiển thị **principal đã xác thực**:

~~~java
@GetMapping("/me")
public Map<String, Object> me(
        @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
    return Map.of(
        "subject", principal.getName(),
        "registrationId", principal.getRelyingPartyRegistrationId());
}
~~~

**Đoạn này không triển khai JIT; nó chỉ là ví dụ đọc principal trong Spring MVC.** JIT nên được thực hiện trong một **post-validation account resolver / custom response authentication conversion** bọc hoặc ủy quyền cho provider chuẩn, không thay signature/audience/recipient/time checks bằng tự parse XML.

Quy trình:
1. Spring SAML2 verifier xác nhận signed assertion và toàn bộ trust conditions.
2. Lấy IdP entityID và stable NameID/immutable attribute theo federation contract.
3. Dựng natural key có namespace IdP/SP theo policy.
4. Gọi local identity resolver transactional để lookup/create binding.
5. Kiểm tra status, tenant, entitlement; PENDING onboarding-only hoặc deny.
6. Tạo Authentication/authorities gắn local account theo tích hợp đã kiểm thử.
7. Không tạo local session business khi JIT fails.

**Cẩn thận:** `OpenSaml5AuthenticationProvider` và converter APIs có thể thay đổi giữa releases. Không tự xây `Saml2Authentication` sau khi đọc XML chưa validate; hãy dùng extension point phù hợp version, bảo toàn default validation và test SAML signature, wrong audience, replay, transient NameID.

### 12.1. Rủi ro transient NameID

~~~text
Login 1: NameID = transient-aa1
Login 2: NameID = transient-bb2
Same real human, but different identifiers.
~~~

Nếu JIT dùng `principal.getName()` trực tiếp làm khóa, app có thể tạo tài khoản thứ hai mỗi login. Phải yêu cầu IdP cung cấp **persistent NameID** hoặc thuộc tính ổn định theo hợp đồng. **Không giải quyết bằng email matching** vì chính điều đó tạo rủi ro takeover.

## 13. Attribute sync khi login: cái gì được phép thay đổi?

| Field | Quy tắc gợi ý |
| --- | --- |
| Display name | Có thể sync nếu IdP là authoritative, có consent/retention; không làm identity key. |
| Email | Có thể sync theo chính sách sau khi verified; **không tự relink** account. |
| Locale / avatar | Chỉ lưu nếu có nhu cầu; validate và tránh SSRF khi fetch remote URLs. |
| Department/manager | Dùng nguồn HR/Directory phù hợp, có timestamp/provenance. |
| Employee ID | Chỉ xem làm stable ID nếu issuer contract đảm bảo bất biến và không tái sử dụng. |
| Tenant membership | Chỉ từ directory/policy authoritative, không từ user query/unchecked group. |
| Account status | **Không được auto DISABLED→ACTIVE** chỉ vì login. |
| App role/entitlement | Chỉ từ approved local authority source và mapping có scope. |
| MFA/assurance | Chỉ từ verified authentication context, không suy từ email_verified. |
| Internal account ID | Bất biến, giữ nguyên foreign keys và audit. |

Không có một “IdP là nguồn chính cho mọi trường” mặc định. Có thể user tự sửa display name trong app, trong khi department lấy từ HR và role lấy từ entitlement system. Sync profile phải theo **source-of-truth per field** và không chạy những update không cần thiết.

### 13.1. Defer noncritical writes

Nếu chỉ cần cập nhật avatar/display name nhưng hệ thống profile phụ đang lỗi, có thể cho login tiếp khi **identity binding, status và quyền** đã được xác minh. Ngược lại, nếu không xác nhận được active employment/tenant thì không được chấp nhận business access dựa trên role cũ một cách vô hạn.

Tách transaction quan trọng (identity binding + account) khỏi các side effects không quan trọng (email welcome, avatar fetch, analytics) bằng outbox/events. Không enqueue “user_created” rồi báo thành công trước khi binding commit.

## 14. Account linking: khác JIT, yêu cầu chứng cứ

Trường hợp user đã có account local #42 từ IdP A; nay truy cập bằng IdP B với email giống account #42. Resolver không tìm thấy binding B.

**Sai:** tìm account có email trùng rồi gắn identity B vào #42, nhất là khi #42 có quyền admin hoặc dữ liệu nhạy cảm.

**Đúng:** thực hiện account linking:
1. Người dùng có **một phiên được xác thực đủ mạnh với local account #42** hoặc quy trình identity-proofing/admin approval tương đương.
2. Bắt đầu yêu cầu “Link another identity” với CSRF/state/nonce protections.
3. Thực hiện OIDC/SAML login với IdP B qua đúng protocol.
4. Xác minh issuer/subject B, tenant, consent/risk và đảm bảo identity B chưa bind account khác.
5. Transaction thêm `federated_identity(B, subB) -> account #42`, có unique constraint.
6. Audit người thực hiện, thời gian, chính sách và thông báo cho account owner.
7. Khi gỡ binding, phải chặn login từ identity bị gỡ, không âm thầm tái JIT vào account cũ.

Nếu di chuyển IdP hàng loạt, dùng mapping approved dựa trên stable HR ID và admin review; tránh “cùng email là cùng người” làm đường migration.

## 15. Deprovisioning và trạng thái DISABLED

JIT chỉ được kích hoạt tại login, **không tự nhận sự kiện người dùng nghỉ việc** khi không có login mới. Cần:
- **SCIM 2.0** hoặc HR/IGA sync để disable, update groups/memberships.
- Account state machine có DISABLED/SUSPENDED/tombstones.
- Session invalidation, local token revocation, securityVersion checks.
- Short TTL/revalidation cho quyền nhạy cảm.
- Periodic reconciliation cho accounts orphan/permissions stale.
- Identity unlinking workflows có audit và không gây accidental relinking.
- Quy định việc gửi thông báo cho người dùng khi account bị vô hiệu hóa.

Bất biến:

~~~text
Verified federation authentication SUCCEEDS
AND local_account.status = DISABLED
=> DO NOT grant business access
=> DO NOT reactivate via JIT
~~~

Nếu user bị xóa khỏi DB mà còn IdP credential, JIT có thể vô tình tạo account mới. Do đó cần tombstone/revocation marker hoặc deny record theo chính sách, đồng thời tuân thủ data minimization và retention.

### 15.1. Revoke phiên hiện có

Spring `SecurityContext` có thể lưu Authentication cũ trong `HttpSession`. User disabled sau login vẫn có thể giữ session cho đến khi session hết hạn nếu app **không kiểm tra lại**. Cần phân biệt:
- **Login-time JIT checks** khi tạo Authentication mới.
- **Per-request or critical-action authorization checks** với status/entitlements hiện hành.
- **Back-channel logout/session invalidation** khi IdP/IGA báo sự kiện.
- **Bearer token revocation/introspection** nếu API dùng token độc lập.

Không hứa “disable ở IdP sẽ logout ngay mọi app” khi các downstream sessions/tokens chưa có cơ chế thu hồi.

## 16. Fail-closed và hoạt động an toàn khi sự cố

### 16.1. Khi local DB lỗi

| Điều kiện | Hành vi an toàn |
| --- | --- |
| External identity mới, DB không ghi được. | **Không** cấp full session; hiển thị lỗi onboarding và retry có kiểm soát. |
| Không đọc được status của account đã có. | Không thể xác nhận ACTIVE ⇒ deny hoặc chỉ restricted mode được policy định trước. |
| Unique violation do concurrent first login. | Rollback transaction, load winner, kiểm tra status/tenant. |
| DB commit outcome không rõ do timeout. | Requery natural key sau khi DB phục hồi; không tạo bừa bản ghi khác. |
| Chỉ profile avatar update lỗi. | Có thể login theo policy nếu account/status/rights đã xác minh, audit side effect. |
| IdP/API entitlement không sẵn sàng. | Không tự dùng roles mạnh từ cache stale ngoài SLA. |
| Event queue retry. | Idempotent account creation và event handling. |

### 16.2. Chống cấp phát hàng loạt trái phép

Nếu IdP cho phép bất kỳ email nào self-signup, một attacker có thể tạo hàng nghìn tài khoản trong RP dù OIDC token hợp lệ. JIT cần:
- Tenant/corporate cohort eligibility thực.
- Invitation/approval hoặc domain-only rule bổ trợ chứ không thay proofing.
- Rate/quota theo issuer/client/tenant, alert account spike.
- Chặn identity không phù hợp policy, không cấp quyền business cho PENDING.
- Limits cho profile attributes, Unicode/length, chống XSS/SSRF trong avatar URLs.
- Cleanup orphan/tombstone theo retention, không xóa mù quáng account có dữ liệu.

### 16.3. Logs, privacy và audit

Không log raw ID Token, SAMLResponse, access/refresh tokens, browser cookies, full profile claims hay email nếu không cần. Có thể lưu reference như sau:

~~~text
event=JIT_PROVISIONING
trace_id=login-20261107-a742
issuer_ref=corporate-oidc
subject_ref=HMAC(issuer|subject)
tenant_ref=finance-vn
local_account_ref=u-742
result=CREATED_PENDING
account_status=PENDING
policy_version=jit-v4
time_utc=2026-11-07T09:00:00Z
~~~

Đây là event schema minh họa, không phải log mặc định Spring. Audit cần ghi khi account created/approved/linked/disabled, change of role và login denied. Dùng HMAC keyed reference thay vì raw subject/email ở metric labels; quản lý khóa và thời hạn lưu theo chính sách quyền riêng tư.

## 17. Kiểm thử JIT: ma trận quan trọng

| Test case | Kết quả mong đợi |
| --- | --- |
| Trusted OIDC token, new issuer/sub, eligible tenant. | Một account + federated binding tạo transactionally. |
| Login lần hai với cùng issuer/sub. | Cùng local account ID, không duplicate. |
| Hai node login cùng issuer/sub đồng thời. | Unique constraint đảm bảo 1 account, không orphan. |
| Cùng sub nhưng khác issuers. | Không auto-link. |
| Cùng email nhưng khác sub. | Không auto-link, không account takeover. |
| Email đổi nhưng issuer/sub giữ nguyên. | Cùng account, profile update có policy. |
| email_verified=true trùng admin email. | **Không** liên kết vào admin account. |
| OIDC ID Token signature/issuer/audience/expiry/nonce không đúng. | Protocol validator reject, **không JIT**. |
| SAML transient NameID đổi giữa hai login. | Reject stable mapping hoặc dùng persistent ID được xác minh. |
| SAML valid signature nhưng IdP ngoài trust contract. | Không tạo account. |
| IdP đổi pairwise subject khi migration. | Approved identity linking, không email merge. |
| Local account PENDING. | Chỉ onboarding nếu policy cho phép; business API denied. |
| Local account DISABLED/SUSPENDED. | Không login business, không tự kích hoạt lại. |
| Deleted user có tombstone, IdP vẫn cấp token. | Không JIT recreate trái phép. |
| Upstream group “admins”. | Không tự gán ROLE_ADMIN. |
| User có account ACTIVE nhưng thiếu resource permissions. | 403 theo local authorization. |
| Tenant từ query bị đổi giả. | Deny, không được chuyển membership. |
| Unique conflict sau insert local account. | Transaction rollback toàn bộ, lookup winner. |
| SCIM disable cùng lúc user đang login. | Deny theo status/consistency policy và revocation SLA. |
| DB outage tại first login. | Fail closed, không tạo full session. |
| IdP token hợp lệ nhưng HR eligibility service timeout. | Fail-safe, không cấp quyền mạnh vô điều kiện. |
| Account linking B→A khi chưa xác thực A. | Reject. |
| Linking đã approved với authenticated A + verified B. | Unique binding, audit thành công. |
| Local account status đổi khi session vẫn active. | Session/token revocation hoặc per-action check theo SLA. |
| Cùng user nhiều tenants. | Đúng membership/tenant resource boundaries, không leak. |
| Event tạo account bị retry nhiều lần. | Idempotent, không tạo nhiều rows. |
| 10.000 first logins trong giờ cao điểm. | Rate/quota, transaction integrity, không fail-open. |
| UserInfo display name chứa HTML/script. | Không XSS; account key không bị ảnh hưởng. |

**Không chỉ test happy-path login.** Các lỗi có mức độ nguy hiểm cao là email-based account takeover, race duplicate, disabled account resurrection, cross-tenant grants và automatic admin role mapping.

## 18. Troubleshooting

| Triệu chứng | Nguyên nhân thường gặp | Cách tìm lỗi |
| --- | --- | --- |
| Login OIDC thành công nhưng 403 tại app. | Local status PENDING, thiếu entitlements. | Kiểm tra account status và authz, không bỏ security matcher. |
| Mỗi login tạo local account mới. | Dùng email/session hoặc SAML transient NameID. | Kiểm tra identity key theo issuer/subject. |
| Hai accounts cho cùng user sau login song song. | Không DB unique / transaction. | Kiểm tra unique violation handling và orphan records. |
| Unique violation dẫn tới HTTP 500. | Không rollback/requery ở transaction mới. | Sửa transaction boundary, bounded retry. |
| User đổi email rồi mất dữ liệu. | Email dùng làm primary external key. | Migration binding theo issuer/sub, giữ local account ID. |
| User từ partner IdP nhận account admin. | Auto-link theo email. | Stop auto-link, review access/audit và account ownership. |
| Local user DISABLED tự ACTIVE sau login. | Upsert ghi đè status. | Deny precedence và tombstone checks. |
| PENDING được vào /reports. | Dùng authenticated() thay vì check permission. | Restrict business endpoints by approved authorities. |
| IdP groups tự sinh quyền admin. | Group mapping không allowlist/không app scope. | Enforce local entitlements. |
| SAML NameID đổi sau IdP update. | Transient/pairwise/qualifier changed. | Xác định stable identifier contract, migration plan. |
| JIT tạo user nhưng thiếu federated binding. | Không atomic transaction. | Commit local + identity cùng transaction. |
| SCIM disable mà session còn hiệu lực. | Không revoke session/token. | Session registry, TTL, per-request checks. |
| Multi-tenant user thấy dữ liệu tenant khác. | Membership/role không scoped resource. | Check tenant at resource/service layer. |
| JIT failed khi IdP/HR outage. | Sync dependency timeout; không có fail-safe. | Circuit breaker, eligibility cache với TTL rõ, deny where needed. |
| UserInfo email khác trước. | Legitimate profile update hoặc source mismatch. | Không tạo binding mới từ email. |
| Các hệ thống lưu nhiều raw tokens. | Audit/retention sai. | Mask/redact, HMAC references, data minimization. |

## 19. Checklist triển khai production

1. Có trust agreement rõ cho issuers, client/RP registrations, stable subjects và tenant không?
2. JIT chỉ chạy **sau** OIDC/SAML/CAS validation thành công không?
3. OIDC dùng verified `iss+sub`, không dùng email/username làm account key không?
4. SAML dùng persistent NameID/immutable attribute và IdP entityID namespace đúng không?
5. Có allowed issuers/tenant/eligibility, không auto signup từ IdP lạ không?
6. Có unique index, transaction tạo local account + binding atomic không?
7. Hai login đồng thời tạo đúng một account không?
8. Unique conflict rollback hoàn toàn và load winner đúng không?
9. Account mới nhận PENDING/least privilege, không auto-admin không?
10. Có precedence DENY cho DISABLED/SUSPENDED/tombstone không?
11. Local authorities, tenant/resource permission được kiểm tra riêng không?
12. Có account linking workflow thay vì email auto-match không?
13. Có approved migration khi pairwise sub/IdP thay đổi không?
14. Có profile sync source-of-truth từng field, không ghi đè status/roles không?
15. Có SCIM/HR deprovisioning, revoke sessions/API tokens không?
16. Có throttling, quota, anti-mass-provisioning và audit events không?
17. DB/HR outages fail safely, không cấp full session khi state không rõ không?
18. Có kiểm tra privacy/PII retention và không log raw assertions/tokens không?
19. Có integration test multi-node concurrency, wrong issuer, same-email takeover và disabled recreation không?
20. Có tài liệu giải thích người dùng được SSO nhưng account đang PENDING nên chưa truy cập được nghiệp vụ không?

## 20. Tự kiểm tra kiến thức

1. **JIT là gì?** — Tạo/bind local account khi gặp verified federated identity mới trong lần login đầu theo policy.
2. **JIT có xác minh token không?** — Không; phải dùng protocol validator trước.
3. **Khóa OIDC ổn định nào nên dùng?** — Cặp `iss` và `sub`.
4. **email_verified=true có đủ ghép account cũ không?** — Không.
5. **Vì sao SAML transient NameID không phù hợp?** — Có thể đổi theo mỗi phiên, gây tạo account trùng.
6. **JIT khác SCIM?** — JIT tại login; SCIM đẩy lifecycle qua API.
7. **Vì sao cần DB unique constraint?** — Chống race giữa nhiều tabs/nodes; app-level check không đủ.
8. **Nếu unique conflict sau khi tạo local account?** — Rollback toàn transaction, requery identity winner.
9. **Account mới có tự nhận admin không?** — Không; PENDING hoặc minimal privileges theo policy.
10. **Khi DISABLED user login OIDC vẫn thành công?** — Deny local business access, không reactivate.
11. **Nếu hai IdPs cùng sub thì sao?** — Hai identities khác nhau nếu issuer khác.
12. **Cùng email có thể là hai sub khác nhau?** — Có, không auto-merge.
13. **Account linking cần gì?** — Authenticated existing local account/identity proofing và verified new identity.
14. **JIT có giải quyết offboarding tự động không?** — Không; cần SCIM/HR, session/token revocation.
15. **Hook Spring OIDC nào thích hợp?** — Delegate verified OidcUserService rồi resolve local account trước hoàn tất session.
16. **Nếu DB outage ở first login?** — Không cấp full session.
17. **Role từ IdP groups có dùng trực tiếp không?** — Chỉ qua trusted mapping và local entitlements theo app/tenant.
18. **Pairwise sub thay đổi khi migration thì sao?** — Account linking/migration có chứng cứ, không merge email.
19. **Tại sao cần test nhiều request đầu đồng thời?** — Để bảo đảm idempotency và không tạo duplicate/orphan.
20. **Có account ACTIVE là đủ xem mọi dữ liệu không?** — Không; còn app permission, tenant và resource ownership.

## Tài liệu tham khảo

- [NIST SP 800-63C — Federation and Assertions; Just-in-Time Provisioning and Account Linking](https://pages.nist.gov/800-63-4/sp800-63c.html)
- [OpenID Connect Core 1.0 — Claim Stability, Uniqueness, iss and sub](https://openid.net/specs/openid-connect-core-1_0.html)
- [Spring Security — OAuth2 Login Advanced Configuration, OidcUserService](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html)
- [Spring Security — OAuth2 Login Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html)
- [Spring Security — SAML2 Authentication and Saml2AuthenticatedPrincipal](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html)
- [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html)
- [SCIM 2.0 RFC 7643 — Core Schema](https://www.rfc-editor.org/rfc/rfc7643.html)
- [SCIM 2.0 RFC 7644 — Protocol](https://www.rfc-editor.org/rfc/rfc7644.html)
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
