# Báo cáo monitoring trong IAM: đo vòng đời danh tính, quyền hiệu lực và rủi ro tồn dư

**Báo cáo monitoring (monitoring reporting)** trong Identity and Access Management (IAM) là quá trình **tổng hợp các tín hiệu về danh tính, xác thực, cấp quyền, sử dụng quyền và thu hồi quyền** thành bằng chứng có thể giải thích, so sánh, theo dõi và dẫn tới hành động. Mục tiêu không chỉ là xuất biểu đồ số tài khoản hay số lần đăng nhập, mà là trả lời: **“Ai đang có quyền gì, tại sao, quyền đó có còn hợp lệ theo vòng đời, và hệ thống đích thực sự thực thi quyết định nào?”**

Bài **“Báo cáo monitoring”** thuộc chương **Identity monitoring**, trong module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Phạm vi module gồm quản lý vòng đời danh tính theo **Joiner–Mover–Leaver (JML)**, từ xác minh danh tính, tạo account và cấp quyền, đến rà soát và thu hồi khi vai trò thay đổi; liên kết **HRIS, IGA, IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, token, kiểm toán** và việc giảm **quyền truy cập tồn dư**. Do đó, báo cáo phải nối được **sự kiện nghiệp vụ → yêu cầu thay đổi → thực thi → trạng thái thực tế → bằng chứng kiểm chứng**.

**Tình huống mở đầu:** HRIS ghi nhận 100 Leaver trong tuần. IGA báo 100 quy trình offboarding hoàn tất. Nhưng 8 tài khoản SaaS chưa có target readback, 2 access tokens cũ vẫn được một API chấp nhận và 3 service credentials do nhân viên cũ quản lý chưa chuyển owner. Một dashboard chỉ hiển thị **“100% Leaver completed”** là sai nếu định nghĩa “completed” là **không còn quyền hiệu lực trên các target bắt buộc**. Báo cáo tốt phải hiển thị đồng thời **workflow completion**, **verified revocation coverage**, **unverified exposure**, **residual ALLOW** và **người chịu trách nhiệm khắc phục**.

## 1. Báo cáo monitoring là gì và khác những hoạt động lân cận ra sao?

| Hoạt động | Câu hỏi chính | Đầu ra |
| --- | --- | --- |
| **Monitoring** | Hệ thống IAM đang hoạt động/thay đổi thế nào? | Sự kiện, số đo, tình trạng liên tục. |
| **Alerting** | Có điều kiện vượt ngưỡng hoặc vi phạm cần can thiệp ngay không? | Cảnh báo/incident có owner. |
| **Dashboard** | Những xu hướng và tình trạng cần xem nhanh là gì? | Biểu đồ, bảng, bộ lọc, drill-down. |
| **Monitoring report** | Trong kỳ đo, rủi ro, SLA, hiệu quả kiểm soát và việc cần làm là gì? | Báo cáo có định nghĩa chỉ số, nguồn, bằng chứng và quyết định. |
| **Audit evidence** | Có bằng chứng tin cậy cho một hành động hoặc kiểm soát cụ thể không? | Event, approval, trạng thái đích, kết quả PEP/probe. |
| **Access review/certification** | Quyền được cấp còn cần thiết và đã được owner xác nhận không? | Quyết định KEEP/REVOKE/EXCEPTION và kết quả thực thi. |
| **Incident response** | Rủi ro đã được kiềm chế và xử lý chưa? | Timeline, containment, remediation và verification. |

**Một chỉ số trong báo cáo không phải bằng chứng độc lập** nếu mẫu số sai, nguồn log thiếu hoặc diễn giải sai trạng thái. Báo cáo nên cho phép đi từ **số tổng hợp** tới **nhóm dữ liệu, phép tính, evidence references và thời điểm quan sát**, nhưng vẫn tuân thủ quyền riêng tư.

### Ba lớp thông tin phải tách biệt

1. **Desired state:** HRIS/IGA và chủ sở hữu nghiệp vụ yêu cầu tài khoản/quyền nên có trạng thái nào.
2. **Applied/configured state:** IdP, directory, SCIM, SaaS, API gateway hoặc DB ghi nhận đã tạo, sửa, disable hay xóa grant.
3. **Effective access:** Resource Server/Policy Enforcement Point (PEP) thực tế **ALLOW/DENY** đối với hành động/tài nguyên đã xác định.

**Applied không tự động bằng effective.** SCIM trả 204, IdP xóa group hoặc OAuth AS revoke refresh token không đủ chứng minh access token, local ACL, SaaS PAT hoặc DB session cũ đã mất hiệu lực.

## 2. Báo cáo phục vụ ai và họ cần quyết định gì?

| Nhóm người đọc | Câu hỏi và quyết định | Nhịp xem phù hợp |
| --- | --- | --- |
| **IAM Operations** | Connector nào lỗi, provisioning nào trễ, deprovision nào còn pending? | Gần thời gian thực; hàng ngày. |
| **SOC/Incident Response** | Có Leaver còn truy cập, bất thường privilege escalation, token misuse? | Alert tức thời và báo cáo sự cố. |
| **Application/Data Owner** | Ai còn quyền nhạy cảm trên app/dataset, ai phải review? | Theo risk; tuần/tháng/chiến dịch. |
| **HR/People Operations** | JML events đã khớp danh tính/tài khoản được quản trị chưa? | Hàng ngày, theo đợt onboarding/offboarding. |
| **Compliance/Auditor** | Chính sách, approval, SoD và bằng chứng thu hồi có đầy đủ không? | Theo kỳ kiểm toán; cần snapshot tái lập. |
| **CISO/Risk Committee** | Xu hướng residual access, privileged exposure, control coverage, ngoại lệ quá hạn? | Tháng/quý; ưu tiên rủi ro. |
| **Engineering/SRE** | IdP, SCIM, token service, PDP/PEP hoạt động và đáp ứng SLO không? | Liên tục, theo incident/change. |
| **Owner service accounts** | Workload nào orphaned, secret sắp hết hạn, JIT grants còn tồn dư? | Theo risk và vòng đời ứng dụng. |

Không gửi mọi thông tin chi tiết về danh tính hoặc xác thực cho mọi vai trò. **Executive view** nên có xu hướng, mức rủi ro, coverage và action owners; **analyst/auditor view** có bằng chứng theo quyền truy cập được phân cấp.

## 3. Câu hỏi nghiệp vụ phải định nghĩa trước khi chọn KPI

Một báo cáo có ích bắt đầu từ **quyết định** cần hỗ trợ:

- **Joiner:** người đủ điều kiện đã được kích hoạt đúng ngày, đúng quyền, không bị cấp sớm hay thiếu quyền thiết yếu?
- **Mover:** quyền cũ có bị gỡ và quyền mới có đúng phê duyệt, không tạo chồng lấn SoD?
- **Leaver:** tất cả target bắt buộc đã chặn quyền trong SLA, hay vẫn có tài khoản/tokens/sessions tồn dư?
- **Authorization:** các action nhạy cảm có đi qua RBAC/ABAC/SoD/PEP; có ALLOW ngoài entitlement không?
- **Authentication:** IdP/SSO/MFA có hoạt động; có rủi ro user bị khóa, MFA fatigue hoặc token misuse?
- **Access review:** chủ sở hữu đã xác nhận quyền; quyết định REVOKE có được thực thi và kiểm chứng không?
- **Non-human identity:** service principal/batch/CI-CD có owner, scope, credential expiry và môi trường tin cậy phù hợp?
- **Reliability:** có target thiếu log, connector retry quá lâu, event đến trễ hay identity mapping chưa xác minh?
- **Audit/privacy:** có thể tái lập bằng chứng mà không đưa credential, dữ liệu cá nhân nhạy cảm vào báo cáo không?

### Từ câu hỏi tới chỉ số

~~~text
Câu hỏi:
  Sau Leaver, còn quyền truy cập dữ liệu khách hàng không?

Phạm vi:
  Tất cả HRIS Leavers effective trong tuần.
  Tất cả target/app/resource path bắt buộc theo access inventory.

Đơn vị:
  (subject lifecycle epoch, target, entitlement, protected access path).

Bằng chứng:
  Leaver effectiveAt + IdP/SCIM applied state
  + target readback + API/PEP DENY + no forbidden side effects.

Báo cáo:
  verified in SLA, verified late, still ALLOW,
  pending, unverified, approved exception; owner và deadline.
~~~

**Không bắt đầu bằng biểu đồ “login failures theo ngày” rồi đoán biểu đồ đó đại diện mức an toàn của offboarding.** Login failure hữu ích nhưng không trả lời câu hỏi **user Leaver còn được API chấp nhận token hay không**.

## 4. Chuỗi hệ thống cần được quan sát trong IAM lifecycle

~~~mermaid
flowchart LR
    HR["HRIS / lifecycle events"] --> IGA["IGA / desired rights + approvals"]
    IGA --> IDP["IdP / SSO / directory"]
    IGA --> CON["SCIM / app provisioning"]
    IDP --> AS["OAuth AS / token & session"]
    CON --> APP["SaaS / ERP / local grants"]
    AS --> PEP["API / PEP / PDP"]
    APP --> PEP
    HR --> PIPE["Monitoring collection"]
    IGA --> PIPE
    IDP --> PIPE
    CON --> PIPE
    APP --> PIPE
    AS --> PIPE
    PEP --> PIPE
    PIPE --> NORM["Schema validation + identity mapping"]
    NORM --> STORE["Protected event and state store"]
    STORE --> REPORT["Reports / dashboards / alerts"]
    REPORT --> ACTION["Owners / remediation / audit"]
~~~

### Vai trò của mỗi nguồn

| Nguồn | Dữ liệu cung cấp | Điều không chứng minh được một mình |
| --- | --- | --- |
| **HRIS** | Joiner/Mover/Leaver effectiveAt, employment/contract status. | Target account đã tạo/thu hồi quyền. |
| **IGA** | Access request, approval, entitlement delta, review, desired state. | Target đã thực sự áp quyền. |
| **IdP/SSO** | Authentication, MFA, account/group, sessions, risk. | Tất cả SaaS local accounts/API sessions hết hiệu lực. |
| **OAuth AS** | Token issuance, refresh, grant revoke, client identity. | Mọi JWT đã phát bị RS từ chối tức thời. |
| **SCIM connector** | Provision/revoke request, ACK, retry, target account ref. | API đích không còn nhận token hoặc local PAT. |
| **Target SaaS/DB** | Account status, direct roles/ACL, keys, grant readback. | Mọi endpoint/worker đã enforce DENY. |
| **API/PDP/PEP** | AUTHZ_ALLOW/DENY, policy version, action/resource, session context. | Business transaction đã commit nếu chỉ có ALLOW. |
| **Business ledger/audit** | Transaction commit, export file, payment approval effects. | Toàn bộ hành vi không được log ở hệ khác. |
| **Service/CI/CD/PAM** | Workload trust, privileged activation, credential/key lifecycle. | Owner nhân sự còn active hoặc không có đường privilege khác. |

**Không có telemetry hoặc không có target inventory là một trạng thái cần báo cáo**, không được tự coi missing = no risk.

## 5. Thiết kế dữ liệu: event, snapshot và evidence là ba lớp khác nhau

Một nền tảng reporting hiệu quả thường cần:

1. **Event stream:** ghi nhận những gì đã xảy ra với eventId, provenance, occurredAt, observedAt, phiên bản schema.
2. **State snapshots:** giá trị desired/current của subject/grant/account/policy tại thời điểm chụp; cần watermark và version.
3. **Verification evidence:** target readback, API negative probe, positive control, no-side-effect proof, verifiedAt.
4. **Reference catalog:** danh sách nguồn/target bắt buộc, policy, owner, data classification, risk tier và SLA.
5. **Historical/temporal identity mapping:** link subject HRIS/IdP/SCIM/app theo khoảng hiệu lực.
6. **Reporting facts/dimensions:** dữ liệu đã chuẩn hóa phục vụ cohort, KPI và truy vết nguồn.

### Phân biệt các trạng thái

~~~mermaid
flowchart TD
    A["HRIS / IGA desired-state change"] --> B["REQUESTED"]
    B --> C["APPROVED / SCHEDULED"]
    C --> D["APPLIED by connector / AS / target"]
    D --> E["TARGET READBACK CONFIRMED"]
    E --> F{"Effective authorization evidence?"}
    F -->|DENY for removed action, target healthy| G["VERIFIED_REVOKED"]
    F -->|Still ALLOW| H["RESIDUAL_ACCESS / REMEDIATION"]
    F -->|No proof / timeout / unknown| I["UNVERIFIED"]
    B --> J["FAILED / RETRY / EXCEPTION"]
    C --> J
    D --> J
~~~

**Không áp dụng sơ đồ trạng thái một cách máy móc cho mọi provider:** có target chỉ hỗ trợ một phần readback/probe. Báo cáo phải khai báo **capability/coverage limitations** rõ ràng; không đổi tên UNVERIFIED thành SUCCESS để đạt KPI.

## 6. Data contract của event dùng cho báo cáo

Mẫu event có thể gồm:

~~~json
{
  "schemaVersion": "iam-monitoring-event.v1",
  "eventId": "evt-0421",
  "eventType": "ACCESS_REVOKE_APPLIED",
  "sourceSystem": "finance-erp-connector",
  "occurredAt": "2026-11-23T02:05:00Z",
  "observedAt": "2026-11-23T02:05:09Z",
  "correlationId": "corr-leaver-884",
  "causationId": "jml-leaver-884",
  "operationId": "op-revoke-445",
  "attemptId": "attempt-2",
  "actor": {
    "type": "WORKLOAD",
    "authority": "corporate-iga",
    "subjectRef": "iga-connector-prod"
  },
  "affectedSubject": {
    "type": "HUMAN",
    "authority": "corporate-idp",
    "tenantRef": "tenant-vn",
    "subjectRef": "person-884"
  },
  "targetRef": "finance-erp",
  "targetAccountRef": "finance-user-561",
  "entitlementRef": "payment.create",
  "lifecycleRevision": 42,
  "effectiveAt": "2026-11-23T02:00:00Z",
  "status": "APPLIED",
  "policyVersion": "finance-v7",
  "evidenceRef": "ev-445-apply",
  "rawCredentialLogged": false
}
~~~

**Đây là schema minh họa, không phải chuẩn OpenTelemetry/SCIM/SIEM chung.** Khi triển khai cần chính thức hóa mỗi enum, mandatory field, producer authority, timestamp precision, retention và backward compatibility.

### Những fields không được gộp

| Cặp trường | Lý do phải tách |
| --- | --- |
| **actor / affectedSubject** | Connector là người thực thi, nhân viên là chủ thể được thay đổi quyền. |
| **requester / beneficiary / approver** | Access request có thể do người A xin cho người B, người C duyệt. |
| **operationId / attemptId** | Một revoke logic có thể retry nhiều lần. |
| **occurredAt / observedAt** | Ingestion delay không thay thời điểm sự kiện. |
| **effectiveAt / appliedAt / verifiedAt** | SLA bắt đầu theo quyền cần hiệu lực, kết thúc khi có proof tại target. |
| **policyDecision / businessCommit** | API ALLOW không tự xác nhận payment/export đã commit. |
| **subjectId / email** | Email thay đổi, có alias hoặc tái sử dụng; stable ID có authority. |
| **target config / PEP outcome** | Role gỡ khỏi group không đồng nghĩa token cũ đã bị chặn. |

## 7. Định danh và scope: không join dữ liệu bằng email hoặc IP

Identity mapping là nền tảng của báo cáo monitoring đáng tin. Một employee có thể có nhiều IdP identities, SaaS accounts, workload ownership và aliases. Một account legacy có thể không liên kết được với HRIS, khi đó phải **UNVERIFIED_MAPPING**.

