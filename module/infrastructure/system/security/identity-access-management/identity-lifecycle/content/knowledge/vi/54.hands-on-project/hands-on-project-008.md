# Dự án thực hành: Chạy access review cho vòng đời danh tính IAM

## 1. Bối cảnh, mục tiêu và đầu ra

**Access review** hay **access certification** là chiến dịch rà soát định kỳ hoặc theo biến cố nhằm xác nhận danh tính nào đang giữ quyền truy cập, quyền đó còn cần thiết hay không và ai có thẩm quyền phê duyệt. Khác với thao tác liệt kê tài khoản, một access review có giá trị phải đi từ **kiểm kê quyền thực tế → quyết định KEEP/REVOKE/ESCALATE → thực thi thu hồi → xác minh tại hệ thống đích**.

Trong module `SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE`, bài thực hành gắn với **Joiner–Mover–Leaver (JML)**. Khi Joiner, quyền phải phù hợp vai trò mới; khi Mover, không được tích lũy quyền từ vai trò cũ; khi Leaver, mọi đường truy cập không còn hợp lệ phải được thu hồi. Dữ liệu thường nằm phân tán giữa HRIS, IAM, Identity Provider (IdP), SSO, SCIM, các mô hình RBAC/ABAC, ứng dụng có role cục bộ và service account. Do đó, người thực hiện cần thu thập và đối soát nhiều nguồn, thay vì chỉ phê duyệt danh sách group trong IdP.

**Đầu ra cần nộp** gồm: phạm vi chiến dịch; inventory và snapshot danh tính–quyền; ma trận reviewer; bằng chứng quyết định; danh sách yêu cầu remediation; kết quả readback và kiểm thử quyền thực tế; báo cáo KPI, ngoại lệ và bài học vận hành. Toàn bộ bài làm sử dụng tenant sandbox, danh tính giả và policy giả định; không sửa quyền thật của nhân sự.

## 2. Tình huống nghiệp vụ của dự án

Giả lập tổ chức **Northwind Labs** sử dụng HRIS làm nguồn trạng thái nhân sự, IdP để cấp nhóm và SSO, CRM hỗ trợ SCIM, hệ thống Finance sử dụng API riêng và một bot CI/CD được quản lý dưới dạng service principal.

| Danh tính | Trạng thái mới nhất | Quyền quan sát ban đầu | Điều đáng rà soát |
|---|---|---|---|
| `test-join-101` | Joiner đã active, Sales VN | `crm.customer.read.vn` | Quyền mới cấp có đúng least privilege? |
| `test-move-102` | Mover Sales → Finance | `crm.export` và `finance.report.read` | Quyền Sales cũ còn dư |
| `test-leave-103` | Leaver đã effective | Account CRM local còn active | Quyền truy cập tồn dư |
| `test-admin-104` | Active, quyền admin tạm thời đã hết hạn | `finance.payment.approve` | Đặc quyền quá hạn, có thể vi phạm SoD |
| `test-contractor-105` | Contractor hết hạn dự án | Group `project-alpha` | Quyền dự án không còn hợp lệ |
| `test-bot-106` | Service principal đang chạy CI/CD | Deploy quyền cao, owner đã Leaver | Bàn giao owner và secret |
| `test-active-107` | Active, Finance | `finance.report.read` | Quyền hợp lệ cần KEEP |

Ví dụ **quy tắc được phê duyệt trong lab**:

- Nhân viên Sales VN active được đọc khách hàng CRM VN nhưng không có quyền export toàn bộ.
- Finance active được đọc báo cáo Finance; quyền Sales cũ chỉ được giữ nếu có ngoại lệ độc lập, hợp lệ và còn hạn.
- Leaver không có quyền truy cập tương tác sau deadline thu hồi.
- Quyền admin/SoD nhạy cảm đòi phê duyệt riêng và giới hạn thời gian.
- Service principal cần owner hiện hành và quyền tối thiểu; sự kiện owner rời đi không tự động là lý do xóa bot.

Các SLA và tần suất rà soát phải lấy từ chính sách được phê duyệt khi triển khai thật. Trong lab, thiết lập rõ hạn bằng tham số thử nghiệm để kiểm tra, không coi các giá trị giả lập là chuẩn chung.

