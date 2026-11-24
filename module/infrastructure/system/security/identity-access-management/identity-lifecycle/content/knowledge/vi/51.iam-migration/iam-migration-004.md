# Di trú application trong quản lý vòng đời danh tính (IAM)

> **Chương:** IAM migration  
> **Chủ đề:** Di trú application  
> **Phạm vi:** Quản lý vòng đời danh tính theo Joiner–Mover–Leaver (JML), liên kết identity source, IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán và giảm quyền truy cập tồn dư.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **di trú application** với thay identity source, directory hoặc identity provider (IdP).
2. Lập inventory account, entitlement, group, local role, dữ liệu gắn chủ sở hữu và mọi đường truy cập mà ứng dụng cũ đang sử dụng.
3. Thiết kế ánh xạ account cũ–mới an toàn dựa trên **canonical identity** thay vì chỉ dựa vào email hoặc username.
4. Chuyển quyền theo ngữ nghĩa nghiệp vụ, bảo toàn RBAC/ABAC, separation of duties (SoD) và quyền theo bản ghi.
5. Giữ đúng luồng **Joiner–Mover–Leaver**, SCIM/API provisioning và thu hồi session/token trong suốt quá trình chuyển đổi.
6. Thiết kế pilot, coexistence, cutover, rollback, reconciliation và nghiệm thu có bằng chứng.
7. Xử lý tài khoản service, workload identity, guest, quyền cục bộ và các quyền truy cập tồn dư.

**Tình huống xuyên suốt:** Doanh nghiệp thay CRM-Legacy bằng CRM-Cloud. Cả hai dùng cùng IdP để đăng nhập SSO, nhưng cách đánh số user, mô hình vai trò và phân quyền truy cập dữ liệu khác nhau. Một số nhân viên có direct grant không qua nhóm IdP, các bot dùng API key, còn record của nhân viên cũ vẫn cần giữ lịch sử. Làm thế nào để chuyển ứng dụng mà không cấp nhầm quyền, mất ownership hoặc để lại đường truy cập cho leaver?

## 2. Application migration trong IAM là gì?

**Application migration** là chuyển một ứng dụng, tenant, phiên bản hoặc workload sang môi trường/giải pháp đích. Trong IAM, phạm vi không chỉ là copy user record hoặc đổi URL. Cần bảo đảm người dùng được nhận diện là đúng chủ thể, có đúng tài khoản và quyền hợp lệ trong toàn bộ vòng đời.

| Thành phần | Trách nhiệm | Vấn đề khi đổi ứng dụng |
|---|---|---|
| **Identity source** | HRIS/nguồn nhà thầu xác nhận trạng thái, vai trò, ngày hiệu lực | Không được mất sự kiện joiner, mover, leaver |
| **Directory** | Lưu tài khoản, nhóm và thuộc tính phục vụ IAM | Group/attribute có tiếp tục được hiểu đúng? |
| **IdP** | Xác thực, SSO, MFA, phát token/assertion | Ứng dụng mới liên kết user theo khóa nào? |
| **IAM/IGA** | Điều phối lifecycle, RBAC/ABAC, phê duyệt và rà soát quyền | Desired entitlement ở app mới là gì? |
| **Ứng dụng cũ** | Account, role, direct grant, dữ liệu, phiên và API credential | Những quyền/tài nguyên nào còn phụ thuộc? |
| **Ứng dụng mới** | Account ID, entitlement schema, dữ liệu, API và chính sách mới | Quyền thực tế sau chuyển có đúng chính sách không? |
| **Provisioning connector** | Đồng bộ account/group qua SCIM hoặc API | Khóa liên kết, single writer, retry, deactivate |

Có nhiều dạng di trú: ứng dụng tự xây dựng sang SaaS, chuyển ERP/CRM sang sản phẩm khác, nâng cấp ứng dụng nhưng thay mô hình quyền, hợp nhất tenant sau sáp nhập, chuyển các module từ hệ thống cũ sang mới theo giai đoạn.

### 2.1. Sơ đồ quan hệ

~~~mermaid
flowchart LR
    HR["HRIS / nguồn nhà thầu"] --> IAM["IAM / IGA: JML và policy"]
    IAM --> IDP["Directory / IdP: SSO, MFA"]
    IDP --> OLD["Ứng dụng cũ"]
    IDP --> NEW["Ứng dụng mới"]
    IAM --> SCIM["SCIM / API provisioning"]
    SCIM --> OLD
    SCIM --> NEW
    OLD -. "Mapping account, role, dữ liệu" .-> MAP["Identity & entitlement crosswalk"]
    MAP -. "Đối soát" .-> NEW
    OLD --> AUDIT["Audit & reconciliation"]
    NEW --> AUDIT
    AUDIT --> IAM
~~~

**Authentication** trả lời “ai đang đăng nhập?”. **Authorization** trả lời “người đó được thao tác trên tài nguyên nào?”. **Provisioning** tạo/sửa/vô hiệu hóa account và entitlement; **data ownership** xác định người/nhóm sở hữu bản ghi. Cả bốn mảng cần được kiểm chứng độc lập.

Di trú application **không đồng nghĩa** di trú IdP. Giữ nguyên IdP vẫn có thể phát sinh app user ID mới, record ownership mới hoặc quyền đích có nghĩa khác.

## 3. Bất biến cần giữ xuyên suốt

Nhóm triển khai nên chốt các điều kiện không được vi phạm:

| Bất biến | Bằng chứng kiểm chứng |
|---|---|
| Cùng chủ thể phải liên kết đúng account cũ/mới | Canonical person ID và mapping có phê duyệt |
| Không tự động gộp nhầm hai người | Không merge chỉ vì email/tên giống; ca mơ hồ được cách ly |
| Đúng người sở hữu và đọc/sửa đúng dữ liệu | Kiểm thử record owner, team scope, API và UI |
| Mọi quyền phải còn lý do nghiệp vụ | Desired vs actual entitlement, exception có owner/expiry |
| Mover phải mất quyền cũ khi hết hiệu lực | Kiểm tra group, direct grant, delegated role và SoD |
| Leaver không truy cập app cũ hay mới trái SLA | Kiểm thử SSO, local auth, token, session và API |
| Service account không trở thành orphan | Có owner, purpose, secret lifecycle và access review |
| Không mất dấu vết | Event ID, mapping version, actor, approver, before/after |
| Lỗi đồng bộ không gây mass disable/grant | Guardrail, chế độ hold, dry-run, rollback đã diễn tập |