| Hệ thống | Khóa/namespace nên dùng | Kiểm chứng |
| --- | --- | --- |
| **HRIS** | HR authority + immutable person/workforce ID + employment epoch. | HR event revision/effectiveAt. |
| **OIDC/IdP** | Issuer + subject ID + tenant/sector context theo contract. | IdP mapping và provenance; có thể có pairwise sub. |
| **SAML** | IdP entity + NameID format + SP mapping; ưu tiên identifier bền vững. | Không dùng transient NameID như ID bất biến. |
| **SCIM SaaS** | Target system + tenant + SCIM id; externalId với provenance khi có. | SCIM provisioning link được xác minh. |
| **Legacy app** | App namespace + local account ID + valid interval. | Manual/connector verified mapping. |
| **Service principal** | Trust domain + immutable workload/client principal ID. | Owner, app/team và role bindings riêng. |
| **Device** | Device authority + verified immutable device ref. | MDM/EDR/trust evidence; device không phải người. |

### Tương quan theo thời gian

~~~text
identityLink:
  canonicalSubjectRef: person-884
  sourceAuthority: corporate-idp
  sourceSubjectRef: oidc-sub-152
  targetSystem: finance-erp
  targetTenant: tenant-vn
  targetAccountRef: finance-user-561
  validFrom: 2026-01-12T00:00:00Z
  validTo: 2026-11-23T02:00:00Z
  verificationStatus: VERIFIED
  mappingEvidenceRef: link-991
~~~

Đây chỉ là dữ liệu mô phỏng. **Không dùng mapping hiện tại để tự gắn log lịch sử cho một nhân viên được tuyển lại có cùng email.** Khi tính cohort JML, cần phân biệt **person identity**, một giai đoạn employment và **account epoch**; tất cả phải được ánh xạ theo authority và thời điểm.


## 8. Thời gian: kỳ báo cáo, event time, watermark và snapshot

Báo cáo hằng ngày/tuần/tháng phải mô tả chính xác **kỳ đo, timezone, thời điểm chốt dữ liệu (as-of), cách xử lý late events và policy version**.

| Thời điểm | Ý nghĩa | Dùng để làm gì |
| --- | --- | --- |
| **effectiveAt** | Mốc chính sách/HRIS yêu cầu quyền bắt đầu hoặc kết thúc hiệu lực. | Tính SLA JML và quyền tồn dư. |
| **occurredAt** | Producer báo sự kiện xảy ra. | Dựng timeline sự kiện, có clock uncertainty. |
| **observedAt/ingestedAt** | Collector nhận sự kiện. | Tính ingestion delay và phát hiện event đến trễ. |
| **appliedAt** | Thay đổi đã được áp ở source/target theo semantics. | Đo connector provisioning, khác PEP verification. |
| **verifiedAt** | Target/PEP đã có bằng chứng thực thi đúng yêu cầu. | Tính verified revoke latency. |
| **reportPeriodStart/End** | Cửa sổ chọn cohort hoặc events. | Giữ nhất quán mẫu số. |
| **dataAsOf** | Thời điểm snapshot dữ liệu mới nhất đã dùng. | Giải thích báo cáo tạm thời/chốt. |
| **generatedAt** | Thời điểm chạy job tổng hợp. | Audit sản xuất báo cáo, không thay as-of. |

### Kỳ báo cáo không đồng nghĩa thời điểm hoàn tất

Giả sử Leaver có effectiveAt vào **23:59 cuối tháng**, còn target được verify DENY lúc **00:05 đầu tháng kế tiếp**. Báo cáo theo **Leaver effectiveAt cohort** phải giữ subject đó trong mẫu số tháng trước và cập nhật kết quả **verified late/within SLA** theo policy. Không chuyển subject sang tháng sau chỉ vì verifiedAt nằm ở tháng sau.

### Timezone và dữ liệu đến muộn

- Lưu timestamps theo UTC/offset rõ và hiển thị timezone theo nhu cầu người đọc; công bố timezone của báo cáo.
- Dùng half-open interval: **start <= effectiveAt < end** để không đếm trùng biên kỳ.
- Dữ liệu đến trễ có thể cần **provisional report** và **finalized snapshot** sau watermark/cutoff công bố.
- Báo cáo đã phát hành cần có **reportVersion**, snapshot hash/reference và correction/appendix thay vì âm thầm thay số lịch sử.
- Khi đồng hồ producer lệch hoặc độ phân giải kém, nêu **clock uncertainty**; không báo SLA chính xác tới millisecond một cách giả tạo.
- Rehire hoặc một subject có hai employment epochs trong cùng kỳ cần dùng khóa cohort đúng.

## 9. Danh mục báo cáo monitoring theo trường hợp sử dụng

| Report | Câu hỏi chính | Đơn vị và bằng chứng quan trọng |
| --- | --- | --- |
| **Identity inventory** | Có bao nhiêu human/non-human identities, trạng thái/owner ra sao? | Principal/account IDs, owner, mapping, last reviewed. |
| **Joiner activation** | Người mới được cấp đúng quyền, đúng thời điểm không? | Joiner epoch × required target, effectiveAt và verified ALLOW. |
| **Mover entitlement delta** | Quyền cũ đã gỡ, quyền mới đúng approval chưa? | Subject × target × entitlement, SoD và PEP checks. |
| **Leaver deprovision** | Còn account/token/PAT hiệu lực sau offboarding? | Leaver cohort × required access paths, verified DENY. |
| **Access request/approval** | Quyền được cấp đúng thẩm quyền và đúng scope? | RequestItem, decision, role snapshot, target readback. |
| **Access review** | Quyền được xác nhận lại/thu hồi theo review? | ReviewItem, reviewer/decision và execution evidence. |
| **Privileged access/JIT** | Privileged grants có TTL, SoD, session audit và revoke? | Activation × target, approval và target DENY sau expiry. |
| **Authentication/SSO/MFA** | Lỗi đăng nhập, MFA fatigue, step-up, risky sessions? | Authentication events, IdP health, reason codes. |
| **Token/session lifecycle** | Token cũ còn dùng được sau revoke/Leaver? | AS grant/token refs + RS decision. |
| **Service/workload identities** | Account phi con người có owner, scope và credential hợp lệ? | Workload principal × target grant/trust. |
| **Connector/SCIM health** | Request/ACK/readback/verification có trễ và lỗi? | Logical operation, attempt, target state. |
| **RBAC/ABAC drift/SoD** | Role/attribute/tenant mismatch hoặc xung đột nhiệm vụ? | Policy evaluation, effective rights, transaction history. |
| **Coverage/data quality** | Target nào không có telemetry/probe hoặc mapping đáng tin? | Approved target catalog × observed coverage. |
| **Residual access/incidents** | Những đường đã bị yêu cầu thu hồi nhưng còn ALLOW? | Actual PEP outcomes, no-side-effect/commit evidence. |

Không phải báo cáo nào cũng có chu kỳ giống nhau. **Residual ALLOW critical** phải đi qua alert và incident ngay, không chỉ chờ tổng hợp báo cáo cuối tuần.

## 10. Báo cáo Joiner: đúng người, đúng ngày, đúng quyền

Một báo cáo Joiner tốt không chỉ tính số account được tạo; cần xem **activation readiness** và mức độ cấp quyền theo baseline phê duyệt.

### Cohort và các trạng thái

**Cohort:** những Joiner có HRIS employment effectiveAt thuộc kỳ đo, được nối bằng stable subject/employment epoch. **Required targets:** từ chính sách onboarding/role/location/contract, không lấy số tài khoản đã tạo làm mẫu số.

| Trường hợp | Báo cáo cần thể hiện |
| --- | --- |
| Account tạo trước start date để chuẩn bị thiết bị. | PRE_PROVISIONED, không tự coi early provisioning là vi phạm. |
| User được phép truy cập dữ liệu nhạy cảm trước effectiveAt trái policy. | EARLY_ACCESS violation candidate. |
| Joiner ACTIVE, 7/8 target có quyền cần thiết. | PARTIAL_PROVISIONING; target thứ 8 có owner/remediation. |
| SCIM trả 201 nhưng app login chưa hoạt động. | APPLIED_UNVERIFIED; không gọi READY nếu policy cần positive test. |
| User được cấp group admin ngoài approved baseline. | EXCESS_ENTITLEMENT finding, kể cả mọi target khác đã sẵn sàng. |
| Chưa xác minh danh tính/enrollment cần thiết. | IDENTITY_PROOFING/ENROLLMENT_GAP, không báo pass vì account tồn tại. |

### Các KPI gợi ý

- **On-time activation rate:** Joiners có mọi quyền thiết yếu hoạt động theo deadline, không vượt quyền, trên số Joiners có yêu cầu đầy đủ.
- **Missing entitlement instances:** số subject–target–entitlement thiếu so với desired state.
- **Early-access violations:** privileged access được PEP ALLOW trước effectiveAt trái policy.
- **Excess grants:** quyền hiệu lực ngoài baseline/approved exceptions.
- **Time to readiness:** từ thời điểm có đủ eligibility/approval đến verified readiness; định nghĩa clock start tách khỏi thời điểm HRIS tạo bản ghi.
- **Joiner verification coverage:** số required paths đã kiểm được/ tổng required paths.

**Không tối ưu chỉ cho nhanh cấp quyền:** một onboarding “đúng hạn” nhưng vô tình cấp admin toàn tenant là thất bại bảo mật.

## 11. Báo cáo Mover: đối chiếu delta và quyền chồng lấn

Một Mover có ít nhất ba nhóm entitlement: **toRevoke, toKeep và toGrant**. Báo cáo phải đối soát **đúng phần delta**, tránh coi thay role thành công khi old grants vẫn tồn tại.

~~~mermaid
flowchart LR
    HR["HR Role Changed"] --> D["Compute desired delta"]
    D --> REV["Revoke outdated rights"]
    D --> KEEP["Retain still-approved rights"]
    D --> GR["Grant new approved rights"]
    REV --> V["Target readback + effective DENY"]
    KEEP --> V
    GR --> V
    V --> S["SoD, token/session and policy coverage"]
    S --> R["Mover report: verified / partial / residual"]
~~~

### Ví dụ Mover từ Sales sang Finance

| Entitlement | Trước Mover | Desired sau Mover | Phép kiểm |
| --- | --- | --- | --- |
| sales.crm.customer.write | ALLOW | REVOKE | API CRM DENY, kiểm old PAT/local role. |
| sales.analytics.read | ALLOW | KEEP nếu owner xác nhận | Vẫn ALLOW trong phạm vi được duyệt. |
| finance.invoice.read | DENY | GRANT | Finance API ALLOW đúng tenant. |
| finance.payment.approve | DENY | PENDING_APPROVAL | Không tự ALLOW chỉ vì role Finance. |
| cloud.iam.admin | DENY | DENY | Kiểm không có privilege path bất thường. |

### Nhìn SoD đúng

Một người chuyển từ **Payment Creator** sang **Payment Approver** có thể giữ JWT chứa role cũ cho tới expiry nếu RS không kiểm current state. Nếu quyền Approver mới được kích hoạt trong khi Creator cũ vẫn ALLOW, báo cáo phải hiển thị **SoD overlap exposure**. Ngay cả khi role cũ đã gỡ, **transaction-level SoD** vẫn cấm user duyệt payment từng tự tạo.

### KPI gợi ý

- **Mover verified revoke rate** trên các old entitlement paths bắt buộc.
- **Unauthorized overlap duration** của cặp role/action xung đột theo effective access.
- **Wrong grants/failed scope reduction**, kèm approval snapshot.
- **Target convergence latency** từ policy effectiveAt tới actual PEP state.
- **Token/session residual access count**: old role action vẫn ALLOW sau revoke.
- **Unverified mapping/coverage** cho app legacy, không xóa khỏi mẫu số.

**Một event “ROLE_CHANGED” không đủ làm mẫu số chuẩn** nếu nhiều quyền/target cần đổi và một người có nhiều employment/access epochs.

## 12. Báo cáo Leaver: tiêu chí đóng là verified deprovision

Leaver thường là báo cáo rủi ro quan trọng nhất. Cần phân biệt **disable account**, **revoke entitlement**, **terminate/restrict token/session** và **evidence của quyền hiệu lực**.

### Mẫu trạng thái báo cáo theo từng đường truy cập

| Trạng thái | Ý nghĩa | Cách xử lý |
| --- | --- | --- |
| **NOT_STARTED** | Chưa gửi revoke hoặc chưa đến effectiveAt. | Theo deadline/owner. |
| **REQUESTED** | Đã gửi yêu cầu/connector queued. | Theo dõi retries/backlog. |
| **APPLIED** | IdP/SCIM/target nhận thay đổi. | Chưa được báo VERIFIED. |
| **READBACK_CONFIRMED** | Config/grant không còn theo target state. | Cần xác minh token/session/PEP behavior theo capability. |
| **VERIFIED_DENY** | Access path bị thu hồi đã bị PEP từ chối đúng policy, có positive control/no forbidden side effects. | Đếm pass cho path tương ứng. |
| **RESIDUAL_ALLOW** | PEP vẫn cho thực hiện action cũ. | Containment, incident/remediation, SLA risk. |
| **UNVERIFIED** | Không có telemetry/negative proof, target outage hoặc mapping chưa tin cậy. | Đếm coverage gap, không tính success. |
| **EXCEPTION_APPROVED** | Có ngoại lệ được owner/risk approve với scope và expiry. | Báo tách riêng, không hòa vào verified deny. |
| **FAILED** | Connector/target báo lỗi có ý nghĩa. | Escalation và retry theo runbook. |

### Ví dụ tách workflow với security outcomes

~~~text
Leavers effective this week                    : 100
IGA workflows marked completed                : 100
Required target-access paths                  : 420
Paths with verified DENY                      : 405
Paths with residual ALLOW                     : 2
Paths lacking proof / unavailable             : 13

Workflow completion                           : 100/100
Required-path verification coverage           : 405/420
Overall "all required paths verified"         : NOT MET
~~~

**Đây là số liệu giả định để minh họa, không phải số đo hệ thống thật.** Nếu hệ thống chỉ đếm **405 paths verified** nhưng báo “100% Leavers safe”, đó là kết luận vượt quá bằng chứng.

### Leaver có thể liên quan nhiều credential

- IdP/SSO sessions và app-local sessions.
- OAuth access tokens đã phát, refresh grants; JWT có thể còn exp.
- SaaS PAT/API keys không quản lý chung với OAuth.
- VPN, PAM activations, DB roles/session, cloud federation.
- Direct ACL và group-based roles bên ứng dụng.
- Quyền đọc vault, sửa CI/CD/repository cho service credentials.
- Workload chính đang hoạt động hợp lệ nhưng **nhân viên owner** cần bị gỡ quyền và bàn giao.

**Không xóa một workload còn được phê duyệt chỉ vì owner nhân sự nghỉ**, nhưng phải ghi rõ owner mới, quyền cá nhân cũ và nhu cầu rotate credentials.

## 13. Báo cáo về quyền truy cập tồn dư: residual access

**Residual access** là quyền hiệu lực còn tồn tại sau khi một chính sách/event yêu cầu quyền đó không còn, thường do **JWT/session còn hạn, local ACL, cache, connector lag, app-specific PAT, trust stale, mis-provisioning** hoặc đường thực thi không gọi PEP.

### Nguồn tín hiệu cần liên kết

1. **Effective event** từ HRIS/IGA hoặc expiry policy.
2. **Desired revoked permission set** theo subject/target/action/resource.
3. **Connector/IdP/SCIM events** cùng operationId/correlationId.
4. **Target readback** vai trò/credential/account status.
5. **Token issuance/introspection/session events** khi có và được phép.
6. **API/PEP decision** đúng subject, action, tenant và thời điểm.
7. **Business commit outcome** để biết có xảy ra side effect.
8. **Exception/incident state** và owner đúng.

### Phân biệt phát hiện và kết luận

