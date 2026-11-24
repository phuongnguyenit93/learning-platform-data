# Third-party audit: Kiểm toán danh tính và quyền truy cập của bên thứ ba

## 1. Third-party audit trong IAM là gì?

**Third-party audit** là hoạt động thu thập, đối chiếu và đánh giá bằng chứng về danh tính, tài khoản và quyền truy cập của các chủ thể **không phải nhân sự nội bộ**: nhà thầu, nhân viên nhà cung cấp, đối tác, đơn vị thuê ngoài, chuyên gia tư vấn và các tích hợp máy–máy. Mục tiêu là chứng minh quyền được cấp **đúng người, đúng mục đích, đúng phạm vi, đúng thời hạn**, được giám sát và bị thu hồi khi quan hệ hợp tác kết thúc.

Trong module `SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE`, kiểm toán bên thứ ba phải bám sát **Joiner–Mover–Leaver (JML)**: xác minh người được đối tác giới thiệu; cấp tài khoản qua IdP/SSO hoặc federation; gán quyền theo RBAC/ABAC; cập nhật khi thay đổi hợp đồng, vai trò hoặc sponsor; và deprovision bằng SCIM/API khi hợp đồng hết hạn. Khác với nhân sự chính thức, dữ liệu HRIS có thể **không bao phủ** danh tính bên ngoài. Vì vậy, mỗi danh tính cần có nguồn xác nhận và người bảo trợ nội bộ (sponsor/owner) rõ ràng.

**Phân biệt:** kiểm toán danh tính bên thứ ba không đồng nhất với kiểm toán tuân thủ toàn bộ nhà cung cấp (tài chính, pháp lý, bảo mật hạ tầng). Nội dung ở đây tập trung vào tài khoản, authentication, authorization, entitlement, session/credential, sự kiện vòng đời và chứng cứ vận hành IAM. Kết quả của nó có thể cung cấp đầu vào cho đánh giá rủi ro nhà cung cấp rộng hơn.

## 2. Các rủi ro đặc thù của danh tính bên ngoài

| Rủi ro | Biểu hiện | Bằng chứng cần kiểm tra |
|---|---|---|
| Không có nguồn danh tính chuẩn | Người đã rời nhà cung cấp vẫn nằm trong nhóm SSO | Hồ sơ sponsor, nguồn xác minh và status hiện hành |
| Quyền hết hạn nhưng chưa thu hồi | Nhà thầu vẫn truy cập repo sau ngày kết thúc | Contract end date, effective grants và API test |
| Quá phụ thuộc IdP đối tác | Partner disable user nhưng ứng dụng giữ session cũ | Federation logs, session/token policy, access tests |
| Tài khoản chung | Nhiều người dùng một tài khoản vendor | Identity mapping, sign-in logs, hợp đồng kiểm soát |
| Gán quyền vượt phạm vi | Partner đọc dữ liệu tenant hoặc dự án khác | RBAC/ABAC policy, PEP decisions và thử truy cập |
| Người bảo trợ nghỉ việc | Tài khoản vendor không còn owner nội bộ | Sponsor inventory và quy trình reassignment |
| Quyền cấp trực tiếp | App local role không có trong IAM | Application entitlement export và reconciliation |
| Credential máy tồn dư | API key tích hợp không có owner/expiry | Secret inventory, rotation/revocation evidence |
| Không đủ log | Không thể chứng minh ai duyệt hoặc thu hồi | Correlation ID, immutable audit trail và completeness |

Kiểm toán phải đánh giá **quyền có hiệu lực tại ứng dụng**, không chỉ trạng thái một user object trong IdP. Ví dụ, IdP có thể báo account inactive nhưng tài khoản local hoặc personal access token tại SaaS vẫn hoạt động.

## 3. Xác định phạm vi, tiêu chí và chủ thể chịu trách nhiệm

Định nghĩa phạm vi trước khi lấy mẫu: các nhà cung cấp, ứng dụng, hệ thống dữ liệu, tenant, môi trường, loại tài khoản và khoảng thời gian. Với đơn vị có quyền cao như quản trị hạ tầng hoặc xử lý dữ liệu nhạy cảm, ưu tiên độ phủ hơn lấy mẫu ngẫu nhiên.

