# Security approval trong Approval workflow và quản lý vòng đời danh tính IAM

## 1. Security approval là gì?

**Security approval** là bước **thẩm định và ra quyết định từ góc độ an toàn thông tin** đối với một yêu cầu truy cập, đặc biệt khi quyền được xin có thể tạo rủi ro đáng kể cho dữ liệu, hệ thống, tài khoản đặc quyền hoặc nguyên tắc phân tách nhiệm vụ. Bước này nằm trong **approval workflow** của Identity and Access Management (IAM) và thường được thực hiện bởi **Security team**, người được ủy quyền về rủi ro bảo mật hoặc một **policy engine** đã được phê duyệt để tự động đánh giá một tập điều kiện.

Ví dụ, Minh là kỹ sư vận hành cần quyền **production.database.admin** trong 45 phút để xử lý sự cố. Người quản lý xác nhận đây là công việc được giao; application owner xác định database và các thao tác cần thực hiện. **Security approval** đánh giá thêm: Minh có đủ điều kiện xin quyền đặc biệt không, tài khoản và phiên đã xác thực mạnh chưa, có xung đột SoD không, phạm vi có vượt nhu cầu không, giới hạn thời gian và cơ chế giám sát/thu hồi có đủ không.

**Security approval không phải chỉ là nút Approve cuối cùng.** Đây là một quyết định có căn cứ, gắn với **người hưởng quyền, tài nguyên, action, phạm vi, mục đích, thời hạn, điều kiện và phiên bản chính sách**. Quyết định chỉ là một phần của quy trình: sau đó phải **provision quyền tại đích và đối soát khả năng thực thi thực tế**.

Bài này thuộc chương **Approval workflow** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, xoay quanh vòng đời **Joiner–Mover–Leaver (JML)**. Mô-đun bao quát xác minh danh tính, tạo account, cấp và rà soát quyền, thu hồi sau khi thay đổi quan hệ; liên hệ **IdP, SSO, SCIM, RBAC/ABAC, service account, audit** và phòng tránh **quyền truy cập tồn dư**.

### Mục tiêu học tập

Sau bài này, người học cần:

1. Phân biệt **Security approval** với manager, resource owner và application owner approval.
2. Biết **khi nào cần Security approval**, khi nào có thể áp policy tự động và khi nào phải từ chối.
3. Mô hình hóa đầu vào, điều kiện và kết quả thẩm định theo rủi ro.
4. Thiết kế luồng duyệt bảo đảm **least privilege, SoD, MFA, time-bound/JIT và traceability**.
5. Xử lý request thay đổi, approver vắng mặt, xung đột phê duyệt, timeout và sự kiện JML đến muộn.
6. Tích hợp quyết định với **IAM/IGA, IdP/SSO, SCIM, PAM/PIM, RBAC/ABAC/PBAC** và resource server.
7. Kiểm toán, kiểm thử và xác minh rằng **approved** không bị đánh đồng với **access active** hoặc **revoked**.

## 2. Security approval nằm ở đâu trong approval workflow?

Một Access request có thể đi qua nhiều quyết định, mỗi quyết định có mục đích khác nhau:

| Khâu | Câu hỏi trọng tâm | Người/hệ thống chịu trách nhiệm |
|---|---|---|
| **Request validation** | Đối tượng và quyền được xin có hợp lệ về dữ liệu? | IAM/IGA, access request service |
| **Manager approval** | Nhu cầu có phù hợp nhiệm vụ và quan hệ công việc? | Manager được xác minh |
| **Resource owner approval** | Có được truy cập dữ liệu/tài nguyên cụ thể này? | Data owner, application/resource owner |
| **Security approval** | Rủi ro, đặc quyền, SoD, MFA, scope, giới hạn và kiểm soát có chấp nhận được? | Security approver hoặc policy tự động được ủy quyền |
| **Compliance/legal review** | Có điều kiện pháp lý hoặc tuân thủ chuyên biệt không? | Bộ phận có thẩm quyền nếu áp dụng |
| **Fulfillment** | Connector đã gán đúng quyền tại đích chưa? | IAM provisioning, PAM/PIM, SCIM/API |
| **Verification** | Quyền thực tế đúng policy, không thừa hoặc thiếu? | Reconciliation, application owner, monitoring |

**Security approval không thay thế xác nhận nhu cầu nghiệp vụ của manager hay thẩm quyền của data owner.** Security có thể yêu cầu thu hẹp scope hoặc tăng kiểm soát nhưng không nên tự khẳng định người dùng cần quyền truy cập dữ liệu mà business owner chưa cho phép.

Tương tự, manager hoặc application admin không nên được phép bỏ qua **guardrail bảo mật bắt buộc** chỉ vì đã phê duyệt nghiệp vụ.

### Quy trình minh họa

~~~mermaid
flowchart TD
    R[Access request được tạo] --> V{Identity, scope, catalog hợp lệ?}
    V -->|Không| REJ[Từ chối hoặc yêu cầu bổ sung]
    V -->|Có| B[Manager / Resource owner review]
    B --> A{Nhu cầu nghiệp vụ được duyệt?}
    A -->|Không| REJ
    A -->|Có| T{Security risk / policy}
    T -->|Rủi ro thấp, rule đủ| AUTO[Security policy auto-decision]
    T -->|Nhạy cảm / ngoại lệ| SEC[Security review]
    AUTO --> D{Security decision}
    SEC --> D
    D -->|DENY| REJ
    D -->|CONDITIONAL| COND[Kiểm tra điều kiện trước khi cấp]
    COND --> F[Provisioning / PAM / SCIM]
    D -->|APPROVE| F
    F --> RB[Target readback]
    RB --> MATCH{Quyền thực tế khớp?}
    MATCH -->|Không| INC[Partial / remediation / escalation]
    MATCH -->|Có| DONE[Verified access]
    DONE --> REV[Expiry / Mover / Leaver / Review]
    REV --> OFF[Revoke + verify revoked]
~~~

Sơ đồ trình bày **một khả năng tổ chức luồng**, không phải quy trình bắt buộc của mọi doanh nghiệp. Một số loại request có thể cần thẩm định Security trước business approval hoặc chạy song song, tùy rủi ro và chính sách đã xác định.

## 3. Security approval khác Security authentication và authorization

Ba hoạt động cùng liên quan đến bảo mật nhưng có câu hỏi khác nhau:

- **Authentication:** chủ thể đang kiểm soát phiên/credential có được xác minh theo mức yêu cầu không?
- **Security approval:** có chấp thuận **cấp hoặc kích hoạt** quyền được xin với các điều kiện bảo mật không?
- **Runtime authorization:** tại thời điểm action xảy ra, người dùng có **quyền hiện hành** đối với resource cụ thể và ngữ cảnh đó không?

Ví dụ, Lan đăng nhập thành công qua SSO và MFA. Security đã chấp thuận cho Lan có thể xin quyền **report.export** trong một dự án. Tuy nhiên, API vẫn phải kiểm tra Lan có **grant đang active**, đúng dataset, tenant, thời hạn, độ nhạy dữ liệu và giới hạn xuất hay không.

**Approval không trở thành token xác thực**, và **một access token hợp lệ không chứng minh yêu cầu đặc quyền đã được Security phê duyệt**. Ứng dụng cần liên kết nguồn entitlement/grant với quyết định còn hiệu lực, rồi kiểm tra policy ở lúc truy cập.

## 4. Khi nào cần Security approval?

Không phải mọi yêu cầu đều cần một nhân viên Security bấm duyệt. Quy trình nên xác định **risk-based routing** để sử dụng nguồn lực đúng chỗ và tránh tạo hàng đợi gây chậm trễ không cần thiết.

| Nhóm yêu cầu | Ví dụ | Hướng xử lý thường phù hợp |
|---|---|---|
| **Quyền baseline rủi ro thấp** | Đọc wiki nội bộ của team | Có thể tự duyệt bằng policy đã kiểm soát |
| **Dữ liệu nghiệp vụ giới hạn** | Read báo cáo thuộc department | Manager/resource owner theo chính sách |
| **Dữ liệu nhạy cảm / xuất hàng loạt** | HR payroll export, customer bulk export | Security review hoặc guardrail tăng cường |
| **Quyền quản trị danh tính** | user.assignRole, federation.config.change | Security review, SoD, thời hạn và audit |
| **Production/cloud/database privilege** | cluster admin, privileged SQL | PAM/PIM/JIT, phê duyệt phù hợp |
| **Quyền vượt tenant hoặc region** | Truy cập dữ liệu nhiều khách hàng | Security và owner review chuyên biệt |
| **Quyền xung đột SoD** | Vừa tạo vendor vừa phê duyệt thanh toán | Thường DENY hoặc yêu cầu giải pháp kiểm soát độc lập |
| **Ngoại lệ chính sách** | Bỏ một điều kiện chuẩn trong thời gian ngắn | Security exception review với biện pháp bù trừ |
| **Contractor/partner đặc quyền** | Nhà thầu quản trị môi trường prod | Kiểm tra sponsor, hợp đồng, MFA và thời hạn |
| **Non-human identity đặc quyền** | CI/CD pipeline deploy production | Workload owner + Security policy |
| **Break-glass** | Truy cập cứu hệ thống khi IdP/PAM lỗi | Quy trình khẩn cấp đã được phê chuẩn, giám sát hậu kiểm |

