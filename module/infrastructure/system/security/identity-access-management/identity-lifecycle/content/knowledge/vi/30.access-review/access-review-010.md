# Báo cáo access review: đo lường, giải trình và chứng minh quyền truy cập đã được rà soát

Một chiến dịch rà soát quyền truy cập thông báo **“98% completed”**. Ban quản lý yên tâm, nhưng kiểm toán viên phát hiện hàng chục tài khoản của nhân viên đã nghỉ vẫn còn quyền trong ứng dụng SaaS. Nguyên nhân không nằm ở phép tính 98%: hệ thống chỉ đo **số quyết định mà reviewer đã nhấn Approve/Reject**, còn những lệnh thu hồi thất bại, tài khoản ngoài phạm vi chiến dịch và phiên đăng nhập còn hoạt động đều không được thể hiện.

Một **báo cáo access review (báo cáo rà soát quyền truy cập)** tốt phải trả lời đầy đủ: **ai hoặc workload nào có quyền gì, quyền đó thuộc phạm vi nào, ai đã đánh giá dựa trên căn cứ nào, quyết định cuối cùng ra sao, thay đổi đã thực sự được thi hành ở đích chưa, và những rủi ro nào vẫn còn tồn tại**. Báo cáo không chỉ đếm số ticket đã đóng; nó là phương tiện điều hành, kiểm toán và phát hiện **quyền truy cập tồn dư (residual access)**.

Bài học thuộc chương **Access review**, chủ đề trực tiếp **Báo cáo access review**, của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Mô-đun bao quát quản lý vòng đời danh tính **Joiner–Mover–Leaver (JML)**, từ xác minh danh tính, tạo tài khoản, cấp quyền tới rà soát và thu hồi khi thay đổi vai trò, kết hợp **HRIS, IAM/IGA, IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ và kiểm toán** nhằm giảm quyền truy cập dư thừa.

Sau bài học, người học có thể:

- Xác định **mục đích, độc giả, phạm vi, mốc thời gian và mẫu số** của báo cáo.
- Phân biệt **coverage, review completion, decision quality, remediation và verified access**.
- Thiết kế **dữ liệu hạt nhân**, khóa định danh, snapshot, provenance và lineage từ nguồn nhân sự tới quyền ở ứng dụng.
- Định nghĩa KPI có công thức, chỉ rõ trạng thái **PENDING, RETAIN, REVOKE, REDUCE, EXCEPTION và VERIFIED**, tránh báo cáo gây hiểu nhầm.
- Đưa **quyền đặc quyền, SoD, Mover/Leaver, service/workload accounts, app-local roles và session/token** vào đánh giá rủi ro.
- Soạn hai lớp báo cáo **executive** và **operational/audit**, có bảng số liệu minh họa và hành động theo owner.
- Áp dụng kiểm tra chất lượng, bảo vệ dữ liệu nhạy cảm, truy vết quyết định và xác minh thu hồi tại hệ thống đích.

## 1. Báo cáo access review là gì?

**Access review** là quá trình xác nhận rằng những quyền đang được gán hoặc thực sự có hiệu lực vẫn phù hợp **nhiệm vụ, quan hệ làm việc, phạm vi tài nguyên, mức nhạy cảm và chính sách tổ chức**. **Báo cáo access review** tổng hợp bằng chứng và kết quả của quá trình đó để nhiều nhóm có thể đưa ra quyết định, xử lý sai lệch và kiểm toán.

Một bản báo cáo cần phục vụ tối thiểu ba lớp mục tiêu:

1. **Governance:** chủ sở hữu quyền có thể chứng minh quyền đang có là cần thiết, được phê duyệt và tuân thủ chính sách.
2. **Security operations:** đội vận hành biết **quyền nào cần thu hồi/giảm phạm vi, tài khoản nào chưa xác minh và hệ thống nào đang tồn dư**.
3. **Audit/assurance:** có thể truy vết từ **phạm vi rà soát → bằng chứng reviewer đã xem → quyết định → lệnh cấp/thu hồi → kết quả thực tế**.

### 1.1. Những gì báo cáo phải làm rõ

| Câu hỏi | Dữ liệu bắt buộc | Sai lầm thường gặp |
| --- | --- | --- |
| **Có rà soát đầy đủ đối tượng không?** | Population có thẩm quyền, inventory từ đích, trường hợp ngoài phạm vi. | Chỉ tính những item đã được đưa vào campaign. |
| **Ai đã rà soát?** | Reviewer identity, authority, thời điểm, delegation. | Chỉ lưu tên hiển thị hoặc email reviewer. |
| **Rà soát quyền nào?** | Effective entitlement, resource, scope, role/permission mapping. | Chỉ ghi “được duyệt nhóm X” mà không biết nhóm cho phép gì. |
| **Kết luận là gì?** | RETAIN, REVOKE, REDUCE, INVESTIGATE, EXCEPTION... | Gộp tất cả thành “completed”. |
| **Đã thi hành chưa?** | Remediation task và phản hồi provider. | Coi reviewer bấm Revoke là quyền đã mất. |
| **Đã xác minh quyền thật chưa?** | Readback và kiểm authorization ở ứng dụng đích. | Chỉ tin HTTP 200/204 từ connector. |
| **Còn rủi ro gì?** | Residual access, SoD, orphan accounts, exceptions, data gaps. | Báo cáo tỷ lệ đẹp mà ẩn sai lệch. |

### 1.2. Báo cáo không thay thế quyền kiểm soát

Báo cáo là **bằng chứng và công cụ điều hành**, không phải cơ chế thu hồi quyền. Hệ thống vẫn cần:

- Policy về **least privilege, RBAC/ABAC, Separation of Duties (SoD)**.
- Quy trình phê duyệt và owner chịu trách nhiệm.
- Connector tới IdP, directory, SCIM, ứng dụng và PAM.
- Đối soát **expected state** với **actual/effective access**.
- Xử lý exception, sự cố và xác minh sau khắc phục.

## 2. Ai sử dụng báo cáo và cần nhìn thấy gì?

Một báo cáo duy nhất thường không thể trình bày mọi trường ở cùng mức chi tiết.

| Độc giả | Câu hỏi ưu tiên | Hình thức phù hợp |
| --- | --- | --- |
| **Ban lãnh đạo / risk committee** | Rủi ro lớn còn lại là gì, tiến độ giảm rủi ro ra sao? | Executive summary có KPI và top risks. |
| **IAM/IGA operations** | Item nào đang chờ, lỗi connector nào, ai cần xử lý? | Dashboard/trang chi tiết theo status, SLA và owner. |
| **Business/data owner** | Quyền của nhóm dữ liệu/tài nguyên tôi sở hữu còn phù hợp không? | Report theo app/role/scope với quyết định và căn cứ. |
| **Security / PAM** | Có standing admin, SoD conflict, JIT eligibility hay session tồn dư không? | Privileged/SoD risk view. |
| **HR/lifecycle operations** | Leaver/Mover có quyền chưa thu hồi hoặc mapping sai không? | JML exception và trạng thái theo effectiveAt. |
| **Audit/compliance** | Có đủ phạm vi, bằng chứng và truy vết quyết định không? | Audit evidence register, snapshot và event lineage. |
| **Application owner/IT** | Phải sửa quyền nào ở đích, quyền thực tế đã đúng chưa? | Remediation queue, provider status và verification evidence. |

**Nguyên tắc trình bày:** báo cáo tổng hợp trả lời **“có vấn đề gì và ai chịu trách nhiệm?”**, còn drill-down trả lời **“quyền nào, từ nguồn nào, được quyết định ra sao và xác minh bằng gì?”**.

## 3. Xác định phạm vi trước khi tính tỷ lệ

Tỷ lệ sẽ gây hiểu nhầm nếu không xác định **population**. Phạm vi cần được chốt theo:

- **Kỳ rà soát:** bắt đầu, kết thúc, report as-of, múi giờ.
- **Đơn vị tổ chức/tenant:** công ty, business unit, dự án, vùng quản lý.
- **Loại danh tính:** Employee, Contractor, Partner, External, Service account, Workload.
- **Ứng dụng:** IdP, directory, SaaS, on-prem, cloud account, database, API, PAM.
- **Loại quyền:** direct role, group membership, app-local grant, delegated privilege, JIT eligibility, active elevation, API credential.
- **Mức rủi ro:** tất cả quyền hay chỉ privileged/high-risk.
- **Quy tắc loại trừ:** những hệ thống, account, quyền không thuộc kỳ và lý do chính đáng.

### 3.1. Ba tập hợp không được đánh đồng

~~~text
In-scope population
  = tất cả quyền/subject-target pairs phải review theo policy

Campaign population
  = các item đã được tạo và giao cho reviewer trong chiến dịch

Completed decision population
  = các item đã có quyết định reviewer hợp lệ
~~~

Nếu có 1.200 item phải rà soát nhưng hệ thống chỉ tạo 1.140 item trong campaign và nhận được 1.000 quyết định, thì:

- **Coverage** = 1.140 / 1.200 = **95%**.
- **Decision completion trên campaign** = 1.000 / 1.140 ≈ **87,72%**.
- **Decision completion trên toàn population** = 1.000 / 1.200 ≈ **83,33%**.

Ba tỷ lệ trả lời **ba câu hỏi khác nhau**. Một dashboard chỉ hiển thị 87,72% mà bỏ 60 item chưa được đưa vào campaign sẽ làm mất thông tin quan trọng.

### 3.2. Định nghĩa review item và mẫu số

Một review item có thể là:

~~~text
reviewItem = (
  campaignId,
  principalId,
  targetSystemId,
  entitlementId,
  resourceScopeId,
  grantPathId?  // nếu một quyền có nhiều nguồn cấp cần rà soát riêng
)
~~~

Đây là mô hình khái niệm, **không phải khóa duy nhất mặc định của mọi IGA**. Cần quyết định:

- Một người giữ cùng role qua hai nguồn **đếm một quyền hiệu lực hay hai grant paths**?
- Một role áp dụng cho ba tenant **đếm một hay ba item**?
- Một group có một nghìn thành viên **đếm theo group hay từng subject-group assignment**?
- Một item có hai reviewer **đếm một quyết định item hay hai approval steps**?

Định nghĩa mẫu số phải **ổn định, được tài liệu hóa và hiển thị trong báo cáo**. Không nhân đôi item chỉ vì có nhiều lượt phê duyệt hoặc retry connector.

### 3.3. Loại trừ phải có căn cứ

