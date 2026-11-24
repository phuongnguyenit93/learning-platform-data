# Policy Decision Point (PDP) trong PBAC: ra quyết định truy cập theo chính sách và vòng đời danh tính IAM

## 1. PDP là gì và tại sao quan trọng?

Trong bài này, **PBAC** được hiểu là **Policy-Based Access Control**: kiểm soát truy cập dựa trên những **chính sách được định nghĩa, quản trị và thực thi có hệ thống**. **Policy Decision Point (PDP)** là thành phần **đánh giá một yêu cầu truy cập dựa trên chính sách và dữ liệu ngữ cảnh đáng tin cậy**, rồi trả về kết quả quyết định cho thành phần thực thi.

Ví dụ, nhân viên Lan gửi yêu cầu **READ** báo cáo của Dự án Atlas. PDP không chỉ hỏi “Lan có đăng nhập thành công hay không?” mà phải đánh giá những điều kiện đã được tổ chức phê duyệt:

- Lan là chủ thể nào, thuộc identity và quan hệ làm việc nào?
- Báo cáo thuộc organization, project và phân loại dữ liệu nào?
- Lan có role/entitlement hoặc phê duyệt nào cho hành động READ?
- Các thuộc tính và quyền đó **còn hiệu lực ở thời điểm yêu cầu** không?
- Có quy tắc **deny** ưu tiên, yêu cầu MFA tăng cường hoặc hạn chế đặc quyền không?

Nếu các điều kiện phù hợp, PDP có thể trả **Permit**. Nếu không, PDP trả **Deny**, **NotApplicable** hoặc **Indeterminate** tùy mô hình quyết định. **Policy Enforcement Point (PEP)** mới là thành phần thực sự cho phép hoặc chặn request tại API/resource server. PDP **đề xuất quyết định theo policy**, còn PEP **thực thi quyết định**.

Trong module quản lý vòng đời danh tính **Joiner–Mover–Leaver (JML)**, PDP đặc biệt quan trọng vì quyền phải đổi khi nhân viên gia nhập, chuyển vị trí, kết thúc hợp đồng; khi ứng dụng đồng bộ qua **SCIM**; khi **IdP/SSO** thay đổi phiên xác thực; và khi **RBAC/ABAC** quyết định quyền tại tài nguyên. Một PDP dùng dữ liệu cũ có thể tạo **quyền truy cập tồn dư** ngay cả khi hệ thống IAM đã ghi nhận sự kiện Leaver.

### Mục tiêu học tập

Sau bài này, người học có thể phân biệt PDP/PEP/PIP/PAP; thiết kế request và response quyết định; hiểu Permit/Deny/NotApplicable/Indeterminate, obligations và chính sách kết hợp; xử lý dữ liệu cũ, lỗi phụ thuộc và tenant; nối quyết định với HRIS, IdP, OAuth/OIDC, SCIM, RBAC/ABAC; kiểm thử, giám sát và đối soát quyền hiệu lực xuyên suốt JML.

## 2. PBAC khác RBAC và ABAC ở góc nhìn nào?

Tên gọi **PBAC** trong tài liệu và sản phẩm có thể được dùng theo những cách khác nhau; ở đây trọng tâm là **Policy-Based Access Control**. Đây là cách tổ chức quyền quanh **bộ chính sách được đánh giá lúc có yêu cầu**, có thể dùng role, attribute, quan hệ, ownership, thời điểm và ngữ cảnh làm đầu vào. PBAC không nhất thiết là một chuẩn kỹ thuật độc lập hoặc một mô hình thay thế hoàn toàn RBAC/ABAC.

| Mô hình/khái niệm | Điểm nhấn | Ví dụ trong PDP |
| --- | --- | --- |
| **RBAC** — Role-Based Access Control | Quyền theo vai trò và phạm vi role | Người có role ReportReader tại org-a có thể READ |
| **ABAC** — Attribute-Based Access Control | Điều kiện trên thuộc tính subject/resource/action/environment | Cho phép khi project của người dùng trùng project của báo cáo |
| **ReBAC/relationship rules** | Quan hệ giữa người, nhóm và tài nguyên | Tác giả hoặc người được chia sẻ trực tiếp có quyền đọc |
| **PBAC** — Policy-Based Access Control | Quản trị và đánh giá những quy tắc quyết định tập trung/phi tập trung có kiểm soát | Kết hợp role, project, clearance, MFA và deny khẩn cấp |
| **PDP** | Nơi tính toán quyết định theo các quy tắc | Trả Permit/Deny và chỉ thị thực thi liên quan |

Ví dụ, tổ chức có chính sách: “Cho phép **xuất** báo cáo nếu người dùng thuộc dự án tương ứng, được cấp entitlement EXPORT, dữ liệu nằm trong mức clearance, có phiên xác thực đủ mới và không có lệnh đình chỉ”. PDP có thể kết hợp **RBAC + ABAC + điều kiện step-up**, thay vì chỉ kiểm tra một role.

**Không được coi quyền đã đăng nhập là quyền trên dữ liệu.** SSO/MFA trả lời về xác thực, còn PDP cần đánh giá ủy quyền dựa trên tài nguyên và chính sách hiện hành.

## 3. Bốn thành phần PAP, PDP, PIP và PEP

Trong các kiến trúc kiểm soát truy cập theo policy, đặc biệt những mô hình tham chiếu như **XACML**, thường phân biệt bốn trách nhiệm:

| Thành phần | Tên đầy đủ | Trách nhiệm | Rủi ro nếu triển khai sai |
| --- | --- | --- | --- |
| **PAP** | Policy Administration Point | Tạo, phê duyệt, phiên bản hóa và phân phối chính sách | Policy quá rộng, thay đổi không kiểm soát |
| **PDP** | Policy Decision Point | Đánh giá yêu cầu theo policy và thuộc tính | Quyết định sai vì quy tắc hoặc dữ liệu sai |
| **PIP** | Policy Information Point | Cung cấp thuộc tính, entitlement và quan hệ đáng tin cậy | Dữ liệu HR/organization/role cũ hoặc không đúng người |
| **PEP** | Policy Enforcement Point | Chặn/cho request theo quyết định và thực thi obligations | API bỏ qua Deny, không kiểm tra object-level authorization |

Một hệ thống có thể triển khai cả bốn vai trò trong **một service** hoặc tách thành các service, thư viện và kho dữ liệu. PDP không bắt buộc là một microservice độc lập. Điều quan trọng là **ranh giới trách nhiệm** và việc API không thể tự bỏ qua quyết định.

### Sơ đồ kiến trúc

~~~mermaid
flowchart TD
    H["HRIS / Sponsor<br/>Employment, end date, organization"] --> IAM["IAM/IGA<br/>Identity mapping, approval, entitlement"]
    PR["Project/Resource registry"] --> PIP["PIP<br/>Trusted attributes and relationships"]
    IAM --> PIP
    IDP["IdP/SSO<br/>Subject, authentication assurance"] --> PIP
    WC["Workload/Service catalog"] --> PIP
    PAP["PAP<br/>Versioned policies, approval"] --> PDP["PDP<br/>Policy evaluation"]
    PIP --> PDP
    U["User / Workload / OAuth client"] --> API["API / PEP"]
    API -->|"Subject, action, resource, context"| PDP
    PDP -->|"Permit / Deny / NotApplicable / Indeterminate"| API
    API -->|"Chỉ khi thực thi quyết định hợp lệ"| RES["Protected resource"]
    API --> AUD["Audit, monitoring, reconciliation"]
    PDP --> AUD
~~~

**PDP có thể trả Permit nhưng API vẫn cần từ chối** nếu PEP không thể hoàn thành một nghĩa vụ bắt buộc (obligation) hoặc trạng thái bảo mật thay đổi trước khi thực thi. Ngược lại, **PDP trả Deny nhưng API vẫn trả dữ liệu** là lỗi thực thi nghiêm trọng, không thể sửa chỉ bằng thay policy.

## 4. PDP nhận đầu vào gì?

Một yêu cầu đánh giá thường gồm **subject, action, resource và environment/context**, cùng metadata bảo đảm request đến từ PEP được tin cậy.