Việc “đã sao chép đủ 100% user” chỉ nói lên số lượng bản ghi, chưa chứng minh những bất biến trên.

## 4. Khảo sát trước khi chuyển ứng dụng

### 4.1. Inventory user và quyền

Với từng ứng dụng/tenant, ghi nhận:

- Owner nghiệp vụ, owner kỹ thuật, hệ thống tích hợp và SLA.
- Giao thức đăng nhập: OIDC, SAML, LDAP, local password, OAuth, API key, mTLS, VPN.
- Khóa user/account: app user ID, IdP subject/NameID, SCIM id, externalId, username, email.
- Cách cấp quyền: IdP group claim, SCIM group, app role, direct grant, workflow thủ công, JIT.
- Role/permission, group lồng nhau, administrator, delegated access và exception.
- Quyền theo tài nguyên: dự án, ticket, tài khoản khách hàng, document, row-level và field-level ACL.
- Active/inactive/blocked user, guest, contractor, rejoiner và account có nhiều persona.
- Service account, bot, workflow, OAuth consent, job scheduler, webhook, API token, personal access token.
- Cơ chế deactivation, session invalidation, audit export, API pagination, rate limit, backup/restore.

Ví dụ:

| Đối tượng | Truy cập | Tài nguyên / quyền | Điều cần kiểm tra |
|---|---|---|---|
| Nhân viên Sales | SSO, nhóm | Khách hàng thuộc team | Team scope mới có tương đương không? |
| Sales manager | SSO + MFA | Duyệt giảm giá, xem dữ liệu nhóm | SoD, cấp duyệt và phạm vi bản ghi |
| Nhà thầu | Guest SSO | Project có ngày hết hạn | Contractor expiry không lệ thuộc HRIS nhân viên |
| Admin | SSO + MFA nâng cao | Cấu hình tenant, export | Không tự copy đặc quyền rộng |
| Bot tích hợp | OAuth client/token | Đọc và cập nhật record | Quyền tối thiểu, rotate secret, owner |
| Tài khoản local | Mật khẩu độc lập | Chức năng ứng dụng | Không được bỏ sót khi xử lý leaver |

### 4.2. Đo baseline trước cutover

Chụp trạng thái account, entitlement, record ownership, dữ liệu nhạy cảm, session/token đang hoạt động, orphan/duplicate và JML latency. Phân biệt quyền **đã sai từ trước** với drift mới do migration. Với ứng dụng lớn, lấy baseline theo cohort, department, tenant và mức độ nhạy cảm.

Đặc biệt tìm **đường hard-code** trong tích hợp: URL API, tenant ID, app user ID, group ID, role name, callback URL, signing certificate, client ID, scope, webhook secret và scheduled job. Chuyển dữ liệu mà bỏ qua chúng có thể làm lỗi nghiệp vụ hoặc để lại credential cũ.

### 4.3. Đừng giả định một người chỉ có một account

Một chủ thể có thể cố ý có account người dùng thường, privileged account riêng hoặc nhiều affiliation/tenant. Ngược lại, service account là một identity phi con người và có owner chịu trách nhiệm. Khi đối soát duplicate, phải phân biệt **nhiều account hợp lệ theo mục đích** với **duplicate ngoài dự kiến**.

## 5. Ánh xạ danh tính và tài khoản ứng dụng

### 5.1. Những khóa khác nhau

| Định danh | Phạm vi | Lưu ý |
|---|---|---|
| **Canonical person ID** | Identity registry/IAM | Ổn định, không dựa trên email, không tái sử dụng |
| **App user ID cũ** | Ứng dụng nguồn | Có thể là khóa owner của dữ liệu và lịch sử |
| **App user ID mới** | Ứng dụng đích | Có thể được sinh mới, phải liên kết với canonical ID |
| **SCIM `id`** | Resource tại service provider | Không mặc định bằng canonical ID |
| **SCIM `externalId`** | Khóa do provisioning client cung cấp | Phải có quy ước và hành vi vendor rõ |
| **OIDC issuer + sub** | Principal trong phạm vi issuer | Có thể thay khi đổi IdP/client |
| **SAML NameID** | Subject trong federation context | Phải xác minh format, issuer và tính ổn định |
| **Email / UPN** | Liên hệ hoặc tên đăng nhập | Có thể thay đổi hoặc được tái sử dụng |

Không được tự gộp account chỉ dựa trên email. Nếu CRM cũ và CRM mới dùng cùng email, vẫn phải xác minh người sở hữu, account type, tenant context và dữ liệu liên quan.

### 5.2. Ví dụ bảng crosswalk

~~~yaml
canonicalPersonId: person-00518
personType: employee
lifecycleStatus: active
applicationLinks:
  - system: crm-legacy
    tenant: corp-a
    appUserId: old-user-918
  - system: crm-cloud
    tenant: corp-a
    appUserId: new-user-271
identityEvidence:
  source: verified-hr-record
  approvedByRole: identity-steward
  mappingVersion: 5
dataOwnership:
  oldOwnerId: old-user-918
  newOwnerId: new-user-271
~~~

Dữ liệu này **chỉ minh họa mô hình**, không phải schema tiêu chuẩn hay ID có thật. Bảng mapping nên lưu actor, approver, nguồn bằng chứng, timestamp, phạm vi tenant, mapping version và lý do sửa. Ràng buộc duy nhất cho cặp **(application, tenant, appUserId)** giúp tránh một account đồng thời trỏ vào hai người.

Quy trình matching an toàn:

1. Xác định chủ thể từ nguồn có thẩm quyền và canonical ID.
2. So khớp account nguồn và đích bằng bảng mapping tin cậy.
3. Đối chiếu ngữ cảnh tenant, loại account, owner dữ liệu, lịch sử quyền và các bằng chứng độc lập.
4. Với trường hợp một–nhiều, nhiều–một hoặc thiếu chứng cứ: **quarantine**, không auto-merge.
5. Chỉ link/merge theo khả năng sản phẩm và phê duyệt; giữ audit trước/sau.
6. Giữ mapping đủ lâu cho reconciliation, điều tra và rollback theo retention policy.