Ví dụ một service principal được loại khỏi campaign Employee không có nghĩa **không cần review**; nó có thể phải được đánh giá trong **non-human privileged review** riêng. Phải ghi **reason, policy owner, approvedBy, effectiveAt/expiry và campaign chịu trách nhiệm thay thế**. Không dùng loại trừ để làm tăng tỷ lệ hoàn thành.

## 4. Nguồn dữ liệu và kiến trúc tổng hợp

Access review không chỉ lấy dữ liệu từ một hệ thống IGA. Để báo cáo đáng tin, cần kết hợp **nguồn có thẩm quyền**, dữ liệu cấp phát và **quyền thực tế**.

~~~mermaid
flowchart LR
    HR["HRIS / hợp đồng<br/>JML + hiệu lực"] --> COR["Identity correlation<br/>Person/Engagement/Workload"]
    IDP["IdP / Directory<br/>accounts + groups"] --> INV["Entitlement inventory"]
    APP["SCIM / SaaS / API<br/>local roles + grants"] --> INV
    PAM["PAM / Cloud / DB<br/>privileges + sessions"] --> INV
    OWN["Role & resource catalog<br/>owner + SoD + risk"] --> NORM["Normalize + risk classify"]
    COR --> NORM
    INV --> NORM
    NORM --> SNAP["Campaign snapshot<br/>in-scope + exclusions"]
    SNAP --> REV["Reviewer decisions<br/>attestations + evidence"]
    REV --> REM["Grant/reduce/revoke<br/>remediation tasks"]
    REM --> VER["Target readback<br/>effective-access checks"]
    SNAP --> REP["Access review reporting"]
    REV --> REP
    REM --> REP
    VER --> REP
    REP --> GOV["Executive / Operations / Audit"]
~~~

### 4.1. Nguồn nào có thẩm quyền về điều gì?

| Dữ liệu | Nguồn chủ đạo thường gặp | Điều cần kiểm |
| --- | --- | --- |
| **Person/Engagement/Start/End date** | HRIS hoặc hệ thống hợp đồng. | Có hiệu lực, đúng loại quan hệ, tránh gắn bằng email. |
| **Subject/account mapping** | IAM, directory và kết quả correlation được xác minh. | ID namespace, rehire, tài khoản phụ. |
| **Role ownership, permissions và risk** | Role catalog, app/data owner. | Phiên bản và scope. |
| **Approval/SoD/exceptions** | IGA/workflow, security governance. | Ai duyệt, quyền duyệt, policy version. |
| **Direct account/group assignments** | Directory/IdP, ứng dụng, cloud IAM. | Nested groups, role inheritance và local grants. |
| **SCIM provisioning** | Connector/provider logs và readback. | Response không luôn là quyền đã thực thi. |
| **Privileged/JIT access** | PAM/PIM và hệ thống cloud/admin đích. | Eligible vs activated, session, secret. |
| **Effective authorization** | API/ứng dụng và các điểm thực thi quyền. | Quyền không còn hợp lệ có bị từ chối thật không? |

**Một nguồn có thể là bản sao, không phải source of authority.** Ví dụ IdP claim về department thường được đồng bộ từ HRIS; chữ ký token đúng không bảo đảm giá trị còn phù hợp sau Mover.

## 5. Định danh và độ hạt (granularity) của dữ liệu

Một báo cáo cần tránh hai lỗi đối nghịch: **đếm trùng quyền** và **bỏ sót những đường cấp quyền khác nhau**.

| ID | Công dụng | Sai lầm cần tránh |
| --- | --- | --- |
| **personId** | Nhận diện con người được xác minh. | Ghép nhiều người theo email đã tái cấp. |
| **engagementId** | Phân biệt lần làm việc/hợp đồng. | Tự khôi phục quyền của engagement cũ khi rehire. |
| **subjectId** | Định danh canonical trong IAM. | Giả định duy nhất xuyên mọi tenant/issuer. |
| **accountId** | Tài khoản tại IdP/directory/ứng dụng. | Coi hai account của một Person là hai reviewer độc lập. |
| **workloadId / principalId** | Danh tính non-human. | Đếm theo nhân viên owner thay vì workload. |
| **entitlementId / permissionId** | Quyền ở hệ thống đích. | Suy luận từ tên nhóm hiển thị. |
| **resourceScopeId** | Tenant, dự án, resource, môi trường. | Coi role admin một dự án bằng role toàn tổ chức. |
| **grantPathId** | Nguồn cấp quyền trực tiếp/gián tiếp. | Gỡ một group rồi bỏ sót local grant cùng quyền. |
| **reviewItemId** | Một đơn vị review có policy rõ. | Tạo nhiều bản ghi do retry hoặc nhiều reviewer. |
| **decisionId/remediationId** | Quyết định và tác vụ khắc phục. | Đếm decision như một entitlement mới. |

### 5.1. Ví dụ quyền có nhiều đường cấp

~~~text
Person P-1042
  → app-account app-user-88
      → IdP Group finance-admins → App role admin
      → Direct app role admin (được gán thủ công)
      → Local API key có scope report.export
~~~

Khi reviewer chọn **REVOKE admin**, việc gỡ nhóm IdP có thể không làm mất direct role hoặc API key. Báo cáo cần biểu diễn **quyền hiệu lực cần loại bỏ** và **các đường cấp liên quan**. Nếu không, một remediation task thành công sẽ khiến số liệu giả định quyền đã thu hồi.

### 5.2. Phân biệt human và non-human

Human identity thường liên kết **Person/Engagement**, trong khi workload liên kết **service principal, workload, ownerTeam và ngày decommission**. Không bỏ qua workload chỉ vì không có employeeNumber; cũng không dùng account owner đã Leaver làm bằng chứng workload hết nhiệm vụ nếu hệ thống vẫn có consumer hợp lệ.

## 6. Snapshot, thời gian và tính tái lập

Báo cáo cần nói rõ **dữ liệu được chụp lúc nào**. Một báo cáo tổng hợp vào sáng thứ Hai có thể khác kết quả chạy chiều thứ Ba vì:

- HRIS phát Mover/Leaver mới.
- Role được bổ sung permission.
- Reviewer thay đổi quyết định.
- Connector retry thành công.
- Tài khoản/nhóm đích được sửa trực tiếp.
- Token hoặc session cũ hết hạn.

### 6.1. Những mốc thời gian cần lưu

| Trường | Ý nghĩa |
| --- | --- |
| **campaignStartAt, campaignDueAt** | Kỳ và hạn giao quyết định. |
| **snapshotAt** | Thời điểm đóng băng tập item và evidence đầu kỳ. |
| **reportAsOf** | Mốc tổng hợp trạng thái, phải hiển thị timezone. |
| **sourceObservedAt / sourceVersion** | Khi dữ liệu nguồn được đọc, phiên bản nào. |
| **effectiveAt** | Khi thay đổi JML/assignment phải có hiệu lực. |
| **decisionAt** | Khi reviewer quyết định. |
| **remediationDueAt** | Hạn thực thi grant/revoke/reduce. |
| **providerUpdatedAt** | Khi hệ thống đích ghi nhận thay đổi, nếu có bằng chứng. |
| **verifiedAt** | Khi đọc lại/kết luận quyền thực tế. |
| **exceptionExpiresAt** | Khi ngoại lệ hết hạn/phải được duyệt lại. |

**Không so sánh ngày theo timezone mơ hồ.** Ví dụ Start date của một Employee tại Việt Nam có thể được quy đổi theo **Asia/Ho_Chi_Minh**, trong khi log connector dùng UTC. Cần định nghĩa rõ policy xử lý **date-only**, ca trực và thời điểm hiệu lực.

### 6.2. Báo cáo dạng snapshot và dạng live

| Dạng | Dùng khi nào | Giới hạn |
| --- | --- | --- |
| **Snapshot at campaign close** | Bằng chứng kỳ rà soát, ký duyệt và tái lập kiểm toán. | Phản ánh một thời điểm, không đại diện hiện tại mãi mãi. |
| **Operational live dashboard** | Theo dõi item còn mở, retry và quyền tồn dư. | Dữ liệu đổi liên tục, cần as-of và freshness. |
| **Trend theo kỳ** | So sánh tiến bộ và SLA. | Phải chuẩn hóa population/định nghĩa KPI giữa các kỳ. |
| **Exception register** | Theo dõi rủi ro chưa đóng sau campaign. | Không được xoá khỏi báo cáo chỉ vì campaign kết thúc. |

Mỗi dòng quan trọng nên có **source reference, version và snapshot** để người kiểm toán có thể tái dựng câu hỏi “tại thời điểm đó, reviewer biết những gì?”.

## 7. Vòng đời một review item: quyết định khác kết quả

Để báo cáo chính xác, nên tách ba trạng thái:

1. **Review workflow state:** item đang chờ reviewer hay đã có quyết định?
2. **Remediation state:** có yêu cầu thay quyền không, đã gửi lệnh chưa?
3. **Access verification state:** quyền thực tế ở hệ thống đích đã đúng chưa?

### 7.1. Bảng trạng thái đề xuất

| Lớp | Giá trị minh họa | Ý nghĩa |
| --- | --- | --- |
| **Review** | IN_SCOPE, ASSIGNED, PENDING, DECIDED, EXCEPTION | Tiến độ đánh giá/attestation. |
| **Decision** | RETAIN, REVOKE, REDUCE, REPLACE, INVESTIGATE | Reviewer kết luận quyền cần làm gì. |
| **Remediation** | NOT_REQUIRED, QUEUED, IN_PROGRESS, ACKNOWLEDGED, FAILED, UNKNOWN | Lệnh kỹ thuật được xử lý tới đâu. |
| **Verification** | NOT_STARTED, PENDING, VERIFIED, NOT_MATCHED, UNVERIFIABLE | Kết quả đích đã khớp expected state chưa. |
| **Risk exception** | OPEN, ACCEPTED_TIME_BOUND, MITIGATED, RESOLVED, EXPIRED | Rủi ro còn mở và cách quản trị. |

Trạng thái trên là **mô hình gợi ý**, không phải trạng thái chuẩn bắt buộc trong IAM/SCIM. Hệ thống thật có thể dùng tên khác; quan trọng là giữ được **ý nghĩa và mối liên kết giữa các lớp**.

### 7.2. RETAIN không đồng nghĩa mãi mãi

Một quyết định **RETAIN** chỉ hợp lệ trong **điều kiện, scope, role version và thời hạn** đã đánh giá. Sau Mover, Leaver, hết hợp đồng hoặc thay permission của role, quyền đó có thể cần tái xem xét. Nếu reviewer chọn Retain nhưng role không có owner hoặc không đủ dữ liệu, đó không phải một attestation chất lượng cao.

### 7.3. REVOKE không đồng nghĩa đã thu hồi