## 3. Thiết kế chiến dịch review

Tạo chiến dịch `review-jml-2026-q4-sandbox` với phạm vi các danh tính trên và quyền ở IdP, CRM, Finance, CI/CD. Xác định trước thời điểm **snapshot**, thời hạn reviewer ra quyết định và thời hạn remediation sau quyết định.

~~~yaml
campaignId: review-jml-2026-q4-sandbox
environment: sandbox
scope:
  identities: [employee, contractor, service-principal]
  targets: [idp, crm, finance, cicd]
  includeDirectGrants: true
  includeNestedGroups: true
  includeInactiveAccounts: true
snapshotAt: "2026-12-06T02:00:00Z"
decisionDueAt: "2026-12-08T17:00:00Z"
reviewPolicyVersion: "lab-policy-1"
~~~

Đây là mẫu dữ liệu mô tả chiến dịch, không phải API có sẵn của sản phẩm IAM. Việc đưa inactive account vào phạm vi nhằm phát hiện Leaver chưa bị thu hồi đầy đủ; không có nghĩa mọi account inactive phải bị xóa cùng dữ liệu lưu trữ.

Một chiến dịch đầy đủ phải định nghĩa được:

1. Ai/những gì thuộc diện rà soát: user, contractor, machine identity và quyền đặc biệt.
2. Những nguồn quyền nào được thu thập: direct grants, nested groups, role nội bộ và entitlement cấp qua SCIM.
3. Ai quyết định: manager, application owner, security hoặc người được ủy quyền hợp lệ.
4. Quyết định nào được phép: KEEP, REVOKE và ESCALATE.
5. Kết quả thế nào mới được đóng: quyết định hoàn tất hay remediation đã được readback và kiểm tra quyền thực tế.

## 4. Dựng inventory và snapshot làm bằng chứng

Không bắt đầu bằng việc yêu cầu manager bấm KEEP hàng loạt. Trước tiên phải đối chiếu nguồn danh tính hiện hành với quyền thực tế:

~~~mermaid
flowchart TD
    H[HRIS: identity status / manager] --> I[Identity inventory]
    D[IdP: groups / SSO mapping] --> G[Grant inventory]
    A[CRM / Finance: local roles / ACL] --> G
    S[Service principals / secret owner] --> G
    I --> R[Normalize identity-grant pairs]
    G --> R
    R --> V[Validate completeness / freshness]
    V --> N[Review snapshot]
    N --> O[Assign reviewer]
    O --> E[KEEP / REVOKE / ESCALATE]
    E --> P[Provision / Deprovision]
    P --> Q[Readback and access test]
    Q --> L[Evidence / findings]
~~~

Thiết kế một hàng inventory theo cấu trúc:

~~~json
{
  "personId": "test-move-102",
  "employmentStatus": "ACTIVE",
  "department": "FINANCE",
  "target": "crm",
  "entitlementId": "crm.export",
  "grantSource": "LOCAL_ROLE",
  "grantedAt": "2026-10-01T09:00:00Z",
  "observedAt": "2026-12-06T02:00:00Z",
  "reviewerId": "app-owner-crm",
  "policyVersion": "lab-policy-1"
}
~~~

Với quyền đến từ nhiều nguồn, nên định danh bằng bộ `(subjectId, target, entitlementId, grantSource)`, tránh gộp một quyền local với cùng quyền có được từ group. Sau thu hồi một grant source, **effective entitlement** có thể vẫn tồn tại qua grant source khác.

### Bảng kiểm tra tính đầy đủ

| Kiểm tra | Câu hỏi | Điều kiện đạt |
|---|---|---|
| Source coverage | Mọi target trong scope đã phản hồi? | Không có nguồn bị bỏ sót không được đánh dấu |
| Pagination | Đã thu hết các trang/nhóm kết quả? | Tổng inventory khớp phép liệt kê |
| Identity mapping | `externalId` có trỏ đúng người? | Không gộp hai identity do email trùng |
| Nested groups | Quyền kế thừa có được giải quyết? | Effective grants được phản ánh |
| Local grants | Ứng dụng có quyền trực tiếp ngoài IAM không? | Quyền cục bộ xuất hiện trong snapshot |
| Temporal validity | Dữ liệu có đúng tại mốc snapshot? | Có thời điểm và version rõ ràng |
| Machine identity | Bot có owner, scope, expiry? | Có dòng cần review và owner hoặc finding |

