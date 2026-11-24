# Giám sát identity trong IAM: theo dõi danh tính, vòng đời và quyền truy cập thực tế

**Giám sát identity (identity monitoring)** là hoạt động **thu thập, liên kết, phân tích, cảnh báo và xác minh liên tục** các sự kiện về danh tính, tài khoản, xác thực, quyền, phiên, credential và trạng thái vòng đời. Mục tiêu là phát hiện **danh tính không hợp lệ, hoạt động bất thường, quyền cấp sai, quyền còn tồn dư và điểm mù trong thực thi chính sách** — trước khi chúng kéo dài thành sự cố nghiêm trọng.

Ví dụ, HR thông báo nhân viên Leaver lúc 17:00; IdP báo tài khoản đã bị vô hiệu, nhưng một API vẫn chấp nhận JWT cấp từ trước và một account cục bộ chưa bị thu hồi. Một hệ thống giám sát đúng không dừng tại `account.disabled=true`: nó nối **Leaver event → yêu cầu thu hồi → trạng thái role/account → session/token → quyết định PERMIT/DENY tại target**, phát hiện khoảng chênh và điều phối xác minh.

Bài thuộc chương **Identity monitoring**, đề mục **Giám sát identity**, của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Nội dung gắn với quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**: từ xác minh, tạo account và cấp quyền đến rà soát, điều chỉnh và thu hồi khi nhiệm vụ thay đổi. Bài kết nối **IdP, SSO, SCIM, RBAC/ABAC, PAM/PIM, danh tính phi con người, kiểm toán và giảm quyền truy cập tồn dư**.

**Nguyên tắc:** **Một login thành công không chứng minh quyền cấp đúng; một lệnh revoke thành công không chứng minh mọi target đã chặn; không thấy log không chứng minh không có hoạt động.** Monitoring phải phân biệt **sự kiện nguồn, trạng thái mong muốn, trạng thái quan sát, quyền hiệu dụng, độ trễ và chất lượng bằng chứng**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Định nghĩa identity monitoring và phân biệt **logging, identity audit, access review, SIEM, UEBA, IAM governance**.
2. Xác định telemetry cho **person/workload, account, role, grant, authentication, session, token, credential, owner và lifecycle state**.
3. Ghép nguồn HR/VMS, IdP, directory, SCIM, ứng dụng, API, PAM/PIM và cloud bằng **canonical ID và correlation ID**.
4. Thiết kế phát hiện chậm cấp/quyền thừa trong **Joiner–Mover–Leaver**, theo mốc hiệu lực và target readback.
5. Phát hiện **orphan/duplicate account, excessive privilege, unauthorized grants, residual access và regrant**.
6. Theo dõi tài khoản **service/workload/CI/CD/Kubernetes/OAuth client** theo mô hình khác con người.
7. Hiểu giới hạn giám sát **RBAC/ABAC/PBAC, IdP/SSO, session và token**.
8. Thiết kế cảnh báo, phân loại, xử lý sự cố và giám sát chất lượng collector.
9. Đo **coverage, freshness, detection delay, revoke propagation và verified closure**.
10. Sử dụng sơ đồ, mẫu dữ liệu, mã giả, tình huống và checklist để triển khai kiểm soát.

## 2. Giám sát identity khác các hoạt động liên quan như thế nào?

| Hoạt động | Câu hỏi chính | Kết quả |
|---|---|---|
| **IAM/IGA** | Subject được phép có quyền nào và vì sao? | Policy, desired entitlements, workflow |
| **Identity monitoring** | Danh tính/quyền nào đang thay đổi, lệch chuẩn hoặc không kiểm chứng được? | Alerts, drift, owner gaps, telemetry |
| **Authentication logging** | Ai xác thực lúc nào, bằng yếu tố gì và kết quả gì? | IdP/SSO/MFA events |
| **SIEM/security analytics** | Sự kiện tổng hợp có dấu hiệu xâm nhập không? | Correlation, case, incident |
| **UEBA** | Hành vi khác baseline đến mức nào? | Risk/anomaly signal, cần triage |
| **Access review/recertification** | Quyền còn được business owner chấp thuận? | KEEP/REVOKE/MODIFY |
| **Identity audit** | Có chứng minh kiểm soát đã vận hành đúng? | Snapshot, decision, remediation/readback |
| **Incident response** | Khi thấy rủi ro, ai xác minh và can thiệp? | Containment, recovery, evidence |

Monitoring thường tạo tín hiệu để **review theo sự kiện**, phát hiện policy drift hoặc mở incident. Quyết định **REVOKE** sau review lại phải được monitoring theo dõi cho tới khi **quyền thực tế tại target được xác minh**.

### 2.1. Nhiều log chưa chắc có khả năng quan sát tốt

Hàng triệu dòng login log không giúp phân tích nếu thiếu **canonical subject, account, target, resource, action, policy version và timestamp đáng tin**. Cần lựa chọn telemetry theo **câu hỏi kiểm soát**, không đo thành công chỉ bằng số log ingest.

## 3. Sáu lớp đối tượng cần theo dõi

| Lớp | Đối tượng | Ví dụ tín hiệu | Rủi ro nếu bỏ sót |
|---|---|---|---|
| **Identity lifecycle** | Person, contractor, workload, engagement, owner | Joiner/Mover/Leaver, owner changed | Danh tính hết căn cứ vẫn truy cập |
| **Account lifecycle** | IdP, app-local, directory, DB, cloud account | Created/enabled/disabled/deleted | Account mồ côi, local bypass |
| **Authentication** | Login, SSO, MFA, recovery, federation | MFA reset, risky login | Account takeover |
| **Authorization** | Role, group, ACL, policy, JIT eligibility | Role granted/revoked, policy changed | Quyền thừa, privilege creep |
| **Session/credential** | Cookie, token, PAT, key, cert, privileged session | Token issued, session open, key rotated | Residual access sau revoke |
| **Governance/evidence** | Owner, review, exception, SoD, readback | Review overdue, exception expired | Rủi ro chưa có người xử lý |

Một subject có thể có nhiều account, credential và grant. **Đừng đưa tất cả vào một trường `userStatus`** rồi suy ra hệ thống an toàn.

## 4. Identity, account, actor, session và entitlement

~~~text
Canonical subject: P-2048 (nhân viên)
  ├─ Engagement ENG-A, status ACTIVE
  ├─ IdP account IDP-2048
  │    ├─ SSO session SES-103
  │    └─ OAuth grant/token family GR-7
  ├─ CRM account CRM-88
  │    └─ Direct ACL customer.export@tenant-A
  └─ Cloud admin persona CLOUD-2048
       └─ PIM eligible project.admin

Non-human subject: workload:nightly-reconcile
  ├─ Service principal SP-91
  ├─ CI/CD or scheduler run RUN-12
  └─ Data API permission invoice.read@tenant-B
~~~

Nên phân biệt:

- **Actor:** Người hoặc automation thực hiện một thao tác.
- **Subject:** Danh tính được hệ thống xác thực/ủy quyền.
- **Account:** Thực thể tại IdP/target.
- **Session/token:** Ngữ cảnh hoặc phương tiện chứng minh truy cập.
- **Grant/entitlement:** Căn cứ cho phép action trên resource.
- **Owner:** Người/đội chịu trách nhiệm quản trị subject/account.
- **Desired state:** Những quyền policy/JML cho phép tồn tại.
- **Effective access:** Những action PEP/Resource Server thực sự chấp nhận.

Người **ACTIVE** có thể giữ account local trái phép; IdP account **DISABLED** nhưng token JWT cũ còn hạn; role đã gỡ khỏi group nhưng direct ACL vẫn PERMIT. Cần kiểm từng lớp.

## 5. Kiến trúc tham chiếu identity monitoring

~~~mermaid
flowchart TD
    HR["HR/VMS<br/>JML + engagement"] --> COL["Collectors + normalization<br/>Source, event time, IDs"]
    IDP["IdP/SSO/MFA/OAuth<br/>Auth + tokens"] --> COL
    DIR["Directory/SCIM<br/>Accounts + groups"] --> COL
    IAM["IAM/IGA/PAM/PIM<br/>Grants + reviews"] --> COL
    API["Cloud/App/DB/Resource Server<br/>Audit + PERMIT/DENY"] --> COL
    WL["Service catalog/CI-CD/K8s<br/>Workload + owner"] --> COL
    COL --> BUS["Event pipeline<br/>Dedup, provenance, integrity"]
    BUS --> GRAPH["Identity correlation<br/>Subject–account–grant–target"]
    GRAPH --> ST["Desired / Observed / Effective<br/>State + freshness"]
    ST --> DET["Detections<br/>JML drift, anomalies, risk"]
    DET --> TRI["IAM Ops / SOC / Risk owner<br/>Triage + decisions"]
    TRI --> ACT["Approved remediation<br/>Revoke, rotate, reassign"]
    ACT --> TARGET["Target enforcement<br/>PEP / identity provider"]
    TARGET --> VERIFY["Readback + safe test<br/>Close or exception"]
    VERIFY --> ST
    BUS --> HEALTH["Collector health<br/>Coverage + gaps + delay"]
    HEALTH --> TRI
~~~

Đây là **mô hình logic**; có thể phối hợp nhiều hệ thống đã có, không cần triển khai mỗi khối thành sản phẩm riêng.

### 5.1. Event-driven và state reconciliation bổ sung nhau

- **Event-driven:** Phản ứng sớm khi HR phát Leaver, MFA reset, PIM activation, role grant.
- **Periodic reconciliation:** Đọc lại target theo chu kỳ phù hợp để phát hiện event mất, local account ngoài IAM hoặc role tự tái cấp.

Chỉ dùng event có thể **bỏ qua thay đổi ngoài pipeline**; chỉ quét định kỳ có thể **phát hiện quá chậm**.

## 6. Các nguồn telemetry và giới hạn của chúng

| Nguồn | Dữ liệu hữu ích | Giới hạn |
|---|---|---|
| **HR/VMS** | Person/engagement, status, effectiveAt, sponsor | Không chứng minh ứng dụng đã revoke |
| **IdP/SSO** | Login, MFA, sessions, group claims, grants | Không bao phủ mọi app-local account |
| **Directory LDAP/AD** | Accounts, nested groups, replication, auth | Không biết mọi direct ACL app |
| **SCIM connector** | Create/update/disable/group PATCH, response | Không mặc định revoke JWT/PAT |
| **IAM/IGA** | Requested/approved/desired rights, review | Desired không tự là effective |
| **PAM/PIM** | Checkout, JIT, eligible/active grant, session | Target session có thể sống ngoài broker |
| **Cloud IAM/audit** | Service principal, role bindings, API actions | Cần ánh xạ actor/owner |
| **Application/API** | Account, resource/action, PERMIT/DENY | Có thể thiếu đường admin trực tiếp |
| **Database** | User, role, session, DDL, audit | Shared account giảm attribution |
| **Vault/PKI** | Credential access, cert expiry/rotation | Không được ghi secret plaintext |
| **CI/CD/K8s** | Repo, workflow/run, workload, namespace | Job actor khác subject target |
| **Service catalog** | Owner, purpose, lifecycle/dependency | Có thể lỗi thời nếu không reconcile |
| **SIEM/case system** | Incident, alert triage, response | Alert không là bằng chứng tấn công |

