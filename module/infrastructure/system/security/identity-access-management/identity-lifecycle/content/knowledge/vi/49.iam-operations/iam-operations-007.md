# Khắc phục account mồ côi trong IAM: nhận diện, xác minh chủ sở hữu và thu hồi quyền an toàn

## 1. Account mồ côi là gì và vì sao phải xử lý?

**Account mồ côi** (*orphan account*) là tài khoản đang tồn tại trong một hệ thống nhưng **không còn liên kết được với chủ thể, người bảo trợ hoặc chủ sở hữu hợp lệ** theo nguồn thông tin có thẩm quyền tại thời điểm kiểm tra. Account có thể chưa bị disable, có thể còn quyền, credential, phiên đăng nhập hoặc đường truy cập riêng. Không xác định được ai có trách nhiệm đối với account là một rủi ro quản trị danh tính, ngay cả khi chưa thấy hoạt động bất thường.

Trong chương **IAM operations** của module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, mục tiêu là vận hành vòng đời danh tính **Joiner–Mover–Leaver (JML)**: xác minh người mới, tạo tài khoản và cấp quyền đúng, điều chỉnh/thu hồi khi chuyển vai trò, chặn truy cập khi nghỉ việc và giảm **quyền truy cập tồn dư**. Khắc phục account mồ côi là công việc liên kết **Identity Provider (IdP), SSO, SCIM, RBAC/ABAC, service account, PAM, kiểm toán** và cả các hệ thống chưa tích hợp tập trung.

Một account có thể trở thành mồ côi vì nhân viên đã nghỉ mà ứng dụng không nhận sự kiện deprovision, nhà thầu hết sponsor, tài khoản tạo bằng tay không ghi owner, tài khoản local không được liên kết với danh tính IdP, khóa dịch vụ vẫn hoạt động khi workload đã ngừng hoặc quá trình đổi định danh làm mất mapping.

Tuy nhiên, **không có bản ghi HR không đồng nghĩa tự động là tài khoản mồ côi cần xóa ngay**. Tài khoản dịch vụ, tài khoản khẩn cấp được quản lý, đối tác B2B, khách bên ngoài và danh tính công nghệ có thể hợp lệ dù không có nhân sự tương ứng. Người vận hành phải xác minh **loại account, nguồn thẩm quyền và quan hệ sở hữu thực tế** trước khi thay đổi.

**Mục tiêu bài học:** phát hiện đúng, tránh nhầm tài khoản hợp lệ, ưu tiên chặn các đường truy cập có rủi ro, khôi phục liên kết chủ sở hữu khi thích hợp, vô hiệu hóa/thu hồi tài khoản không còn cần thiết và xác minh mọi đường quyền tại đích.

**Kết quả mong đợi sau bài học:**

1. Phân biệt orphan account, dormant account, disabled account, stale entitlement và account chưa được provisioning.
2. Tập hợp inventory IdP/SCIM/ứng dụng, dữ liệu nhân sự/nhà thầu và owner của workload để nhận diện sai lệch.
3. Xác minh account mapping bằng ID bền vững thay vì ghép tùy tiện theo email/tên.
4. Áp dụng quy trình triage, containment, xác minh owner, quyết định retain/relink/transfer/disable và hậu kiểm.
5. Xử lý các trường hợp Joiner, Mover, Leaver, guest, privileged account, service account và SCIM failure.
6. Đo lường, ghi audit và ngăn account bị tạo mồ côi trở lại.

> **Lưu ý:** Các bước dưới đây là runbook tham khảo, không phải lệnh xóa tài khoản trực tiếp. Quy tắc lưu giữ dữ liệu, thời gian vô hiệu hóa trước khi xóa, người phê duyệt và mức ưu tiên phải dựa trên chính sách tổ chức và khả năng của từng hệ thống.

## 2. Phân biệt các tình trạng tài khoản dễ nhầm

| Tình trạng | Bản chất | Có thể vẫn hợp lệ? | Hành động ban đầu |
|---|---|---|---|
| **Orphan account** | Không xác định được chủ thể/owner/sponsor hợp lệ hoặc quan hệ với nguồn chủ quản bị mất | Có, nếu inventory/mapping chưa đầy đủ | Xác minh danh tính, owner, nguồn và rủi ro |
| **Dormant account** | Ít hoặc không có hoạt động trong một khoảng thời gian | Có, ví dụ dự phòng hoặc công việc định kỳ | Kiểm tra nhu cầu, owner và chu kỳ sử dụng |
| **Stale account** | Account không còn phù hợp trạng thái vòng đời hoặc nhu cầu hiện tại | Thường cần remediation | Đối chiếu JML và tính hợp lệ của quyền |
| **Disabled account** | Account bị chặn đăng nhập hoặc không còn active | Có thể được giữ để audit/retention | Kiểm tra lý do, token/local access và retention |
| **Unmanaged local account** | Account không đồng bộ qua IdP/SCIM | Có, nếu được phê duyệt và có owner | Kiểm tra quyền, owner, local credential và kế hoạch quản lý |
| **Duplicate identity/account** | Một người có nhiều bản ghi, hoặc một account xuất hiện hai lần trong inventory | Có thể là do vai trò/tenant khác nhau | So định danh bất biến, không tự merge |
| **Guest/B2B account** | Tài khoản người ngoài có sponsor, tenant hoặc chính sách riêng | Có | Kiểm tra sponsor, hợp đồng, expiry và access review |
| **Workload/service identity** | Danh tính của dịch vụ, job, ứng dụng hoặc máy | Có | Tìm owner kỹ thuật/nghiệp vụ, dependency và secret |
| **Break-glass account** | Account khẩn cấp cố ý quản lý khác danh tính nhân sự | Có, nếu có chính sách riêng | Chuyển PAM/Security, không xóa vì không có HR row |
| **Not-yet-provisioned** | Nguồn đã có Joiner nhưng target chưa tạo user | Không phải orphan ở target | Xử lý provisioning failure thay vì tìm account để xóa |

**Phát hiện mồ côi là một giả thuyết cần được điều tra**, không phải kết luận có thể dùng để tự động xóa mọi account không khớp HRIS. Ví dụ một nhân viên đổi email có thể tạo sai lệch nếu inventory dùng email làm khóa; một tài khoản SSO được tạo kiểu just-in-time có thể chỉ tồn tại sau lần đăng nhập đầu tiên.

### 2.1. Rủi ro chính của account mồ côi

- **Truy cập tồn dư:** người đã nghỉ, nhà thầu hết hạn hoặc tài khoản không được quản lý còn quyền vào dữ liệu.
- **Thiếu trách nhiệm:** không biết ai phê duyệt quyền, ai rotate secret, ai trả lời audit hay xử lý incident.
- **Bị lợi dụng làm điểm bám:** local credential, API key, token hoặc quyền đặc quyền tồn tại ngoài vòng thu hồi tập trung.
- **Xung đột SoD/least privilege:** account phụ không chịu cùng review và có thể tích lũy quyền không phù hợp.
- **Gián đoạn vận hành nếu xử lý sai:** xóa nhầm service account, automation account, integration hoặc tài khoản khẩn cấp đang hoạt động.
- **Sai lệch dữ liệu:** account ứng dụng bị ghép với nhầm người khi email/username được tái sử dụng.

## 3. Những nguồn phải đối chiếu trong kiến trúc IAM