Nếu connector CRM bị lỗi, **không** được biến danh sách CRM thành rỗng rồi kết luận mọi quyền đã được rà soát. Trạng thái thích hợp là `UNKNOWN/INCOMPLETE`, kèm cảnh báo và yêu cầu thu thập lại.

## 5. Phân công reviewer và kiểm soát SoD

Phân công theo chính sách đã duyệt. Một sơ đồ trách nhiệm minh họa:

| Đối tượng | Reviewer đề xuất | Bổ sung |
|---|---|---|
| Role nghiệp vụ thông thường | Manager hiện hành | App owner tư vấn khi cần |
| Role ứng dụng nhạy cảm | Application owner | Security nếu thuộc privileged scope |
| SoD exception | Người duyệt độc lập | Có lý do và ngày hết hạn |
| Contractor | Sponsor hoặc owner hợp đồng | Xác minh ngày kết thúc hợp đồng |
| Service principal | Chủ sở hữu ứng dụng/workload | Security xem xét credential nhạy cảm |
| Tài khoản orphan | IAM Ops chuyển xử lý | Không tự xác nhận KEEP |

Thử trường hợp `test-move-102` đã chuyển sang Finance nhưng reviewer được lấy từ manager Sales cũ. Cần xác minh thông tin mới nhất hoặc quy tắc trách nhiệm tại snapshot; nếu người duyệt cũ không còn thẩm quyền, task phải được chuyển cho người có thẩm quyền.

Các nguyên tắc an toàn:

- Không cho reviewer tự phê duyệt đặc quyền của chính mình khi chính sách cấm.
- Nếu có ủy quyền reviewer, phải kiểm tra nguồn ủy quyền, phạm vi và thời hạn.
- Bulk approve phải tuân thủ cùng validation với quyết định riêng lẻ.
- Quyền reviewer truy cập API không đồng nghĩa quyền sửa mọi chiến dịch; kiểm tra authorization theo campaign và entitlement.
- Reviewer bị suspended hoặc Leaver không được tiếp tục ký xác nhận.

## 6. Thực hiện quyết định KEEP, REVOKE và ESCALATE

Giao cho học viên ra quyết định dựa trên bằng chứng:

| Identity | Entitlement | Quyết định dự kiến | Lý do |
|---|---|---|---|
| `test-join-101` | `crm.customer.read.vn` | KEEP | Sales VN đang active và cần quyền |
| `test-move-102` | `crm.export` | REVOKE | Đã sang Finance, không có ngoại lệ hợp lệ |
| `test-move-102` | `finance.report.read` | KEEP | Phù hợp vai trò hiện tại |
| `test-leave-103` | CRM local access | REVOKE | Leaver đã có hiệu lực |
| `test-admin-104` | `finance.payment.approve` | REVOKE hoặc ESCALATE theo policy | Đặc quyền hết hạn/cần xem SoD |
| `test-contractor-105` | `project-alpha` | REVOKE | Hết hạn dự án |
| `test-bot-106` | CI/CD deploy | ESCALATE | Cần owner mới và kiểm tra secret |
| `test-active-107` | `finance.report.read` | KEEP | Quyền hợp lệ |

**KEEP** có nghĩa reviewer xác nhận quyền tiếp tục hợp lệ trong điều kiện đã được duyệt, không phải miễn trừ khỏi những thay đổi HRIS sau thời điểm quyết định. **REVOKE** phải tạo hành động thu hồi và đối soát tại target. **ESCALATE** phải có owner, lý do và deadline; không biến thành trạng thái treo vô thời hạn.

Mẫu bản ghi quyết định:

~~~json
{
  "campaignId": "review-jml-2026-q4-sandbox",
  "subjectId": "test-move-102",
  "target": "crm",
  "entitlementId": "crm.export",
  "decision": "REVOKE",
  "reviewerId": "app-owner-crm",
  "reasonCode": "NO_LONGER_REQUIRED_AFTER_MOVER",
  "decidedAt": "2026-12-07T03:00:00Z",
  "snapshotVersion": "snapshot-001",
  "policyVersion": "lab-policy-1"
}
~~~

