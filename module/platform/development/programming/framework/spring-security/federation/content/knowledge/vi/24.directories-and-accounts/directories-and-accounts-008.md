# Xử lý đổi tên, thay email, chuyển tổ chức và xóa tài khoản trong Spring Security Federation

## 1. Bài toán: một con người có thể đổi hồ sơ nhưng không được đổi nhầm danh tính

Một ứng dụng Spring Boot doanh nghiệp có thể xác thực bằng LDAP/Active Directory, Kerberos/SPNEGO, CAS, SAML 2.0 hoặc OpenID Connect (OIDC). Hồ sơ người dùng đến từ HRIS, directory, Identity Provider (IdP), hoặc một SCIM provisioning connector.

Ví dụ:

~~~text
Người dùng:        Nguyễn Minh Anh
Tên đăng nhập:     minh.anh
Email:             minh.anh@old.example.org
Phòng ban:         Finance
Tổ chức/tenant:    company-a
App account ID:    acct-8f20
External identity: (issuer=https://idp.example.org, sub=user-9832)
~~~

Sau đó nhân sự **đổi tên**, **đổi email**, **chuyển phòng ban/tổ chức**, rồi **nghỉ việc hoặc yêu cầu xóa tài khoản**. Hệ thống phải làm đồng thời hai việc tưởng như đối lập:

- Giữ đúng **cùng một app account** và quyền sở hữu dữ liệu khi thay đổi chỉ là thông tin hồ sơ của cùng người.
- **Thu hồi quyền cũ và phiên còn hoạt động** khi thay đổi tổ chức, trạng thái account hoặc quan hệ làm việc; không cho tài khoản mới nhận dữ liệu người cũ vì email/username được tái sử dụng.

Bài học thuộc **Spring Security - federation → Thư mục và tài khoản**, chủ đề **“Xử lý đổi tên, thay email, chuyển tổ chức và xóa tài khoản”**. Không giả định một IdP hoặc một database là nguồn chính cho mọi tổ chức; cần hợp đồng rõ giữa HRIS, directory, provisioning và ứng dụng.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **định danh ổn định** và các thuộc tính có thể thay đổi như email, displayName, UPN, DN, phòng ban.
2. Thiết kế **app-local account ID** bất biến và external identity bindings đúng phạm vi.
3. Xử lý đổi tên/email **không tạo duplicate account** hoặc làm mất dữ liệu.
4. Nhận diện **account takeover do tái sử dụng email** và ngăn account linking không có bằng chứng.
5. Xử lý chuyển tổ chức/tenant bằng **revoke-before-grant**, không giữ stale roles.
6. Hiểu SCIM `id`, `externalId`, `userName`, `active`, PATCH/DELETE và ETag.
7. Phân biệt OIDC `iss+sub`, SAML persistent NameID và LDAP/AD object identifiers.
8. Xây lifecycle state machine ACTIVE/SUSPENDED/DISABLED/DELETED.
9. Tích hợp Spring Security account gate, authorities, HttpSession và token revocation.
10. Xử lý duplicate/out-of-order events, partial provisioning failures và reconciliation.
11. Chạy một ví dụ Java 17 độc lập thể hiện rename, email update, org transfer và disable.
12. Kiểm thử toàn bộ vòng đời joiner–mover–leaver với privacy, audit và least privilege.

Các ví dụ dùng Java 17+, Spring Boot 3.x, Spring Security Servlet 6.x/7.x và SCIM 2.0. Các mã account/URL đều giả. Spring integration snippets phải được đặt trong project có dependencies/beans thích hợp, khác với demo Java 17 standalone.

## 2. Định danh không được là một chuỗi email

Một hệ thống thường có năm lớp thông tin:

| Lớp | Ví dụ | Nguồn | Có đổi không? |
| --- | --- | --- | --- |
| Directory/person identity | AD objectGUID, Entra object ID, HR person record | Directory/HRIS | Ổn định trong phạm vi đối tượng; có thể đổi khi recreate/migrate |
| Federated identity | OIDC `iss+sub`, SAML persistent subject | IdP | Theo hợp đồng federation; có thể đổi khi issuer/sector migration |
| Internal account | UUID `acct-8f20` | Ứng dụng | **Không đổi vì rename/email** |
| Profile | Display name, email, username, department | HRIS/IdP/profile service | Có thể đổi thường xuyên |
| Authorization state | Active, org memberships, roles, ACL, security epoch | IAM và app policy | Phải cập nhật khi quyền thay đổi |

Nếu thiết kế:

~~~sql
CREATE TABLE business_documents (
    document_id BIGINT PRIMARY KEY,
    owner_email VARCHAR(320) NOT NULL
);
~~~

thì một địa chỉ email đổi hoặc tái cấp có thể làm tài liệu mất chủ hoặc chuyển nhầm sang người mới. Nên có khóa ownership độc lập:

~~~sql
CREATE TABLE app_accounts (
    account_id UUID PRIMARY KEY,
    display_name VARCHAR(255),
    primary_email VARCHAR(320),
    status VARCHAR(32) NOT NULL,
    authz_version BIGINT NOT NULL DEFAULT 1
);

CREATE TABLE business_documents (
    document_id BIGINT PRIMARY KEY,
    owner_account_id UUID NOT NULL
        REFERENCES app_accounts(account_id)
);
~~~

Đây chỉ là DDL minh họa cho hệ quản trị cơ sở dữ liệu hỗ trợ UUID. Trong production còn cần tenant scope, FK/indexes, constraints, migrations, PII protections và business authorization. **FK theo account ID không tự giải quyết truy cập chéo tenant** nếu query thiếu organization/resource ACL checks.

### So sánh độ ổn định của identifier

| Trường | Có thể dùng làm identity key? | Giới hạn |
| --- | --- | --- |
| `displayName, givenName, familyName` | **Không** | Tên trùng và có thể đổi |
| Email | **Không** | Có thể đổi, email được tái cấp |
| Username/UPN | Không mặc định | Có thể đổi theo tên/domain/tổ chức |
| LDAP DN | Không phải khóa bất biến | Rename/move OU làm DN đổi |
| AD `objectGUID` | Có điều kiện | Ổn định cho cùng object, không bảo đảm qua delete-recreate/cross-forest migration |
| AD `objectSid` | Có điều kiện | Domain/security principal scope; migration có thể đổi SID |
| Entra `objectId` | Có, scoped tenant | Object khác trong tenant đích có ID khác |
| OIDC `sub` | **Chỉ khi ghép với `iss`** | Pairwise sub khác theo client/sector |
| SAML persistent `NameID` | Theo contract federation | Scope issuer/qualifiers, không coi mọi Format đều persistent |
| SAML transient NameID | **Không** | Có thể thay mỗi session |
| CAS `cas:user` | Tùy contract | Có thể là username mutable |
| Kerberos `user@REALM` | Tùy contract | Principal/realm có thể thay do rename/migration |
| SCIM `id` | Trong provider namespace | Theo RFC không tái cấp, do SCIM server phát |
| SCIM `externalId` | Scoped provisioning domain | Do SCIM client cấp, không globally unique |
| App `account_id` | **Có** | Immutable, non-reassignable và quản lý vòng đời |

**OIDC Core** quy định cặp `(iss, sub)` là định danh được bảo đảm về uniqueness/stability trong phạm vi issuer. Các claim `email`, `preferred_username` và `name` không có bảo đảm tương tự. **RFC 7643** nêu SCIM `id` phải stable, non-reassignable trong tập resources của service provider; `externalId` thuộc provisioning client và chỉ có ý nghĩa theo provisioning domain.

### Bài học quan trọng về namespace

~~~text
Identity A: (iss=https://idp-a.example.org, sub=user-001)
Identity B: (iss=https://idp-b.example.org, sub=user-001)
~~~

Hai identity này **không tự là cùng một người**. Với multi-tenant, phải giữ tenant hoặc directory/provisioning namespace tùy contract; tuyệt đối không dùng tên/email giống nhau để tự merge.

## 3. Data model: local account và external identity bindings

Một app nên có ít nhất:

~~~text
AppAccount:
  accountId [immutable UUID]
  displayName [mutable]
  primaryEmail [mutable]
  emailVerifiedAt [nullable]
  lifecycleStatus [PROVISIONED/ACTIVE/SUSPENDED/DISABLED/DELETED]
  authzVersion [monotonic]
  updatedAt, sourceVersion

ExternalIdentityBinding:
  bindingId
  accountId
  protocol [OIDC/SAML/LDAP/CAS/SCIM/...]
  issuerOrDirectoryNamespace
  externalSubjectIdentifier
  linkedAt
  verifiedMethod
  bindingStatus [ACTIVE/REVOKED]

Membership:
  accountId
  organizationId
  role/grant/resourceScope
  status, validFrom, validUntil
  policyVersion

Audit:
  eventId, source, accountId, eventType, actor
  occurredAt, processedAt, result
  authorizationDecision, correlationId
~~~

Ví dụ một binding table (SQL minh họa):

~~~sql
CREATE TABLE external_identity_bindings (
    binding_id UUID PRIMARY KEY,
    account_id UUID NOT NULL
        REFERENCES app_accounts(account_id),
    protocol VARCHAR(24) NOT NULL,
    issuer_namespace VARCHAR(512) NOT NULL,
    subject_value VARCHAR(512) NOT NULL,
    binding_status VARCHAR(24) NOT NULL,
    linked_at TIMESTAMP NOT NULL,
    verified_method VARCHAR(64) NOT NULL,
    CONSTRAINT one_account_per_external_identity
        UNIQUE (protocol, issuer_namespace, subject_value)
);
~~~

Nếu ứng dụng có nhiều tenant/provisioning domains, unique constraint cần phản ánh chính xác namespace có thẩm quyền. Không có nghĩa một app-local account luôn phải map một external identity duy nhất: có thể có nhiều bindings được **liên kết có kiểm chứng** tới cùng account, nhưng mỗi active external identity chỉ được map tối đa tới một app account.

**Không đặt email làm khóa chứng minh identity.** Một unique email constraint phục vụ contact/notification có thể có ích, nhưng uniqueness không chứng minh hai identity lịch sử là cùng người.

### Ràng buộc account linking

1. Lookup external subject chỉ được thực hiện sau khi **giao thức xác thực** đã validate issuer, signature, audience và các điều kiện.
2. Binding mới phải có **bằng chứng**: cả hai account contexts được xác thực lại, hoặc authoritative migration mapping có phê duyệt.
3. Binding đã revoked/disabled không được tự bật lại vì email hoặc username mới trùng.
4. Link/unlink là **security-sensitive operation**, phải audit actor, proof và approval.
5. Nếu IdP issuer hoặc subject chuyển đổi, tạo binding mới theo migration procedure, không tự matching bằng email.
6. Hạn chế mọi account restore sau offboarding theo business policy, không thừa hưởng old privileges.

## 4. Nguồn sự thật cho từng loại dữ liệu

Không nhất thiết một hệ thống có toàn quyền sửa mọi trường:

| Dữ liệu | Nguồn thường có thẩm quyền | Trường hợp phải cảnh giác |
| --- | --- | --- |
| Employment status | HRIS/identity governance | App admin tự bật lại user đã nghỉ |
| Directory identifier | AD/Entra/directory | Recreate object nhưng app tự coi same ID |
| Login authentication | IdP/AS/KDC | Tin header/claim chưa verify |
| Profile/display name | HRIS/directory/profile owner | “Rename” tự đổi account ID |
| Email công việc | Corporate directory/verified self-service | Đổi recovery email khi chưa verified |
| Department / org | HRIS/organization governance | Đổi department mà không thu hồi groups |
| Roles/privileged grants | App/resource owner + approval | Map `department=Finance` thành ADMIN |
| Resource ownership | Business domain owner | Tự chuyển tài liệu theo email/org mới |
| Account status in app | IAM + local security policy | Token còn valid sau disable |
| Legal hold / data retention | Legal/privacy policy | SCIM DELETE tự xóa hồ sơ tài chính |

**Lưu ý:** nếu hai nguồn cùng có khả năng cập nhật một trường, cần field ownership/conflict policy; không dùng “event nào đến cuối cùng sẽ thắng” cho status hoặc privileged roles.

## 5. Sự kiện đổi tên: cập nhật hồ sơ, giữ owner ID

Trước:

~~~text
accountId  = acct-8f20
displayName= Nguyen Minh Anh
email      = minh.anh@example.org
external   = (https://idp.example.org, subject-123)
~~~

Sau:

~~~text
accountId  = acct-8f20        (không đổi)
displayName= Nguyen Thi Minh Anh
email      = minh.anh@example.org
external   = (https://idp.example.org, subject-123) (không đổi)
~~~

### Các bước

1. Nhận event rename từ nguồn có thẩm quyền, có source object ID và event revision.
2. Lookup **stable external binding** đến app account.
3. Kiểm tra idempotency và version (không áp event cũ).
4. Cập nhật displayName, familyName/givenName, search profile, cached labels theo policy.
5. Không tạo user mới, không thay `account_id` trong bảng tài liệu.
6. Không tự thay roles, tenant hay permissions vì họ tên đổi.
7. Audit bằng account ID, giữ PII tối thiểu.
8. Kiểm tra các legacy integrations có dùng username/DN làm key và sửa.
9. Nếu rename đi cùng UPN/email change, xử lý **hai sự kiện** và verification riêng.

### Session sau rename

Một `SecurityContext` đang có có thể còn `principal.getName()` cũ. Nếu đây chỉ là tên hiển thị, có thể refresh từ profile store mà không cần force logout tất cả. Nếu identity principal string còn được dùng làm khóa downstream, đó là dấu hiệu thiết kế cần refactor về immutable subject/account ID.

**Đừng dùng một thay đổi profile nhẹ để cấp lại toàn bộ quyền**. Các quyền phải đi qua authorization policy riêng.

## 6. LDAP/Active Directory: rename DN không phải đổi identity

Một LDAP distinguished name ban đầu:

~~~text
cn=Minh Anh,ou=Finance,dc=corp,dc=example,dc=org
~~~

Sau rename/chuyển OU:

~~~text
cn=Minh Anh Nguyen,ou=People,dc=corp,dc=example,dc=org
~~~

DN là đường định vị directory entry. Nó có thể thay trong rename/move, nên hardcode DN vào app principal/account key dễ gây lỗi lookup.

Phương án phù hợp:
- Lookup object bằng thuộc tính **ổn định có scope rõ**, ví dụ AD `objectGUID` trong directory instance tương ứng;
- Lưu `directoryNamespace+objectGUID` liên kết app account;
- Khi DN đổi, cập nhật search/index cache và bind target, không tạo account khác;
- Không coi `cn`, `sAMAccountName`, `userPrincipalName` bất biến;
- Lưu ý `objectGUID` ở AD có biểu diễn binary, phải encode nhất quán;
- `objectSid` và `SIDHistory` thuộc domain/migration semantics, không dùng thay nhau tùy tiện;
- Object delete-and-recreate/cross-forest migration có thể sinh identity mới; cần verified migration mapping.

Trong Spring LDAP, có thể dùng directory search theo username rồi bind hoặc compare credential và nạp authorities. Không lấy LDAP DN hoặc query filter từ browser rồi nối chuỗi chưa escape. Dùng Spring LDAP escaping/query APIs, LDAPS/StartTLS và service account chỉ có quyền cần thiết.

### Entra ID

Microsoft khuyến nghị developer dùng user **object ID** thay UPN/email, vì UPN có thể đổi do tên, domain, tái cơ cấu hoặc chuyển tổ chức. Object ID phải được scope với **tenant ID**. Chuyển sang tenant khác có thể tạo object mới; cần migration mapping thay vì auto-link bằng email.

## 7. Đổi email: tránh account takeover do email được tái cấp

Email có thể là:
- Nơi nhận notification;
- Recovery endpoint;
- Username giao diện login;
- Một claim OIDC hoặc attribute SAML/SCIM;
- Địa chỉ công việc được cấp theo nhân sự.

**Không dùng email làm unique identity key.** Cùng địa chỉ có thể do hai người sở hữu ở các thời điểm khác nhau.

### Kịch bản sai

~~~text
T1: A sở hữu shared.name@example.org, app account acct-A.
T2: A nghỉ việc; email trả về kho địa chỉ.
T3: B được cấp shared.name@example.org.
T4: IdP xác thực B và trả claim email=shared.name@example.org.
T5: App tự tìm acct-A qua email và cấp cho B lịch sử/quyền của A.
~~~

Đây là một dạng **account takeover** do auto-linking bằng thuộc tính mutable. Dù `email_verified=true`, điều đó chỉ có ý nghĩa theo contract IdP về quyền kiểm soát email **tại thời điểm xác minh**, không chứng minh B là A.

### Workflow chuẩn

1. Xác định nguồn được phép thay email: HRIS/directory hoặc self-service có kiểm tra.
2. Với self-service, yêu cầu reauthentication/step-up khi rủi ro cao.
3. Lưu `pendingEmail` nếu cần; gửi challenge tới email mới; không đổi recovery trước verification.
4. Kiểm tra email mới theo chính sách uniqueness trong tenant. Nếu trùng account khác, **không tự merge**.
5. Chỉ sau nguồn có thẩm quyền/xác minh phù hợp mới cập nhật primary email và verified status.
6. Giữ nguyên account ID và external binding ổn định.
7. Cập nhật notification subscriptions, contact lists, UI search indexes, cache.
8. Xem xét vô hiệu hóa recovery path ở email cũ và thông báo đổi email qua kênh độc lập.
9. Đánh giá session/OIDC ID Token vẫn chứa email cũ nhưng không phụ thuộc email làm authorization key.
10. Ghi audit event bằng app account ID và correlation ID; giới hạn PII retention.

### Không làm những việc sau

- Không dùng email chưa xác minh để reset password.
- Không chuyển owner của tài liệu từ A sang B vì B đang dùng email cũ.
- Không gửi mã recovery về email mà nguồn IAM đã báo không còn thuộc user.
- Không lấy query `newEmail` làm “email_verified” do browser tự khai.
- Không auto-link SAML/OIDC/CAS account khác chỉ vì claim email trùng.
- Không cho admin ở tenant A sửa email của account tenant B thiếu object-level authorization.

## 8. OIDC: dùng iss + sub, không dùng email làm khóa

OIDC Core chỉ bảo đảm stable end-user identifier theo **cặp `(iss, sub)`**. Những claim như `email`, `preferred_username` và `name` không bảo đảm duy nhất hoặc không đổi theo thời gian.

Ví dụ ID Token claims **đã được kiểm chứng** trong flow hợp lệ:

~~~json
{
  "iss": "https://idp.example.org",
  "sub": "subject-123",
  "email": "minh.anh@old.example.org",
  "email_verified": true,
  "preferred_username": "minh.anh",
  "name": "Nguyen Minh Anh"
}
~~~

Sau rename:

~~~json
{
  "iss": "https://idp.example.org",
  "sub": "subject-123",
  "email": "minh.anh.nguyen@new.example.org",
  "email_verified": true,
  "preferred_username": "minh.anh.nguyen",
  "name": "Nguyen Thi Minh Anh"
}
~~~

Identity binding **giữ nguyên**:

~~~text
(https://idp.example.org, subject-123) -> acct-8f20
~~~

**Không tìm account bằng email mới** và không tạo duplicate account chỉ vì email/username đổi.

### Pairwise subject và issuer migration

OIDC có pairwise subject identifiers; một người có thể có `sub` khác giữa các clients/sector identifiers. Nếu issuer URL, tenant hoặc sector identifier đổi, app có thể nhận subject mới. Điều đó không cho phép tự nối qua email. Cần:
- Approved migration roster/signed authoritative mapping;
- Verification rằng old và new identity thực sự cùng người theo quy trình IAM;
- Thêm binding mới tới app account cũ khi được phép;
- Audit link/unlink; chặn một external subject map nhiều accounts;
- Chỉ rút binding cũ sau cutover và security review.

## 9. SAML, CAS và Kerberos cũng có vấn đề đổi username

### SAML 2.0

- `NameID Format=emailAddress` là email-like identity, có thể đổi/tái cấp.
- `transient NameID` không thích hợp làm persistent account key.
- `persistent NameID` được thiết kế để liên hệ lâu dài trong federation relationship, có thể cần `Issuer/NameQualifier/SPNameQualifier` đúng scope.
- Một số federation dùng `subject-id` hay `pairwise-id` theo profile.
- SP phải validate SAML signature, issuer, audience, subject confirmation và thời gian **trước** khi lấy identity.
- Nếu mapping IdP đổi, thực hiện verified re-link, không email fallback.

### CAS Protocol

- CAS `cas:user` có thể là username/UPN tùy CAS Server.
- Service Ticket là credential dùng một lần, **không** làm stable user identifier.
- Nếu username CAS đổi, ứng dụng cần CAS attributes hoặc directory object ID có hợp đồng ổn định, hoặc migration có kiểm soát.
- CAS SLO không tự giải quyết việc account mapping sai hoặc quyền cũ còn trong app.

### Kerberos/SPNEGO

- Principal như `person@REALM` có thể thay vì rename/domain migration.
- Có thể map sang stable directory object ID sau khi mechanism Kerberos được xác minh.
- Không đồng nhất hai username giống nhau từ hai realms với nhau.

## 10. Chuyển bộ phận hoặc tổ chức: đây là thay đổi quyền

Khi chuyển Finance → People, không chỉ cần cập nhật `department=People`. Cần kiểm tra:
- Group memberships trong directory/IdP/SCIM;
- Local role grants;
- Project/workspace/resource ACL;
- App session chứa authorities cũ;
- API tokens và background jobs;
- Audit/approval privileges;
- Data ownership của tài liệu tại tổ chức cũ.

Bảng trước/sau:

| Thuộc tính | Trước | Sau |
| --- | --- | --- |
| App account ID | `acct-8f20` | `acct-8f20` (nếu cùng identity được phép giữ) |
| Department | Finance | People |
| Local roles | `FINANCE_READ`, `FINANCE_EXPORT` | `PEOPLE_READ` |
| Finance resource access | Có theo quyền cũ | **Phải thu hồi** nếu không có grant riêng |
| Old HttpSession authorities | Finance | **Phải invalidate/refresh** |
| Ownership of historical finance documents | Theo policy | **Không tự chuyển** theo org mới |

### Quy trình revoke-before-grant

1. Xác thực **authoritative mover event** bằng stable identity và event version.
2. Xác định đây là move trong một tenant hay cross-tenant/legal entity.
3. Chặn các quyền nhạy cảm org cũ **trước** khi cấp org mới.
4. Remove old group roles, direct grants, delegated access, approval permissions.
5. Áp target org rules và phê duyệt role mới; không copy nguyên role cũ.
6. Tăng `authzVersion/securityEpoch` để session/tokens cũ không dùng nguyên trạng.
7. Invalidate/refresh sessions, authorized clients, caches và tokens theo cơ chế sẵn có.
8. Cập nhật group memberships/SCIM downstream, theo dõi ACK và SLA.
9. Quyết định data ownership theo business/legal policy.
10. Kiểm thử user không thể vào org cũ và chỉ có quyền mới đã phê duyệt.

### Tenant khác phòng ban

Đổi department trong cùng tenant có thể chỉ thay group grants. Chuyển pháp nhân/tenant có thể yêu cầu:
- Tách dữ liệu và resource ownership;
- External identity mới từ IdP của tenant đích;
- Không auto-migrate account do yêu cầu pháp lý;
- Quản lý employment/contract relationship mới;
- Approved account binding hoặc app account khác;
- Data residency và retention khác.

**Đừng lấy request query `tenant=people` làm bằng chứng user thuộc People.** Business authorization phải dựa vào current membership từ nguồn tin cậy và resource org.

## 11. Mover race: đồng bộ groups chậm, quyền cũ còn

Một flow bất đồng bộ có thể tạo trạng thái nguy hiểm:

~~~text
T0: HR chuyển Finance -> People.
T1: IdP thêm user vào People group.
T2: Finance group chưa bị gỡ vì connector lỗi.
T3: User có token/session chứa cả Finance và People roles.
T4: User gọi endpoint tài chính nhạy cảm trong cửa sổ T1-T2.
~~~

Biện pháp:
- **Revoke-before-grant** theo orchestration;
- Với high-risk actions, đặt account `SUSPENDED</BT>/deny cho đến khi reconcile xong;
- Tăng authzVersion ngay khi bắt đầu thay đổi entitlement;
- Backend current permission check trước commit;
- Dùng SCIM Group membership updates và local ACL cleanup;
- Gắn status `PENDING_DOWNSTREAM` khi connector chưa ACK;
- Alert theo revocation SLA thay vì chỉ ghi “event delivered”.

Một account ACTIVE không tự chứng minh role hiện tại đã đồng bộ đúng. Hãy tách **employment status**, **membership status** và **business authorization**.

## 12. Nhiều tổ chức: model membership thay vì một chuỗi org

Nếu user có nhiều hợp đồng/tenant, chỉ một `user.organizationId` có thể không đủ. Một mô hình minh họa:

~~~sql
CREATE TABLE memberships (
    account_id UUID NOT NULL,
    organization_id UUID NOT NULL,
    membership_status VARCHAR(24) NOT NULL,
    authz_version BIGINT NOT NULL,
    PRIMARY KEY (account_id, organization_id)
);

CREATE TABLE resource_grants (
    resource_id UUID NOT NULL,
    account_id UUID NOT NULL,
    organization_id UUID NOT NULL,
    permission VARCHAR(64) NOT NULL,
    PRIMARY KEY (resource_id, account_id, organization_id, permission)
);
~~~

Đây là DDL minh họa, chưa có đầy đủ FK, indexes hay row-level security. Khi đánh giá truy cập:
- Xác định immutable account ID đã login;
- Kiểm tra account status hiện hành;
- Kiểm selected organization là membership có hiệu lực;
- Kiểm resource thuộc đúng tenant;
- Kiểm quyền read/write/approve trên tài nguyên;
- Không tin role từ một token cũ sau mover event nếu policy yêu cầu revocation gần tức thì.

Chuyển org không được tự chuyển hết resources cũ sang org mới. Data transfer phải theo business ownership workflow có audit và approval.

## 13. Vô hiệu hóa và xóa account không phải cùng một thao tác

| Trạng thái | Login mới | Session đang hoạt động | Dữ liệu/audit |
| --- | --- | --- | --- |
| `SUSPENDED` | Deny theo policy | Revoke/deny | Có thể khôi phục có phê duyệt |
| `DISABLED` | Deny | Revoke/deny | Thường giữ record theo policy |
| SCIM `active=false` | Administrative inactive | **Provider/app phải tự áp policy** | Resource có thể còn trong SCIM |
| SCIM `DELETE` | Không được tồn tại như resource truy vấn | App phải deny/revoke | Physical retention tùy provider và legal policy |
| Internal `DELETED_TOMBSTONE` | Deny | Deny | Giữ dấu vết tối thiểu nếu policy cho phép |

**SCIM RFC 7643** mô tả `active` là administrative status, không mặc định tất cả sessions/tokens tự bị revoke. **RFC 7644** cho phép service provider sau DELETE không cần physical-delete vĩnh viễn, nhưng các truy vấn tới resource đã xóa phải trả not found và resource không được xuất hiện trong query results.

### Offboarding đúng thứ tự

1. Nhận leaver event từ HRIS/IAM đáng tin, lookup immutable identity/account ID.
2. Disable app account và IdP/directory account theo policy.
3. Thu hồi organization memberships, roles, privileged grants, delegated access, access to projects.
4. Revoke hoặc expire Spring HttpSession, OAuth2 grants/refresh tokens, API keys, long-running connections và personal credentials theo khả năng.
5. Gửi SCIM disable/remove/delete tới downstream applications và group memberships.
6. Dừng scheduled jobs/automations/service integrations đứng tên user.
7. Transfer ownership của tài liệu, workflow, invoices theo business approval; không auto chuyển bừa.
8. Thực hiện data retention/deletion/archiving theo privacy/legal policy.
9. Dọn notifications/recovery email, search indexes, caches và invitations phù hợp.
10. Theo dõi ACK, failure/retry và reconciliation. Không tuyên bố thành công nếu downstream còn quyền.

**IdP disable không tự làm mọi JWT hết hạn.** Một Spring HttpSession có `SecurityContext` đã tạo vẫn có thể còn; một access token đã ký có thể được resource server chấp nhận đến `exp` nếu server không có revocation/introspection/live account gate.

## 14. SCIM 2.0: chuẩn hóa thay đổi tài khoản

RFC 7643 định nghĩa SCIM User:
- `id`: service-provider-issued, stable, non-reassignable trong tập resources đó, read-only;
- `externalId`: optional identifier do provisioning client cấp, scoped provisioning domain;
- `userName`: tên đăng nhập theo provider contract, không xem bất biến;
- `displayName`, `name.givenName/familyName`: profile;
- `emails`: danh sách địa chỉ và `primary` flag;
- `active`: administrative status;
- Enterprise User extension: `department, organization, manager, employeeNumber` và thuộc tính doanh nghiệp.

### Ví dụ SCIM User response

~~~json
{
  "schemas": [
    "urn:ietf:params:scim:schemas:core:2.0:User",
    "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"
  ],
  "id": "scim-provider-user-001",
  "externalId": "hr-person-5001",
  "userName": "minh.anh@company.example.org",
  "displayName": "Nguyen Minh Anh",
  "emails": [
    {
      "value": "minh.anh@company.example.org",
      "type": "work",
      "primary": true
    }
  ],
  "active": true,
  "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User": {
    "department": "Finance",
    "organization": "Company A"
  }
}
~~~

**Đây là JSON giả lập response.** Trên SCIM POST tạo mới, client **không được tự cấp `id`**; id được service provider trả. ExternalId không tự globally unique và cần scoping.

### PATCH rename và email

~~~http
PATCH /scim/v2/Users/scim-provider-user-001 HTTP/1.1
Host: app.example.org
Authorization: Bearer [REDACTED]
Content-Type: application/scim+json
If-Match: W/"v17"
~~~

~~~json
{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations": [
    {
      "op": "replace",
      "path": "displayName",
      "value": "Nguyen Thi Minh Anh"
    },
    {
      "op": "replace",
      "path": "emails",
      "value": [
        {
          "value": "minh.anh.nguyen@new.example.org",
          "type": "work",
          "primary": true
        }
      ]
    }
  ]
}
~~~

**Giải thích:**
- `W/"v17"` chỉ là ETag giả; nếu provider hỗ trợ ETags, lấy giá trị thực từ resource.
- SCIM PATCH có operations áp tuần tự nhưng phải **atomic trong một request** theo RFC; khi một operation fail, toàn request không được áp một phần.
- `PUT` replacement có thể làm mất attributes không gửi; PATCH thích hợp cho field-level updates nếu server hỗ trợ.
- Some SCIM providers có hạn chế đổi `userName` hoặc behavior riêng của emails array; kiểm tra `/Schemas`, `/ServiceProviderConfig` và vendor contract.
- Dùng `id` hoặc externalId binding có scope, không lấy email mới để “tạo user mới”.

### PATCH disable

~~~http
PATCH /scim/v2/Users/scim-provider-user-001 HTTP/1.1
Content-Type: application/scim+json
Authorization: Bearer [REDACTED]
If-Match: W/"v18"
~~~

~~~json
{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations": [
    {
      "op": "replace",
      "path": "active",
      "value": false
    }
  ]
}
~~~

Sau khi nhận đúng:
- Cập nhật app-local lifecycle status để **deny login/authorization**;
- Kích hoạt revocation sessions/tokens/grants theo requirement;
- Gửi downstream deprovision event;
- Ghi audit và outcome.
- Không tự mặc định mọi vendor đã hủy các phiên chỉ vì đã lưu active=false.

### DELETE

~~~http
DELETE /scim/v2/Users/scim-provider-user-001 HTTP/1.1
Authorization: Bearer [REDACTED]
If-Match: W/"v19"
~~~

Theo RFC 7644, provider có thể không xóa vật lý, nhưng resource đã DELETE phải không còn có thể GET/QUERY dưới SCIM endpoint theo contract. App phải deny và thu hồi quyền, còn data retention/archival xử lý riêng.

**Đừng dùng DELETE cho mọi leaver** nếu business process cần suspended/reactivatable accounts. Hãy phân biệt administrative disable và resource removal với provisioning client.

## 15. SCIM Group membership và department không tự tương đương

Đổi SCIM `department` từ Finance sang People không tự gỡ user khỏi directory/SCIM Group `finance-analysts`. Nếu authorization dựa vào groups, cần:
- Remove old group memberships;
- Revoke direct roles/ACLs;
- Add new groups theo approval;
- Sync local grants và refresh authorities;
- Theo dõi update trên Group resources, không chỉ User.department;
- Kiểm nested groups và group mapping restrictions.

Với SCIM, field `User.groups` có thể được trả như tham chiếu/read-only theo schema/provider; thay membership thường qua `Group.members`. Không ép SCIM client ghi department rồi tuyên bố roles đã đúng.

### Concurrency/ETag

Khi HRIS, IdP và app admin cùng thay đổi:
- Sử dụng PATCH hẹp thay cho PUT toàn resource khi phù hợp;
- Nếu server hỗ trợ versioning, gửi `If-Match` với ETag đã đọc;
- Với lỗi precondition mismatch, đọc current state rồi reconcile;
- Không retry vô hạn bản cũ;
- Tách quyền sửa theo field owner, không cho profile sync bật lại disabled account.

## 16. Session và token revocation trong Spring Security

Một app dùng Servlet login thường lưu `Authentication` và authorities trong `SecurityContext`, có thể gắn với `HttpSession`. Khi user chuyển org hoặc bị disable, Authentication đã tạo có thể vẫn mang:
- Account status cũ;
- Finance roles cũ;
- Old email/profile attributes;
- Tokens/refresh grants đang hoạt động;
- Selected tenant cũ.

Một chiến lược phù hợp mức rủi ro:

| Cơ chế | Tác dụng | Giới hạn |
| --- | --- | --- |
| Account gate tại login | Chặn login mới nếu disabled | **Không** tự dừng session cũ |
| Current-state authorization gate | Deny user disabled/membership revoked tại request | Cần DB/cache consistency |
| `authzVersion/securityEpoch` | Session version khác state hiện tại thì deny/reauth | Phải kiểm thường xuyên tại chỗ nhạy cảm |
| Session invalidation/index | Hủy phiên theo immutable account ID | Multi-node cần session store/index phù hợp |
| JWT short TTL | Giảm cửa sổ token stale | Không ngay tức thì |
| Token revocation/introspection | Cho backend kiểm current token validity | Cần infrastructure và policy |
| OAuth refresh grant revocation | Chặn cấp token mới từ grant cũ | Access token đã phát có thể còn hiệu lực |
| SCIM downstream disable | Thu hồi app khác qua provisioning | Asynchronous, cần ACK/retry |
| WebSocket/job shutdown | Dừng kết nối và background actions | Không tự xảy ra khi HttpSession logout |

**Quan trọng:** SAML SLO, OIDC logout hay CAS SLO có thể giúp một số sessions bị hủy theo protocol và cấu hình. Nhưng không có bảo đảm mọi JWT, API key, WebSocket và SaaS downstream đều tự revoke.

### Security epoch khi chuyển org

Một session tạo lúc `authzVersion=6` giữ quyền Finance. Khi HR chuyển org, app tăng version thành 7. Mọi request nhạy cảm từ session version 6 phải bị deny hoặc yêu cầu reauthenticate/refresh **trước khi đọc tài nguyên**. Reauth vẫn phải nạp group/membership mới, không tái cấp quyền cũ.

## 17. Spring Security OIDC: ví dụ account gate theo issuer + subject

Trong OIDC login, Spring Security có `OidcUserService`, có thể dùng để kiểm tra account sau khi ID Token/claims đã được OIDC provider xác minh.

Mẫu **Spring config partial**:

~~~java
package com.example.identity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

@Configuration
public class OidcAccountGateConfig {

    @Bean
    OAuth2UserService<OidcUserRequest, OidcUser> gatedOidcUserService(
            AccountAccessGuard accountAccessGuard) {

        var delegate = new OidcUserService();

        return request -> {
            OidcUser user = delegate.loadUser(request);

            String issuer = user.getIdToken()
                    .getIssuer().toString();
            String subject = user.getIdToken()
                    .getSubject();

            // App-owned service: exact (issuer, subject) lookup,
            // status active, current memberships/tenant checks.
            // Must throw a suitable AuthenticationException
            // if unknown/disabled/forbidden.
            accountAccessGuard.requireActive(issuer, subject);
            return user;
        };
    }
}
~~~

**Điều kiện:** `AccountAccessGuard` là interface/service tự triển khai; cần OAuth2/OIDC client configuration, Spring Security dependencies, trusted issuer, SecurityFilterChain và database. Mã không biên dịch bằng `javac` trần và không phải ứng dụng đầy đủ.

Gắn vào flow:

~~~java
@Bean
SecurityFilterChain security(
        HttpSecurity http,
        OAuth2UserService<OidcUserRequest, OidcUser> gatedOidcUserService)
        throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/health", "/error").permitAll()
                    .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                    .userInfoEndpoint(userInfo -> userInfo
                            .oidcUserService(gatedOidcUserService)))
            .build();
}
~~~

Snippet cần imports `@Bean`, `HttpSecurity` và `SecurityFilterChain`. Đây là **login gate**, không thay session revocation khi account bị disable **sau** login.

Không dùng `user.getEmail()` làm account lookup key. Nếu cần local roles, dùng `GrantedAuthoritiesMapper` hoặc advanced OIDC UserService theo hướng dẫn Spring để map authorities an toàn; không tin tùy ý `email domain` hoặc `groups` chưa được thẩm định để cấp quyền cao.

## 18. Tích hợp LDAP/SAML/CAS cần account gate độc lập

**LDAP/AD**:
- Directory search/bind xác minh user login;
- DN có thể đổi khi rename/OU move;
- Group memberships có thể đổi sau user login;
- App cần stable directory binding và current account status;
- Không coi LDAP auth success tự làm cũ hóa mọi HttpSession.

**SAML 2.0**:
- Spring SP xác minh chữ ký, issuer, audience, recipient, timing và subject confirmation;
- Dùng persistent identity subject + qualifiers theo federation contract;
- Attributes có thể chỉ cập nhật ở lần đăng nhập tiếp theo;
- Provisioning events (SCIM) cập nhật account/group sớm hơn, không thay assertion validation;
- SAML Session Logout không tự revoke mọi API tokens.

**CAS Protocol**:
- CAS Server xác minh Service Ticket, app tạo Authentication;
- CAS `cas:user` có thể thay khi directory username đổi;
- Nếu không có stable directory attribute, cần approved account migration;
- CAS SLO giải quyết một số sessions, không thay current entitlement gate.

**Kerberos**:
- Kerberos principal/UPN và realm có scope, có thể thay theo migration;
- Mapping từ verified Kerberos principal sang directory object ID có thể cần thiết;
- Không gộp hai principal cùng username ở realms khác nhau.

## 19. Java 17 độc lập: rename, email, mover, disable và quyền phiên cũ

Chương trình sau dùng **chỉ Java Standard Library**. Nó mô phỏng `ExternalIdentity(issuer, subject)` gắn với immutable app account ID, profile được đổi, quyền bị thu hồi khi chuyển org và mọi request bị chặn sau disable.

Tệp `AccountLifecycleDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

public final class AccountLifecycleDemo {

    record ExternalIdentity(String issuer, String subject) {}

    static final class Account {
        final String accountId;
        String displayName;
        String email;
        String organization;
        boolean active = true;
        Set<String> roles;
        long authzVersion = 1;

        Account(String accountId, String displayName,
                String email, String organization,
                Set<String> roles) {
            this.accountId = accountId;
            this.displayName = displayName;
            this.email = email;
            this.organization = organization;
            this.roles = Set.copyOf(roles);
        }
    }

    static final class Directory {
        private final Map<String, Account> accounts = new HashMap<>();
        private final Map<ExternalIdentity, String> bindings =
                new HashMap<>();

        synchronized void create(Account account, ExternalIdentity identity) {
            if (accounts.containsKey(account.accountId)
                    || bindings.containsKey(identity)) {
                throw new IllegalArgumentException("duplicate identity");
            }
            accounts.put(account.accountId, account);
            bindings.put(identity, account.accountId);
        }

        synchronized String resolve(ExternalIdentity identity) {
            return bindings.getOrDefault(identity, "NO_MATCH");
        }

        private Account require(String id) {
            Account account = accounts.get(id);
            if (account == null) {
                throw new IllegalArgumentException("unknown account");
            }
            return account;
        }

        synchronized void rename(String id, String newName) {
            require(id).displayName = newName;
        }

        synchronized void changeEmail(String id, String verifiedEmail) {
            // Real service must verify event origin/email ownership.
            require(id).email = verifiedEmail;
        }

        synchronized void transfer(String id, String newOrganization,
                                   Set<String> newRoles) {
            Account account = require(id);
            account.organization = newOrganization;
            account.roles = Set.copyOf(newRoles);
            account.authzVersion++;
        }

        synchronized void disable(String id) {
            Account account = require(id);
            account.active = false;
            account.roles = Set.of();
            account.authzVersion++;
        }

        synchronized long version(String id) {
            return require(id).authzVersion;
        }

        synchronized String profile(String id) {
            Account account = require(id);
            return account.displayName + " / " + account.email;
        }

        synchronized String authorize(String id, long sessionVersion,
                                      String requiredOrg, String role) {
            Account account = accounts.get(id);
            if (account == null) {
                return "DENY_UNKNOWN";
            }
            if (!account.active) {
                return "DENY_DISABLED";
            }
            if (account.authzVersion != sessionVersion) {
                return "REAUTH_REQUIRED";
            }
            if (!account.organization.equals(requiredOrg)
                    || !account.roles.contains(role)) {
                return "DENY_SCOPE";
            }
            return "ALLOW";
        }
    }

    public static void main(String[] args) {
        Directory directory = new Directory();
        ExternalIdentity original = new ExternalIdentity(
                "https://idp.example.org", "subject-101");

        directory.create(new Account(
                "acct-001", "Linh Tran",
                "linh.old@example.org", "finance",
                Set.of("REPORT_READ")), original);

        long oldSessionVersion = directory.version("acct-001");
        directory.rename("acct-001", "Linh Nguyen");
        directory.changeEmail("acct-001", "linh.new@example.org");

        System.out.println("Stable account: "
                + directory.resolve(original));
        System.out.println("Updated profile: "
                + directory.profile("acct-001"));
        System.out.println("Finance before transfer: "
                + directory.authorize("acct-001",
                        oldSessionVersion, "finance", "REPORT_READ"));

        directory.transfer("acct-001", "people", Set.of("PEOPLE_READ"));
        System.out.println("Old session after transfer: "
                + directory.authorize("acct-001",
                        oldSessionVersion, "finance", "REPORT_READ"));

        long newSessionVersion = directory.version("acct-001");
        System.out.println("Old org after reauth: "
                + directory.authorize("acct-001",
                        newSessionVersion, "finance", "REPORT_READ"));
        System.out.println("New org after reauth: "
                + directory.authorize("acct-001",
                        newSessionVersion, "people", "PEOPLE_READ"));

        ExternalIdentity anotherPerson = new ExternalIdentity(
                "https://idp.example.org", "subject-999");
        System.out.println("Reused email cannot link: "
                + directory.resolve(anotherPerson));

        directory.disable("acct-001");
        System.out.println("After disable: "
                + directory.authorize("acct-001",
                        newSessionVersion, "people", "PEOPLE_READ"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac AccountLifecycleDemo.java
java AccountLifecycleDemo
~~~

Stdout **chính xác**:

~~~text
Stable account: acct-001
Updated profile: Linh Nguyen / linh.new@example.org
Finance before transfer: ALLOW
Old session after transfer: REAUTH_REQUIRED
Old org after reauth: DENY_SCOPE
New org after reauth: ALLOW
Reused email cannot link: NO_MATCH
After disable: DENY_DISABLED
~~~

**Giải thích:**
1. Đổi tên/email không đổi external subject binding hay app account ID.
2. Chuyển org tăng authzVersion, phiên cũ bị chặn.
3. Sau reauth, org Finance không còn hợp lệ dù principal vẫn là cùng người.
4. Org People được phép chỉ khi user active và có role mới.
5. Một external subject khác không được auto-link dù email hiển thị có trùng.
6. Sau disable, mọi request bị chặn trước khi so role.

**Giới hạn:** ví dụ không chứng minh OIDC token/SCIM request đã được ký/xác minh, không dùng DB/transactions, không làm revocation thật, không có multi-tenant memberships hay audit. Tham số `verifiedEmail` chỉ là tên trong demo; production cần quá trình xác minh thực. Không dùng `HashMap` làm identity store production.

## 20. Event ordering, duplicate và conflict resolution

Một event nội bộ mẫu:

~~~json
{
  "eventId": "evt-3901",
  "source": "trusted-hris",
  "sourceVersion": 18,
  "subject": {
    "directoryNamespace": "corp-ad-01",
    "directoryObjectId": "opaque-object-123"
  },
  "type": "ORGANIZATION_TRANSFER",
  "effectiveAt": "2026-11-07T04:00:00Z",
  "changes": {
    "oldOrgId": "finance",
    "newOrgId": "people"
  }
}
~~~

Đây là **schema ví dụ**, không phải SCIM event chuẩn. Một endpoint webhook phải xác minh sender (mTLS/OAuth token/chữ ký theo contract), tenant scope và event integrity; không nhận bất kỳ JSON từ browser để thay quyền.

### Cần xử lý bốn trường hợp

- **Duplicate delivery:** cùng event ID tới nhiều lần → idempotent; không tạo thêm account hoặc cấp lại role.
- **Out-of-order events:** disable version 20 đến trước org move version 18 → không để bản cũ bật lại account.
- **Partial failure:** local app đã disable nhưng downstream SCIM connector lỗi → ghi trạng thái PENDING/FAILED, retry có backoff, alert và reconciliation.
- **Conflicting authorities:** HRIS sửa department, app admin sửa role, IdP sửa email → dùng field ownership matrix, không “last write wins” cho mọi trường.

### occurredAt không đủ

`occurredAt` do source đặt có thể lệch clock. Nếu source hỗ trợ revision monotonic hoặc ETag có trust, dùng nó để chặn stale updates. Nếu không, reconcile current authoritative state thay vì áp blind event theo processedAt.

### Transactional outbox

Một mô hình an toàn:
1. App commit account status/membership changes cùng outbox record trong transaction local.
2. Worker phát revocation/deprovision events sau commit.
3. Consumer xử lý idempotently.
4. ACK/retry/backoff và dead-letter queue khi lỗi.
5. Reconciliation định kỳ so state HRIS/IdP/app/downstream.
6. Dashboard theo SLA để không nói “offboarding hoàn tất” nếu còn resource active.

Không giả vờ một Spring `@Transactional` trên app DB tự commit cả IdP, SCIM, Redis và SaaS services.

## 21. Rehire và account delete-recreate

Một người nghỉ rồi trở lại làm việc có thể có:
- Email giống trước hoặc khác;
- HR person ID giống hoặc employment record mới;
- Directory object recreated với objectGUID/objectId mới;
- OIDC issuer/sub mới hoặc cũ tùy IdP;
- Những tài nguyên lịch sử mà người đó **không được quyền lấy lại** theo role mới.

Quyết định tạo account mới hay cho reactivation phải dựa trên:
- Employment relationship và tenant policy;
- Business/data ownership approvals;
- Verified old/new identity mapping;
- New role grants được phê duyệt;
- Revocation của credentials cũ;
- Audit link/relink.

**Không auto-enable DISABLED account hoặc khôi phục ADMIN role chỉ vì email trùng.** Một tombstone local có thể giúp phát hiện lịch sử account ID nhưng retention và PII phải được quản lý.

### Xóa account và privacy

Có thể phải:
- Chặn access ngay;
- Giữ invoice/ledger/audit theo yêu cầu bảo quản hồ sơ;
- Xóa/ẩn profile PII không còn cần;
- Chuyển business ownership có phê duyệt;
- Xóa API keys/notifications/search indexes;
- Xử lý backups theo retention schedule;
- Quản lý legal holds.

SCIM DELETE không thể thay toàn bộ quy trình này. Quy định privacy khác nhau theo quốc gia/ngành; cần làm việc với privacy/legal owner cho retention policy thực tế.

## 22. Runbook vận hành sau thay đổi

### Rename/email

1. Đối chiếu external stable identifier và internal account ID trước/sau.
2. Check profile attributes mới, verified email status.
3. Xác nhận document owner FK không đổi.
4. Kiểm mail recovery/notification paths.
5. Đảm bảo không xuất hiện duplicate account.
6. Audit event with sourceVersion; không log raw tokens hoặc PII quá mức.

### Mover

1. Xác minh source event và old/new organization.
2. Chặn quyền cũ và bump authzVersion.
3. Gỡ group/project/privileged grants cũ.
4. Thêm quyền mới sau approval.
5. Kiểm active sessions/token access đã bị refresh/revoke.
6. Test object-level access ở old/new org.
7. Xác minh downstream ACK và tài liệu ownership.

### Leaver

1. App account status DISABLED/SUSPENDED theo policy.
2. Login mới deny.
3. Sessions, OAuth grants, API keys và background automations revoked theo SLA.
4. Directory groups/SCIM apps downstream deprovisioned.
5. Tài liệu/vật sở hữu business transferred/archived theo approval.
6. Chặn reuse email từ tự động khôi phục account.
7. Data retention/privacy và audit đã được đánh dấu.
8. Reconciliation hoàn tất; nếu partial failure phải alert/escalate.

## 23. Lỗi thường gặp và cách khắc phục

| Dấu hiệu | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Đổi email sinh thêm account | Email là key | Dùng issuer+subject/stable binding và account ID |
| Đổi họ mất tài liệu | Owner dùng name/email | FK tới immutable account ID |
| Move OU làm LDAP login fail | Hardcoded DN | Search theo directory identity hiện tại |
| User B có dữ liệu A | Recycled email + auto-link | Stop auto-link, revoke, audit identity links |
| SCIM PATCH trả 412 | ETag/version conflict | Fetch current state, reconcile |
| Email đã đổi nhưng UI vẫn cũ | Token/session/profile cache | Refresh profile cache, không đổi identity |
| Group đổi nhưng session còn role cũ | Stale authorities | authzVersion, session revoke/live check |
| Chuyển org mất hết dữ liệu | Ownership chuyển tự động | Business data ownership restoration |
| IdP khóa user nhưng API vẫn vào | JWT còn hạn và không live gate | Revocation/introspection/TTL |
| SCIM active=false nhưng app vẫn login | Inactive flag không kết nối app gate | Implement active check/revocation |
| SCIM DELETE rồi account tái sinh | Connector stale create event | Tombstone/idempotency/sourceVersion |
| SAML mới không map old account | Issuer/persistent subject đổi | Controlled identity migration |
| CAS username đổi tạo user mới | Mutable username làm identity key | Stable directory ID/approved re-link |
| Entra tenant migration mất mapping | objectId scoped tenant | Authoritative cross-tenant link |
| Rehire tự có role cũ | Auto-enable account | New role approval |
| Downstream leaver vẫn active | Partial sync failure | ACK/retry/alert/manual revoke |
| Event version cũ mở account | Last-write-wins | Source revision + security gate |
| Cross-tenant data leak | Query thiếu tenant/resource scope | Object-level authorization + constraints |

## 24. Bộ kiểm thử end-to-end

| Case | Điều phải đúng |
| --- | --- |
| Rename displayName | Cùng external identity và accountId, không đổi owner |
| Rename username/UPN | LDAP/AD object binding vẫn đúng |
| LDAP move DN | Entry lookup được qua search, không duplicate |
| Verified email change | Primary email được cập nhật; recovery path cũ dọn |
| Unverified email change | Không dùng pending email để reset login |
| Email tái cấp cho người mới | **Không** nhận data/roles của account cũ |
| OIDC sub trùng nhưng issuer khác | Hai identity khác nhau |
| OIDC pairwise subject thay do sector migration | Chỉ link qua verified migration |
| SAML transient NameID đổi | Không làm persistent account key |
| SCIM id/externalId từ hai providers | Không gộp ngoài namespace |
| Transfer Finance→People | Quyền cũ revoke trước new grant |
| Org move nhưng session giữ Finance role | Session denied/reauth/version stale |
| Cross-tenant move | Không tự chuyển ownership/PII |
| SCIM active=false | Login mới deny, sessions revoke theo SLA |
| SCIM DELETE | Resource removal contract và app denial đúng |
| JWT issued trước disable | Không vượt được revocation SLA |
| Duplicate disable event | Idempotent, không lỗi/không cấp quyền |
| Stale enable event sau disable | Không được mở lại account |
| Rehire có email giống | Không có quyền cũ nếu chưa approve |
| Cross-tenant account ID request | Object-level authorization deny |
| Downstream SCIM timeout | Báo partial/alert, không complete giả |
| Multi-node active sessions | Revocation hoạt động trên mọi node |
| Multiple IdPs | Không tự link bằng email |
| Audit/retention | Không log secrets, PII đúng hạn lưu |

**E2E test không dừng ở HTTP 200 từ SCIM PATCH.** Cần xác nhận database account link, session access, group memberships, authorization trên object và ACK từ downstream thực tế.

## 25. Những ngộ nhận phải tránh

1. **“Email là ID vì nó duy nhất.”** Email có thể đổi/tái cấp.
2. **“OIDC email_verified chứng minh cùng người với account cũ.”** Không.
3. **“OIDC sub không cần issuer.”** Sai, khóa phải có issuer.
4. **“SCIM id do provisioning client tự tạo.”** Sai, do service provider cấp.
5. **“SCIM externalId là globally unique.”** Sai, scoped provisioning domain.
6. **“LDAP DN không bao giờ đổi.”** Sai, rename/move thay DN.
7. **“SAML transient NameID dùng lâu dài.”** Sai.
8. **“CAS ST chính là user ID.”** Sai, ST là one-time login credential.
9. **“Đổi department tự gỡ mọi role.”** Sai, cần group/grant reconciliation.
10. **“IdP disable làm mọi HttpSession mất hiệu lực ngay.”** Không tự có.
11. **“SCIM active=false revoke tất cả JWT.”** Không.
12. **“SCIM DELETE phải xóa vật lý toàn bộ backup/audit.”** Không phải bảo đảm SCIM.
13. **“JWT signature hợp lệ nghĩa user vẫn được làm mọi việc.”** Không, còn active status và ACL.
14. **“Chuyển org tự chuyển mọi tài liệu sang org mới.”** Không, business ownership riêng.
15. **“Rehire cùng email tự bật role cũ.”** Nguy hiểm.
16. **“Event mới đến sau luôn đáng tin hơn.”** Cần source/version/field authority.
17. **“Một Spring @Transactional sửa đồng bộ mọi SaaS.”** Không.
18. **“Account linking bằng email đủ cho cross-tenant migration.”** Không.
19. **“Spring authorities tự update ngay khi directory groups đổi.”** Không bảo đảm.
20. **“Xóa user khỏi IdP không cần theo dõi tokens/API keys.”** Sai.

## 26. Câu hỏi luyện tập có đáp án

**Câu 1.** User đổi email nhưng `iss+sub` không đổi. Có tạo app account mới không?

**Đáp án:** không. Giữ internal account ID, cập nhật email có xác minh, refresh contact/recovery.

**Câu 2.** Email cũ của A chuyển sang B. IdP của B có email_verified=true. B có được nhận dữ liệu A không?

**Đáp án:** không. Không có bằng chứng hai subject là một người. Không auto-link.

**Câu 3.** Hai OIDC issuers cùng trả `sub=123`. Có phải cùng user không?

**Đáp án:** không tự kết luận; dùng `iss+sub`.

**Câu 4.** LDAP rename OU làm DN đổi. Nên dùng gì để tìm user?

**Đáp án:** stable directory object identifier có scope, directory search và mapping; không dùng DN bất biến giả.

**Câu 5.** Microsoft Entra khuyến nghị object ID hay UPN làm immutable account binding?

**Đáp án:** object ID scoped tenant; UPN/email có thể đổi.

**Câu 6.** SCIM `id` do ai cấp?

**Đáp án:** SCIM service provider; `externalId` tùy chọn do provisioning client cấp theo domain.

**Câu 7.** SCIM `externalId=100` của hai provisioning clients có được gộp không?

**Đáp án:** không chỉ vì trùng string. Phải scope nguồn và dùng verified linking nếu thực sự cùng identity.

**Câu 8.** Mover Finance→People nên revoke hay grant trước?

**Đáp án:** revoke quyền cũ trước grant quyền mới, với session/cache/token update để không có cửa sổ dual access.

**Câu 9.** Vì sao chuyển org làm session cũ nguy hiểm?

**Đáp án:** authorities, tenant và claims có thể stale; cần live account gate/authzVersion/session revocation.

**Câu 10.** `active=false` có tự revoke access token đã phát không?

**Đáp án:** không. App/resource server phải thực thi revocation/introspection/TTL hoặc current-state check.

**Câu 11.** SCIM DELETE có luôn là hard delete vật lý không?

**Đáp án:** không, server có thể giữ dữ liệu nội bộ theo RFC nhưng resource phải không còn xuất hiện qua SCIM API như trước.

**Câu 12.** Có nên đổi account ID khi email đổi để đồng bộ hệ thống?

**Đáp án:** không. Account ID bất biến giữ ownership/audit đúng.

**Câu 13.** Pairwise OIDC sub đổi sau sector migration. Làm sao link lại?

**Đáp án:** authoritative migration mapping hoặc strong account-link verification, không email fallback.

**Câu 14.** User được chuyển org nhưng tài liệu Finance do user sở hữu. Có chuyển tự động sang People không?

**Đáp án:** không; business ownership và privacy policy quyết định.

**Câu 15.** Disabled event version 20 tới trước enable event version 18. Có áp enable cũ không?

**Đáp án:** không, kiểm source version và reconcile current state.

**Câu 16.** Spring session đã login trước khi IdP disable account. Login gate mới đủ không?

**Đáp án:** không, cần revocation/current-state authorization cho session hiện tại.

**Câu 17.** SAML Assertion đúng chữ ký mang NameID=email. Có dùng email làm key không?

**Đáp án:** không, signature không biến mutable email thành immutable subject.

**Câu 18.** Rehire cùng email có được khôi phục quyền admin cũ không?

**Đáp án:** không tự động; cần employment/account approval và least privilege mới.

**Câu 19.** SCIM PUT vs PATCH trong rename?

**Đáp án:** PUT replacement cả resource, PATCH field-level operations và atomic theo RFC; nên xử lý ETag/version.

**Câu 20.** Một connector bị lỗi sau khi local app đã disable người dùng. Có báo offboarding hoàn tất không?

**Đáp án:** không. Ghi partial state, retry/alert/manual revoke và reconciliation.

## 27. Checklist production

- [ ] Internal account ID bất biến, không tái cấp và dùng cho owner/audit FK.
- [ ] External identity scoped theo issuer/directory/provider/tenant đúng.
- [ ] Không dùng email, display name, UPN, DN làm identity key duy nhất.
- [ ] OIDC account lookup theo verified `iss+sub`, không email fallback.
- [ ] SAML subject sử dụng contract persistent/qualifiers phù hợp.
- [ ] CAS/Kerberos/LDAP có stable directory binding hoặc migration approved.
- [ ] SCIM id/externalId được hiểu đúng provider/client domain.
- [ ] Rename không tạo duplicate account hoặc đổi owner.
- [ ] Email update có verification, recovery/notification cleanup.
- [ ] Email reuse không thể gây account takeover.
- [ ] LDAP DN rename/move không phá lookup.
- [ ] Mover thu hồi quyền cũ trước khi cấp role mới.
- [ ] Tenant/resource ACL kiểm object-level, không chỉ check role.
- [ ] Current sessions và tokens stale được xử lý theo SLA.
- [ ] Disable/suspend deny login mới và revoke active permissions/sessions.
- [ ] SCIM active=false/DELETE được test theo vendor, không giả định xóa hết tokens.
- [ ] Downstream provisioning có ACK/retry/reconciliation.
- [ ] Event idempotency, sourceVersion và out-of-order handling rõ.
- [ ] Stale enable event không mở lại account disabled.
- [ ] Rehire/cross-tenant migration qua verified identity linking.
- [ ] SCIM endpoint bảo vệ bằng provisioning-client auth, tenant scope, input validation.
- [ ] ETags/If-Match giảm lost updates nếu provider hỗ trợ.
- [ ] Audit lưu identity theo immutable ID, giảm PII và không lưu secrets.
- [ ] Data deletion/retention/legal hold theo policy riêng.
- [ ] Monitoring revocation latency, unmapped identities, downstream failures.
- [ ] Test user B có email A tái cấp **không** truy cập được A.
- [ ] E2E tests chạy ở multi-node/session store/IdP migration paths.

## 28. Kết luận

**Đổi tên và email là thay đổi hồ sơ, không được làm đổi chủ thể.** **Chuyển tổ chức là thay đổi quyền**, bắt buộc thu hồi entitlements cũ và kiểm tra sessions/tokens còn hiệu lực. **Disable/xóa tài khoản là quy trình nhiều hệ thống**, không chỉ một SCIM PATCH hoặc IdP logout.

Ghi nhớ bốn nguyên tắc:

1. **Stable identity:** app-local account ID bất biến; external bindings với issuer/provisioning scope rõ và đã được xác minh.
2. **Mutable profile:** display name, email, username, LDAP DN không phải quyền sở hữu dữ liệu.
3. **Current authorization:** ACTIVE, org memberships, resource ACL, security epoch và revocation phải được thực thi cả sau login.
4. **No implicit relinking:** cùng email không chứng minh cùng người; migration, rehire và tenant moves phải có approval/evidence.

Hệ thống federation trưởng thành phải bảo đảm **đúng người, đúng tài khoản, đúng tổ chức, đúng quyền và đúng vòng đời** dù thông tin đăng nhập, email hay tổ chức thay đổi.

### Tài liệu chính thức

1. OpenID Connect Core 1.0, Section 5.7 Claim Stability and Uniqueness: https://openid.net/specs/openid-connect-core-1_0.html
2. IETF RFC 7643 — SCIM Core Schema (id, externalId, active, emails, enterprise extension): https://www.rfc-editor.org/rfc/rfc7643.html
3. IETF RFC 7644 — SCIM Protocol (PATCH, DELETE, ETag, If-Match): https://www.rfc-editor.org/rfc/rfc7644.html
4. Microsoft Learn — UPN changes, using Entra object ID instead of UPN/email: https://learn.microsoft.com/en-us/azure/active-directory/hybrid/howto-troubleshoot-upn-changes
5. OASIS SAML 2.0 Core, persistent/transient NameID and qualifiers: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
6. Spring Security — OAuth2 Login advanced OIDC UserService and authorities mapping: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
7. Spring Security — LDAP Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html
8. Spring Security — Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
9. Spring Security — SAML2 Login: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
10. Spring Security — CAS Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html
11. Spring Session — SessionRepository and distributed sessions: https://docs.spring.io/spring-session/reference/api.html