~~~mermaid
flowchart LR
    HR[HRIS / Workforce] --> JML[Bộ điều phối JML]
    CONTRACT[Nhà thầu / Sponsor] --> JML
    CATALOG[Danh mục ứng dụng, workload và owner] --> JML
    JML --> IDP[IdP / Directory]
    JML -->|SCIM / API| SAAS[SaaS / Ứng dụng nội bộ]
    IDP -->|OIDC / SAML SSO| SAAS
    SAAS --> LOCAL[Local accounts / grants / tokens]
    JML --> CLOUD[Cloud / Service principal / CI-CD]
    JML --> PAM[PAM / Break-glass]
    IDP --> AUDIT[Audit / SIEM]
    SAAS --> AUDIT
    CLOUD --> AUDIT
    PAM --> AUDIT
    AUDIT --> RECON[Phát hiện orphan / So actual với desired]
    RECON --> JML
~~~

### 3.1. Nguồn thẩm quyền theo loại identity

| Loại danh tính | Nguồn xác nhận hợp lệ thường gặp | Trường owner quan trọng |
|---|---|---|
| Nhân viên | HRIS + trạng thái JML | Employee/person ID, manager, ngày hiệu lực |
| Nhà thầu | Hệ thống hợp đồng/sponsor + JML | Contractor ID, sponsor, contract end |
| Người ngoài/guest | B2B guest directory + sponsor/access owner | Guest ID, tenant, expiry, lý do truy cập |
| Service account | Workload catalog/CMDB + owner + secret manager | Service ID, technical owner, business owner |
| Service principal/workload | Cloud/CI/CD/asset inventory + owner đã duyệt | Application ID, project, trust, service owner |
| Break-glass | PAM/Security exception registry | Privileged owner, lý do, cơ chế kiểm tra định kỳ |
| Shared/legacy account | Registry được phê duyệt có owner và trách nhiệm sử dụng | Account owner, hệ thống, ngày hết hạn và phương án thay thế |

Không có **một** nguồn thẩm quyền chung cho tất cả các loại account. Dữ liệu HR không thể tự định nghĩa owner của mọi workload; account có bản ghi ở IdP cũng chưa chắc có quan hệ lao động còn hợp lệ.

### 3.2. Actual state và desired state

- **Actual state:** bản ghi tại IdP, SaaS, VPN, cloud, local account; trạng thái active/disabled; membership, role, resource grant, session, API key và secret.
- **Desired state:** tập identity/account/quyền **đáng lẽ tồn tại** dựa trên lifecycle hiện hành, owner, approval, RBAC/ABAC, SoD, expiry và chính sách.
- **Mapping:** liên kết tin cậy giữa subject ID ở nguồn và ID đích, ví dụ HR person ID ↔ IdP object ID ↔ SCIM `externalId` ↔ application user ID.
- **Drift:** sai khác actual với desired, có thể là account thừa, account thiếu, role cũ, active trái policy hoặc local grant không được quản lý.

Một account không map được cần được gắn trạng thái **suspected orphan**, kiểm tra nguồn/mapping và phân loại. Chỉ sau khi xác minh mới quyết định **relink, retain with owner, quarantine, disable hoặc delete theo retention**.

## 4. Khóa định danh bền vững và các bẫy identity mapping

### 4.1. Không dùng email làm bằng chứng duy nhất

Email, username, display name và department có thể đổi. Email còn có thể được tái sử dụng sau khi người cũ nghỉ. Ghép một account cũ với nhân viên mới vì cùng email có thể chuyển sai dữ liệu và quyền.

**Thứ tự ưu tiên:**

1. Đối chiếu **immutable subject ID** hoặc ID được nguồn chủ quản cung cấp.
2. Liên kết IdP object ID và SCIM `externalId`/target user ID đã được quản lý.
3. Kiểm tra timestamp tạo account, tenant, lịch sử provisioning và evidence phê duyệt.
4. Nếu dữ liệu mâu thuẫn, chuyển người có thẩm quyền xác nhận **không tự merge/link**.

### 4.2. Các trường hợp mapping sai phổ biến

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Account có email hợp lệ nhưng không map HR | Email đổi, alias không đồng bộ, mapping ID mất | Lịch sử IdP, source subject ID và JML events |
| Hai SaaS account cùng email | Tenant khác, duplicate provisioning, tái tuyển dụng | Target IDs, owner, thời điểm tạo và app scope |
| HR Terminated nhưng app still active | Deprovision SCIM lỗi, local account ngoài luồng | Connector logs, app actual state và token/session |
| Một account có owner là người đã nghỉ | Owner của service account chưa bàn giao | Workload catalog, dependency, sponsor mới |
| Cloud principal không có email/HR row | Workload identity hợp lệ hoặc shadow principal | App ID, cloud audit, service owner, policy/trust |
| Guest không có bản ghi HR | B2B access thường không nằm trong HRIS | Sponsor, contract, expiry và access review |
| Account xuất hiện trong app nhưng IdP không có | Local login, JIT, federation ngoại bộ hoặc mapping sai | App authentication method, trust và owner |

### 4.3. Chuyển trạng thái không đồng nghĩa xóa bản ghi

Người dùng rời tổ chức có thể cần giữ **account disabled** để bảo toàn lịch sử audit, ownership dữ liệu hoặc nghĩa vụ lưu trữ. Mục tiêu là **không còn đường truy cập hợp lệ cho chủ thể không còn được phép**, không nhất thiết xóa ngay tất cả dữ liệu cá nhân/tài khoản. Quyết định xóa vĩnh viễn phải theo retention, legal hold, chính sách privacy và dependency của ứng dụng.

## 5. Điều kiện phát hiện account mồ côi

### 5.1. Các tín hiệu từ inventory/reconciliation

1. Target account **active** nhưng không map được tới subject/sponsor/owner hợp lệ.
2. Subject HR hoặc nhà thầu đã **Terminated/Expired**, nhưng target account hoặc local credential vẫn active.
3. Workload/service principal có quyền mà **không có owner**, catalog entry hoặc tài nguyên phụ thuộc hợp lệ.
4. Guest account vượt ngày hết hạn hoặc sponsor không còn thuộc tổ chức.
5. Account được tạo thủ công ngoài provisioning flow, không có approval/evidence.
6. Account có credential/token nhưng không thuộc catalog, đang giữ privilege hoặc app access.
7. SaaS account vẫn active sau khi IdP/SCIM đã deprovision, kể cả nếu SSO login không còn thành công.
8. Account trùng định danh hoặc group membership bất thường sau migration/rehire.
9. Access review nhiều kỳ không thể xác nhận owner/necessity của account.
10. Token, SSH key hoặc PAT không gắn owner còn tồn tại sau khi account chính đã disable.

### 5.2. Tín hiệu chưa đủ để kết luận

**Không có đăng nhập gần đây** chưa đủ kết luận account mồ côi. Account khẩn cấp, báo cáo cuối quý hoặc workload theo lịch dài có thể ít sử dụng. Tương tự, **account vẫn phát sinh API activity** không chứng minh owner hợp lệ; hoạt động có thể đến từ credential cũ hoặc bên không có thẩm quyền.

### 5.3. Bộ dữ liệu phát hiện mẫu