| Vai trò | Trách nhiệm trong cuộc audit |
|---|---|
| Business sponsor | Xác nhận nhu cầu truy cập và trạng thái hợp đồng |
| Vendor/partner manager | Xác minh liên hệ đối tác, thời hạn và quy trình thông báo biến động |
| IAM Operations | Cung cấp inventory, provisioning/deprovisioning records, reconciliation |
| Application owner | Xác nhận quyền và kiểm thử tại ứng dụng đích |
| Security / IAM Governance | Đặt policy, đánh giá SoD, đặc quyền và ngoại lệ |
| Internal auditor | Đánh giá bằng chứng độc lập, ghi finding và theo dõi remediation |
| Third-party IdP administrator | Cung cấp bằng chứng federation/nguồn theo thỏa thuận |

Một người có thể kiêm nhiều vai trò trong tổ chức nhỏ, nhưng **quyền tự phê duyệt** và xung đột lợi ích phải được xử lý theo chính sách. Không xem việc vendor tự xác nhận “tất cả account hợp lệ” là bằng chứng duy nhất.

Các câu hỏi audit cốt lõi:

1. Danh tính bên ngoài được tạo từ nguồn nào, có người bảo trợ và thời hạn hợp lệ không?
2. Ai phê duyệt quyền, chính sách nào được áp dụng và có ngoại lệ nào?
3. Danh tính có thể truy cập dữ liệu hoặc thao tác gì tại mỗi ứng dụng?
4. Khi sponsor, vai trò hoặc hợp đồng thay đổi, quyền nào đã được cập nhật?
5. Khi chấm dứt, thời gian từ hiệu lực đến lúc **thực sự không còn quyền** là bao lâu?
6. Có tài khoản máy, credential, token hoặc local grant ngoài phạm vi kiểm soát không?
7. Có đủ dấu vết để chứng minh kết luận và phân công xử lý các sai lệch không?

## 4. Kiến trúc luồng dữ liệu cần kiểm toán

~~~mermaid
flowchart TD
    V[Vendor / Partner identity source] --> F[External IdP / Federation]
    B[Business sponsor / Contract system] --> I[IAM Governance / Lifecycle]
    F --> I
    I --> P[RBAC / ABAC / SoD policy]
    P --> A[Approval & expiry]
    A --> D[Local IdP / Directory]
    D --> S[SSO session and claims]
    A --> C[SCIM / API provisioning]
    C --> T[Application / SaaS / Repository]
    S --> T
    T --> R[Readback effective access]
    R --> L[Audit / Reconciliation]
    I --> L
    L --> X{Approved desired state?}
    X -->|Có| Q[Evidence and certification]
    X -->|Không| E[Finding / Remediation / Retest]
~~~

Sơ đồ có thể thay đổi theo mô hình thực tế: một số hệ thống dùng **B2B federation** và không cần tài khoản local, một số ứng dụng vẫn duy trì “shadow account”, còn hệ thống cũ chỉ hỗ trợ quy trình thủ công. Cuộc kiểm toán phải nêu rõ các đường truy cập **ngoài luồng SSO tập trung**.

Ba khái niệm cần tách:

- **Desired state:** danh tính và entitlement hợp lệ theo hợp đồng, sponsor, policy và approval hiện hành.
- **Reported state:** kết quả workflow IAM/SCIM/connector tự báo đã xử lý.
- **Observed state:** tài khoản, group, direct grant, token/session và khả năng truy cập thực tế tại target.

Chỉ báo cáo PASS nếu observed state hội tụ về desired state theo deadline đã duyệt.

## 5. Kiểm toán dữ liệu nguồn, định danh và hợp đồng

Các trường nên được kiểm kê:

~~~yaml
externalIdentity:
  immutableId: ext-person-041
  organizationId: vendor-acme
  identityType: CONTRACTOR
  sponsorId: internal-sponsor-017
  source: partner-registry
  verifiedAt: "2026-12-01T03:00:00Z"
  contractStartAt: "2026-12-01T00:00:00Z"
  contractEndAt: "2027-02-28T17:00:00Z"
  status: ACTIVE
  approvedAccess:
    - project.alpha.read
  allowedTenant: sandbox-partner
~~~