**Link** bổ sung quan hệ giữa các account đã xác minh của cùng một chủ thể. **Merge** hợp nhất hai hồ sơ từng được coi là độc lập; merge có thể trộn dữ liệu và quyền, cần đánh giá rủi ro riêng.

### 5.3. Các trường hợp đặc biệt

- Người đổi email hoặc họ tên: vẫn giữ canonical identity.
- Nhà thầu chuyển thành nhân viên: xác minh lại tư cách và tính lại quyền, không tự giữ quyền contractor.
- Người nghỉ việc nhưng dữ liệu còn cần bảo tồn: chuyển ownership theo policy, không mở lại account chỉ để đọc history.
- Một người ở hai tenant: mapping phải có tenant context.
- Shared queue/nhóm được cấp ownership: xác định owner group và người chịu trách nhiệm.
- Privileged account riêng: không gộp account admin vào account thường để “giản lược” migration.

## 6. Chuyển entitlement theo ngữ nghĩa, không theo tên

Đây là chỗ thường gây **mất quyền cần thiết hoặc cấp vượt quyền**. Role có cùng tên trong hai ứng dụng có thể cho phép các hành động rất khác nhau.

### 6.1. Entitlement catalog

Với mỗi quyền ở app nguồn, ghi rõ:

- Mã quyền và mục đích nghiệp vụ.
- Resource type, action, scope: tenant, team, project, record, field.
- Nguồn cấp: role, group, direct grant, delegated admin, policy.
- Điều kiện được cấp: department, employmentType, jobFunction, manager, loại hợp đồng.
- Owner, approver, risk tier, hạn hiệu lực và access review.
- Ràng buộc SoD hoặc yêu cầu step-up/MFA cho hành động nhạy cảm.
- Mapping sang role/permission ở ứng dụng mới.
- Bài kiểm tra hành vi **được phép** và **bị từ chối**.

### 6.2. Ma trận ví dụ

| Quyền ở CRM-Legacy | Ý nghĩa cũ đã xác minh | Thiết kế tại CRM-Cloud | Rủi ro |
|---|---|---|---|
| `SALES_READ` | Đọc khách hàng thuộc team | Reader + team scope | Role reader toàn tenant quá rộng |
| `SALES_EDIT` | Sửa record mình được giao | Editor + owner/team policy | Ghi record của nhóm khác |
| `EXPORT_ALL` | Xuất dữ liệu nhạy cảm toàn tổ chức | Quyền riêng, cần approval mới | Tự gộp vào admin |
| `APPROVE_DISCOUNT` | Duyệt theo ngưỡng | Policy role + hạn mức | SoD với người tạo đề xuất |
| `APP_ADMIN` | Quản trị nhiều chức năng | Tách admin role tối thiểu | Tăng quyền do role mới gộp |

Một mapping có thể 1→nhiều, nhiều→1 hoặc không có tương đương. Chủ ứng dụng và security phải phê duyệt **quyền theo hành vi**, không phê duyệt qua tên role giống nhau.

### 6.3. RBAC, ABAC và SoD

**RBAC** gắn quyền với vai trò. **ABAC** quyết định theo thuộc tính chủ thể, tài nguyên và ngữ cảnh. Ví dụ mã đơn vị `FIN` trong app cũ đổi thành `FINANCE` ở app mới; policy thiếu bước chuẩn hóa có thể cấp sai quyền.

Kiểm thử các tình huống:

- Người dùng role Sales chỉ xem đúng team của mình.
- Nhân viên chuyển Sales → Finance mất quyền Sales cũ.
- Một user không thể vừa tạo vừa tự duyệt một giao dịch nếu SoD cấm.
- User có group claim đúng nhưng còn direct grant trái chính sách ở app mới.
- Role admin tạm cho migration có hạn và được tự thu hồi.
- Quyền truy cập qua API/export phù hợp với quyền ở giao diện.

**Desired entitlements** đến từ policy hiện hành và ngoại lệ được phê duyệt. **Actual entitlements** là quyền app mới đang thực thi: nhóm, direct role, local ACL, delegated access và token. Phải đối soát hai phía; chỉ đọc danh sách group chưa đủ.

## 7. Di trú data ownership và quyền theo bản ghi

Nếu copy dữ liệu đúng nhưng không chuyển **authorization context**, record có thể bị người không hợp lệ xem hoặc owner hợp lệ không còn thấy.

### 7.1. Các lớp dữ liệu liên quan IAM

- Record owner, creator, assignee, team, organization/tenant.
- Nhóm người xem/sửa, record-level ACL, field-level access.
- Delegated owner, shared queue, approval chain.
- Dữ liệu của người đã nghỉ hoặc tài khoản đã bị khóa.
- Lịch sử audit có subject ID của hệ nguồn.
- Chia sẻ cho guest, partner và các liên kết công khai có điều kiện.

### 7.2. Cách chuyển ownership

1. Lập mapping record ID và owner ID cũ ↔ ID mới.
2. Xác minh owner là user, group hay service identity; không mặc định owner luôn là người.
3. Tính lại phạm vi quyền theo policy hiện hành thay vì copy ACL cũ nguyên xi.
4. Với owner không còn active, áp quy trình bàn giao và retention đã phê duyệt.
5. Kiểm thử cả positive và negative authorization trên dữ liệu mẫu an toàn.
6. Kiểm tra API, báo cáo và chức năng xuất dữ liệu; chúng có thể bỏ qua filter UI.
7. Giữ lịch sử truy vết actor cũ, không gán sai hành động quá khứ cho user mới.

**Ví dụ:** Role “Manager” ở app cũ chỉ xem record thuộc nhóm mình quản lý. Role “Manager” ở app mới mặc định xem toàn tenant. Copy theo tên tạo privilege escalation. Phải cấu hình scope hoặc custom policy tương đương, rồi thử với record của nhóm khác.