| Trường | Mục đích |
|---|---|
| `account_ref` và `target_system` | Tham chiếu đối tượng chính xác ở đích |
| `account_type` | Human, guest, service, admin, shared/legacy |
| `subject_id` / `externalId` | Mapping tới nguồn danh tính |
| `owner_ref` / `sponsor_ref` | Chủ sở hữu hoặc người bảo trợ hợp lệ |
| `lifecycle_state` | Active, Pending, Suspended, Terminated, Expired |
| `created_at`, `last_activity_at` | Timeline và tín hiệu sử dụng, không thay cho owner |
| `active`, `local_login_enabled` | Các đường xác thực còn có thể sử dụng |
| `roles` / `privileged_access` | Blast radius của account |
| `api_key_refs` / `token_refs` | Credential ngoài SSO còn tồn tại |
| `source_version` / `last_reconcile_at` | Tránh áp event cũ hoặc dùng snapshot lỗi thời |
| `review_status`, `evidence_ref` | Theo dõi xác minh/ngoại lệ và audit |

Chỉ lưu **ID và metadata cần thiết**, không đưa password, access token, refresh token, private key hoặc thông tin nhân sự nhạy cảm vào bảng kiểm kê và ticket.

## 6. SOP-OA01 — Triage: nhận diện, phân loại và kiểm tra nguồn

**Trigger:** cảnh báo orphan scan, access review, sự kiện Leaver, drift từ SCIM, security finding hoặc audit phát hiện account không có owner. **Owner:** IAM Operations, phối hợp HR/sponsor, application owner và Security theo rủi ro.

**Các bước:**

1. **Tạo case:** gắn `case_id`, `account_ref`, `target_system`, thời điểm, loại phát hiện, nguồn báo và owner tạm thời.
2. **Xác nhận account tồn tại:** đọc trạng thái trực tiếp tại target, không dựa duy nhất bản xuất dữ liệu cũ.
3. **Phân loại account:** human, guest, contractor, local, shared, service, cloud principal, emergency hoặc không rõ.
4. **Xác định subject/owner bằng ID bền vững:** đối chiếu HRIS, guest/sponsor registry, catalog workload, PAM register và provisioning history tương ứng với từng loại.
5. **Kiểm tra trạng thái JML:** Active, Pending, Mover, Suspended, Terminated, ngày hiệu lực và sự kiện mới nhất.
6. **Liệt kê đường truy cập:** SSO, password local, VPN, API key, PAT, SSH, service principal, session và token; đồng thời xác định roles/grants.
7. **Đánh giá rủi ro:** có đặc quyền, quyền ghi/xóa dữ liệu, truy cập PII, SoD, hoạt động đáng ngờ hay nhiều tài nguyên không?
8. **Gắn trạng thái tạm:** `PENDING_OWNER_VERIFICATION` nếu còn nghi ngờ; `CONFIRMED_ORPHAN` nếu đủ bằng chứng không có chủ thể/owner hợp lệ; `VALID_ACCOUNT` nếu tìm thấy owner/approval.
9. **Chuyển đúng người xác nhận:** HR/manager cho nhân viên, sponsor cho khách, app owner cho local account, platform/DevOps cho workload, PAM/SOC cho admin/break-glass.
10. **Ghi outcome:** có thể sửa mapping, giữ có owner, cách ly hoặc thu hồi; giữ evidence và thời hạn xử lý.

### 6.1. Bảng hỏi để tránh false positive

| Câu hỏi | Nếu câu trả lời là “Có” |
|---|---|
| Account liên quan tới người còn Active ở HR/sponsor? | Kiểm tra mapping lỗi và hướng relink |
| Đây là service principal có dependency production? | Tìm owner kỹ thuật/nghiệp vụ trước khi disable |
| Đây là guest/B2B có sponsor và hợp đồng còn hiệu lực? | Xem lại expiry/access review, không tự xóa |
| Đây là break-glass được phê duyệt? | Chuyển PAM/Security, kiểm tra chính sách khẩn cấp |
| Có migration/rehire/rename gần đây? | Đối chiếu ID, tránh merge nhầm |
| Đích giữ account disabled vì audit/retention? | Kiểm tra local grants/tokens nhưng không vội xóa |
| Có dấu hiệu compromise trên account chưa rõ owner? | Chuyển SOC, ưu tiên containment |

## 7. SOP-OA02 — Đánh giá rủi ro và containment

### 7.1. Vì sao không xóa ngay?

Một account thực sự mồ côi có thể giữ tài liệu, sở hữu job hoặc khóa tích hợp. Xóa ngay có thể làm hỏng audit trail hoặc dịch vụ. Tuy nhiên trì hoãn vô thời hạn với account active có đặc quyền cũng nguy hiểm. Phương án phù hợp là **ngăn khả năng truy cập không hợp lệ theo mức rủi ro**, bảo toàn bằng chứng rồi tiếp tục điều tra ownership/dependency.

### 7.2. Phân loại mức ưu tiên minh họa

| Mức | Ví dụ | Hướng xử lý |
|---|---|---|
| **P0** | Account không rõ owner có admin cao, dấu hiệu đang bị lạm dụng; Leaver còn truy cập dữ liệu trọng yếu | Kích hoạt SOC/IAM/PAM; chặn đường truy cập theo quy trình ứng phó |
| **P1** | Account của nhà thầu hết hạn còn local login/PAT; service principal quyền rộng không có owner | Ưu tiên hạn chế quyền/credential, xác minh dependency và owner |
| **P2** | SaaS account active không map được HR nhưng không có privilege cao và chưa thấy lạm dụng | Xác minh source, application owner, containment phù hợp |
| **P3** | Account đã disabled, không còn credential có thể dùng, chỉ cần quyết định retention | Kiểm tra bằng chứng và lịch lưu/xóa |

Đây không phải SLA chuẩn. Cần đánh giá **blast radius**, độ nhạy dữ liệu, trạng thái credential, khả năng truy cập từ Internet, tính bất biến audit và mức tác động nếu disable.

### 7.3. Các biện pháp containment theo khả năng hệ thống

- **Block sign-in/disable account** tại hệ thống có thẩm quyền khi có quyết định hợp lệ.
- **Revoke session/refresh token/API key/PAT** hoặc chặn tại resource server/app nếu account có đường truy cập ngoài SSO.
- **Gỡ đặc quyền tạm thời hoặc deny hành động nhạy cảm** theo chính sách, tránh mở rộng quyền của người khác.
- **Quarantine có thời hạn:** account không được sử dụng nhưng vẫn giữ metadata, audit, resource ownership phục vụ điều tra và retention.
- **Cô lập workload hoặc hạn chế trust** khi có khả năng lạm dụng, phối hợp owner để hạn chế gián đoạn dịch vụ.
- **Security monitoring:** phát hiện tạo token mới, thay đổi group, sign-in bất thường, quyền bị tái cấp hoặc truy cập dữ liệu sau khi chặn.

**Không dùng một thao tác vô hiệu hóa ở IdP để suy rằng mọi session hoặc local account của SaaS đã mất hiệu lực.** Đọc lại từng đường có khả năng truy cập.

## 8. Mô hình trạng thái xử lý account mồ côi