### 6.1. Source of truth theo loại chủ thể

HR/VMS có thể là nguồn cho **con người và engagement**; service catalog/deployment registry là nguồn cho **workload**, trong khi **target** là nguồn đáng tin cho quyền thực thi tại đó. Login timestamp không thể thay hợp đồng HR, và tên `svc-` không thể chứng minh account là non-human.

### 6.2. Monitoring health là dữ liệu bảo mật

Nếu connector không gửi event 30 phút, trạng thái đúng là **telemetry degraded/unknown**, không phải “không có vi phạm”. Cần theo dõi last seen, collection lag, drop count và pipeline outage.

## 7. Mô hình sự kiện có thể liên kết và kiểm toán

Những field nên định nghĩa nhất quán:

| Field | Ý nghĩa |
|---|---|
| `eventId` / `eventType` | Event duy nhất và loại hành động |
| `sourceSystem` / `schemaVersion` | Nguồn và phiên bản dữ liệu |
| `sourceEventTime` / `observedAt` | Khi xảy ra và khi collector nhận |
| `canonicalSubjectId` | Person/workload được liên kết |
| `sourceAccountId` | Account tại IdP/target |
| `actorId` / `actorKind` | Ai/job nào thực hiện; khác subject nếu delegated |
| `resourceId` / `tenantId` | Phạm vi đối tượng bị tác động |
| `action` / `decision` | Action và PERMIT/DENY/CHANGE |
| `grantSourceRef` | Role, group, direct ACL hoặc policy |
| `changeId` / `incidentId` | Căn cứ change/incident nếu có |
| `correlationId` | Liên kết từ workflow tới target |
| `policyVersion` | Quy tắc được áp dụng |
| `result` / `verificationStatus` | Kết quả và mức đã kiểm chứng |

### 7.1. JSON event minh họa

~~~json
{
  "schemaVersion": "identity-event-v1",
  "eventId": "EVT-2026-4102",
  "eventType": "ENTITLEMENT_REMOVAL_OBSERVED",
  "sourceSystem": "crm-authorization-api",
  "sourceEventTime": "2026-12-05T17:02:00+07:00",
  "observedAt": "2026-12-05T17:02:05+07:00",
  "canonicalSubjectId": "P-2048",
  "sourceAccountId": "CRM-USER-8821",
  "actor": {"kind": "WORKLOAD", "id": "iam-provisioner"},
  "resource": {
    "applicationId": "crm-production",
    "tenantId": "tenant-A",
    "action": "customer.export"
  },
  "grantSourceRef": "direct-acl-399",
  "changeId": "JML-MOVER-221",
  "correlationId": "CORR-8821",
  "policyVersion": "access-policy-v4",
  "result": "REMOVED_FROM_ASSIGNMENT",
  "verificationStatus": "PENDING_EFFECTIVE_ACCESS_CHECK"
}
~~~

**Dữ liệu giả lập, không phải schema chuẩn.** Sự kiện gỡ assignment chưa bảo đảm mọi token/session hay nguồn grant khác mất hiệu lực.

### 7.2. Bảo vệ event ngay từ nguồn

Không ghi **password, OTP, access/refresh token, session cookie, private key** vào log. Dùng token/session references được bảo vệ, schema có type và privacy classification, cùng control về ai được truy vấn.

## 8. Correlation: nối actor, subject, account và target

Một người có thể đăng nhập SSO, dùng admin persona riêng, mở PAM session dưới shared target account và kích hoạt CI/CD job dùng service principal. Nếu chỉ đọc username của từng hệ thống, rất khó giải thích **ai đã đổi quyền gì và theo căn cứ nào**.

~~~text
Human actor P-2048
  -> SSO session SES-103
  -> Approved change CHG-901
  -> CI/CD run RUN-700
  -> Workload principal SP-DEPLOY-PROD
  -> Cloud API request REQ-88
  -> Role policy change policy-123
  -> Audit event EVT-2026-5200
~~~

Dùng **stable IDs** và mapping với `validFrom/validTo`. Email có thể đổi, IP bị NAT/VPN, hostname tái sử dụng; không dùng chúng làm khóa nhận diện duy nhất. Khi mapping thiếu, giữ **UNKNOWN_ACTOR/LOW_CONFIDENCE** thay vì suy đoán một người cụ thể.

### 8.1. Automation tự chạy không luôn có actor người

Nếu job chạy theo scheduler, log phải ghi **job/run ID, trigger/policy version và technical owner**. Đừng bịa “người thao tác” là người viết code năm trước nếu họ không thực hiện request đó.

## 9. Giám sát Joiner: cấp account/quyền đúng căn cứ

**Joiner** cần xác minh danh tính, tạo account và cấp quyền theo engagement/role. Monitoring nên theo dõi:

- Account được tạo trước ngày bắt đầu nhưng **chỉ có onboarding access** hay đã vào production?
- First login và issuance token trước `effectiveAt` có được policy cho phép không?
- Baseline role/birthright grant có khớp role catalog và approval?
- Joiner được gán privileged role có thẩm quyền và SoD hợp lệ?
- Duplicate account do rehire, alias hoặc identity correlation lỗi?
- MFA enrollment/credential issuance có đúng owner và trust?
- SCIM provisioning tới app có complete và target readback?
- HR hủy onboarding: có revoke account/credential đã chuẩn bị?

**Tạo account sớm không tự là vi phạm** nếu mục đích onboarding đã được duyệt. Cần giám sát **business access thực tế** tại thời điểm chính sách, không chỉ tồn tại account.

## 10. Giám sát Mover: quyền mới không che quyền cũ

Mover là đổi vai trò, bộ phận, địa điểm, dự án hoặc engagement. Rủi ro đặc trưng là **privilege accumulation**: quyền mới được thêm nhưng quyền cũ còn.

~~~text
T0: P-2048 thuộc Sales / Project-A
    assigned: crm.export@tenant-A

T1: HR phát Mover sang Finance / Project-B
    desired: invoice.read@B
    undesired: crm.export@A

T2: IAM thêm Finance role
T3: SCIM gỡ Sales group
T4: CRM direct ACL vẫn cấp crm.export@A
T5: API customer.export@A vẫn PERMIT

Kết luận: Mover chưa đạt effective desired state.
~~~

Giám sát cần nối **Mover effectiveAt → desired entitlement delta → provisioning tasks → target roles/ACL → token/session → API decision**. Kiểm cả PIM eligibility, quyền CI/CD/vault human từng có và regrant từ sync/IaC.

### 10.1. Nhiều engagement

Một contractor có dự án A và B; A kết thúc nhưng B còn ACTIVE. Chặn đúng **quyền A** và giữ B hợp lệ nếu policy cho phép. Không dùng một `accountDisabled` toàn cục nếu chỉ một engagement bị hủy.

## 11. Giám sát Leaver: thời điểm revoke và quyền tồn dư

Leaver cần theo dõi **thời gian từ HR/VMS effective event đến khi Resource Server/target không còn cho thực hiện hành động trái căn cứ**.

~~~mermaid
sequenceDiagram
    autonumber
    participant HR as HR / VMS
    participant IAM as IAM / IGA
    participant IDP as IdP / SSO
    participant TAR as App / SCIM / Target
    participant MON as Identity monitoring
    participant VER as Verification / Risk owner
    HR->>IAM: Leaver + effectiveAt
    IAM->>IDP: Disable / revoke sessions
    IAM->>TAR: Revoke grants + local access
    HR-->>MON: Authoritative lifecycle event
    IDP-->>MON: Account/session outcome
    TAR-->>MON: Target change + API events
    MON->>MON: Compare desired/observed/effective
    MON-->>VER: Overdue, residual or unknown
    VER->>TAR: Safe readback / authorization check
    TAR-->>VER: DENY / PERMIT / UNKNOWN
    VER-->>MON: Verified result / exception
~~~

### 11.1. Kiểm những đường nào?

- IdP/SSO session và app-local account.
- SCIM group, nested grants, direct ACL, cloud role.
- Access/refresh token, PAT, API key, SSH key/certificate.
- PAM/PIM eligible/active privileged role và target session.
- Database/VPN connections, external guest access.
- Credentials mà Leaver từng biết hoặc có thể lấy ở vault.
- Quyền từ engagement khác vẫn hợp lệ.

Ví dụ HR effectiveAt 17:00, IdP disable 17:01, SCIM update 17:03, API negative test DENY lúc 17:06. **Chỉ có bằng chứng DENY tại 17:06 trong scope kiểm**, không khẳng định quyền đã chặn chính xác 17:00.

### 11.2. Unknown khác denied

Nếu target timeout hoặc collector hỏng, `verification=UNKNOWN`; cần risk owner, mitigation và retry. **Network failure không phải authorization DENY**.

## 12. Contractor, guest và federated identity

Những account từ đối tác có thể xác thực thành công ở external IdP dù hợp đồng tại tenant đã hết. Monitoring cần theo dõi:

- Sponsor/engagement còn ACTIVE không?
- External issuer/subject mapping có đúng và trust được duyệt?
- Local app role/guest membership có hết hạn đúng mốc?
- Group/federation mapping có tự cấp scope rộng hơn dự kiến?
- Target session/token còn cho access sau kết thúc engagement?
- Hai engagement có bị thu hồi nhầm lẫn không?
- Guest được tạo không có sponsor hay không?

**SSO login thành công không chứng minh engagement ở tài nguyên đích còn hợp lệ.** Identity và resource authorization phải được kiểm độc lập.

## 13. Giám sát non-human identity và service account

**Non-human identities (NHI)** gồm service accounts, OAuth clients, cloud service principals, managed identities, Kubernetes ServiceAccounts, bots, CI/CD và recovery jobs.