## 8. Xác thực, SSO và account linking

Ứng dụng đích có thể dùng cùng IdP nhưng khóa nhận diện nội bộ vẫn khác. Cần xác định ứng dụng liên kết user bằng **OIDC issuer + sub**, SAML **issuer/NameID**, SCIM externalId hoặc một ID riêng.

### 8.1. Tránh JIT tạo account trùng

Một số ứng dụng có **just-in-time (JIT) provisioning** khi người dùng đăng nhập lần đầu. Nếu connector SCIM đã tạo account mới nhưng JIT không nhận ra liên kết, hệ thống có thể sinh account thứ hai, mỗi account có dữ liệu/quyền khác nhau.

Trước khi mở đăng nhập diện rộng:

- Xác nhận cách vendor hỗ trợ pre-link, external ID và cập nhật user hiện có.
- Kiểm thử trên người đổi email, người có nhiều role và trường hợp trùng email.
- Không auto-create khi mapping chưa đủ bằng chứng.
- Quy định ai là writer và quy tắc giải quyết xung đột SCIM/JIT.
- Xác minh không tồn tại app user ẩn hoặc role cũ sau liên kết.

### 8.2. Không bỏ sót đường truy cập ngoài SSO

SSO thành công không chứng minh tất cả credential cũ đã hết hiệu lực. Kiểm tra:

- Local username/password hoặc quyền đăng nhập khẩn cấp.
- Mobile/desktop session và refresh token.
- Personal access token, API key, SSH key.
- OAuth delegated consent cho ứng dụng bên thứ ba.
- Bot, service principal và certificate.
- Guest account, account liên tenant và tích hợp webhook.

Một token tự chứa có thể tiếp tục hợp lệ đến hạn hết hiệu lực nếu resource server không hỗ trợ thu hồi tức thì. Cần thiết kế SLA, session lifetime và biện pháp giảm rủi ro theo khả năng sản phẩm.

## 9. Provisioning qua SCIM/API

### 9.1. Phân biệt các loại ID

- **SCIM id:** do service provider phát hành, dùng để thao tác trên resource trong SP.
- **SCIM externalId:** giá trị phía client định nghĩa để liên kết với hệ quản lý danh tính.
- **Application user ID:** khóa nội bộ của app; có thể giống SCIM id ở vài sản phẩm nhưng không được mặc định.
- **Canonical person ID:** khóa danh tính chuẩn; chỉ dùng làm externalId nếu vendor và thiết kế hỗ trợ.

Trước khi thay connector, phải kiểm kê tài khoản app mới đang có và xác nhận phương pháp **link/update** thay vì tạo mới theo email.

### 9.2. Ma trận hành vi cần thử

| Tác vụ | Kết quả mong đợi |
|---|---|
| Create | Tạo đúng account cho chủ thể được xác minh, role ban đầu tối thiểu |
| Update attribute | Đổi email, manager, department mà không mất liên kết |
| Add/remove group | Quyền tăng/giảm theo policy, không để direct grant tồn dư |
| Deactivate | Chặn truy cập theo effective time, kiểm tra ứng dụng và phiên |
| Rejoiner | Xác minh lại trước khi khôi phục account, tính lại quyền |
| Retry/duplicate event | Idempotent, không tạo user/role lặp |
| Out-of-order event | Event cũ không hồi sinh account đã nghỉ |
| API failure/timeout | Retry/backoff có kiểm soát, lưu lỗi và đối soát |
| Bulk change | Có guardrail, không tự xóa hàng loạt do source thiếu |
| Reconciliation | Đọc actual state từ ứng dụng đích, không chỉ HTTP response |

SCIM hoặc API vendor có thể khác nhau về soft-delete, deactivate, PATCH, group semantics và rate limit. Phải kiểm thử trên sản phẩm và phiên bản thực tế.

### 9.3. Single writer trong giai đoạn song song

Đề ra ma trận **source of truth** cho từng thuộc tính/role/cohort. Có thể cùng cập nhật app cũ và mới từ IAM/IGA, nhưng không để hai connector tự đọc/ghi lẫn nhau tạo vòng lặp.

Ví dụ lỗi: IAM cập nhật nhóm Finance ở app mới, một sync ngược lấy nhóm cũ từ app cũ rồi ghi đè; quyền dao động giữa hai trạng thái. Giải pháp là writer duy nhất có thẩm quyền, xác định phiên bản sự kiện và đối soát định kỳ.

### 9.4. Pseudocode xử lý lifecycle

~~~text
onLifecycleEvent(event):
    verifyAuthoritativeSource(event)
    if alreadyProcessed(event.id):
        return NO_OP

    person = resolveCanonicalIdentityWithEvidence(event)
    if person is ambiguous:
        quarantine(event)
        return NEED_REVIEW

    if event.version < latestAcceptedVersion(person):
        return STALE_EVENT

    oldAccount = lookupVerifiedOldAppAccount(person)
    newAccount = lookupVerifiedNewAppAccount(person)

    desired = evaluateCurrentJmlAndEntitlementPolicy(
        person, event.effectiveTime, approvedExceptions
    )

    if unusualBulkGrantOrDisable(desired):
        holdAndRequestApproval(event)
        return HOLD

    applyIdempotentlyViaAuthorizedWriter(newAccount, desired)
    reconcileAppEntitlementsAndSessions(newAccount, desired)
    audit(event.id, person.id, oldAccount, newAccount, desired)
~~~

Đây là **mã giả**, không phải mã triển khai production. Hệ thực cần xử lý concurrency, transaction/queue, retry, race condition, version và kiểm tra kết quả ở từng target.

## 10. Bảo toàn Joiner–Mover–Leaver

Việc nhập snapshot user không mang theo toàn bộ logic vòng đời. Trong thời gian migration, HRIS/nguồn hợp đồng vẫn phát sự kiện mới; IAM/IGA phải tính **trạng thái quyền ở thời điểm hiện hành**.