~~~mermaid
stateDiagram-v2
    [*] --> DETECTED
    DETECTED --> INVESTIGATING: Kiểm tra identity / owner
    INVESTIGATING --> VALID_ACCOUNT: Owner + approval hợp lệ
    INVESTIGATING --> SUSPECTED_ORPHAN: Mapping hoặc owner chưa rõ
    INVESTIGATING --> CONFIRMED_ORPHAN: Không còn owner / source hợp lệ
    SUSPECTED_ORPHAN --> VALID_ACCOUNT: Sửa mapping / xác nhận sponsor
    SUSPECTED_ORPHAN --> CONFIRMED_ORPHAN: Điều tra xác nhận
    CONFIRMED_ORPHAN --> QUARANTINED: Containment theo rủi ro
    CONFIRMED_ORPHAN --> RETAIN_WITH_OWNER: Chuyển owner hợp lệ
    QUARANTINED --> RETAIN_WITH_OWNER: Cần phục hồi theo approval
    QUARANTINED --> DISABLED_VERIFIED: Thu hồi đường truy cập
    RETAIN_WITH_OWNER --> VERIFIED: Quyền và owner đúng policy
    VALID_ACCOUNT --> VERIFIED: Mapping / access đúng
    DISABLED_VERIFIED --> RETAINED_FOR_AUDIT: Cần giữ theo retention
    DISABLED_VERIFIED --> DELETION_APPROVED: Được phép xóa sau retention
    RETAINED_FOR_AUDIT --> [*]
    DELETION_APPROVED --> [*]
    VERIFIED --> [*]
~~~

Trạng thái **DELETION_APPROVED** mới là quyết định đủ điều kiện xóa theo quy trình; xóa thực tế còn phụ thuộc legal hold, giữ dữ liệu, ownership và kiểm tra hệ thống đích. Không dùng “suspected orphan” như căn cứ duy nhất cho một lệnh DELETE tự động.

### 8.1. Quyền đi kèm trạng thái

| Trạng thái | Còn có thể truy cập? | Điều kiện đóng |
|---|---|---|
| `DETECTED` | Chưa rõ | Không đóng; cần xác minh |
| `SUSPECTED_ORPHAN` | Có thể | Có owner/deadline và kiểm soát rủi ro |
| `VALID_ACCOUNT` | Theo policy | Mapping và owner đã chứng minh |
| `CONFIRMED_ORPHAN` | Có thể | Cần quyết định retain/contain/revoke |
| `QUARANTINED` | Bị hạn chế theo khả năng đích | Chứng minh đường truy cập rủi ro bị chặn |
| `RETAIN_WITH_OWNER` | Theo approval mới | Owner, lifecycle, expiry và least privilege đúng |
| `DISABLED_VERIFIED` | Không còn đường truy cập bị cấm | Readback và xác minh quyền thực tế |
| `RETAINED_FOR_AUDIT` | Không | Retention, ownership dữ liệu và audit còn nguyên |

## 9. SOP-OA03 — Xác minh chủ thể và sửa liên kết account

**Khi nào dùng:** phát hiện account không map nhưng có thể là account hợp lệ vì rename, migration, hệ thống tích hợp chưa đồng bộ hoặc dữ liệu owner chưa đủ.

**Trình tự:**

1. Thu thập **account ID của đích**, IdP object ID, SCIM `externalId` nếu có, nguồn tạo account và sự kiện provisioning/SSO liên quan.
2. Đối chiếu HR/person ID, contractor ID, guest ID, workload app ID hoặc privileged registry theo account type.
3. Kiểm tra lịch sử đổi email, tên, tenant, department, rehire hoặc migrations; không gộp hai account chỉ vì cùng email.
4. Kiểm tra **approval và ownership còn hiệu lực**: ai cần account, tài nguyên nào, mục đích và thời hạn.
5. Nếu mapping lỗi, sửa **tại nguồn sở hữu quan hệ** (IAM identity mapping, source HR/guest/workload registry hoặc connector config) theo change/approval.
6. Tránh thao tác “link” vào một subject mới chưa xác minh khi account cũ chứa dữ liệu hoặc token riêng; khi nghi có reuse account, chuyển owner/Security điều tra.
7. Chạy lại provisioning/reconciliation **idempotent**, kiểm tra account target và quyền hiệu lực.
8. Ghi bằng chứng relink, owner mới, chính sách quyền, version sự kiện và xác nhận từ ứng dụng.

### 9.1. Ví dụ: đổi email làm account trông như orphan

Một nhân viên đổi họ, email mới đã đồng bộ vào IdP nhưng SaaS inventory còn email cũ. Job quét so sánh theo email đánh dấu SaaS account là orphan.

**Cách xử lý đúng:** đối chiếu subject ID → IdP object ID → SCIM `externalId` → SaaS user ID. Nếu là cùng một người, sửa mapping và thuộc tính email theo nguồn có thẩm quyền, xác minh role và session. Không disable hoặc tạo account thứ hai chỉ vì hai email khác nhau.

### 9.2. Ví dụ: email tái sử dụng

Một email từng thuộc nhân viên A đã nghỉ, sau đó được cấp lại cho nhân viên B. SaaS còn bản ghi cũ của A. Nếu tự link theo email, B có thể nhận dữ liệu/quyền của A.

**Cách xử lý đúng:** dùng ID bất biến, thời điểm tạo, lịch sử lifecycle và ownership dữ liệu. Account A phải được xử lý theo Leaver/retention; B được provision hoặc link tới account riêng được phê duyệt. Không tự merge nội dung hoặc grants.

## 10. SOP-OA04 — Vô hiệu hóa và thu hồi account không còn hợp lệ

**Trigger:** owner/source xác nhận account không cần giữ active, người dùng đã nghỉ, sponsor hết hạn hoặc Security quyết định phải chặn.

**Các bước:**

1. Xác minh **quyết định có thẩm quyền**, subject/target ID, version JML và time effective.
2. Lập inventory account ở IdP, directory, SSO-relying apps, SaaS SCIM, VPN, PAM, cloud, local login và API/SSH keys liên quan.
3. Chặn đăng nhập ở nguồn phù hợp và tại đích có local authentication; với Leaver khẩn cấp, ưu tiên những đường còn điều khiển được dù connector đang lỗi.
4. Thu hồi session/refresh token/PAT/API key/SSH key hoặc quyền đặc biệt **khi liên quan và hệ thống hỗ trợ**; không giả định disable IdP tự thu hồi mọi token.
5. Gỡ entitlement không còn hợp lệ: RBAC role, ABAC policy bindings, group/direct grants, delegated access, PAM/JIT elevation.
6. Giữ dữ liệu/ownership phục vụ audit, pháp lý và chuyển giao theo chính sách; chuyển ownership tài nguyên cho chủ thể được duyệt thay vì đăng nhập bằng account mồ côi.
7. Đối chiếu trạng thái IdP–SCIM–app–cloud và kiểm tra không còn đường truy cập không được phép, kể cả local account.
8. Nếu một đích bị lỗi, đánh dấu `EXCEPTION_OPEN`, gán owner và deadline, áp containment thay thế; không ghi “fully deprovisioned”.
9. Sau retention và legal/privacy review, chỉ thực hiện xóa vĩnh viễn nếu có quyết định riêng, kiểm thử tác động và xác minh đúng resource.

### 10.1. Disable khác Delete

| Tác vụ | Tác động | Khi nào cân nhắc |
|---|---|---|
| **Disable/block sign-in** | Chặn đăng nhập mới theo semantics của đích | Bước giảm rủi ro đầu tiên |
| **Revoke session/token/key** | Chặn đường truy cập đã phát hành hoặc độc lập | Khi cần thu hồi hiệu lực ngoài lần login mới |
| **Remove grants/role** | Giảm quyền ở nguồn/ứng dụng | Mover, Leaver, excessive access |
| **Transfer ownership** | Đổi người phụ trách dữ liệu/workload | Bàn giao hệ thống, file, job, ứng dụng |
| **Retain disabled account** | Giữ lịch sử/audit mà không cho truy cập | Có yêu cầu retention, pháp lý hoặc dependency |
| **Delete account/data** | Có thể phá vỡ tham chiếu, ownership hoặc audit | Chỉ sau phê duyệt và kiểm tra quy định |