Đây là dữ liệu giả và schema minh họa. Trong hệ thống thật, phải xác minh `immutableId` hoặc khóa liên kết ổn định thay vì dùng duy nhất email. Một nhân viên đối tác đổi email, chuyển công ty hoặc được tái thuê không được tự động kế thừa quyền của một định danh khác.

Checklist nguồn:

1. Mỗi danh tính có owner/sponsor chịu trách nhiệm còn hoạt động?
2. Hợp đồng, project và `contractEndAt` có nguồn và ngày cập nhật đáng tin cậy?
3. Có quy trình thông báo từ đối tác khi người dùng nghỉ hoặc đổi vai trò?
4. Tài khoản hết hạn đã bị suspend hoặc deprovision đúng SLA?
5. Trạng thái vendor và quyền ứng dụng có khớp không?
6. Có ngoại lệ được phê duyệt với lý do, phạm vi, người duyệt và expiry?
7. Có bản ghi trùng, orphan hoặc account không xác định được chủ thể thực không?

Đối với tài khoản không có sponsor, nên phân loại **UNKNOWN/ORPHANED** và escalation, không tự coi là hợp lệ chỉ vì đăng nhập gần đây.

## 6. Kiểm toán Joiner–Mover–Leaver cho bên thứ ba

### Joiner: xác minh và cấp quyền

Khi đối tác yêu cầu đưa người mới vào dự án, audit cần dấu vết về **định danh đã xác minh**, sponsor, hợp đồng còn hạn, phê duyệt quyền, cấp account và readback. Kiểm tra rằng người dùng chưa đủ điều kiện hoặc trước `effectiveAt` không có quyền sử dụng sớm. Đặc quyền admin, quyền dữ liệu nhạy cảm hoặc truy cập nhiều tenant phải có phê duyệt độc lập theo policy.

### Mover: đổi project, sponsor hoặc phạm vi

Mover của vendor có thể không hiện trong HRIS, nên nguồn đối tác/contract registry cần đẩy event. Ví dụ nhà thầu chuyển từ `project-alpha` sang `project-beta`: quyền beta được cấp nếu duyệt, quyền alpha phải được gỡ nếu không còn cần. Kiểm tra quyền kế thừa qua nhóm lồng nhau, role local và ACL chia sẻ. Nếu cần bàn giao tạm thời, ngoại lệ phải có thời hạn và người chịu trách nhiệm.

### Leaver: hết hợp đồng hoặc chấm dứt khẩn cấp

Đến `contractEndAt` hoặc khi được thông báo chấm dứt hợp lệ, phải chặn truy cập tương tác và thu hồi entitlement ở các đích. Kiểm cả SSO, session, access/refresh token, local account, PAT, API key và VPN theo phạm vi. Không suy rằng partner IdP disable user tức thời làm mọi session tại ứng dụng hết hiệu lực: JWT tự chứa vẫn có thể được chấp nhận tới `exp` nếu resource server chỉ kiểm chữ ký. Cần đối chiếu deadline, cơ chế revocation và kết quả API.

### Tái ký hợp đồng hoặc quay lại làm việc

Không tự mở mọi quyền lịch sử khi contractor quay lại. Yêu cầu xác minh lại status, sponsor, ngày hiệu lực và entitlement mới theo phê duyệt hiện hành. Có thể liên kết hồ sơ cũ bằng định danh ổn định nếu policy cho phép, nhưng **quyền cũ không tự động sống lại**.

## 7. Kiểm toán federation, SSO và xác thực

Với SAML/OIDC B2B, xem xét:

| Điểm kiểm soát | Nội dung cần kiểm toán |
|---|---|
| Trust relationship | IdP/issuer, audience, redirect/ACS, certificates và key trust còn hợp lệ |
| Subject mapping | NameID/sub trỏ đúng external identity, không gộp người theo email |
| Authentication assurance | MFA hoặc assurance claim phù hợp với mức độ nhạy cảm |
| Conditional access | Chính sách thiết bị, vị trí, rủi ro nếu có, không bị bypass |
| Session lifecycle | Timeout, refresh, logout và revoke theo chính sách |
| Disabled identity | Người hết hạn không tạo được phiên mới, kể cả qua đường local |
| Failure mode | Khi đối tác IdP hoặc PIP lỗi, ứng dụng xử lý an toàn theo policy |