| Nhóm dữ liệu | Trường minh họa | Yêu cầu kiểm chứng |
| --- | --- | --- |
| **Subject** | identityId, identityType, employmentRelation, clientId | ID ổn định, nguồn/issuer đúng, mapping đáng tin |
| **Action** | READ, EXPORT, APPROVE, DELETE | Được ánh xạ từ operation thật tại API, không tin tên do client tùy chọn |
| **Resource** | resourceId, ownerOrganization, projectId, classification | Thuộc tính được tải từ backend/nguồn tài nguyên tin cậy |
| **Environment** | requestTime, sessionAssurance, device posture | Thời điểm server và tín hiệu có nguồn đáng tin |
| **Authorization context** | grantedScopes, activeRoles, directACL, approvals | Phân biệt quyền đã phê duyệt với quyền đang hiệu lực |
| **Policy metadata** | policySetId, policyVersion, evaluationMode | Xác định bộ quy tắc dùng để đánh giá |
| **Correlation metadata** | requestId, tenantContext, targetService | Đối soát và kiểm toán, tránh trộn tenant |

Ví dụ **JSON request minh họa**, không phải schema chính thức của XACML hay một sản phẩm:

~~~json
{
  "evaluationRequestId": "authz-eval-2026-091",
  "subject": {
    "identityId": "iam-user-482",
    "identityType": "EMPLOYEE",
    "employmentRelationId": "emp-org-a-01"
  },
  "action": "READ",
  "resource": {
    "id": "report-42",
    "type": "FinancialReport",
    "organizationId": "org-a",
    "projectId": "atlas",
    "classification": "CONFIDENTIAL"
  },
  "context": {
    "requestedAt": "2026-11-23T09:30:00+07:00",
    "relyingParty": "reports-api",
    "accessTokenAudience": "https://reports.example.invalid",
    "correlationId": "req-774"
  }
}
~~~

Các giá trị subject, organization và token audience **phải được PEP lấy/kiểm tra từ nguồn tin cậy**, không tự tin một đối tượng JSON bất kỳ do trình duyệt gửi.

### Không biến input từ client thành bằng chứng quyền

Nếu request HTTP chứa **X-Role: Admin** hoặc **X-Tenant-Id: org-b**, chúng chỉ là dữ liệu do phía gọi có thể tự đặt. PEP phải xác minh danh tính và quyền tenant trước khi lập **decision request** cho PDP. PDP không thể cứu một hệ thống mà lớp chuẩn hóa đầu vào đã giả mạo chủ thể.

## 5. PDP trả kết quả gì? Bốn trạng thái thường gặp

Trong mô hình quyết định kiểu **XACML**, các kết quả tiêu biểu gồm:

| Decision | Nghĩa | Hành động PEP thường cần làm |
| --- | --- | --- |
| **Permit** | Policy phù hợp cho phép request | Chỉ cho phép khi tất cả điều kiện thực thi và obligations đạt |
| **Deny** | Policy kết luận không được phép | Chặn request |
| **NotApplicable** | Không có policy/rule phù hợp để quyết định | Thường **không cho phép** theo deny-by-default ở mức áp dụng |
| **Indeterminate** | Không thể xác định Permit/Deny/NotApplicable do lỗi hay dữ liệu thiếu | **Không cho phép**; phân biệt lỗi để xử lý vận hành |

**NotApplicable khác Deny:** NotApplicable nói rằng không có quy tắc áp dụng, còn Deny là kết quả chính sách từ chối. Khi áp dụng deny-by-default, PEP hoặc lớp policy gốc **ánh xạ cả hai thành không cấp quyền**, nhưng vẫn nên giữ mã lý do khác nhau trong audit.

**Indeterminate khác Deny:** nếu PIP timeout, không có đủ dữ liệu, PDP có thể trả Indeterminate. API không được biến điều đó thành Permit; có thể trả lỗi vận hành phù hợp như **503** hoặc một phản hồi được contract định nghĩa, thay vì giả vờ đã đánh giá đầy đủ và báo 403.

### Response và obligations minh họa

~~~json
{
  "requestId": "authz-eval-2026-091",
  "decision": "PERMIT",
  "policyId": "financial-report-read",
  "policyVersion": "v12",
  "attributeSnapshotVersion": "attrs-210",
  "reasonCode": "ALL_REQUIRED_CONDITIONS_MET",
  "obligations": [
    {
      "id": "record-access-audit",
      "required": true
    }
  ],
  "evaluationCompletedAt": "2026-11-23T09:30:00+07:00"
}
~~~

Đây là **mô hình minh họa**. Hệ thống phải định nghĩa rõ **obligation nào bắt buộc**, cách PEP phản hồi khi không thực hiện được và chính sách ghi log. Không gửi bí mật token, mật khẩu hoặc toàn bộ hồ sơ HR trong response.

## 6. Obligations và advice: quyết định có thể kèm điều kiện thực thi

PDP có thể trả về **obligations** (nghĩa vụ phải thi hành) hoặc **advice** (hướng dẫn không mang cùng tính bắt buộc tùy mô hình). Trong cách dùng kiểu XACML, một obligation gắn với quyết định phải được PEP xử lý để quyết định được thi hành đúng. Nếu không thể thi hành obligation bắt buộc, PEP **không được âm thầm coi Permit là thành công**.

| Kết quả phụ | Ví dụ | Hành động phù hợp |
| --- | --- | --- |
| Obligation: audit | Phải ghi dấu vết giao dịch xuất dữ liệu | PEP bảo đảm yêu cầu kiểm toán được đáp ứng trước khi hoàn tất theo thiết kế |
| Obligation: data masking | Chỉ trả trường đã được ẩn dữ liệu nhạy cảm | Không trả dữ liệu thô nếu không áp dụng masking được |
| Obligation: response filtering | Loại bỏ cột ngoài scope | Đảm bảo cả đường export/download tuân thủ |
| Advice: user message | Gợi ý yêu cầu phê duyệt tài nguyên | Không thay thế quyết định bảo mật |
| Step-up required | Cần xác thực nâng mức trước thao tác | Thường thiết kế thành challenge/flow riêng, sau đó **đánh giá lại** |

Không phải mọi engine có khái niệm obligations giống nhau. Cần đọc contract thực tế và định nghĩa rõ PEP, PDP, ứng dụng nào chịu trách nhiệm. Nếu rule yêu cầu **step-up**, không chỉ trả Permit kèm chuỗi “MFA” rồi cho request đi qua; phải xác minh mức bảo đảm thực sự trước khi tiếp tục.

## 7. Một chu trình đánh giá hoàn chỉnh

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant RP as Application / PEP
    participant IdP as IdP / Verifier
    participant PIP as PIP / Trusted sources
    participant PDP as PDP / Policy engine
    participant DB as Protected resource
    User->>RP: Yêu cầu READ report-42
    RP->>IdP: Kiểm chứng phiên/token khi cần
    IdP-->>RP: Subject và authentication evidence
    RP->>DB: Đọc metadata report thật theo quyền hệ thống
    DB-->>RP: organizationId, projectId, classification
    RP->>PDP: Decision request đã chuẩn hóa
    PDP->>PIP: Lấy role, employment, project và policy inputs
    PIP-->>PDP: Thuộc tính + version + freshness
    PDP->>PDP: Evaluate policy / combining algorithm
    PDP-->>RP: Decision + obligations + metadata
    alt Permit, obligations thực thi được
        RP->>DB: Đọc tài nguyên có kiểm soát
        DB-->>RP: Dữ liệu được phép
        RP-->>User: Response phù hợp
    else Deny / NotApplicable / Indeterminate
        RP-->>User: Từ chối hoặc lỗi theo contract
    end
~~~

Sơ đồ minh họa; nhiều ứng dụng xác thực token ngay tại gateway, dùng PDP nhúng trong service hoặc có PIP cache. Mọi triển khai đều cần bảo đảm **PEP không bị bypass**, **policy decision dùng đúng ngữ cảnh** và **quyền tại đối tượng được kiểm tra ở đường truy cập thực tế**.

## 8. Thu thập thuộc tính: trách nhiệm của PIP và sự thận trọng của PDP

Một PDP đánh giá tốt vẫn có thể cho phép sai nếu thuộc tính đầu vào **sai người, sai nguồn hoặc quá cũ**. Những nguồn thường gặp:

| Nhóm thuộc tính | Nguồn có thẩm quyền | Nguồn bản sao/quan sát |
| --- | --- | --- |
| Employment status, start/end date | HRIS hoặc nguồn bảo trợ được chỉ định | IAM, IdP, ứng dụng |
| Department, jobCode | HRIS | Directory, token, SCIM User |
| Project assignment | Nguồn quản lý dự án/chủ tài nguyên | Nhóm IdP, SaaS ACL |
| Approved roles/entitlements | IGA và chủ tài nguyên theo phê duyệt | IdP group, app role |
| Authentication assurance | IdP/verifier theo hợp đồng | OIDC/SAML assertion, session |
| Resource owner/tenant | Resource database/catalog | API request metadata |
| Workload owner/environment | Service catalog/cloud IAM | Credential và token metadata |
| Emergency restrictions | SOC/IAM governance theo quyền hạn | Revocation/deny store |

**Nguồn có thẩm quyền là theo từng thuộc tính.** Không mặc định IdP quyết định tình trạng lao động vì IdP có claim department; không lấy bản ghi SaaS cập nhật gần nhất làm nguồn chuẩn cho mọi trường.

PDP hoặc PIP cần phân biệt **value thật**, **UNKNOWN**, **MISSING**, **UNVERIFIED** và **STALE**. Nếu PIP không có quyền đọc employmentStatus, không được gán ACTIVE theo mặc định để phục vụ tính sẵn sàng.

## 9. Identity correlation: ghép đúng subject trước khi quyết định

Quyết định sẽ sai nghiêm trọng nếu dữ liệu của người A được gắn vào tài khoản B. Trong JML, cần phân biệt **person**, **employment/worker relation**, **IAM identity**, **IdP subject**, **application account**.

Các nguyên tắc:

1. Ưu tiên **ID ổn định** và liên kết đã được xác minh theo namespace/tenant.
2. Với OIDC, phân biệt định danh bởi **issuer + subject**, không dùng riêng **sub** để ghép xuyên mọi issuer.
3. Với SCIM, **id do SP cấp** khác **externalId do provisioning client quản lý**; lưu mapping đúng target.
4. Email, họ tên, username và số điện thoại là dữ liệu có thể thay đổi/tái sử dụng, **không đủ để tự gộp identity**.
5. Nếu nhiều ứng viên hoặc mapping xung đột, **không cấp quyền dựa trên kết quả khớp mơ hồ**; mở exception có người chịu trách nhiệm.

Ví dụ, nhân viên nghỉ rồi được tuyển lại có thể giữ cùng personId nhưng có employmentId mới. PDP phải xét **quan hệ đang có hiệu lực và quyền mới được phê duyệt**, không tự phục hồi role từ hợp đồng trước.

## 10. Chính sách kết hợp và thứ tự ưu tiên

Một request có thể khớp nhiều policy. Ví dụ một rule cho **ReportReader** đọc báo cáo Atlas, còn rule khác **Deny** tất cả tài khoản bị đình chỉ. PDP cần thuật toán **policy combining** được công bố và kiểm thử.

| Cách kết hợp | Ý tưởng | Trường hợp cần lưu ý |
| --- | --- | --- |
| **Deny-overrides** | Khi có Deny phù hợp thì ưu tiên từ chối theo ngữ nghĩa engine | Hữu ích cho quy tắc đình chỉ/thu hồi ưu tiên cao |
| **Permit-overrides** | Khi có Permit phù hợp có thể ưu tiên cho phép | Cần đánh giá kỹ; có thể vô tình vượt hạn chế |
| **First-applicable** | Lấy kết quả của rule áp dụng đầu tiên theo thứ tự | Phụ thuộc thứ tự, dễ gây lỗi khi thêm rule |
| **Only-one-applicable** | Yêu cầu chỉ một policy áp dụng ở ngữ cảnh tương ứng | Giúp phát hiện chính sách chồng lấn không mong muốn |
| **Quy tắc kết hợp tùy chỉnh** | Theo business semantics cụ thể | Cần tài liệu hóa, version và kiểm thử hồi quy |

Tên gọi trên gợi ý các cách kết hợp phổ biến trong hệ sinh thái policy/XACML; **chi tiết với Indeterminate và NotApplicable có thể phức tạp hơn quy tắc tóm tắt**. Không tự triển khai “Deny-overrides = duyệt từng rule, gặp Deny thì dừng” mà bỏ qua ngữ nghĩa chính thức nếu dùng một engine chuẩn.

### Ví dụ chính sách đối kháng

~~~text
Policy A:
    Permit READ report Atlas
    IF role == ReportReader AND projectMembership == Atlas

Policy B:
    Deny ALL
    IF subject.employmentStatus == TERMINATED

Policy C:
    Deny EXPORT
    IF resource.classification == RESTRICTED

Expected:
    Người đã Leaver không thể được mở quyền chỉ vì còn role ReportReader
~~~

Khi có **lệnh chặn khẩn cấp**, phải đảm bảo một Permit khác không tự làm vô hiệu Deny của cơ chế được thiết kế ưu tiên. Ngoài thuật toán kết hợp, còn cần kiểm tra **policy target**, thứ tự phiên bản và thời điểm hiệu lực.

## 11. Deny-by-default, fail-closed và trạng thái lỗi

Hai nguyên tắc thường song hành nhưng khác nhau:

- **Deny-by-default:** không có rule/ủy quyền cho phép hợp lệ thì request không được truy cập.
- **Fail-closed:** khi không thể xác minh điều kiện bảo mật bắt buộc, hệ thống không biến lỗi thành Permit.

Ví dụ:

~~~text
result = pdp.evaluate(normalizedRequest)

if result.decision == PERMIT:
    if allMandatoryObligationsSatisfied(result):
        return ALLOW
    return CONTROLLED_ERROR_NO_ACCESS

if result.decision == DENY:
    return FORBIDDEN

if result.decision == NOT_APPLICABLE:
    return DEFAULT_DENY

if result.decision == INDETERMINATE:
    alertOnPolicyEvaluationFailure()
    return CONTROLLED_ERROR_NO_ACCESS
~~~

Đối với request HTTP, **401** thường là thiếu/thông tin xác thực không hợp lệ; **403** thường là không đủ quyền; **404** đôi khi được dùng để không tiết lộ sự tồn tại resource; lỗi phụ thuộc PDP/PIP có thể phù hợp với **503**. Quyết định **không trả dữ liệu** phải được giữ nguyên ngay cả khi mã HTTP khác nhau tùy contract.

**Không sử dụng “PDP timeout thì ALLOW tất cả”** làm đường dự phòng. Nếu cần vận hành offline, phải có cache policy/entitlement đáng tin, phạm vi thao tác và TTL được phê duyệt; các hành động nhạy cảm có thể cần bị từ chối khi không đủ độ mới.

## 12. Chính sách mẫu: role, thuộc tính, đối tượng và hành động

Giả sử chỉ Analyst được phép đọc báo cáo của dự án mà họ đang tham gia. Các điều kiện:

~~~text
policy: read-project-report-v3

Permit IF
    subject.identityType == EMPLOYEE
    AND exists relation IN subject.employmentRelations WHERE
        relation.status == ACTIVE
        AND relation.organizationId == resource.organizationId
        AND resource.projectId IN relation.approvedProjects
        AND relation.effectiveFrom <= evaluationTime
        AND (relation.effectiveUntil is not set
             OR evaluationTime < relation.effectiveUntil)
    AND subject.hasEntitlement("REPORT_READ", resource.projectId)
    AND action == READ
    AND resource.classification <= subject.approvedClearance
    AND NOT subject.hasEmergencyDeny

Otherwise:
    Deny or NotApplicable according to policy design;
    the system never grants access without a valid Permit
~~~

Đây là **mã giả policy**, không phải cú pháp chạy trực tiếp của XACML, OPA/Rego hay Spring Security. Điều kiện **classification <= approvedClearance** chỉ đúng nếu hệ thống có thứ bậc mức độ rõ ràng. Giá trị **effectiveUntil không đặt** chỉ hợp lệ khi **nguồn thẩm quyền xác nhận quan hệ không có hạn đã biết**; nếu thiếu dữ liệu do lỗi đồng bộ thì không được tự coi là vô hạn.