## 11. Xử lý orphan account trong vòng đời Joiner–Mover–Leaver

### 11.1. Joiner: account bị tạo ngoài chuẩn hoặc tạo trùng

Một Joiner có thể được người quản trị tạo account local để làm việc gấp, sau đó SCIM tạo user khác khi JML hoàn tất. Account local ban đầu không được quản lý và trở thành suspected orphan.

**Runbook Joiner:**

1. Xác nhận identity proofing, HR/sponsor, ngày hiệu lực và yêu cầu cấp quyền hợp lệ.
2. Đối chiếu IdP, SCIM và app user IDs; tìm account local/JIT/SSO duplicate.
3. Xác định account nào chứa dữ liệu/ownership hợp lệ và cơ chế link/migration được app hỗ trợ.
4. Đặt desired state theo RBAC/ABAC, không giữ quyền admin “để tránh lỗi provisioning”.
5. Cô lập account dư, chuyển ownership dữ liệu theo phê duyệt, revoke credential và xác minh account chính hoạt động.
6. Sửa luồng onboarding để không tạo duplicate khi retry hoặc làm thủ công.

### 11.2. Mover: account và quyền cũ không tự biến mất

Người đổi vai trò có thể giữ account riêng ở ứng dụng phòng ban cũ, quyền trực tiếp ngoài IdP, role cũ trong nhóm lồng nhau hoặc PAT dùng cho dự án đã kết thúc.

**Runbook Mover:**

1. Lấy role/thuộc tính **trước và sau**, version sự kiện Mover và ngày hiệu lực.
2. Tính chênh lệch **KEEP / GRANT / REVOKE / REVIEW**, có SoD và approval.
3. Tìm account local hoặc bản ghi ứng dụng không map với vai trò mới; xác minh owner và dependency.
4. Thu hồi quyền và account không còn nhu cầu, kể cả token/session/personal credentials khi policy yêu cầu.
5. Đảm bảo role mới được cấp đúng và account cần giữ có owner; không để trùng account ngoài kiểm soát.
6. Kiểm chứng quyền mới được phép và quyền cũ bị từ chối tại target.

### 11.3. Leaver: ưu tiên chặn truy cập tồn dư

Với người nghỉ việc hoặc nhà thầu hết hạn, account tại SaaS/local/cloud có thể không nhận được SCIM deactivation. Đây là rủi ro nghiêm trọng ngay cả khi IdP đã disabled.

**Runbook Leaver:**

1. Xác nhận thông tin Leaver từ nguồn có thẩm quyền, subject ID và ngày/giờ hiệu lực.
2. Disable IdP/SSO/VPN/PAM theo quy trình, đồng thời thu hồi account local/ứng dụng đích.
3. Revoke session, PAT, API token, SSH key, cloud role và delegated access khi còn hiệu lực.
4. Đối soát danh sách tất cả target, không chỉ target có SCIM. Account không map phải được kiểm tra theo identity history.
5. Chuyển ownership dữ liệu, repo, automation và workload cho owner đã duyệt; không giữ Leaver active để bàn giao.
6. Nếu connector đứt, thực hiện đường disable thủ công có kiểm toán; chặn job cũ tái kích hoạt tài khoản sau khi Terminated.
7. Đóng khi quyền hiệu lực của Leaver đã được xác minh theo chính sách và ngoại lệ được quản lý rõ ràng.

### 11.4. Suspended và tái tuyển dụng

Một tài khoản bị **Suspended** có thể cần giữ disabled tạm thời; không tự xóa trước khi chủ quản xác định kết quả. Một người **rehired** không mặc nhiên nhận lại account/role/token cũ. Xác minh quan hệ lao động mới, nguồn chủ quản và approval rồi provision trạng thái hiện hành; tránh tài khoản bị liên kết nhầm do email tái sử dụng.

## 12. SOP-OA05 — Service account và workload mồ côi

Service account, application registration, managed identity, cloud service principal và CI/CD credential không có “người dùng HR” tương ứng. Orphan ở nhóm này thường nghĩa là **không có technical/business owner hợp lệ, workload đã bị hủy hoặc credential/quyền còn tồn tại ngoài kiểm soát**.

### 12.1. Những câu hỏi phải trả lời trước khi disable

- Workload/service nào sử dụng account, ở môi trường nào, với SLA và owner nào?
- Account có chạy job theo lịch, pipeline, webhook, agent, backup, monitoring hoặc integration quan trọng?
- Có bí mật, certificate, managed identity, trust relationship hoặc token nào được dùng bởi nhiều instance không?
- Account có quyền cloud IAM, repository, database, queue, vault hoặc network quá mức?
- Có thành viên cũ của tổ chức giữ quyền quản trị service principal hoặc secret không?
- Nếu disable, sẽ gián đoạn hệ thống nào? Có cách chuyển owner/secret an toàn không?

### 12.2. Quy trình tìm owner và xử lý

1. Đọc asset/workload catalog, CI/CD config, cloud resource labels/tags, audit trail, owner của deployment và các nguồn hỗ trợ điều tra.
2. Không mặc định **last login** là tiêu chí quyết định; job có thể chỉ chạy theo tháng/quý.
3. Gửi yêu cầu xác nhận tới technical owner, business owner và application owner; nếu người phụ trách đã nghỉ, tìm người kế nhiệm thông qua hệ thống/quy trình tổ chức.
4. Nếu tìm thấy workload vẫn cần thiết, **gán owner mới**, ghi mục đích, quyền tối thiểu, ngày rà soát và phương pháp rotation/secret storage.
5. Nếu workload đã ngừng, xác minh dependency không còn; thu hồi trust/grants, revoke key/secret và disable theo change/approval.
6. Với account có đặc quyền và chưa rõ owner, áp containment theo mức rủi ro với SOC/PAM, tránh để credential không quản lý hoạt động vô hạn.
7. Giám sát batch job, lỗi xác thực và đường truy cập sau thay đổi; chỉ đóng khi account không còn quyền trái policy hoặc đã có owner hợp lệ.

### 12.3. Ví dụ: service principal do nhân viên đã nghỉ tạo

Một service principal có quyền ghi lên bucket production, được tạo bởi nhân viên A đã nghỉ. Workload vẫn đồng bộ dữ liệu hàng ngày, nhưng secret chưa có technical owner.

**Hướng xử lý:** xác định app/deployment đang sử dụng, tìm technical/business owner kế nhiệm, rà scope, chuyển owner qua quản trị đúng quy trình, rotate/đưa secret vào vault nếu cần. Thu hồi mọi đường truy cập cá nhân của A. **Không** xóa service principal đang chạy chỉ vì owner cũ là Leaver; cũng không để quyền hiện tại không có người chịu trách nhiệm.

### 12.4. Managed identity không tự hết rủi ro

Managed identity hoặc workload federation giảm phụ thuộc secret tĩnh nhưng vẫn cần owner, trust, scope RBAC và lifecycle. Một identity không có secret riêng **vẫn** có thể là orphan nếu workload đã bị xóa mà policy grant còn tồn tại.

## 13. Guest, B2B, đối tác và tài khoản dùng chung

### 13.1. Guest account