**Kiểm toán hoạt động** nên kiểm cả assertion/token hợp lệ, token hết hạn, sai issuer/audience và session phát hành trước sự kiện chấm dứt. Nhiều ứng dụng tin vào IdP đối tác để xác thực nhưng tự giữ quyền của user; cần đo riêng AuthN và AuthZ.

Trong trường hợp partner dùng cùng một tài khoản chung cho nhiều nhân viên, tổ chức nhận dịch vụ thường không thể quy trách nhiệm từng người. Cần ghi finding, kiểm tra điều khoản quản lý danh tính và phương án cấp account cá nhân hoặc xác thực workload riêng.

## 8. Kiểm toán RBAC/ABAC, tenant boundary và SoD

Kiểm tra quyền theo bộ bốn **subject–action–resource–context**. Ví dụ vendor chỉ được xem dữ liệu dự án Alpha nhưng không được xuất toàn bộ dữ liệu khách hàng hoặc truy cập tenant của khách hàng khác.

| Subject | Action | Resource | Kỳ vọng |
|---|---|---|---|
| Vendor Alpha active | `document.read` | Project Alpha | ALLOW |
| Vendor Alpha active | `document.read` | Project Beta | DENY |
| Vendor Alpha active | `customer.export.all` | CRM | DENY |
| Vendor Alpha expired | `document.read` | Project Alpha | DENY |
| Partner support đã duyệt | `ticket.read` | Ticket được gán | ALLOW |
| Vendor không có phê duyệt admin | `iam.role.admin` | IAM console | DENY |

**RBAC** cho biết role nào chứa quyền gì; **ABAC** giới hạn theo organization, project, tenant, contract status, phân loại dữ liệu hoặc môi trường. Nếu thuộc tính bắt buộc bị thiếu hoặc stale, phải xác định failure behavior theo chính sách; tránh fail-open với tài nguyên nhạy cảm.

Kiểm tra SoD khi một nhà thầu có thể vừa tạo vừa phê duyệt giao dịch mà quy trình cấm. Quyền đặc biệt phải có approval độc lập, lý do, expiry và audit. Đừng chỉ kiểm group membership: quyền qua nested group, direct ACL hoặc role cục bộ có thể tạo entitlement hiệu lực ngoài ý muốn.

## 9. Kiểm toán provisioning SCIM và đồng bộ ứng dụng

SCIM 2.0 thường hỗ trợ thao tác tạo user, cập nhật thuộc tính, membership và `active=false`; nhưng các ứng dụng có thể xử lý session và direct role khác nhau. Với mỗi thay đổi phải đối chiếu **request, response, readback và authorization thực tế**.

Ví dụ deactivation minh họa:

~~~http
PATCH /scim/v2/Users/vendor-user-041
Content-Type: application/scim+json

{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations": [
    {"op": "replace", "path": "active", "value": false}
  ]
}
~~~

Các tình huống kiểm toán cần chú ý:

1. Trùng `externalId` hoặc email: không tạo hai identity hay thu hồi nhầm.
2. Timeout sau khi ứng dụng đã xử lý: lookup trước retry, không tạo grant/account trùng.
3. `429` hoặc `5xx`: retry/backoff có giới hạn; quá SLA phải alert.
4. Event đến ngoài thứ tự: Mover cũ không được khôi phục quyền sau Leaver mới hơn.
5. `404` khi revoke: xác minh mapping và trạng thái thực, không tự coi là đã thu hồi.
6. Connector chỉ cập nhật IdP group nhưng bỏ sót role cục bộ: reconciliation phải phát hiện.
7. Một target thất bại: hiển thị partial failure và remediation có owner.

Sự kiện `active=false` cần được readback, nhưng vẫn phải thử đăng nhập và gọi API khi kết luận quyền đã hết hiệu lực.

## 10. Kiểm toán service account và tích hợp do bên thứ ba quản lý

Vendor có thể vận hành bot, agent tích hợp dữ liệu, webhook hoặc service principal. Chúng không đăng nhập bằng MFA tương tác như nhân viên, mà thường dùng chứng chỉ, workload federation, OAuth client credentials hoặc API key.