| Giai đoạn | Luồng cần giữ | Nguy cơ đặc thù |
|---|---|---|
| **Joiner** | Xác minh, link/tạo account, cấp quyền theo ngày hiệu lực | JIT/SCIM sinh duplicate; cấp quyền quá sớm |
| **Mover** | Cấp role mới, thu hồi role cũ, kiểm tra SoD | Chỉ thêm quyền mới, direct role cũ còn tồn dư |
| **Leaver** | Ngừng SSO/local auth, thu hồi app role, token, session | App cũ còn hoạt động, token/API key không bị revoke |
| **Rejoiner** | Xác minh lại và tính lại quyền | Khôi phục quyền cũ không có lý do |
| **Contractor expiry** | Theo nguồn hợp đồng có thẩm quyền | HRIS nhân viên không chứa nhà thầu |
| **Leave of absence** | Xử lý trạng thái tạm thời theo policy | Bị hiểu nhầm thành nghỉ việc vĩnh viễn |

### 10.1. Joiner

Có thể chuẩn bị account trước ngày bắt đầu làm việc nhưng kích hoạt quyền phải theo chính sách. Nếu người mới đã có account từ giai đoạn thử nghiệm, cần **link** thay vì tạo lại.

### 10.2. Mover

Nhân viên chuyển từ Sales sang Finance trong ngày cutover. Snapshot cũ còn quyền CRM Sales nhưng policy hiện hành chỉ cho Finance. IAM cần replay event hoặc tính lại desired entitlement trước khi kích hoạt app mới, xử lý direct grant và quyền bàn giao có expiry.

### 10.3. Leaver

Khi người dùng nghỉ việc, phải chặn cả hai ứng dụng đang phục vụ, kể cả local login, API key, OAuth grant và phiên. Không coi “không còn trong batch HRIS” là bằng chứng leaver duy nhất: batch lỗi có thể thiếu dữ liệu và gây mass deprovision.

### 10.4. Service account và workload identity

Service account, bot và workload OAuth thường không có record trong HRIS. Dùng registry riêng có owner, lý do tồn tại, quyền tối thiểu, target API, secret/credential, expiry và review cycle.

Khi owner cá nhân nghỉ việc, cần bàn giao service account và rotate credential theo runbook, không tự động xóa job đang phục vụ sản xuất mà không đánh giá phụ thuộc. Cũng không để service account trở thành account vô chủ.

## 11. Các chiến lược migration

| Chiến lược | Cơ chế | Phù hợp | Rủi ro |
|---|---|---|---|
| **Big-bang** | Đổi toàn bộ tại một cửa sổ | Ít user và phụ thuộc, rollback đã thử | Tác động rộng khi mapping/role sai |
| **Phased by cohort** | Chuyển từng nhóm người dùng | Tổ chức lớn, nhiều đơn vị | Record/role chia sẻ giữa cohort |
| **Phased by capability** | Chuyển từng module/tính năng | Hệ có thể chia ranh giới nghiệp vụ | Hai app giữ dữ liệu/quyền khác nhau |
| **Parallel run** | Chạy cũ và mới cùng lúc | Muốn so sánh và thử nghiệm trên thực tế | Dual write, drift, leaver phải bị chặn ở cả hai |
| **Read-only legacy** | App cũ giữ quyền đọc có kiểm soát | Cần tra cứu lịch sử | “Chỉ đọc” vẫn có thể lộ dữ liệu |
| **Incremental replacement** | Thay dần API/workflow cũ | Nhiều tích hợp phức tạp | Source of truth không rõ, lộ đường truy cập cũ |

Chọn theo khả năng hỗ trợ account linking, scope dữ liệu, SLA, độ phức tạp tích hợp, rủi ro vận hành và khả năng rollback. **Shadow/dry-run** giúp so mapping và entitlement dự kiến trước khi cho writer tác động production.

## 12. Từng bước triển khai

### Giai đoạn A — Discover & design

1. Lập inventory account, role, group, data owner, local access, token, integration và owner.
2. Chụp baseline user/account/entitlement và JML latency; phân loại drift đã có.
3. Xác định canonical ID, mapping old/new account/record owner và nguồn có thẩm quyền.
4. Thiết kế entitlement catalog, RBAC/ABAC, SoD và kiểm thử quyền trên record/API.
5. Chốt single writer, chiến lược rollout, no-go criteria, SLA và runbook rollback.

### Giai đoạn B — Build & mapping

1. Cấu hình app mới, SSO/MFA, API, SCIM và quyền connector tối thiểu.
2. Tạo/link account đã xác minh; quarantine ca mơ hồ.
3. Ánh xạ role/permission dựa trên hành vi và scope, có phê duyệt.
4. Chuyển dữ liệu mẫu cùng owner/ACL; kiểm tra cả quyền bị từ chối.
5. Thiết lập queue, event deduplication, idempotency, monitoring và reconciliation.
6. Chuẩn bị service identity, secret, API scope và phương án thu hồi credential cũ.

### Giai đoạn C — Pilot

Chọn cohort gồm user thường, user nhiều role, manager, admin, joiner có ngày hiệu lực tương lai, mover, leaver, nhà thầu, guest, service account, user có direct grant và owner record đặc biệt. Thử đăng nhập, thao tác nghiệp vụ, account linking, API, export và quyền dữ liệu.

Bổ sung failure case: source batch rỗng, SCIM trả lỗi, API rate limit, event trùng/sai thứ tự, quyền mới rộng hơn, mapping mơ hồ, session/token tồn dư, rollback khi có event mới.

### Giai đoạn D — Cutover

1. Xác nhận go/no-go, backup/snapshot, mapping version, phân công trực và kênh báo sự cố.
2. Tạm dừng/chuyển writer theo cohort, ghi mốc event backlog và dữ liệu delta.
3. Chuyển account, record ownership, role và routing theo trình tự có kiểm soát.
4. Replay JML delta theo version/effective time; không hồi sinh account của leaver.
5. Kiểm tra SSO/MFA, actual entitlement, quyền record, API và service job.
6. Theo dõi drift, lỗi, queue lag và kết quả người dùng; pause khi vượt guardrail.

### Giai đoạn E — Stabilize & retire

Đối soát toàn bộ desired vs actual state, review quyền đặc quyền/direct grant, xác nhận không còn đường truy cập app cũ ngoài phạm vi được duyệt. Thu hồi credential, connector, OAuth client, certificate, local account và quyền quản trị cũ theo kế hoạch. Giữ hồ sơ audit/crosswalk theo retention và chủ ứng dụng ký nghiệm thu.