| Loại | Tín hiệu đáng theo dõi | Finding |
|---|---|---|
| **Service principal** | Owner, grants, secret/key, API actions | Ownerless, excessive role |
| **OAuth client** | Token issuance, allowed scope/audience | Client vượt grant |
| **Managed identity** | Runtime binding, cloud IAM role | Role còn sau workload retire |
| **CI/CD** | Repo/workflow/run, release, deploy actor | Staging sửa production |
| **Kubernetes ServiceAccount** | Namespace, RoleBinding, pod identity | Cluster-admin không cần thiết |
| **DB service user** | Permission, credential, session | DBA role tồn dư |
| **Bot/RPA** | Automation owner, runtime, app actions | Dùng password người làm bot |
| **Backup/recovery** | Recovery purpose, DR drills, secret | Privileged identity không owner |
| **Certificate/mTLS** | Issuer/trust, expiry, rotation | Unmanaged cert/key |

### 13.1. Owner JML khác workload lifecycle

Khi kỹ sư owner Mover/Leaver, **không tự xóa production workload**. Giám sát phải yêu cầu **transfer owner**, gỡ quyền human vào vault/CI/cloud, đánh giá credential từng biết, rotate theo rủi ro và kiểm account workload còn purpose/least privilege. Khi service thật sự retire, cần revoke principal, role, key/token, direct ACL và readback.

### 13.2. Last used không đủ

Recovery account có thể hiếm dùng nhưng hợp lệ; một service principal dùng hàng ngày vẫn có thể giữ `cloud.owner` không cần thiết. Cần **purpose, dependency, owner và effective scope**.

## 14. Giám sát đăng nhập IdP/SSO và authentication

Các tín hiệu:

- Login success/failure theo subject/account/app/client/time.
- Nhiều thất bại rồi một lần thành công.
- Login sau Leaver/suspend hoặc từ admin account ngoài policy.
- Authentication context yếu hơn yêu cầu cho thao tác nhạy cảm.
- New device/session và risk indicators bất thường.
- Federation assertion từ issuer/audience không khớp.
- SSO session còn sau security revoke nếu policy yêu cầu chặn.
- Admin/direct login ngoài PAM/bastion bắt buộc.
- Login gần thời điểm MFA reset hoặc password recovery bất thường.

**Không coi địa lý IP là sự thật tuyệt đối.** VPN, proxy, NAT và carrier mobile có thể làm “impossible travel” giả. Alert cần triage theo trusted context và activity thực tế.

## 15. Giám sát MFA, account recovery và assurance

Đặc biệt theo dõi:

1. Thêm/gỡ authenticator cho tài khoản privileged.
2. Reset MFA sau helpdesk request thiếu proofing/approval.
3. Thay recovery method rồi mở phiên mới bất thường.
4. Chuyển sang yếu tố yếu hơn policy risk yêu cầu.
5. Repeated MFA prompt failures, bất thường theo baseline.
6. Step-up trước policy change hoặc export nhạy cảm.
7. Thay password/credential kèm nhiều token issuances.
8. Emergency bypass/fallback được kích hoạt không đúng căn cứ.

**MFA reset không tự chứng minh compromise**: người dùng đổi điện thoại có thể hợp lệ. Cần xem actor, identity verification workflow, timestamps, case ID, policy và hành động tiếp theo. Không ghi OTP, recovery code hoặc private key vào log.

## 16. Giám sát Directory/SCIM provisioning

| Event | Câu hỏi cần theo dõi |
|---|---|
| SCIM create/update | Target account map đúng canonical subject? |
| SCIM `active=false` | Local session/token còn chấp nhận? |
| Group removal | Direct ACL/nested role còn cấp quyền? |
| Directory replication delay | DC/replica còn nhìn thấy quyền cũ? |
| IdP disable | RP/app local session còn? |
| Connector retry/timeouts | Duplicate operation hoặc partial apply? |
| Directory privilege group change | Có approval và effective permission đúng? |
| Federation trust config change | Issuer/certificate/metadata được duyệt? |

**HTTP 200/202** phản ánh contract của endpoint, không tự bảo đảm mọi API key/session/direct ACL bị thu hồi. Nếu directory/IaC tự tái cấp role đã gỡ, phải tìm **source-of-truth** gây regrant thay vì gỡ lặp vô hạn.

## 17. Giám sát RBAC/ABAC/PBAC và quyền hiệu dụng

**RBAC** cấp theo role, **ABAC** dùng thuộc tính, **PBAC** dựa policy và context. Monitoring cần quan sát:

- **Identity drift:** Subject–account mapping sai hoặc unknown.
- **Role drift:** Role/group ngoài catalog/approval.
- **Attribute drift:** Department/tenant/status cũ trong cache.
- **Policy drift:** Allow/Deny rule thay ngoài change management.
- **Direct grant drift:** App-local ACL không có trong IGA.
- **Session drift:** Token/connection còn quyền cũ.
- **Ownership drift:** Role/service account không owner.
- **Regrant drift:** IaC/controller tái tạo quyền bị revoke.

~~~text
Desired:   P-2048 không có customer.export@tenant-A
Assigned:  IdP group Sales đã gỡ
Target:    CRM direct ACL vẫn cấp customer.export@tenant-A
Effective: API PERMIT cho action tương ứng
Detection: RESIDUAL_EFFECTIVE_ACCESS
~~~

**Không chỉ so role names**; Resource Server còn xét resource, action, tenant, trusted attributes, deny rules và token/session.


## 18. Giám sát đặc quyền với PAM/PIM và break-glass

Đặc quyền có thể cho phép tạo danh tính, đổi role, xem secrets, sửa production hoặc vô hiệu kiểm toán. Vì vậy ngoài login còn cần giám sát **standing, eligible và active privilege**, bao gồm:

1. Grant admin mới, đặc biệt qua direct assignment.
2. PIM **eligible** role chưa kích hoạt nhưng có khả năng kích hoạt.
3. JIT activation, mục đích, approval, TTL và target.
4. PAM checkout, actor–shared account mapping, session start/end.
5. Hành động target: thay IAM policy, federation trust, MFA, key, audit.
6. Credential hoặc local account được tạo trong phiên admin.
7. Privileged session tồn tại sau mốc role activation expiry.
8. Truy cập trực tiếp ngoài broker bắt buộc theo policy.
9. Emergency/break-glass không có incident hoặc hậu kiểm.
10. Log/recording bất ngờ bị tắt khi phiên đặc quyền hoạt động.

### 18.1. JIT hết hạn không tự chặn target session

~~~text
20:00  PIM cấp role database.admin tới 20:30
20:10  PAM mở DB session
20:30  PIM báo activation expired
20:45  DB session vẫn cho ALTER ROLE
21:00  DB session mới đóng

Monitoring finding:
  PRIVILEGED_SESSION_SURVIVED_GRANT_EXPIRY
~~~

Phải xác định khả năng **kill session, re-evaluate authorization, revoke credential** của target. Không kết luận quyền đã mất chỉ vì dashboard PIM có timestamp expiry.

### 18.2. Giám sát khẩn cấp khi PAM/IdP/SIEM lỗi

Đường break-glass đôi khi phải độc lập với thành phần đang hỏng. Cần **fallback logging, actor attribution khi khả thi, native target audit, kênh thông báo ngoài hệ thống và post-use review** được thiết kế trước. Monitoring hỏng không được biến thành quy tắc `PERMIT_ALL` không giới hạn.

## 19. Session, token và credential: nhiều đồng hồ khác nhau

Một subject có thể có **IdP SSO session, application session cookie, OAuth access/refresh token, mobile session, PAT/API key, cloud CLI credential, SSH cert hoặc database connection**. Những hiện vật này có TTL/revocation semantics khác nhau.

| Biến cố | Monitoring cần kiểm |
|---|---|
| IdP user disabled | Ứng dụng local và Resource Server còn nhận request? |
| Logout một app | IdP/SSO và app khác có còn session? |
| Refresh-token family revoked | Access token JWT đã phát còn tới `exp`? |
| Client secret rotated | Client credential cũ và token còn được dùng? |
| PIM grant expired | Target privileged session còn PERMIT? |
| Service principal retired | Cloud IAM role, API key, cert, ACL còn? |
| MFA reset | Session cần re-auth/revoke theo policy? |
| Idle timeout | Request nền có đang gia hạn sai phiên người? |

### 19.1. JWT hợp lệ vẫn có thể trái quyền

Access token có chữ ký, issuer, audience và expiry hợp lệ không tự chứng minh request **được phép trên tenant/resource cụ thể**. API phải kiểm policy phù hợp, và monitoring nên lấy **auth decision events** khi cần chứng minh quyền.

### 19.2. Session end khác grant end

Một PAM session có thể đóng, nhưng role/PAT tiếp tục kích hoạt quyền khác. Một role đã revoke vẫn có thể tồn tại trong token/session cache. **Trạng thái kết thúc phải được định nghĩa theo scope**, không chỉ một record.

## 20. Monitoring governance: ownership, approval và review

Giám sát identity không chỉ là phát hiện xâm nhập; nó còn phát hiện **quyền không có trách nhiệm giải trình**.

| Tín hiệu | Hướng xử lý |
|---|---|
| Human account không còn engagement | Kiểm JML/target/owner mapping |
| Service principal không owner | Tìm service/deployment và giao technical owner |
| High-risk role cấp không có approval | Điều tra grant source và risk |
| Access review quá hạn | Escalate reviewer/resource owner |
| Reviewer tự KEEP privileged role trái SoD | Independent review/exception |
| REVOKE decision nhưng API còn PERMIT | Remediation và effective access verification |
| Approved exception đã quá expiry | Risk escalation, không auto-close |
| Automation tự regrant quyền | Sửa provisioning source-of-truth |
| Owner Mover nhưng còn vault/CI admin | Gỡ human administrative entitlements |
| Role catalog không biết semantics | Bổ sung entitlement dictionary trước review |

### 20.1. Phân biệt từng bước

~~~text
REVIEW_PENDING
  -> DECISION_RECORDED
  -> REMEDIATION_REQUESTED
  -> TARGET_CHANGE_OBSERVED
  -> EFFECTIVE_ACCESS_VERIFIED
hoặc
  -> EXCEPTION_OPEN / ESCALATED
~~~

**Một item `review=COMPLETE` không đồng nghĩa `access=VERIFIED_REVOKED`**. Monitoring cần giữ các trạng thái riêng cùng audit trail.

## 21. Phát hiện bất thường phải theo bối cảnh

Một rule có thể phát hiện:

- Impossible travel giữa hai login.
- Password spraying hoặc thất bại nhiều rồi thành công.
- Privilege elevation ngoài giờ.
- Account admin bất ngờ tạo key mới.
- Workload API traffic tăng đột biến.
- MFA reset tiếp theo là truy cập dữ liệu nhạy cảm.
- Service principal mới có cloud owner role.
- Login qua direct path không được policy cho phép.