### Ma trận quyết định

| Subject | Resource / action | Expected | Vì sao |
| --- | --- | --- | --- |
| Analyst ACTIVE, dự án Atlas | READ report Atlas đúng org | Permit | Đủ entitlement và điều kiện |
| Analyst ACTIVE, chỉ Atlas | READ report Nova | Deny | Sai assignment |
| Analyst đã Leaver org-a | READ report org-a | Deny | Employment liên quan hết hiệu lực |
| Analyst ACTIVE org-b, hết hợp đồng org-a | READ report org-a | Deny | Không lấy role org-b dùng cho org-a |
| Analyst đúng project, thiếu entitlement | READ report Atlas | Deny | Thiếu phê duyệt quyền |
| Analyst có quyền READ | DELETE report Atlas | Deny | Sai hành động |
| Identity chưa xác minh | READ report Atlas | Không Permit | Thiếu căn cứ xác định chủ thể |

**Kiểm thử Deny quan trọng không kém Permit.** Nếu chỉ kiểm thử bằng account quản trị hoặc chỉ kiểm tra UI, rất dễ bỏ qua lỗ hổng object-level authorization.

## 13. Policy Decision Point không phải IdP

**Identity Provider (IdP)** xác minh danh tính, phương thức xác thực và phát hành kết quả **SSO/OIDC/SAML**. **PDP** đánh giá **authorization** trên tài nguyên và hành động theo policy.

| Công việc | IdP/Authorization Server | PDP/PEP |
| --- | --- | --- |
| Người dùng đăng nhập bằng passkey/MFA | Thường chịu trách nhiệm | Dùng bằng chứng assurance nếu policy yêu cầu |
| Phát hành ID token/assertion | Theo OIDC/SAML | Không tự xem là quyền API |
| Cấp OAuth access token/scope | Authorization Server theo grant/policy | API kiểm tra token và scope trước/ngoài quyết định |
| Kiểm tra quyền báo cáo của org-a | Có thể cung cấp role/claim | PDP quyết định theo resource, PEP thực thi |
| Mover mất quyền Atlas | Có thể cập nhật group/claim | PDP cần dùng quyền hiệu lực mới và chặn ở API |
| Leaver còn session ứng dụng | Có thể khóa login và revoke phần mình quản lý | PEP/resource server phải từ chối những đường còn hiệu lực |

Mỗi ứng dụng có thể sử dụng một PDP trung tâm hoặc local PDP. Điểm mấu chốt: **SSO thành công không phải Permit**. Một session được xác thực tốt vẫn phải bị từ chối khi không có role/entitlement cần thiết hoặc khi policy ưu tiên Deny.

## 14. OAuth scope, token và quyết định PDP

Trong OAuth 2.0, **scope** là phạm vi khả năng client/token được cấp; **audience** xác định API đích. Cả hai khác với entitlement chi tiết của người dùng.

Ví dụ, token có **reports:read** chỉ cho biết một điều kiện cần để gọi Reports API. PDP vẫn phải kiểm tra user còn thuộc Dự án Atlas, báo cáo đúng organization, account có trạng thái hợp lệ, dữ liệu không vượt clearance và không có lệnh deny khác.

Các bước thường cần tại resource server:

1. Kiểm tra token hợp lệ theo **issuer, audience, chữ ký/introspection, hạn và trạng thái thu hồi**.
2. Xác định **subject + client** đáng tin và phân biệt grant người dùng với client credentials.
3. Kiểm tra **scope** bắt buộc của endpoint.
4. Tải resource metadata từ nguồn đáng tin, không lấy ownership từ body client.
5. Gửi yêu cầu quyết định với identity, action, resource, tenant và policy context.
6. Thực thi kết quả/obligations; ghi audit và không trả dữ liệu khi thiếu quyền.

**ID token không dùng thay access token cho API.** OIDC scopes **openid, profile, email** không tự mở quyền nghiệp vụ. JWT tự chứa có thể giữ claim role cũ tới khi hết hạn; nếu yêu cầu thu hồi nhanh phải có cơ chế kiểm tra lại quyền hoặc chặn token theo kiến trúc.

## 15. Nhiều organization, tenant và quan hệ lao động

Một người có thể đồng thời có **hai employment relations** hợp lệ. Ví dụ Lan làm cho org-a theo hợp đồng A, đồng thời còn hợp đồng tư vấn được duyệt tại org-b. Nếu A kết thúc, PDP phải từ chối quyền xuất phát từ A nhưng vẫn có thể cho phép quyền hợp lệ của B.

Ví dụ biểu diễn quan hệ:

~~~json
{
  "identityId": "iam-482",
  "employmentRelations": [
    {
      "employmentId": "emp-a",
      "organizationId": "org-a",
      "status": "TERMINATED",
      "approvedProjects": []
    },
    {
      "employmentId": "emp-b",
      "organizationId": "org-b",
      "status": "ACTIVE",
      "approvedProjects": ["nova"]
    }
  ]
}
~~~

**Không gom mọi role của một người thành tập quyền dùng chung cho mọi tenant**. Cùng role **ReportReader** có thể chỉ hợp lệ ở org-b, còn báo cáo đang yêu cầu thuộc org-a. PDP phải gắn từng role/entitlement vào **quan hệ, resource scope và organization**.

Một user được chọn tenant bằng URL hoặc header không chứng minh membership. PEP/PDP cần đối chiếu tenant đó với nguồn đáng tin và thuộc tính thật của tài nguyên. Đây là điều kiện quan trọng để ngăn **cross-tenant authorization bypass**.

## 16. Độ mới dữ liệu: event, cache và vòng đời quyết định

PDP thường cần thời gian phản hồi nhỏ, nên có thể dùng **cache thuộc tính hoặc entitlement**. Tuy nhiên, cache có thể gây truy cập tồn dư sau Mover/Leaver.

Các mốc cần phân biệt:

| Mốc | Ý nghĩa |
| --- | --- |
| **effectiveAt** | Khi quyết định nhân sự/quyền có hiệu lực về nghiệp vụ |
| **recordedAt** | Khi nguồn HR/IGA ghi nhận sự kiện |
| **receivedAt** | Khi IAM/PIP/PDP nhận cập nhật |
| **policyPublishedAt** | Khi phiên bản policy có hiệu lực |
| **evaluatedAt** | Khi PDP đưa ra decision |
| **enforcedAt** | Khi PEP cho/chặn request |
| **verifiedAt** | Khi kiểm chứng trạng thái thực tế ở target |

**updatedAt mới nhất không đồng nghĩa nguồn đáng tin nhất.** Cần dùng source authority, version/sequence, effectiveAt và policy để tránh event đến trễ ghi đè trạng thái mới.

Các kỹ thuật giảm stale access:

- **Event-driven invalidation** khi HR/IGA chuyển trạng thái hoặc có lệnh thu hồi khẩn cấp.
- **Attribute/entitlement version** và security epoch để chống dùng snapshot quá cũ.
- **TTL khác nhau theo rủi ro:** quyền admin và dữ liệu nhạy cảm có thể yêu cầu kiểm tra gần thời gian thực.
- **Reconciliation snapshot** định kỳ bên cạnh xử lý sự kiện tăng dần.
- **Read-through PIP** cho một số quyết định đặc biệt, khi yêu cầu độ mới và tính sẵn sàng cho phép.
- **Short-lived access token** và cơ chế chặn token trước hạn khi cần.

Không có một con số TTL phù hợp cho mọi tổ chức. Một cache 15 phút có thể ổn cho dữ liệu ít nhạy cảm nhưng vượt SLA cắt quyền của ứng dụng quản trị sản xuất.

## 17. Cache quyết định PDP: khi nào có thể dùng lại Permit?

Ngoài cache attributes, có hệ thống **cache luôn kết quả quyết định** để giảm chi phí đánh giá. Đây là vùng rủi ro vì Permit từng hợp lệ có thể trở nên sai khi subject, resource hoặc policy thay đổi.