~~~mermaid
flowchart TD
    A["Review item"] --> B{"Reviewer decision"}
    B -->|"RETAIN"| C["Kiểm scope/expiry<br/>lưu attestation"]
    B -->|"REVOKE / REDUCE"| D["Tạo remediation task"]
    B -->|"INVESTIGATE"| E["Exception có owner và hạn"]
    D --> F["Gửi lệnh tới provider"]
    F --> G{"Readback và kiểm<br/>effective access"}
    G -->|"Khớp"| H["VERIFIED + audit"]
    G -->|"Sai/không rõ"| E
    E --> I["Giảm thiểu / điều tra / retry"]
    I --> G
~~~

**Không nên báo cáo “280 quyền đã thu hồi” nếu thực tế chỉ có 280 quyết định REVOKE/REDUCE và 210 tác vụ được VERIFIED.** Hãy báo riêng **quyền cần xử lý, số đã xác minh và số còn mở**.

## 8. Các loại báo cáo nên có

### 8.1. Báo cáo tổng quan chiến dịch

Tập trung vào:

- Population in-scope, coverage, excluded/unmapped items.
- Số reviewer được phân công, số quyết định hợp lệ, pending và overdue.
- Phân bố RETAIN/REVOKE/REDUCE/INVESTIGATE.
- Số remediation yêu cầu, hoàn tất, thất bại và chưa xác minh.
- Số rủi ro nghiêm trọng: quyền Leaver còn sống, privileged grants, SoD conflicts.
- Top systems/owners có vấn đề, kế hoạch và hạn xử lý.

### 8.2. Báo cáo theo người duyệt và chủ sở hữu

Trả lời:

- Reviewer nào đang có item quá hạn?
- Người duyệt còn thẩm quyền sau thay manager không?
- Có self-review hoặc trùng người duyệt–beneficiary không?
- Những quyền nào owner không xác định hoặc review bị chuyển tuyến?
- Các quyết định đã dựa trên scope/permission cụ thể chưa?

Không dùng báo cáo reviewer để công khai dữ liệu nhân sự nhạy cảm cho mọi người. Phải giới hạn theo **need-to-know** và thẩm quyền quản trị.

### 8.3. Báo cáo theo ứng dụng/entitlement

Trả lời:

- Ứng dụng nào chưa có inventory chính xác?
- Role/group nào không có owner hoặc mapping?
- Quyền nào được gán trực tiếp ngoài IGA?
- Role nào có nhiều quyền đặc biệt hoặc SoD conflicts?
- Connector nào không thể readback hoặc thu hồi?

### 8.4. Báo cáo privileged/SoD

Bao gồm:

- Standing admins, eligible JIT roles, active privileged sessions.
- Tài khoản máy có quyền cao và owner không rõ.
- Đường nâng đặc quyền qua role assumption, chỉnh policy hoặc credential.
- SoD conflicts còn mở, ngoại lệ có hạn và mức rủi ro.
- Độ trễ và bằng chứng thu hồi privileged access.

### 8.5. Báo cáo JML và quyền tồn dư

Đặc biệt nhấn mạnh:

- **Joiner:** quyền cấp sớm trước Start date hoặc vượt birthright policy.
- **Mover:** quyền bộ phận/dự án cũ chưa bị thu hồi.
- **Leaver:** account, group, API credential hoặc session tiếp tục được chấp nhận sau effectiveAt.
- **Rehire:** quyền/approval cũ vô tình được kích hoạt lại.

## 9. KPI quan trọng và cách định nghĩa công thức

### 9.1. Nhóm coverage và review

| KPI | Công thức gợi ý | Diễn giải |
| --- | --- | --- |
| **Population coverage** | `campaignItems ÷ inScopeItems` | Bao nhiêu item bắt buộc đã được đưa vào review? |
| **Decision completion** | `validDecidedItems ÷ assignedCampaignItems` | Bao nhiêu item được giao đã có quyết định hợp lệ? |
| **Overall decision coverage** | `validDecidedItems ÷ inScopeItems` | Bao nhiêu item toàn phạm vi đã được quyết định? |
| **Timely decision rate** | `decidedByDueAt ÷ itemsDueWithinPeriod` | Quyết định có đúng hạn không? |
| **Undecided overdue count** | Số item chưa có quyết định khi `dueAt < reportAsOf` | Khối lượng xử lý trễ. |
| **Reviewer authority compliance** | `decisionsWithValidAuthority ÷ validDecisionsChecked` | Quyết định có được thực hiện bởi người có thẩm quyền? |
| **Evidence completeness** | `itemsWithRequiredEvidence ÷ itemsRequiringEvidence` | Quyết định có đủ căn cứ có thể kiểm tra? |

Lưu ý: không cộng lẫn số **review items**, số **approval steps** và số **nhân viên**. Một item qua hai reviewer vẫn là **một item** ở completion denominator, trừ khi KPI được đặt tên rõ là **approval-step completion**.

### 9.2. Nhóm remediation và thực thi

| KPI | Công thức gợi ý | Diễn giải |
| --- | --- | --- |
| **Remediation required** | Số item đã quyết định REVOKE/REDUCE/REPLACE cần thay trạng thái ở đích. | Việc kỹ thuật phải hoàn tất. |
| **Verified remediation rate** | `verifiedRemediations ÷ requiredRemediations` | Bao nhiêu thay đổi đã được xác minh? |
| **Open remediation count** | `requiredRemediations - verifiedRemediations`, có điều chỉnh cho các item hủy hợp lệ. | Việc còn mở sau review. |
| **Overdue remediation count** | Các task chưa VERIFIED vượt `remediationDueAt`. | Rủi ro chưa xử lý đúng SLA. |
| **Revocation latency** | `verifiedAt - effectiveAt` hoặc `verifiedAt - decisionAt`, ghi rõ điểm bắt đầu. | Thời gian quyền dư được loại bỏ. |
| **Failed/unknown provider actions** | Số action FAILED/UNKNOWN theo hệ thống và lỗi. | Khả năng connector/đích kém tin cậy. |
| **Residual access count** | Đường truy cập chưa hợp lệ **được xác minh còn sử dụng được**. | Nguy cơ thực tế cần giảm thiểu. |

**Open remediation không luôn bằng số lần retry lỗi.** Một task có thể retry mười lần nhưng vẫn là **một nghĩa vụ thu hồi**, có nhiều attempt logs. Cần quản lý đúng cấp item/task.

### 9.3. Nhóm chất lượng quản trị

| KPI | Cách đo | Lưu ý |
| --- | --- | --- |
| **Ownerless entitlements** | Số quyền/role không có business/application owner hợp lệ. | Nên phân biệt owner rời công ty với owner chưa từng được xác định. |
| **Orphan accounts** | Account không liên kết chắc chắn tới Person/Engagement hoặc workload/owner. | Không suy luận từ email/name. |
| **Excess privileged entitlements** | Quyền đặc biệt vượt expected/approved scope. | Tính cả indirect grants. |
| **SoD violations** | Tổ hợp quyền hoặc giao dịch xung đột chưa xử lý. | Phân biệt SSD, DSD và ngoại lệ hợp lệ. |
| **Expired assignments active** | Quyền đã vượt expiresAt nhưng hệ thống đích vẫn ACTIVE. | Ưu tiên theo mức rủi ro. |
| **JML residual access** | Quyền còn sau Mover/Leaver effectiveAt, xác minh theo phạm vi. | Không giới hạn ở IdP group. |
| **Unverifiable targets** | Số app/role/path không có cách kiểm quyền thực tế. | Không được gộp vào VERIFIED. |

### 9.4. Mẫu số bằng 0

Khi không có remediation phải thực hiện, **không tính 0/0 thành 100% một cách máy móc**. Báo KPI là **N/A (không phát sinh)**, kèm số lượng 0; cũng không hiển thị 0% như thất bại. Với report trend, nêu rõ kỳ nào KPI không áp dụng.

## 10. Tách ba ý nghĩa của “hoàn thành”

Nên trình bày ba chỉ số cạnh nhau:

~~~text
Review decision completed?  → reviewer đã có quyết định hợp lệ?
Remediation completed?      → nhiệm vụ sửa quyền đã được thực hiện?
Access state verified?      → quyền thực tế ở đích đã khớp trạng thái mong đợi?
~~~

Một item RETAIN có thể không cần remediation nhưng vẫn cần **bằng chứng căn cứ và quyền không vượt phạm vi**. Một item REVOKE cần remediation nhưng chưa chắc đã được xác minh. Một item INVESTIGATE hoặc exception không nên được tính như **giữ quyền hợp lệ** nếu còn thiếu chứng cứ.

### 10.1. Bảng sự thật

| Review | Remediation | Verification | Cách báo cáo |
| --- | --- | --- | --- |
| RETAIN hợp lệ | NOT_REQUIRED | Quyền/điều kiện đã được kiểm đủ theo policy | Đã chứng nhận giữ quyền trong kỳ. |
| REVOKE | QUEUED | NOT_STARTED | Có quyết định thu hồi, **chưa thu hồi**. |
| REVOKE | ACKNOWLEDGED | PENDING | Provider báo xử lý, **chưa xác minh**. |
| REVOKE | COMPLETED | VERIFIED | Thu hồi đã xác minh trong phạm vi. |
| REDUCE | PARTIAL/FAILED | NOT_MATCHED | Quyền cũ có thể còn; theo dõi exception. |
| INVESTIGATE | NOT_REQUIRED | UNVERIFIABLE | Chưa có quyết định cuối có căn cứ. |
| EXCEPTION accepted | MITIGATION_ACTIVE | NOT_MATCHED | Rủi ro được chấp nhận tạm thời, **không phải đã thu hồi**. |

## 11. Phân tích hạn xử lý, SLA và aging

Một báo cáo hiệu quả không chỉ cung cấp tổng số mở mà còn cho thấy **đang chậm ở đâu**.

### 11.1. Aging buckets

Ví dụ nhóm thời gian kể từ khi quá hạn:

| Bucket | Điều kiện ví dụ | Hành động |
| --- | --- | --- |
| **Chưa đến hạn** | `reportAsOf <= dueAt` | Theo dõi thường lệ. |
| **Quá hạn 1–2 ngày** | `0 < overdueDays <= 2` | Nhắc owner, ưu tiên sửa lỗi. |
| **Quá hạn 3–7 ngày** | `2 < overdueDays <= 7` | Escalate theo policy. |
| **Quá hạn hơn 7 ngày** | `overdueDays > 7` | Review rủi ro và xử lý cấp cao. |