Ghi audit với quyết định và trạng thái thực thi **riêng biệt**; không dùng cùng một trường `completed=true` cho cả việc reviewer đã bấm REVOKE và connector đã gỡ quyền thành công.

## 7. Thực thi thu hồi và xác minh tại hệ thống đích

Sau khi reviewer chọn REVOKE, IAM có thể thực thi qua IdP group, SCIM PATCH, ứng dụng API hoặc ticket thủ công. Một ví dụ loại bỏ membership qua SCIM Group PATCH:

~~~http
PATCH /scim/v2/Groups/group-crm-sales
Content-Type: application/scim+json

{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations": [
    {"op": "remove", "path": "members[value eq \"user-102\"]"}
  ]
}
~~~

Đây là payload minh họa; SCIM server phải hỗ trợ cú pháp path/filter tương ứng. Một role local CRM không thuộc nhóm SCIM sẽ cần thao tác độc lập bằng API hoặc quy trình có bằng chứng.

~~~mermaid
sequenceDiagram
    participant R as Reviewer
    participant I as IAM
    participant D as IdP
    participant A as CRM
    R->>I: REVOKE test-move-102 / crm.export
    I->>D: Remove mapped group if any
    D-->>I: Updated
    I->>A: Revoke local role
    A--xI: Timeout
    I->>A: Read current role
    A-->>I: Role still present
    I->>A: Retry safely
    A-->>I: Removed
    I->>A: Test export with old session
    A-->>I: DENY
    I-->>R: Remediation verified
~~~

Đối với Leaver, kiểm tra đăng nhập mới, session và access/refresh token theo kiến trúc và SLA. JWT tự chứa có thể được chấp nhận tới `exp` nếu resource server chỉ kiểm chữ ký; việc disable IdP không tự động vô hiệu hóa mọi JWT. Nếu quyền bị gỡ khỏi IdP nhưng API còn trả dữ liệu, báo **residual access** và không đánh dấu remediation hoàn tất.

## 8. Đối soát quyền sau chiến dịch

Tính toán snapshot hiện hành so với quyết định, policy và trạng thái HRIS:

~~~text
desired = policy.evaluate(authoritativeIdentityState, approvedExceptions)
observed = inventory.effectiveGrants(allTargets)

unexpectedGrants = observed - desired
missingRequiredGrants = desired.required - observed

revokedButEffective = reviewedRevocations ∩ observed
~~~

Phép tính trong hệ thống thật cần giữ scope theo subject/target/permission, cùng mốc thời gian và trạng thái nguồn. Với quyền cấp qua nhiều nhánh, `revokedButEffective` có thể vẫn tồn tại mặc dù một nhánh đã được thu hồi; cần tìm grant source còn lại.

Kiểm thử thêm hai tình huống có tính quyết định:

1. **Mover cũ tới muộn:** sau khi HRIS ghi Leaver version mới, một event Mover từ queue mới tới. Việc replay không được hồi sinh quyền vì quyết định KEEP trước đó.
2. **Quyền local còn hiệu lực:** IdP báo gỡ group thành công, nhưng CRM vẫn cho phép `crm.export`. Chiến dịch phải mở finding, phân công owner và xác minh DENY sau remediation.

Mỗi sai lệch cần được liên kết với `campaignId, eventId, personId, target, entitlement, observedAt, reviewerId, owner, deadline`. Không tự động xóa tài khoản inactive đang giữ dữ liệu có nghĩa vụ lưu trữ; vấn đề là quyền thực tế có còn được sử dụng hay không.

## 9. Kiểm thử lỗi và tính bền vững của workflow

Chạy ít nhất các test sau:

| ID | Lỗi/tình huống | Kỳ vọng |
|---|---|---|
| AR-L01 | Source CRM không phản hồi khi dựng snapshot | Báo scope incomplete, không tự ghi 100% coverage |
| AR-L02 | Mapping email đổi sau Mover | Vẫn liên kết theo ID ổn định |
| AR-L03 | Reviewer không còn quyền | Chặn quyết định và reassign |
| AR-L04 | Reviewer tự duyệt privileged grant | Chặn theo policy SoD |
| AR-L05 | Bulk approve bỏ qua reason | Từ chối hoặc yêu cầu dữ liệu hợp lệ |
| AR-L06 | SCIM timeout sau khi đã gỡ grant | Lookup/readback trước retry |
| AR-L07 | Connector trả `429` | Backoff có giới hạn, giữ trạng thái pending |
| AR-L08 | App local grant tồn dư | API test phát hiện và tạo finding |
| AR-L09 | Leaver xảy ra trước quyết định KEEP cũ | Không kích hoạt lại quyền |
| AR-L10 | Session token cũ vẫn dùng được | Cảnh báo và đo theo revocation SLA |
| AR-L11 | Owner service account đã nghỉ | Escalate và bàn giao có phê duyệt |
| AR-L12 | Audit quyết định thiếu | Không đóng review là đầy đủ |

Đối với lỗi một target, phân biệt `DECISION_COMPLETE` và `REMEDIATION_PENDING/FAILED`. Retry có thể tạo thêm bản ghi audit nhưng không được tạo entitlement mới hoặc tái cấp quyền đã bị thu hồi.

## 10. Tự động hóa smoke test

Ví dụ mã giả Python sau mô tả một bài thử access review; các client và `eventually` là abstraction do test harness cung cấp:

~~~python
def test_review_revokes_stale_sales_access(review, crm, iam, policy):
    campaign = review.start_test_campaign("review-jml-2026-q4-sandbox")
    user = "test-move-102"
    grant = "crm.export"

    snapshot = review.snapshot(campaign)
    assert snapshot.contains(user, target="crm", entitlement=grant)

    reviewer = review.authorized_reviewer(campaign, user, target="crm")
    review.decide(
        campaign=campaign,
        subject=user,
        target="crm",
        entitlement=grant,
        reviewer=reviewer,
        decision="REVOKE",
        reason="No longer required after Mover",
    )

    eventually(
        lambda: grant not in crm.effective_permissions(user),
        timeout_seconds=policy.remediation_sla_seconds,
    )
    assert crm.authorize(user, "customer.export") == "DENY"
    assert iam.audit_contains(campaign=campaign, subject=user, decision="REVOKE")
~~~

Test cần bổ sung ca quyền local, phiên cũ, lỗi connector và reviewer sai thẩm quyền. Không thay toàn bộ xác minh bằng mock policy: cần gọi endpoint thực thi tại ứng dụng thử nghiệm để khẳng định hành động bị từ chối.

## 11. KPI và bằng chứng nghiệm thu

| Chỉ số | Công thức khái niệm | Lưu ý |
|---|---|---|
| Review coverage | Cặp identity–grant đã nằm trong snapshot / tổng cặp thuộc scope | Mẫu số lấy từ inventory đáng tin |
| Decision completion | Số quyết định hợp lệ / tổng quyết định cần xử lý | Chưa nói lên quyền đã bị thu hồi |
| Revocation verified | Quyền REVOKE đã thật sự hết hiệu lực / số quyền REVOKE đến hạn | Dựa trên readback và API |
| Overdue review | Task quá hạn mà chưa được quyết định | Gắn owner/escalation |
| Remediation latency | Thời gian quyết định tới khi DENY tại đích | So với SLA được duyệt |
| Orphan service identities | Số machine identity thiếu owner hợp lệ | Ưu tiên theo mức rủi ro |
| Residual access findings | Số quyền thừa vẫn hiệu lực sau deadline | Không bỏ qua do ticket đã đóng |

Đừng dùng con số “100% reviewed” khi connector không đầy đủ. Khi thiếu nguồn, đánh dấu coverage **UNKNOWN/INCOMPLETE** và nêu giới hạn rõ trong báo cáo.

## 12. Biểu mẫu kết quả chiến dịch

~~~markdown
# Access Review Campaign Report

Campaign ID:
Policy version:
Environment:
Snapshot version / time:
Campaign owner:
Decision deadline / remediation deadline:

| Subject | Target | Entitlement | Reviewer | Decision | Remediation | VerifiedAt | Evidence |
|---|---|---|---|---|---|---|---|
| test-active-107 | Finance | finance.report.read | ... | KEEP | N/A | ... | ... |
| test-move-102 | CRM | crm.export | ... | REVOKE | ... | ... | ... |
| test-leave-103 | CRM | local-access | ... | REVOKE | ... | ... | ... |
| test-bot-106 | CI/CD | deploy | ... | ESCALATE | ... | ... | ... |