Tuy nhiên:

- IP qua VPN/NAT/mobile carrier có thể làm sai vị trí địa lý.
- Batch job hợp lệ có thể tăng API calls cuối tháng.
- Emergency response có thể xảy ra lúc 02:00.
- Một account ít dùng có thể là recovery identity bắt buộc.
- Account lockout có thể do client bị cấu hình sai.

**Signal không phải kết luận tấn công.** Triage cần thông tin **identity, grant, risk, workload, incident/change, baseline và target actions**, sau đó phân loại benign, authorized exception, control failure, suspected compromise hoặc confirmed incident theo quy trình.

## 22. Những trường hợp cảnh báo cần ưu tiên

| Nhóm detection | Điều kiện ví dụ | Thực thể chịu trách nhiệm |
|---|---|---|
| **JML_TIME_VIOLATION** | Login hoặc API PERMIT sau Leaver effectiveAt | IAM + App owner + SOC |
| **MOVER_RESIDUAL_ACCESS** | Action cũ vẫn PERMIT sau role change | IAM + Resource owner |
| **ORPHAN_ACCOUNT** | Account không mapping/owner trong phạm vi yêu cầu | Identity governance |
| **UNAPPROVED_PRIVILEGE_GRANT** | Admin role tăng ngoài workflow | Security + PAM/target owner |
| **REGRANT_AFTER_REVOKE** | Quyền xuất hiện lại sau verified revoke | Provisioning/IaC owner |
| **MFA_RECOVERY_RISK** | Reset MFA không khớp approval hoặc kèm login lạ | IdP/security |
| **FEDERATION_TRUST_CHANGE** | Issuer/certificate/mapping bị sửa ngoài change | IAM platform + security |
| **CREDENTIAL_EXPOSURE** | Secret/token xuất hiện trong log | Incident response |
| **PRIVILEGED_SESSION_OVERTIME** | Target session còn action sau JIT expiry | PAM/target owner |
| **WORKLOAD_OWNER_MISSING** | Service principal quyền cao không owner | Service/platform owner |
| **POLICY_DRIFT** | PDP/PEP policy lệch baseline | App/security owner |
| **MONITORING_GAP** | Collector mất log khi quyền cao active | Observability/incident |
| **REVIEW_REMEDIATION_OVERDUE** | REVOKE chưa đạt target state quá hạn | IAM governance + target owner |
| **SUSPICIOUS_TOKEN_REUSE** | Refresh token đã USED bị trình lại | Authorization Server/security |
| **UNEXPECTED_SERVICE_IDENTITY_USE** | Job dùng principal ngoài environment được phép | Cloud/CI owner |

### 22.1. Rule cần phiên bản và căn cứ

Một alert nên lưu **ruleId, ruleVersion, detection time, source events, account/target, evidence confidence, current JML state và owner**. Không chỉ có một chuỗi `suspicious=true` không giải thích được.

## 23. Tương quan theo thời gian: trình tự hành vi quan trọng

Một sự kiện riêng lẻ có thể hợp lệ; chuỗi sự kiện có thể cho thấy sự cố:

~~~mermaid
sequenceDiagram
    autonumber
    participant HR as HR / VMS
    participant IDP as IdP / MFA
    participant IAM as IAM / IGA
    participant API as Resource Server
    participant MON as Identity monitoring
    participant SOC as SOC / IAM Ops

    HR-->>MON: Mover P-2048 effective 09:00
    IDP-->>MON: MFA factor reset 09:05
    IAM-->>MON: Admin role granted 09:06
    IDP-->>MON: New session 09:07
    API-->>MON: Bulk export permitted 09:08
    MON->>MON: Correlate subject + grant + resource + time
    MON-->>SOC: High-priority risk signal + evidence
    SOC->>IAM: Verify approval, status, ownership
    SOC->>API: Check action/resource context and containment need
    SOC-->>MON: Triage decision and case outcome
~~~

Chuỗi trên **chưa tự chứng minh tấn công**. Có thể là incident/recovery hợp lệ hoặc hành động trái policy. Nhưng việc nối **MFA change → privilege grant → session → bulk action** tạo cơ sở triage hơn hẳn bốn alert độc lập.

### 23.1. Event đến trễ hoặc sai thứ tự

Nếu cloud audit gửi chậm 3 phút, thứ tự `ingestedAt` khác `sourceEventTime`. Correlation engine cần thiết kế **time window, allowed lateness, deduplication, source clock skew**; không tự biến request đến trước thành hành động xảy ra trước.

## 24. Event-driven detection và periodic reconciliation

| Cách làm | Phù hợp để | Hạn chế |
|---|---|---|
| **Streaming events** | Leaver/privileged grant, login risk, token reuse, emergency | Mất event nếu collector/queue lỗi |
| **Scheduled target inventory** | Orphan account, direct ACL, stale role, credential inventory | Phát hiện chậm giữa hai lần quét |
| **State diff** | Desired vs observed roles/accounts/grants | Cần mapping và as-of nhất quán |
| **Effective permission checks** | Chứng minh target PERMIT/DENY action cụ thể | Chỉ bao phủ scope đã kiểm |
| **Access review signals** | Business necessity, owner certification | Quyết định định kỳ có thể lỗi thời |
| **Threat intelligence/risk signals** | Account compromise context | Có false positive, thay đổi theo nguồn |

### 24.1. Giám sát quyền trực tiếp ngoài workflow

Một operator có thể gán quyền ngay tại target mà không qua IGA, nên **IGA workflow logs không thấy request**. Periodic target inventory và native audit cần phát hiện **unmanaged grant**, tìm actor, approval và remediator.

### 24.2. Reconciliation cần xử lý quyền kế thừa

Một role cấp qua nested groups hoặc policy conditions có thể không xuất hiện như direct assignment. Cần biểu diễn **grant provenance/lineage** để không bỏ sót effective permissions hoặc xóa sai nhóm phục vụ nhiều hệ thống.

## 25. Freshness, eventual consistency và thời gian hội tụ

Giám sát phải phân biệt:

- `sourceEventTime`: Khi nguồn cho rằng sự kiện xảy ra.
- `observedAt`: Khi collector ghi nhận.
- `processedAt`: Khi correlation/detection hoàn tất.
- `desiredEffectiveAt`: Khi chính sách yêu cầu quyền đổi.
- `targetAppliedAt`: Khi target xác nhận áp thay đổi.
- `verifiedAt`: Khi đã readback/permission-check.
- `lastHeartbeatAt`: Khi nguồn collector còn hoạt động.

Một Leaver effectiveAt 17:00 nhưng target DENY lúc 17:06 có thể vi phạm policy có mốc tức thời. **Phải báo độ trễ thực tế và phạm vi đo**, không thay bằng timestamp lệnh revoke lúc 17:01.

### 25.1. Cần đặt expectation theo rủi ro

Tài nguyên admin production có thể yêu cầu phản ứng nhanh hơn ứng dụng ít nhạy cảm. Không có con số SLO áp cho mọi tổ chức. Cần xác định **độ trễ cho phép, nguồn thời gian, độ mới cache, connector retries, canary/negative test** theo policy.

### 25.2. As-of mismatch

So role snapshot lúc 08:00 với directory state lúc 10:00 và HR state lúc 12:00 có thể tạo false drift. Lưu **asOf/observedAt + staleness** cho từng nguồn và chỉ kết luận khi có dữ liệu đủ thời gian.

## 26. Chất lượng và tính liên tục của telemetry

Một số lỗi pipeline:

- Collector ngừng gửi event nhưng dashboard vẫn xanh.
- Connector đọc được 80% target nhưng 20% trả lỗi permission.
- Duplicate delivery tạo nhiều alert.
- Log schema đổi khiến mapping actor/subject bị mất.
- Timezone/clock skew làm sai thứ tự sự kiện.
- Event backlog tạo false SLA breach hoặc phát hiện trễ.
- Storage retention xóa dữ liệu trước kỳ audit.
- Một nguồn quan trọng bị mất mà không có cảnh báo.
- Log ghi raw token hoặc dữ liệu nhạy cảm ngoài dự kiến.
- SIEM/central collector bị ảnh hưởng đúng lúc emergency access.

### 26.1. Health signals cần tách khỏi security detections

| Chỉ số health | Cách dùng |
|---|---|
| **Source last seen** | Phát hiện nguồn ngừng gửi |
| **Ingest/processing lag** | Biết event đến trễ |
| **Event drop/dead-letter count** | Xác định mất record |
| **Schema validation failure** | Xử lý sự kiện không parse được |
| **Source API permission failures** | Phát hiện collector mất quyền |
| **Inventory coverage** | Biết hệ thống/account bị bỏ ngoài scope |
| **Time sync skew** | Bảo vệ tính đúng timeline |
| **Correlation unmatched rate** | Biết account không map canonical subject |
| **Log integrity failure** | Phát hiện artifact bị sửa |
| **Recovery/replay success** | Đo phục hồi sau outage |

**Alert `MONITORING_GAP` có thể có ưu tiên cao** nếu đó là nguồn duy nhất quan sát một privileged target đang bị truy cập.

## 27. Alert lifecycle: từ phát hiện đến đóng có kiểm chứng

~~~mermaid
flowchart TD
    A["Event / State mismatch"] --> B["Detection<br/>Rule + evidence + confidence"]
    B --> C["Dedup / correlation<br/>Risk + entity + time window"]
    C --> D["Route to IAM Ops / SOC / owner"]
    D --> E{"Triage outcome?"}
    E -->|Benign / false positive| F["Document reason<br/>Tune rule if needed"]
    E -->|Authorized exception| G["Validate approval, TTL<br/>Monitor expiration"]
    E -->|Policy violation / compromise| H["Contain + investigate<br/>Authorized action"]
    H --> I["Revoke / rotate / correct target"]
    I --> J["Readback / safe negative test"]
    J --> K{"Effective state verified?"}
    K -->|Yes| L["Close with evidence"]
    K -->|No / Unknown| M["Exception + owner + deadline"]
    M --> I
    F --> N["Audit outcome + learning"]
    G --> N
    L --> N
~~~

### 27.1. Event ACK khác xử lý xong

- **ALERT_CREATED:** Rule phát hiện.
- **ACKNOWLEDGED:** Người trực đã nhận.
- **TRIAGED:** Đã xác minh/nghiên cứu căn cứ.
- **ACTION_REQUESTED:** Có lệnh remediation.
- **TARGET_CHANGED:** Target báo cập nhật.
- **VERIFIED_CLOSED:** Quyền/điều kiện trong scope đạt policy.
- **EXCEPTION_OPEN:** Chưa đủ bằng chứng hoặc chưa xử lý.