Khoảng 1–2/3–7 ngày là **ví dụ**, không phải tiêu chuẩn bắt buộc. Privileged Leaver cần phản ứng theo chính sách nhanh hơn những quyền ít nhạy cảm.

### 11.2. Tách review SLA và revoke SLA

| SLA | Mốc bắt đầu | Mốc kết thúc |
| --- | --- | --- |
| **Reviewer decision SLA** | AssignedAt hoặc campaignStartAt theo policy. | Valid decisionAt. |
| **Remediation SLA** | DecisionAt hoặc effectiveAt theo policy. | VerifiedAt tại target. |
| **Leaver access revocation SLA** | Termination effectiveAt từ nguồn có thẩm quyền. | Effective access bị chặn và xác minh theo scope. |
| **Exception resolution SLA** | Ngày mở exception/rủi ro được phát hiện. | Resolution verified. |

Nếu Leaver có hiệu lực từ 17:00 nhưng reviewer chọn Revoke lúc 18:00, đo từ 18:00 sẽ **bỏ sót một giờ quyền tồn dư**. Hãy dùng mốc hiệu lực phù hợp với câu hỏi rủi ro.

## 12. Báo cáo reviewer, attestation và chất lượng quyết định

Một quyết định chỉ nên được xem là **hợp lệ** nếu:

1. Reviewer là **chủ thể đã xác thực** và đủ thẩm quyền với role/tenant/scope.
2. Không xảy ra **self-review, conflict of interest hoặc delegation sai** theo policy.
3. Quyết định ràng buộc với **reviewItemId, entitlement, request/campaign version** cụ thể.
4. Reviewer có đủ thông tin: nhiệm vụ, role permissions, scope, owner, expiry và risk.
5. Thời điểm quyết định nằm trong thời hạn hợp lệ, sau khi kiểm trạng thái JML cần thiết.
6. Nếu chọn RETAIN/EXCEPTION, có **lý do và căn cứ** theo mức rủi ro.
7. Nếu reviewer đã Mover/Leaver, quyết định được tái xác minh theo thẩm quyền hiện hành.

### 12.1. Không phải mọi lượt duyệt đều độc lập

Một người có tài khoản thường và admin có thể phê duyệt qua tài khoản thứ hai; **hai account IDs không phải hai con người độc lập**. Báo cáo SoD của review cần quy về **canonical subject/Person** và xác định control của service accounts/delegates.

### 12.2. Những tín hiệu chất lượng yếu

- RETAIN hàng loạt mà không xem role/permission.
- Reviewer không thuộc owner domain được phép.
- Phê duyệt sau khi requester/beneficiary đã Leaver.
- Quyền high-risk không có lý do hoặc expiry.
- Access review giao cho người đã nghỉ việc.
- Một nhóm role có tỷ lệ RETAIN gần tuyệt đối qua nhiều kỳ nhưng tăng quyền theo thời gian.

Những tín hiệu này **gợi ý cần điều tra**, không tự là bằng chứng gian lận. Có thể kết hợp sampling và kiểm tra role catalog.

## 13. SoD và privileged access trong báo cáo

Với quyền rủi ro cao, cần bổ sung cột:

- **Privileged category:** identity admin, secret manager, production operator, data export, policy changer.
- **Standing vs JIT eligible vs JIT active:** phân biệt quyền luôn sẵn có với khả năng kích hoạt.
- **Privilege escalation path:** có thể cấp role cho chính mình, assume role khác hoặc quản lý credential.
- **SoD rule IDs:** SSD/DSD/procedural conflicts, phạm vi và exception.
- **Session/credential controls:** MFA, PAM, session logging, token age và rotation metadata.
- **Independent reviewer:** có đúng risk owner và không self-review?
- **Expected revocation time:** mức ưu tiên khi owner rời tổ chức.

### 13.1. Vì sao “0 tài khoản admin” có thể sai?

Nếu chỉ đếm role có tên `admin`, có thể bỏ qua:

- Principal có quyền **tự cấp admin**.
- Người được **assume role** qua trust policy.
- Account đọc được **secret/token của admin khác**.
- Quyền sửa SSO, MFA, audit hoặc role mapping.
- Nested group dẫn tới quyền quản trị.
- Local role không xuất hiện trong IdP.

Vì vậy, privileged report cần mô hình **effective permission và đường nâng quyền**, không chỉ lọc một từ khóa.

## 14. Báo cáo Joiner–Mover–Leaver và quyền tồn dư

### 14.1. Joiner

Báo cáo nên phát hiện:

- Tài khoản đã provision nhưng **Start date chưa tới**, role nghiệp vụ đang active quá sớm.
- Nhân viên mới có role không thuộc birthright policy hoặc thiếu approval.
- Identity mapping chưa chắc chắn, duplicate accounts, app-local privilege.
- SCIM/IdP thành công nhưng ứng dụng chưa có quyền cần thiết đúng hạn.

**Không nên mặc định mọi pre-provisioned account là lỗi.** Cần so với policy và quyền sử dụng thực tế, đặc biệt các role preboarding được phép.

### 14.2. Mover

Một Mover tạo hai nghĩa vụ:

1. **Grant** quyền mới hợp lệ theo phòng ban/nhiệm vụ mới.
2. **Revoke** quyền cũ không còn căn cứ, gồm direct roles, groups, delegation và token/phiên liên quan.

Báo cáo phải chỉ rõ **expected-before, expected-after, actual-after, effectiveAt**. Nếu ứng dụng A đã thêm quyền mới nhưng ứng dụng B vẫn giữ quyền cũ, trạng thái tổng không được phép là **FULLY_VERIFIED**.

### 14.3. Leaver

Phải xác định:

- **Person/Engagement** và thời điểm chấm dứt có thẩm quyền.
- IdP/directory account, app-local account, SCIM User active state.
- Group, role, PAM/JIT eligibility, delegated grants.
- API key/PAT, session, refresh/access token và credential độc lập nếu có.
- Hệ thống đã kiểm quyền ở nơi thực thi và đường nào còn chưa quan sát.

Một account `disabled` tại IdP không chứng minh **local password, API key hoặc session đã chết**. Với residual access đã được xác minh, báo cáo cần **severity, window, target, owner, remediation và status**.

### 14.4. Rehire

Khi một người quay lại làm việc, có thể liên kết cùng Person nếu có bằng chứng, nhưng **Engagement mới** phải được đánh giá lại. Báo cáo cần phát hiện nếu role, approval hoặc credential từ engagement cũ bị tự động khôi phục khi không còn phù hợp.

## 15. Non-human identities trong báo cáo access review

Service account, workload identity, OAuth client và pipeline principals có thể có quyền cao mà không nằm trong HRIS Employee campaign.

| Trường | Ý nghĩa đối với non-human review |
| --- | --- |
| **principalId / workloadId** | Xác định chính xác danh tính máy. |
| **ownerTeam / technicalOwner** | Ai chịu trách nhiệm chứng nhận quyền? |
| **purpose / consumer** | Job, service, pipeline nào đang dùng principal? |
| **environment / tenant** | Phạm vi production, staging, development. |
| **permissionSet / resourceScope** | Quyền đúng action/resource cần dùng. |
| **credential type / expiry** | Managed identity, federation, certificate, secret, PAT... |
| **lastUsed / monitoring coverage** | Tín hiệu sử dụng có đầy đủ không? |
| **decommission state** | Workload còn hoạt động, thay owner hay đã retire? |
| **reviewDecision / verifier** | Ai giữ/giảm/thu hồi và đã kiểm chứng ở đâu? |

### 15.1. “Owner đã Leaver” là tín hiệu cần điều tra

Nếu một kỹ sư tạo service principal đã nghỉ việc, workload có thể vẫn hợp lệ nhưng phải có **owner được chuyển giao**. Không nên tự xóa principal production đang chạy, cũng không được giữ PAT cá nhân của người đã nghỉ để job tiếp tục hoạt động. Báo cáo cần thể hiện **đường chuyển đổi sang workload identity và việc giảm quyền rộng**.

### 15.2. Credential không phải review item giống user role

Một API key có thể cho truy cập theo scope khác role User. Nếu báo cáo ghi nó vào cùng tập với user-role assignments, cần rõ **khóa của item và rủi ro đếm trùng**. Có thể dùng chương trình review credential riêng, nhưng **phải xuất kết quả và uncovered risks vào báo cáo tổng hợp**.

## 16. Phân loại phát hiện: thiếu quyền, thừa quyền và quyền chưa xác định

Không phải mọi phát hiện đều là lỗi “access denied”. Báo cáo cần phân loại để đội xử lý biết phải **cấp đúng, thu hồi hoặc điều tra**.

| Loại phát hiện | Ví dụ | Tác động | Hành động |
| --- | --- | --- | --- |
| **Excess entitlement** | Nhân viên Finance còn role Sales Editor sau Mover. | Privilege creep, truy cập ngoài nhiệm vụ. | Thu hồi quyền cũ, xác minh API/ứng dụng. |
| **Missing approved entitlement** | Joiner đã được duyệt nhưng SaaS chưa có Reader role. | Công việc hợp lệ bị cản trở. | Kiểm provisioning, cấp quyền đúng scope. |
| **Unauthorized direct grant** | Admin gán quyền tại ứng dụng ngoài IGA. | Bỏ qua review/approval. | Xác minh owner/căn cứ, xử lý theo policy. |
| **Orphan account** | Local account không liên kết chắc chắn đến Person/workload. | Không rõ chủ sở hữu và quyền. | Điều tra identity mapping, kiểm soát tạm theo rủi ro. |
| **Expired entitlement active** | Quyền dự án hết hạn nhưng role vẫn ACTIVE. | Quyền tồn dư sau thời gian được duyệt. | Thu hồi và kiểm cơ chế TTL. |
| **SoD conflict** | Cùng người tạo vendor và duyệt thanh toán trong cùng scope. | Rủi ro gian lận/quản trị. | Xử lý SSD/DSD, exception nếu policy cho phép. |
| **Unverifiable entitlement** | App không hỗ trợ đọc role hoặc kiểm session. | Không thể xác nhận quyền thực tế. | Ghi data gap, biện pháp thay thế và owner. |
| **Residual access confirmed** | API vẫn chấp nhận token của Leaver. | Rủi ro truy cập đã được quan sát. | Ưu tiên khắc phục và điều tra cửa sổ rủi ro. |
| **Reviewer authority invalid** | Manager cũ duyệt request sau Mover. | Quyết định thiếu thẩm quyền. | Hủy/tái duyệt theo nguồn hiện hành. |
| **Role definition drift** | Role Reader được thêm quyền export. | Các assignment cũ rộng hơn reviewer hiểu. | Version role và tái chứng nhận khi cần. |