Các ví dụ là **phân loại tham khảo**; mức phê duyệt chính thức phải do tổ chức xác định theo **dữ liệu, rủi ro, sản phẩm, trách nhiệm và nghĩa vụ áp dụng**. Không khẳng định mọi quyền đọc luôn ít rủi ro: đọc khóa bí mật hoặc dữ liệu cá nhân nhạy cảm có thể đặc biệt nghiêm trọng.

### Không đồng nhất “cần Security approval” với “luôn phải duyệt thủ công”

Với policy rõ ràng, đã được security owner review và có đủ dữ liệu tin cậy, một bước **automatic security decision** có thể hợp lệ. Cần ghi rõ **policy ID, phiên bản, điều kiện và căn cứ**, không giả mạo một người đã bấm Approve.

## 5. Các bên tham gia và giới hạn trách nhiệm

| Tác nhân | Trách nhiệm | Rủi ro nếu nhầm quyền |
|---|---|---|
| **Requester** | Tạo yêu cầu, nêu lý do và scope | Tự mở rộng quyền qua form |
| **Beneficiary** | Người/workload nhận quyền | Nhầm với requester khi xin hộ |
| **Manager** | Xác nhận công việc | Chưa chắc được quyết định về dữ liệu nhạy cảm |
| **Resource/Data owner** | Cho phép truy cập tài nguyên thuộc phạm vi sở hữu | Không tự bỏ qua hard security guardrail |
| **Security approver** | Thẩm định rủi ro, SoD, điều kiện, ngoại lệ | Không tự cấp role ngoài workflow |
| **Risk/Compliance owner** | Chấp thuận ngoại lệ theo quyền hạn nếu cần | Không mặc nhiên thay Security approver |
| **IAM/IGA administrator** | Thiết kế catalog, policy và fulfillment | Không tự cho phép request của chính mình ngoài quy tắc |
| **PAM/PIM administrator** | Cấu hình eligible/active privileged access | Phải tách tài khoản vận hành khỏi quyết định độc lập khi yêu cầu |
| **Approver delegate** | Duyệt thay theo phạm vi, thời hạn được ủy quyền | Không vượt thẩm quyền gốc hoặc self-approval |
| **Auditor** | Kiểm tra evidence và review hiệu quả | Không được sửa lịch sử để hợp thức hóa grant |

### Requester và beneficiary khác nhau

Ví dụ manager tạo request cấp quyền cho nhân viên mới. **RequesterId là manager**, **beneficiaryId là nhân viên**. Kiểm tra eligibility, lịch sử quyền và lifecycle phải áp lên **beneficiary**; kiểm tra quyền **canRequestFor** phải áp lên **requester**. Security approval phải thấy rõ cả hai để tránh **impersonation** hoặc gán nhầm account.

## 6. Dữ liệu đầu vào cần có trước thẩm định

Một yêu cầu Security approval không nên chỉ chứa câu “xin quyền admin”. Những trường quan trọng:

| Trường | Mục đích | Nguồn/kiểm tra |
|---|---|---|
| **requestId / version** | Gắn quyết định với phiên bản request chính xác | Server tạo và quản lý |
| **requesterId** | Người khởi tạo | Session/tài khoản được xác minh |
| **beneficiaryId** | Người/workload nhận quyền | IAM identity mapping |
| **relationshipId** | Quan hệ nhân sự/hợp đồng làm căn cứ | HRIS/contract source |
| **targetSystem / tenantId** | Đích và biên tenant | Catalog và target registry |
| **catalogItem / entitlement** | Loại quyền được yêu cầu | Catalog đã quản trị |
| **action / resourceScope** | Làm gì, trên đối tượng nào | Chính sách least privilege |
| **requestedFrom / requestedUntil** | Cửa sổ hiệu lực | Thời gian server, max TTL |
| **justification / purposeRef** | Lý do công việc, ticket liên kết | Chủ nghiệp vụ xác minh |
| **dataClassification** | Độ nhạy dữ liệu liên quan | Data owner/catalog |
| **currentGrants** | Quyền đang có, kể cả trực tiếp/kế thừa | IAM/target readback |
| **authenticationAssurance** | Phiên có đáp ứng mức bảo đảm không | IdP/session được xác minh |
| **approvalsSoFar** | Những bước nghiệp vụ đã duyệt | Approval service có integrity |
| **policyVersion** | Phiên bản policy dùng đánh giá | PAP/IGA |
| **riskFindings** | SoD, toxic combination, scope, trust | Security policy engine |

**Không yêu cầu người xin dán mật khẩu, access token, private key hoặc recovery code** để “Security xác minh”. Những credential này phải được quản lý qua kênh khác; hồ sơ phê duyệt chỉ nên chứa metadata cần thiết.

## 7. Ví dụ payload của một yêu cầu cần Security approval

~~~json
{
  "requestId": "ar-20261123-0085",
  "requestVersion": 3,
  "requesterId": "person-2046",
  "beneficiaryId": "person-2046",
  "relationshipId": "employment-2046-v1",
  "catalogItemId": "production-db-operator",
  "target": {
    "systemId": "db-payments",
    "tenantId": "org-vn",
    "environment": "production",
    "resourceId": "cluster-payments-primary"
  },
  "requestedActions": [
    "database.schema.inspect",
    "database.maintenance.execute"
  ],
  "requestedFrom": "2026-11-23T10:00:00+07:00",
  "requestedUntil": "2026-11-23T10:45:00+07:00",
  "purposeRef": "INC-2026-1427",
  "justification": "Kiểm tra và khắc phục lỗi schema đã được xác nhận",
  "approvalStatus": "PENDING_SECURITY_REVIEW",
  "businessApprovalRef": "approval-business-714",
  "riskTier": "HIGH",
  "correlationId": "corr-c6f2"
}
~~~

Đây là **schema minh họa nội bộ**, không phải chuẩn chung của OAuth, SCIM hay một sản phẩm IGA. Hệ thống phải kiểm tra **requestVersion**, định danh bên hưởng quyền, phạm vi tài nguyên và thời hạn từ nguồn tin cậy. **riskTier không được chấp nhận từ client như kết luận cuối cùng** mà phải tính hoặc xác minh bằng policy.

### Vì sao version quan trọng?

Security phê duyệt bản **v3** với quyền bảo trì hạn chế. Nếu requester sửa thành bản **v4** có **database.superuser** sau khi được duyệt, **phê duyệt cũ không còn bao phủ yêu cầu mới**. Cần tạo lại hoặc đánh giá lại approval theo định nghĩa thay đổi ảnh hưởng bảo mật.

## 8. Checklist đánh giá rủi ro của Security

Một Security reviewer nên đánh giá có cấu trúc thay vì chỉ đọc nội dung justification:

1. **Identity trust:** beneficiary có identity ID đúng, không trùng/giả mạo?
2. **Lifecycle state:** quan hệ làm việc đang có hiệu lực, không bị Leaver/suspended?
3. **Business justification:** công việc thực cần quyền, có ticket/owner đáng tin?
4. **Requested action:** yêu cầu chính xác thao tác, hay dùng role rộng không cần thiết?
5. **Resource scope:** đúng hệ thống, tenant, project, môi trường và dữ liệu?
6. **Privilege level:** có quyền admin, export hàng loạt, secret read hoặc sửa IAM?
7. **Existing access:** đã có quyền tương đương, hay quyền mới gây tích lũy?
8. **Separation of Duties:** quyền mới có tạo toxic combination hoặc tự phê duyệt?
9. **Authentication:** MFA/step-up có đủ assurance theo rủi ro?
10. **Endpoint/session risk:** thiết bị, phiên, token và kênh truy cập có đáng tin?
11. **Duration:** có ngắn đủ, đúng change window, trong hạn hợp đồng?
12. **Monitoring:** có ghi audit, log hành động và cảnh báo phù hợp?
13. **Revocation:** hết hạn hoặc Leaver có thu hồi được tại ứng dụng thật?
14. **Recovery:** thao tác có phá hủy dữ liệu hoặc quyền? Có rollback/backup theo quy trình?
15. **Data handling:** export/download có masking, watermark hay giới hạn lượng dữ liệu?
16. **Policy exceptions:** có vượt một guardrail bắt buộc? Ai có quyền chấp thuận?
17. **Residual access:** nhóm lồng nhau, local account, API key hoặc token cũ có thể giữ quyền?
18. **Coverage:** những đường truy cập không quan sát được có được ghi thành ngoại lệ?

**Một lý do hợp lý không đủ để bỏ qua điều kiện an toàn bắt buộc.** Ngược lại, một request quyền thấp đã đáp ứng tất cả policy có thể được xử lý nhanh mà không bắt một reviewer thủ công đọc lại từng ticket.

## 9. Đánh giá theo rủi ro nhưng không dựa duy nhất vào điểm số