**ACK trong 2 phút không tự chứng minh mất quyền trong 2 phút.**

## 28. Cấp độ ưu tiên và routing theo risk

| Mức minh họa | Ví dụ | Hướng xử lý |
|---|---|---|
| **Informational** | Joiner được tạo account đúng workflow | Correlation/audit, không làm phiền |
| **Attention** | Account mapping thiếu owner, login khác thói quen | IAM owner kiểm trong quy trình |
| **High** | Admin role cấp không approval, Leaver target chưa verify | IAM/SOC/target owner triage |
| **Critical** | Leaver vẫn được PERMIT production admin action, nghi chiếm privileged session | Incident response theo policy |
| **Monitoring degraded** | Log/collector chết trên critical privileged target | Fallback + owner khôi phục giám sát |

### 28.1. Severity không tự quyết chỉ bởi tên event

`ROLE_GRANTED` có thể hợp lệ theo JIT approval; `MFA_RESET` có thể hợp lệ vì người dùng đổi điện thoại. Risk cần xét **resource sensitivity, actor authority, request scope, timing, incident/change context, subject status và khả năng can thiệp**.

### 28.2. Tách quyền triage với quyền can thiệp

SOC analyst có thể thấy alert nhưng không có quyền kill database session. Quy trình phải định nghĩa **ai được revoke account/token, ai dừng workload, ai phê duyệt ảnh hưởng availability và ai hậu kiểm**.

## 29. Ví dụ policy detection cấu trúc (YAML)

~~~yaml
# Chỉ là mô hình ý định kiểm soát, không phải cấu hình SIEM chuẩn.
policyId: identity-monitoring-v1
owner: iam-security-governance
sources:
  required:
    - hr-vms-lifecycle
    - idp-authentication
    - directory-groups
    - target-authorization
  health:
    alertWhenSourceSilent: POLICY_DEFINED
    monitorSchemaErrors: true
    monitorIngestLag: true
identity:
  canonicalCorrelationRequired: true
  unknownOwnerCreatesFinding: true
  sourceTrustRequired: true
lifecycle:
  joiner:
    checkAccessBeforeEffectiveAt: true
    detectUnexpectedBirthrightPrivilege: true
  mover:
    compareOldNewDesiredGrants: true
    checkResidualAccess: true
  leaver:
    requireTargetVerification: true
    doNotWaitForReviewCampaign: true
  nonHuman:
    requireOwnerAndPurpose: true
    checkRetiredWorkloadResidualGrants: true
detections:
  - unapproved-privileged-grant
  - account-active-after-leaver
  - mover-residual-access
  - orphan-identity
  - suspicious-mfa-recovery
  - regrant-after-revoke
  - privileged-session-after-jit-expiry
  - monitoring-gap
response:
  requireRiskBasedTriage: true
  prohibitAutoCloseOnUnknownTarget: true
  storeEvidenceReferencesNotSecrets: true
  exceptionsNeedOwnerAndExpiry: true
~~~

**Không áp các ngưỡng/triệu chứng một cách máy móc**. Policy phải được cấu hình với nguồn dữ liệu đáng tin và hiện thực hỗ trợ. Một field `requireTargetVerification=true` không tự cung cấp API permission-check nếu target chưa có khả năng đó.

## 30. Mã giả đánh giá sai lệch JML

~~~python
# Pseudocode để học, không phải engine IAM production.
def assess_identity_state(subject_id, event, sources):
    subject = sources.canonical_identity(subject_id)
    if subject is None:
        return {"state": "UNKNOWN_IDENTITY", "requiresTriage": True}

    authoritative = sources.lifecycle_state(subject_id)
    target = sources.target_state(subject_id, event.target_id)

    if authoritative is None or target is None:
        return {
            "state": "UNKNOWN_INCOMPLETE_TELEMETRY",
            "requiresTriage": True
        }

    observations = []

    if authoritative.is_leaver_effective(event.observed_at):
        if target.account_enabled:
            observations.append("ACCOUNT_ACTIVE_AFTER_LEAVER")
        if target.recent_authorization_permit:
            observations.append("EFFECTIVE_ACCESS_AFTER_LEAVER")

    if authoritative.has_mover_effective(event.observed_at):
        stale = target.effective_grants - authoritative.desired_grants
        if stale:
            observations.append("MOVER_RESIDUAL_GRANT")

    if not target.owner_is_known:
        observations.append("OWNER_UNKNOWN")

    if not sources.telemetry_is_fresh(event.target_id):
        observations.append("MONITORING_FRESHNESS_GAP")

    # Những kết quả này chỉ là signals để triage.
    # Không xóa account hoặc kết luận compromise tại đây.
    return {
        "signals": observations,
        "requiresTriage": bool(observations),
        "verificationRequired": True
    }
~~~

### 30.1. Các giả định cần làm rõ

- `sources` phải trả dữ liệu **authoritative**, không tin JSON client tự khai.
- Date/time phải chuẩn UTC/offset, có clock skew và as-of.
- `effective_grants` là khái niệm lý tưởng; thực tế cần xử lý nhiều source, deny policy, token/session và ACL.
- Human có thể có nhiều engagement; không so tất cả quyền với một field department.
- Không có record từ target chưa chắc đồng nghĩa tài khoản/quyền đã mất.
- Rule engine cần dedup, idempotency, concurrency, policy version và escalation.
- **Không tự chạy revoke production từ pseudocode này**.

## 31. Giám sát quyền truy cập thực tế và safe verification

Một finding như `ACCOUNT_ACTIVE_AFTER_LEAVER` có thể được xác nhận bằng target account readback; nhưng **không đủ chứng minh action cụ thể còn được phép**. Ngược lại, một API PERMIT ở thời điểm đã hết quyền tạo bằng chứng mạnh hơn về residual access trong scope đó.

### 31.1. Các trạng thái verification

| Trạng thái | Nghĩa |
|---|---|
| **VERIFIED_DENIED** | Target từ chối action trong phạm vi đã kiểm |
| **VERIFIED_ALLOWED** | Target còn chấp nhận action trong scope |
| **UNKNOWN** | Không thể kết luận do source/target lỗi hoặc thiếu quyền kiểm |
| **PARTIALLY_VERIFIED** | Một số đường đạt, số khác còn unknown |
| **NOT_APPLICABLE** | Không có phép kiểm phù hợp, có lý do rõ |

**Không thử lệnh phá hoại trên production** chỉ để kiểm quyền. Dùng authorization-check API, read-only permissions query, môi trường kiểm thử hoặc safe negative test được phê duyệt, có expected/observed decision và timestamp.

### 31.2. Verifying at one point is not forever

Quyền đã bị từ chối lúc 17:05 vẫn có thể bị **IaC/directory sync cấp lại lúc 02:00**. Vì vậy cần monitoring regrant và source-of-truth drift; bằng chứng phải luôn có thời điểm và phạm vi.

## 32. Mẫu event alert và triage

~~~json
{
  "alertId": "ALERT-2026-2201",
  "ruleId": "MOVER_RESIDUAL_ACCESS",
  "ruleVersion": "v3",
  "detectedAt": "2026-12-08T10:10:00+07:00",
  "subjectRef": "P-2048",
  "subjectKind": "EMPLOYEE",
  "sourceLifecycleEventRef": "MOVER-ENG-288",
  "target": {
    "applicationId": "crm-production",
    "tenantId": "tenant-A",
    "action": "customer.export"
  },
  "evidence": {
    "desiredStateRef": "IAM-DESIRED-11",
    "assignedGrantRef": "CRM-DIRECT-399",
    "authorizationDecisionRef": "CRM-REQ-781",
    "observedDecision": "PERMIT",
    "sourceFreshness": "CURRENT_AT_OBSERVED_TIME"
  },
  "classification": "CONTROL_GAP_REQUIRES_TRIAGE",
  "riskTier": "HIGH",
  "ownerRef": "crm-resource-owner",
  "incidentRef": null,
  "status": "OPEN",
  "verificationStatus": "PENDING_REMEDIATION"
}
~~~

Các ID, thời điểm và trạng thái là **giả lập**. `PERMIT` trong event là bằng chứng cho request đó tại thời điểm đó, không phải mọi endpoint. Không lưu token, mật khẩu hoặc dữ liệu khách hàng để tạo alert.

## 33. Tính toàn vẹn, nguồn gốc và quyền riêng tư

Identity monitoring thường xử lý dữ liệu về người và quyền nhạy cảm. Kiểm soát cần:

- **Data minimization:** Chỉ thu fields cần thiết, tránh payload chứa PII/secret.
- **Role-based access to telemetry:** IAM ops, SOC và auditor xem đúng scope.
- **Encryption:** Khi truyền và lưu, quản lý key riêng.
- **Audit pipeline changes:** Ai sửa rule/collector/retention và lúc nào.
- **Versioning/provenance:** Event source, schema, policy version, collection method.
- **Tamper resistance:** Hạn chế target admin xóa audit có liên quan đến chính họ.
- **Integrity checking:** Hash/signature/append-only khi phù hợp, không tự khẳng định bất biến tuyệt đối.
- **Time consistency:** UTC/offset và monitoring clock skew.
- **Controlled retention:** Theo nghĩa vụ thực tế; tránh lưu vô hạn.
- **Data access history:** Ai search/export/share log và evidence.
- **Fallback and recovery:** Nếu central SIEM hỏng, native audit/buffer/kênh khác và ghi gaps.
- **De-identification for trends:** Aggregate/pseudonymous analytics khi không cần lộ người cụ thể.

### 33.1. Không đánh đồng hash với độ tin cậy nguồn

Một CSV thiếu 20% entitlement vẫn có hash SHA-256 hợp lệ. Hash bảo vệ **nguyên vẹn sau thu thập**, không chứng minh population đầy đủ hoặc mapping chính xác.

### 33.2. Không dùng “giám sát” để giữ credential

Không log raw access/refresh tokens, session IDs có thể dùng, API keys, OTP, private keys hay nội dung authentication secret. Reference/correlation ID là đủ cho nhiều trường hợp.

## 34. Giám sát coverage, freshness và chất lượng phát hiện

Những metrics có giá trị:

| Chỉ số | Đo điều gì | Bẫy |
|---|---|---|
| **Source coverage** | Target/IdP/DB/cloud nào có telemetry | Mẫu số inventory thiếu |
| **Identity correlation coverage** | Account map canonical subject/owner | Unknown không phải không tồn tại |
| **Source event freshness** | Lag giữa event time và observation | Collector trễ làm phát hiện chậm |
| **Lifecycle-to-target latency** | Từ JML effectiveAt tới target desired state | Connector ACK không bằng effective deny |
| **Verified revocation latency** | Từ mốc cần chặn tới DENY được chứng minh | Cần đúng scope/time |
| **Residual access count/age** | Quyền trái policy vẫn còn | Direct ACL/token bị bỏ sót |
| **Unauthorized privileged grants** | Admin grants thiếu approval | Có ngoại lệ hợp lệ cần phân loại |
| **Orphan identity count** | Account/workload thiếu owner | Không tự xóa recovery account |
| **Regrant-after-revoke count** | Quyền đã gỡ quay lại | Cần sửa IaC/source |
| **Alert precision** | Alert được triage là actionable | Labeling bias, missing events |
| **Time-to-triage** | Từ alert tới quyết định sơ bộ | ACK không phải remediation |
| **Time-to-verified-closure** | Alert tới target permission state đúng | Cần phân biệt exceptions |
| **Monitoring gap duration** | Khoảng thiếu telemetry | Không có event ≠ không có hành động |
| **Schema/error rate** | Event sai định dạng hoặc drop | Có thể âm thầm làm mất detections |
| **Privileged monitoring coverage** | Standing/eligible/active paths được quan sát | Chỉ PAM recording là chưa đủ |
| **NHI owner/credential coverage** | Service principals có owner/credential status | Dùng tiền tố tên không đủ |
| **Exception aging** | Rủi ro chưa xử lý theo deadline | Approved exception không phải fixed |

### 34.1. SLI/SLO nên có mẫu số đúng

~~~text
JML Verified Closure Rate =
  count(JML items có target readback PASS theo scope)
  / count(JML items cần verify theo policy)

Identity Correlation Coverage =
  count(target accounts có canonical subject/owner mapping)
  / count(target accounts thuộc inventory scope)

Telemetry Freshness =
  observedAt - sourceEventTime
  (cần chú thích clock skew và source latency)

Residual Access Age =
  thời gian từ desired revoke effectiveAt
  tới khi target đạt verified denied
~~~

**Một tỷ lệ 100% chỉ có nghĩa trong scope và thời điểm đã đo**. Không loại account không owner hoặc ứng dụng connector lỗi khỏi mẫu số mà không công khai.


## 35. Runbook: từ một identity alert tới verified closure

Khi rule phát hiện **quyền vẫn PERMIT sau Leaver**, chuỗi phản ứng nên có các bước:

1. **Nhận và xác thực alert:** Kiểm rule, phiên bản, source events, event IDs, thời điểm, account/subject mapping.
2. **Phân loại severity:** Dựa trên resource, mức quyền, impact và yêu cầu JML; không chỉ tên alert.
3. **Xác minh authoritative state:** HR/VMS effectiveAt, owner, engagement và exception hợp lệ.
4. **Xác định effective path:** IdP, app-local role, direct ACL, PAM/PIM, token/session, API/DB/VPN.
5. **Kiểm sự kiện liên quan:** Login, MFA reset, key issuance, privilege grant, last access.
6. **Quyết định containment:** Người có thẩm quyền đánh giá revoke/disable/terminate session, tránh phá hoạt động hợp lệ ngoài phạm vi.
7. **Thực hiện remediation:** Thay đúng source-of-truth và target grants; dùng workflow có audit.
8. **Readback từ target:** Permission check/negative test an toàn cho action/resource/tenant cụ thể.
9. **Đối chiếu độ trễ:** `requiredEffectiveAt` so với `verifiedAt`; ghi gaps và sự cố telemetry.
10. **Đánh giá regrant:** Kiểm sync/IaC/controller có tái cấp quyền không.
11. **Đóng hoặc giữ exception:** `VERIFIED_CLOSED` chỉ khi có bằng chứng; nếu UNKNOWN/PERMIT, có owner/risk/deadline.
12. **Cải tiến kiểm soát:** Sửa rule, mapping, connector, runbook và training dựa root cause.

**Nếu là security incident nghiêm trọng**, runbook phải phối hợp SOC/incident lead, bảo toàn evidence và ưu tiên giảm thiểu nguy cơ theo chính sách; không biến workflow kiểm toán thành lý do trì hoãn containment.

### 35.1. Giữ sự khác biệt giữa action và evidence

~~~text
Alert created
  -> Owner acknowledged
  -> Investigation completed
  -> Revoke requested
  -> Target updated
  -> Effective access verified
  -> Monitoring closed

Mỗi mốc có actor/time/source/reference riêng.
~~~

Không ghi `closedAt` bằng thời điểm `revokeRequestedAt`.

## 36. Đối soát identity drift bằng truy vấn (SQL minh họa)

Giả sử hệ thống phân tích có bảng:

~~~text
desired_access(subject_id, target_id, entitlement_id,
               desired_state, effective_at, policy_version)
observed_access(subject_id, target_id, entitlement_id,
                observed_state, observed_at, source_ref)
identity_state(subject_id, lifecycle_state, state_effective_at)
~~~

Một truy vấn read-only tìm **quyền đã có desired state REVOKED nhưng target vẫn quan sát ASSIGNED**:

~~~sql
-- Minh họa. Điều chỉnh schema, time validity và grant lineage.
SELECT
    d.subject_id,
    d.target_id,
    d.entitlement_id,
    d.effective_at AS revoke_required_at,
    o.observed_at,
    o.source_ref,
    i.lifecycle_state
FROM desired_access AS d
JOIN observed_access AS o
  ON o.subject_id = d.subject_id
 AND o.target_id = d.target_id
 AND o.entitlement_id = d.entitlement_id
LEFT JOIN identity_state AS i
  ON i.subject_id = d.subject_id
WHERE d.desired_state = 'REVOKED'
  AND o.observed_state = 'ASSIGNED'
  AND o.observed_at >= d.effective_at;
~~~

**Giới hạn:** Kết quả chỉ cho thấy **assigned-state drift** theo dữ liệu và mốc được lấy. Nó không tự chứng minh action thực sự PERMIT; không xử lý tốt nhiều grants cho một permission, event history, policy deny hoặc observed snapshot cũ. Triển khai thật phải chọn **trạng thái mới nhất đúng source/as-of, grant lineage, account mappings, ABAC và token/session**. Không dùng query này để tự revoke production.

### 36.1. Phân loại mismatch

- **Expected propagation window:** Thay đổi đang hội tụ, còn trong giới hạn đã duyệt.
- **Unexpected overrun:** Vượt thời hạn policy.
- **Source-of-truth conflict:** IAM và target đều cho rằng mình có authority khác nhau.
- **Mapping error:** Cùng subject ID bị ánh xạ nhầm account.
- **Direct grant:** Target role không sinh từ catalog.
- **Token/session persistence:** Assigned đã gỡ nhưng effective còn.
- **Monitoring incomplete:** Không đủ chứng cứ để kết luận.

## 37. Test matrix cho identity monitoring

| Test | Kết quả kỳ vọng |
|---|---|
| Leaver effectiveAt trước JWT `exp` | Detect/verify residual access theo policy |
| Mover gỡ group nhưng còn direct ACL | Phát hiện quyền cũ vẫn còn |
| Joiner có quyền production trước effectiveAt | Phân loại có/không có onboarding exception |
| Non-human principal owner Leaver | Review ownership, secret access, không tự xóa workload |
| Local app account không có IdP mapping | Orphan/unknown subject finding |
| Role admin được gán ngoài workflow | Alert actor/target/approval mismatch |
| PIM eligible chưa active | Vẫn được inventory và review |
| PIM activation hết hạn, DB session còn | Privileged session alert theo target |
| SCIM 202 nhưng app chưa áp | Không tự verified success |
| API PERMIT sau role revoke | Residual access finding, safety escalation |
| IdP MFA reset trong incident được duyệt | Triage recognized exception, không auto compromise |
| Service principal API burst theo batch job | Baseline + context giảm false positives |
| Unknown actor trong shared PAM account | Giữ attribution uncertainty và yêu cầu bổ sung |
| CI/CD staging dùng production role | Detect cross-environment workload privilege |
| Leaver có hai engagements, chỉ A hết | Chặn A nhưng không tự gỡ B |
| Directory IaC tái cấp quyền đã revoke | Detect REGRANT_AFTER_REVOKE |
| Token reuse sau hai refresh đồng thời | Alert nhưng triage race vs theft |
| Directory replica lag | Ghi freshness, không kết luận thiếu dữ liệu |
| Collector ngừng 30 phút | MONITORING_GAP và fallback notification |
| Source event gửi trùng | Dedup theo ID/version, không tạo nhiều remediation |
| Source event đến trễ | Dùng sourceEventTime và observedAt riêng |
| Collector schema thay đổi | Dead-letter/parse error alert, không im lặng |
| Log có raw token | Security/privacy control failure |
| Reviewer đã Leaver tự KEEP admin | Invalid reviewer authority finding |
| Account ownerless có quyền high-risk | Ownership/risk escalation |
| Permission test sai tenant | Không được đánh dấu verified đúng scope |
| API target timeout khi kiểm | UNKNOWN, không coi DENY |
| Dashboard báo 100% nhưng app ngoài inventory | Coverage metric công khai giới hạn |
| Revoked role xuất hiện lại | Monitoring phát hiện và truy nguyên nguồn |
| Break-glass khi SIEM lỗi | Fallback/incident evidence và log gap được ghi |

### 37.1. Test đối chứng âm và dương

- **Positive control:** Một hành động hợp lệ, tài nguyên đúng phạm vi được PERMIT khi policy cho phép.
- **Negative control:** Action/resource không còn được phép bị DENY theo quyền hiệu dụng.
- **Collector failure control:** Khi nguồn mất, hệ thống báo UNKNOWN/GAP, không giả vờ không có hoạt động.
- **Replay/dedup control:** Event gửi nhiều lần không tự làm IAM revoke lặp gây outage.

Không dùng thao tác phá hoại như xóa dữ liệu thật để chứng minh authorization; dùng **safe permission check** hoặc môi trường được phê duyệt.

## 38. Những tình huống thực hành

### 38.1. Tình huống A — Nhân viên Leaver vẫn truy cập API

**Bối cảnh:** HR kết thúc engagement lúc 17:00, IdP disabled đúng giờ, nhưng mobile app còn access token JWT tới 17:45. Resource Server chỉ kiểm signature/`exp` và vẫn cho đọc dữ liệu sau 17:00.

**Vấn đề:** Account lifecycle đã cập nhật nhưng **effective API authorization chưa đáp ứng mốc chính sách**.

**Hướng xử lý:** Kiểm JML event/effectiveAt, token validation method, cached roles và target logs. Đánh giá revocation/status enforcement hoặc token TTL/PEP phù hợp; revoke grants/session, kiểm permission DENY bằng test an toàn và lưu propagation latency.