### 16.1. Phân biệt confirmed với suspected

Một quyền không có audit log sử dụng **không đồng nghĩa đã thu hồi**; một SCIM timeout **không chứng minh** quyền vẫn tồn tại; một tài khoản không có owner trong directory **chưa chắc** là tài khoản độc hại.

Nên có mức độ bằng chứng, ví dụ:

~~~text
CONFIRMED_RESIDUAL   = đã xác minh quyền không hợp lệ còn sử dụng được
CONFIRMED_REVOKED    = đã xác minh quyền đích không còn hoạt động
POTENTIAL_DRIFT      = dữ liệu nguồn/đích lệch, chưa kiểm quyền thực tế
UNKNOWN              = chưa có đủ dữ liệu để kết luận
NOT_IN_SCOPE         = ngoài phạm vi theo rule được ghi nhận
~~~

Từng trạng thái phải có **định nghĩa và bằng chứng**, tránh trộn “unknown” vào “không có vấn đề”.

## 17. Exception và rủi ro được chấp nhận có thời hạn

Một access review không kết thúc vì chiến dịch đóng trên giao diện. Những vấn đề chưa xử lý phải được theo dõi qua **exception register**.

### 17.1. Dữ liệu exception tối thiểu

| Trường | Nội dung cần lưu |
| --- | --- |
| **exceptionId / findingId** | Định danh không bị tạo lại mỗi lần chạy report. |
| **relatedReviewItemIds** | Những quyền/tài khoản liên quan. |
| **exceptionType / severity** | SoD, orphan, failed revoke, unknown access... |
| **riskOwner** | Người có thẩm quyền xử lý/chấp nhận rủi ro. |
| **businessJustification** | Vì sao chưa thể khắc phục hoặc vẫn cần quyền? |
| **compensatingControls** | Giám sát, giảm scope, khóa chức năng, session controls... |
| **firstObservedAt / effectiveAt** | Khi phát hiện và khi rủi ro bắt đầu phát sinh. |
| **dueAt / exceptionExpiresAt** | Hạn khắc phục, hạn chấp nhận rủi ro. |
| **approvalRef / policyVersion** | Căn cứ chấp nhận nếu được phép. |
| **verificationEvidence** | Bằng chứng quyền đã được chặn/sửa. |
| **status** | OPEN, MITIGATED, ACCEPTED_TIME_BOUND, RESOLVED, EXPIRED. |

### 17.2. Không tính exception là quyền đã an toàn

Ví dụ một SaaS không hỗ trợ thu hồi tức thời token, tổ chức có thể chấp nhận một **cửa sổ quyền tồn dư có kiểm soát** sau khi đánh giá rủi ro. Tuy nhiên, báo cáo vẫn phải giữ:

- Mốc Leaver/thu hồi được yêu cầu.
- Hạn chót và đường truy cập chưa vô hiệu.
- Người phê duyệt ngoại lệ độc lập.
- Biện pháp giảm thiểu và kết quả giám sát.
- Thời điểm cần tái đánh giá.

**“Accepted risk” không phải “Remediation verified”.** Hai trạng thái cần xuất hiện riêng và không được phép tự động triệt tiêu nhau trong KPI.

## 18. Thiết kế mô hình dữ liệu cho báo cáo

Một cấu trúc dữ liệu hợp lý thường **tách entity và event** để tránh sửa đè lịch sử:

| Entity/collection | Trường đại diện | Quan hệ |
| --- | --- | --- |
| **Campaign** | campaignId, scope, policyVersion, snapshotAt, dueAt. | Có nhiều ReviewItem. |
| **ReviewItem** | reviewItemId, principalId, entitlementId, scope, owner. | Có một hoặc nhiều DecisionEvent. |
| **IdentityLink** | subjectId, personId, engagementId, accountId hoặc workloadId. | Liên kết chủ thể với tài khoản. |
| **GrantPath** | grantPathId, source, parentGroup, role, target. | Làm rõ quyền trực tiếp/kế thừa. |
| **DecisionEvent** | decisionId, reviewerId, requestVersion, decision, decisionAt. | Lưu lịch sử thay đổi quyết định. |
| **RemediationTask** | taskId, action, target, requiredAt, dueAt, state. | Một item có thể cần nhiều thao tác đích. |
| **ProviderAttempt** | attemptId, HTTP/result, requestId, at. | Nhiều lần retry không nhân đôi nghĩa vụ. |
| **VerificationEvidence** | evidenceId, checkedAt, observedState, method. | Chứng minh kết quả ở đích. |
| **RiskException** | exceptionId, severity, owner, dueAt, status. | Theo dõi tới khi khép kín. |
| **ReportSnapshot** | reportId, asOf, denominatorVersion, sourceVersions. | Tái lập số liệu đã công bố. |

### 18.1. Ví dụ dữ liệu một review item

~~~json
{
  "reviewItemId": "ar-item-01042",
  "campaignId": "ar-2026-q4",
  "snapshotAt": "2026-11-20T10:00:00+07:00",
  "principalType": "HUMAN",
  "subjectId": "person-1042",
  "engagementId": "EMP-5812",
  "targetSystemId": "finance-saas",
  "targetAccountId": "app-user-8802",
  "entitlementId": "sales-report-exporter",
  "resourceScope": "tenant-a/sales",
  "grantSource": "APP_LOCAL_DIRECT",
  "riskTier": "HIGH",
  "reviewerSubjectId": "person-2088",
  "reviewDecision": "REVOKE",
  "decisionAt": "2026-11-18T09:00:00+07:00",
  "remediationState": "ACKNOWLEDGED",
  "verificationState": "NOT_MATCHED",
  "exceptionId": "ar-exception-0074",
  "ownerTeam": "identity-operations",
  "lastEvidenceAt": "2026-11-20T09:45:00+07:00"
}
~~~

Các ID và số liệu là **giả định**; JSON trên là **schema báo cáo minh họa**, không phải chuẩn của SCIM/OIDC/IGA. Trạng thái `ACKNOWLEDGED` và `NOT_MATCHED` cùng tồn tại có nghĩa **provider nhận lệnh nhưng quyền thực tế vẫn chưa đúng**.

### 18.2. Khóa liên kết audit

Một đường truy vết nên hoạt động như:

~~~text
HRIS event / source version
    → subjectId + engagementId
    → targetAccountId
    → entitlementId + resourceScope
    → reviewItemId
    → decisionId + reviewer + policyVersion
    → remediationTaskId
    → providerRequestId + attempts
    → verificationEvidenceId
    → exceptionId nếu chưa khép kín
~~~

Không liên kết quyền chỉ bằng **email** hoặc **displayName**. Hai giai đoạn tuyển dụng của cùng một người hoặc hai tenant có cùng username không tự chia sẻ quyền hợp lệ.

## 19. Pseudocode tổng hợp KPI không đếm trùng

### 19.1. Quy trình xử lý khái niệm

~~~text
buildAccessReviewReport(campaignId, asOf):
    scope = loadApprovedCampaignScope(campaignId)
    inScopeItems = reconstructRequiredPopulation(scope, asOf)
    campaignItems = loadCampaignItems(campaignId, asOf)

    validateStableItemKeysAndSourceIdentityMapping(inScopeItems)
    recordOutOfCampaignAndUnmappedItems(inScopeItems, campaignItems)

    for item in campaignItems:
        decision = getLatestValidAuthorizedDecision(item, asOf)
        if decision is missing:
            markPending(item)
            continue

        attachDecisionAndEvidence(item, decision)
        if decision.requiresRemediation:
            tasks = getAuthorizedRemediationObligations(item, decision)
            attachProviderAttemptsWithoutDuplicatingTasks(tasks)
            attachLatestTargetVerificationForAllRequiredPaths(tasks)

        evaluateJmlSoDPrivilegeAndResidualAccess(item, asOf)

    metrics = computeSeparateCoverageDecisionAndVerificationRates()
    reportExceptionsWithOwnerDueAtAndRisk(metrics)
    recordDataFreshnessAndUnverifiablePaths(metrics)
    publishVersionedSnapshotWithAuditReferences(metrics)
~~~

Giả mã mô tả **trách nhiệm của reporting pipeline**, không phải chương trình chạy trực tiếp. Hệ thống thật phải xác định nghiệp vụ khi **decision bị hủy, item được tách/ghép, grant path trùng và dữ liệu đến muộn**.

### 19.2. Ví dụ SQL tổng hợp

Giả sử kho báo cáo đã có **một dòng cho mỗi reviewItemId** trong bảng `review_items`, cùng cờ đã được chuẩn hóa. Query dưới dùng cú pháp kiểu PostgreSQL, nhằm minh họa **cách giữ mẫu số nhất quán**, không phải schema sẵn có:

~~~sql
-- Ví dụ, không chạy trên production nếu chưa chuẩn hóa dữ liệu.
WITH population AS (
    SELECT
        review_item_id,
        in_scope,
        in_campaign,
        assigned_reviewer,
        valid_decision,
        remediation_required,
        remediation_verified
    FROM review_items
    WHERE campaign_id = :campaign_id
      AND report_as_of = :as_of
)
SELECT
    COUNT(*) FILTER (WHERE in_scope) AS total_in_scope,
    COUNT(*) FILTER (WHERE in_scope AND in_campaign) AS in_campaign,
    COUNT(*) FILTER (
        WHERE in_scope AND in_campaign AND valid_decision
    ) AS valid_decisions,
    COUNT(*) FILTER (
        WHERE in_scope AND in_campaign AND remediation_required
    ) AS required_remediations,
    COUNT(*) FILTER (
        WHERE in_scope AND in_campaign
          AND remediation_required AND remediation_verified
    ) AS verified_remediations
FROM population;
~~~

**Điều kiện bắt buộc**: bảng đầu vào thực sự đã chứa **toàn bộ in-scope items**, kể cả chưa vào campaign. Nếu chỉ có các item trong campaign, `COUNT(*) WHERE in_scope` sẽ **không thể phát hiện 60 item bị bỏ sót**. Trong thực tế nên xây population từ nguồn độc lập theo policy và kiểm khóa duy nhất trước khi tính tỷ lệ.

### 19.3. Các bất biến dữ liệu (data invariants)

~~~text
0 <= validDecisions <= assignedCampaignItems <= inScopeItems
0 <= verifiedRemediations <= requiredRemediations
0 <= confirmedResidual <= openOrAtRiskItems

decisionRetain + decisionRevoke + decisionReduce
    + decisionReplace + decisionOtherFinal
    == validDecisions

remediationVerified không được TRUE khi không có evidence hợp lệ
reviewerSubjectId phải có authority tại decisionAt
reportAsOf và sourceVersion phải có trong mỗi snapshot
~~~