Một key cache an toàn phải cân nhắc **identity/issuer/tenant, action, resource ID, phiên bản policy và thuộc tính, thời điểm/độ mới cùng yếu tố ngữ cảnh**. Nếu quyết định phụ thuộc vào classification, device posture hay thời điểm, cache không chứa những yếu tố đó có thể phát lại Permit không hợp lệ.

| Tình huống | Rủi ro khi cache Permit | Khuyến nghị |
| --- | --- | --- |
| Mover chuyển project | Decision cũ vẫn cho đọc project trước | Invalidate theo employment/assignment version |
| Leaver bị disable | Cache vẫn trả Permit | Cơ chế thu hồi ưu tiên, epoch hoặc lookup phù hợp |
| Tài nguyên đổi owner | Permit theo owner cũ | Gắn resource version hoặc re-evaluate |
| Device trust thay đổi | Phiên trước được tin cậy | TTL/ngữ cảnh phù hợp chính sách |
| Thay policy khẩn cấp | Node còn dùng phiên bản trước | Phân phối policy và xác minh adoption |

**Không cache mãi một Permit**. Khi thiếu version hoặc không biết độ mới của một dependency quan trọng, cần không cấp quyền cho quyết định nhạy cảm theo chính sách fail-closed.

## 18. JML — PDP trong Joiner lifecycle

**Joiner** bắt đầu từ xác minh người mới, nguồn HR/bảo trợ, ngày bắt đầu và nhu cầu truy cập. Để PDP quyết định đúng:

1. **HRIS/nguồn bảo trợ** xác nhận person, employmentId, organization, start date và người quản lý.
2. **IAM** liên kết person → identity → IdP account → application accounts theo ID tin cậy.
3. **IGA/owner** phê duyệt role/entitlement; PDP không tự cấp admin chỉ từ department.
4. **SCIM/API provisioning** tạo user/group ở target, nhưng không tự tạo quyền khi chưa có chính sách.
5. **IdP/SSO/MFA** bảo đảm chủ thể có phương tiện xác thực theo yêu cầu.
6. **PIP** phân phối các thuộc tính, version và effectiveAt cần cho policy.
7. **PDP/PEP** kiểm thử các hành động **được phép** và **phải bị từ chối**.
8. **Reconciliation** xác nhận tài khoản, quyền và trạng thái có hiệu lực tại ứng dụng.

Ví dụ: account được tạo trước ngày đi làm để chuẩn bị thiết bị nhưng **start date chưa đến**. PDP phải đánh giá điều kiện thời gian và không cấp quyền nghiệp vụ sớm nếu policy không cho phép. Có thể có quyền onboarding giới hạn riêng với phê duyệt rõ ràng.

**Response SCIM 201 Created không đồng nghĩa Permit**; quyền truy cập còn cần role, thuộc tính, MFA và mốc hiệu lực.

## 19. JML — PDP trong Mover lifecycle

**Mover** thay đổi vai trò, dự án hoặc organization. Đây là điểm dễ phát sinh **privilege accumulation** nếu hệ thống chỉ cấp mới mà không thu hồi cũ.

Ví dụ:

| Quyền | Trước Mover | Sau Mover mong muốn | PDP cần nhận biết |
| --- | --- | --- | --- |
| READ Atlas | Permit | Deny | Project assignment Atlas đã hết |
| READ Nova | Deny | Permit khi đã duyệt | Assignment Nova và entitlement hợp lệ |
| EXPORT Atlas | Deny/Permit theo vai trò trước | Deny | Không dùng grant cũ vượt quyền |
| ADMIN Nova | Deny | Deny trừ khi phê duyệt riêng | Không kế thừa role admin từ tên chức vụ |

Quy trình Mover nên:

1. Xác định **nguồn thay đổi và effectiveAt**, so sánh version.
2. Tính lại **expected access** từ tất cả employment/assignment còn hợp lệ.
3. Cập nhật IdP/SCIM/IGA, cache PIP và phiên bản entitlement.
4. Thu hồi direct ACL, role/nhóm cũ hoặc grant không còn căn cứ.
5. Xử lý token/JWT, phiên và cache policy còn lưu claim quyền cũ theo SLA.
6. Kiểm thử **Atlas = Deny, Nova = Permit** khi đạt đủ điều kiện, không chỉ tin trạng thái của một connector.

Nếu cần **quyền bàn giao tạm thời**, policy ngoại lệ phải có owner, phạm vi, căn cứ phê duyệt và thời hạn. PDP không nên giữ Permit vô hạn chỉ vì có một record “temporary” chưa có end date.

## 20. JML — PDP trong Leaver lifecycle

**Leaver** kết thúc quan hệ làm việc. Nếu PAM/IGA/HRIS đã đổi trạng thái mà PDP còn dùng thuộc tính ACTIVE hoặc quyền cũ, ứng dụng có thể tiếp tục cho phép truy cập.

Các lớp cần phối hợp:

| Lớp | Việc làm | Giới hạn |
| --- | --- | --- |
| HRIS/nguồn bảo trợ | Xác nhận trạng thái, end date và mốc cắt quyền | Không quản lý mọi account và token |
| IAM/IGA | Tính quyền mong muốn, phát sự kiện thu hồi | Quyền thực tế có thể cập nhật trễ |
| IdP/SSO | Khóa xác thực mới, revoke phiên do IdP quản lý | RP/SP có phiên riêng |
| SCIM | Deactivate user, sửa group/assignment ở app hỗ trợ | Không tự thu hồi mọi local credential/token |
| PIP/PDP | Dùng employment/entitlement mới, xóa Permit cache cũ | Cần propagation/verification |
| PEP/resource server | Từ chối request theo quyền mới | JWT offline có thể còn hạn nếu không recheck |
| Local application | Thu hồi PAT, API key, ACL, session | Đường đăng nhập không qua IdP có thể còn |

**Đổi employmentStatus sang TERMINATED không tự làm mọi token đã phát hành mất hiệu lực**. Tùy hệ thống, cần token introspection, denylist, security epoch, refresh-token/grant revocation, policy recheck hoặc TTL được chấp nhận. Với tài nguyên nhạy cảm, PDP/PEP cần chặn quyền trong giới hạn SLA đã công bố.

Nếu một người còn hợp đồng hợp lệ ở org-b, không tự vô hiệu mọi quyền của họ chỉ vì hợp đồng org-a kết thúc. PDP phải **gắn quyết định với quan hệ và organization của resource**.

## 21. Workload identity và PDP cho truy cập máy–máy

PDP không chỉ dành cho người dùng SSO. Một **service account, CI/CD job hoặc workload** có thể gọi API bằng OAuth client credentials, certificate hoặc workload identity federation.

Thuộc tính workload cần thiết:

- **serviceId/workloadId** ổn định và issuer/namespace tin cậy;
- **ownerTeam** hoặc sponsor còn hiệu lực;
- **environment** như development, staging, production;
- **applicationId** và mục đích workload;
- **allowedResources**, **permittedActions**, scopes và audience;
- **credential status**, thời hạn, policy/grant version;
- **lifecycleStatus**: active, suspended, decommissioned.

Ví dụ policy:

~~~text
Permit EXPORT(report) IF
    subject.identityType == WORKLOAD
    AND subject.serviceId == "report-exporter"
    AND subject.environment == PRODUCTION
    AND subject.ownerTeam is VERIFIED
    AND subject.lifecycleStatus == ACTIVE
    AND resource.organizationId IN subject.allowedOrganizations
    AND action IN subject.permittedActions
    AND token.audience == expectedResourceServer
    AND noExplicitDeny
~~~

Không yêu cầu bot bấm **MFA push của nhân viên** mỗi lần gọi API. Workload cần credential máy, scope ngắn và tối thiểu, chủ sở hữu cùng quy trình revoke riêng. Khi owner nghỉ việc, cần **chuyển trách nhiệm, rà soát các secret cá nhân đã biết và entitlement**, không tự xóa dịch vụ sản xuất vẫn có nhiệm vụ hợp lệ.

## 22. PDP và sự nhất quán giữa policy với dữ liệu

Trong hệ thống phân tán, các node PDP có thể sử dụng **phiên bản policy khác nhau**, còn PIP có thể đồng bộ chậm. Đây là rủi ro cho một quyết định vừa bị thu hồi khẩn cấp.