| Phát hiện | Đủ căn cứ để nói gì? |
| --- | --- |
| Leaver còn AUTH_SUCCESS ở IdP. | Có khả năng identity/session policy lệch; cần xác minh subject/authority. |
| API có AUTHZ_DENY sau Leaver. | Đường request đã bị chặn; không phải access thành công. |
| API có AUTHZ_ALLOW sau effectiveAt. | Một path được cho phép theo log; kiểm provenance, business effects, exception và scope. |
| API HTTP 503 khi test. | Không xác minh được authorization; không tính VERIFIED_DENY. |
| SCIM 204 và local PAT vẫn export được. | Quyền tồn dư thực tế trên đường local PAT. |
| Không có log API cả tuần. | Chưa biết API có hành vi hay không, không có nghĩa không còn quyền. |

### Ưu tiên theo rủi ro

Một token read-only cho tài nguyên công khai và một privileged account cross-tenant có quyền xóa dữ liệu không nên được cộng bằng cùng một **“1 residual credential”** trong bảng tổng hợp duy nhất. Nên hiển thị **risk tier, data sensitivity, blast radius, exploitability, duration và owner**, đồng thời giữ count thô để kiểm toán.

## 14. Access request, RBAC/ABAC, SoD và access-review reporting

### Approval-to-effective-right reconciliation

Các thực thể khác nhau cần được báo cáo rõ:

| Đối tượng | Trường cần lưu | Ý nghĩa |
| --- | --- | --- |
| **Access request** | requestId, requester, beneficiary, resource, requested scope. | Nhu cầu ban đầu. |
| **Approval** | approver identity, decision, policyVersion, timestamp. | Quyết định có thẩm quyền. |
| **Approved entitlement snapshot** | roles/actions/tenant, TTL, conditions, version. | Quyền được phép cấp. |
| **Provisioning operation** | operationId, target, status, attempt. | Bước thực thi, có thể retry. |
| **Actual target state** | role membership/direct ACL/current configuration. | Grant đang tồn tại. |
| **Effective authorization** | verified actor/action/resource/context và ALLOW/DENY. | Quyền có được thực thi ở PEP. |
| **Access review item** | reviewer, KEEP/REVOKE/EXCEPTION, dueAt. | Quyền còn hợp lệ không. |
| **Review remediation evidence** | appliedAt, target readback, verifiedAt. | Quyết định REVOKE đã tác động chưa. |

### Các báo cáo cần hỗ trợ

- **Self-approval violations:** requester/beneficiary/approver trùng stable subject khi SoD cấm.
- **Unapproved privileged grants:** có role/quyền tại target nhưng không có approved snapshot tương ứng.
- **Review decisions pending execution:** reviewer chọn REVOKE nhưng connector/PEP chưa DENY.
- **Review coverage & aging:** những items đến hạn/chậm hạn, reviewer delegation và exceptions còn hiệu lực.
- **RBAC role drift:** role cấu hình khác danh mục/phê duyệt.
- **ABAC policy gaps:** PEP không kiểm tenant/resource classification, subject lifecycle hoặc dynamic conditions theo policy.
- **Transaction-level SoD:** nhân viên có role mới nhưng vẫn là người tạo payment lịch sử, không được tự duyệt.

**Quyền đã được reviewer KEEP không tự hợp thức hóa mọi grant phát sinh ngoài approval**, nhất là role admin hoặc quyền trên tenant khác. Đồng thời, một review item REVOKE chưa thực thi cần báo **PENDING_REMEDIATION**, không hòa vào “campaign completed”.


## 15. Báo cáo privileged access, PAM/JIT và vi phạm SoD

Quyền privileged có thể được **kích hoạt ngắn hạn**, nhưng nguồn quyền trực tiếp và session còn sống có thể tồn tại ngoài thời gian yêu cầu. Báo cáo phải dùng **effective privilege**, không chỉ số ticket JIT được phê duyệt.

| Nhóm đo | Dữ liệu | Cảnh báo |
| --- | --- | --- |
| **Standing admin grants** | Principal × target × admin action/grant không có expiry ngắn hạn. | Quyền tồn tại lâu, không owner hoặc không approved. |
| **JIT activation** | Request, approver, scope, start/end, reason, session. | Activation ngoài change window hoặc tự phê duyệt. |
| **JIT expiry enforcement** | Target grant readback và API/role-assumption DENY sau expiry. | Expired in PAM but still ALLOW at target. |
| **Break-glass usage** | Emergency identity, approver/incident, action, reason, post-use review. | Dùng không incident hoặc không có hậu kiểm. |
| **Sensitive credential use** | Secret/key access, token issuance, role assume. | Human owner Leaver vẫn có thể đọc service keys. |
| **SoD** | Creator/Approver, grantor/reviewer, policy editor/auditor. | Một effective controller kiểm soát cả hai nhánh. |
| **Session recording coverage** | Các privileged sessions được yêu cầu có protected audit. | Đường direct API/SSH bypass recording. |

### Số giờ đặc quyền (privilege-hours)

Một metric hữu ích khi có thời gian hiệu lực đáng tin:

\[
\text{PrivilegeHours} =
\sum_i \text{durationHours}(\text{effective grant interval}_i)
\]

Cách đếm phải xác định **overlap**: cùng một principal có hai grants cho cùng action không nhất thiết nên tính gấp đôi thời gian **effective capability**, nhưng cả hai grants vẫn cần báo riêng vì là **hai đường cấp quyền**. Không sử dụng số giờ được **request** thay số giờ quyền thực tế **ALLOW**.

### SoD ở mức quyền kiểm soát

Hai service accounts khác tên vẫn có thể do cùng một admin hoặc pipeline operator điều khiển. Báo cáo SoD cần nhìn **trust/assumeRole graph, người sửa workflow, người đọc secret** và approval authority, không chỉ so usernames. Khi phát hiện nguy cơ, cần owner review có bằng chứng, không tự khẳng định gian lận.

## 16. Báo cáo IdP, SSO, MFA và risk-based access

Nhóm báo cáo xác thực giúp đánh giá **khả dụng, rủi ro và khả năng phục hồi**, nhưng không được đồng nhất đăng nhập thành công với quyền API.

### Các bảng đo có ích

| Metric | Diễn giải đúng | Điểm dễ đo sai |
| --- | --- | --- |
| **Authentication success/failure** | Số authentication attempts theo principal/client, reason code. | Một người có nhiều retries; số failures cao có thể do cấu hình. |
| **MFA enrollment coverage** | Tỷ lệ identities thuộc scope có authenticator đạt policy. | Enrollment không chứng minh factor đã được dùng trong action critical. |
| **Phishing-resistant usage** | Tỷ lệ yêu cầu risk tier cao dùng assurance hợp lệ. | amr=mfa không đủ chứng minh phishing resistance. |
| **Step-up required/completed** | Số challenge phát hành, verified completion, fail/cancel/timeout. | Completion không tự là business authorization ALLOW. |
| **Suspicious sign-in** | Risk engine detections có provenance/time/false-positive review. | IP/địa lý/NAT không đủ kết luận compromise. |
| **SSO login failures by app** | Phân biệt IdP, SP, SAML/OIDC configuration drift. | Không gộp 401 API/403 authz thành IdP auth failure. |
| **Factor recovery/changes** | Thay MFA, password reset, admin recovery, trusted approval. | Recovery có thể là đường bypass assurance. |
| **Session age and revocation** | Session creation/termination, policy current state, active sessions. | Logout IdP không tự giết SP session/JWT đã phát. |

### MFA và step-up trong báo cáo

Một user có thể đã MFA lúc 08:00 nhưng phải reauthenticate bằng WebAuthn lúc 16:00 để duyệt payment. Cần xem **verified authentication time, required assurance, policy version và final PEP decision**, không lấy access token issuedAt hoặc refresh time làm bằng chứng xác thực mới.

Nếu hệ thống thiếu metric về **false-step-up** hoặc **factor recovery friction**, tổ chức có thể tăng challenge mà không tăng bảo mật. Báo cáo cần phân biệt **phishing attempts thật, user cancel, IdP outage, expired challenge, helpdesk recovery**.

## 17. Báo cáo OAuth access token, refresh token và phiên

Trong hệ thống dùng OAuth/OIDC, các thực thể **IdP session, RP session, authorization grant, refresh token và access token** có vòng đời khác nhau. Theo dõi chúng như một mục duy nhất “session revoked” thường gây báo cáo sai.

### Bộ tín hiệu token

- **AS token issuance**: issuer, client, protected subjectRef, audience, scopes, expiry, grantRef, tokenRef nếu có.
- **Refresh grant changes**: issued/rotated/revoked/reuse detected và owner/client context.
- **API JWT validation**: signature/issuer/audience/token type/exp/nbf outcomes, key/JWKS drift.
- **Opaque token introspection**: active/inactive outcomes, cache/availability và fail-safe.
- **Resource authorization**: action, tenant/resource, PEP ALLOW/DENY, current entitlement/policy.
- **Revocation events**: effectiveAt/appliedAt, RS deny evidence, token cache stale, leftover sessions.
- **App-local API keys/PATs**: inventory/revoke riêng nếu nằm ngoài OAuth infrastructure.

### Tách token lỗi với quyền lỗi

| API event | Loại kết quả | Gợi ý báo cáo |
| --- | --- | --- |
| JWT expired/invalid audience. | Authentication/token validation reject. | Lỗi client token flow, token misuse hoặc config. |
| Valid token, insufficient scope. | Authorization DENY. | Scope/grant mismatch theo approved access. |
| Valid token, cross-tenant object. | Resource authorization DENY. | PEP đang chặn; điều tra intent theo context. |
| Valid old token, user Leaver, API vẫn ALLOW. | Residual effective access. | Critical review, containment và evidence. |
| Refresh token revoked nhưng JWT cũ ALLOW. | New issuance blocked, old access remains. | Tách hai bước; đo revocation latency. |
| API 503 khi probe old token. | Target unavailable/unknown. | UNVERIFIED, không coi là DENY. |

**Không ghi raw access/refresh tokens để ghép log**. Dùng protected token references/correlation theo issuer contract và access control, hoặc điều tra bằng controlled test tokens khi có thẩm quyền.

## 18. Báo cáo service accounts và non-human identities

Báo cáo IAM cần bao phủ cả **service principals, CI/CD identities, Kubernetes ServiceAccounts, batch accounts, máy và API clients**. “Không có người dùng tương tác” không đồng nghĩa rủi ro thấp.

| Chỉ số | Đơn vị | Cần kiểm |
| --- | --- | --- |
| **Owner coverage** | Workload principals có business/technical owner còn active. | Owner nhân sự Leaver, chuyển đội; ownerRef cần cập nhật. |
| **Approved need/expiry** | Service identity có purpose, asset owner, review/expiry. | Orphan principal không có application hoặc target. |
| **Broad grants** | IAM roles/API scopes/DB privileges vượt nhiệm vụ. | Effective permission, inheritance/assumeRole và wildcard. |
| **Cross-environment trust** | Dev/staging principal có thể assume prod. | Issuer/subject/branch/namespace trust policy. |
| **Credential posture** | Secret/key/cert age, expiry, rotation và old-key validity. | Rotate mới không revoke token/key cũ tức thời. |
| **Token issuance anomalies** | App-only token ngoài lịch/run, audience/scope lạ. | Job schedule không phải time-bound entitlement. |
| **Decommission verification** | Trust, grants, sessions, PATs và PEP DENY. | Xóa CronJob/VM không tự revoke OAuth client/DB login. |
| **CI/CD control graph** | Ai sửa pipeline/repo/approval và có thể đọc secrets. | Một người điều khiển nhiều service accounts gây SoD conflict. |
| **Batch reliability** | Expected runs, actual runs, retries, duplicate/timeout. | Missed run có thể bỏ sót nghiệp vụ dù quyền vẫn đứng. |

### Human owner Leaver khác workload Leaver

Nếu nhân viên sở hữu job nghỉ việc, **không tự xóa batch account đang phục vụ công việc hợp lệ**. Phải chuyển ownership, gỡ quyền repo/vault/CI/CD của người cũ, đánh giá secret rotation và xác minh service vẫn hoạt động đúng scope. Báo cáo cần **hai chiều:** human access revoked và workload continuity maintained.

## 19. Báo cáo SCIM, provisioning connectors và reconciliation

Một connector có thể **ACK** thao tác thành công nhưng target không thay đổi hoặc role/token khác vẫn còn. Cần tách độ tin cậy vận hành với quyền thực tế.

### Funnel theo logical operation

~~~mermaid
flowchart LR
    R["Approved operation"] --> S["Sent to connector"]
    S --> A["Target ACK"]
    A --> B["Target readback"]
    B --> V["PEP verification"]
    V --> C["Completed with evidence"]
    S --> F["Failure / Retry / DLQ"]
    A --> F
    B --> F
    V --> F
~~~

| Metric | Định nghĩa | Cảnh báo |
| --- | --- | --- |
| **Queue lag** | Thời gian chờ từ eligible operation đến lần dispatch đầu. | Không tính pending approvals là connector lag. |
| **Attempt rate** | Số attempts cho một logical operation. | Retry count không được xem thành nhiều revoke requests. |
| **HTTP 429/5xx by target** | Rate limiting/network/provider errors. | Không auto-classify 404/409 cho mọi provider; xem semantics. |
| **Dead-letter count/age** | Operations bị kẹt không xử lý tự động. | DLQ không được mất operation/subject correlation. |
| **ACK rate** | Connector nhận phản hồi thành công theo contract. | Không phải target readback hoặc verified rate. |
| **Readback rate** | Target state đúng desired snapshot. | Có thể chưa chặn JWT/SP sessions. |
| **Verified enforcement rate** | Required access paths đã qua probe phù hợp. | Phụ thuộc coverage và target health. |
| **Provisioning drift** | Actual roles khác desired/approved. | Manual out-of-band grants cần investigation. |
| **Late event/replay** | Lifecycle revision cũ bị bỏ qua hoặc bị apply sai. | Regrant sau Leaver là sự cố. |

**Không suy “connector response 200/204 = toàn bộ tài khoản đã an toàn”**. Khi target hỗ trợ SCIM nhưng không hỗ trợ API effective-access probe, phải ghi **coverage limitation** và áp control bù trừ được owner chấp nhận.

## 20. Chất lượng dữ liệu, tính toàn vẹn và độ bao phủ

Một KPI có thể bị lệch nghiêm trọng bởi **thiếu logs, mapping sai, clock drift, schema mismatch hoặc dữ liệu đến trễ**. Bản thân những hạn chế đó phải thành báo cáo riêng.

### Các lớp chất lượng

1. **Completeness:** nguồn và required target nào gửi dữ liệu đầy đủ? Có missing intervals?
2. **Validity:** eventType, schemaVersion, status, reference keys đúng contract?
3. **Uniqueness:** eventId trùng do duplicate delivery hay hai business attempts thật?
4. **Consistency:** HRIS trạng thái Leaver nhưng IdP ACTIVE, ERP still ALLOW?
5. **Freshness:** dataAsOf, lag và TTL của risk/entitlement caches?
6. **Provenance:** logs có trusted producer, cryptographic transport và traceability?
7. **Temporal correctness:** time-valid subject mappings, lifecycle revision và clock quality?
8. **Coverage:** các required targets/PEP/resource paths có probe hay telemetry thật?
9. **Privacy/security:** credentials không lọt vào raw logs, query exports/dashboards?
10. **Reproducibility:** cùng snapshot/policy/calculation version tái tạo đúng số không?

### Báo cáo không được biến UNKNOWN thành PASS

| Thiếu hụt | Cách ghi đúng |
| --- | --- |
| Target SaaS không có API audit. | TELEMETRY_UNAVAILABLE, risk owner và compensating control. |
| Identity mapping chỉ dựa vào email. | UNVERIFIED_MAPPING; không tự gán hành vi cho nhân viên. |
| Probe trả 503. | UNVERIFIED_OUTAGE, không tính policy DENY. |
| Connector mất events trong 2 giờ. | INGESTION_GAP, affected window và completeness reduction. |
| Source time lệch nhiều phút. | CLOCK_UNCERTAIN; SLA cần xét khoảng sai số. |
| Event cũ đến sau báo cáo phát hành. | Late correction/version, không sửa âm thầm. |
| Không xác định được owner của service principal. | OWNER_UNKNOWN và remediation. |
| API chỉ log authorization ALLOW, không business commit. | ACTION_ALLOWED, business outcome UNKNOWN. |