## 13. Đối soát, guardrail và failure mode

| Chênh lệch | Nguyên nhân | Hành động |
|---|---|---|
| Có người nhưng app đích thiếu account | Provisioning lỗi hoặc chưa đến ngày hiệu lực | Retry/ticket theo SLA, không tự tạo trùng |
| Hai app account trỏ một người ngoài thiết kế | JIT và SCIM cùng tạo | Pause, xác minh link/merge |
| Một app account trỏ hai người | Mapping sai nghiêm trọng | Cách ly account và điều tra |
| User có role quá rộng | Role mapping 1:1 theo tên | Sửa scope, thu hồi quyền và review |
| Owner dữ liệu lệch | Mapping record owner sai | Đối soát crosswalk, test ACL |
| User đã nghỉ vẫn đăng nhập được | Local auth/token/session hoặc app cũ | Thu hồi từng đường, xác minh thực tế |
| Group thay đổi liên tục | Hai writer tranh chấp | Pause một writer, sửa authority |
| Batch nguồn giảm bất thường | Export lỗi, sự kiện thiếu | Hold, xác minh trước bulk disable |
| Service bot thất bại | Token/endpoint/scope đổi | Sửa theo owner, kiểm tra least privilege |

**Guardrail bulk change:** Nếu một batch đề xuất vô hiệu hóa một tỷ lệ lớn user active hoặc cấp nhiều quyền nhạy cảm, hệ thống phải nhận diện bất thường, dừng các thay đổi ảnh hưởng rộng và xác minh nguồn có thẩm quyền. Ngưỡng thực tế dựa trên baseline tổ chức; không sử dụng một ngưỡng minh họa như tiêu chuẩn phổ quát.

## 14. Bảo mật, quyền riêng tư và audit

Connector nên dùng service identity riêng với quyền tối thiểu; phân biệt credential **read-only dry-run** với writer production. Lưu secret trong vault, rotate khi chuyển sang app mới; giới hạn quyền xem export dữ liệu, bảng mapping và nhật ký.

Mỗi quyết định tạo/link/disable account, chuyển record ownership, grant/revoke role cần lưu:

| Trường audit | Ý nghĩa |
|---|---|
| `eventId` / `correlationId` | Liên kết HR source, IAM, app cũ và mới |
| Canonical person ID | Chủ thể thực của thay đổi |
| Old/new app user ID và tenant | Bằng chứng liên kết account |
| Old/new entitlement, record scope | Quyền và tài nguyên bị tác động |
| Policy/mapping version | Quy tắc đã tạo ra quyết định |
| Actor, approver, exception, ticket | Người/hệ thống chịu trách nhiệm |
| Timestamp, target, outcome/retry | Điều tra thời điểm, lỗi và trạng thái |

Không ghi password, private key, raw token hoặc dữ liệu HR nhạy cảm không cần thiết vào log. Áp mã hóa, phân quyền truy cập và retention phù hợp chính sách/pháp luật áp dụng.

Sau chuyển đổi, **access review** cần rà soát role đặc quyền, direct grant, guest, service account, account shared và exception migration. Một quyền không còn owner hoặc lý do nghiệp vụ phải có kế hoạch thu hồi.

## 15. Rollback không chỉ là chuyển URL về ứng dụng cũ

Một số thay đổi khó đảo ngược như merge account, xóa dữ liệu, rotate credential, chuyển record ownership hoặc cập nhật dữ liệu ở cả hai ứng dụng. Vì vậy cần diễn tập rollback trước cutover.

### 15.1. Khi nào cần pause/rollback?

Các tình huống như mapping sai người, user nhìn thấy dữ liệu ngoài scope, mất đăng nhập rộng, leaver vẫn truy cập, cấp nhầm đặc quyền hoặc sync gây mass disable cần ngưỡng và owner quyết định.

### 15.2. Runbook rollback

1. **Pause writer** gây lỗi; lưu snapshot, mapping version, event backlog, log và audit.
2. Xác định mọi joiner/mover/leaver, role change và data update phát sinh sau cutover.
3. Chốt hệ thống nào giữ dữ liệu có thẩm quyền và IAM nào tính quyền hiện hành.
4. Khôi phục routing/trust chỉ cho account hợp lệ; không mở lại leaver từ snapshot cũ.
5. Replay delta idempotent, xử lý version và kiểm chứng quyền thực tế ở cả hai hệ.
6. Xác minh SSO/MFA, local auth, API token, record ownership và service job.
7. Ghi incident, nguyên nhân, hành động khắc phục và quyết định có tiếp tục rollout.

**Lưu ý:** một bản backup cũ có thể chứa trạng thái active của người đã nghỉ việc. Restore từ backup phải đi kèm tính lại desired state theo **JML hiện tại**, không copy quyền cũ một cách mù quáng.

## 16. Case study: chuyển CRM-Legacy sang CRM-Cloud

Giả sử công ty có **900 nhân viên, 60 nhà thầu, 4 nhóm kinh doanh và 18 hệ tích hợp**. CRM-Legacy dùng SSO và API tự phát, còn CRM-Cloud dùng cùng IdP nhưng có app user ID mới, RBAC khác và SCIM provisioning.

### Bước 1 — Đánh giá hiện trạng

Nhóm phát hiện 23 người có quyền `EXPORT_ALL` cấp trực tiếp, 7 bot dùng personal API token, một số record thuộc account của người đã nghỉ việc và role “Manager” ở cloud cho phép xem phạm vi rộng hơn ở legacy.

### Bước 2 — Mapping danh tính và quyền

Identity registry giữ canonical person ID. Bảng old/new app user ID được xác minh bởi nguồn danh tính và chủ ứng dụng. Các hồ sơ trùng email hoặc ownership không rõ được cách ly. Entitlement owner quyết định `EXPORT_ALL` phải được phê duyệt lại; role Manager được giới hạn theo team. Record của leaver được bàn giao theo policy, không kích hoạt lại user.

### Bước 3 — Pilot

Pilot phát hiện hai lỗi:

- Một nhân viên chuyển Sales → Finance sau thời điểm snapshot nhưng trước lúc app mới được kích hoạt. Đồng bộ snapshot khiến user còn quyền Sales.
- Một user đăng nhập SSO lần đầu làm JIT tạo account mới trong khi SCIM đã có account cùng người.

Nhóm sửa bằng cách tính lại desired state từ JML hiện hành, replay delta theo version, pre-link account và giới hạn auto-create. Sau đó thử lại cả cấp/thu hồi quyền và quyền bị từ chối trên record khác team.

### Bước 4 — Cutover

Chuyển từng cohort; app cũ chỉ đọc có kiểm soát trong thời gian được phê duyệt. Tất cả đường local/API access ở app cũ tiếp tục được giám sát và thu hồi theo leaver. Bot được cấp scope tối thiểu và rotate credential; quyền cũ chỉ bị loại bỏ sau khi có bằng chứng tác vụ mới hoạt động.

### Bước 5 — Nghiệm thu

Chủ ứng dụng ký xác nhận khi mapping account đúng, owner dữ liệu đúng, quyền thực tế phù hợp policy, JML hoạt động, direct grant/token tồn dư có owner và audit đủ truy vết.

**Bài học:** Di trú application thành công giữ **identity continuity**, **data access correctness** và **lifecycle correctness**; thay giao diện/URL chưa đủ.

## 17. Bộ kiểm thử nghiệm thu

| Mã | Tình huống | Kết quả mong đợi |
|---|---|---|
| T01 | User đổi email nhưng không đổi chủ thể | Account cũ/mới link đúng canonical ID |
| T02 | Hai người trùng tên/email | Không tự merge; quarantine |
| T03 | App mới dùng user ID khác | Dữ liệu và quyền link đúng user |
| T04 | JIT và SCIM cùng tạo user | Không duplicate; single writer rõ |
| T05 | Joiner có effective date tương lai | Account/quyền hoạt động đúng thời điểm |
| T06 | Mover đổi đơn vị | Thu hồi role/direct grant cũ, cấp quyền mới và kiểm tra SoD |
| T07 | Leaver giữa cutover | Chặn app cũ/mới, local login, session/token trong SLA |
| T08 | Rejoiner | Không tự khôi phục quyền cũ |
| T09 | Contractor expiry | Quyền hết hạn theo nguồn nhà thầu |
| T10 | Role mới cùng tên nhưng scope rộng hơn | Không cấp quá quyền |
| T11 | Record-level và field-level security | User đúng được xem/sửa, user sai bị chặn qua UI/API |
| T12 | Record của owner đã nghỉ | Ownership được bàn giao, không mở account cũ |
| T13 | SCIM retry lặp | Không tạo user/role trùng |
| T14 | JML event đến sai thứ tự | Không hồi sinh leaver hoặc role đã thu hồi |
| T15 | API timeout/rate limit | Retry/backoff và reconciliation có audit |
| T16 | Batch HRIS thiếu dữ liệu | Guardrail không mass disable |
| T17 | Direct grant/PAM privilege | Phát hiện và xử lý quyền tồn dư |
| T18 | API token/personal token cũ | Revoked/rotated theo lộ trình |
| T19 | Service account có owner nghỉ việc | Có owner thay thế, không orphan |
| T20 | Parallel run | Không có xung đột dữ liệu hoặc quyền do dual writer |
| T21 | Rollback sau mover/leaver mới | Không cấp lại quyền đã thu hồi hợp lệ |
| T22 | Guest và người dùng nhiều tenant | Đúng identity context, đúng scope |

Với mỗi ca, lưu expected/actual result, cohort/tenant, user thử, log ID, thời điểm, người kiểm tra, owner và ngoại lệ. Tối thiểu phải có kiểm thử **quyền bị từ chối**, vì một test “login OK” không phát hiện lộ dữ liệu.

## 18. KPI và tiêu chí go/no-go

Các số đo nên theo dõi theo cohort, ứng dụng và nhóm quyền:

- **Verified mapping coverage:** tỷ lệ account đã có mapping có bằng chứng.
- **Duplicate/orphan rate:** tỷ lệ account ngoài thiết kế hoặc thiếu chủ thể/owner.
- **Entitlement drift:** chênh lệch quyền thực tế và quyền được phê duyệt.
- **Record ownership accuracy:** tỷ lệ record có owner/ACL đúng ở đích.
- **Provisioning success & latency:** tỷ lệ và độ trễ create/update/disable.
- **Leaver revocation latency:** thời gian từ effective leaver đến khi mọi đường truy cập thuộc phạm vi bị thu hồi.
- **SSO/API failure rate:** lỗi đăng nhập/tích hợp theo nhóm người dùng.
- **Token/credential retirement coverage:** tỷ lệ đường truy cập hệ cũ đã xử lý xong.
- **Outstanding migration exceptions:** các ca mơ hồ, lỗi quyền và owner chưa giải quyết.

**Go/no-go** phải dựa trên ngưỡng đã được owner nghiệp vụ và security thống nhất từ baseline, không chỉ dựa số lượng dữ liệu copy.

### 18.1. RACI ngắn gọn

| Vai trò | Trách nhiệm |
|---|---|
| HR/nguồn nhà thầu | Trạng thái lao động và effective time |
| IAM/IGA và identity steward | Canonical ID, linking, JML, entitlement desired state |
| Chủ ứng dụng/nghiệp vụ | Role mapping, data ownership, nghiệm thu chức năng |
| Security/PAM | Quyền đặc quyền, SoD, secret/token và risk acceptance |
| Migration lead/vận hành | Cutover, rollback, incident và KPI |
| Chủ dữ liệu/privacy | Truy cập dữ liệu, retention, chia sẻ và quy định áp dụng |

## 19. Checklist trước và sau go-live

### Trước cutover