Guest/B2B có thể là người bên ngoài không nằm trong HRIS nhưng được mời qua tenant; cần sponsor, mục đích, expiry và phạm vi tài nguyên. Account guest không sponsor hoặc hết hợp đồng cần review:

1. Xác định source/tenant và guest ID, người mời/sponsor, hợp đồng, dữ liệu truy cập.
2. Kiểm tra ngày hết hạn, điều kiện ABAC, role và login history.
3. Nếu sponsor còn hợp lệ, gia hạn qua approval theo policy; không tự giữ vô hạn.
4. Nếu hết nhu cầu, revoke invite/session/permissions và disable/delete theo chính sách của IdP/ứng dụng.
5. Đối soát các ứng dụng có local guest account và API token độc lập.

### 13.2. Tài khoản chia sẻ hoặc tài khoản chung

Shared account làm khó quy trách nhiệm. Nếu buộc phải giữ cho hệ thống legacy, cần owner rõ, lý do kinh doanh, vault/PAM, kiểm soát sử dụng, MFA nếu hỗ trợ, lịch review và kế hoạch thay thế bằng danh tính riêng khi khả thi. Một shared account không có owner/giám sát là ứng viên orphan; không hợp thức hóa nó chỉ vì “nhiều người vẫn sử dụng”.

### 13.3. Break-glass

Tài khoản khẩn cấp có thể cố ý không gắn nhân sự cụ thể, nhưng phải có **Security/PAM owner**, cơ chế giữ bí mật, kiểm soát kích hoạt, log, kiểm thử định kỳ và hậu kiểm. Không xóa ngay tài khoản khẩn cấp hợp lệ vì hệ thống orphan scanner không tìm thấy HR row. Nếu break-glass không có owner/trust/giám sát hợp lệ, escalated review là bắt buộc.

## 14. SCIM, SSO và thất bại đồng bộ làm phát sinh orphan

### 14.1. SCIM không đồng nghĩa bao phủ mọi account

SCIM có thể đồng bộ user/group và trạng thái `active` ở target hỗ trợ. Nhưng ứng dụng có thể còn local accounts, vai trò gán trực tiếp, sessions, API keys hoặc một số object không được SCIM quản lý. Vì vậy:

- IdP disabled không chứng minh app local account đã disabled.
- SCIM `active=false` không mặc nhiên revoke mọi API token hoặc session hiện hành.
- Account app “không có SCIM externalId” không nhất thiết là xấu: cần kiểm tra JIT provisioning, migration và guest identity.
- SCIM sync successful không thay thế readback actual và kiểm tra effective access.

### 14.2. Ma trận điều tra lỗi connector

| Dấu hiệu | Khả năng nguyên nhân | Bước xử lý |
|---|---|---|
| `401/403` | Token connector hết hạn hoặc thiếu scope | Owner sửa credential/quyền tối thiểu, retry có kiểm soát |
| `404` | ID đích sai, resource đã thay hoặc bị xóa | Đối chiếu ID bất biến/actual state |
| `409` | Conflict/trùng unique field | Điều tra identity mapping, không merge theo email |
| `412` | Version/ETag không còn khớp nếu được hỗ trợ | Đọc lại version và diff |
| `429` | Rate limit | Tôn trọng `Retry-After` và backoff có jitter |
| `5xx / timeout` | Lỗi tạm hoặc không rõ request đã áp dụng chưa | Mark `UNKNOWN`, đọc lại trước retry |
| `2xx nhưng still active` | Async processing, cache, mapping hoặc local login | Chờ/đọc lại và xác minh app state |
| Account bị cấp lại sau disable | Event cũ, policy desired sai, job retry | Chặn stale event bằng source version và reconcile |

Các mã lỗi trên là gợi ý HTTP thường gặp, **không phải bảo đảm mỗi vendor có hành vi giống nhau**. Phải đọc response và capability của ứng dụng đích.

### 14.3. Session/token của orphan account

Đăng nhập qua **OIDC/SAML SSO** có thể tạo phiên riêng tại ứng dụng; khi IdP không còn cấp token mới, phiên cũ đôi khi vẫn hoạt động. Access token dạng self-contained có thể được resource server chấp nhận tới hạn, trừ khi đích có cơ chế revoke/deny. Với suspected/confirmed orphan có rủi ro cao, cần kiểm tra và thu hồi đúng hệ thống, đồng thời đánh giá PAT/API key và quyền cục bộ.

## 15. SOP-OA06 — Phòng tránh tái kích hoạt và xử lý race condition

Một lỗi nguy hiểm là sau khi IAM disable account mồ côi, connector hoặc job cũ lại chạy và **tạo/cấp lại account**.

### 15.1. Nguyên nhân điển hình

- Event Joiner/Mover tới trễ sau sự kiện Leaver.
- Retry một lệnh create/`active=true` sau timeout mà không kiểm tra actual state.
- Desired state trong provisioning còn cho phép quyền cũ.
- Admin gỡ thủ công tại ứng dụng trong khi IdP/SCIM vẫn còn group/role.
- Guest/sponsor expiry chưa đồng bộ hoặc workload catalog chưa đánh dấu decommissioned.
- Tài khoản bị clone từ template mặc định có quyền rộng.

### 15.2. Nguyên tắc bảo vệ

1. Sử dụng **event ID, immutable subject ID, source version và target ID** để chống nhầm/trùng.
2. Trước thao tác **grant/enable**, đọc lifecycle mới nhất và approval.
3. Với Leaver, ngăn event cũ re-enable; kiểm tra version guard và ưu tiên các lệnh chặn truy cập theo chính sách.
4. Áp **idempotency** và readback khi API timeout; không tạo account mới nếu chưa xác minh account cũ.
5. Sửa desired state ở **source of truth** rồi reconcile; nếu chỉ disable thủ công, ghi exception để connector không cấp lại ngoài ý muốn.
6. Giám sát reactivation, grants mới, local account creation và orphan recurrence sau remediation.

### 15.3. Pseudocode phát hiện và xử lý an toàn

~~~text
handle_suspected_orphan(account_ref, target):
    actual = read_target_account_and_access(account_ref, target)
    evidence = collect_account_mapping_and_provisioning_events(actual)
    category = classify_account_type(actual, evidence)

    owner = resolve_authoritative_owner(category, actual, evidence)
    lifecycle = resolve_latest_lifecycle(category, owner, actual)

    if mapping_is_ambiguous(actual, owner, lifecycle):
        open_review_case("UNVERIFIED_MAPPING")
        apply_risk_based_containment_if_authorized()
        return

    if category == "BREAK_GLASS":
        route_to_pam_security_review()
        return

    if category == "SERVICE" and workload_dependency_is_unknown():
        discover_workload_and_owners()
        apply_risk_controls_without_blind_delete()
        return

    desired = evaluate_current_policy_and_approvals(lifecycle, owner, target)
    risk = classify_risk(actual, desired, account_type=category)

    if desired.requires_account:
        update_owner_and_identity_mapping_if_approved()
        reconcile_entitlements_to_desired_state()
        verify_target_access_and_owner()
        return

    confirm_revocation_authority(lifecycle, risk)
    disable_account_at_authoritative_source()
    revoke_related_sessions_and_credentials_when_required()
    remove_invalid_direct_and_inherited_grants()
    verify_no_unauthorized_effective_access()
    preserve_resources_and_audit_under_retention_policy()
    record_evidence_and_open_exceptions_for_unverified_targets()
~~~