Các cơ chế cần cân nhắc:

| Vấn đề | Dấu hiệu | Giải pháp thiết kế |
| --- | --- | --- |
| Node A dùng policy v12, node B dùng v11 | Cùng request cho kết quả khác | Policy version pinning, rollout và quan sát adoption |
| PIP nhận event HR đến trễ | Employment bị ghi lại ACTIVE sau Leaver | Source sequence/version, idempotent updates |
| Độ trễ revoke khẩn cấp | Permit cũ còn trên API | Priority deny, invalidation, security epoch |
| Rule thay đổi không được kiểm thử | Phát sinh false deny hàng loạt | Policy-as-code, review, unit/integration tests |
| PDP cache theo identity nhưng không theo resource | Permit của Atlas dùng cho Nova | Cache key đầy đủ hoặc không cache decision |
| Request có nhiều quyền trực tiếp và role kế thừa | Bỏ sót đường cho phép khác | Tính effective access và thuật toán kết hợp nhất quán |

Không có giao dịch nguyên tử tự động giữa **HRIS, IGA, IdP, nhiều PDP và mọi SaaS**. Phải thiết kế **eventual consistency có kiểm soát**, phân loại deadline theo rủi ro và dùng reconciliation để chứng minh trạng thái cuối.

## 23. Threat model: những cách PDP/PEP bị vượt qua

| Kiểu lỗi/rủi ro | Ví dụ | Kiểm soát |
| --- | --- | --- |
| **PEP bypass** | Endpoint download không gọi PDP | Enforcement tại mọi đường API, integration tests |
| **IDOR/BOLA** | Đổi reportId đọc dữ liệu người khác | Object-level check dựa trên resource thật |
| **Cross-tenant bypass** | Scope read nhưng gọi tenant khác | Tenant membership và resource ownership check |
| **Spoofed subject attributes** | Client gửi role = Admin | Chỉ dùng nguồn/claim đã xác minh |
| **Confused deputy** | Service có quyền rộng dùng để đọc tài nguyên ngoài ủy quyền của caller | Kiểm tra cả actor, delegated subject và quyền theo resource |
| **Policy injection/unsafe expressions** | Input người dùng được nối thành policy rồi evaluate | Schema validation, policy immutable/versioned, không eval input tùy ý |
| **Stale Permit cache** | Quyền Atlas còn sau Mover | Cache invalidation và version |
| **Overly broad default policy** | Không khớp rule thì Permit | Deny-by-default và negative tests |
| **Incorrect combining algorithm** | Permit khác vô hiệu emergency deny | Test deny priority và conflict |
| **Incomplete obligations** | Permit export nhưng không áp masking | PEP không trả dữ liệu nếu nghĩa vụ bắt buộc thất bại |
| **Policy outage fail-open** | PDP timeout thì API ALLOW | Fail-closed và error status phù hợp |
| **Uncontrolled admin override** | Quyền khẩn cấp không có owner/hạn | Approval, monitoring, SoD và expiry |

**Confused deputy** đặc biệt đáng chú ý với service-to-service. Nếu API trung gian gọi một API khác bằng quyền service của chính nó, PDP phải bảo đảm service không dùng đặc quyền rộng đó để mở dữ liệu mà **người gọi gốc không được ủy quyền**, khi nghiệp vụ yêu cầu kiểm tra quyền người dùng được ủy quyền.

## 24. Mã giả xây dựng một PDP an toàn

Mã giả sau là khung giáo dục, không phải API trực tiếp của OPA, XACML hoặc Spring Security.

~~~text
evaluateAccess(decisionRequest):
    requireAuthenticatedTrustedPEP(decisionRequest.caller)
    request = normalizeAndValidateRequest(decisionRequest)

    subject = resolveVerifiedSubject(
        request.subjectReference,
        request.issuerAndTenant
    )
    resource = loadTrustedResourceMetadata(request.resourceId)
    policyBundle = loadApprovedPolicyVersion(request.policyContext)

    if subject.isAmbiguous or resource.isUnknown:
        return Indeterminate(reason="UNVERIFIED_IDENTITY_OR_RESOURCE")

    attributeSnapshot = pip.loadFor(
        subject,
        resource.organizationId,
        request.action,
        request.evaluationTime
    )

    if attributeSnapshot.isIncompleteOrStale:
        return Indeterminate(reason="ATTRIBUTE_UNAVAILABLE")

    if policyBundle.isMissingOrUntrusted:
        return Indeterminate(reason="POLICY_UNAVAILABLE")

    if hasPriorityDeny(subject, resource, attributeSnapshot):
        return Deny(reason="PRIORITY_RESTRICTION")

    evaluations = evaluateApplicableRules(
        policyBundle,
        subject,
        resource,
        request.action,
        attributeSnapshot,
        request.trustedContext
    )

    decision = combineAccordingToApprovedAlgorithm(evaluations)
    return decision.with(
        policyVersion=policyBundle.version,
        attributeVersion=attributeSnapshot.version,
        auditCorrelationId=request.correlationId
    )
~~~

**Indeterminate** trong ví dụ phải được PEP xử lý **không cho truy cập**. Nếu policy không áp dụng, engine có thể trả **NotApplicable**; cách gộp kết quả do policy root và PEP quyết định.

Trong hệ thống thật, cần thêm xử lý timeout, bounded retries, circuit breaker, caching an toàn, theo dõi phiên bản, schema validation, phân biệt yêu cầu đọc với thao tác thay đổi trạng thái và bảo vệ audit.

## 25. Tích hợp PDP vào API/Java một cách đúng trách nhiệm

Trong ứng dụng Java, có thể triển khai kiểm tra quyền tại **service layer**, kết hợp **Spring Security** cho authentication/scope và policy client cho quyết định truy cập chi tiết.

~~~java
@Service
public class ReportService {
    private final ReportRepository reports;
    private final PolicyDecisionClient policyClient;

    public ReportService(ReportRepository reports,
                         PolicyDecisionClient policyClient) {
        this.reports = reports;
        this.policyClient = policyClient;
    }

    @PreAuthorize("hasAuthority('SCOPE_reports:read')")
    public ReportDto readReport(UUID reportId, Authentication auth) {
        Report report = reports.findById(reportId)
                .orElseThrow(ReportNotFoundException::new);

        PolicyResult result = policyClient.evaluate(
                PolicyRequest.forRead(auth, report));

        // Permit chỉ có hiệu lực khi được xác minh và obligations đạt.
        if (!result.isVerifiedPermit()) {
            throw new AccessDeniedException("Access denied");
        }
        return ReportDto.from(report);
    }
}
~~~

**Đoạn mã là ví dụ định hướng, không biên dịch độc lập**: PolicyDecisionClient/PolicyResult là kiểu minh họa, ứng dụng cần định nghĩa cách lấy verified identity, resource metadata và kiểm tra obligations. Trong triển khai thật, **result.isVerifiedPermit()** phải gắn với source, policy version, nghĩa vụ bắt buộc và cơ chế xác minh tính toàn vẹn của quyết định nếu PDP chạy từ xa.

Lưu ý:

- Cần cấu hình OAuth2 Resource Server, mapping scope và **method security** đúng nếu dùng **@PreAuthorize**.
- Đừng tin **organizationId** do client gửi; lấy từ report đã đọc trong backend và verified identity.
- Nếu PDP lỗi, **không catch exception rồi trả dữ liệu**.
- Method security dựa trên proxy có những trường hợp self-invocation không được intercept; không chỉ dựa vào một annotation mà bỏ qua boundary khác.
- Endpoint export, download, batch, GraphQL resolver hoặc background task cũng phải kiểm tra quyền.
- Với thao tác cập nhật, cần xử lý **TOCTOU**: trạng thái tài nguyên có thể đổi từ lúc kiểm tra tới lúc ghi; cân nhắc transaction, version check hoặc điều kiện truy cập cùng thao tác theo mô hình dữ liệu.

## 26. Policy-as-code và quản trị PAP

PDP chỉ đáng tin nếu bộ policy đầu vào có quy trình quản trị tốt. **Policy Administration Point** cần:

1. Quy định **owner, reviewer và approver** cho nhóm chính sách.
2. Lưu chính sách dưới dạng **versioned artifacts**, có mô tả mục đích, tài nguyên, hành động và ranh giới tenant.
3. Có **kiểm thử tự động** cho Permit, Deny, NotApplicable, Indeterminate và các ngoại lệ.
4. Kiểm tra **thay đổi rủi ro cao** như thêm Permit rộng, đổi thứ tự ưu tiên hoặc bỏ deny.
5. Triển khai theo quy trình được duyệt: staging, canary/shadow evaluation khi phù hợp và rollback có kiểm soát.
6. Xác nhận **mọi PDP node nhận phiên bản policy cần thiết** trước khi tuyên bố rollout hoàn tất.
7. Theo dõi **break-glass** và temporary policy bằng owner, hạn sử dụng, giới hạn phạm vi và audit.
8. Có cơ chế phản ứng khẩn cấp để hạn chế quyền nếu phát hiện lộ dữ liệu hoặc quyền tồn dư.

**Shadow mode** có thể chạy đánh giá policy mới mà không cho phép nó tự thay đổi enforcement, nhằm so sánh quyết định mới/cũ. Tuy nhiên không được dùng kết quả shadow “Permit” làm quyền thật khi bản phát hành chưa được phê duyệt.

Nội dung policy có thể gắn với repository và CI/CD, nhưng **không phải cứ dùng Git là đã có kiểm soát**. Quy trình approval, test và quản lý quyền deploy vẫn phải được thực thi.

## 27. Kiểm thử PDP: quyết định, độ mới và PEP enforcement

Một bộ test đủ tốt cần kiểm thử **logic PDP** và **thực thi tại API**.

| Case | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| T01 | Employee ACTIVE, đúng project, entitlement và resource | Permit |
| T02 | Employee ACTIVE, sai project | Deny hoặc kết quả policy tương ứng, PEP chặn |
| T03 | Employee đã Leaver đúng org | Không Permit |
| T04 | Cùng người ACTIVE org-b nhưng đã Leaver org-a, request org-a | Không Permit |
| T05 | Request thiếu thuộc tính quan trọng do PIP timeout | Indeterminate, PEP không trả dữ liệu |
| T06 | Không có policy phù hợp | NotApplicable, PEP deny-by-default |
| T07 | Permit nhưng masking obligation thất bại | PEP không trả dữ liệu thô |
| T08 | Role Reader nhưng action DELETE | Không Permit |
| T09 | Token đúng chữ ký nhưng sai audience | Request bị chặn trước/ngoài PDP |
| T10 | Token có scope read nhưng không có ownership | Deny ở policy/resource |
| T11 | Cache Permit trước Mover | Bị invalidation hoặc không dùng vượt freshness |
| T12 | Policy mới có emergency deny, node cũ chưa nhận | Chặn theo quy trình rollout và consistency |
| T13 | Client tự khai role admin | Không được nâng quyền |
| T14 | Workload dev gọi API prod | Deny |
| T15 | Account chưa liên kết identity chắc chắn | Không Permit |
| T16 | API download bypass gateway | Integration test phải phát hiện thiếu PEP |

Một **unit test PDP** chỉ chứng minh kết quả engine trên dữ liệu mô phỏng. Cần **integration test** ở API/resource server để chứng minh Deny thật sự chặn dữ liệu, kể cả đường API phụ hoặc giao diện mobile.

### Property-based hoặc invariant tests

Các bất biến đáng kiểm tra:

- **Thêm một Deny ưu tiên cao không được mở quyền mới** theo combining contract đã chọn.
- **Đổi tenant trong request không tự tạo membership**.
- **Tăng mức nhạy cảm resource không được tự tăng quyền** nếu policy không cho phép.
- **Leaver không được truy cập nhờ cache Permit cũ** ngoài giới hạn SLA đã duyệt.
- **PDP/PEP lỗi không được trả tài nguyên** ngoài đường dự phòng đã phê duyệt.

## 28. Audit decision và dấu vết enforcement

Để giải thích một lỗi phân quyền, cần biết **PDP đã quyết định gì** và **PEP đã làm gì**. Nếu chỉ log HTTP 200/403 mà không có policy version, rất khó tìm nguồn sai lệch.

Ví dụ audit metadata minh họa:

~~~json
{
  "eventId": "pbac-decision-2026-092",
  "correlationId": "req-774",
  "subjectRef": "iam-user-482",
  "subjectKind": "EMPLOYEE",
  "resourceRef": "org-a/report-42",
  "action": "READ",
  "policyId": "financial-report-read",
  "policyVersion": "v12",
  "attributeSnapshotVersion": "attrs-210",
  "pdpDecision": "DENY",
  "decisionReason": "PROJECT_MEMBERSHIP_MISSING",
  "pepEnforcement": "BLOCKED",
  "decisionLatencyMs": 12,
  "eventTime": "2026-11-23T09:30:00+07:00"
}
~~~

Đây không phải chuẩn log bắt buộc. **Không ghi bearer token, refresh token, password, private key, OTP seed hoặc nguyên bộ hồ sơ HR**. Nên lưu ID tham chiếu, policy/attribute version, reason code không nhạy cảm, tenant/resource scope và kết quả enforcement.

Với quyết định Permit, **kiểm toán nên phân biệt quyền đã được cho phép về logic và dữ liệu thật sự được trả**. Với lỗi PEP, cần phát hiện trường hợp **PDP Deny nhưng resource vẫn được truy cập**; đây là tín hiệu nghiêm trọng hơn một lỗi 403 thông thường.

## 29. Chỉ số vận hành và SLO cho PDP

| Chỉ số | Ý nghĩa | Cần phân loại |
| --- | --- | --- |
| **Decision latency p95/p99** | Độ trễ đánh giá chính sách | Theo loại ứng dụng, khu vực, mức rủi ro |
| **Permit/Deny/NotApplicable/Indeterminate ratio** | Phân phối kết quả để phát hiện bất thường | Không suy ít Deny là an toàn |
| **PIP timeout / attribute stale rate** | Chất lượng và độ mới dữ liệu đầu vào | HR, IGA, project, workload |
| **Policy version adoption** | Node PDP đã nhận bản policy cần thiết chưa | Theo cluster/tenant |
| **Unexpected deny rate** | Người đủ quyền bị cản trở | Joiner/Mover và target |
| **Unauthorized allow findings** | Quyền được mở sai phát hiện qua audit/test | Theo độ nhạy và nguồn sai |
| **Leaver residual access** | Quyền còn hoạt động sau mốc thu hồi | Theo API, token, local app |
| **Time to verified revocation** | Từ sự kiện đến lúc PEP thực sự từ chối | Theo SLA/risk class |
| **Obligation execution failure** | Permit không thể thực thi yêu cầu bảo mật bắt buộc | Audit, masking, step-up |
| **Policy evaluation coverage** | Endpoint/hành động có kiểm tra quyền hay không | Kể cả download, batch, admin |

Không có một ngưỡng latency hay TTL đúng cho mọi hệ thống. PDP trong dịch vụ nhạy cảm có thể đánh đổi hiệu năng lấy độ mới cao hơn; nhưng việc tăng tốc bằng **bỏ qua authorization** không phải tối ưu hợp lệ.

SLO nên phân biệt **tính sẵn sàng kỹ thuật của PDP**, **tính đúng đắn quyết định** và **thời gian quyền bị thu hồi có hiệu lực**. Một PDP luôn trả response nhanh nhưng dùng entitlement cũ vẫn có thể gây sự cố.

## 30. Quy trình xử lý lỗi PDP và sai lệch quyền

Một quy trình vận hành có thể theo các bước:

~~~mermaid
flowchart TD
    A["Phát hiện false deny / unauthorized allow / evaluation error"] --> B["Khoanh vùng subject, tenant, action, resource"]
    B --> C{"PDP decision nào?"}
    C -->|"Deny hoặc NotApplicable"| D["Kiểm tra policy, attributes, scope và approval"]
    C -->|"Indeterminate"| E["Kiểm tra PIP/PDP lỗi, không cấp quyền"]
    C -->|"Permit nhưng truy cập sai"| F["Kiểm tra policy, PEP và effective access"]
    D --> G["Xác định nguồn thẩm quyền và version"]
    E --> G
    F --> G
    G --> H["Đánh giá rủi ro, chặn đường sai theo quy trình"]
    H --> I["Sửa policy/attribute/mapping/enforcement"]
    I --> J["Test positive + negative, readback ở API"]
    J --> K{"Đã xác minh?"}
    K -->|"Chưa"| L["Giữ incident mở, owner, deadline"]
    L --> J
    K -->|"Rồi"| M["Audit, đóng case và cải thiện kiểm soát"]