- [ ] Đã inventory account, role, group, token, API, session, service account và owner.
- [ ] Có mapping canonical ID ↔ old/new app user ID đã xác minh.
- [ ] Role/ABAC/SoD/record scope có owner phê duyệt và bộ kiểm thử.
- [ ] Đã thử JML, SSO/MFA, SCIM/API, JIT, local auth, guest và service account.
- [ ] Có quy tắc source of truth, single writer, retry và bulk-change guardrail.
- [ ] Có snapshot, audit, backup/restore, delta replay và rehearsal rollback.
- [ ] Có kênh hỗ trợ, ngưỡng go/no-go, người duyệt và nhân sự trực sự cố.

### Sau cutover

- [ ] Desired và actual entitlements đã được đối soát.
- [ ] Dữ liệu/record ownership và quyền bị từ chối đã kiểm chứng.
- [ ] Leaver, mover, contractor và rejoiner vẫn chạy đúng SLA.
- [ ] Duplicate, orphan, direct grant, admin role và exception có owner/hạn xử lý.
- [ ] API token, local credential, OAuth client và connector cũ đã được đóng theo kế hoạch.
- [ ] Lưu mapping/audit theo retention, owner ký nghiệm thu.

## 20. Những sai lầm thường gặp

**Dùng email làm khóa ghép:** có thể tạo duplicate hoặc ghép nhầm chủ thể. Dùng canonical person ID và account crosswalk được xác minh.

**Copy role theo tên:** cùng tên không đồng nghĩa cùng phạm vi. Ánh xạ theo quyền thực thi trên tài nguyên, có approval.

**Chỉ thử đăng nhập:** bỏ sót direct grant, record-level policy, API token và local login. Thử cả quyền **được phép** và **bị từ chối**.

**Cấp role mới mà không thu hồi role cũ:** mover tích lũy quyền, vi phạm least privilege/SoD. Tính desired state hiện hành, đối soát quyền cũ.

**Để hai writer tự ghi vòng lặp:** quyền và thuộc tính thay đổi liên tục. Chỉ định owner và chiều đồng bộ rõ.

**Xem user vắng trong batch là leaver:** batch lỗi có thể gây mass deprovision. Phải xác minh nguồn có thẩm quyền và guardrail.

**Quên account dịch vụ:** job bị gián đoạn hoặc credential cũ tồn tại. Dùng registry, owner, secret lifecycle riêng.

**Rollback bằng snapshot quyền cũ:** có thể hồi sinh leaver và quyền đã thu hồi. Replay JML mới nhất theo version.

**Ngừng app cũ quá sớm:** bỏ sót lịch sử, dữ liệu, audit và phụ thuộc. Retire theo exit criteria và retention được duyệt.

## 21. Câu hỏi tự kiểm tra

1. Vì sao đổi ứng dụng nhưng giữ nguyên IdP vẫn cần account linking?
2. SCIM `id`, `externalId`, canonical person ID và app user ID khác nhau thế nào?
3. Nếu role Manager ở app mới cho phép xem toàn tenant, cần làm gì khi role cũ chỉ xem một team?
4. Một nhân viên chuyển bộ phận trong cửa sổ cutover thì quyền nào có thẩm quyền?
5. Nếu JIT và SCIM cùng tạo account, lỗi gì xảy ra và xử lý ra sao?
6. Tại sao leaver đã disable trong IdP vẫn có thể dùng API key cũ?
7. Record owner của nhân viên đã nghỉ nên được xử lý thế nào?
8. Service account cần quản lý độc lập với HRIS người dùng ở điểm nào?
9. Vì sao kiểm thử negative authorization quan trọng như login thành công?
10. Khi rollback, làm sao tránh khôi phục quyền đã bị thu hồi sau snapshot?
11. Một batch dữ liệu nguồn bị rỗng bất thường cần trigger điều gì?
12. Tại sao không nên đánh giá migration chỉ bằng số lượng record đã import?

**Gợi ý:** Xem lại canonical identity, single writer, desired/actual entitlements, quyền theo dữ liệu, event version, reconciliation, token/session và bằng chứng kiểm toán.

## 22. Thuật ngữ và tài liệu nền tảng

| Thuật ngữ | Nghĩa |
|---|---|
| **Application account linking** | Liên kết account ứng dụng với đúng chủ thể chuẩn |
| **Canonical person ID** | Khóa danh tính ổn định không phụ thuộc ứng dụng |
| **Entitlement / direct grant** | Quyền cụ thể / quyền cấp trực tiếp |
| **RBAC / ABAC / SoD** | Kiểm soát theo role / thuộc tính / phân tách nhiệm vụ |
| **IdP / SSO / MFA** | Nhà cung cấp danh tính / đăng nhập một lần / xác thực đa yếu tố |
| **SCIM / JIT** | Provisioning user/group chuẩn hóa / tạo user khi đăng nhập lần đầu |
| **JML** | Joiner–Mover–Leaver |
| **Desired / actual state** | Trạng thái quyền kỳ vọng / thực tế |
| **Reconciliation** | Đối soát quyền và trạng thái account |
| **Coexistence / cutover / rollback** | Đồng tồn tại / chuyển đổi chính thức / khôi phục |
| **Orphan account / stale access** | Tài khoản vô chủ / quyền không còn lý do |
| **Idempotency** | Lặp lại thao tác không phát sinh tác động lặp ngoài ý muốn |

Tài liệu tra cứu khi triển khai:

- **RFC 7643** — SCIM Core Schema.
- **RFC 7644** — SCIM Protocol.
- **OpenID Connect Core 1.0** — nhận diện người dùng dựa trên issuer/subject.
- **OASIS SAML 2.0 Core và Bindings** — trust, assertion và liên kết subject.
- **NIST SP 800-53 (Access Control)** — nguyên tắc kiểm soát quyền, least privilege và audit.
- **Tài liệu chính thức của ứng dụng nguồn/đích** về account linking, JIT/SCIM, API, role/data ownership, session/token revocation, backup và rollback; hành vi cụ thể phụ thuộc sản phẩm.

**Tiêu chí cuối cùng:** Sau khi di trú application, cùng một chủ thể phải được nhận diện chính xác, giữ đúng ownership dữ liệu, chỉ có quyền hợp lệ theo trạng thái JML hiện tại và được thu hồi đầy đủ khi thay đổi vai trò hoặc rời tổ chức. Tất cả quyết định cần có bằng chứng đủ để đối soát, kiểm toán và phục hồi.