**Bài học:** **Identity monitoring phải nhìn thấy quyền ở Resource Server, không chỉ IdP status**.

### 38.2. Tình huống B — Mover có quyền hai bộ phận

**Bối cảnh:** Người dùng chuyển Sales → Finance, IAM cấp Finance group nhưng app vẫn giữ local Sales export ACL. Dashboard IGA báo Mover complete.

**Hướng xử lý:** So desired/assigned/effective; truy grant source, gỡ ACL không còn căn cứ, kiểm token/session và negative test quyền export cũ. Đồng thời giữ Finance access hợp lệ.

**Bài học:** **Provision quyền mới không thay deprovision quyền cũ**.

### 38.3. Tình huống C — Hai employee records trỏ cùng local account

**Bối cảnh:** Đợt rehire tạo person ID mới. Directory link lỗi khiến hai canonical identities đều map tới một target account; monitoring cho rằng account còn thuộc người ACTIVE.

**Hướng xử lý:** Dùng authoritative identity resolution, lịch sử alias, engagement, target account ID, source timestamps. Không tự hợp nhất chỉ theo email; tạm giữ tình trạng `IDENTITY_MAPPING_CONFLICT` và kiểm quyền trước khi quyết định.

**Bài học:** **Correlation sai có thể che Leaver, tạo attribution sai và phá quyền người khác**.

### 38.4. Tình huống D — MFA reset rồi gán admin role

**Bối cảnh:** Helpdesk reset MFA cho operator lúc 09:05; một phút sau account nhận cloud-admin role, tiếp đó có export credential metadata. Tất cả events đơn lẻ đều có vẻ thành công.

**Hướng xử lý:** Nối event timeline, kiểm proofing/approval, actor đã thực hiện, privileged policy, token issuance và target action. Nếu có compromise, kích hoạt incident response và containment theo thẩm quyền; nếu hợp lệ, ghi căn cứ và cải tiến monitoring.

**Bài học:** **Một chuỗi sự kiện có rủi ro cao hơn từng event riêng lẻ**.

### 38.5. Tình huống E — Workload không owner nhưng cần cho DR

**Bối cảnh:** Service principal `svc-recovery` có quyền cao, dùng một lần mỗi quý để thử disaster recovery. Owner cũ đã nghỉ, dashboard gắn `unused` vì không có last-login gần đây.

**Hướng xử lý:** Tìm service catalog/runbook, dependency, test DR, owner mới và credential rotation. Hạn quyền theo runbook, monitor activation, kiểm service vẫn dùng được hợp lệ. Không xóa tự động chỉ vì hiếm dùng.

**Bài học:** **Giám sát lifecycle của NHI dựa owner/purpose/dependency, không chỉ mức hoạt động**.

### 38.6. Tình huống F — SCIM thành công nhưng account local còn

**Bối cảnh:** Connector gửi `active=false` và nhận 200. App vẫn cho login bằng local password mà không hỏi IdP.

**Hướng xử lý:** Xác minh contract SCIM, app-local account status, authentication paths và target logs. Chặn đường local trái policy, kiểm session/token và readback, ghi discrepancy giữa control plane và data plane.

**Bài học:** **SCIM success không tự chứng minh chặn mọi đường truy cập**.

### 38.7. Tình huống G — Regrant vào ban đêm

**Bối cảnh:** IGA đã revoke group `project-admin` và permission test DENY, nhưng batch sync lúc 02:00 tái gán group từ một file cấu hình cũ.

**Hướng xử lý:** Dùng event correlation từ `REVOKE` tới `ROLE_GRANTED`, xác định automation actor và IaC/source rule. Sửa nguồn cấp, revoke lại và monitor recurrence.

**Bài học:** **Verified revoke chỉ đúng tại mốc đã kiểm; quyền có thể tái xuất hiện nếu nguồn cấp không sửa**.

### 38.8. Tình huống H — PIM hết hạn nhưng DB session vẫn admin

**Bối cảnh:** PIM admin role hết hạn 20:30. PAM connection đóng 20:40, nhưng một direct database session vẫn có thể thay schema lúc 20:45.

**Hướng xử lý:** Kiểm target sessions, revoke grant và credential, thiết kế session termination/recheck tại DB, audit action và verified denial.

**Bài học:** **Privilege activation, broker session và target session là những vòng đời khác nhau**.

### 38.9. Tình huống I — “Impossible travel” do VPN

**Bối cảnh:** Cùng một người login từ IP trông như hai quốc gia trong 5 phút. Người đó đang kết nối qua VPN doanh nghiệp và một mobile network.

**Hướng xử lý:** Kiểm device identity, VPN egress, auth assurance, session lineage, app resource actions. Không tự kết luận compromise hay khóa account nếu chưa đánh giá bối cảnh; nếu có tín hiệu khác mạnh hơn thì escalate.

**Bài học:** **IP location là tín hiệu rủi ro, không phải sự thật định danh**.

### 38.10. Tình huống J — Mất collector nhưng dashboard vẫn xanh

**Bối cảnh:** SIEM collector cho cloud admin audit ngừng hoạt động sau khi token truy cập của collector hết hạn. Dashboard không có alert vì “không có suspicious event”.

**Hướng xử lý:** Giám sát heartbeat, event ingestion rate, API permission errors, dead letters và known test events. Dùng alternate/native audit hoặc protected buffer khi có thể, phục hồi pipeline và đánh dấu thiếu evidence; audit những action trong thời gian gap.

**Bài học:** **Sự vắng mặt của telemetry không phải bằng chứng an toàn**.

### 38.11. Tình huống K — CI/CD tăng quyền bằng workflow

**Bối cảnh:** Một developer không có cloud-admin nhưng có quyền sửa workflow CI/CD dùng service principal production mạnh. Họ thêm bước thay IAM policy và pipeline thực thi.

**Hướng xử lý:** Liên kết human change actor, commit, CI run, workload principal, cloud API event và target policy. Kiểm branch protection/approvals, least-privilege CI role và workload federation subject binding; nếu trái policy, xử lý incident và thu hồi quyền.

**Bài học:** **Danh tính workload có thể truyền đặc quyền gián tiếp cho người sửa automation**.

### 38.12. Tình huống L — Có review đầy đủ nhưng thiếu permission evidence

**Bối cảnh:** Quarterly access review báo 100% decisions, mọi reviewer đã bấm KEEP/REVOKE. Tuy nhiên 15% account app-local không nằm trong inventory, và 10 item REVOKE chưa đọc lại target.

**Hướng xử lý:** Tách `decision completion` khỏi `population coverage` và `verified remediation`, công khai exclusions/unknowns, bổ sung import app-local grants, assign remediation/readback owners và risk escalation.

**Bài học:** **Dashboard hoàn tất review không thay monitoring của quyền hiệu dụng**.

## 39. Dashboard vận hành và báo cáo cho các nhóm

Một dashboard nên phục vụ quyết định cụ thể:

| Nhóm | Thông tin cần xem | Quyết định |
|---|---|---|
| **IAM Ops** | Provisioning failures, JML latency, orphan accounts | Sửa mapping/connector |
| **SOC/Incident** | Risky auth, unusual privilege, token reuse, high-impact actions | Triage/contain theo policy |
| **App/Resource owner** | Target grants, ABAC/policy drift, residual access | Thu quyền hoặc sửa PEP |
| **HR/VMS governance** | Engagement effectiveAt và sự kiện lệch nguồn | Sửa identity/engagement data |
| **PAM/PIM team** | Standing/eligible/active role, session overtime | Revoke/terminate/review |
| **Service owners** | NHI owners, credentials/expiry, workload access | Transfer/rotate/decommission |
| **Audit/Risk** | Coverage, exceptions, verified closure, evidence gaps | Đánh giá control effectiveness |

### 39.1. Không đưa mọi PII lên màn hình chung

Màn hình tổng hợp có thể hiển thị **counts, latency distributions, service/risk tiers**, với khả năng drill-down được kiểm soát tới subject cụ thể. Người không có need-to-know không cần xem toàn bộ lịch sử login hoặc danh sách secret path của đồng nghiệp.

### 39.2. Báo coverage minh bạch

Nếu đang giám sát 80/100 ứng dụng, không báo “100% user lifecycle monitored” dựa trên 80 ứng dụng đó. Nêu **scope coverage**, ứng dụng ngoài phạm vi, đặc quyền chưa quan sát và kế hoạch bổ sung.

## 40. Khả năng phục hồi của identity monitoring

Identity monitoring có thể ngừng hoạt động đúng khi:

- IdP/SSO lỗi diện rộng.
- API target hoặc directory không trả lời.
- SIEM pipeline bị nghẽn.
- Mạng segment mất kết nối.
- Log agent/certificate hết hạn.
- Cloud audit delivery trễ.
- Secret store bị sự cố.
- Emergency access cần chạy ngoài đường quản trị chuẩn.

Một kiến trúc có khả năng phục hồi phải:

1. Có **inventory nguồn telemetry** và các dependency quan trọng.
2. Theo dõi health của collector, queue, auth credential và target API.
3. Duy trì **protected local buffer/native audit** khi có thể.
4. Có **alternative paging/out-of-band channel** khi alerting chính mất.
5. Giữ **time/correlation metadata** để replay an toàn sau khôi phục.
6. Dedup sự kiện khi gửi lại; không tự chạy remediation hai lần.
7. Có thẩm quyền vận hành khi chính IAM/SIEM không sẵn sàng.
8. Đánh dấu **monitoring gap** trong báo cáo audit.
9. Đánh giá các privileged actions diễn ra trong khoảng gap.
10. Diễn tập outage và xác minh phương án fallback thực sự độc lập với thành phần hỏng.

**Không dùng `monitoringDown → ALLOW_ALL` như cơ chế mặc định**. Đường emergency cần policy, scope, thời hạn, actor attribution và post-use review.

## 41. Sai lầm thường gặp khi giám sát identity