~~~

**False deny** có thể gây gián đoạn công việc nhưng không nên sửa bằng cách cấp **Admin** chung. **Unauthorized allow** là rủi ro bảo mật cần ưu tiên đánh giá tác động, chặn đường quyền sai, rà soát truy cập đã xảy ra và kiểm thử hồi quy.

Khi điều tra, không kết luận “không có rò rỉ” nếu log thiếu dữ liệu hoặc hệ thống không theo dõi từng access. Báo cáo phải phản ánh giới hạn quan sát.

## 31. Tình huống thực hành: Mover và PDP dùng dữ liệu cũ

**Bối cảnh:** Nhân viên Minh có role Analyst thuộc Dự án Atlas. Ngày 01/12/2026 lúc 09:00 +07:00, hệ thống dự án xác nhận Minh chuyển sang Nova. IAM/IGA đã tính quyền mục tiêu:

- **READ Atlas = Deny**.
- **READ Nova = Permit** sau khi đã cấp entitlement.
- **DELETE báo cáo = Deny** ở cả hai nếu chỉ có role đọc.

Nhưng ở thời điểm 09:05, Reports API vẫn trả dữ liệu Atlas. Phân tích phát hiện PDP node đang dùng snapshot **approvedProjects = [Atlas]** từ trước 09:00.

### Xác định nguyên nhân

1. Kiểm tra sự kiện nguồn có **effectiveAt** và version đúng chưa.
2. Kiểm tra IAM/IGA đã thu hồi role/entitlement Atlas và cấp Nova đúng quy trình chưa.
3. Kiểm tra PIP cache và PDP node đang dùng **attributeSnapshotVersion** nào.
4. Kiểm tra token JWT/phiên có chứa claim project cũ, và PEP lấy claim đó hay gọi PIP.
5. Kiểm tra **direct ACL** hoặc role cục bộ ở ứng dụng có cấp Atlas ngoài PDP không.
6. Kiểm tra response PDP và enforcement thật, tránh nhầm PDP Deny nhưng API vẫn cho.

### Cách xử lý đúng

- Tạm hạn chế truy cập Atlas theo cơ chế bảo vệ được ủy quyền.
- Invalidate hoặc cập nhật PIP/PDP cache theo **source version**, không sửa trực tiếp claim đã phát hành.
- Thu hồi những entitlement/ACL và phiên/token cần thiết để đáp ứng SLA.
- Rà soát kết quả tại **mọi node/route** của Reports API.
- Kiểm thử các trường hợp **READ Atlas = Deny; READ Nova = Permit; DELETE = Deny**.
- Lưu thời điểm quyền Atlas thật sự bị chặn và những ngoại lệ chưa xử lý.

### Câu hỏi tự kiểm tra

**Câu 1:** PDP trả Permit có đủ để chắc chắn người dùng đã được cấp quyền thực tế không?

**Trả lời:** Chưa. PEP phải thực thi đúng Permit cùng obligations và các điều kiện cần thiết; dữ liệu nguồn/policy phải đúng và đủ mới.

**Câu 2:** PDP trả NotApplicable có đồng nghĩa Permit vì không có rule cấm không?

**Trả lời:** Không. Theo deny-by-default, không có Permit hợp lệ thì không được cấp quyền.

**Câu 3:** Một phiên SSO có MFA mạnh có thể truy cập Atlas sau Mover không?

**Trả lời:** Không nếu quyền Atlas đã hết. Authentication assurance không thay thế authorization trên tài nguyên.

**Câu 4:** Cập nhật group ở IdP có tự thay mọi cache và JWT cũ không?

**Trả lời:** Không. Cần cơ chế cập nhật attribute, cache, policy và token phù hợp với mục tiêu thu hồi.

**Câu 5:** Owner của bot nghỉ việc có đồng nghĩa xóa bot production ngay không?

**Trả lời:** Không. Cần chuyển owner, rà soát credential cá nhân và entitlement; chỉ decommission khi workload không còn nhiệm vụ hợp lệ.

## 32. Checklist triển khai PDP trong PBAC

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Thuật ngữ PBAC và mô hình policy được định nghĩa? | Phạm vi Policy-Based Access Control, engine và contract quyết định |
| PAP/PDP/PIP/PEP có trách nhiệm rõ? | Owner, đường dữ liệu, đường enforcement |
| Input có subject/action/resource/context đủ? | Stable identity, trusted tenant, backend resource metadata |
| Subject và account được liên kết đúng? | Source ID, issuer/sub, SCIM mapping; không dùng email đơn thuần |
| Policy có được phê duyệt và phiên bản hóa? | Policy owner, review, test, rollout/rollback |
| Có phân biệt Permit/Deny/NotApplicable/Indeterminate? | Response contract và mặc định không cấp quyền |
| Có combining algorithm rõ và test deny priority? | Xử lý conflict, exception, emergency revoke |
| Obligations/advice có semantics rõ? | PEP biết khi nào phải từ chối Permit chưa thể thực thi |
| Có deny-by-default và fail-closed? | PDP/PIP lỗi không trả tài nguyên |
| Có kiểm tra object- và function-level authorization? | API/mobile/export/download đều qua PEP |
| Có kiểm tra token issuer/audience/scope? | IdP/OIDC, resource server và claim mapping đúng |
| Attribute source và freshness rõ? | HRIS/IGA/project/workload authority matrix |
| Cache key/TTL và invalidation đúng? | Policy version, attribute version, tenant, resource/action |
| Có hỗ trợ nhiều employment/tenant? | Không mang role từ quan hệ A sang B |
| Joiner được nghiệm thu theo quyền thực tế? | Provisioning, MFA, Permit/Deny tests và readback |
| Mover có thu hồi quyền cũ và cập nhật PDP? | Recompute rights, cache/token và direct ACL |
| Leaver có chặn phiên/token và quyền đích? | IdP, SCIM, RP, PEP, workload/PAT, residual access |
| Workload có định danh/owner/quyền riêng? | Service catalog, environment, credential lifecycle |
| Có audit decision và PEP enforcement? | Correlation ID, policy version, reason, target, readback |
| Có kiểm thử sự cố phụ thuộc và rollout? | Timeout, stale data, mixed policy versions, rollback |

## 33. Tổng kết

**Policy Decision Point (PDP)** là trung tâm **đánh giá chính sách truy cập** trong cách tiếp cận **Policy-Based Access Control (PBAC)**. PDP nhận yêu cầu từ PEP, sử dụng thuộc tính và quan hệ đáng tin cậy do PIP cung cấp cùng bộ policy được PAP quản trị, rồi trả **Permit, Deny, NotApplicable hoặc Indeterminate** theo contract. **PDP không thay thế PEP**: chỉ khi điểm thực thi tuân thủ quyết định và obligations, hệ thống mới thực sự kiểm soát được quyền.

Trong **Joiner–Mover–Leaver**, dữ liệu **HRIS/nguồn bảo trợ** xác nhận quan hệ làm việc; **IAM/IGA** quản lý identity/entitlement; **IdP/SSO/MFA** cung cấp căn cứ xác thực; **SCIM** hỗ trợ user/group provisioning; **RBAC/ABAC** đóng góp những điều kiện chính sách; còn **resource server** thực thi quyền trên tài nguyên. **Workload/service accounts** có chủ thể, owner và credential riêng. Một PDP đáng tin phải có **deny-by-default, fail-closed, phân biệt lỗi với từ chối, policy/attribute version, cache có kiểm soát, negative tests, audit và đối soát tại hệ thống đích**, từ đó ngăn quyền cấp nhầm, giảm **quyền truy cập tồn dư** và bảo đảm mọi quyết định truy cập có thể giải thích, kiểm chứng được.