Nhiều tổ chức dùng **risk score** để quyết định route phê duyệt. Điểm số có thể giúp ưu tiên, nhưng **không nên thay thế các điều kiện từ chối bắt buộc**.

Ví dụ các chiều đánh giá:

| Chiều | Mức tác động thấp hơn | Mức tác động cao hơn |
|---|---|---|
| **Action** | Đọc cấu hình công khai | Cấp quyền admin, xóa dữ liệu |
| **Resource** | Môi trường test cô lập | Production, identity provider |
| **Data** | Dữ liệu công khai | Dữ liệu nhạy cảm, secrets |
| **Scope** | Một đối tượng có owner | Nhiều tenant hoặc toàn hệ thống |
| **Duration** | Một phiên ngắn | Đặc quyền thường trực |
| **Beneficiary** | Nhân viên có nhiệm vụ đã xác minh | Account không rõ owner hoặc quan hệ hết hạn |
| **Credential** | Credential ngắn hạn được ràng buộc | Shared password/token không kiểm soát |
| **Observability** | Log/PEP có coverage | Không ghi được ai đã làm gì |

### Guardrail quan trọng hơn phép cộng điểm

Một yêu cầu **người đã Leaver muốn có global admin** không được tự biến thành “acceptable” chỉ vì các yếu tố khác có điểm thấp. Tương tự, một quyền xung đột SoD bị cấm không nên được Permit bởi công thức trung bình.

Một mô hình định hướng:

~~~text
if identity.lifecycleState invalid:
    DENY
if beneficiary not entitled to request:
    DENY
if SoD hard constraint violated:
    DENY
if target scope cannot be verified:
    DENY

risk = evaluateRisk(action, resource, data, duration, identity, controls)

if risk is low and predefinedPolicySatisfied:
    POLICY_APPROVE
else if risk is within security review mandate:
    REQUIRE_SECURITY_REVIEW
else:
    ESCALATE_OR_DENY according to approved risk policy
~~~

Đây là **giả mã**, không phải engine cấu hình sẵn. **Điểm số, ngưỡng và người được quyền chấp nhận rủi ro phải do tổ chức định nghĩa**, kiểm thử và rà soát định kỳ.

## 10. Least privilege là điều kiện trung tâm

**Least privilege** yêu cầu quyền được cấp không rộng hơn nhu cầu thực tế về **action, resource, thời gian và bối cảnh**.

| Nhu cầu thực | Yêu cầu quá rộng | Điều Security nên cân nhắc |
|---|---|---|
| Xem log service A | Cloud global admin | logs.read trên service A |
| Restart service payments | Kubernetes cluster-admin | service.restart hoặc namespace-scoped operation |
| Đọc dữ liệu báo cáo | DB superuser | SELECT trên view/dataset đã duyệt |
| Duyệt chi phí nhóm | Finance super-admin | invoice.approve trong hạn mức và SoD |
| Xuất dữ liệu phục vụ incident | Full data lake export | Dataset/columns/rows được phép, masking |
| Deploy ứng dụng | Admin mọi môi trường | JIT deploy đúng service và environment |
| Quản lý nhóm nhân viên | Directory domain admin | Group membership management đúng scope |

**Security approval có thể yêu cầu giảm scope**: từ toàn subscription xuống project, từ admin vĩnh viễn xuống JIT, hoặc từ quyền sửa tùy ý sang một tập lệnh được trung gian hóa.

Nếu hệ thống đích **không thực thi scope hẹp**, chỉ ghi scope trong approval text không phải kiểm soát bảo mật. Khi đó cần **cơ chế bù trừ hoặc từ chối**, thay vì phê duyệt và giả định đã an toàn.

## 11. RBAC, ABAC, PBAC và Security approval

### RBAC

**Role-Based Access Control** ánh xạ role với permission. Security review cần hiểu **effective permissions** của role, không chỉ tên vai trò như **READ_ONLY_ADMIN**. Một role có thể kế thừa quyền rộng hoặc chứa direct grants ít ai biết.

### ABAC

**Attribute-Based Access Control** giới hạn theo department, tenant, data classification, chủ tài nguyên và thời điểm. Security cần kiểm tra các thuộc tính này có **nguồn đáng tin** và được cập nhật khi Mover/Leaver.

### PBAC

**Policy-Based Access Control** có thể đưa các điều kiện trên thành rule có kiểm thử. Security approval có thể được tự động hóa nếu policy được review trước, nhưng việc **tự động hóa quyết định** không loại bỏ trách nhiệm ownership và audit.

### ReBAC

Trong những trường hợp quyền theo project/owner, quan hệ có thể xác định phạm vi. Security cần kiểm tra **quan hệ đã có hiệu lực, ai được quyền tạo quan hệ và cách thu hồi khi project hoặc hợp đồng kết thúc**.

### Quyết định nhiều lớp

~~~mermaid
flowchart TD
    Q[Request: subject/action/resource/context] --> ID{Danh tính và JML hợp lệ?}
    ID -->|Không| DENY[DENY]
    ID -->|Có| RBAC{Role / entitlement phù hợp?}
    RBAC -->|Không| DENY
    RBAC -->|Có| SCOPE{Tenant / scope / ABAC đúng?}
    SCOPE -->|Không| DENY
    SCOPE -->|Có| SOD{SoD và guardrails đạt?}
    SOD -->|Không| DENY
    SOD -->|Có| MFA{Assurance và duration đạt?}
    MFA -->|Không| FIX[Step-up / thu hẹp / xem xét lại]
    MFA -->|Có| REVIEW[Security decision + conditions]
~~~

Sơ đồ đánh giá **điều kiện cấp quyền**; nó không thay thế **authorization kiểm tra từng action** ở resource server sau khi cấp.

## 12. Separation of Duties: tránh người tự phê duyệt

**Separation of Duties (SoD)** bảo vệ khỏi việc một người tự tạo, duyệt và thực hiện hành vi rủi ro khi tổ chức yêu cầu độc lập.

### Các trường hợp cần kiểm tra

- Requester tự nhận là **Security approver** cho request của mình.
- Application admin gửi request, rồi tự cấp role và tự chứng nhận fulfillment.
- Người có quyền tạo vendor xin thêm quyền thanh toán cho chính vendor đó.
- Người tạo hóa đơn xin role cho phép **tự duyệt** hóa đơn.
- Người đang nắm role đặc quyền qua nhóm lồng nhau xin thêm role xung đột.
- Approver được ủy quyền từ một người không còn ACTIVE hoặc ủy quyền đã hết hạn.

### Static và dynamic SoD

| Kiểu | Nội dung | Ví dụ |
|---|---|---|
| **Static SoD** | Cấm nắm đồng thời các permission/role xung đột | vendor.create và vendor.payment.approve trong cùng scope |
| **Dynamic SoD** | Cấm hành động xung đột trên một đối tượng/ngữ cảnh | Không duyệt invoice do chính mình tạo |
| **Workflow SoD** | Tách người xin, người duyệt, người cấp và người kiểm tra khi cần | Không tự chứng nhận toàn bộ chuỗi cấp admin |

Security approval nên tính **quyền hiệu lực** sau role hierarchy, nested groups và direct grants. Chỉ cấm hai **tên role** có thể bỏ sót một role thứ ba chứa cả hai permission.

### SoD không phải lý do duy nhất để yêu cầu nhiều chữ ký

Hai người cùng bấm Approve không bảo đảm độc lập nếu họ cùng dùng một account hoặc cùng bị policy lỗi. Cần kiểm soát **identity của approver, quyền duyệt, conflict of interest, delegation và audit**.

## 13. Kiểm tra danh tính, MFA và mức bảo đảm

Security approval có thể đặt điều kiện **xác thực mạnh** khi cấp quyền nhạy cảm:

- Xác minh requester/beneficiary qua IdP và account mapping đáng tin.
- Kiểm tra **lifecycleState, relationshipId, effectiveAt** theo nguồn có thẩm quyền.
- Yêu cầu **MFA/step-up** gần thời điểm kích hoạt quyền khi cần.
- Ưu tiên **phishing-resistant MFA** cho hoạt động đặc quyền theo chính sách phù hợp.
- Kiểm tra **device posture/session risk** từ nguồn được xác minh, không tin User-Agent tự khai.
- Ràng buộc approval và grant với **đúng subject**; không chia sẻ credential.

**MFA chứng minh một đặc tính của phiên, không chứng minh nhu cầu nghiệp vụ.** Manager approval chứng minh nhu cầu, không thay thế MFA. Một request được Security phê duyệt cũng không có nghĩa mọi phiên tương lai tự đạt assurance cần thiết.

### Khi approver là người duyệt

Bản thân **Security approver** cũng phải được xác thực và phân quyền. Với phê duyệt rủi ro cao, có thể yêu cầu step-up khi đưa ra quyết định hoặc ký approval, cùng chống thay đổi nội dung request sau khi ký.

## 14. Quy trình duyệt nối tiếp, song song và điều kiện quorum

Tùy chính sách, các bước duyệt có thể:

- **Sequential:** Manager → Resource owner → Security.
- **Parallel:** Manager và Security cùng nhận yêu cầu độc lập, sau đó tổng hợp kết quả.
- **Conditional:** chỉ gọi Security khi action/risk/SoD vượt ngưỡng.
- **Quorum:** một số quyết định yêu cầu nhiều người có thẩm quyền cùng đồng ý.
- **Delegated:** người được ủy quyền hợp lệ phê duyệt khi primary approver vắng mặt.
- **Policy-driven:** một nhóm yêu cầu được tự động chấp thuận theo rule có kiểm soát.

### Lựa chọn nào tốt hơn?

| Mô hình | Điểm mạnh | Rủi ro |
|---|---|---|
| **Sequential** | Thấy đầy đủ căn cứ của bước trước | Độ trễ do phụ thuộc hàng đợi |
| **Parallel** | Rút ngắn thời gian chờ | Cần quản lý xung đột, phiên bản request |
| **Conditional Security** | Tập trung nguồn lực vào rủi ro cao | Nếu risk classification sai, request bị đi vòng |
| **Quorum** | Tăng độc lập cho quyền đặc biệt | Tốn thời gian, phải xác minh từng thành viên |
| **Auto-decision** | Tốc độ, nhất quán | Phụ thuộc chất lượng policy và dữ liệu |

### Kết hợp kết quả

Một policy có thể yêu cầu **Manager Permit AND ResourceOwner Permit AND Security Permit**. Nếu Security trả **Deny bắt buộc**, việc các bên khác đồng ý không tạo quyền override. Nếu Security cần **additional information**, workflow không được coi là Approved.

**Quorum không đồng nghĩa một số người bất kỳ bấm Agree.** Phải xác minh đúng **nhóm chức năng, độc lập, thẩm quyền và yêu cầu số lượng**.

## 15. Các kết quả Security approval cần tách biệt

Một quyết định cần có ngữ nghĩa đủ rõ:

| Decision | Ý nghĩa | Hành động tiếp theo |
|---|---|---|
| **APPROVED** | Các điều kiện bắt buộc đạt, được phép đi tới fulfillment | Revalidate trước khi cấp |
| **APPROVED_WITH_CONDITIONS** | Chấp thuận chỉ nếu nghĩa vụ/giới hạn cụ thể được thực thi | Kiểm tra điều kiện trước activation |
| **DENIED** | Không cho cấp theo policy hoặc rủi ro | Không provision; ghi reason code |
| **MORE_INFO_REQUIRED** | Thiếu dữ liệu hoặc mục đích chưa rõ | Bổ sung thông tin rồi đánh giá lại |
| **ESCALATED** | Ngoài thẩm quyền Security reviewer cấp này | Chuyển đúng risk owner/quy trình |
| **EXPIRED** | Quyết định không còn giá trị theo thời hạn | Yêu cầu đánh giá mới |
| **CANCELED / SUPERSEDED** | Request thay đổi hoặc bị hủy | Không cấp dựa trên approval cũ |
| **POLICY_APPROVED** | Policy đã được ủy quyền tự động chấp thuận | Ghi policy version và căn cứ |

Một số sản phẩm có tên trạng thái khác; đây là **mô hình đề xuất**, không phải tập status chuẩn của OAuth/SCIM.

### APPROVED_WITH_CONDITIONS không phải một ghi chú tùy chọn

Ví dụ Security chấp thuận nếu:
- chỉ cấp **DB_MAINTENANCE** thay vì **DB_SUPERUSER**;
- giới hạn **45 phút**;
- yêu cầu **phishing-resistant MFA**;
- ghi audit các lệnh nhạy cảm;
- ngăn export dữ liệu khách hàng.

**Fulfillment phải thực thi những điều kiện này**, hoặc request phải quay lại thẩm định nếu target không làm được. Không được biến quyết định có điều kiện thành **full admin không hạn** chỉ vì connector không hỗ trợ đủ.

## 16. Một bản ghi Security decision cần chứa gì?

Ví dụ minh họa:

~~~json
{
  "decisionId": "sec-approval-20261123-028",
  "requestId": "ar-20261123-0085",
  "requestVersion": 3,
  "decision": "APPROVED_WITH_CONDITIONS",
  "approver": {
    "identityId": "security-713",
    "approvalAuthority": "PRIVILEGED_ACCESS_REVIEWER"
  },
  "evaluatedSubjectId": "person-2046",
  "targetSystem": "db-payments",
  "approvedScope": {
    "tenantId": "org-vn",
    "resourceId": "cluster-payments-primary",
    "actions": [
      "database.schema.inspect",
      "database.maintenance.execute"
    ]
  },
  "approvedFrom": "2026-11-23T10:00:00+07:00",
  "approvedUntil": "2026-11-23T10:45:00+07:00",
  "conditions": [
    "STRONG_MFA_BEFORE_ACTIVATION",
    "PAM_SESSION_AUDIT",
    "NO_BULK_EXPORT",
    "REVOKE_AFTER_EXPIRY"
  ],
  "riskTier": "HIGH",
  "reasonCode": "TIME_BOUND_MAINTENANCE_ACCEPTED",
  "policyVersion": "privileged-access-v7",
  "decidedAt": "2026-11-23T09:44:00+07:00",
  "decisionExpiresAt": "2026-11-23T10:00:00+07:00",
  "correlationId": "corr-c6f2"
}
~~~

Đây là dữ liệu minh họa, không phải chuẩn API. **approvedUntil** mô tả thời hạn grant được cho phép; **decisionExpiresAt** là hạn dùng quyết định để bắt đầu fulfillment. Chúng không bắt buộc bằng nhau.

### Trường bắt buộc phải gắn kết

**Một decision chỉ được dùng cho đúng request version, beneficiary, scope và thời hạn đã xét.** Nếu những trường đó thay đổi bản chất, workflow phải xác định approval cũ không còn phù hợp và đánh giá lại.

## 17. State machine của Security approval

~~~mermaid
stateDiagram-v2
    [*] --> Pending
    Pending --> Evaluating: Kiểm tra eligibility, risk, SoD
    Evaluating --> MoreInfo: Cần bổ sung dữ liệu
    MoreInfo --> Evaluating: Request cập nhật phiên bản
    Evaluating --> Approved: Điều kiện đạt
    Evaluating --> Conditional: Chấp thuận kèm guardrail
    Evaluating --> Denied: Không đạt policy
    Evaluating --> Escalated: Ngoài thẩm quyền
    Escalated --> Evaluating: Reviewer có thẩm quyền tiếp nhận
    Approved --> Superseded: Request thay đổi đáng kể
    Conditional --> Superseded: Điều kiện hoặc scope đổi
    Approved --> Expired: Quyết định quá hạn
    Conditional --> Expired: Quyết định quá hạn
    Approved --> FulfillmentReady: Revalidation đạt
    Conditional --> FulfillmentReady: Obligations được xác minh
    FulfillmentReady --> [*]
    Denied --> [*]
    Expired --> [*]
    Superseded --> [*]
~~~

Đây là **state machine riêng của approval decision**, không bao gồm toàn bộ vòng đời entitlement sau khi đã cấp. Một quyết định **FulfillmentReady** chưa có nghĩa ứng dụng đã nhận quyền; job cấp phát, target readback và runtime enforcement vẫn phải diễn ra.

### Chống đánh tráo trạng thái

Không cho phép các transition như **DENIED → FULFILLED** không qua đánh giá mới, hoặc **SUPERSEDED → APPROVED** chỉ bằng retry job cũ. Mỗi transition phải có **actor, version, timestamp, idempotency key và audit** phù hợp.

## 18. Kiểm tra lại ngay trước fulfillment

Một lỗi nguy hiểm: Security duyệt lúc 09:00; đến 09:15 nhân viên bị chuyển vai trò hoặc Leaver; 09:30 một worker đọc trạng thái APPROVED cũ và cấp quyền admin.

**Điều kiện JML phải được kiểm tra lại tại thời điểm provision/activation**, không chỉ lúc approver bấm duyệt.

### Luồng kiểm tra trước khi cấp

~~~text
function canFulfillApprovedRequest(request, decision):
    require decision.requestId == request.id
    require decision.requestVersion == request.version
    require decision.beneficiaryId == request.beneficiaryId
    require decision.scopeCovers(request.approvedScope)
    require decision.isValidAt(serverTime)

    identity = loadTrustedIdentity(request.beneficiaryId)
    relationship = loadAuthoritativeRelationship(request.relationshipId)

    if not relationship.isActiveFor(request.activationWindow):
        return DENY

    if identity.isTerminatedOrSuspended():
        return DENY

    if currentSourceVersionSupersedes(request.sourceVersion):
        return REEVALUATE

    if not requiredBusinessApprovalsAreValid(request):
        return DENY

    if not currentSecurityGuardsAllow(request, identity):
        return DENY

    if not allMandatoryConditionsAreEnforceable(decision.conditions):
        return DENY_OR_ESCALATE

    return PERMIT_FULFILLMENT
~~~

Đây là **giả mã**. Với **future-effective Joiner**, có thể được phép **chuẩn bị account** trước ngày bắt đầu nhưng chưa được kích hoạt action. Quy trình cần phân biệt **prepared, provisioned, active và usable**, không kết luận mọi thao tác sớm đều sai trong mọi trường hợp.