| Sai lầm | Vì sao nguy hiểm | Cách sửa |
|---|---|---|
| Chỉ xem successful/failed logins | Bỏ qua grant, token, local account | Quan sát toàn identity/authorization lifecycle |
| Dùng email làm canonical ID | Rename/reuse gây mapping sai | Stable subject/account IDs + history |
| Tin `SCIM success` là full revoke | App-local session/ACL còn | Target readback/RS checks |
| Chỉ nhìn group, bỏ direct ACL | Quyền còn qua nguồn khác | Grant lineage + target inventory |
| Chỉ nhìn PIM active, bỏ eligible | Vẫn có khả năng kích hoạt | Review cả eligible/standing/JIT |
| Giữ token raw trong log | Credential leakage | References, redaction, access control |
| Không đo collector silence | Điểm mù không được phát hiện | Health SLI, heartbeat, gap alert |
| Auto-block mọi anomaly | False positive, có thể gây outage | Risk triage + authorized action |
| Tự kết luận hacker từ IP mới | VPN/NAT/mobile làm sai | Correlate device, JML, actions |
| Tin `review=100%` là safe | Chưa biết target effective access | Tách decisions/remediation/verification |
| Gỡ NHI khi owner Leaver | Có thể phá workload production | Transfer owner, assess credential |
| Giữ orphan NHI vô thời hạn | Privileged shadow access | Owner/risk review và decommission |
| Revoke cùng một quyền mỗi đêm | Source tự regrant | Fix IaC/directory mapping |
| Dùng một timestamp cho mọi bước | Che delay/consistency | Source/observed/applied/verified times |
| Không xử lý multiple engagements | Thu hồi sai quyền hợp lệ | Scope theo engagement/resource |
| Không đo time-to-verify | ACK được nhầm với remediation | Target-deny evidence |
| So snapshot khác `asOf` | False mismatch | Track source freshness |
| Hash file rồi coi population đủ | Integrity ≠ completeness | Census/source reconciliation |
| Rule không có owner | Alert trôi không ai xử lý | Routing, escalation, on-call |
| Đánh dấu UNKNOWN là DENY | Che residual access | Explicit pending verification |

## 42. Câu hỏi tự kiểm tra

**Câu 1.** Identity monitoring khác access review ở đâu?

**Gợi ý:** Monitoring phát hiện trạng thái/sự kiện/rủi ro liên tục; review đưa quyết định business về quyền; cả hai cần nối với remediation và verification.

**Câu 2.** Vì sao disabled account ở IdP không bảo đảm API đã từ chối mọi access token?

**Gợi ý:** JWT tự chứa, app-local sessions và token cache có lifecycle riêng; Resource Server phải thực thi theo policy.

**Câu 3.** Human actor khác workload subject thế nào?

**Gợi ý:** Người có thể kích hoạt CI/CD job; cloud API thấy service principal, cần correlation job/actor/change.

**Câu 4.** Mover đã thêm role mới nhưng chưa gỡ direct ACL cũ; monitoring cần báo gì?

**Gợi ý:** Privilege accumulation và effective access drift; kiểm target action và grant source.

**Câu 5.** Vì sao Leaver cần `effectiveAt` thay vì chỉ biết event được nhận lúc mấy giờ?

**Gợi ý:** Mốc policy cho phép xác định quyền phải mất từ lúc nào, từ đó đo latency/violation.

**Câu 6.** Dựa vào IP location có thể kết luận một tài khoản bị chiếm không?

**Gợi ý:** Không; IP là tín hiệu, cần device/assurance/session, VPN và target action context.

**Câu 7.** Service principal owner Leaver có nên tự xóa?

**Gợi ý:** Không tự động; transfer ownership, kiểm dependency, gỡ quyền người và rotate credential theo rủi ro.

**Câu 8.** PIM eligible nhưng không active có cần inventory/review không?

**Gợi ý:** Có, vì quyền kích hoạt đặc quyền vẫn tồn tại.

**Câu 9.** Tại sao monitoring không thể chỉ dựa SCIM PATCH response?

**Gợi ý:** Không bao trùm app-local ACL, token, session, asynchronous apply và effective enforcement.

**Câu 10.** Nếu source không gửi events trong 30 phút, kết luận an toàn là gì?

**Gợi ý:** Telemetry gap/unknown, không phải không có hoạt động.

**Câu 11.** Một API permission-check cho DENY có đủ chứng minh mọi target đều đã revoke không?

**Gợi ý:** Chỉ chứng minh trong scope/action/resource/context/time đã kiểm.

**Câu 12.** Vì sao cần `grantSourceRef`?

**Gợi ý:** Để tìm role/group/direct ACL/policy thực sự cấp quyền và sửa nguồn tái cấp.

**Câu 13.** Alert ACK khác VERIFIED_CLOSED như thế nào?

**Gợi ý:** ACK chỉ có người nhận; verified closure cần bằng chứng policy/target state.

**Câu 14.** Vì sao nên kết hợp event streaming và reconciliation?

**Gợi ý:** Streaming nhanh nhưng có thể mất event; reconciliation bắt drift ngoài workflow nhưng có độ trễ.

**Câu 15.** Mất credential collector khiến dashboard không có alert, đây có phải chứng minh không có login nguy hiểm?

**Gợi ý:** Không; đây là lỗi monitoring health.

**Câu 16.** Một recovery workload lâu không login có thể là tài khoản dư thừa không?

**Gợi ý:** Có thể, nhưng phải kiểm mục đích, owner, DR dependency và security scope trước khi quyết định.

**Câu 17.** Token/credential rotation có tự thu hồi vai trò admin ở target không?

**Gợi ý:** Không; xác thực, token lifetime và authorization grant là các lớp khác nhau.

**Câu 18.** Vì sao phải đo `verifiedRevocationLatency` thay vì chỉ thời gian gửi lệnh gỡ group?

**Gợi ý:** Người dùng có thể tiếp tục quyền qua cache/token/direct ACL sau connector ACK.

## 43. Checklist triển khai giám sát identity

- [ ] **Scope:** Đã liệt kê HR/VMS, IdP/SSO, directory, SCIM, IAM/IGA, PAM/PIM, app, cloud, DB, workload?
- [ ] **Canonical identity:** Person/workload ID và mapping account có nguồn tin cậy?
- [ ] **Actor attribution:** Ghi đúng actor người/job và account tại target?
- [ ] **Lifecycle:** Joiner/Mover/Leaver events có effectiveAt và engagement scope?
- [ ] **Joiner:** Phát hiện business access trước start date nếu không có exception?
- [ ] **Mover:** So desired entitlement trước/sau, kiểm quyền cũ và direct ACL?
- [ ] **Leaver:** Không chờ access review/timeout nếu policy yêu cầu revoke sớm?
- [ ] **Contractor/guest:** Sponsor, trust issuer, multiple engagements và tenant mapping?
- [ ] **NHI:** Service principal, OAuth client, CI/CD, K8s có owner/purpose/credential reference?
- [ ] **Credential:** Key/secret/certificate issuance, rotation, exposure có telemetry?
- [ ] **Authentication:** Login, MFA enrollment/reset, SSO/federation, recovery được giám sát?
- [ ] **Privilege:** Standing/JIT/eligible rights, PAM sessions, direct admin path?
- [ ] **Authorization:** Role/group/direct ACL, ABAC policy và action/resource decisions?
- [ ] **Session/token:** IdP logout, app session, JWT, refresh grants, PAT/API keys được phân biệt?
- [ ] **Population/coverage:** Có inventory target và chủ thể ngoài IGA?
- [ ] **Correlation:** Event/source/canonical IDs, grant provenance, job/run/request IDs?
- [ ] **Time:** Dùng UTC/offset, sourceEventTime, observedAt, appliedAt, verifiedAt?
- [ ] **Freshness:** Có đo ingest lag, source last seen và độ mới snapshot?
- [ ] **Rule quality:** Rule có version, owner, test, scope, risk và false-positive analysis?
- [ ] **Alert lifecycle:** Có triage/routing, escalation, authorized remediation và evidence?
- [ ] **Monitoring health:** Collector silence, schema errors, API permissions, dead-letter và replay?
- [ ] **Residual access:** Target permission-check theo scope, không chỉ connector success?
- [ ] **Readback:** Denied/Allowed/Unknown/PartiallyVerified được phân biệt?
- [ ] **Regrant:** Có phát hiện directory sync/IaC/controller tái cấp?
- [ ] **SoD:** Có kiểm self-approval/privileged role và reviewer authority?
- [ ] **Governance:** Overdue review, expired exception, ownerless account được xử lý?
- [ ] **Privacy:** Không log raw token/OTP/password, phân quyền truy cập telemetry?
- [ ] **Integrity:** Có provenance, versioning, chống sửa/xóa theo threat model?
- [ ] **Outage/fallback:** Có phương án native log và thông báo khi IAM/SIEM gặp sự cố?
- [ ] **Metrics:** Đo coverage, JML-to-target latency, verified revocation, false positives?
- [ ] **Tests:** Có kịch bản Leaver JWT, Mover ACL, PAM session, collector outage, regrant?
- [ ] **Exceptions:** Mọi UNKNOWN/PERMIT trái policy có owner, risk, deadline và mitigation?
- [ ] **Audit:** Có thể tái dựng quyết định/alert/remediation và target evidence?
- [ ] **Kết quả:** Giám sát trả lời được **ai/điều gì có quyền thực tế vào đâu, khi nào, vì sao và đã bị chặn đúng policy hay chưa**?

## 44. Kết luận

**Giám sát identity** là kiểm soát quan trọng để duy trì sự phù hợp giữa **danh tính, tài khoản, quyền, session/credential và trạng thái thực tế của hệ thống**. Nó không chỉ thu login logs mà còn theo dõi **HR/VMS engagement, IdP/SSO/MFA, directory, SCIM, RBAC/ABAC/PBAC, PAM/PIM, service principals/workloads, API authorization, owner, review và evidence**.

Một thiết kế vững phải kết hợp **event-driven signals** với **reconciliation định kỳ**, định danh actor/subject/target đủ tin cậy, phát hiện **drift và residual access**, bảo vệ tính sẵn có/toàn vẹn của telemetry, cùng **alert triage có người chịu trách nhiệm**. Sự vắng mặt của event, một role bị xóa ở IGA hoặc một ticket đã đóng không chứng minh kiểm soát đã hiệu quả.

Trong **Joiner–Mover–Leaver**, người mới phải được cấp quyền đúng thời điểm, người đổi vai trò phải mất quyền cũ, và người rời tổ chức phải bị chặn theo mốc policy. Đối với **non-human identity**, ownership, credential và lifecycle của workload cần theo dõi riêng với người tạo. **Quyền truy cập tồn dư chỉ được coi đã xử lý khi hành động tại target không còn được phép trong phạm vi cần kiểm và có evidence đáng tin**, hoặc phần chưa xác minh được ghi là ngoại lệ có owner/rủi ro/đường khắc phục.

**Một hệ thống identity monitoring đáng tin không chỉ phát hiện “có chuyện bất thường”, mà có thể nối từng tín hiệu với nguồn danh tính, căn cứ quyền, người chịu trách nhiệm, hành động xử lý và bằng chứng rằng trạng thái truy cập cuối cùng đã đúng chính sách.**