Scope gaps and freshness:
Reviewer / SoD exceptions:
Outstanding remediations:
Evidence references:
Final approver:
~~~

Audit tối thiểu gồm chiến dịch, snapshot, reviewer, quyền, quyết định, lý do, thời điểm, thao tác thu hồi, phản hồi connector, readback và kết quả kiểm thử. Tránh ghi mật khẩu, token, secret, payload HR hay dữ liệu khách hàng nhạy cảm vào báo cáo.

## 13. Kế hoạch thực hiện dự án

### Giai đoạn A — Chuẩn bị

Xác định scope, chính sách, tenant thử, reviewer, ngày snapshot, SLA và quyền được mô phỏng. Chuẩn bị account và quyền giả tương ứng bảng tình huống.

### Giai đoạn B — Thu thập

Đọc inventory từ HRIS, IdP, ứng dụng và service principal. Kiểm pagination, ID, freshness và đường cấp quyền. Chặn tuyên bố coverage hoàn chỉnh nếu còn connector bị thiếu.

### Giai đoạn C — Ra quyết định

Giao reviewer, kiểm SoD, ghi KEEP/REVOKE/ESCALATE với căn cứ. Thử reviewer sai thẩm quyền và bulk approval để chứng minh validation.

### Giai đoạn D — Thực thi và xác minh

Gửi remediation tới IdP/SCIM/API, xử lý lỗi, readback role/group, thử ALLOW/DENY bằng API/session thực tế và đối soát với HRIS.

### Giai đoạn E — Báo cáo

Tính coverage, decision completion, verified revocations, findings còn mở và độ trễ. Ghi bài học, owner và hạn xử lý cho mọi sai lệch.

## 14. Rubric chấm dự án

| Tiêu chí | Điểm tối đa | Bằng chứng |
|---|---:|---|
| Xác định phạm vi và chính sách rõ | 10 | Campaign definition và tiêu chí |
| Snapshot đầy đủ gồm nested/local grants | 20 | Inventory và đối soát nguồn |
| Reviewer đúng thẩm quyền, có SoD | 15 | Reviewer mapping và test âm tính |
| Quyết định có căn cứ, audit đầy đủ | 15 | KEEP/REVOKE/ESCALATE records |
| Thực thi và xác minh quyền tại đích | 20 | SCIM/API readback và access DENY |
| Xử lý lỗi, stale event, service account | 10 | Fault-injection findings |
| Báo cáo KPI, owner, remediation | 10 | Report có số liệu và giới hạn |
| **Tổng** | **100** | **Đạt từ 80 điểm và không để quyền tồn dư nghiêm trọng chưa xử lý** |

Điểm số là rubric học tập, không thay thế tiêu chuẩn kiểm toán hoặc yêu cầu tuân thủ thật. Một chiến dịch không an toàn chỉ vì đã đạt tỷ lệ reviewer bấm duyệt cao.

## 15. Câu hỏi tự đánh giá

1. Tại sao snapshot chỉ chứa IdP group chưa đủ để rà soát quyền CRM?
2. Khi manager đổi do Mover, cần xác định reviewer theo nguồn nào?
3. REVOKE khác gì với việc đã xác minh quyền không còn hiệu lực?
4. Nếu một quyết định KEEP được gửi sau Leaver, hệ thống phải xử lý thế nào?
5. Khi SCIM trả timeout sau khi đã thu hồi, có nên gửi thao tác khác ngay không?
6. Đâu là cách chứng minh quyền cục bộ và phiên cũ không còn cho phép truy cập?
7. Vì sao service account thiếu owner cần ESCALATE thay vì tự động xóa?

**Kết luận:** Chạy access review không phải công việc đánh dấu checkbox. Một chiến dịch hữu ích phải **đủ phạm vi, có người duyệt có thẩm quyền, quyết định dựa trên trạng thái JML hiện hành, thu hồi quyền thật sự và ghi nhận bằng chứng**. Đây là cách ngăn tích lũy entitlement khi Joiner, Mover hoặc Leaver và giảm quyền truy cập tồn dư trong hệ thống IAM.