### Đừng dùng bản phê duyệt cũ để vượt Leaver

Một request Approved ở phiên bản hợp lệ trước đây không mang quyền chống lại **nguồn JML mới hơn**. Cần **source version/fencing** để ngăn job cũ mở lại entitlement đã bị thu hồi.

## 19. Security approval trong Joiner lifecycle

Khi người mới gia nhập, hệ thống thường cấp **birthright access** tự động theo job function và phê duyệt chính sách đã có. Security approval bổ sung cần thiết cho **quyền nhạy cảm ngoài baseline**, không nhất thiết cho mọi account.

### Trình tự mẫu

1. HRIS/contract source xác minh **personId, relationshipId và effectiveAt**.
2. Identity proofing và enrollment gắn đúng chủ thể với account/authenticator.
3. IAM tính **baseline roles** theo RBAC/ABAC.
4. Nếu cần quyền đặc biệt, người có thẩm quyền gửi **Access request**.
5. Manager xác nhận nhiệm vụ; Security kiểm **least privilege, SoD, MFA, scope và TTL**.
6. Connector SCIM/API hoặc PAM cấp quyền **đúng thời điểm được phép**.
7. Resource server xác minh action/tenant/permission.
8. Reconciliation chứng minh không có thiếu quyền hoặc quyền thừa.

### Sai lầm Joiner

Copy tất cả role của người tiền nhiệm có thể tái tạo **privilege creep** đã tích lũy trong nhiều năm. Security approval cần nhìn vào **effective permissions thực**, không chỉ vai trò mẫu hoặc tên chức danh.

### Account đã tồn tại trước ngày bắt đầu

Cho phép chuẩn bị identity và account không đồng nghĩa cấp sẵn **production-admin** có thể sử dụng. Nếu policy yêu cầu chờ effectiveAt, phải chặn action cho đến mốc đó.

## 20. Security approval trong Mover lifecycle

**Mover** là chuyển chức năng, bộ phận, hợp đồng, dự án, tenant hoặc quan hệ quản lý. Rủi ro chính là **privilege accumulation**: cấp quyền mới nhưng không gỡ quyền cũ.

### Tình huống mẫu

Lan chuyển từ Sales Operations sang Finance Analysis.

| Quyền | Trước Mover | Mong muốn sau Mover | Việc cần xem |
|---|---|---|---|
| CRM Sales Reader | Có | Thu hồi | Group/role cũ |
| CRM Customer Export | Có qua ngoại lệ | Thu hồi ngay khi không còn căn cứ | Token, session và JIT grant |
| Finance Report Reader | Không | Cấp | Policy có thể tự duyệt |
| Finance Invoice Approver | Không | Chỉ cấp khi được chấp thuận | SoD, scope, hạn mức |
| IAM Admin | Không | Không | Ngăn quyền quá rộng |

### Security phải kiểm tra gì?

- Tập quyền **trước/sau**, bao gồm direct grants, nested groups và role hierarchy.
- SoD giữa quyền cũ chưa gỡ và quyền mới sắp cấp.
- Các request đang chờ có còn phù hợp với **job/relationship version mới** không.
- Token/claim SSO còn chứa role cũ có thể cho phép action không mong muốn không.
- Hệ thống đích đã gỡ các entitlement cũ qua SCIM/API và đối soát chưa.

**Security approval cho role mới không có nghĩa đồng ý giữ role cũ.** Một Mover hoàn chỉnh cần có cả **grant mới và revoke quyền không còn hợp lệ**.

## 21. Security approval trong Leaver lifecycle

Khi quan hệ công việc kết thúc, **Leaver không nên đòi một lượt Security approval thủ công để được thu hồi quyền** nếu chính sách đã yêu cầu thu hồi ngay. Việc cắt truy cập là nghĩa vụ theo nguồn có thẩm quyền và cần thực thi kịp thời.

### Những nguyên tắc quan trọng

1. **Không cấp quyền mới** hoặc thực hiện request còn chờ dựa trên approval cũ của người đã Leaver.
2. **Hủy/đình chỉ** approval và request không còn căn cứ.
3. **Thu hồi entitlement** của quan hệ đã kết thúc tại hệ thống đích.
4. **Disable IdP/SSO** và xử lý session theo chính sách.
5. **Thu hồi privileged grants, JIT/PAM sessions, API key, SSH key, OAuth refresh/access token** hoặc chặn chúng ở resource server.
6. Kiểm tra **local account** và direct grants không đi qua IGA/IdP.
7. Ghi **readback, revoke latency, owner và exception** nếu có quyền tồn dư.

### Một ví dụ lỗi cần tránh

- 16:00: HRIS phát Leaver hiệu lực.
- 16:01: IdP disable account.
- 16:05: Queue tiếp tục chạy một request đã Security-approved từ 15:00.
- 16:06: Connector gán quyền admin trong SaaS vì không kiểm lifecycle mới.

Tình huống này là **stale approval / stale fulfillment**. Giải pháp là kiểm nguồn JML ngay trước thay đổi, chặn phiên bản workflow cũ, xử lý race condition với revocation và đối soát tại đích.

### Một người có nhiều quan hệ

Một cá nhân có thể vừa là nhân viên vừa có hợp đồng độc lập. Việc kết thúc một quan hệ phải làm mất căn cứ cho những quyền gắn với **relationshipId đó**, không xóa hoặc giữ nhầm quyền của quan hệ khác. Security approval phải nhìn **quyền theo quan hệ và mục đích**, không chỉ email.

## 22. Rejoiner: phê duyệt cũ không tự có hiệu lực trở lại

Khi một người quay lại tổ chức, IAM có thể giữ identity ID lịch sử để liên kết dữ liệu theo chính sách, nhưng **authorization phải dựa trên quan hệ công việc mới**.

- Không sử dụng lại **approval cũ, grant cũ hoặc ticket cũ** để mở lại quyền.
- Xác minh job function, contract, tenant, manager và resource scope mới.
- Xác minh account linkage tránh trường hợp email đã được tái sử dụng.
- Enrollment/MFA và thiết bị phải đáp ứng yêu cầu hiện hành.
- Security review mới khi quyền đặc biệt cần thiết.
- Đối soát để tránh local admin hoặc direct permission từ giai đoạn trước còn sót.

**Same person không có nghĩa same entitlement.** Phê duyệt là quyết định theo **ngữ cảnh và thời điểm**, không phải đặc quyền đi theo cá nhân vĩnh viễn.

## 23. Security approval cho JIT/PAM/PIM

**Just-in-time access (JIT)** giới hạn quyền đặc biệt theo tác vụ và thời hạn. **PAM/PIM** có thể hỗ trợ eligibility, activation, session brokering, approval và revocation.

### Hai mức quyết định

| Mức | Ý nghĩa | Điều không được suy ra |
|---|---|---|
| **Eligible approval** | Người dùng đủ điều kiện **xin kích hoạt** role | Role đang active |
| **Activation approval** | Một yêu cầu bật quyền cụ thể được duyệt | Target đã cấp và session/token đã đồng bộ |
| **Active grant** | Quyền được cấp và còn hiệu lực | Đã sử dụng hợp lệ mọi action |
| **Expired/revoked grant** | Quyền không còn căn cứ cho thực thi | Mọi target/session tự chắc chắn đã chặn |

### Security nên xem

- Có thể **giảm standing privilege** bằng JIT không?
- Có thể giới hạn **action/resource** thay vì toàn bộ admin role không?
- Mức MFA và **approval theo rủi ro** có phù hợp?
- Thời hạn tối đa và **khả năng thu hồi sớm** khi Mover/Leaver?
- Session recording/command audit có cần và được bảo vệ đúng không?
- Token/credential tạm có thể sống vượt grant không?
- Có chứng cứ **readback và deny test** khi quyền hết hạn không?

Một yêu cầu JIT **30 phút** không tự động an toàn nếu được cấp **global-admin**. Cần kết hợp **scope hẹp, just-enough-administration, credential protection và enforcement**.

## 24. Security approval cho contractor, partner và guest

Tổ chức có thể có các quan hệ không được HRIS nhân viên quản lý đầy đủ:

| Điều kiện | Câu hỏi thẩm định |
|---|---|
| **Sponsor** | Ai trong tổ chức chịu trách nhiệm cho đối tác? |
| **Contract validity** | Hợp đồng/quan hệ còn hiệu lực đến khi nào? |
| **Identity proofing** | Đã xác minh đúng người/đơn vị hợp tác? |
| **Federation trust** | IdP bên ngoài có đáp ứng assurance yêu cầu? |
| **Resource scope** | Đối tác được phép vào ứng dụng/dataset nào? |
| **MFA/device controls** | Có yêu cầu tăng cường theo dữ liệu/rủi ro? |
| **Duration** | Thời hạn truy cập có vượt hợp đồng không? |
| **Delegation** | Sponsor có được phép xin hộ và phê duyệt không? |
| **Revocation** | Khi sponsor/contract kết thúc, ai nhận sự kiện cắt quyền? |