Đây là quy tắc gợi ý cho một **mô hình item/obligation nhất quán**. Nếu hệ thống có nhiều remediation tasks trên một item, phải chọn đúng **đơn vị đo** trước khi dùng công thức thứ hai; không trộn số lượng item với số lượng task.

## 20. Ví dụ thực hành: lập báo cáo chiến dịch giả định

Giả sử một tổ chức tổng hợp access review vào **20/11/2026, 10:00 (Asia/Ho_Chi_Minh)**. Campaign cần rà soát các role theo policy ở 12 ứng dụng. Các số dưới đây **hoàn toàn giả định**, dùng để minh họa cách đọc báo cáo.

### 20.1. Dataset tổng hợp

| Chỉ tiêu | Giá trị giả định | Diễn giải |
| --- | ---: | --- |
| **In-scope review items** | 1.200 | Tổng quyền/assignment phải review theo định nghĩa. |
| **Items thực tế có trong campaign** | 1.140 | 60 item chưa được đưa vào campaign. |
| **Items có valid decision** | 1.000 | 140 item trong campaign đang chờ. |
| **RETAIN** | 720 | Giữ quyền sau khi kiểm căn cứ. |
| **REVOKE** | 190 | Quyết định thu hồi. |
| **REDUCE_SCOPE** | 90 | Quyết định giảm phạm vi quyền. |
| **Remediation obligations cần xác minh** | 280 | 190 revoke + 90 reduce, mỗi item giả định một obligation. |
| **Remediation verified** | 210 | Trạng thái thực tế đã khớp. |
| **Remediation chưa verified** | 70 | Bao gồm pending, failed hoặc unknown. |
| **Remediation quá SLA** | 40 | Là một phần của 70 item chưa verified. |
| **Residual access đã xác nhận** | 7 | Là một phần những item chưa giải quyết; cần ưu tiên theo rủi ro. |

Tất cả con số tính theo **một review item/obligation** trong ví dụ; không phải số người hay số request HTTP.

### 20.2. Tính KPI và kết luận đúng

~~~text
Coverage:
    1.140 / 1.200 = 95,00%

Decision completion trong campaign:
    1.000 / 1.140 = 87,72%

Decision coverage toàn population:
    1.000 / 1.200 = 83,33%

Decision pending trong campaign:
    1.140 - 1.000 = 140 items

Items chưa có quyết định trên toàn population:
    1.200 - 1.000 = 200 items
    = 140 pending + 60 chưa được đưa vào campaign

Verified remediation rate:
    210 / 280 = 75,00%

Open remediation obligations:
    280 - 210 = 70 items

Overdue among open remediation:
    40 / 70 = 57,14%  (một tỷ lệ bổ sung, không thay verified rate)
~~~

**Kết luận không đúng:** “Campaign hoàn thành 87,72%, gần như không còn rủi ro”.

**Kết luận có cơ sở:** “95% population được đưa vào campaign; 83,33% toàn population đã có quyết định; 75% nghĩa vụ sửa quyền đã được xác minh. Vẫn còn 60 item không được bao phủ, 140 item đang chờ quyết định, 70 nghĩa vụ chưa xác minh, trong đó 40 quá SLA và 7 đường truy cập tồn dư đã được xác nhận. Cần ưu tiên xử lý theo severity và owner.”

### 20.3. Hạn review khác hạn remediation

Trong ví dụ, hạn của chiến dịch có thể là **30/11/2026**. Vì vậy, 140 item chưa quyết định vào 20/11 **chưa nhất thiết quá hạn**. Tuy nhiên, 40 nghĩa vụ sửa quyền **có thể đã quá SLA riêng** tính từ quyết định trước đó. Báo cáo phải tránh suy ra mọi pending đều overdue hoặc mọi remediation trong kỳ đều được phép chờ tới campaign dueAt.

## 21. Mẫu executive summary có thể áp dụng

Một trang executive nên ngắn nhưng không đánh đổi sự chính xác.

### 21.1. Cấu trúc báo cáo

~~~text
ACCESS REVIEW – EXECUTIVE SUMMARY
Campaign: ar-2026-q4
As-of: 2026-11-20 10:00 +07:00
Scope: 12 ứng dụng, human roles thuộc policy; non-human review báo riêng

1. PHẠM VI
   In scope: 1.200      In campaign: 1.140      Coverage: 95%
   Gap: 60 item chưa vào campaign

2. QUYẾT ĐỊNH
   Valid decisions: 1.000 / 1.200 = 83,33% toàn population
   Retain: 720          Revoke: 190             Reduce: 90
   Pending in campaign: 140

3. KHẮC PHỤC
   Required: 280        Verified: 210           Open: 70
   Verified rate: 75%   Overdue: 40

4. RỦI RO ĐÁNG CHÚ Ý
   Confirmed residual access: 7
   Uncovered population: 60
   High-risk ownerless / SoD: trình bày theo số liệu được xác minh

5. HÀNH ĐỘNG
   Ưu tiên 7 residual access theo severity và chính sách ứng cứu
   Điều tra 60 item thiếu coverage và gán reviewer
   Phân owner, hạn khắc phục cho 70 remediation còn mở
   Kiểm lỗi dữ liệu/connector và xác minh lại ở ứng dụng

6. GIỚI HẠN
   Chưa bao gồm non-human identities trong mẫu số trên.
   Trạng thái các đường không kiểm chứng phải báo riêng.
~~~

**Ví dụ hoàn toàn giả định**; các số thuộc phần 20, không phải dữ liệu thực tế của tổ chức nào. Những mục không có bằng chứng thì ghi **“chưa có số liệu”**, không được tự đặt số 0.

### 21.2. Diễn đạt rủi ro theo hành động

Thay vì viết “Ứng dụng có 12 cảnh báo”, nên nêu:

> Trong 12 phát hiện, có 3 quyền quản trị đang chờ xác minh thu hồi. Application owner phụ trách xử lý trước hạn nội bộ đã thống nhất; những đường truy cập chưa kiểm chứng vẫn nằm trong exception register.

Một executive summary tốt luôn có **mức rủi ro, owner, hạn xử lý và mức độ xác minh**.

## 22. Mẫu báo cáo vận hành chi tiết

IAM operations cần **drill-down** cho từng item, không chỉ biểu đồ.

| Item ID | Target/scope | Decision | Remediation | Verification | Risk/owner |
| --- | --- | --- | --- | --- | --- |
| AR-101 | finance-saas / tenant-a | REVOKE | SCIM sent | NOT_MATCHED | HIGH / IAM Ops |
| AR-102 | cloud-prod / project-p | REDUCE | Completed | VERIFIED | CRITICAL / Cloud Owner |
| AR-103 | directory / support | RETAIN | Not required | REVIEW_ATTESTED | LOW / Service Owner |
| AR-104 | app-sales / project-k | INVESTIGATE | Not started | UNKNOWN | HIGH / App Owner |
| AR-105 | PAM / privileged account | REVOKE | Failed | NOT_VERIFIED | CRITICAL / PAM Ops |

Các dòng chỉ minh họa cấu trúc, không phải dữ liệu thực. **REVIEW_ATTESTED** có nghĩa reviewer đã chứng nhận giữ quyền theo policy; không nên dùng nhãn đó thay cho **ACCESS_VERIFIED** khi chính sách đòi kiểm quyền trực tiếp tại resource.

### 22.1. Trang chi tiết của một item

Nên có:

1. **Nguồn và danh tính:** Person/Engagement hoặc workload/owner, account đích.
2. **Permission:** role, quyền kế thừa, grant path, resource scope.
3. **Bằng chứng reviewer:** snapshot, permission description, approval/review history.
4. **Decision:** người duyệt, thẩm quyền, lý do, version, decisionAt.
5. **SoD/risk:** xung đột, đặc quyền, session/token, exception.
6. **Remediation:** các lệnh kỹ thuật theo từng target và kết quả.
7. **Verification:** phương thức đọc lại, observedAt, kết quả còn/không còn quyền.
8. **Owner/SLA:** người xử lý, hạn và lịch cập nhật.

Cho phép lọc theo **ứng dụng, severity, owner, status và tuổi của exception**; lưu audit thao tác xem/export báo cáo nếu chứa metadata quyền nhạy cảm.

## 23. Audit evidence: chứng minh được điều gì và giới hạn nào?

Một access review report dùng cho kiểm toán cần bảo đảm **tính đầy đủ, chính xác, nhất quán và có thể tái lập**.

### 23.1. Bộ bằng chứng đề xuất

| Evidence | Chứng minh | Không tự chứng minh |
| --- | --- | --- |
| **Campaign scope & policy version** | Tổ chức dự định review đối tượng nào. | Mọi đối tượng đã được phát hiện đầy đủ. |
| **Source extraction + timestamp** | Dữ liệu nào đã được lấy từ provider. | Quyền đó không đổi sau snapshot. |
| **Identity correlation evidence** | Tài khoản liên kết đến đúng subject/workload. | Reviewer đủ thẩm quyền, nếu không kiểm riêng. |
| **Reviewer decision log** | Ai quyết định, lúc nào, với item nào. | Provider đã thực hiện revoke. |
| **SoD/approval policy result** | Xung đột đã được kiểm theo rule cụ thể. | Mọi đường quyền gián tiếp đã được quan sát. |
| **Connector request/response** | Đã gửi thao tác và nhận phản hồi nào. | Tài nguyên cuối đã hết quyền. |
| **Target readback** | User/role/group ở đích có trạng thái nào. | Token/phiên hoặc quyền qua đường khác không còn. |
| **Authorized access verification** | Một đường thực thi cụ thể đã cho phép/từ chối. | Mọi đường khác đều đã được kiểm. |
| **Exception approval and closure** | Rủi ro còn tồn tại được quản trị ra sao. | Rủi ro đã biến mất nếu chưa có verification. |

### 23.2. Evidence lineage

Một reviewer quyết định **REVOKE** phải có chuỗi:

~~~text
reviewItemId
  → decisionId / reviewerSubjectId / decisionAt
  → policyVersion / entitlement scope
  → remediationTaskId
  → providerRequestId / response / retry attempts
  → targetReadbackEvidenceId
  → verifiedAt / effectiveAccessResult
  → exceptionId nếu chưa giải quyết
~~~

Nếu mất một mắt xích, báo cáo nên **đánh dấu evidence gap** và chỉ kết luận trong phạm vi còn chứng minh được.

### 23.3. Không lưu raw secrets

Không đưa vào báo cáo, bảng export hoặc audit log:

- Mật khẩu, mã MFA/OTP, cookie phiên.
- Raw OAuth access/refresh token, API key, PAT, client secret.
- Private key, key material hoặc bản đầy đủ SAML/OIDC assertion.
- Hồ sơ HRIS vượt nhu cầu kiểm soát.

Chỉ lưu **reference ID, nguồn/phiên bản, trạng thái, thời gian và kết quả** cần để truy vết. Áp dụng phân quyền, mã hóa, integrity protection, lưu giữ phù hợp và quy trình phê duyệt xuất dữ liệu.

## 24. Xu hướng giữa các kỳ: so sánh sao cho công bằng?

Báo cáo trend có thể làm sai lệch kết luận nếu population thay đổi.

Ví dụ:

~~~text
Q3: 800 review items, 20 excess permissions.
Q4: 1.200 review items, 25 excess permissions.

Số phát hiện tăng 20 → 25.
Nhưng tỷ lệ phát hiện theo item:
    Q3 = 20 / 800 = 2,50%
    Q4 = 25 / 1.200 ≈ 2,08%
~~~

Số vụ tăng không nhất thiết là môi trường kém đi: **coverage có thể mở rộng**. Ngược lại, tỷ lệ giảm có thể do thiếu inventory hoặc loại bỏ hệ thống rủi ro cao.

### 24.1. Các yếu tố cần chuẩn hóa

- Population: số app, tenant, accounts, roles và loại principals.
- Risk tier: quyền admin hay quyền thông thường.
- Review item granularity: subject-role-scope hay grant path.
- Định nghĩa outcome: quyết định hay verified remediation.
- Threshold/SLA: thay đổi chính sách giữa các kỳ.
- Năng lực đọc quyền thực tế: nhà cung cấp mới có readback tốt hơn hay kém hơn?
- Thời điểm báo cáo: giữa kỳ và sau closing không so trực tiếp.

Một báo cáo trend tốt thể hiện đồng thời **absolute count, denominator, coverage và thay đổi phạm vi**.

### 24.2. Những đồ thị nên ưu tiên

- Coverage và overall decision completion theo kỳ.
- Open/overdue remediation theo owner, app và risk tier.
- Revocation latency p50/p95 nếu mẫu đủ tin cậy.
- SoD conflict và excess privileged grants theo nguồn phát hiện.
- Confirmed residual access theo JML event và target.
- Unverifiable systems và ownerless entitlements theo thời gian.

Không tô “xanh” một KPI chỉ vì nó cải thiện nếu **số quyền nghiêm trọng chưa thu hồi vẫn vượt ngưỡng được phê duyệt**.

## 25. Case study: báo cáo Mover che giấu quyền cũ

**Bối cảnh giả định:** tổ chức có HRIS, IGA, IdP và một SaaS quản lý khách hàng. Nhân viên Bình chuyển từ **Sales** sang **Finance** lúc 08:00 ngày 01/12.

| Mốc giả định | Dữ liệu quan sát | Điều báo cáo phải ghi |
| --- | --- | --- |
| **30/11 16:00** | HRIS thông báo Mover, effectiveAt 01/12 08:00. | Source event/version và trạng thái mong đợi. |
| **01/12 08:00** | IGA tính Finance Reader và bỏ Sales Editor. | Hai nghĩa vụ: grant mới và revoke cũ. |
| **01/12 08:02** | IdP bỏ nhóm Sales, thêm nhóm Finance. | Group status đúng ở IdP. |
| **01/12 08:04** | SCIM cập nhật User/Group trả 204. | Connector ACKNOWLEDGED; chưa phải xác minh toàn bộ. |
| **01/12 08:05** | SaaS vẫn có direct local Sales Editor role. | Excess entitlement, Mover drift. |
| **01/12 08:07** | Kiểm quyền được ủy quyền thấy API export Sales vẫn chấp nhận. | Confirmed residual access, severity theo dữ liệu. |
| **01/12 08:10** | App owner thu hồi direct role; xử lý session cũ. | Remediation action và owner. |
| **01/12 08:12** | API từ chối export Sales, Finance Reader hoạt động. | VERIFIED trong phạm vi và bằng chứng. |

### 25.1. Báo cáo trước và sau đối soát

**Trước:** dashboard ghi `SCIM success=100%`, `Mover completed=true`.

**Sau khi thiết kế báo cáo đúng:** hiển thị **IdP/SCIM provisioning success**, nhưng **Mover access verification chưa đạt** từ 08:05 đến 08:12. Báo cáo ghi **cửa sổ truy cập tồn dư được phát hiện và đã khắc phục**, không viết lại lịch sử thành “luôn an toàn”.

### 25.2. Hành động cải tiến

Đưa **direct app roles** vào inventory, thêm kiểm tra actual entitlement sau Mover, kiểm session/token stale, và mở cảnh báo khi expected-vs-actual lệch quá thời hạn policy.

## 26. Case study: báo cáo Leaver với dữ liệu không hoàn chỉnh

**Bối cảnh giả định:** nhân viên Mai nghỉ việc lúc 17:00. IdP đã disabled; SCIM ứng dụng A xử lý tốt, ứng dụng B trả 503 và hệ thống C không có API đọc session.

| Đích | Kết quả ban đầu | Trạng thái báo cáo đúng |
| --- | --- | --- |
| **IdP** | Account disabled. | Đã xác nhận hạn chế đăng nhập mới qua IdP. |
| **SaaS A** | SCIM User active=false; local role được kiểm lại. | Account/role verified theo phạm vi đã kiểm. |
| **SaaS B** | SCIM 503; không rõ quyền hiện tại. | FAILED/UNKNOWN, ngoại lệ có owner và biện pháp giảm thiểu. |
| **Ứng dụng C** | Không có khả năng kiểm session cũ. | UNVERIFIABLE SESSION PATH, không giả định session đã chết. |
| **PAT cá nhân** | Issuer báo token chưa thu hồi. | Credential residual risk cần revoke/rotate theo chính sách. |

### 26.1. Executive conclusion nên viết thế nào?

**Không nên:** “Leaver đã được deprovision thành công vì IdP disabled”.

**Nên:** “Đã chặn đăng nhập mới qua IdP và xác minh trạng thái ở SaaS A. SaaS B chưa xác minh do lỗi provider, phiên ứng dụng C chưa quan sát được, PAT còn cần thu hồi. Các mục chưa hoàn tất có owner, SLA và biện pháp giảm thiểu riêng.”

### 26.2. Sau khi khắc phục

Cần cập nhật **verifiedAt, source evidence, thời điểm quyền thực tế hết hiệu lực** và giữ lịch sử sự cố. Nếu chỉ chỉnh trạng thái cuối thành VERIFIED mà xóa window rủi ro cũ, báo cáo sẽ không còn giúp đánh giá SLA và mức phơi lộ sau Leaver.

## 27. Bảo mật, riêng tư và phân quyền báo cáo

Access review report có thể cho biết **ai là admin, quyền nằm ở đâu, tenant nào có dữ liệu nhạy cảm và đường cấp quyền từ nhóm nào**. Đây là dữ liệu cần quản trị, không phải tài liệu công khai mặc định.

### 27.1. Nguyên tắc bảo vệ

1. **Role-based report access:** executive chỉ thấy tổng hợp, owner thấy hệ thống phụ trách, IAM/Security thấy drill-down phù hợp, audit truy cập theo nhiệm vụ.
2. **Data minimization:** giữ đủ thông tin cho quyết định, không xuất hồ sơ nhân sự hoặc raw credential.
3. **Pseudonymization:** dùng stable IDs và reference links ở các báo cáo rộng khi phù hợp.
4. **Tenant isolation:** truy vấn và export không lộ tài khoản/quyền của tenant khác.
5. **Integrity/audit:** ghi nhận thay đổi quyết định, sửa số liệu, lịch sử export và người xem khi cần.
6. **Retention:** lưu bằng chứng đủ theo chính sách/lawful purpose, có quy trình xóa khi hết hạn.
7. **Secure distribution:** tránh email attachment chứa danh sách admin/PII nếu không có kiểm soát phù hợp.
8. **Least privilege for reporting service:** pipeline chỉ đọc dữ liệu cần dùng, không dùng token admin toàn môi trường nếu không cần.

### 27.2. Cẩn trọng khi xuất file CSV/XLSX

Nếu xuất dữ liệu ra bảng tính, các trường do người dùng/ứng dụng cung cấp cần được xử lý như **dữ liệu không đáng tin**. Chuỗi bắt đầu bằng ký tự được ứng dụng bảng tính diễn giải là công thức (ví dụ `=`, `+`, `-`, `@`) có thể gây **formula injection** khi người xem mở file. Cần dùng cơ chế export an toàn, kiểu dữ liệu rõ và không cho công thức từ dữ liệu đầu vào chạy ngoài ý muốn.

Không nên đưa raw JWT, access token hoặc mật khẩu vào CSV để “dễ đối chiếu”.

## 28. Kiểm tra chất lượng báo cáo trước khi phát hành

Một báo cáo access review nên qua **data quality gate**, riêng với academic/content QA của bài học.

### 28.1. Kiểm tra cấu trúc

- Mỗi `reviewItemId` là duy nhất trong phạm vi/phiên bản đã chọn.
- `campaignId`, `snapshotAt` và `reportAsOf` không rỗng.
- Các trạng thái thuộc enum được định nghĩa.
- `verifiedAt` không có trước khi thao tác liên quan xảy ra, trừ tình huống backdated evidence được giải thích.
- Reviewer, role, principal và resource thuộc đúng tenant.
- Một item không vừa mang quyết định cuối **REVOKE** vừa được báo **RETAIN** trong cùng phiên bản mà không có event supersede.

### 28.2. Kiểm tra tính đầy đủ

- So population từ source of authority với inventory/assigned items.
- So số app được kết nối với danh mục app bắt buộc.
- Đảm bảo tài khoản đặc quyền và non-human thuộc phạm vi được review hoặc được giao chiến dịch thay thế rõ.
- Kiểm direct local grants và group/role inheritance.
- Kiểm các trường hợp unknown/unmapped, không tự loại khỏi denominator.
- Kiểm số liệu reviewer và remediation không phình do attempts/retries.

### 28.3. Kiểm tra tính nhất quán

Ví dụ những assertion:

~~~text
count(valid_decision) <= count(assigned_campaign_item)
count(assigned_campaign_item) <= count(in_scope_item)

count(RETAIN) + count(REVOKE) + count(REDUCE)
    + count(REPLACE) + count(OTHER_FINAL)
    == count(valid_decision)

count(verified_remediation) <= count(required_remediation)

count(open_remediation) + count(verified_remediation)
    == count(required_remediation)   // khi cùng cấp obligation