Đoạn này là **pseudocode** phục vụ học tập, không phải lệnh admin trực tiếp. Production cần concurrency control theo `subject_id + target`, ACL thao tác, approval, bounded retry, dead-letter queue, audit và chính sách riêng cho user, service, guest và break-glass.

## 16. Phát hiện account mồ côi bị lợi dụng

Account không rõ owner nhưng vẫn có credential hoạt động có thể bị sử dụng làm điểm bám. Nếu thấy **login bất thường, tạo PAT/key mới, tăng quyền, xuất dữ liệu, thay đổi MFA hoặc account login từ nguồn lạ**, cần coi đây là tình huống Security triage, không chỉ ticket dọn vệ sinh account.

### 16.1. Dấu hiệu điều tra

| Nhóm | Bằng chứng nên xem |
|---|---|
| Authentication | Sign-in success/failure, IP/client/device, MFA, phương thức local/SSO |
| Entitlement | Thay đổi group, role, policy, delegated admin, PAM elevation |
| Credential | API key/PAT/SSH key tạo mới, secret read, certificate issuance |
| Data access | Lượt truy cập dữ liệu nhạy cảm, bulk export, download, repository clone |
| Persistence | Tạo automation, local account, OAuth app consent, service principal |
| Correlation | Thời điểm HR Leaver, IdP disable, SCIM failure, sự kiện lạ |

### 16.2. Quy trình khi có dấu hiệu compromise

1. Chuyển SOC/Incident Commander, lưu log theo quy trình bảo vệ chứng cứ.
2. Thực hiện containment trên IdP, app, VPN, PAM, cloud và token/key nếu được chỉ đạo.
3. Rà credentials hoặc grants phát sinh từ account; disable account không tự xóa những quyền đã cấp cho principal khác.
4. Xác định phạm vi dữ liệu và người dùng bị ảnh hưởng; phối hợp Legal/Privacy khi cần.
5. Đối soát target theo desired state, loại persistence trái phép, chuyển ownership dữ liệu hợp pháp.
6. Chỉ đóng khi các quyền và đường truy cập không hợp lệ được kiểm chứng đã xử lý hoặc ngoại lệ có owner/giảm thiểu rõ ràng.

Không coi **thiếu sign-in gần đây** là bằng chứng không có lạm dụng; hoạt động API, token hoặc các nguồn log chưa đầy đủ có thể làm sai kết luận.

## 17. Hậu kiểm, retention và quyết định xóa

### 17.1. Account không còn quyền nhưng dữ liệu vẫn cần giữ

Một account disabled có thể vẫn là owner của file, báo cáo, workflow, repo, khóa mã hóa hoặc audit trail. Cần tách **quyền sử dụng account** khỏi **quyền sở hữu dữ liệu**:

- Chuyển dữ liệu/tài nguyên cho người hoặc service owner có thẩm quyền qua quy trình bàn giao.
- Đảm bảo các đường delegation/share tồn dư không còn sử dụng được ngoài policy.
- Giữ audit và metadata cần thiết theo retention/hold.
- Chỉ xóa object/account nếu quy định cho phép và không gây mất tính toàn vẹn tham chiếu.

### 17.2. Không xóa hàng loạt từ một truy vấn

Danh sách suspected orphan có thể bao gồm mapping lỗi, guests hợp lệ, break-glass hoặc workloads theo lịch dài. Một thao tác **bulk delete** từ danh sách này có thể làm mất truy cập production, dữ liệu hoặc khả năng khôi phục sự cố.

Với chiến dịch dọn account số lượng lớn:

1. Chọn tiêu chí và nguồn thẩm quyền rõ ràng; kiểm chứng false positives bằng mẫu có ý nghĩa.
2. Phân nhóm tài khoản có rủi ro cao, account active, disabled và workload dependencies.
3. Gửi owner review đúng kênh và deadline, có escalation khi không phản hồi.
4. Ưu tiên disable/quarantine có khả năng phục hồi theo retention thay vì xóa ngay.
5. Canaries trước khi triển khai phạm vi rộng, giám sát business/system errors.
6. Duy trì rollback có thẩm quyền cho trường hợp nhầm mà không phục hồi quyền trái policy.
7. Xác nhận từng target và quyền hiệu lực; không đóng chỉ vì API trả success.

## 18. Audit record, KPI và giám sát

### 18.1. Bằng chứng tối thiểu

~~~yaml
case_id: IAM-ORPHAN-EXAMPLE-071
detected_at: "2026-11-23T10:15:00+07:00"
target_system: legacy-reporting-app
account_ref: target-user-841
account_type: HUMAN_LOCAL
detection_reason: NO_AUTHORITATIVE_OWNER_MAPPING
inventory_snapshot_ref: inventory-20261123
source_checks:
  hris_ref: lifecycle-check-071
  idp_ref: idp-lookup-071
  scim_ref: scim-job-071
identity_verification:
  subject_id: person-1042
  lifecycle_state: TERMINATED
  lifecycle_version: 18
risk_classification: STALE_LEAVER_ACCESS
decision:
  action: DISABLE_AND_REVOKE
  approval_ref: iam-approval-071
remediation:
  operator_ref: iam-operator-09
  applied_at: "2026-11-23T10:35:00+07:00"
  account_status: DISABLED
  revoked_grant_refs:
    - reporting-editor
  revoked_credential_refs:
    - pat-id-88
verification:
  sign_in_new: DENIED
  api_token_access: DENIED
  effective_privileges: REVOKED
  evidence_ref: access-check-071
data_retention:
  transferred_owner_ref: reporting-data-owner
  deletion_status: NOT_REQUESTED
exceptions: []
case_status: CLOSED
~~~

Đây là dữ liệu **giả lập**. Audit thực tế cần liên kết detection → mapping/owner xác minh → quyết định risk/approval → containment/thu hồi → readback và xác minh quyền hiệu lực → retention/ngoại lệ. Không lưu password, token, private key, recovery code hoặc dữ liệu cá nhân không cần thiết trong hồ sơ.

### 18.2. Metrics gợi ý

| Metric | Cách hiểu |
|---|---|
| **Suspected orphan count** | Số account chưa map/owner; cần theo dõi tỉ lệ false positive |
| **Confirmed orphan count** | Số account được xác minh không có chủ thể/owner hợp lệ |
| **Active orphan exposure** | Số confirmed orphan vẫn có đường đăng nhập hoặc credential hoạt động |
| **Privileged orphan count** | Account không có owner hợp lệ nhưng còn quyền đặc quyền |
| **Time to ownership resolution** | Thời gian từ phát hiện đến xác nhận owner/relink/disable decision |
| **Time to verified revocation** | Thời gian đến khi quyền và credential không hợp lệ được kiểm chứng đã thu hồi |
| **Orphan recurrence rate** | Account xuất hiện lại sau xử lý do provisioning/policy hoặc mapping lỗi |
| **Leaver residual access** | Tài khoản Leaver còn khả năng truy cập tại các target |
| **Unowned service identity count** | Workloads/service principals chưa có owner và lịch review |
| **Expired guest account count** | Guest vượt hạn vẫn còn quyền |
| **Exceptions overdue** | Ngoại lệ account/quyền chưa xác minh quá deadline |
| **Review-to-action completion** | Tỉ lệ quyết định của owner đã được thực hiện và kiểm chứng |

Đừng tối ưu chỉ số bằng cách **xóa account hàng loạt**: mục tiêu là đúng owner, đúng lifecycle, quyền hiệu lực tối thiểu và kiểm soát rủi ro. Nên báo cáo riêng số suspected, confirmed, disabled, verified, retained-for-audit và false positives.