Kiểm tra:

- Mỗi machine identity có **technical owner**, **business sponsor**, hệ thống tiêu thụ và mục đích đã duyệt.
- Scope token/API nhỏ nhất, tenant/project bị giới hạn và không dùng một khóa quản trị dùng chung cho nhiều tích hợp.
- Credential lưu trong secret manager; có expiry/rotation theo chính sách, audit truy cập và thu hồi.
- Khi hợp đồng chấm dứt, integration bị ngắt hoặc bàn giao có kiểm soát; khóa cũ không tiếp tục được sử dụng.
- Nếu sponsor chuyển vai trò hoặc Leaver, quyền quản trị secret của người cũ bị gỡ nhưng bot hợp lệ không bị xóa tùy tiện.
- OAuth consent, app grants và delegated permissions được kiểm kê: thu hồi user account không mặc nhiên thu hồi mọi application grant.

Đối với credential đã từng được vendor biết, việc gỡ quyền truy cập vault không làm khóa cũ vô hiệu; audit phải tìm bằng chứng rotation/revocation và thử credential cũ trong môi trường được phép.

## 11. Thiết kế mẫu bằng chứng audit

Một bản ghi nên phân biệt **yêu cầu**, **quyết định** và **kết quả hiệu lực**:

~~~json
{
  "auditId": "tp-audit-2026-001",
  "correlationId": "corr-offboard-041",
  "sourceEventId": "contract-end-041-v7",
  "externalIdentityId": "ext-person-041",
  "organizationId": "vendor-acme",
  "sponsorId": "internal-sponsor-017",
  "target": "partner-document-portal",
  "action": "ENTITLEMENT_REVOKE",
  "entitlement": "project.alpha.read",
  "policyVersion": "third-party-policy-v3",
  "decision": "REVOKE",
  "executionStatus": "SUCCEEDED",
  "observedAccess": "DENY",
  "observedAt": "2027-02-28T17:00:12Z"
}
~~~

Mẫu chỉ minh họa. Bằng chứng nên gồm quyết định phê duyệt, source status, ticket/change ID, IdP/SCIM logs, nhóm và role ở đích, thử API, timestamp, SLA, remediation và kết quả xác minh độc lập. Giữ correlation ID xuyên qua nhiều connector để xác định một sai lệch xảy ra ở nguồn, policy, provisioning hay enforcement.

Không lưu password, OTP, refresh/access token, private key hoặc nội dung dữ liệu nhạy cảm vào audit trail. Quyền truy cập bằng chứng cần được phân tách; thời gian lưu và dữ liệu cá nhân phải tuân theo chính sách và nghĩa vụ áp dụng.

## 12. Kiểm toán access review và phát hiện quyền tồn dư

Chiến dịch access review cho vendor cần kiểm kê danh tính và entitlement từ tất cả các hệ thống đích, kể cả account local, nhóm lồng nhau, API key và service principal. Reviewer phải là sponsor/application owner có thẩm quyền, không mặc định là người đang sử dụng account.

~~~text
approved = policy.calculate(currentContractState, roles, exceptions)
observed = inventory.effectiveGrants(idp, applications, localACLs)

unexpected = observed - approved
missing = approved.required - observed
orphaned = actualExternalAccounts - validSponsoredExternalAccounts
~~~

Các quyết định thường là `KEEP`, `REVOKE`, `ESCALATE`. Đối với `KEEP`, phải kiểm hợp đồng và sponsor vẫn hợp lệ. Đối với `REVOKE`, cần đối soát quyền thực tế bị chặn trong SLA, không chỉ ticket đóng. Với `ESCALATE`, phải có owner, lý do và deadline.

Không tuyên bố “100% reviewed” nếu connector không trả dữ liệu đủ; đánh dấu coverage `UNKNOWN/INCOMPLETE` và mở finding. Quyền không sử dụng gần đây là tín hiệu cần xem xét nhưng không phải bằng chứng duy nhất cho phép tự động gỡ.

## 13. Ma trận test case third-party audit