**Không mặc định manager approval của nhân viên nội bộ là đủ để cấp admin cho bên thứ ba.** Cần owner tài nguyên và những kiểm soát phù hợp với quan hệ ngoài tổ chức.

Nếu sponsor Leaver, quyền của guest/contractor phải được **rà soát lại owner**, không để tài khoản bên ngoài tiếp tục hoạt động vô chủ.

## 25. Security approval cho service account và workload

**Service account, bot, CI/CD pipeline, device identity** không thể xử lý y hệt nhân viên vì chúng thường không có ngày sinh/đi làm/nghỉ việc trong HRIS.

### Dữ liệu cần có

- **Workload/client ID** và registry được xác minh.
- **Owner team** và người phê duyệt nghiệp vụ.
- **Action, API audience và resource** được phép.
- **Environment/tenant** rõ ràng.
- **Credential mechanism**: workload federation, managed identity, certificate, secret manager.
- **Thời hạn và lịch review** theo workload lifecycle.
- **Khả năng thu hồi secret/token** nếu workload ngừng hoặc owner bị thay đổi.
- **Khả năng đo tác vụ thực tế** và phát hiện scope không dùng.

### Ví dụ

Một pipeline cần **deployment.deploy** trên service-payments production. Security review yêu cầu **không dùng shared user password**, dùng workload identity có thể xác minh, giới hạn deployment permission và bảo vệ artifact/approval chain.

**Không cho bot vay tài khoản SSO của nhân viên** chỉ vì workflow phê duyệt dễ hơn. Ngược lại, khi owner cá nhân nghỉ việc, không xóa mù quáng một workload production còn hợp lệ: cần chuyển owner, xem lại quyền, bí mật người cũ biết và kế hoạch rotation.

## 26. Break-glass và Security approval trong tình huống khẩn cấp

**Break-glass** là đường truy cập khẩn cấp được **thiết kế, phê duyệt và kiểm thử trước** để sử dụng khi quy trình chuẩn không thể đáp ứng sự cố nghiêm trọng.

### Điểm khác với Security approval bình thường

| Tiêu chí | Quy trình thông thường | Break-glass |
|---|---|---|
| **Thẩm định** | Có thể yêu cầu security reviewer trước cấp | Có thể dùng kiểm soát khẩn cấp thay thế đã được duyệt |
| **Thời gian** | Theo nhu cầu được duyệt | Kích hoạt nhanh trong emergency được xác minh |
| **Quyền** | Least privilege theo request | Vẫn giảm phạm vi tối đa có thể |
| **Audit** | Ghi request/decision/provision | Cảnh báo tức thời và review sau sử dụng |
| **Credential** | Kênh IAM/PAM thường | Cơ chế dự phòng được bảo vệ |
| **Thu hồi** | Khi hạn hoặc thay đổi JML | Ngay khi khẩn cấp kết thúc, kiểm tra kỹ |
| **Kiểm thử** | Workflow integration tests | Kiểm tra định kỳ khả năng hoạt động khi phụ thuộc bị lỗi |

### Không được lạm dụng

- Nhãn **URGENT** trong form không tự chuyển thành break-glass.
- Tài khoản emergency không nên dùng như **đường hậu cửa thường trực**.
- Nếu IdP/PAM không hoạt động, phương án break-glass không nên phụ thuộc hoàn toàn vào đúng thành phần đang lỗi.
- Khi dùng ngoại lệ khẩn cấp phải có **nguyên nhân, actor, resource scope, cảnh báo, thời hạn và post-incident review**.

**Security approval của quy trình break-glass thường diễn ra ở cấp chính sách/cơ chế từ trước**, còn mỗi lần sử dụng cần ghi đầy đủ và rà soát theo mức rủi ro.

## 27. Kết nối approval với IdP, SSO, OAuth và SCIM

### IdP/SSO

IdP và SSO thực hiện **xác thực/federation**. Chúng có thể truyền nhóm, claim hoặc trạng thái phiên, nhưng **Security approval không tự trở thành SSO session**.

### OAuth/OIDC

- **OIDC ID token** dành cho relying party xác nhận sự kiện đăng nhập.
- **OAuth access token** dành cho resource server/API.
- **Refresh token** có thể cho phép xin access token mới theo policy.

Một approval cho quyền export có thể dẫn đến thay đổi claim hoặc group, nhưng API vẫn phải kiểm **audience, scope, quyền trên resource, trạng thái chủ thể và điều kiện hiệu lực**. Token cũ có thể chứa role đã thu hồi nếu resource server không có cơ chế kiểm trạng thái mới.

### SCIM provisioning

SCIM 2.0 giúp tạo/sửa/vô hiệu hóa **User/Group** tại ứng dụng đích. Security approval có thể làm căn cứ cho connector cập nhật membership/entitlement, nhưng:

- **Approval không phải SCIM User hoặc Group.**
- **SCIM Group.members** có thể được dùng để thay đổi thành viên nếu vendor hỗ trợ.
- **User.groups** trong core schema thường read-only.
- **SCIM active=false** không tự bảo đảm mọi session/API key lập tức bị vô hiệu.
- Một số role/license cần **API riêng**, không thể cấp chỉ qua SCIM.

### Các lớp liên kết

~~~mermaid
flowchart LR
    HR[HRIS / Contract registry] --> IGA[IAM / IGA]
    REQ[Access request] --> IGA
    IGA --> SEC[Security approval + Policy]
    SEC --> PROV[SCIM / App API / PAM]
    PROV --> APP[Target application]
    IGA --> IDP[IdP / SSO / MFA]
    IDP --> APP
    APP --> AUTHZ[PEP: RBAC / ABAC / PBAC]
    APP --> OBS[Readback / Audit]
    OBS --> IGA
~~~

**Đã phê duyệt ≠ đã cấp ≠ API đã cho phép đúng ≠ đã thu hồi khi không còn quyền.** Mỗi lớp cần evidence và trách nhiệm riêng.

## 28. Lỗi vận hành: timeout, retry, đồng thời và approval stale

### Timeout sau khi cấp quyền

Connector gọi API thêm role, ứng dụng đã thực hiện nhưng response bị mất. Workflow không nên retry mù quáng hoặc báo thất bại hoàn toàn. Cần **readback** trạng thái target, tránh duplicate grant và kiểm tra đúng beneficiary/resource.

### Request bị sửa khi đang chờ duyệt

Nếu Security xem **v3** xin report.read, còn requester đổi thành **v4** xin report.export, quyết định trên v3 phải được **superseded/invalidated** theo policy; cần đánh giá lại phạm vi đã thay đổi.

### Hai reviewer đưa quyết định khác nhau

Một reviewer APPROVED, reviewer khác DENIED. Workflow phải dùng **quy tắc kết hợp đã được quy định**; không lấy “quyết định cuối cùng thắng” chỉ vì đến sau nếu hệ thống yêu cầu mọi reviewer đồng ý hoặc Deny có ưu tiên.

### Mover/Leaver xảy ra trong lúc chờ

Cần **authoritative source version** và kiểm tra lại ngay trước fulfillment. Một job cũ không được được phép **mở lại entitlement** sau khi người hưởng quyền đã chuyển vai trò hoặc nghỉ.

### Retry có bảo vệ

- Request ID và version được gắn với từng quyết định.
- Connector có operation/correlation ID và **idempotency** theo khả năng.
- Readback khi outcome không rõ.
- Backoff và giới hạn retry khi 429/5xx.
- Không tự bỏ điều kiện **ETag/If-Match** để ghi đè.
- Nếu không thể đảm bảo, chuyển **PARTIAL/FAILED** có owner và deadline.
- Không dùng đặc quyền quá rộng làm “workaround” cho một request nhỏ.

## 29. Threat model: cách Security approval có thể bị vượt qua

| Rủi ro | Hậu quả | Biện pháp phòng vệ |
|---|---|---|
| **Self-approval** | Người xin tự duyệt đặc quyền | Tách vai trò, kiểm identity/SoD |
| **Approver impersonation** | Attacker duyệt dưới danh nghĩa Security | Xác thực mạnh, RBAC approver, audit |
| **Approval replay** | Tái sử dụng decision cho request khác | Bind requestId/version/scope/subject/time |
| **Scope escalation after approval** | Sửa read thành admin sau duyệt | Immutable snapshot và re-approval |
| **Approval fatigue** | Reviewer bấm duyệt hàng loạt không thẩm định | Risk grouping, UI rõ permission, alerts, định kỳ review |
| **Fake ticket or justification** | Xin admin dựa trên incident giả | Kiểm nguồn ticket/owner có thẩm quyền |
| **Toxic role combination** | Vượt SoD qua nhiều role/nested group | Kiểm effective permissions và scope |
| **Wrong identity mapping** | Cấp quyền nhầm account | Immutable identity + target ID verification |
| **Cross-tenant provisioning** | Gán quyền cho tenant khác | Enforce tenant ID ở catalog, policy và target |
| **Stale approval after Leaver** | Mở quyền cho người đã nghỉ | Revalidate JML ngay trước grant |
| **Expired exception reused** | Duy trì quyền trái policy | Decision expiry và re-review |
| **Connector credential compromise** | Cấp role trái phép qua API | Least privilege, vault, monitoring, rotation |
| **Unenforced conditions** | “Approved with MFA” nhưng role luôn bật | Conditions gắn PEP/PAM và readback |
| **Token/session residual access** | Quyền vẫn dùng sau revoke | Session/token policy và target authorization |
| **Incomplete evidence** | Không chứng minh được ai đã duyệt/cấp | Decision/action/revocation traceability |