every(REVOKED_VERIFIED) has valid verificationEvidenceId
every(accepted_exception) has owner + authority + expiresAt
every(critical_unverified_item) has owner + dueAt + mitigation
~~~

Các bất biến giả định mỗi item/obligation được chuẩn hóa và không bị hủy hợp lệ giữa kỳ. Hệ thống cần xử lý **superseded item, merge/split records và changed scope** bằng quy tắc được tài liệu hóa.

### 28.4. Kiểm độ tươi (freshness)

Nếu reportAsOf là 10:00 nhưng SCIM inventory chỉ mới được lấy lúc 08:00 hôm trước, không nên gọi mọi quyền trong báo cáo là **current**. Cần:

- Cung cấp `sourceObservedAt` theo hệ thống.
- Cảnh báo vượt freshness threshold tương ứng mức rủi ro.
- Nhận diện event mới chưa được ingest.
- Tránh xác nhận “no residual access” từ dữ liệu không thể kiểm đúng thời điểm.

## 29. Operating model: ai sở hữu báo cáo và ai xử lý kết quả?

| Vai trò | Trách nhiệm |
| --- | --- |
| **IAM governance owner** | Định nghĩa population, metric, campaign policy và sign-off báo cáo. |
| **IGA/Review program owner** | Điều phối chiến dịch, reviewer, hạn và evidence. |
| **HR/lifecycle owner** | Bảo đảm Person/Engagement/Start/End state đúng và có hiệu lực. |
| **Application/data owner** | Xác định ý nghĩa entitlement, approve/revoke và đánh giá dữ liệu. |
| **IAM/IT operations** | Sửa connector, role/group và xác minh target. |
| **PAM/cloud/security owner** | Xử lý privileged, SoD, token/session và rủi ro cao. |
| **Data/reporting engineer** | Chuẩn hóa nguồn, pipeline, lineage và kiểm số liệu. |
| **Risk/exception owner** | Chấp nhận hoặc xử lý ngoại lệ theo thẩm quyền. |
| **Internal audit** | Kiểm tra độ tin cậy và bằng chứng, không tự thay quyết định owner. |

### 29.1. Chu trình vận hành gợi ý

~~~mermaid
flowchart TD
    A["Chốt scope & population"] --> B["Thu inventory, chuẩn hóa<br/>ID + risk + owner"]
    B --> C["Chụp snapshot chiến dịch<br/>và giao reviewer"]
    C --> D["Theo dõi decisions<br/>authority + overdue"]
    D --> E["Thực hiện revoke/reduce<br/>theo từng ứng dụng"]
    E --> F["Readback / verify<br/>effective permissions"]
    F --> G["Báo cáo KPI + data gaps<br/>exception + owner/SLA"]
    G --> H["Management review<br/>follow-up actions"]
    H --> I["Đối soát tới khi khép kín"]
    I --> G
~~~

Khi campaign đóng, **exception follow-up vẫn tiếp tục** cho tới khi quyền thực tế được xử lý hoặc rủi ro được quản trị đúng chính sách. Không đặt **campaign close** là điểm dừng duy nhất của trách nhiệm IAM.

## 30. Những sai lầm thường gặp khi báo cáo

| Sai lầm | Vì sao nguy hiểm | Cách sửa |
| --- | --- | --- |
| **Chỉ báo % reviewer đã nhấn Approve/Reject** | Bỏ sót những revoke chưa thi hành. | Tách decision, remediation, verification. |
| **Chỉ lấy items đã vào campaign làm population** | Không thấy hệ thống hoặc principal bị bỏ sót. | Reconstruct in-scope population độc lập. |
| **Đếm số approver step như số entitlement** | KPI phình giả tạo. | Stable reviewItemId và đơn vị đo. |
| **Báo SCIM 204 là quyền đã thu hồi** | Local role/session/token có thể còn hoạt động. | Readback và kiểm effective access. |
| **Không ghi reportAsOf/sourceObservedAt** | Số liệu stale bị trình bày như trạng thái hiện tại. | Snapshot và freshness metadata. |
| **Gộp UNKNOWN vào DENIED/VERIFIED** | Che quyền chưa quan sát. | Trạng thái riêng cho unverifiable. |
| **Không báo orphan/unmapped** | Tài khoản không owner biến mất khỏi báo cáo. | Unknown population và exception. |
| **Chỉ đếm human accounts** | Service principal có thể có quyền rất rộng. | Non-human campaign và roll-up. |
| **Không tính nested group/direct grants** | Bỏ sót effective privileges. | Grant-path inventory và app readback. |
| **Coi risk exception là đã khắc phục** | Rủi ro được hợp thức hóa vĩnh viễn. | Exception có expiry, owner và remediation. |
| **Dùng mốc reviewer decision để đo Leaver** | Bỏ sót thời gian từ termination đến quyết định. | Dùng effectiveAt của nguồn có thẩm quyền. |
| **Không chuẩn hóa scope giữa các kỳ** | Trend so sánh không có ý nghĩa. | Ghi denominator và thay đổi phạm vi. |
| **Chỉ nhìn role name chứa admin** | Bỏ sót đường nâng quyền. | Phân tích permission, delegation và token. |
| **Xuất bảng quyền/secret không giới hạn** | Rò rỉ danh mục đặc quyền/credential. | Quyền báo cáo tối thiểu, masking và audit. |
| **Xóa lịch sử sau khi khắc phục** | Không đo được cửa sổ quyền tồn dư hoặc SLA. | Event log bất biến và snapshot có phiên bản. |

## 31. Checklist lập và kiểm duyệt báo cáo access review

### 31.1. Phạm vi, dữ liệu và khóa

1. Đã xác định **kỳ, timezone, reportAsOf, snapshotAt và sourceObservedAt** chưa?
2. Có định nghĩa rõ **in-scope population**, campaign population và exclusion có căn cứ không?
3. Một review item được tính theo **principal–entitlement–resource scope** hay quy tắc khác; đã ghi trong báo cáo chưa?
4. Có phân biệt Person/Engagement, accountId, workloadId, issuer/tenant và target role không?
5. Có inventory cả **IdP/directory, SCIM, app-local grants, cloud IAM, PAM, API key và session** theo phạm vi không?
6. Role catalog có **owner, risk tier, permission, scope và version** chưa?
7. Những account không owner, không mapping hoặc app không có API đọc có được ghi là **gap**, thay vì loại im lặng không?

### 31.2. Review và quyết định

8. Reviewer có **thẩm quyền tại thời điểm quyết định**, độc lập theo policy và không tự phê duyệt không?
9. Có tách **RETAIN, REVOKE, REDUCE, REPLACE, INVESTIGATE và exception** không?
10. Có kiểm những quyết định dựa trên role definition hoặc manager stale sau Mover không?
11. Những quyền high-risk/privileged có scope, reason, expiresAt và evidence theo yêu cầu không?
12. Có báo **coverage**, **decision completion trên campaign** và **decision coverage toàn population** riêng không?
13. Pending và overdue có được định nghĩa theo dueAt, không suy từ thời điểm campaign close không?
14. Khi nhiều reviewer duyệt một item, có tránh đếm quyết định hai lần không?

### 31.3. Khắc phục và quyền thực tế

15. Có tách **quyết định**, **lệnh thực thi**, **provider ACK** và **access verified** không?
16. Mỗi nghĩa vụ REVOKE/REDUCE có owner, target, SLA và remediationTaskId không?
17. Có đọc lại đúng role/group/entitlement và các grant path ở ứng dụng đích không?
18. Với Leaver/Mover, có xem **session/token, PAT/API key, app-local role** khi thuộc phạm vi rủi ro không?
19. Có chống retry cũ tái cấp quyền sau Leaver bằng source version/effectiveAt không?
20. Các remediation FAILED/UNKNOWN có tiếp tục nằm trong exception register và dashboard không?
21. Confirmed residual access có severity, evidence, cửa sổ rủi ro và kế hoạch giảm thiểu không?
22. Có phân biệt **verified remediation rate** với % decision completed và % HTTP success không?

### 31.4. Audit, chất lượng và bảo mật

23. Có truy vết **HRIS/IGA event → review item → reviewer decision → provider → verification** không?
24. Có kiểm tính duy nhất của item, consistency các tổng và freshness của từng nguồn không?
25. Đã giải thích các hệ thống hoặc loại quyền **không thể quan sát** và sự thay đổi phạm vi giữa các kỳ chưa?
26. Có báo KPI privileged/SoD, orphan workload, role expiry và review/revoke latency phù hợp không?
27. Dashboard executive có **top risks, owner, dueAt, recommended action** thay vì chỉ số đẹp không?
28. Có phân quyền xem/export, ẩn PII thừa và không lưu token/password/private key không?
29. Nếu export CSV/XLSX, có bảo vệ dữ liệu khỏi **formula injection** và lộ metadata đặc quyền không?
30. Báo cáo đã được owner xác nhận **phạm vi, công thức, dữ liệu nguồn và giới hạn kết luận** trước khi phát hành chưa?

## 32. Kết luận: báo cáo tốt phải giúp quyền dư thực sự biến mất

Một **báo cáo access review** đáng tin không dừng ở biểu đồ hoàn thành, cũng không coi người duyệt đã nhấn “Revoke” là bằng chứng truy cập đã mất. Nó phải liên kết bốn lớp:

~~~text
PHẠM VI ĐẦY ĐỦ
    ↓
QUYẾT ĐỊNH CÓ THẨM QUYỀN
    ↓
THAY ĐỔI QUYỀN ĐƯỢC THỰC HIỆN
    ↓
QUYỀN THỰC TẾ ĐƯỢC XÁC MINH
    ↓
NGOẠI LỆ CÒN MỞ ĐƯỢC THEO DÕI ĐẾN KHI KHÉP KÍN
~~~

**Ghi nhớ:** **Báo cáo access review phải phân biệt rõ population coverage, reviewer decision completion, remediation progress và verified effective access**. Chỉ số phải có **mẫu số, thời điểm, phạm vi, nguồn dữ liệu và bằng chứng có thể tái lập**; những tài khoản ngoài campaign, quyền đặc quyền, SoD conflicts, session/token tồn dư và trạng thái UNKNOWN phải được báo trung thực. Khi liên kết reporting với **Joiner–Mover–Leaver, HRIS, IdP/SSO, SCIM, RBAC/ABAC, PAM, workload identity và kiểm toán**, tổ chức không chỉ chứng minh đã *rà soát* quyền mà còn biết **quyền nào cần giảm, ai chịu trách nhiệm, đã thu hồi thật chưa và còn rủi ro gì phải xử lý**.