| ID | Trường hợp | Kỳ vọng |
|---|---|---|
| TP01 | Contractor mới đã xác minh và có sponsor | Quyền chỉ được cấp theo approval và ngày hiệu lực |
| TP02 | Contractor thiếu sponsor | Không cấp đặc quyền, tạo yêu cầu xác minh |
| TP03 | Vendor đổi email | Không nhầm identity hoặc cấp quyền trùng |
| TP04 | Partner đổi project | Quyền cũ gỡ, quyền mới đúng policy |
| TP05 | Contract hết hạn | Không còn quyền tương tác ngoài SLA |
| TP06 | Partner IdP disable user | App session/token cũ bị kiểm theo policy |
| TP07 | Role local còn sau SCIM deactivate | Reconciliation phát hiện residual access |
| TP08 | Nhóm lồng nhau còn quyền | Effective entitlement không bị bỏ sót |
| TP09 | Vendor xem tenant khác bằng ID tài nguyên | DENY, không lộ dữ liệu |
| TP10 | Quyền admin không có approval | DENY và audit |
| TP11 | Sponsor đã Leaver | Phát hiện owner không hợp lệ, reassign/escalate |
| TP12 | SCIM timeout, retry | Không duplicate, readback đúng |
| TP13 | Event Mover cũ đến sau Leaver | Không hồi sinh quyền |
| TP14 | Service account thiếu owner hoặc secret quá hạn | Có finding và remediation |
| TP15 | OAuth app grant vẫn sống sau hợp đồng | Phát hiện và xử lý đúng phạm vi |
| TP16 | Audit log không đủ hoặc chứa token | Không đủ điều kiện PASS; sửa pipeline |

Mỗi testcase ghi `caseId`, nguồn chính sách, identity/target, expected, observed, thời điểm hiệu lực, deadline, evidence, status và remediation. Các kết quả ALLOW/DENY phải được xác minh qua API/PEP thật trong sandbox nếu có thể; kiểm tra dữ liệu trong IAM đơn thuần là chưa đủ.

## 14. Quy trình thực hiện một cuộc third-party audit

### Bước 1 — Chọn scope và policy baseline

Xác định danh sách vendor/partner, ứng dụng, loại quyền, thời kỳ audit, SLA và trách nhiệm. Liệt kê các ngoại lệ, hợp đồng và mô hình federation. Với quyền nhạy cảm, kiểm toàn bộ account thuộc phạm vi khi khả thi.

### Bước 2 — Thu thập inventory và kiểm tra chất lượng

Lấy identity từ registry/HRIS phù hợp, sponsor, IdP, SCIM, app, nhóm, ACL, service account, token/app grants. Kiểm tính đủ của pagination, độ mới dữ liệu, mapping ID và account không có chủ thể xác minh. Ghi các nguồn bị thiếu thành finding thay vì coi là không có quyền.

### Bước 3 — Kiểm thử thiết kế kiểm soát

Xác định policy cấp quyền, xác minh MFA/federation, manager/sponsor approval, expiry, SoD, khả năng thu hồi và trách nhiệm bảo mật. Đối chiếu tài liệu hợp đồng/quy trình với logic thực tế mà tổ chức đang áp dụng.

### Bước 4 — Kiểm thử vận hành

Chọn mẫu từ Joiner, Mover, Leaver, privileged, expired và machine identity; kiểm evidence phê duyệt, source event, thời điểm đồng bộ, quyền tại đích và session. Tạo negative test trong sandbox như truy cập tenant khác hoặc dùng credential đã revoke.

### Bước 5 — Phân loại sai lệch

Đánh giá tác động, phạm vi quyền, dữ liệu liên quan và số ngày quyền tồn dư. Gán mức ưu tiên theo chính sách; với quyền nguy hiểm đang hiệu lực, chuyển containment qua quy trình có thẩm quyền. Không áp dụng thay đổi production ngoài phê duyệt.

### Bước 6 — Remediation và kiểm chứng độc lập

Lập ticket có owner, hành động, deadline, bằng chứng readback và thử API. Kiểm rằng các chỉnh sửa không gây gián đoạn quyền hợp lệ của tài khoản khác. Đóng finding khi đã có chứng cứ, không chỉ khi owner báo “đã xử lý”.

## 15. Mẫu báo cáo third-party audit

~~~markdown
# Third-party IAM Audit Report

Audit ID / period:
Scope: vendors, applications, environments:
Policy version / source of truth:
Audit owner / application owners:
Sampling method and scope exclusions:

| Finding ID | Identity / Vendor | Target | Expected | Observed | Risk | Owner | Due | Evidence |
|---|---|---|---|---|---|---|---|---|
| TP-F01 | ext-person-041 / vendor-acme | CRM | Inactive | Active | High | IAM Ops | ... | ... |
| TP-F02 | test-bot-12 / partner | CI/CD | Current owner | Missing | Medium | App Owner | ... | ... |

Coverage gaps and assumptions:
Joiner–Mover–Leaver results:
Federation/SSO and token findings:
Direct grants and service principal findings:
Remediation verification:
Residual risk accepted by:
Final audit conclusion:
~~~

Một báo cáo tốt phải phân biệt **design deficiency** (chính sách hoặc kiến trúc thiếu kiểm soát) với **operating deficiency** (đã có kiểm soát nhưng không chạy đúng), và nêu nguồn chứng cứ của từng kết luận. Nếu không đủ dữ liệu, đánh dấu giới hạn audit thay vì khẳng định hệ thống an toàn.

## 16. Chỉ số theo dõi sau audit

| Chỉ số | Diễn giải | Lưu ý |
|---|---|---|
| External identity coverage | Tài khoản vendor được liên kết với sponsor/hợp đồng hợp lệ | Không đo chỉ từ IdP nếu còn account local |
| Expired access count | Số quyền hết hạn vẫn còn hiệu lực | Phân loại đặc quyền và dữ liệu nhạy cảm |
| Third-party revocation latency | Thời gian từ hết hiệu lực tới lúc PEP chặn | Đo theo target và SLA |
| Review completion | Quyền vendor đã được xác nhận bởi reviewer hợp lệ | Không thay thế verified revoke |
| Orphan machine identities | Service principals không có owner | Gắn remediation và due date |
| Audit evidence completeness | Tỷ lệ thay đổi có đủ approval, action và readback | Dữ liệu thiếu phải lộ rõ |
| Residual access findings | Quyền không hợp lệ còn dùng được | Không đóng chỉ vì SCIM trả 200 |

Đo lường nên được phân nhóm theo vendor, độ nhạy cảm tài nguyên và ứng dụng. Không dùng person ID/email làm nhãn metric có độ phân biệt cao; để điều tra từng người dùng audit event/search có kiểm soát.

## 17. Bài thực hành

Giả lập một nhà thầu `ext-person-041` từ `vendor-acme` được phép đọc tài liệu Project Alpha đến cuối hợp đồng. Sau đó nhà thầu chuyển sang Project Beta và hết hợp đồng; hệ thống gồm partner IdP, local IdP, ứng dụng tài liệu qua SCIM, một CRM có role local và service principal tích hợp CI/CD.

1. Tạo inventory các danh tính và entitlement, liên kết với sponsor, hợp đồng và ngày hết hạn.
2. Thiết kế test cho Joiner, Mover, Leaver, bao gồm quyền direct grant và nested groups.
3. Kiểm federation, SSO/MFA, session và token khi partner IdP disable người dùng.
4. Gây một SCIM timeout sau khi ứng dụng đã xử lý, rồi kiểm idempotency và readback.
5. Gắn một role CRM local còn tồn dư, chứng minh reconciliation phát hiện và API kiểm tra DENY sau remediation.
6. Giả lập sponsor nghỉ việc và service account thiếu owner; ghi finding với owner xử lý.
7. Thử truy cập tài nguyên thuộc tenant khác và quyền quản trị không có approval; phải bị DENY.
8. Tạo báo cáo có ít nhất ba finding, bằng chứng, severity, remediation, deadline và kiểm tra sau sửa.

**Kết luận:** Kiểm toán danh tính bên thứ ba chỉ đáng tin khi tổ chức biết **ai đang truy cập, ai bảo trợ, quyền có căn cứ và thời hạn gì, hệ thống đích thực thi ra sao và quyền được thu hồi thật sự khi quan hệ kết thúc**. Đây là cách áp dụng JML, IdP/SSO, SCIM, RBAC/ABAC, quản lý tài khoản dịch vụ và kiểm toán để hạn chế quyền truy cập tồn dư qua ranh giới tổ chức.