### 18.3. Tiêu chí đóng ticket

| Câu hỏi | Bằng chứng cần có |
|---|---|
| Account và target đã xác định chắc chắn? | ID bền vững, mapping, source records |
| Đã phân loại human/guest/service/break-glass? | Owner/sponsor/registry tương ứng |
| Lifecycle/approval hiện hành chính xác? | HR/sponsor/owner, event version, ngày hiệu lực |
| Có quyền/credential tồn dư? | Role/grant, token/session, app-local access inventory |
| Đã thực hiện quyết định hợp lệ? | Approval, actor, change/ticket, API response |
| Đã xác minh trạng thái thực tế? | Readback ở đích và effective access phù hợp |
| Resource ownership và retention được xử lý? | Owner mới hoặc kế hoạch giữ dữ liệu được duyệt |
| Có lỗi connector, retry hoặc account bị re-enable? | Reconciliation, monitoring và exception |
| Ngoại lệ có owner, deadline và kiểm soát? | Evidence và escalation path |

## 19. Tình huống luyện tập có lời giải định hướng

### Tình huống A — SaaS account của Leaver vẫn Active

HR xác nhận nhân viên đã nghỉ, IdP disabled nhưng SaaS chưa nhận SCIM `active=false` vì connector trả 403. SaaS có local login và PAT còn hiệu lực.

**Hướng xử lý:** xác minh subject ID và sự kiện Leaver; ưu tiên disable local account, revoke PAT/session, gỡ quyền đích theo owner, sau đó sửa SCIM connector scope/credential và reconcile. Không đóng Leaver chỉ vì IdP đã chặn.

### Tình huống B — Account bị đánh nhầm orphan vì đổi email

Nhân viên vẫn Active, đã đổi email. SaaS giữ email cũ nhưng `externalId` trùng subject hợp lệ.

**Hướng xử lý:** so IDs bền vững, cập nhật mapping/attribute tại nguồn, kiểm tra rights. Ghi false positive và sửa orphan detector tránh dùng email làm khóa duy nhất. Không disable account hoặc tạo account mới.

### Tình huống C — Service principal không còn người quản lý

Ứng dụng sản xuất sử dụng service principal có quyền đọc dữ liệu, nhưng owner kỹ thuật trước đây đã nghỉ. Last activity xuất hiện đều đặn mỗi sáng.

**Hướng xử lý:** tìm workload/CMDB/CI/CD dependency, xác nhận owner kế nhiệm, chuyển trách nhiệm và rà least privilege/secret rotation. Không xóa service principal production theo tiêu chí “owner ở HR đã nghỉ”; giám sát cho tới khi ownership được chứng minh.

### Tình huống D — Guest account hết hạn nhưng có sponsor mới

Guest hợp đồng cũ đã hết hạn, nhưng business owner muốn tiếp tục hợp tác với cùng người ở dự án mới.

**Hướng xử lý:** không giữ quyền cũ mặc định. Xác nhận sponsor mới, mục đích, expiry và approval; thu hồi grants không còn hợp lệ, cấp phạm vi mới theo RBAC/ABAC và xác minh account chỉ truy cập đúng tài nguyên đã duyệt.

### Tình huống E — Tài khoản break-glass không có HR row

Orphan scanner phát hiện tài khoản admin không có person ID và gợi ý xóa.

**Hướng xử lý:** đối chiếu PAM/Security emergency account register, owner, kiểm soát khóa, monitoring và lịch kiểm thử. Nếu hợp lệ, phân loại `BREAK_GLASS` và loại khỏi rule dành cho human identities; vẫn kiểm tra định kỳ. Nếu thực sự không có owner/trust, chuyển Security review theo rủi ro.

### Tình huống F — Mover còn account ở ứng dụng phòng ban cũ

Nhân viên sang Finance, HR và IdP group đã cập nhật nhưng ứng dụng Support còn local account có quyền export dữ liệu.

**Hướng xử lý:** dựa theo Mover mới nhất, kiểm tra direct grants/PAT/session, thu hồi local access Support, giữ Finance access được duyệt, sửa ứng dụng/provisioning policy để lần sau thu hồi cả tài khoản local.

### Tình huống G — Account bị cấp lại sau khi disable

IAM disable một SaaS account mồ côi, vài phút sau job SCIM tạo lại vì source desired state chưa được sửa.

**Hướng xử lý:** xác định job/event, version, source mapping và policy; chặn regrant ngoài ý muốn, sửa source of truth, chạy reconciliation idempotent và giám sát. Không lặp vòng disable mà không sửa nguyên nhân.

### Tình huống H — Email nhân viên mới trùng với email Leaver cũ

Nhân viên B nhận email từng thuộc A. Một ứng dụng dựa email đề xuất link B tới account cũ của A, nơi vẫn chứa báo cáo và quyền owner.

**Hướng xử lý:** xác minh immutable IDs và lịch sử account, không merge. Xử lý dữ liệu/ownership của A theo retention/Leaver; tạo hoặc link account riêng cho B với role mới được duyệt; kiểm tra quyền không bị chuyển nhầm.

### Tình huống I — Dormant account của job cuối quý

Một integration chỉ chạy báo cáo mỗi ba tháng, không có login trong 80 ngày, nhưng còn owner và dependency hợp lệ.

**Hướng xử lý:** đây là **dormant** chứ chưa chắc orphan. Xác minh lịch, owner, quyền tối thiểu, secret expiry và thời điểm rà soát; quản lý như workload hợp lệ. Không disable chỉ vì không hoạt động trong cửa sổ ngắn hơn chu kỳ job.

## 20. Checklist vận hành nhanh và kết luận

**Checklist 10 bước cho IAM Operations:**

1. Xác định account/target bằng **ID bền vững**, không chỉ email.
2. Phân loại **human, contractor, guest, service, shared hay break-glass**.
3. Đối chiếu **nguồn thẩm quyền** và JML version hiện hành.
4. Xác minh owner/sponsor, mục đích, approval và expiry.
5. Liệt kê **toàn bộ đường truy cập**: SSO, local, PAT/API, token/session, PAM, SSH, cloud.
6. Phân loại rủi ro và **contain** kịp thời nếu account còn quyền nhạy cảm hoặc có dấu hiệu lạm dụng.
7. Chọn đúng quyết định: **relink, transfer owner, retain, quarantine, disable, revoke hoặc delete theo retention**.
8. Thực hiện thay đổi tại source và target, tránh stale event/connector regrant.
9. Đọc lại account/grant, kiểm chứng **effective access** và dữ liệu/owner hợp lệ được giữ.
10. Lưu audit, monitoring, owner và deadline cho mọi ngoại lệ.

**Nguyên tắc kết luận:** Không có owner được xác minh là một tín hiệu cần xử lý; **không có HR row hoặc không đăng nhập gần đây không tự động cho phép xóa account**. Khắc phục account mồ côi đúng nghĩa là chứng minh một tài khoản còn hợp lệ có chủ sở hữu và quyền phù hợp, hoặc vô hiệu hóa mọi đường truy cập không còn được phép mà vẫn bảo toàn dữ liệu/audit theo quy định. Khi thực hiện nhất quán với **Joiner–Mover–Leaver, IdP, SSO, SCIM, RBAC/ABAC và quản lý service identities**, tổ chức sẽ giảm quyền tồn dư mà không làm gián đoạn các workload và tài khoản dự phòng hợp lệ.