### Security approval cũng là bề mặt tấn công

Tài khoản của người duyệt, workflow engine, danh sách approver và API xử lý quyết định đều là **tài sản đặc quyền**. Cần phân quyền chặt, review quyền duyệt, hạn chế service token, kiểm toán và bảo vệ khả năng sửa lịch sử. Không cho người dùng tự chọn **securityApproverId** ngoài tập thẩm quyền rồi mặc nhiên chấp nhận.

## 30. Audit trail: phải giải thích được quyết định

Một bản ghi Security approval tốt cần giúp trả lời:

> Ai xin quyền cho ai, quyền gì trên tài nguyên nào, Security đánh giá những điều kiện gì, kết luận ra sao, phiên bản policy nào, và quyền có thực sự được cấp/thu hồi như quyết định?

### Các event hữu ích

1. **RequestSubmitted** – requester, beneficiary, scope, purpose, version.
2. **RiskEvaluationCompleted** – policy/risk finding, không chứa secret.
3. **SecurityReviewAssigned** – approver có thẩm quyền.
4. **SecurityDecisionRecorded** – quyết định, actor, điều kiện và reason.
5. **DecisionSuperseded/Expired** – bản cũ không còn hiệu lực.
6. **FulfillmentAuthorized** – đã revalidate nguồn và conditions.
7. **ProvisioningDispatched/Acknowledged** – connector/target operation.
8. **GrantObserved** – trạng thái account/group/role ở đích.
9. **PrivilegedActionObserved** – action thực tế khi cần.
10. **GrantExpired/Revoked** – sự kiện, actor và thời điểm.
11. **RevocationObserved** – bằng chứng quyền không còn active.
12. **ReconciliationFindingClosed** – nguyên nhân và người giải quyết.

### Audit event minh họa

~~~json
{
  "eventId": "audit-sec-20261123-087",
  "correlationId": "corr-c6f2",
  "requestId": "ar-20261123-0085",
  "requestVersion": 3,
  "beneficiaryId": "person-2046",
  "eventType": "SecurityDecisionRecorded",
  "decision": "APPROVED_WITH_CONDITIONS",
  "actorId": "security-713",
  "decisionId": "sec-approval-20261123-028",
  "policyVersion": "privileged-access-v7",
  "reasonCode": "TIME_BOUND_MAINTENANCE_ACCEPTED",
  "decisionTime": "2026-11-23T09:44:00+07:00",
  "scopeFingerprint": "scope-7d91",
  "evidenceRef": "review-privileged-284"
}
~~~

Đây là **JSON minh họa**, không phải format chuẩn của hệ thống IAM. Các mã fingerprint và reference không phải chữ ký bảo mật trừ khi implementation thực sự thiết kế chúng như vậy.

**Log không nên chứa password, bearer token, refresh token, private key, mã khôi phục hoặc toàn bộ dữ liệu cá nhân nhạy cảm.** Phải kiểm soát truy cập, thời hạn lưu và chống sửa trái phép đối với hồ sơ audit.

## 31. Các chỉ số đánh giá hiệu quả Security approval

| Metric | Ý nghĩa | Cần tránh suy diễn |
|---|---|---|
| **Security review volume** | Số request cần thẩm định theo loại và rủi ro | Nhiều review không tự nghĩa an toàn hơn |
| **High-risk request rate** | Tỷ lệ yêu cầu đặc quyền/dữ liệu nhạy cảm | Phụ thuộc phạm vi đo |
| **Auto-decision coverage** | Bao nhiêu request phù hợp policy tự động | Tỷ lệ cao không chứng minh đúng nếu policy lỗi |
| **Security decision lead time** | Từ ready-for-review tới decision | Nhanh không đồng nghĩa chất lượng |
| **Request rework rate** | Số request thiếu dữ liệu hoặc scope không hợp lệ | Giúp cải thiện catalog |
| **Denial/conditional rate** | Tỷ lệ từ chối, yêu cầu điều kiện | Không nên tối ưu chỉ bằng tăng Deny |
| **SoD conflicts prevented** | Xung đột được phát hiện/chặn | Không phản ánh toàn bộ xung đột chưa có coverage |
| **Stale approval blocked** | Request cũ bị chặn sau JML/version change | Cần xác minh không lọt |
| **Conditions enforcement rate** | Grant đã thực thi đúng giới hạn Security | Đòi readback và PEP evidence |
| **Approved-to-verified time** | Từ decision tới target khớp desired state | Tách khỏi decision latency |
| **Expired approval use attempts** | Cố dùng quyết định hết hạn | Phát hiện replay/bug |
| **Leaver revoke latency** | Từ effectiveAt tới hết quyền thực tế | Đánh giá quyền tồn dư |
| **Unowned approver routes** | Catalog thiếu Security approver hoặc owner | Rủi ro workflow bị kẹt |
| **Audit coverage** | Chuỗi request–decision–grant–revoke được ghi | Phải báo rõ app ngoài phạm vi |

### SLA khác nhau

Một request **read wiki** không cần quy trình giống **database admin trong incident**. Nên có SLA theo loại quyền và mức rủi ro. Nhưng với **Leaver hoặc thu hồi khẩn cấp**, hành động ưu tiên là **chặn quyền thực tế**, không chờ một lượt duyệt thường kỳ.

## 32. Kiểm thử Security approval workflow

Không chỉ test trường hợp mọi approver bấm Approve.

| Test case | Điều kiện | Kết quả mong đợi |
|---|---|---|
| Baseline hợp lệ | Low risk, policy đủ điều kiện | Auto-decision phù hợp |
| Yêu cầu đặc quyền | High risk, đủ business approval | Chuyển Security review |
| Thiếu nhu cầu nghiệp vụ | Không có owner/ticket cần thiết | More info hoặc Deny |
| Approver không đủ quyền | Người bất kỳ bấm Approve | Không ghi quyết định hợp lệ |
| Self-approval | Người xin trùng Security reviewer trong rule cấm | Deny/escalate |
| Cross-tenant | Request resource thuộc tenant khác | Deny |
| Scope rộng | Xin global admin khi chỉ cần read | Thu hẹp hoặc Deny |
| SoD conflict | Vai trò mới xung đột effective permissions | Deny/exception control |
| Thiếu MFA | Chưa đủ assurance khi activation | Step-up hoặc không cấp |
| Request thay đổi | Từ version 3 sang 4 sau approval | Approval v3 không hợp lệ cho v4 |
| Approval hết hạn | Fulfillment tới muộn | Reevaluate, không cấp mù |
| Mover trước fulfillment | Role cũ không còn phù hợp | Cancel/reevaluate |
| Leaver trước fulfillment | Quan hệ hết hiệu lực | Không cấp; xử lý grant đã tạo một phần |
| Connector timeout | Đích đã gán role nhưng response mất | Readback, tránh duplicate |
| Điều kiện không thực thi được | Target không hạn chế thời gian hoặc MFA | Không nâng cấp sang quyền rộng |
| Revocation còn session | Gỡ group nhưng session/token vẫn permit | Partial và remediation |
| Reviewer Leaver | Người được route approval đã rời tổ chức | Reassign theo authority, không giả mạo |
| Approver disagreement | Một Permit, một Deny | Kết hợp theo policy, không last-writer-wins |
| Break-glass | Luồng chuẩn không khả dụng | Chỉ dùng đường dự phòng đã kiểm soát |
| Service account không owner | Bot xin cloud admin không sponsor | Deny/More info theo policy |

### Các tầng kiểm thử

1. **Policy unit tests:** risk, SoD, approval authority, expiry.
2. **Workflow state tests:** version, cancel, supersede, reassign, expiration.
3. **Integration tests:** IdP, HRIS/JML, IAM, PAM, SCIM/API và target.
4. **Concurrency/race tests:** approval cạnh tranh với revoke hoặc Leaver.
5. **Adversarial tests:** sửa subject/scope sau approval, approval replay, IDOR.
6. **Failure injection:** timeout, 429, 5xx, missing attributes, PDP unavailable.
7. **Runtime verification:** permission đủ hẹp và deny đúng sau expiry.
8. **Audit tests:** đủ evidence nhưng không rò rỉ secret.

**Kiểm thử Approval flow thành công chưa đủ nếu không kiểm thử việc backend thực sự từ chối action không được phép.**

## 33. Runbook: Security approval bị kẹt hoặc gây sai lệch

### Trường hợp A — Review chờ quá hạn

1. Kiểm request còn nhu cầu, beneficiary còn ACTIVE và thời hạn chưa qua.
2. Xác minh nhóm Security approver, delegation và thẩm quyền hiện tại.
3. Kiểm Security cần thêm thông tin gì từ business/resource owner.
4. Escalate theo quy trình, không tự gán approver là requester.
5. Nếu requester đã Mover/Leaver hoặc công việc đã hủy, vô hiệu yêu cầu cũ.
6. Ghi quyết định và lý do đầy đủ.