### Sampled traces khác audit events

Distributed traces có thể bị sample để giảm chi phí. Không lấy **sampled spans** làm mẫu số kiểm toán cấp/thu hồi quyền nếu action critical phải được ghi đầy đủ. Monitoring cần phân biệt **sampling ratio, dropped event counters, audit delivery guarantees và các target không phát log**.


## 21. Từ điển KPI: tên, đơn vị, mẫu số, thời gian và trách nhiệm

Mỗi metric nên có **data contract**. Các thuật ngữ như “Leaver completion”, “MFA compliant” hoặc “revoke success” dễ được hiểu khác nhau giữa HR, IAM, SOC và kiểm toán.

| Metric | Đơn vị/đối tượng | Mẫu số đúng | Điều kiện đạt | Owner điển hình |
| --- | --- | --- | --- | --- |
| **Joiner readiness** | Joiner employment epoch | Cohort Joiners cần provisioning | All mandatory entitlements verified by deadline, no excess access. | IAM Ops/HR. |
| **Mover revoke coverage** | Old-right access path | Tất cả paths bắt buộc phải revoke từ approved delta. | Verified DENY tại target. | IGA/App owner. |
| **Leaver verified coverage** | Required access path | Tất cả Leaver paths bắt buộc trong inventory. | Verified DENY hoặc được phân loại riêng theo ngoại lệ policy. | IAM/Security. |
| **Leaver all-target completion** | Leaver epoch | Cohort Leavers effective trong kỳ. | Tất cả required paths verified, không còn residual. | IAM Ops. |
| **Revocation on-time rate** | Required revoked path/Leaver epoch, định nghĩa rõ | Những đường có SLA deadline đã đến hạn trong cohort. | verifiedAt <= deadline, mọi điều kiện chứng cứ đạt. | IAM/SRE. |
| **Residual ALLOW rate** | Access path hoặc actual action | Scope đã bị revoke theo policy. | Có ALLOW sau effectiveAt ngoài approved exception. | SOC/App owner. |
| **Access review closure** | Review item | Review items đến hạn. | Decision recorded và execution evidence nếu REVOKE. | Access Governance. |
| **Privileged exception expiry** | Time-bound exception | Exceptions đang/đã đến hạn. | Được revoke/verified đúng thời gian. | PAM/Security. |
| **MFA compliance** | In-scope human identity | Accounts bắt buộc có MFA theo policy. | Enrolled and validated policy-required authenticator; tách usage. | IdP team. |
| **Service owner coverage** | Non-human identity | In-scope workload identities, gồm dormant. | Verified owner còn active và chịu trách nhiệm. | Platform/IAM. |
| **Target reporting coverage** | Required target/path | Catalog nguồn/target bắt buộc, không chỉ observed logs. | Telemetry + verification capability đủ theo policy. | IAM/SRE. |
| **Data freshness** | Producer/time window | Tất cả sources trong scope. | observedAt/dataAsOf trong SLO, không thiếu data window. | Data Platform. |
| **SoD conflict count** | Conflict instance | Scope of effective roles/transactions được đánh giá. | Unresolved conflicts, có severity/owner. | Control owner. |
| **Token grant hygiene** | OAuth app/client/subject grants | In-scope approved grants. | Đúng audience/scopes/expiry; stale grants được xử lý. | AS/Client owner. |

**Báo cáo phải ghi chính xác unit**: “96% target paths verified” khác hoàn toàn “96% nhân viên Leaver đã an toàn”. Một Leaver có 20 targets chưa verify không nên biến mất trong một tỷ lệ bình quân theo người nếu metric đang đo paths.

### Metadata bắt buộc cho mỗi KPI

~~~yaml
metricDefinition:
  id: leaver_verified_required_path_coverage
  version: "2"
  unit: required-access-path
  cohortBy: leaver-effectiveAt
  filters: [approved-required-target-scope, valid-subject-link]
  numerator: countVerifiedDenyPaths
  denominator: countRequiredPaths
  exclusions: [none-by-default]
  exceptionsReportedSeparately: true
  timeZone: UTC
  eventTimeField: effectiveAt
  asOfField: dataAsOf
  requiredEvidence: [target-healthy, effective-policy-deny, no-forbidden-side-effect]
  ownerRef: iam-operations
  description: "Tỷ lệ các access paths phải thu hồi đã có bằng chứng DENY hợp lệ"
~~~

Đây là **mô tả dữ liệu minh họa**, không phải cú pháp report engine cụ thể. Không chấp nhận một metric chỉ có tên, giá trị và màu đèn mà **không có định nghĩa mẫu số và evidence**.

## 22. Công thức monitoring: coverage, latency, backlog, error budget

### 22.1. Coverage theo đường truy cập

Cho \(T\) là **tập required access paths** thuộc scope, \(V\) là tập paths đã có **verified deny evidence** hợp lệ ở mốc báo cáo:

\[
\operatorname{Coverage}_{\mathrm{verified}} =
\begin{cases}
\dfrac{|V|}{|T|}\times 100\%, & |T|>0\\
\text{N/A}, & |T|=0
\end{cases}
\]

**Không mặc định mẫu số 0 tạo ra 100%.** Trạng thái cần là N/A hoặc NO_APPLICABLE_TARGETS có nguồn kiểm chứng inventory; nếu thiếu inventory thì UNKNOWN, không phải 0.

### 22.2. On-time revocation

Với các required paths đã đến hạn và có deadline áp dụng:

\[
\operatorname{OnTimeRate} =
\frac{\#\{p \in T_{\text{due}}: \operatorname{verifiedAt}_p \leq \operatorname{deadline}_p\}}
{|T_{\text{due}}|}\times 100\%
\]

Tách trạng thái **verified late**, **still ALLOW**, **unverified**, **failed**, **approved exception**. Nếu policy định nghĩa SLA theo **toàn Leaver**, phải lấy thời điểm **target bắt buộc cuối cùng** được verify cho Leaver đó.

### 22.3. Revocation latency

\[
L_p = \operatorname{verifiedAt}_p - \operatorname{effectiveAt}_p
\]

\[
L_{\mathrm{workflow}} =
\max_{p \in \mathrm{requiredPaths}}(\operatorname{verifiedAt}_p)
-\operatorname{effectiveAt}_{\mathrm{workflow}}
\]

Chỉ tính workflow latency **hoàn tất** khi **mọi path cần thiết có verifiedAt hợp lệ**, theo đúng effectiveAt. Nếu có path missing, giữ **INCOMPLETE/UNVERIFIED** và không đưa workflow đó vào histogram “successful completions” mà không nêu rõ selection bias.

### 22.4. Connector backlog và age

~~~text
PendingOperations(t) =
  logical operations chưa đạt terminal state theo policy tại thời điểm t

OldestPendingAge(t) =
  t - min(eligibleAt của pending operations)

RetryAmplification =
  total delivery attempts / distinct logical operations in scope
~~~

Không tính một operation retry ba lần là ba access requests. Giữ **operationId** qua attempts; nếu không có idempotency/provenance, metrics có thể bị thổi phồng.

### 22.5. SLA và error budget

Nếu policy xác định ví dụ **99,5% required Leaver paths cần verified DENY trong 15 phút**, hãy đo với cohort/target risk tier rõ. Đây là **giả định minh họa**, không phải tiêu chuẩn bắt buộc. Số paths cho phép trễ trong kỳ theo SLO phải được mô tả theo quy tắc làm tròn và sample sizes; một path admin critical có thể là **zero-tolerance** dù overall rate vẫn vượt ngưỡng.

### 22.6. Những trường hợp không nên cộng gộp

- **Authentication failures** và **authorization denials** là hai loại.
- **User count** và **account count** khác nhau; một user có nhiều accounts.
- **Operations** và **attempts** khác nhau.
- **Access review decisions** và **actual entitlement revocations** khác nhau.
- **Role assignments** và **effective capabilities** khác nhau.
- **Raw access events** và **committed business actions** khác nhau.
- **System healthy** và **security verified** không đồng nghĩa nhau.

## 23. SQL minh họa: mô hình dữ liệu đầu vào cho báo cáo

Các truy vấn sau dùng **cú pháp gần PostgreSQL** trên bảng logic đã được chuẩn hóa, không phải DDL hoặc bảng có thật của nhà cung cấp. Trước khi dùng cần có **data contracts**, bảo vệ PII, schema version, trusted identity mappings và correct target inventory.

~~~sql
-- Cohort business events:
-- lifecycle_event(event_id, authority, tenant_id, subject_id,
--   employment_epoch, event_type, revision, effective_at,
--   occurred_at, observed_at)
--
-- Required paths from approved access inventory at lifecycle boundary:
-- required_revoke_path(path_id, lifecycle_event_id, target_id,
--   target_account_id, entitlement_id, action_id, resource_scope,
--   deadline_at, risk_tier)
--
-- Verification evidence (validated and linked to actual PEP path):
-- verification_evidence(evidence_id, path_id, evidence_type,
--   status, occurred_at, observed_at, verified_at,
--   target_healthy, no_unauthorized_side_effect)
--
-- Effective authorization events:
-- authorization_event(event_id, authority, tenant_id, subject_id,
--   target_id, action_id, resource_ref, decision,
--   occurred_at, observed_at, business_effect)
--
-- Verified identity mapping/link tables are assumed to exist;
-- never join by mutable email or IP.
~~~

### Nguyên tắc bảo vệ query

- Scope theo **authority, tenant, subject/epoch, target và time interval**.
- Dùng **required_revoke_path** từ catalog/phê duyệt làm mẫu số, không dựa số target có log.
- Deduplicate **delivery duplicates** bằng eventId/source/version, nhưng giữ các attempts nghiệp vụ thật.
- Đừng lấy event **CONNECTOR_ACK** làm verified evidence.
- Dùng half-open intervals và công bố UTC/cutoff.
- Kiểm **clock skew, event revisions, late arrivals** trước khi dựng SLA.
- Không xuất raw token, session cookie, credential hoặc full personal payload.

## 24. SQL: tỷ lệ verified revoke và phân loại các đường chưa hoàn tất

Truy vấn minh họa cách **không tự biến thiếu evidence thành PASS**. Nếu cần báo cáo reproducible, query phải chạy trên **snapshot nhất quán đã chốt** thay vì dữ liệu streaming đang biến đổi không có as-of.

~~~sql
WITH cohort AS (
    SELECT e.event_id
    FROM lifecycle_event e
    WHERE e.event_type = 'LEAVER_EFFECTIVE'
      AND e.effective_at >= TIMESTAMPTZ '2026-11-16 00:00:00+00'
      AND e.effective_at <  TIMESTAMPTZ '2026-11-23 00:00:00+00'
),
proof AS (
    SELECT
        v.path_id,
        MAX(v.verified_at) AS last_verified_at
    FROM verification_evidence v
    WHERE v.evidence_type = 'EFFECTIVE_ACCESS_PROBE'
      AND v.status = 'VERIFIED_DENY'
      AND v.target_healthy = TRUE
      AND v.no_unauthorized_side_effect = TRUE
    GROUP BY v.path_id
),
population AS (
    SELECT
        p.path_id,
        p.deadline_at,
        proof.last_verified_at
    FROM required_revoke_path p
    JOIN cohort c
      ON c.event_id = p.lifecycle_event_id
    LEFT JOIN proof
      ON proof.path_id = p.path_id
)
SELECT
    COUNT(*) AS required_paths,
    COUNT(last_verified_at) AS verified_paths,
    COUNT(*) - COUNT(last_verified_at) AS missing_proof_paths,
    COUNT(*) FILTER (
        WHERE last_verified_at IS NOT NULL
          AND last_verified_at <= deadline_at
    ) AS verified_within_deadline,
    ROUND(
        100.0 * COUNT(last_verified_at) / NULLIF(COUNT(*), 0),
        2
    ) AS verified_coverage_percent
FROM population;
~~~

### Giới hạn phải xử lý trước production

- **MAX(verified_at)** là cách lấy lần quan sát cuối trong ví dụ; có thể che đường truy cập được **regrant sau khi từng DENY**. Production cần kiểm **state as-of, event revision, sustained DENY** và không có reactivation trái phép.
- Query chưa hiển thị **RESIDUAL_ALLOW, approved exceptions và SLA breach categories**; phải bổ sung bằng các nguồn event/cases phù hợp.
- Nếu một path có nhiều RS nodes hoặc routes, **path_id phải bao phủ đúng toàn bộ policy-required endpoints** hoặc có child coverage records; một probe không tự phủ mọi node.
- Nếu verification evidence được ghi từ nguồn không tin cậy hoặc dùng token hết hạn không thể kiểm sớm, cần đánh dấu proof invalid.
- **deadline_at** phải được sinh từ policy/risk/target, không tự cộng một TTL cố định cho mọi case.
- Khi count = 0, phép chia trả **NULL**, phải hiển thị N/A kèm catalog scope thay vì tự cho 100%.
- SQL ví dụ không tự giải quyết **rehire, subject identity ambiguity, clock drift hoặc late ingestion**; đó là trách nhiệm pipeline.


## 25. SQL: phát hiện API ALLOW sau Leaver hoặc Mover

Khi cần tìm **quyền tồn dư sau Leaver**, không join chỉ theo email hoặc subject không scoped. Giả định bảng đã map **authority + tenant + stable subject ID** đáng tin theo thời gian và các events có provenance xác minh.

~~~sql
WITH leaver AS (
    SELECT
        e.authority,
        e.tenant_id,
        e.subject_id,
        e.employment_epoch,
        e.effective_at,
        e.event_id
    FROM lifecycle_event e
    WHERE e.event_type = 'LEAVER_EFFECTIVE'
      AND e.effective_at >= TIMESTAMPTZ '2026-11-16 00:00:00+00'
      AND e.effective_at <  TIMESTAMPTZ '2026-11-23 00:00:00+00'
)
SELECT
    l.event_id AS lifecycle_event_id,
    l.subject_id,
    l.tenant_id,
    a.target_id,
    a.action_id,
    a.resource_ref,
    a.event_id AS authorization_event_id,
    a.occurred_at AS allowed_at,
    a.business_effect
FROM leaver l
JOIN authorization_event a
  ON a.authority = l.authority
 AND a.tenant_id = l.tenant_id
 AND a.subject_id = l.subject_id
 AND a.occurred_at >= l.effective_at
WHERE a.decision = 'ALLOW';
~~~

### Cần kiểm gì sau truy vấn?

1. **Temporal subject/account mapping:** user có thể rehire sau Leaver; log API phải được map tới đúng **employment/account epoch**. Query đơn giản chưa thực hiện điều đó.
2. **Target/action scope:** một ngoại lệ đã duyệt hoặc legal retention có thể ảnh hưởng kết luận; phải xét policy.
3. **Trust và event source:** API log “ALLOW” có thể do client gửi giả nếu ingestion không kiểm provenance.
4. **Authorization vs commit:** một ALLOW không tự chứng minh transaction/export thực sự hoàn tất; join downstream business events khi cần.
5. **Coverage:** nếu app không gửi log, số hàng = 0 không đồng nghĩa không có truy cập.
6. **Clock drift:** khi event time không đủ tin cậy cần đối chiếu sequence/trace và uncertainty, không dựa một so sánh timestamp tuyệt đối.
7. **Dữ liệu nhạy cảm:** event subjectRef, IP, resourceRef có thể là personal data; chỉ xuất đúng phạm vi người xem.

### Mover cần query theo permission delta

Đối với Mover, không flag mọi ALLOW sau effectiveAt là sai: **toKeep** và **toGrant** được phép. Cần join với **approved revoked-entitlements set** và **resource-level permission mapping**, tránh hiểu nhầm một role name bằng một API action duy nhất.

## 26. SQL: báo cáo access review REVOKE còn pending

Giả định các bảng đã chuẩn hóa:

~~~sql
-- access_review_item(
--   review_item_id, campaign_id, subject_ref, target_id,
--   entitlement_id, reviewer_ref, decision, decided_at)
--
-- review_revocation(
--   review_item_id, operation_id, required_path_id, deadline_at)
--
-- verification_evidence (... path_id, status, verified_at, ...)
~~~

Ví dụ truy vấn phục vụ **review remediation backlog**:

~~~sql
WITH verified AS (
    SELECT DISTINCT v.path_id
    FROM verification_evidence v
    WHERE v.evidence_type = 'EFFECTIVE_ACCESS_PROBE'
      AND v.status = 'VERIFIED_DENY'
      AND v.target_healthy = TRUE
      AND v.no_unauthorized_side_effect = TRUE
)
SELECT
    i.campaign_id,
    i.review_item_id,
    i.subject_ref,
    i.target_id,
    i.entitlement_id,
    r.operation_id,
    r.deadline_at,
    CASE
      WHEN v.path_id IS NOT NULL THEN 'VERIFIED_AT_LEAST_ONCE'
      WHEN CURRENT_TIMESTAMP > r.deadline_at THEN 'OVERDUE_UNVERIFIED'
      ELSE 'PENDING_VERIFICATION'
    END AS report_state
FROM access_review_item i
JOIN review_revocation r
  ON r.review_item_id = i.review_item_id
LEFT JOIN verified v
  ON v.path_id = r.required_path_id
WHERE i.decision = 'REVOKE';
~~~

**Quan trọng:** “VERIFIED_AT_LEAST_ONCE” chưa phải trạng thái cuối nếu có **regrant/rollback** hoặc nhiều endpoints cần coverage. Production report phải kiểm **latest authoritative state as-of**, effective rights theo từng target, exception và các item thiếu reviewer/approval. Dùng CURRENT_TIMESTAMP khiến query thay đổi theo lúc chạy; báo cáo reproducible cần **đóng băng asOf** và lưu execution metadata.

## 27. Java pseudocode: mô hình tính toán báo cáo theo snapshot

Một reporting job không nên tính tỷ lệ bằng cách chỉ đọc số request success từ connector. Thiết kế tối thiểu cần **cohort, required paths từ approved inventory, evidence đã xác minh và as-of cutoff**.

~~~java
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Set;

record RequiredPath(
    String pathId,
    String lifecycleEventId,
    String subjectRef,
    String targetId,
    String entitlementRef,
    Instant effectiveAt,
    Instant deadlineAt
) {}

record VerifiedEvidence(
    String evidenceId,
    String pathId,
    Instant verifiedAt,
    boolean targetHealthy,
    boolean policyDenied,
    boolean noForbiddenSideEffect
) {}

record MetricResult(
    int requiredPaths,
    int verifiedPaths,
    int unverifiedPaths,
    int onTimeVerifiedPaths,
    Instant dataAsOf
) {}

interface ApprovedInventory {
    List<RequiredPath> requiredPathsForCohort(
        Instant cohortStart, Instant cohortEnd, Instant dataAsOf);
}

interface EvidenceRepository {
    List<VerifiedEvidence> evidenceForPathsAsOf(
        Set<String> pathIds, Instant dataAsOf);
}

// Pseudocode: helper classes/constructors not shown.
final class RevocationReportService {
    private final ApprovedInventory inventory;
    private final EvidenceRepository evidence;

    MetricResult compute(
        Instant start, Instant end, Instant dataAsOf) {

        List<RequiredPath> required =
            inventory.requiredPathsForCohort(start, end, dataAsOf);

        Set<String> ids = required.stream()
            .map(RequiredPath::pathId)
            .collect(java.util.stream.Collectors.toSet());

        Map<String, List<VerifiedEvidence>> byPath =
            groupByPath(evidence.evidenceForPathsAsOf(ids, dataAsOf));

        int verified = 0;
        int withinSla = 0;

        for (RequiredPath path : required) {
            boolean hasValidProof = byPath
                .getOrDefault(path.pathId(), List.of())
                .stream()
                .anyMatch(v ->
                    v.targetHealthy()
                    && v.policyDenied()
                    && v.noForbiddenSideEffect()
                    && !v.verifiedAt().isAfter(dataAsOf));

            if (hasValidProof) {
                verified++;
                boolean onTime = byPath.get(path.pathId()).stream()
                    .anyMatch(v ->
                        v.targetHealthy()
                        && v.policyDenied()
                        && v.noForbiddenSideEffect()
                        && !v.verifiedAt().isAfter(path.deadlineAt())
                        && !v.verifiedAt().isAfter(dataAsOf));
                if (onTime) withinSla++;
            }
        }

        return new MetricResult(
            required.size(),
            verified,
            required.size() - verified,
            withinSla,
            dataAsOf
        );
    }
}
~~~

### Giới hạn quan trọng của ví dụ Java

- Đây là **pseudocode kiến trúc**, vì groupByPath và các repository adapters chưa được triển khai; không phải ví dụ có thể chạy nguyên trạng.
- **anyMatch** chỉ chứng minh một lúc từng DENY, không ngăn **regrant sau đó**. Production cần tính latest as-of và **sustained effective state**, replay/revision và tất cả required nodes/actions.
- **ApprovedInventory** phải có source/policy snapshots đáng tin, xử lý **subject epochs** và target catalog đầy đủ, không chỉ đọc “targets có log”.
- Nếu evidence từ API bị 503 hoặc token quá hạn khi cần chứng minh revoke sớm, repo phải **loại khỏi VERIFIED_DENY** theo evidence contract.
- Không tính một person có nhiều target thành một “Leaver completed” trước khi kiểm all-target closure.
- DataAsOf phải đi kèm **snapshot/reference versions, ingestion watermark** và tính reproducible.
- Không log toàn bộ raw evidence hoặc subject profile khi xuất metrics.

### Vì sao tính hai metric khác nhau?

**Verified paths** đo evidence coverage; **on-time verified paths** đo performance so với deadline. Một path verified sau SLA **nên được tính là covered nhưng vẫn là late**. Điều đó giúp tránh xóa một sự cố SLA chỉ vì cuối cùng đã remediated.

## 28. YAML: hợp đồng một báo cáo monitoring có thể tái lập

~~~yaml
report:
  id: iam-lifecycle-health-weekly
  version: "1.3"
  title: "IAM Lifecycle Monitoring - Weekly"
  language: vi
  ownerTeam: iam-operations
  approvers: [iam-governance, security-assurance]
  frequency: weekly
  timezone: Asia/Ho_Chi_Minh
  periodStart: "2026-11-16T00:00:00+07:00"
  periodEndExclusive: "2026-11-23T00:00:00+07:00"
  dataAsOf: "2026-11-23T04:00:00+07:00"
  revision: 1
  status: PROVISIONAL
  cohortKey: [subjectAuthority, tenantRef, stableSubjectRef, employmentEpoch]
  datasets:
    - hr_lifecycle_event
    - iga_entitlement_snapshot
    - idp_token_session_metadata
    - scim_connector_operations
    - required_target_inventory
    - target_grant_readback
    - pep_verification_evidence
    - protected_audit_events
  metrics:
    - id: leaver_required_path_verified_coverage
      definitionVersion: "2"
      groupBy: [riskTier, targetType]
    - id: mover_revoke_overlap_window
      definitionVersion: "1"
    - id: non_human_owner_coverage
      definitionVersion: "3"
  evidencePolicy:
    connectorAckIsNotVerified: true
    requireTargetHealthyForDenyProbe: true
    requireNoForbiddenSideEffects: true
    distinguishUnknownFromPass: true
  output:
    viewers: [iam-ops, security, authorized-auditors]
    includeRawCredentials: false
    includeUnverifiedTargetList: true
    includeIncidentAndOwnerRefs: true
  reproducibility:
    sourceSnapshotRef: snapshot-iam-20261123-04
    calculationVersion: "iam-report-code-v8"
    policyCatalogVersion: "access-policy-v21"
    requiredTargetCatalogVersion: "target-catalog-v10"
~~~

Đây là **hợp đồng báo cáo minh họa**, không phải schema của một nền tảng cụ thể. Nếu kỳ chốt chưa đủ dữ liệu (watermark chưa đạt), cần hiển thị **PROVISIONAL**, công bố thay đổi khi phát hành bản FINAL và lưu **audit trail revision**.


## 29. Mẫu báo cáo tuần: Identity Lifecycle Monitoring

**Khung báo cáo minh họa — dữ liệu giả định, không phải dữ liệu doanh nghiệp.**

**Tên báo cáo:** Identity Lifecycle Monitoring — Tuần 16–22/11/2026.  
**Kỳ đo:** [2026-11-16 00:00, 2026-11-23 00:00), Asia/Ho_Chi_Minh.  
**As-of:** 2026-11-23 04:00, Asia/Ho_Chi_Minh.  
**Trạng thái:** PROVISIONAL (một target SaaS còn thiếu data feed).  
**Đơn vị quản trị:** IAM Operations; Security Assurance; application owners.

### A. Executive snapshot

| Chỉ số | Kết quả giả định | Diễn giải |
| --- | ---: | --- |
| Joiner employment epochs | 60 | 58 READY, 2 PARTIAL; không suy sẵn 58 đã không có excess grants. |
| Mover employment events | 35 | 32 VERIFIED, 3 còn target/SoD review. |
| Leaver employment epochs | 100 | 100 workflow records completed ở IGA; chưa đủ chứng cứ toàn scope. |
| Leaver required access paths | 420 | Mẫu số từ approved target inventory. |
| Verified DENY paths | 405 | 398 đúng SLA, 7 trễ SLA. |
| Residual ALLOW paths | 2 | Đã phát hiện API/credential tiếp tục cho truy cập; cần incident. |
| Unverified/missing-proof paths | 13 | Thiếu readback/probe, outage hoặc mapping chưa đủ. |
| Non-human identities | 450 | 12 không có verified active owner. |
| Privileged/JIT activations | 86 | 2 activations có expiry/readback gap. |
| Monitoring coverage gaps | 3 sources | Kết quả cần xác minh impact, không tự coi safe. |

### B. Calculated metrics

~~~text
Required access paths                          420
Verified DENY                                  405
Verified within deadline                       398
Verified late                                    7
Residual ALLOW                                   2
Unverified                                      13

Verified coverage                 = 405 / 420 = 96.43%
Verified within SLA               = 398 / 420 = 94.76%
Residual path fraction            =   2 / 420 =  0.48%
Unverified path fraction          =  13 / 420 =  3.10%
Verified but late                 =   7 / 420 =  1.67%
~~~

Các tỷ lệ làm tròn độc lập; không cộng các phần trăm để suy chính xác 100% nếu có sai số làm tròn. **Đây là dữ liệu minh họa** và 420 là tổng số **path** chứ không phải 420 người. Không đủ dữ kiện để nói **bao nhiêu trong 100 Leavers đã hoàn tất tất cả paths**, vì phân phối 15 paths chưa verified/residual theo từng người chưa được cung cấp.

### C. Open risks và quyết định cần chủ sở hữu

| Finding | Severity giả định | Bằng chứng/giới hạn | Owner | Hành động |
| --- | --- | --- | --- | --- |
| R-101 | CRITICAL | Finance API vẫn ALLOW action sau Leaver effectiveAt. | Finance API owner + SOC. | Contain credential/grant; verify DENY tại required routes. |
| R-102 | HIGH | Legacy SaaS PAT còn hoạt động sau disable user. | SaaS owner/IAM. | Revoke PAT, kiểm local ACL và export logs. |
| R-103 | HIGH | 8 required paths thiếu target readback. | SCIM/Target ops. | Fix connector/provider visibility; quản lý như UNVERIFIED. |
| R-104 | MEDIUM | 5 paths probe lỗi do target unavailable. | SRE/Application owner. | Positive control rồi chạy lại negative probe. |
| R-105 | HIGH | 12 service principals thiếu owner còn hiệu lực. | Platform/Asset owner. | Ownership attestation, kiểm trust/grants, hạn chế orphan risk. |
| R-106 | HIGH | 2 JIT roles chưa có evidence hết hiệu lực ở target. | PAM/Cloud owner. | Readback/deny probes, đánh giá privileged exposure. |

### D. Tình trạng dữ liệu

- **One SaaS audit feed chưa đồng bộ:** báo cáo PROVISIONAL; không báo “0 incidents” cho target này.
- **Policy/catalog versions** được lưu trong report metadata để tái lập.
- **Kỳ chốt** dự kiến sau late-event watermark nếu policy cho phép; critical residual ALLOW phải xử lý ngay, không chờ FINAL.
- **Exception register** được tách riêng, có scope/owner/expiry và risk acceptance; không làm giả tỷ lệ verified deny.

### E. Sign-off

**Report owner** xác nhận phạm vi và phép tính. **Security/Risk owner** duyệt các mức ưu tiên. **Target owners** nhận remediation và deadline. **Auditor** có thể mở protected evidence theo RBAC; sign-off không đồng nghĩa mọi findings đã được đóng.

**Lưu ý triển khai:** Mẫu trên được trình bày bằng Markdown tiêu chuẩn để phù hợp nhiều hệ thống hiển thị. Tất cả thông số chỉ mang tính minh họa và không mô tả dữ liệu doanh nghiệp thật.

## 30. Dashboard và cách dẫn từ tổng quan đến bằng chứng

Một dashboard giỏi **không chỉ tô màu xanh/đỏ**. Người xem cần biết đang đo gì và mức tin cậy ra sao.

### Trang executive

- Tình trạng JML theo tháng và risk tier, trend so với kỳ trước.
- Leaver verified coverage và on-time rate, **đơn vị rõ path vs person**.
- Những residual ALLOW/critical exceptions còn mở.
- Coverage gaps/UNVERIFIED với severity, target owner.
- Privileged/grants posture và service identity owner coverage.

### Trang vận hành IAM

- Queue backlog theo logical operation, số attempts, retry reason, DLQ age.
- SCIM target health: request ACK, readback, verification; phân biệt trạng thái.
- Processing duration percentiles theo app/risk tier, late events, propagation lag.
- Failure drill-down theo correlationId, event revision, target account, connector code.
- Target inventory và data freshness checks.

### Trang security/SOC

- Residual ALLOW sau effectiveAt, token/session anomalies, privileged out-of-band grants.
- Unusual role escalation, SoD candidates có verified actor/resource history.
- Risk-based access challenge vs final API outcomes.
- Evidence timeline và current containment status.

### Trang application owner/auditor

- Current effective permissions so với approved snapshots.
- Access review campaign decisions, revoke backlog, policy exceptions.
- Protected drill-down: event IDs, approval refs, target readback, PEP probe.
- ReportVersion/dataAsOf/source snapshots và cách tái lập số.

### Quy tắc hiển thị

1. **Tên metric và đơn vị** luôn nhìn thấy (subjects, access paths, operations, events).
2. **As-of, timezone, policy version, source coverage** được hiển thị.
3. Trạng thái **UNKNOWN/UNVERIFIED** khác **FAILED** và khác **VERIFIED_DENY**.
4. Có lựa chọn lọc theo **tenant, risk tier, target, lifecycle stage, severity, environment** trong quyền được phép.
5. Cùng một chart không trộn không có lý do **subject counts** và **token issuance counts**.
6. Tỷ lệ tốt không che **1 critical unverified target**.
7. Các số thay đổi do correction/late event cần có **revision/variance explanation**.
8. Không phơi bày email đầy đủ, access tokens hay hồ sơ HR nhạy cảm cho viewers không có thẩm quyền.

## 31. Khi nào cần alert ngay, khi nào đủ đưa vào báo cáo kỳ?

Monitoring report hữu ích cho xu hướng và governance, nhưng các tình huống có tác động nghiêm trọng đòi **phát hiện/ứng cứu không đợi tới lịch báo cáo**.

| Tình huống | Cách xử lý |
| --- | --- |
| **Leaver API còn ALLOW privileged action** | Immediate security alert/incident, contain và verify. |
| **Staging workload assume production admin ngoài policy** | Alert ngay, revoke trust/credentials theo incident response. |
| **SaaS SCIM 429 nhiều lần, deadline gần tới** | Operational alert và remediation trước SLA. |
| **Service principal không có owner trong 30 ngày** | Governance backlog/escalation theo risk; không nhất thiết incident tức thời nếu không có abuse. |
| **MFA completion rate giảm dần tuần qua tuần** | Trend analysis và review UX/IdP provider. |
| **Access review sắp đến hạn** | Scheduled reminders/escalation theo owner, có deadline. |
| **Report ingestion gap của app critical** | Telemetry health alert, tách khỏi “không có sự cố”. |
| **JIT admin grant còn ALLOW sau TTL** | Security alert/containment theo risk; không chờ báo cáo tháng. |

### Kết hợp ngưỡng và mục đích

Đừng đặt severity chỉ theo **số lượng**. Một privileged cross-tenant grant tồn dư có thể nghiêm trọng hơn 50 lần login failure do ứng dụng bị cấu hình sai. Risk prioritization nên kết hợp **asset sensitivity, privilege, actor context, actual ALLOW, exploitability, duration và coverage**.

### Incident handoff tối thiểu

~~~yaml
findingRef: residual-access-20261123-011
sourceReportRef: iam-lifecycle-health-weekly-1.3
businessEventRef: jml-leaver-884
affectedSubjectRef: person-884
targetRef: finance-api
action: payment.approve
firstObservedResidualAt: "2026-11-23T02:07:00Z"
lastObservedResidualAt: "2026-11-23T02:10:00Z"
severity: CRITICAL
evidenceRefs:
  - api-allow-331
  - current-role-readback-812
  - lifecycle-effective-884
ownerTeam: finance-security-operations
status: CONTAINMENT_IN_PROGRESS
rawCredentialIncluded: false
~~~

Đây là schema mô phỏng. Một alert phải có **evidence references và owner**, không gửi thông tin bí mật vào chat/webhook không được bảo vệ.

## 32. Risk prioritization và exception reporting

Một báo cáo có thể cần xếp hạng findings để tập trung remediation. Không nên lấy một score tùy ý làm bằng chứng security guarantee.

### Thuộc tính để đánh giá rủi ro

- **Privilege:** read-only tổng hợp, PII export, tenant admin, cloud IAM admin, token signing keys.
- **Resource sensitivity:** production/customer data, payment, HR records, secrets.
- **Actual outcome:** configured role tồn tại hay PEP đã ALLOW giao dịch sau effectiveAt?
- **Exposure duration:** từ mốc policy tới containment/verified DENY có tin cậy.
- **Blast radius:** một tenant, tất cả tenants, một region hay toàn tổ chức.
- **Compensating controls:** network isolation, approvals, step-up, transaction SoD, short-lived tokens.
- **Exploitability:** credential lộ, publicly reachable endpoint, attacker control indicators.
- **Uncertainty:** target có logging/verification không, identity mapping có đáng tin không?
- **Owner/expiry:** finding và exception có responsible owner/deadline không?

### Exception phải là một trạng thái độc lập

Nếu risk owner chấp nhận **temporary access exception** cho migration, báo cáo cần nêu **reason, approver, exact principal/action/resource, effective interval, TTL, monitoring và exit plan**. Không chuyển exception sang VERIFIED_DENY, vì quyền được phép **tiếp tục ALLOW có chủ đích**; phải đo số exceptions đang active/quá hạn và xem xét theo governance.

**Không chấp nhận exception “để trống vô hạn”** hoặc do chính principal hưởng quyền tự duyệt khi policy cần độc lập. Hard regulatory/SoD prohibitions có thể không được phép override bằng exception.

## 33. Privacy, security và retention của báo cáo IAM

Báo cáo IAM có thể liên kết **tài khoản nhân sự, login history, device metadata, vị trí tương đối, quyền nhạy cảm, API behavior, incidents**. Đây là dữ liệu có độ nhạy cao; cần phân quyền và giới hạn mục đích.

| Kiểm soát | Giải pháp |
| --- | --- |
| **Purpose limitation** | Thu thập đủ cho JML/operation/security/audit đã được phê duyệt. |
| **Data minimization** | Dùng protected subject refs và aggregated metrics thay raw HR profile. |
| **Credential hygiene** | Không log/xuất raw access/refresh tokens, passwords, OTP, MFA seeds, private keys, API keys. |
| **Role-/attribute-based viewing** | Executive summary khác SOC detail, audit evidence khác helpdesk view. |
| **Tenant isolation** | Báo cáo/query/export không cho reviewer tenant A xem tenant B nếu không có quyền. |
| **Export protection** | Encrypted storage/transit, controlled download, watermark/classification khi cần. |
| **Retention** | Retention phù hợp policy/luật, legal hold có thẩm quyền, xóa đúng hạn. |
| **Tamper resistance** | Protected append-only/audit trail, separated admins/SoD cho report generation và evidence deletion. |
| **Reproducibility** | Snapshot refs, calculation version, report revision và signed/attested release khi risk yêu cầu. |
| **Access auditing** | Ai đã xem, lọc hoặc xuất báo cáo nhạy cảm và khi nào? |
| **Pseudonymization** | Keyed HMAC/managed identity refs khi hợp lý, bảo vệ mapping keys. |
| **Secure distribution** | Không đính kèm toàn bộ danh sách privileged identities lên mailing list rộng. |

### Pseudonymized không có nghĩa anonymous

Nếu subjectRef hoặc HMAC ID có thể nối lại với người, dữ liệu vẫn có thể là **personal data**. Không dùng hash thường của email có entropy thấp rồi khẳng định đã ẩn danh. Kiểm soát mapping keys, access logs, retention và legal basis theo chính sách áp dụng.

### Tách quyền tạo báo cáo và sửa evidence

Một production admin không nên có quyền **xóa dấu vết privileged actions của chính mình** mà không bị phát hiện. Báo cáo cần được dựng từ nguồn có provenance, audit integrity và approval/sign-off controls phù hợp.


## 34. Reliability của reporting pipeline và giám sát chính hệ thống monitoring

Một vấn đề căn bản: **nếu hệ thống giám sát không hoạt động, báo cáo an toàn vẫn có thể trông rất đẹp** vì không nhận được bất kỳ sự kiện xấu nào. Cần monitoring cho chính data pipeline, từ producer tới report publishing.

~~~mermaid
flowchart TD
    P["IdP / HRIS / IGA / API producers"] --> C["Secure ingestion / collector"]
    C --> V["Schema validation + redaction"]
    V --> Q["Queue / buffer / replay"]
    Q --> N["Normalize + temporal identity mapping"]
    N --> M["Metrics / evidence store"]
    M --> R["Report generation + snapshots"]
    R --> A["Owner access + distribution audit"]
    P -.-> H["Pipeline-health metrics"]
    C -.-> H
    Q -.-> H
    N -.-> H
    M -.-> H
    R -.-> H
    H --> I["Alert on blind spots"]
~~~

### Các lỗi vận hành phải phát hiện

| Lỗi | Ảnh hưởng báo cáo | Kiểm soát |
| --- | --- | --- |
| **Collector down** | Missing events có thể bị hiểu là zero abuse. | Producer heartbeat, ingestion gap, dead-letter/replay. |
| **At-least-once duplicate delivery** | Count tăng sai. | EventId/source dedup, giữ business attempts riêng. |
| **Late events** | Kết luận báo cáo FINAL trước khi đủ evidence. | Watermark, provisional/final revisions. |
| **Out-of-order JML events** | Mover cũ tới sau Leaver, tạo nhầm state. | Lifecycle revision/current-state checks. |
| **Identity link stale** | Gán hành động của người A cho người B. | Temporal mapping/owner verification. |
| **Schema field renamed** | Không đọc được status hoặc đổi nghĩa. | Contract tests/schema versioning. |
| **Clock skew** | Sai causal ordering và SLA latency. | Clock health, uncertainty, event sequence. |
| **RS node thiếu logging** | Một route bypass PEP bị bỏ sót. | Required path coverage và canary probes. |
| **Reporter service permissions quá rộng** | Báo cáo có thể đọc/ghi dữ liệu ngoài scope. | Read-only least privilege, independent audit. |
| **Metric definition drift** | Cùng “verified” nhưng cách tính đổi giữa kỳ. | Versioned metric dictionary và change review. |
| **Report job timeout sau publish** | Publish trùng hoặc nửa dữ liệu. | Atomic artifact release, idempotent runRef và revision. |

### Khi không có khả năng xác minh

Không tuyên bố dashboard “hệ thống khỏe” nếu **nguồn required đã im lặng**. Trạng thái đúng là **DEGRADED_MONITORING/UNKNOWN**, kèm phạm vi bị ảnh hưởng, estimated gap, owner và mitigation. Với action critical, IAM policy/PEP vẫn phải thực thi, không được tự fail-open vì monitoring bất ổn.

## 35. Case study: Leaver hoàn tất trên IGA nhưng Finance API còn ALLOW

### Bối cảnh

**An** rời công ty lúc 17:00. HRIS, IdP, IGA, SCIM và Finance API đều có integration. Nhóm vận hành xuất báo cáo Leaver vào 18:00 và chỉ nhìn **100% connectors ACK**.

### Dòng thời gian

| Giờ | Event/bằng chứng | Diễn giải đúng |
| --- | --- | --- |
| 17:00 | HR_LEAVER_EFFECTIVE. | Mốc quyền cần thu hồi. |
| 17:01 | IGA_REVOKE_REQUESTED. | Workflow bắt đầu. |
| 17:02 | IDP_ACCOUNT_DISABLED. | Có thể ngăn sign-in/issuance mới, chưa chứng minh JWT cũ. |
| 17:03 | SCIM_USER_DISABLED, status 204. | Connector ACK; target đã xử lý theo contract. |
| 17:04 | ERP_ACCOUNT_READBACK inactive. | Configuration phù hợp; local PAT phải kiểm riêng. |
| 17:05 | OAuth refresh grant revoked. | Chặn refresh tiếp nếu flow theo AS contract. |
| 17:06 | Finance API AUTHZ_ALLOW bằng token cũ cho reports.export. | **Residual access**; cần containment, kiểm business export effect. |
| 17:09 | API PEP current-state policy cập nhật. | Cơ chế chặn sớm bắt đầu áp. |
| 17:10 | Safe negative probe ở Finance API trả policy DENY. | Evidence cho path đã test, nếu positive control/API healthy. |
| 17:14 | SaaS PAT local vẫn ALLOW reports.download. | Path khác chưa được chặn. |
| 17:17 | PAT revoked; SaaS negative probe DENY. | Đóng path local theo evidence. |
| 17:18 | Required paths readback/probe đạt, dữ liệu đủ. | Có thể xem VERIFIED nếu inventory đầy đủ. |

### Báo cáo phải chỉ ra điều gì?

1. Workflow **ACK complete** vào 17:03 **không phải** verified deprovision time.
2. Finance API còn ALLOW trong **ít nhất một khoảng sau effectiveAt**, và API event 17:06 cần kiểm có xuất file/side effect không.
3. SaaS PAT là nguồn quyền khác, không tự bị revoke bởi OAuth hoặc IdP logout.
4. Deadline SLA phải tính theo policy của target/risk; nếu policy giả định là **10 phút từ 17:00**, path SaaS verified 17:17 là **late**, dù sau đó an toàn.
5. Nếu report period kết thúc lúc 17:15, cần hiển thị **PARTIAL tại as-of** và cập nhật revision khi có evidence 17:17.
6. Nếu log API 17:06 đến collector lúc 18:20, bản báo cáo 18:00 cần **data freshness warning**, không dùng số 0 để kết luận không residual.

### Root-cause và follow-up

Bảng root cause có thể phân loại: **JWT stale**, **missing PEP current-state**, **local PAT outside provisioning**, **insufficient inventory**, **monitoring latency**. Mỗi finding có owner khác nhau: AS team, Finance API team, SaaS owner và Data Platform. Báo cáo phải liên kết remediation, không chỉ lặp lại biểu đồ.

## 36. Case study: Mover và xung đột SoD bị che bởi số liệu cấp quyền

### Bối cảnh

Nhân viên **Mai** chuyển từ Sales Operations sang Finance Payment Approver. Dashboard ban đầu đo **“new role provisioned in 2 minutes”** và xếp PASS. Tuy nhiên role cũ Creator vẫn cho phép qua local ACL/JWT trước khi thu hồi.

### Timeline

~~~text
09:00  HRIS Mover effectiveAt, revision 28.
09:01  IGA computes rights: revoke Creator, grant Approver.
09:02  IdP group Creator removed; Finance role approved.
09:03  SCIM returns ACK; new Approver role active.
09:04  Old access token still allows payment.create.
09:05  Current-state PEP policy starts denying Creator.
09:06  Safe negative probe confirms Creator DENY.
09:07  User completes WebAuthn step-up for Approver.
09:08  User attempts to approve payment created by same subject.
09:08  Transaction-level SoD correctly DENY.
~~~

### Báo cáo phải có ba hàng kết quả

| Control | Quan sát | Status |
| --- | --- | --- |
| **New Approver provisioning** | Granted và tested theo approved scope. | VERIFIED_GRANTED nếu đúng quyền/target. |
| **Old Creator revocation** | ALLOW sau 09:00 tới khi PEP được sửa. | VERIFIED_LATE và có residual interval. |
| **Transaction SoD** | Self-approval bị backend chặn dù user đã step-up. | PASS cho test được kiểm. |

**Không gom ba hàng này thành một chỉ số “Mover SUCCESS” thiếu giải thích.** Nếu policy cấm overlap dù chỉ vài phút, phát hiện lúc 09:04 vẫn là finding. Cần phân biệt **role-based SoD** và **transaction history**, vì việc đổi role không xóa dấu vết createdBy của payment cũ.

## 37. Case study: batch/service account mất owner và secret tồn dư

### Bối cảnh

Một batch job tạo báo cáo doanh thu theo ngày, dùng **Kubernetes ServiceAccount** ở runtime và **OAuth client credentials** để gọi Finance API. Nhân viên owner nghỉ việc, hệ thống xóa account cá nhân nhưng không kiểm registry workload.

### Dữ liệu báo cáo ban đầu

| Chỉ dấu | Quan sát | Rủi ro |
| --- | --- | --- |
| Human owner Leaver. | HRIS subject đã INACTIVE. | Ai chịu trách nhiệm job, secret và incident? |
| Workload vẫn chạy 02:00. | Job có business purpose còn hợp lệ. | Không nên tự xóa job nếu chưa được business owner duyệt. |
| Client credential chưa rotate. | Owner cũ từng có quyền đọc vault. | Có thể tồn dư credential bị sao chép, cần risk assessment. |
| Trust issuer/subject rộng. | Staging có thể assume role production. | Cross-environment privilege path. |
| Finance API grants. | finance.reports.read và finance.admin tồn tại. | Admin scope thừa so với job. |
| Output bucket. | Báo cáo có thể download ngoài nhóm cho phép. | Dữ liệu read-only ở nguồn vẫn có thể bị lộ ở đích. |
| Token issuance. | Token được xin ngoài lịch chạy thường lệ. | Cần điều tra caller/runner và provenance. |

### Báo cáo hành động đề xuất

1. **Chuyển owner** tới team còn trách nhiệm; verify contact và on-call.
2. **Thu hồi quyền human owner cũ** tại repo, vault, CI/CD và cloud management.
3. **Giảm scope** của service principal xuống đúng app action/tenant/prefix; review role inheritance.
4. **Kiểm trust** theo issuer, namespace, ServiceAccount, repository, branch và environment.
5. **Đánh giá rotate credentials** và vô hiệu old-key trust nếu cần; kiểm tokens đã phát.
6. **Kiểm dữ liệu đầu ra**: ACL/encryption/retention phù hợp classification.
7. **Đo effective access** bằng positive/negative probes: reports.read hợp lệ ALLOW, admin/cross-tenant DENY.
8. **Theo dõi expected runs, duplicate/retry và access outside schedule**.
9. Cập nhật inventory/review deadline/owner và evidence references.
10. Chỉ decommission job khi business purpose kết thúc; lúc đó revoke toàn bộ runtime/target grants/trust/PAT và verify DENY.

### Bài học

**Human Leaver và workload Leaver là hai lifecycle events khác nhau.** Một báo cáo chỉ đếm human accounts sẽ bỏ sót service trust và owner transitions, trong khi một automation xóa service account ngay có thể gây gián đoạn nghiệp vụ hợp lệ.


## 38. Ma trận kiểm thử báo cáo monitoring trong IAM

Bộ test nên có **synthetic HRIS/IGA/IdP/SCIM/API events, giả lập target responses, policy snapshots và test oracle độc lập**. Không chạm tài khoản/credential thật để sinh số liệu hay thử truy cập trái phép.

| ID | Trường hợp | Kết quả báo cáo kỳ vọng |
| --- | --- | --- |
| IM01 | Có 10 Joiners đúng effectiveAt, 9 đủ mandatory targets, 1 thiếu. | Readiness 9/10; 1 PARTIAL, đúng đơn vị. |
| IM02 | Joiner pre-provision trước start date theo policy. | Không gắn nhãn violation chỉ vì account tồn tại sớm. |
| IM03 | Joiner dùng app dữ liệu nhạy cảm trước effectiveAt trái policy. | EARLY_ACCESS finding. |
| IM04 | Joiner được cấp thêm global admin không có approval. | Excess grant finding dù onboarding đầy đủ. |
| IM05 | Một person có 3 target accounts. | Đếm identity, account và required paths khác nhau. |
| IM06 | Hai users có cùng email qua hai thời kỳ. | Không gộp, dùng stable IDs và epoch. |
| IM07 | OIDC pairwise subject khác giữa clients. | Chỉ link nếu IdP/IGA mapping verified. |
| IM08 | SCIM target ID 17 ở tenant A và tenant B. | Không cross-tenant join. |
| IM09 | HRIS event Mover đổi role với 2 quyền revoke, 1 KEEP, 1 grant. | Báo cáo đúng delta, không gắn KEEP thành stale. |
| IM10 | Mover old role đã gỡ group nhưng API cũ còn ALLOW. | Residual old-right, chưa verified revoke. |
| IM11 | Mover mới nhận Approver trong khi Creator còn effective. | SoD overlap finding. |
| IM12 | Sau Mover, user tự duyệt payment từng tạo. | SoD transaction-level finding, không chỉ role check. |
| IM13 | Mover có quyền mới approved nhưng target chưa provision. | PENDING_GRANT, không báo đầy đủ. |
| IM14 | HRIS Leaver 100/100 workflow IGA completed, 1 RS còn ALLOW. | Không báo all-target Leaver VERIFIED. |
| IM15 | SCIM PATCH 204 nhưng target role còn. | ACK_ONLY/TARGET_DRIFT, không VERIFIED. |
| IM16 | Target role đã gỡ, token cũ vẫn ALLOW. | RESIDUAL_ALLOW theo PEP. |
| IM17 | Refresh grant revoked, JWT cũ còn hạn vẫn ALLOW. | Token lifecycle gap, tách new issuance khỏi old access. |
| IM18 | SaaS PAT còn hoạt động sau IdP disable. | Residual app-local credential finding. |
| IM19 | API 503 khi negative probe. | UNVERIFIED_OUTAGE, không tính DENY. |
| IM20 | HTTP 403 nhưng async export worker tạo file. | FAIL no-side-effect; không VERIFIED. |
| IM21 | Token expired tự nhiên khi policy yêu cầu early revoke proof. | Không coi expired-token-only result là proof revoke sớm. |
| IM22 | Một required target chưa có telemetry. | Missing coverage vẫn trong mẫu số. |
| IM23 | Required target inventory chỉ gồm các app có log. | Data contract/test FAIL vì mẫu số thiếu. |
| IM24 | Một Leaver có 20 required paths, 19 verified, 1 missing. | Person all-target completion = false. |
| IM25 | 405/420 paths verified, 2 residual và 13 unverified. | Coverage 96,43%, báo riêng residual/unverified. |
| IM26 | Mẫu số 0 vì không có required events hợp lệ. | Hiển thị N/A, không tự 100%. |
| IM27 | Cohort start inclusive, end exclusive. | Event đúng boundary chỉ thuộc một kỳ. |
| IM28 | Leaver effective cuối tháng, verified đầu tháng sau. | Thuộc cohort tháng trước; closure cập nhật khi as-of đủ. |
| IM29 | Connector log được ingest 30 phút sau occurredAt. | SLA dùng effective/verified times, ingestion lag riêng. |
| IM30 | Producer clock lệch 5 phút. | CLOCK_UNCERTAIN, không báo millisecond SLA giả chính xác. |
| IM31 | Mover revision 41 đến sau Leaver revision 42. | Stale event không regrant và báo đúng causal order. |
| IM32 | Duplicate delivery cùng eventId. | Không tăng business event count hai lần. |
| IM33 | Một revoke operation retry ba lần. | Một logical operation, 3 attempts, đúng error categories. |
| IM34 | Một connector timeout nhưng target đã apply. | Reconciliation xác nhận state, không chỉ FAILED từ timeout. |
| IM35 | Phát hiện 1 target đã VERIFIED rồi được regrant sau đó. | Latest as-of không báo VERIFIED nếu now ALLOW trái policy. |
| IM36 | Proof API DENY chỉ tại một node, node thứ hai stale. | Chưa coi toàn RS cluster covered. |
| IM37 | Token từ staging gọi production API. | Ghi cross-env violation/reject theo policy, không gộp tenant. |
| IM38 | User có APP_ROLE read, cố export PII. | Phân biệt authentication success với authz DENY; report data risk. |
| IM39 | Review campaign 100 items, 90 decisions nhưng 10 REVOKE chưa apply. | Decision coverage khác remediation closure. |
| IM40 | Requester tự approve admin khi policy cấm. | SoD finding với stable principal identity. |
| IM41 | Reviewer chọn KEEP cho quyền không có approved business need. | Cảnh báo review/approval policy gap; không tự hợp thức hóa. |
| IM42 | JIT role expired trong PAM nhưng cloud role còn ALLOW. | Privileged residual access. |
| IM43 | Privileged role có 2 grants chồng nhau 1 giờ. | Privilege-hours theo effective capability không tự nhân đôi. |
| IM44 | User được phê duyệt exception đúng scope và còn TTL. | Báo riêng EXCEPTION_APPROVED, không tính VERIFIED_DENY. |
| IM45 | Exception đã hết hạn nhưng tiếp tục suppress alert. | EXPIRED_EXCEPTION finding. |
| IM46 | MFA enrolled nhưng privileged login dùng factor yếu hơn policy. | Không tính assurance usage compliant. |
| IM47 | Access token issuedAt mới nhưng auth_time cũ. | Không báo user vừa step-up. |
| IM48 | Risk-based step-up completed nhưng API DENY SoD. | Báo proof success và final authz DENY riêng. |
| IM49 | Đăng nhập IdP thất bại vì outage. | Không mặc định credential compromise; phân loại lỗi. |
| IM50 | Một service principal không có owner còn active. | OWNER_UNKNOWN; tính trong non-human inventory. |
| IM51 | Owner nhân viên Leaver, job vẫn còn approved purpose. | Chuyển ownership, không tự decommission job. |
| IM52 | Batch job đã xóa, OAuth client grant vẫn active. | Decommission residual finding. |
| IM53 | Client secret rotated nhưng key cũ vẫn dùng được. | Credential rotation incomplete. |
| IM54 | Service token issuance ngoài approved schedule. | Anomaly candidate, điều tra runner/issuer, không kết luận attacker ngay. |
| IM55 | CI/CD dev principal assume production admin. | Privileged trust path risk. |
| IM56 | Service có app-only token nhưng báo event như user owner. | Identity attribution FAIL, tách technical actor/owner. |
| IM57 | Missing required source heartbeat 3 giờ. | Report DEGRADED/UNKNOWN, không coi zero incidents. |
| IM58 | Audit traces bị sampling loại nhưng security event vẫn có. | Dùng audit events làm evidence, công bố trace limitation. |
| IM59 | API PEP log ALLOW nhưng DB transaction rollback. | Không ghi business action thành công. |
| IM60 | Report generator chạy lại cùng as-of/snapshot. | Reproducible metrics và idempotent release. |
| IM61 | Metric definition thay giữa hai kỳ. | Version/change log, không biểu diễn trend thiếu chú thích. |
| IM62 | Report preliminary có late event đến sau watermark. | New revision/correction audit, không sửa số âm thầm. |
| IM63 | Auditor chỉ có quyền tenant VN xem export tenant SG. | Tenant isolation DENY. |
| IM64 | Report raw storage chứa access token dù dashboard redacted. | Security/privacy FAIL và xử lý credential exposure. |
| IM65 | Một report chỉ có màu xanh nhưng 1 critical target UNVERIFIED. | Hiển thị critical gap rõ, không gộp thành overall PASS. |
| IM66 | Dashboard chart tính subject/target mix trong một tỷ lệ. | Metric definition unit mismatch FAIL. |
| IM67 | Negative probe trả DENY do API down, positive control cũng fail. | Probe UNVERIFIED, không chấp nhận proof. |
| IM68 | Secret owner Leaver vẫn có quyền đọc vault nhưng service chạy hợp lệ. | Human rights revoked riêng, workload continuity report. |
| IM69 | SoD policy editor có quyền xóa audit logs về chính mình. | Governance/tamper-resistance finding. |
| IM70 | Incident đã đóng nhưng một required path còn ALLOW. | Không VERIFIED deprovision; reopen/escalate. |

### Test oracle phải xuất phát từ nguồn nào?

- **HRIS lifecycle truth**: identity, employment epoch, effectiveAt.
- **Approved IAM policy**: required entitlements, role delta, SoD rules, exceptions.
- **Required target inventory**: những systems/access paths cần kiểm, kể cả nơi không có log.
- **Synthetic PEP/transaction outcomes**: ALLOW/DENY, no-side-effect/commit evidence có provenance.
- **Test specification**: định nghĩa “verified”, sample boundary và report as-of độc lập khỏi implementation.
- **Data quality expectations**: nếu source gap, report status không được giả SAFE.

### Kiểm thử sản phẩm reporting từ đầu đến cuối

~~~mermaid
flowchart LR
    FIX["Seed synthetic HRIS/IGA/IdP/SCIM/API events"] --> PIPE["Run normalize + temporal link"]
    PIPE --> SNAP["Build point-in-time snapshots"]
    SNAP --> CALC["Compute versioned metrics"]
    CALC --> COMP["Compare independent expected oracle"]
    COMP --> SEC["Check RBAC/privacy/export access"]
    SEC --> OUT["Verify report revision + evidence links"]
~~~

Một regression suite đúng phải thử **cả positive và negative controls**, chứ không chỉ kiểm báo cáo CSV có số dòng và KPI nhìn hợp lý.


## 39. Những sai lầm phổ biến khi xây dựng báo cáo monitoring

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Báo “Leaver done” từ số ticket completed. | Tài khoản/token/PAT vẫn ALLOW nhưng dashboard xanh. | Tách workflow completion, target readback, verified PEP DENY. |
| Chỉ đếm IdP users, bỏ SaaS/local/DB. | Leaver hoặc service account còn quyền ngoài IdP. | Inventory đầy đủ human/non-human + required paths. |
| Lấy số target có log làm mẫu số. | Target im lặng biến mất khỏi tỷ lệ coverage. | Approved required-target catalog. |
| Xem SCIM HTTP 204 là thu hồi thành công. | Local grants và JWT/session cũ vẫn dùng. | Target readback + actual effective-access probe. |
| Gộp AUTHN_FAILURE với AUTHZ_DENY. | Không biết lỗi login hay vi phạm quyền. | Event taxonomy/reason codes rõ. |
| Đếm cùng một operation retry nhiều lần. | Thổi phồng provisioning/revoke volume. | Logical operationId và attemptId tách biệt. |
| Dùng email làm join key. | Rehire/alias thay đổi, gắn nhầm người. | Authority + immutable subject + temporal mapping. |
| Dùng IP/địa lý kết luận access gian lận. | VPN/NAT/roaming tạo false positives. | Trusted multi-signal và review. |
| Sắp timeline theo ingestion timestamp. | Queue delay đảo thứ tự sự kiện. | effectiveAt/occurredAt/observedAt và causation/revision. |
| Không công bố dataAsOf/timezone. | Không tái lập metric và sai biên SLA. | Versioned report snapshot. |
| Chỉ có “success count”, không có UNKNOWN. | Bỏ sót target outage/thiếu bằng chứng. | Nhiều trạng thái, UNVERIFIED riêng. |
| Tính verified latency trên connector ACK. | Báo SLA ngắn giả tạo. | effectiveAt → PEP verifiedAt. |
| Chỉ lấy AVG latency của workflows hoàn tất. | Che những luồng chưa bao giờ hoàn tất. | Báo completion distribution, backlog age và censored cases. |
| Coi API 503 là authorization DENY. | Outage bị hiểu là đã chặn. | Positive control + policy reason proof. |
| Coi JWT expired là chứng cứ revoke sớm. | Không biết token cũ còn ALLOW trước exp. | Controlled valid-token/PEP checks theo capability. |
| Coi API AUTHZ_ALLOW là business commit. | Báo chuyển tiền/export dù transaction rollback. | Join transaction ledger và side-effect events. |
| Gộp service principal owner với actor. | Sai attribution/SoD và incident response. | Technical actor, initiating human, owner tách. |
| Xóa job của nhân viên Leaver dù workload còn hợp lệ. | Gây gián đoạn kinh doanh. | Transfer owner và revoke human controls. |
| Đếm role assignments như effective capabilities. | Role inheritance/assumeRole/direct ACL bị bỏ sót. | Effective permission reconciliation. |
| Tổng hợp cross-tenant không bảo vệ. | Lộ danh tính/quyền của khách hàng khác. | RBAC/ABAC và tenant-isolated query/export. |
| Mọi KPI đều xanh khi SIEM mất dữ liệu. | False security assurance. | Pipeline-health/report completeness indicators. |
| Metrics label chứa subjectId từng người. | Cardinality và privacy rủi ro cao. | Aggregate labels, protected references trong audit store. |
| Log raw tokens/credentials để join. | SIEM trở thành kho credential replay. | Protected tokenRef/correlation, redaction từ producer. |
| Sửa báo cáo đã phát không để revision. | Auditor không tái lập được số. | Immutable/revisioned artifacts và correction log. |
| Không có owner/deadline cho finding. | Báo cáo chỉ mô tả, không dẫn tới remediation. | Action register, escalation, SLA và verification closure. |
| Cho reviewer tự duyệt grant của mình khi SoD cấm. | Mất độc lập chứng nhận quyền. | Review actor/beneficiary/approver và effective controller. |
| Chỉ đo số người đăng ký MFA. | Không biết action critical có assurance đúng không. | Auth_time/ACR/AMR và PEP final decisions. |
| Mặc định tất cả service accounts không đăng nhập đều low risk. | API tokens/admin roles phi con người tồn dư. | Workload grants, trust, credential/owner reporting. |
| Dùng một risk score để che severity critical. | Một global admin residual bị hòa vào hàng trăm low risk. | Risk-tiered metrics, hard threshold và riêng critical findings. |
| Báo campaign review completed khi REVOKE còn pending. | Quyền được xác nhận “thu hồi” nhưng target vẫn ALLOW. | Decision-vs-execution closure tách rời. |
| Không đưa policy/version vào report. | Không biết metric thay đổi do nguồn hay cách tính. | Dictionary, source snapshots và provenance. |

### Cách kiểm một KPI trước khi đưa vào báo cáo lãnh đạo

Hãy thử trả lời đủ các câu hỏi: **Đơn vị là gì? Ai thuộc mẫu số? Có target không gửi log không? Số dựa trên event hay state? Thời điểm as-of? Có exception? Có thể drill-down evidence? Số thay đổi sau late event thế nào? Ai chịu trách nhiệm?** Nếu một câu trả lời trọng yếu không rõ, hiển thị giới hạn tin cậy thay vì báo một tỷ lệ “chính xác”.

## 40. Checklist triển khai báo cáo monitoring IAM

1. **Mục tiêu kinh doanh:** nêu rõ decision/action mà từng report hỗ trợ.
2. **Owner và audience:** IAM Ops, Security, App/Data Owner, HR, Auditor có nhu cầu và quyền truy cập riêng.
3. **Scope human + non-human:** workforce, contractors, service accounts, devices/trust theo policy.
4. **Source inventory:** HRIS, IGA, IdP, SSO, OAuth, SCIM, SaaS, DB, API/PEP, PAM, CI/CD.
5. **Required target catalog:** bao gồm target thiếu log/probe, owner và risk tier.
6. **Stable identity mapping:** authority + subject/tenant/employment epoch, không join bằng email/IP.
7. **Time-valid mappings:** handling rehire, alias, account rename và target reuse.
8. **Event taxonomy:** REQUESTED/APPLIED/READBACK/VERIFIED/RESIDUAL/UNKNOWN tách rõ.
9. **Schema version:** eventId, eventSource, principal, action/resource, policyVersion và status theo contract.
10. **Business correlation:** lifecycleEventId, operationId, attemptId và causationId đủ để nối retries.
11. **Time semantics:** effectiveAt, occurredAt, observedAt, appliedAt, verifiedAt rõ.
12. **As-of/cutoff:** reportPeriod, timezone, late data handling và provisional/final revisions.
13. **Metric definitions:** tử số, mẫu số, đơn vị, exclusions, exceptions, calculation version.
14. **No silent unknowns:** thiếu bằng chứng/coverage phải thành UNVERIFIED.
15. **Joiner coverage:** pre-start access, required entitlements, excess privileges và verified readiness.
16. **Mover coverage:** revoke/keep/grant delta, old token/session, SoD overlaps và new access.
17. **Leaver coverage:** IdP, SCIM, local apps, OAuth/PAT, privileged grants và PEP DENY.
18. **Authentication/SSO:** login success/fail, MFA strength, token/audience, session state và provider health.
19. **Risk-based access:** step-up outcomes vs final authorization, trusted risk signals và hard-deny.
20. **RBAC/ABAC:** current policy, resource/tenant, direct ACL, role inheritance và deny reasons.
21. **Access review:** campaign decisions, owners, overdue review, REVOKE execution và verified closure.
22. **Privileged access:** PAM/JIT TTL, approval/SoD, effective role expiration và breaks-glass usage.
23. **Service identity:** owner, workload trust, client grants, key rotation, abnormal issuance, decommission.
24. **Connector observability:** attempts, 429/5xx, DLQ, readback, lag và target behavior.
25. **API/PEP checks:** token validity, object-level authorization, no unauthorized side effects.
26. **Residual access metrics:** actual ALLOW after effectiveAt, reason/target/action/owner.
27. **Target verification:** positive control + valid negative probe, healthy target, policy reason.
28. **Risk-tiered SLA:** deadline theo business/risk, không một con số giả cho mọi app.
29. **Incident integration:** critical findings có containment, owner, action deadline và closure evidence.
30. **Data quality:** completeness, uniqueness, late events, clock drift, mapping confidence, freshness.
31. **Pipeline resilience:** collector health, audit delivery, buffered retries, incident khi monitoring blind.
32. **Reproducibility:** source snapshot, policy/catalog versions, metric code version, report revision.
33. **Privacy:** personal data minimization, protected refs, tenant boundaries, credential redaction.
34. **Security:** controlled export, encryption, audit readers, SoD report producers/evidence admins.
35. **Audience-tailored dashboard:** executive trends khác analyst protected details.
36. **Unknown/no-data rendering:** phân biệt N/A, zero, missing và UNVERIFIED.
37. **Regression testing:** synthetic events, independent oracle, positive/negative and boundary tests.
38. **Performance:** query cost/size, indexing, cardinality và timely report generation.
39. **Governance:** phê duyệt report definition, exception expiry, owner attestation và audit sign-off.
40. **Action register:** mỗi finding có severity, target, owner, remediation, verified status.
41. **Success criteria:** chứng minh cả legitimate ALLOW và unauthorized DENY tại required systems.
42. **STEP 4 scope:** sau khi viết Knowledge, Content QA chuyên môn là vòng riêng; không coi file WRITTEN là đã kiểm định thực tế.

### Điều kiện nghiệm thu tối thiểu

- Mỗi KPI có **source, scope, numerator, denominator, time window và version**.
- Leaver/Mover report **không nhầm SCIM ACK/IdP disable với PEP DENY**.
- Có **required target inventory** để phát hiện missing coverage.
- Có **temporal stable identity mapping**, không false join.
- Có **unknown/exception/outage states** và action owners.
- Report replay cùng as-of/snapshots cho kết quả có thể giải thích, audit bảo vệ dữ liệu.
- Có test xác nhận **đúng quyền được ALLOW** và **quyền bị thu hồi bị DENY** theo policy.


## 41. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** Báo cáo monitoring IAM khác dashboard vận hành thuần túy ở đâu?

**Trả lời:** Báo cáo cần liên kết **quyết định nghiệp vụ, định nghĩa chỉ số, phạm vi và evidence**, không chỉ hiển thị đồ thị. Dashboard có thể là giao diện của báo cáo nhưng không thay report metadata và auditability.

**Câu 2.** Vì sao không thể kết luận “Leaver an toàn 100%” khi 100/100 workflow IGA completed?

**Trả lời:** Workflow completed có thể chỉ là connector/IdP state. Token, local PAT, direct ACL hoặc API/PEP vẫn có thể ALLOW. Cần kiểm tất cả **required paths** bằng target readback và **effective-access DENY** theo policy.

**Câu 3.** Mẫu số đúng để đo Leaver verification coverage là gì?

**Trả lời:** **Tổng required access paths** thuộc approved cohort/target catalog (hoặc tổng Leaver epochs nếu metric định nghĩa theo người và yêu cầu all paths). Không lấy số target có log làm mẫu số.

**Câu 4.** Khi không có required paths trong cohort, verified coverage bằng bao nhiêu?

**Trả lời:** **N/A hoặc không áp dụng** nếu catalog khẳng định không có path; không tự báo 100%. Nếu catalog/inventory thiếu, trạng thái cần là UNKNOWN.

**Câu 5.** 405/420 required paths đã verified DENY. Có thể nói bao nhiêu trong 100 Leavers đã an toàn hoàn toàn?

**Trả lời:** **Chưa thể suy ra** nếu không biết 15 paths chưa verified/residual thuộc Leaver nào và còn những paths bắt buộc nào. Coverage theo path ≠ all-target completion theo person.

**Câu 6.** Tại sao effectiveAt và verifiedAt phải tách biệt?

**Trả lời:** effectiveAt là lúc chính sách yêu cầu ngừng quyền, verifiedAt là lúc có bằng chứng PEP thực sự từ chối. Hiệu **verifiedAt − effectiveAt** cho biết độ trễ thu hồi với điều kiện evidence hợp lệ.

**Câu 7.** SCIM trả HTTP 204 và target readback cho thấy role đã gỡ. Có cần kiểm API không?

**Trả lời:** Có khi policy yêu cầu effective-access proof, vì JWT, app-local session/PAT, cache hoặc đường API khác có thể vẫn ALLOW.

**Câu 8.** API trả 503 trong negative probe, báo cáo nên ghi gì?

**Trả lời:** **UNVERIFIED_OUTAGE**, không tính policy DENY. Cần positive control chứng minh target hoạt động và probe phù hợp để verify.

**Câu 9.** Vì sao không nên dùng email làm khóa join duy nhất cho HRIS, IdP và SaaS?

**Trả lời:** Email có thể đổi/tái sử dụng, có alias và không phân biệt tenant. Dùng **stable authority-scoped ID**, verified target mappings và valid-time intervals, đặc biệt với rehire.

**Câu 10.** Một Mover giữ quyền old Creator qua token cũ, role new Approver đã cấp. Báo cáo cần gì?

**Trả lời:** Báo **SoD overlap/residual old-right**, token/session state, old action PEP DENY verification và new approved grant. Không gọi Mover completed chỉ vì role mới provisioned.

**Câu 11.** Vì sao reviewer chọn REVOKE không đồng nghĩa quyền đã được gỡ?

**Trả lời:** Review decision mới là desired governance state; cần connector execution, target readback và effective PEP result. Báo PENDING_REMEDIATION cho item chưa verified.

**Câu 12.** User có 3 account khác nhau. Báo cáo tổng số identities bằng tổng số accounts được không?

**Trả lời:** Không. Person/workload principal, target account và effective access paths là các đơn vị khác nhau; phải nêu metric unit, tránh double counting.

**Câu 13.** Làm sao phát hiện service account orphaned?

**Trả lời:** So inventory of non-human identities/grants với **approved business purpose, active owner, application/job, trust, review/expiry và telemetry**. Không có usage logs không đủ kết luận không dùng.

**Câu 14.** Owner batch account là nhân viên Leaver. Có nên tự xóa job không?

**Trả lời:** Không khi job còn nhiệm vụ hợp lệ. Cần **transfer owner**, revoke human access, kiểm vault/CI-CD/credential rotation và giữ service continuity. Workload decommission là quy trình riêng khi business purpose kết thúc.

**Câu 15.** Vì sao một application chỉ ghi AUTHZ_ALLOW không chứng minh payment đã commit?

**Trả lời:** Authorization quyết định cho phép, transaction có thể timeout hoặc rollback. Cần join business ledger/commit event nếu báo cáo cần kết luận actual effect.

**Câu 16.** Báo cáo nên xử lý event đến muộn như thế nào?

**Trả lời:** Dùng occurredAt/effectiveAt đúng semantics, lưu observedAt/ingestion lag, công bố watermark/dataAsOf, phát **report revision/correction** nếu late events làm thay đổi số; không sửa bản đã ký âm thầm.

**Câu 17.** Tại sao P95 revocation latency của nhóm đã verified có thể gây hiểu nhầm?

**Trả lời:** Các trường hợp chưa bao giờ verified có thể bị loại khỏi mẫu, dẫn tới **selection bias**. Cần báo riêng pending/unverified/overdue count và age, không chỉ thống kê completed.

**Câu 18.** Một JIT role hết hạn ở PAM UI nhưng target còn chấp nhận assumeRole. Báo cáo nào phát hiện?

**Trả lời:** **Privileged access/JIT expiry enforcement report**, nối activation expiry, target role readback và negative probe tại target/PEP.

**Câu 19.** Tại sao risk score thấp không làm một quyền global admin tồn dư trở nên vô hại?

**Trả lời:** Mức độ nhạy cảm và blast radius phải xem độc lập với số lượng và risk score. Một admin grant cross-tenant có thể là finding critical dù các metric tổng khác tốt.

**Câu 20.** Một user đã đăng ký MFA nhưng không dùng phương thức đủ mạnh cho payment approval. Báo cáo compliance nên tính thế nào?

**Trả lời:** Tách **enrollment coverage** khỏi **actual assurance at action**; cần auth_time, factor/ACR contract đáng tin và quyết định PEP cuối.

**Câu 21.** Vì sao không nên log raw access token để dễ tương quan?

**Trả lời:** Raw bearer token là credential có thể bị replay. Dùng protected token references/correlation, secret redaction và RBAC; lưu issuer/client/audience/time metadata cần thiết.

**Câu 22.** Nếu report job chạy lại với cùng source snapshot và calculation version, kết quả cần ra sao?

**Trả lời:** **Reproducible/idempotent** theo data contract, trừ khi có correction đã version hóa. Cần lưu reportVersion, sourceSnapshotRef, policy/catalog versions và asOf.

**Câu 23.** “No alerts this week” có chứng minh zero incidents không?

**Trả lời:** Không khi hệ thống giám sát có thể **mất log, sampling, blind spots hoặc detection gaps**. Cần data quality/coverage monitoring riêng, không suy không thấy = không có.

**Câu 24.** Mục tiêu cuối của báo cáo monitoring IAM là gì?

**Trả lời:** Biến dữ liệu danh tính và quyền thành **quyết định có trách nhiệm**: các quyền hợp lệ được hỗ trợ, các quyền hết hiệu lực bị chặn đúng SLA, những nơi không chắc chắn được hiển thị, và mọi vấn đề có **owner, hành động, bằng chứng xác minh**.

## 42. Tham khảo nền tảng và các điểm cần đối chiếu khi triển khai

| Chủ đề | Tài liệu/hệ sinh thái liên quan | Điều cần kiểm tại hệ thống thật |
| --- | --- | --- |
| **IAM/account management controls** | NIST SP 800-53 nhóm Access Control, Audit and Accountability và các control áp dụng. | Owner, approvals, recertification, audit evidence và exceptions. |
| **Security log management** | NIST SP 800-92; OWASP Logging Cheat Sheet. | Logging schema, completeness, redaction, integrity, incident use. |
| **Identity authentication assurance** | NIST SP 800-63 series. | IdP/MFA/step-up, session age, account recovery và risk. |
| **ABAC** | NIST SP 800-162 và policy engine specs. | Subject/resource/context attributes và PEP/PDP decisions. |
| **SCIM** | RFC 7643 và RFC 7644. | User/group provisioning, target account mapping, PATCH/bulk/readback. |
| **OAuth tokens** | RFC 6749/6750, token revocation RFC 7009, introspection RFC 7662 và các cập nhật áp dụng. | Access/refresh token lifecycle, issuer/audience, RS enforcement. |
| **OIDC/SSO** | OpenID Connect Core, SAML 2.0 profile khi dùng federation. | Session, subject, authentication/authorization separation. |
| **Distributed event correlation** | W3C Trace Context, OpenTelemetry. | trace/operation correlation, sampling, async retries, privacy. |
| **Incident and audit process** | Quy trình SOC/IGA/HRIS nội bộ và policies của từng ứng dụng. | EffectiveAt/verifiedAt, severity, target owners, risk acceptance. |
| **Metrics and SLO** | SRE/error budget/reporting practices của tổ chức. | SLO, time windows, censored cases, target availability, dataAsOf. |
| **Data privacy and retention** | Quy định pháp luật và chính sách dữ liệu áp dụng cho doanh nghiệp. | Lawful purpose, field access, data classification, retention, exports. |

**Tài liệu nguồn không thay thế kiểm chứng platform:** Mỗi IdP, SaaS, SCIM connector, IAM/PAM vendor và API có semantics riêng. Khi triển khai phải đối chiếu **phần nào có readback, phần nào hỗ trợ effective-access probing, timestamp nào đáng tin, chính sách thu hồi trong bao lâu và bộ quyền nào là bắt buộc**. Không giả định mọi tiêu chuẩn hoặc vendor có cùng một trạng thái “revoked” tức thời.

---

**Ghi nhớ:** **Báo cáo monitoring IAM tốt không đo thành công bằng số lệnh cấp/thu hồi đã gửi, mà đo bằng trạng thái danh tính và quyền hiệu lực được chứng minh theo chính sách.** Với **Joiner–Mover–Leaver**, hãy nối **HRIS → IGA/approval → IdP/SSO/OAuth → SCIM/target account → RBAC/ABAC/PEP → audit/evidence**; giữ rõ **subject authority, target, entitlement, cohort, effectiveAt, appliedAt, verifiedAt, dataAsOf và mẫu số**. Phân biệt **ACK, readback, VERIFIED DENY, RESIDUAL ALLOW và UNVERIFIED**, báo riêng tài khoản phi con người, SoD, token/session và các gaps giám sát. Một báo cáo có giá trị khi giúp **người có quyền hợp lệ tiếp tục làm việc, quyền tồn dư được phát hiện và chặn, ngoại lệ được quản trị, dữ liệu thiếu không bị giấu và mỗi finding có owner cùng bằng chứng khắc phục**.