### Trường hợp B — Security đã duyệt nhưng ứng dụng chưa có quyền

1. Xác minh decision dành đúng **requestId/version/subject/scope**.
2. Kiểm điều kiện MFA, JIT TTL, SoD và approval nghiệp vụ.
3. Kiểm connector mapping, tenant và API credential.
4. Readback kết quả sau timeout; tránh POST/patch lặp mù.
5. Kiểm role/group/entitlement tại đích, không chỉ status của broker.
6. Nếu còn 403, kiểm action/object-level ABAC, SSO session và cache.
7. Không cấp Admin rộng để che lỗi entitlement hẹp.

### Trường hợp C — Quyền được cấp vượt phạm vi Security duyệt

1. Ưu tiên **thu hẹp/chặn quyền sai** theo rủi ro.
2. So sánh decision snapshot với target grant thực tế.
3. Xác định lỗi catalog mapping, connector, manual override hoặc request tampering.
4. Kiểm những chủ thể khác cùng chịu ảnh hưởng.
5. Đối soát token/session và direct grants.
6. Mở incident, lưu evidence và sửa policy/automation trước khi cấp lại.

### Trường hợp D — Leaver vẫn còn quyền mặc dù workflow đã đóng

1. Kiểm nguồn HRIS, effectiveAt, relationshipId và event version.
2. Kiểm approval/request cũ có còn job chờ được phép thực hiện không.
3. Kiểm IAM, SCIM, PAM, local account và cloud role.
4. Kiểm session, JWT/access token, refresh token và API key.
5. Chặn action tại PEP/RS khi có thể, xử lý các credential ngoài SSO.
6. Chỉ đóng khi **observed access** đạt chính sách, hoặc ghi ngoại lệ chưa thể giải quyết với owner và SLA.

## 34. Tình huống xuyên suốt: Security approval qua JML

Giả sử **Minh** làm việc tại đội vận hành hệ thống thanh toán. Doanh nghiệp dùng IdP có MFA, IGA, PAM/JIT, SCIM và các API kiểm RBAC/ABAC.

### Giai đoạn A — Joiner

HRIS phát Joiner với identityId, relationshipId và effectiveAt. IAM chuẩn bị account IdP, enrollment MFA và baseline **logs.read**. Minh được **eligible** để yêu cầu quyền bảo trì khi nằm trong nhóm on-call, nhưng không có standing production-admin.

### Giai đoạn B — Access request đặc quyền

Một sự cố production xảy ra. Minh gửi request xin **database.maintenance.execute** trên **cluster-payments-primary** trong 45 phút, liên kết incident đã được xác minh. Manager xác nhận nhiệm vụ; application owner xác định thao tác cần làm.

Security xem quyền hiện có, SoD, khả năng giám sát và thời hạn. Reviewer quyết định **APPROVED_WITH_CONDITIONS**: không cấp global DB superuser, yêu cầu strong MFA và PAM session audit, hạn đến 10:45.

### Giai đoạn C — Fulfillment

PAM broker kiểm lại quyết định và trạng thái JML, bật role hẹp. Target xác nhận role đang active. Minh thực hiện một lệnh bảo trì; PEP và audit ghi nhận actor, action, resource và outcome. Khi incident đóng sớm, broker thu hồi grant và kiểm quyền thực tế đã mất.

### Giai đoạn D — Mover

Minh chuyển khỏi đội vận hành sang nhóm Analytics. IAM thu hồi eligibility production-maintenance và mọi grant còn active; cấp quyền đọc báo cáo theo role mới. Một request bảo trì cũ chưa fulfillment phải bị **cancel hoặc reevaluate**, không được cấp vì đã có Security approval từ khi Minh còn ở Ops.

### Giai đoạn E — Leaver

Sau đó Minh nghỉ việc. HRIS phát Leaver, IdP chặn login, IGA/SCIM deprovision account/group và PAM thu hồi privileged sessions. Security cùng IAM kiểm những API key, SSH key và local account độc lập. Nếu một access token đã phát trước đó vẫn gọi được API, cần chặn tại resource server hoặc cơ chế thu hồi phù hợp; workflow chưa được coi là hoàn tất.

### Giai đoạn F — Rejoiner

Minh quay lại dưới quan hệ mới. Identity lịch sử có thể được liên kết theo chính sách, nhưng **approval cũ không tự bật lại quyền production**. Những request mới phải đánh giá theo nhiệm vụ, owner, SoD và các điều kiện hiện hành.

### Bài học rút ra

**Security approval kiểm soát rủi ro của quyết định cấp quyền, không thay thế toàn bộ vòng đời quyền**. Trong Joiner–Mover–Leaver, những gì cần chứng minh là **quyền được cấp đúng mục đích, đúng phạm vi, đúng thời điểm và bị chặn khi căn cứ không còn**, không chỉ có chữ ký phê duyệt trong ticket.

## 35. Checklist thiết kế Security approval an toàn

1. **Định nghĩa:** đã phân biệt Security approval với business, manager và resource owner approval?
2. **Scope:** có danh mục quyền nào cần Security review, tự duyệt và chuyển escalation?
3. **Requester/beneficiary:** đã lưu riêng người xin và người hưởng quyền bằng ID tin cậy?
4. **JML:** relationshipId/effectiveAt và nguồn có thẩm quyền được kiểm trước review và trước fulfillment?
5. **Catalog:** quyền xin có owner, action, target, tenant/resource scope và mapping kỹ thuật?
6. **Least privilege:** đã giảm role/scope/time xuống đúng tác vụ?
7. **Risk:** đã xét dữ liệu, môi trường, đặc quyền, thời hạn và khả năng giám sát?
8. **Hard guardrails:** SoD, Leaver, cross-tenant hoặc thiếu nguồn tin cậy không bị điểm số khác lấn át?
9. **MFA/step-up:** có assurance phù hợp cho người xin và người duyệt khi cần?
10. **Approver authority:** Security reviewer có quyền hợp lệ, không tự duyệt sai SoD?
11. **Parallel/quorum:** có quy tắc kết hợp và xử lý Deny/conflict rõ ràng?
12. **Decision outcomes:** APPROVED, CONDITIONAL, DENIED, MORE_INFO, ESCALATED và EXPIRED được phân biệt?
13. **Conditions:** điều kiện approved-with-conditions được target/PEP/PAM thực thi thật?
14. **Binding:** quyết định gắn đúng requestId/version/subject/action/scope/time?
15. **Stale approvals:** request sửa, Mover, Leaver hoặc decision quá hạn có kích hoạt đánh giá lại?
16. **JIT/PAM:** có thể dùng eligible/active grant có hạn thay cho standing admin?
17. **IdP/SSO:** đã tách xác thực khỏi cấp và thực thi quyền?
18. **OAuth/SCIM:** token claim, group, local app session và direct grants có được xử lý đúng?
19. **Fulfillment:** connector có theo dõi operation, timeout, retry và target readback?
20. **Leaver:** thu hồi không phải chờ Security duyệt lại khi policy đã yêu cầu cắt ngay?
21. **Rejoiner:** decision/grant của quan hệ cũ không tự hồi sinh?
22. **Non-human:** workload có registry, owner, purpose, credential và review riêng?
23. **External access:** sponsor, contract expiry và federation trust được kiểm soát?
24. **Break-glass:** có đường khẩn cấp được phê chuẩn trước, audit và post-review?
25. **Audit:** lưu decision, policy version, reason, actor, evidence và outcome, không chứa secret?
26. **Testing:** có test self-approval, replay, scope tampering, SoD, stale approval và failure cases?
27. **Metrics:** đo lead time, conditional enforcement, approved-to-verified và revoke latency?
28. **Reconciliation:** đã xác minh target chấp nhận/từ chối đúng action và ghi rõ coverage?
29. **Ownership:** exception/partial fulfillment có owner, deadline và escalation?
30. **Lifecycle closure:** chỉ đóng khi quyết định và quyền thực tế đều phù hợp chính sách hiện hành?

### Ghi nhớ

**Security approval là bước thẩm định rủi ro bảo mật trong approval workflow trước khi cấp hoặc kích hoạt quyền truy cập.** Nó phải đánh giá **identity, quan hệ công việc, action, resource scope, least privilege, SoD, MFA, thời hạn, khả năng giám sát và thu hồi**, đồng thời phân biệt quyết định nghiệp vụ với quyết định Security. Một kết quả **APPROVED** chỉ cho phép đi đến fulfillment; **APPROVED_WITH_CONDITIONS** yêu cầu thực thi đầy đủ guardrail. Trong **Joiner–Mover–Leaver**, approval phải được **gắn với đúng request version và trạng thái danh tính hiện hành**, không bị dùng lại sau Mover/Leaver. **IdP/SSO, SCIM, PAM/JIT, RBAC/ABAC, token/session handling và reconciliation** cùng bảo đảm rằng quyền được cấp đúng và **không còn quyền truy cập tồn dư** khi căn cứ đã hết.
