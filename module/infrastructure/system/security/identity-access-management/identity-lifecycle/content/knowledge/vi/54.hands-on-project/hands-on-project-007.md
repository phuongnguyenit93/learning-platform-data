# Dự án thực hành: Tạo access request trong IAM

> **Chương:** Dự án thực hành  
> **Đề bài:** Tạo access request  
> **Phạm vi:** Thiết kế và triển khai quy trình **yêu cầu cấp quyền truy cập (access request)** cho người dùng hoặc workload trong Identity and Access Management (IAM), gắn với **Joiner–Mover–Leaver (JML)**. Dự án nối yêu cầu, xác minh danh tính, phê duyệt, RBAC/ABAC, IdP/SSO, SCIM/API, rà soát, hết hạn và thu hồi quyền, kiểm toán, kiểm soát quyền truy cập tồn dư.

## 1. Mục tiêu và tư duy của dự án

Một **access request** là hồ sơ yêu cầu được cấp, điều chỉnh hoặc thu hồi khả năng thực hiện một hành động trên tài nguyên. Nó **không phải** quyền đã được cấp: giữa thao tác gửi đơn và trạng thái truy cập thực tế còn có xác minh danh tính, đánh giá chính sách, kiểm tra xung đột, phê duyệt, cấp phát và đọc lại quyền.

Người học sẽ tạo một dịch vụ lab tiếp nhận yêu cầu cấp quyền, tính ai có thẩm quyền phê duyệt, điều phối việc cấp quyền có thời hạn và chứng minh trạng thái cuối. Sau đó kiểm tra hệ thống vẫn an toàn khi người dùng **chuyển vai trò**, **rời công ty**, khi yêu cầu trùng lặp, khi người phê duyệt không đủ thẩm quyền hoặc khi connector tới ứng dụng thất bại.

### 1.1. Năng lực cần chứng minh

1. **Mô hình hóa yêu cầu:** lưu subjectId ổn định, resource, entitlement, mục đích, thời gian, nguồn yêu cầu, owner, trạng thái và bằng chứng.
2. **Xác minh trước phê duyệt:** chỉ người/thiết bị đã xác thực qua kênh tin cậy mới gửi được request; không tin subjectId và managerId do client khai mà không kiểm tra.
3. **Áp dụng policy:** role catalog theo RBAC, điều kiện ABAC, đặc quyền tối thiểu, kiểm tra SoD và hạn quyền.
4. **Tách quyết định và thực thi:** chỉ một quyết định hợp lệ mới cho phép provisioning; API thành công chưa có nghĩa quyền hiệu lực đã đúng.
5. **Thiết kế phê duyệt:** có chủ dữ liệu, chủ hệ thống và approver độc lập cho quyền nhạy cảm; chống tự phê duyệt.
6. **Tích hợp:** phân biệt IdP, SSO và SCIM/API; ánh xạ tài khoản ứng dụng và kiểm tra quyền thực tế tại hệ đích.
7. **Vòng đời:** quyền tạm thời hết hạn phải thu hồi; Mover có thể làm quyền trở nên không hợp lệ; Leaver không được tiếp tục cấp quyền từ request còn chờ.
8. **Độ tin cậy:** yêu cầu trùng không cấp quyền hai lần; lỗi connector để lại trạng thái chưa hoàn tất rõ ràng và có owner.
9. **Kiểm toán:** truy vết yêu cầu, phê duyệt, policy version, lệnh cấp phát, kết quả và thời gian xác minh.

### 1.2. Sản phẩm cần bàn giao

| Sản phẩm | Yêu cầu tối thiểu | Bằng chứng |
| --- | --- | --- |
| Mô hình access request | Schema + trạng thái + quy tắc chuyển trạng thái | Ví dụ JSON và bảng chuyển trạng thái |
| Entitlement catalog | Role, hành động, tài nguyên, mức nhạy cảm, owner, expiry | Ma trận quyền và policy có phiên bản |
| Approval workflow | Manager/app owner, SoD, chống tự phê duyệt | Hồ sơ approver, quyết định, lý do |
| Provisioning workflow | IdP group hoặc SCIM/API/mock adapter có readback | Ảnh chụp trạng thái hoặc log thử nghiệm |
| Lifecycle hooks | Joiner, Mover, Leaver, quyền tạm thời hết hạn | Kịch bản trạng thái trước/sau |
| Mã mẫu | Một chương trình Java 17 mô phỏng end-to-end | Kết quả chạy được từ dữ liệu giả |
| Bộ kiểm thử | Tình huống hợp lệ, bị từ chối, đồng bộ lỗi và quyền tồn dư | Expected/Actual, PASS/FAIL, evidence |
| Runbook và kiểm toán | Cách khắc phục lỗi, ngoại lệ, chủ trách nhiệm | Audit trail + mẫu báo cáo |

**Giới hạn an toàn:** dùng dữ liệu và account **giả lập** trong môi trường được phép. Không thử cấp đặc quyền production, khóa tài khoản người khác hoặc sử dụng token thật. Dự án này tập trung vào quy trình IAM, không hướng dẫn né kiểm soát của hệ thống.

## 2. Đề bài nghiệp vụ DemoCo

Doanh nghiệp giả lập DemoCo dùng một **HRIS** làm nguồn trạng thái nhân viên, một **IdP** hỗ trợ SSO, một ứng dụng **CRM** quản lý ticket, một **Finance Portal** cho báo cáo và một kho mã phục vụ CI/CD. Có cả nhân viên, nhà thầu có sponsor và danh tính máy.

**Nhân vật:** An, mã **EMP-LAB-017**, được HR xác nhận là nhân viên Support đang hoạt động. An cần tạm thời **xuất báo cáo CRM** để làm một nhiệm vụ được giao. Đây là quyền nhạy cảm hơn quyền đọc/sửa ticket bình thường và cần chủ dữ liệu phê duyệt.

Các role/entitlement giả định:

| Entitlement | Tài nguyên/hành động | Ai có thể yêu cầu | Người quyết định | Giới hạn |
| --- | --- | --- | --- | --- |
| **CRM-Ticket-Reader** | tickets:read trong team | Nhân viên Support hợp lệ | Có thể theo role chuẩn | Chỉ team/tenant được giao |
| **CRM-Ticket-Editor** | tickets:update trong team | Nhân viên Support hợp lệ | Theo role catalog | Không xóa hoặc export dữ liệu |
| **CRM-Data-Export** | customers:export | Người được giao nhiệm vụ | **Chủ dữ liệu CRM** | Lý do rõ, scope hẹp, thời hạn |
| **Finance-Report-Viewer** | finance:reports:read | Nhân viên Finance | Quản lý/chủ hệ thống tùy policy | Chỉ tenant/phạm vi liên quan |
| **Finance-Payment-Approver** | payments:approve | Người được ủy quyền | Chủ hệ thống và kiểm soát SoD | Không tự duyệt giao dịch mình tạo |
| **Deploy-Production** | deploy:production | Workload/đội vận hành phù hợp | Chủ nền tảng + kiểm soát rủi ro | JIT/thời hạn, scope dịch vụ |

**Yêu cầu chính của bài lab:** An tự yêu cầu quyền **CRM-Data-Export** trong bảy ngày, chọn phạm vi dự án thử nghiệm và nêu mục đích nghiệp vụ. Hệ thống phải xác minh An còn active và thuộc phạm vi dự án, lấy danh tính người phê duyệt từ cấu hình owner được tin cậy, chống tự phê duyệt, kiểm tra SoD và chỉ sau khi được duyệt mới gọi adapter cấp quyền.

### 2.1. Ba biến thể bắt buộc

1. **Joiner:** An mới gia nhập, chưa đến ngày bắt đầu. Request có thể được ghi nhận theo quy trình nhưng không được mở quyền dữ liệu trước thời điểm chính sách cho phép.
2. **Mover:** An chuyển từ Support sang Finance trong lúc request còn chờ hoặc quyền export đang có hiệu lực. Policy phải đánh giá lại căn cứ; không tích lũy quyền cũ.
3. **Leaver:** HR phát sự kiện nghỉ việc. Request đang chờ không được cấp quyền về sau; quyền đã cấp phải đi vào luồng thu hồi và được xác minh tại hệ đích.

### 2.2. Tiêu chí hoàn tất nghiệp vụ

Yêu cầu **APPROVED** chỉ có nghĩa quyết định phê duyệt đã hợp lệ. Yêu cầu **FULFILLED/VERIFIED** chỉ khi entitlement thực tế khớp chính sách và giới hạn đã duyệt. Hết hạn hoặc mất căn cứ truy cập phải chuyển tới thu hồi; trạng thái **REVOKED** chỉ được ghi khi đã kiểm chứng ở đích. Nếu connector chưa xác minh xong, phải giữ **PENDING_VERIFICATION/PARTIAL/FAILED** với người xử lý.

Đừng đánh đồng **quy trình tạo yêu cầu** với **nút nhấn cấp quyền**. Một người dùng có thể được xác thực thành công bởi SSO nhưng không có quyền yêu cầu bất kỳ entitlement nào; người có quyền tạo request cũng không tự động có quyền phê duyệt hoặc provision.

## 3. Kiến trúc dự án

~~~mermaid
flowchart TD
    USER["Người dùng / Manager / Sponsor"] --> PORTAL["Access Request Portal<br/>Authentication + Input Validation"]
    HR["HRIS / Contractor Registry"] --> POLICY["Policy + Identity State"]
    CATALOG["Entitlement Catalog<br/>Owner / Risk / TTL / SoD"] --> POLICY
    PORTAL --> REQUEST["Access Request Service<br/>Request ID + State"]
    REQUEST --> POLICY
    POLICY -->|Từ chối| REJECT["REJECTED / Audit"]
    POLICY -->|Cần duyệt| APPROVAL["Approval Engine<br/>Owner + SoD + Delegation"]
    APPROVAL -->|Approved| PROVISION["Provisioning Orchestrator"]
    APPROVAL -->|Rejected| REJECT
    POLICY -->|Quyền chuẩn hợp lệ| PROVISION
    PROVISION --> IDP["IdP Groups / User State"]
    PROVISION --> SCIM["SCIM / App APIs / Manual Tasks"]
    IDP --> RECON["Readback / Reconciliation"]
    SCIM --> RECON
    RECON -->|Khớp| FULFILLED["FULFILLED + Audit"]
    RECON -->|Chưa khớp| EX["PENDING / FAILED + Owner"]
    FULFILLED --> EXPIRY["TTL / Mover / Leaver / Access Review"]
    EXPIRY --> REVOKE["Revoke + Readback"]
    REQUEST --> AUDIT["Append-only Audit Events"]
    APPROVAL --> AUDIT
    RECON --> AUDIT
    REVOKE --> AUDIT
~~~

**Không phải mọi hệ thống cần tách thành từng microservice.** Sơ đồ nhấn mạnh trách nhiệm logic: request không tự cấp quyền, approval không phải readback, và thu hồi có lifecycle riêng. Có thể triển khai tất cả trong một chương trình lab nhưng vẫn tách interface và trạng thái để dễ kiểm thử.

### 3.1. Các vai trò và ranh giới tin cậy

| Vai trò | Được làm gì? | Không được mặc nhiên làm gì? |
| --- | --- | --- |
| Requester | Tạo, xem yêu cầu thuộc phạm vi của mình; hủy trước khi xử lý nếu policy cho phép | Tự phê duyệt hoặc sửa trạng thái provisioning |
| Manager/Sponsor | Xác nhận nhu cầu công việc/hợp đồng trong phạm vi | Duyệt quyền dữ liệu nhạy cảm nếu không phải owner có thẩm quyền |
| Resource Owner | Quyết định quyền truy cập tài nguyên và giới hạn scope | Bỏ qua kiểm tra tình trạng nhân sự/SoD |
| IAM Policy Engine | Kiểm tra policy, phiên bản, SoD, trạng thái | Tin mọi thuộc tính client gửi là sự thật |
| IAM Orchestrator | Gọi adapter sau quyết định hợp lệ, kiểm chứng target | Tự cấp thêm quyền nằm ngoài quyết định |
| App Owner | Quản lý connector/role mapping, hỗ trợ sự cố | Thay đổi quyền mà không có audit hoặc quy trình ngoại lệ |
| Auditor | Xem bằng chứng, đánh giá tuân thủ và sai lệch | Chỉnh log hoặc tự dùng quyền quản trị ngoài thẩm quyền |

Danh tính **người gửi yêu cầu** đến từ session đã xác thực. Danh tính **người hưởng quyền** có thể là requester hoặc người khác khi nghiệp vụ cho phép (ví dụ manager yêu cầu cho thành viên), nhưng phải được xác thực ủy quyền. **Approver** phải lấy từ cấu hình owner/đơn vị và chính sách, không lấy giá trị mà requester tự gửi để có thể tự phê duyệt.

## 4. Đặc tả access request

### 4.1. JSON mẫu cho yêu cầu cấp quyền có hạn

~~~json
{
  "requestId": "AR-LAB-2026-0041",
  "operation": "GRANT",
  "requesterId": "EMP-LAB-017",
  "subjectId": "EMP-LAB-017",
  "targetSystem": "crm-lab",
  "entitlementId": "CRM-Data-Export",
  "resourceScope": {
    "tenantId": "TENANT-LAB-01",
    "projectId": "PROJECT-LAB-07"
  },
  "businessJustification": "Xuất báo cáo dự án tuần",
  "requestedAt": "2026-11-23T09:00:00+07:00",
  "effectiveAt": "2026-11-24T09:00:00+07:00",
  "expiresAt": "2026-12-01T09:00:00+07:00",
  "identitySourceVersion": 16,
  "policyVersion": "iam-lab-v3"
}
~~~

Đây là **schema nghiệp vụ minh họa**, không phải chuẩn SCIM hay một payload chuẩn của IdP. Trong một API thật, server phải tự phát sinh **requestId, requesterId, requestedAt** và các trường audit đáng tin. Thông tin như **owner, approver, identitySourceVersion, policyVersion** do server tra nguồn đáng tin, không cho client tùy ý ghi để vượt kiểm soát.

### 4.2. Bộ trường và nguồn dữ liệu

| Trường | Nguồn tin cậy | Kiểm tra |
| --- | --- | --- |
| requestId / createdAt | Access Request Service | Duy nhất; hỗ trợ idempotency |
| requesterId | Authenticated principal | Có quyền tạo request cho subjectId mục tiêu |
| subjectId | HRIS/sponsor/workload registry | Tồn tại, trạng thái hợp lệ, ID ổn định |
| targetSystem / entitlementId | Entitlement catalog | Có owner, mapping và khả năng cấp/thu hồi |
| resourceScope | Catalog + thuộc tính tài nguyên | Thuộc tenant, project, team hợp lệ |
| businessJustification | Người yêu cầu | Có nội dung hữu ích; không thay thế phê duyệt |
| effectiveAt / expiresAt | Người yêu cầu + policy | Thời hạn hợp lý, không vượt TTL tối đa |
| approvers | Policy/owner registry | Không do requester tự chọn tùy ý |
| policyVersion | Chính sách IAM | Xác định quy tắc đã quyết định |
| decision / decidedAt | Approval Engine | Gắn danh tính approver đáng tin |
| targetAccountId | Provisioning connector | Mapping với account thực tế của app |
| verifiedAt / actualEntitlements | Target readback | Chứng minh quyền thực tế ở đích |

### 4.3. Quy tắc validation tối thiểu

- [ ] Requester đã xác thực; server lấy identity và quyền gửi yêu cầu từ session tin cậy.
- [ ] Subject tồn tại và còn quan hệ hợp lệ khi yêu cầu được quyết định/thực thi.
- [ ] Entitlement thuộc catalog đang hỗ trợ, có owner và policy version.
- [ ] Scope nằm trong phạm vi được yêu cầu và quyền requester được phép đề xuất.
- [ ] Mục đích rõ; không ghi secret/token trong trường justification.
- [ ] Thời hạn nằm trong policy; không chấp nhận expiresAt trước effectiveAt.
- [ ] Yêu cầu quyền đặc biệt được đánh dấu cần phê duyệt độc lập.
- [ ] Các cặp quyền xung đột SoD bị chặn hoặc chuyển xử lý ngoại lệ được ủy quyền.
- [ ] Không chấp nhận client tự cung cấp trường “approved=true” hoặc “status=FULFILLED”.
- [ ] Cùng idempotency key và cùng payload không tạo nhiều yêu cầu; cùng key với payload khác bị từ chối.

### 4.4. Các trạng thái và chuyển trạng thái

| Trạng thái | Ý nghĩa | Chuyển hợp lệ tiếp theo |
| --- | --- | --- |
| DRAFT | Yêu cầu chưa gửi, chưa có ý nghĩa quyết định | SUBMITTED, CANCELLED |
| SUBMITTED | Đã nhận; chờ validation/policy | PENDING_APPROVAL, APPROVED, REJECTED |
| PENDING_APPROVAL | Chờ người duyệt có thẩm quyền | APPROVED, REJECTED, CANCELLED, EXPIRED |
| APPROVED | Quyết định hợp lệ, chưa chắc đã cấp | PROVISIONING, CANCELLED, EXPIRED |
| PROVISIONING | Đang gọi adapter/SCIM/API | PENDING_VERIFICATION, FAILED |
| PENDING_VERIFICATION | Đã gửi lệnh, chờ actual readback | FULFILLED, FAILED |
| FULFILLED | Quyền đã có đúng scope, expiry và kiểm chứng | REVOKING, EXPIRED_PENDING_REVOKE |
| REVOKING | Đang thu hồi theo expiry/Mover/Leaver/review | REVOKED, FAILED |
| REVOKED | Thu hồi được xác minh ở target | Trạng thái kết thúc |
| REJECTED / CANCELLED | Không có quyền mới được cấp theo yêu cầu | Trạng thái kết thúc; vẫn ghi audit |
| FAILED | Connector/policy/readback không thể hoàn tất | Retry có kiểm soát hoặc escalation |
| EXPIRED_PENDING_REVOKE | Đã hết hạn nhưng chưa xác minh hết quyền | REVOKING hoặc xử lý ngoại lệ |

**Không cho phép:** requester tự đổi SUBMITTED → FULFILLED; request REJECTED chạy lại provisioning; request APPROVED tiếp tục provision sau khi HR đã ghi Leaver có hiệu lực; expiry được ghi EXPIRED nhưng quyền thực tế vẫn còn mà không có bước REVOKE. Workflow phải theo dõi hai khái niệm riêng: **decision status** và **fulfillment status** nếu một chuỗi enum duy nhất khó biểu diễn trạng thái thực tế.

### 4.5. Sơ đồ vòng đời request

~~~mermaid
stateDiagram-v2
    [*] --> SUBMITTED
    SUBMITTED --> PENDING_APPROVAL: policy cần duyệt
    SUBMITTED --> APPROVED: quyền chuẩn tự động theo policy
    SUBMITTED --> REJECTED: thiếu điều kiện / policy deny
    PENDING_APPROVAL --> APPROVED: duyệt hợp lệ
    PENDING_APPROVAL --> REJECTED: từ chối
    APPROVED --> PROVISIONING: đúng thời điểm + identity hợp lệ
    PROVISIONING --> PENDING_VERIFICATION: adapter đã xử lý
    PENDING_VERIFICATION --> FULFILLED: readback đúng mục tiêu
    PENDING_VERIFICATION --> FAILED: không khớp / timeout
    FAILED --> PENDING_VERIFICATION: retry an toàn
    FULFILLED --> REVOKING: expiry / Mover / Leaver
    REVOKING --> REVOKED: readback mất quyền
    REVOKING --> FAILED: chưa thể xác minh
    REJECTED --> [*]
    REVOKED --> [*]
~~~

Sơ đồ cố ý giản lược một số nhánh **CANCELLED**, **SCHEDULED** và trường hợp đã được phê duyệt nhưng chưa đến effectiveAt. Khi tự triển khai hãy thêm nhánh này, đồng thời xác định hành vi khi trạng thái HR thay đổi **sau approval nhưng trước provisioning**.

## 5. Entitlement catalog và chính sách quyết định

### 5.1. Mỗi quyền phải có một bản ghi có thể kiểm toán

~~~yaml
entitlementId: CRM-Data-Export
targetSystem: crm-lab
description: "Xuất báo cáo khách hàng thuộc dự án được giao"
actions: [customers:export]
scopeAttributes: [tenantId, projectId]
eligibleDepartments: [Support, Analytics]
riskTier: HIGH
owner: crm-data-owner
maxDurationHours: 168
requiresApproval: true
requiresSoDCheck: true
revocationMethod: APP_API_AND_VERIFICATION
policyVersion: iam-lab-v3
~~~

Đây là catalog minh họa: các giới hạn, chủ sở hữu và SLA trong hệ thống thật phải được quyết định theo rủi ro của tổ chức. **MaxDurationHours=168** là giới hạn giả định bảy ngày cho lab, không phải khuyến nghị chung cho mọi quyền xuất dữ liệu.

### 5.2. RBAC để xác định quyền cơ bản

**RBAC (Role-Based Access Control)** ánh xạ vị trí công việc sang quyền phổ biến. Chẳng hạn Support-Agent có quyền đọc và sửa ticket trong team; Finance-Analyst có quyền đọc báo cáo tài chính theo phạm vi; không role cơ bản nào mặc nhiên có quyền xuất toàn bộ dữ liệu khách hàng.

| Role | Entitlement cơ bản | Cần request riêng |
| --- | --- | --- |
| Support-Agent | CRM-Ticket-Reader, CRM-Ticket-Editor | CRM-Data-Export |
| Finance-Analyst | Finance-Report-Viewer | Finance-Payment-Approver |
| Engineer | Repo-Read, CI-View | Deploy-Production |
| Contractor-Support | CRM-Ticket-Reader có thời hạn | Sửa ticket hoặc export nếu được phép theo hợp đồng |

Role catalog cần có phiên bản và người chịu trách nhiệm. Không nên cho requester gõ tự do một chuỗi như **SuperAdmin** để adapter tự cấp nếu catalog không định nghĩa quyền đó.

### 5.3. ABAC để giới hạn theo ngữ cảnh

**ABAC (Attribute-Based Access Control)** đánh giá thuộc tính của **chủ thể, tài nguyên, hành động, bối cảnh**. Ví dụ giả mã:

~~~text
canRequestExport(subject, resource, context):
  subject.status == ACTIVE
  AND subject.department IN {Support, Analytics}
  AND subject.tenantId == resource.tenantId
  AND resource.projectId IN subject.assignedProjects
  AND context.requestedDurationHours <= 168
  AND context.authenticatedRequester == true
~~~

**Quan trọng:** ABAC chỉ hoạt động đúng khi thuộc tính có nguồn đáng tin và được cập nhật. Không cho client tự gửi department hoặc assignedProjects để vượt kiểm soát; thông tin tenant và dự án phải được xác minh ở dữ liệu phía server.

### 5.4. Segregation of Duties (SoD)

Xung đột phân nhiệm có thể là **tĩnh** (không nên cùng giữ hai role) hoặc **động** (một người được phép có role nhưng không được tự duyệt giao dịch do mình tạo). Ví dụ trong Finance:

- Người tạo lệnh thanh toán không được tự phê duyệt **cùng lệnh** nếu chính sách cấm.
- Người yêu cầu một đặc quyền nhạy cảm không được tự phê duyệt chính request đó.
- Một người vừa quản lý role catalog vừa trực tiếp xét quyền của bản thân có thể cần approver độc lập.

| SoD check | Kết quả cần có |
| --- | --- |
| Người duyệt trùng requester hoặc beneficiary | Từ chối quyết định hoặc định tuyến approver khác theo chính sách |
| Role hiện có xung đột role mới | Chặn grant hoặc yêu cầu thay đổi quyền/ngoại lệ hợp lệ |
| Thao tác tạo và duyệt giao dịch bởi cùng người | Backend chặn dựa trên từng giao dịch khi áp dụng SoD động |
| Người duyệt không còn owner hợp lệ | Không chấp nhận phê duyệt; định tuyến lại theo owner registry |
| Phê duyệt đã hết hạn trước khi provision | Yêu cầu đánh giá lại, không thực thi quyết định cũ |

Không gộp **override khẩn cấp** vào một cờ do requester tự đặt. Nếu tổ chức cho phép ngoại lệ SoD, cần người có thẩm quyền, biện pháp bù trừ, thời hạn và hậu kiểm.

### 5.5. Chính sách phê duyệt theo mức rủi ro

| Mức rủi ro | Ví dụ | Duyệt tối thiểu gợi ý | Kiểm soát hậu kiểm |
| --- | --- | --- | --- |
| LOW | Quyền xem tài liệu công việc theo role chuẩn | Tự động nếu policy cho phép | Audit và access review |
| MEDIUM | Quyền cập nhật ticket trong team | Manager hoặc role catalog theo quy trình | Rà soát khi Mover |
| HIGH | Quyền export dữ liệu khách hàng | Chủ dữ liệu có thẩm quyền | Time-bound, log export, expiry |
| PRIVILEGED | Quyền deploy/admin production | Chủ hệ thống + kiểm soát độc lập theo policy | JIT/PAM, MFA mạnh, session log |

Đây chỉ là **ma trận lab**, không phải yêu cầu pháp lý chung. Khi triển khai thật, phân loại dựa trên dữ liệu, môi trường, SoD, khả năng lạm dụng và quy định cụ thể.

## 6. Luồng tạo access request từng bước

### Bước 1 — Xác thực người gửi và xác định beneficiary

Người dùng vào portal qua cơ chế xác thực phù hợp như **IdP/SSO**, có MFA theo yêu cầu. Portal lấy requesterId từ session đã xác minh. Nếu một manager yêu cầu thay cho thành viên, hệ thống kiểm tra quan hệ manager–nhân viên trong nguồn đáng tin; chỉ cho yêu cầu đúng phạm vi được ủy quyền.

**Kỳ vọng:** không được tạo request cho một subjectId bất kỳ chỉ bằng cách sửa ID trong body hoặc URL. Đây là kiểm soát object-level authorization ngay tại portal.

### Bước 2 — Chọn quyền từ catalog và giải thích nhu cầu

Người dùng chọn hệ đích, entitlement, scope, ngày bắt đầu, thời hạn và lý do. Form cần cho thấy **ý nghĩa quyền**, độ nhạy cảm, owner, mức phê duyệt và hạn tối đa để tránh lựa chọn role rộng vì không hiểu.

**Kỳ vọng:** không xuất hiện lựa chọn SuperAdmin tùy tiện; quyền CRM-Data-Export phải yêu cầu scope dự án và expiry.

### Bước 3 — Kiểm tra chính sách trước khi tạo yêu cầu

Hệ thống xác định:

1. Subject còn quan hệ làm việc/hợp đồng hợp lệ tại thời điểm cần cấp?
2. Requester có quyền yêu cầu cho subject này?
3. Resource, tenant, project có thuộc phạm vi được phép?
4. Quyền yêu cầu có trong catalog còn hiệu lực?
5. Có cần phê duyệt, kiểm tra SoD hoặc kiểm tra quyền đã có?
6. Có grant tương đương đang hoạt động hoặc request trùng cần hợp nhất?
7. EffectiveAt/expiresAt hợp lệ so với trạng thái nguồn và policy?

Nếu thiếu thuộc tính nguồn đáng tin, **không tự cấp quyền**. Từ chối hoặc cách ly để bổ sung thông tin, tùy chính sách. Lưu lý do quyết định mà không lộ chi tiết dữ liệu nhạy cảm cho requester không có quyền.

### Bước 4 — Tạo request ở trạng thái SUBMITTED/PENDING_APPROVAL

Tạo mã request duy nhất, lưu bản chụp các giá trị đã xác minh và nguồn tham chiếu. Nếu yêu cầu thuộc quyền chuẩn **được policy phê duyệt trước**, có thể chuyển sang APPROVED tự động; nếu nhạy cảm, tạo nhiệm vụ cho approver hợp lệ từ owner registry. Đã tạo ticket không có nghĩa entitlement có hiệu lực.

### Bước 5 — Quyết định của approver

Approver đăng nhập độc lập, được kiểm tra thẩm quyền **tại thời điểm quyết định**, xem rõ subject, quyền, scope, lý do, thời hạn, xung đột và rủi ro.

Quyết định có thể **APPROVE**, **REJECT**, **REQUEST_MORE_INFO** hoặc **APPROVE_REDUCED_SCOPE** nếu workflow hỗ trợ. Nếu giảm scope, cần lưu scope cuối cùng được duyệt; không cấp theo scope rộng của request ban đầu.

**Chống tự phê duyệt:** requester không thể đổi approverId trong API hay gửi quyết định cho chính mình. Với trường hợp manager cũng là beneficiary, áp dụng cơ chế approver độc lập được quy định.

### Bước 6 — Kiểm tra lại trạng thái trước provision

Đây là chặng dễ bị bỏ sót: **giữa lúc được duyệt và lúc cấp quyền**, nhân viên có thể Mover, Leaver, hợp đồng hết hạn hoặc policy thay đổi. Trình điều phối phải lấy **trạng thái nguồn mới nhất** và so version/effectiveAt trước thao tác grant. Một quyết định duyệt cũ không được bật quyền cho người đã nghỉ.

Nếu quyền mới xung đột với role đang có, hệ thống phải chặn hoặc xử lý theo workflow Mover/SoD, không âm thầm bổ sung.

### Bước 7 — Cấp quyền qua IdP, SCIM hoặc API ứng dụng

| Kênh | Có thể làm gì? | Phải xác minh gì? |
| --- | --- | --- |
| **IdP groups** | Thêm user vào group làm đầu vào quyền | Group đã đồng bộ, role hiệu lực ở app có đúng không |
| **SCIM User/Group** | Tạo/cập nhật user, membership ở app hỗ trợ | User, group/membership và entitlement ở hệ đích |
| **API ứng dụng** | Cấp role, ACL, scope hoặc grant trực tiếp | Quyền hiệu lực đúng subject, scope, TTL |
| **PAM/JIT** | Bật đặc quyền tạm thời | Quyền, phiên và giới hạn thời gian |
| **Manual task** | Admin app thực hiện với sản phẩm không có API phù hợp | Người thực hiện, trạng thái thật, bằng chứng |

Không dùng **SSO login thành công** làm bằng chứng đã có quyền. SSO hỗ trợ xác thực liên kết; quyền thực tế có thể nằm trong role/ACL riêng của ứng dụng. SCIM giúp provision account/group nhưng không tự quyết định quyền nghiệp vụ.

### Bước 8 — Đọc lại và đối soát effective access

Sau lệnh cấp quyền, query tại hệ đích để xác nhận:

- Account đúng beneficiary và còn trạng thái cho phép theo chính sách?
- Đúng entitlement/scope được duyệt, không có grant rộng hơn?
- TTL/expiry đã được cấu hình hoặc workflow theo dõi thực thi thu hồi?
- Có thể dùng quyền trong phạm vi hợp lệ và **không thể** dùng ngoài phạm vi?
- Quyền có đến từ nhiều đường grant, tạo nguy cơ khó thu hồi về sau?

Khi đã có bằng chứng, đánh dấu **FULFILLED/VERIFIED** và thông báo requester. Nếu provisioning hoặc readback lỗi, trạng thái phải chỉ rõ **PENDING_VERIFICATION/FAILED** và owner, không gửi thông báo sai rằng đã có quyền.

### Bước 9 — Hết hạn, Mover, Leaver và access review

Từ khi được cấp, entitlement còn chịu các trigger:

- **ExpiresAt:** quyền tạm thời phải bị revoke; **EXPIRED_PENDING_REVOKE** khác **REVOKED**.
- **Mover:** tính lại quyền mục tiêu; quyền export không còn căn cứ phải được thu hồi dù expiry chưa đến.
- **Leaver:** chặn grant đang chờ, thu hồi quyền đã cấp theo luồng offboarding, xử lý session/token độc lập khi liên quan.
- **Access review:** owner có thể giữ, giảm scope hoặc yêu cầu thu hồi; quyết định review chưa hoàn tất cho đến khi quyền thật được sửa.
- **Compromise/incident:** quyền hoặc credential có thể cần bị chặn sớm theo quy trình ứng cứu được ủy quyền.

## 7. Một kịch bản end-to-end có thể tái hiện

### 7.1. Trước request

An thuộc Support, trạng thái ACTIVE, tenant TENANT-LAB-01, dự án PROJECT-LAB-07. CRM có account hợp lệ nhưng **không** có customers:export. IdP có thể cho An đăng nhập CRM bằng SSO; đây không phải bằng chứng An có quyền xuất dữ liệu.

### 7.2. Submit

An gửi access request có thời hạn bảy ngày. Policy xác minh dự án được giao, trạng thái ACTIVE, scope giới hạn, quyền thuộc catalog và yêu cầu phê duyệt của chủ dữ liệu CRM. Request chuyển **PENDING_APPROVAL**.

### 7.3. Approval

Người có ID **OWNER-CRM-LAB** là chủ dữ liệu theo owner registry, không trùng requester và có thẩm quyền quyết định quyền export. Quyết định được ghi **APPROVED** với scope, thời hạn và phiên bản policy.

### 7.4. Fulfillment

Adapter thêm grant CRM-Data-Export với scope tenant/project. CRM nhận yêu cầu nhưng xử lý bất đồng bộ; trạng thái request là **PENDING_VERIFICATION** cho tới khi đọc lại thấy grant thực tế. Sau readback và kiểm thử âm tính ngoài tenant, request là **FULFILLED**.

### 7.5. Expiry hoặc Mover/Leaver

Sau bảy ngày, workflow thu hồi grant, kiểm tra quyền xuất không còn hiệu lực và đánh dấu **REVOKED**. Nếu An Mover khỏi Support trước đó, quyền có thể bị thu hồi sớm. Nếu An Leaver khi đang chờ duyệt, request bị hủy hoặc chặn cấp phát; không có retry cũ được cấp lại.

| Chặng | Trạng thái quyền thực tế | Trạng thái request | Điều cần ghi |
| --- | --- | --- | --- |
| Trước yêu cầu | Không có quyền export | Chưa có request | Snapshot actual |
| Sau submit | Vẫn không có quyền | PENDING_APPROVAL | Requester, lý do, scope |
| Sau approve | Vẫn chưa chắc có quyền | APPROVED | Approver, policy version |
| Đang cấp | Có thể chưa đồng bộ | PROVISIONING/PENDING_VERIFICATION | Connector result |
| Đã đọc lại | Có đúng scope | FULFILLED | Target grant và verifiedAt |
| Đến hạn | Có thể vẫn còn nếu revoke lỗi | EXPIRED_PENDING_REVOKE | Owner và retry |
| Sau readback revoke | Không còn quyền export | REVOKED | Evidence thu hồi |

## 8. Lab Java 17: tạo request, phê duyệt, cấp quyền và thu hồi

Để quan sát toàn bộ vòng đời, chương này dùng **một chương trình Java thuần**, không cần IdP hoặc CRM thật. MockTarget đại diện cho **một entitlement tại một hệ đích**, còn HrisSource đóng vai nguồn có thẩm quyền. Mọi nhân vật, tenant, resource và ID đều là giả.

**Mục tiêu chạy:** submit đúng yêu cầu, ngăn tự phê duyệt, phê duyệt bằng owner hợp lệ, mô phỏng connector lỗi một lần, retry an toàn, đọc lại quyền, hết hạn tự thu hồi và chặn request đang chờ khi Leaver.

### 8.1. Mã Java 17 tự chứa

Lưu thành file **AccessRequestLab.java** trong môi trường thực hành cá nhân nếu muốn chạy. Không cần thêm thư viện bên ngoài.

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class AccessRequestLab {
    enum Employment { ACTIVE, TERMINATED }
    enum Status {
        PENDING_APPROVAL, APPROVED, SCHEDULED,
        PROVISIONING, PENDING_VERIFICATION, FULFILLED,
        REVOKING, REVOKED, CANCELLED, FAILED
    }

    record Subject(
            String id, String department, String tenant,
            Set<String> projects, Employment employment, long version
    ) {}

    record AccessInput(
            String idempotencyKey, String subjectId, String entitlement,
            String tenant, String project, String justification,
            Instant effectiveAt, Instant expiresAt
    ) {}

    static final class Request {
        final String requestId;
        final String requesterId;
        final AccessInput input;
        final long sourceVersionAtSubmit;
        long sourceVersionAtApproval = -1;
        String approvedBy;
        Status status = Status.PENDING_APPROVAL;

        Request(String id, String requester, AccessInput input, long version) {
            requestId = id;
            requesterId = requester;
            this.input = input;
            sourceVersionAtSubmit = version;
        }
    }

    static final class MockTarget {
        private final Set<String> grants = new HashSet<>();
        private boolean failGrantOnce;

        static String key(AccessInput input) {
            return input.subjectId() + "|" + input.entitlement()
                    + "|" + input.tenant() + "|" + input.project();
        }

        void failNextGrant() { failGrantOnce = true; }

        void grant(AccessInput input) {
            if (failGrantOnce) {
                failGrantOnce = false;
                throw new IllegalStateException("Lab connector timeout");
            }
            grants.add(key(input)); // Idempotent theo desired entitlement.
        }

        boolean hasGrant(AccessInput input) {
            return grants.contains(key(input)); // Readback giả lập.
        }

        void revoke(AccessInput input) {
            grants.remove(key(input)); // Idempotent.
        }
    }

    static final class Service {
        private final Map<String, Subject> subjects = new HashMap<>();
        private final Map<String, Request> byIdempotencyKey = new HashMap<>();
        private final MockTarget target;
        private Instant now;
        private long nextRequestId = 1;

        Service(MockTarget target, Instant now) {
            this.target = target;
            this.now = now;
        }

        void putSubject(Subject subject) {
            subjects.put(subject.id(), subject);
        }

        void advanceTo(Instant time) { now = time; }

        private Subject requireEligible(AccessInput input) {
            Subject s = subjects.get(input.subjectId());
            if (s == null || s.employment() != Employment.ACTIVE
                    || !"Support".equals(s.department())
                    || !Objects.equals(s.tenant(), input.tenant())
                    || !s.projects().contains(input.project())) {
                throw new SecurityException("Identity/policy is not eligible");
            }
            return s;
        }

        Request submit(String authenticatedRequester, AccessInput input) {
            Objects.requireNonNull(input);
            if (input.idempotencyKey() == null
                    || input.idempotencyKey().isBlank()) {
                throw new IllegalArgumentException("Missing idempotency key");
            }
            if (authenticatedRequester == null
                    || !authenticatedRequester.equals(input.subjectId())) {
                throw new SecurityException("Requester may only request for self");
            }
            Request previous = byIdempotencyKey.get(input.idempotencyKey());
            if (previous != null) {
                if (!previous.input.equals(input)
                        || !previous.requesterId.equals(authenticatedRequester)) {
                    throw new SecurityException("Idempotency key reuse");
                }
                return previous;
            }

            Subject s = requireEligible(input);
            if (!"CRM-Data-Export".equals(input.entitlement())
                    || input.justification() == null
                    || input.justification().isBlank()
                    || input.effectiveAt() == null
                    || input.expiresAt() == null
                    || !input.expiresAt().isAfter(input.effectiveAt())
                    || Duration.between(
                            input.effectiveAt(), input.expiresAt()
                    ).compareTo(Duration.ofDays(7)) > 0
                    || !input.expiresAt().isAfter(now)) {
                throw new IllegalArgumentException("Invalid scope or duration");
            }

            Request request = new Request(
                    "AR-LAB-" + nextRequestId++, authenticatedRequester,
                    input, s.version()
            );
            byIdempotencyKey.put(input.idempotencyKey(), request);
            return request;
        }

        void approve(String approverId, Request request) {
            if (request.status != Status.PENDING_APPROVAL) {
                throw new IllegalStateException("Not pending approval");
            }
            if (!"OWNER-CRM-LAB".equals(approverId)
                    || approverId.equals(request.requesterId)
                    || approverId.equals(request.input.subjectId())) {
                throw new SecurityException("Approver not authorized");
            }
            Subject current = requireEligible(request.input);
            if (current.version() != request.sourceVersionAtSubmit) {
                throw new IllegalStateException("Identity changed: review again");
            }
            request.approvedBy = approverId;
            request.sourceVersionAtApproval = current.version();
            request.status = Status.APPROVED;
        }

        Status fulfill(Request request) {
            if (request.status == Status.FULFILLED) {
                return request.status;
            }
            if (request.status != Status.APPROVED
                    && request.status != Status.SCHEDULED
                    && request.status != Status.FAILED
                    && request.status != Status.PENDING_VERIFICATION) {
                throw new IllegalStateException("Request cannot be fulfilled");
            }

            Subject current = subjects.get(request.input.subjectId());
            if (current == null || current.employment() != Employment.ACTIVE
                    || current.version() != request.sourceVersionAtApproval) {
                // Một grant từ lần thử trước có thể đã áp dụng dù ACK bị mất.
                if (target.hasGrant(request.input)) {
                    request.status = Status.REVOKING;
                    target.revoke(request.input);
                    request.status = target.hasGrant(request.input)
                            ? Status.FAILED : Status.REVOKED;
                } else {
                    request.status = Status.CANCELLED;
                }
                return request.status;
            }
            requireEligible(request.input); // Đánh giá policy lần nữa.
            if (!now.isBefore(request.input.expiresAt())) {
                // Hết hạn có thể xảy ra sau một grant chưa xác minh.
                request.status = Status.REVOKING;
                target.revoke(request.input);
                request.status = target.hasGrant(request.input)
                        ? Status.FAILED : Status.REVOKED;
                return request.status;
            }
            if (now.isBefore(request.input.effectiveAt())) {
                request.status = Status.SCHEDULED;
                return request.status;
            }

            try {
                request.status = Status.PROVISIONING;
                if (!target.hasGrant(request.input)) {
                    target.grant(request.input);
                }
                request.status = Status.PENDING_VERIFICATION;
                if (target.hasGrant(request.input)) {
                    request.status = Status.FULFILLED;
                }
            } catch (RuntimeException e) {
                request.status = Status.FAILED;
            }
            return request.status;
        }

        Status expire(Request request) {
            if (now.isBefore(request.input.expiresAt())) {
                return request.status;
            }
            request.status = Status.REVOKING;
            target.revoke(request.input);
            request.status = target.hasGrant(request.input)
                    ? Status.FAILED : Status.REVOKED;
            return request.status;
        }

        void leaver(String subjectId, long sourceVersion) {
            Subject old = subjects.get(subjectId);
            if (old == null || sourceVersion <= old.version()) {
                throw new IllegalArgumentException("Stale or missing HR event");
            }
            putSubject(new Subject(
                    old.id(), old.department(), old.tenant(),
                    old.projects(), Employment.TERMINATED, sourceVersion
            ));
            for (Request request : byIdempotencyKey.values()) {
                if (!request.input.subjectId().equals(subjectId)) {
                    continue;
                }
                if (target.hasGrant(request.input)) {
                    request.status = Status.REVOKING;
                    target.revoke(request.input);
                    request.status = target.hasGrant(request.input)
                            ? Status.FAILED : Status.REVOKED;
                } else if (request.status != Status.REVOKED) {
                    request.status = Status.CANCELLED;
                }
            }
        }
    }

    public static void main(String[] args) {
        Instant start = Instant.parse("2026-11-24T02:00:00Z");
        MockTarget crm = new MockTarget();
        Service service = new Service(
                crm, Instant.parse("2026-11-24T02:05:00Z")
        );
        service.putSubject(new Subject(
                "EMP-LAB-017", "Support", "TENANT-LAB-01",
                Set.of("PROJECT-LAB-07"), Employment.ACTIVE, 16
        ));

        AccessInput input = new AccessInput(
                "FORM-REQUEST-001", "EMP-LAB-017",
                "CRM-Data-Export", "TENANT-LAB-01", "PROJECT-LAB-07",
                "Xuất báo cáo dự án tuần", start, start.plus(Duration.ofDays(7))
        );
        Request request = service.submit("EMP-LAB-017", input);
        System.out.println("Submit: " + request.status);

        try {
            service.approve("EMP-LAB-017", request);
        } catch (SecurityException expected) {
            System.out.println("Self-approval blocked");
        }
        service.approve("OWNER-CRM-LAB", request);
        System.out.println("Approved: " + request.status);

        crm.failNextGrant();
        System.out.println("First provision: " + service.fulfill(request));
        System.out.println("Retry provision: " + service.fulfill(request));
        System.out.println("Actual access: " + crm.hasGrant(input));

        Request replay = service.submit("EMP-LAB-017", input);
        System.out.println("Same request: "
                + request.requestId.equals(replay.requestId));

        service.advanceTo(start.plus(Duration.ofDays(7)).plusSeconds(1));
        System.out.println("Expiry: " + service.expire(request));
        System.out.println("Actual access: " + crm.hasGrant(input));

        AccessInput pendingInput = new AccessInput(
                "FORM-REQUEST-002", "EMP-LAB-017",
                "CRM-Data-Export", "TENANT-LAB-01", "PROJECT-LAB-07",
                "Yêu cầu công việc mới",
                start.plus(Duration.ofDays(8)),
                start.plus(Duration.ofDays(9))
        );
        Request pending = service.submit("EMP-LAB-017", pendingInput);
        service.leaver("EMP-LAB-017", 17);
        System.out.println("Pending after Leaver: " + pending.status);
    }
}
~~~

### 8.2. Kết quả dự kiến

~~~text
Submit: PENDING_APPROVAL
Self-approval blocked
Approved: APPROVED
First provision: FAILED
Retry provision: FULFILLED
Actual access: true
Same request: true
Expiry: REVOKED
Actual access: false
Pending after Leaver: CANCELLED
~~~

Chương trình có một số **giới hạn có chủ ý** để tập trung vào workflow: giả định requester đã được lớp authentication bên ngoài xác thực; approver cố định trong lab; một target/entitlement; lưu trạng thái trong bộ nhớ; đọc lại quyền tức thời; không xử lý giao dịch đồng thời, đa role hay token thật. **Không dùng nguyên trạng chương trình làm dịch vụ IAM production.**

### 8.3. Nhiệm vụ sửa mã

1. Thay owner cố định bằng **EntitlementCatalog** có owner, mức nhạy cảm, maxDuration, mapping app và policyVersion.
2. Thêm **PENDING_VERIFICATION** thật: mock adapter nhận lệnh nhưng readback chưa thấy grant; chỉ FULFILLED khi quyền xuất hiện thực tế.
3. Thêm **revoke failure once**, giữ EXPIRED_PENDING_REVOKE/FAILED thay vì tự đặt REVOKED khi chưa chắc quyền mất.
4. Thêm trạng thái **MOVER** thay department Support → Finance. Các request đang chờ phải bị đánh giá lại; grant xuất dữ liệu cũ phải thu hồi nếu policy không còn cho phép.
5. Mô phỏng **service account** gửi request với sponsor, owner và quyền deploy có scope, không giả định workload thuộc HRIS như nhân viên.
6. Chống hai worker cùng xử lý request bằng optimistic locking/state version trong kho dữ liệu bền vững hoặc mô phỏng compare-and-set.
7. Thêm audit events cho SUBMITTED, APPROVED, PROVISIONING, FULFILLED, FAILED và REVOKED.
8. Thêm một quyền được cấp qua **hai đường** (group và direct ACL). Chứng minh việc gỡ một đường không đủ để thu hồi effective permission.

## 9. Gắn access request với IdP, SSO, SCIM và authorization

### 9.1. Tách rõ chức năng từng thành phần

| Thành phần | Vai trò trong bài lab | Sai lầm cần tránh |
| --- | --- | --- |
| **IdP** | Xác thực principal, trạng thái danh tính, group, MFA | Tưởng rằng có account IdP là đã có mọi role SaaS |
| **SSO (SAML/OIDC)** | Liên kết đăng nhập vào portal/app | Tưởng SSO login thành công là entitlement đã cấp |
| **SCIM User/Group** | Tạo/sửa user và membership khi ứng dụng hỗ trợ | Tưởng SCIM tự quyết định policy nghiệp vụ hoặc xóa mọi token |
| **RBAC** | Quyền cơ sở theo role | Dùng role quá rộng thay cho entitlement có scope |
| **ABAC** | Điều kiện status, tenant, project, bối cảnh | Tin thuộc tính từ client hoặc cache quá cũ |
| **IGA/approval** | Quy trình yêu cầu, phê duyệt, SoD, review | Tưởng approval đồng nghĩa provisioning hoàn tất |
| **Application API/ACL** | Thực thi entitlement cụ thể | Bỏ quên direct grant nằm ngoài IdP group |
| **PAM/JIT** | Đặc quyền ngắn hạn có kiểm soát | Cấp admin thường trực cho nhu cầu tạm thời |

### 9.2. Ví dụ SCIM Group là một bước, không phải kết luận

Nếu CRM cấu hình **CRM-Data-Export** thông qua một Group, adapter có thể thêm thành viên vào SCIM Group. Tuy nhiên, **SCIM Group ID, User ID, mapping group→role và khả năng ứng dụng hỗ trợ** phải được xác minh từ tài liệu và dữ liệu hệ đích.

Ví dụ payload minh họa việc thêm một thành viên bằng SCIM PatchOp:

~~~http
PATCH /scim/v2/Groups/CRM-G-EXPORT HTTP/1.1
Content-Type: application/scim+json
Authorization: Bearer <CONNECTOR_CREDENTIAL>

{
  "schemas": [
    "urn:ietf:params:scim:api:messages:2.0:PatchOp"
  ],
  "Operations": [
    {
      "op": "add",
      "path": "members",
      "value": [
        {"value": "CRM-U-017"}
      ]
    }
  ]
}
~~~

Đây là **ví dụ giao thức**, không phải lệnh sẵn để chạy ở hệ thống thật. Quyền cuối cùng do CRM quyết định. Nếu CRM không hỗ trợ SCIM Group hoặc role export được gán qua API riêng, adapter phải dùng đường khác. Sau thao tác, đọc lại Group membership **và** quyền customers:export thực tế tại app.

### 9.3. Thu hồi quyền SCIM và direct ACL

Khi quyền hết hạn, có thể cần **gỡ membership SCIM Group**, **thu hồi role qua API ứng dụng**, **xóa direct ACL**, và kiểm tra **token/session** còn quyền export hay không. Không dùng thành công của một lệnh gỡ Group làm bằng chứng toàn bộ effective access đã bị chặn.

Với app không thể liệt kê mọi entitlement, cần **biện pháp xác minh thay thế** có owner và ghi rõ giới hạn. Không đánh dấu VERIFIED chỉ vì một ticket thủ công đã được tạo.

### 9.4. Quyền tạm thời và token còn hiệu lực

Một access token đã phát hành có scope export có thể tiếp tục được resource server chấp nhận cho tới khi hết hạn nếu không có cơ chế kiểm tra trạng thái mới hoặc thu hồi. Nếu yêu cầu là **thu hồi ngay**, cần xác định cơ chế cụ thể: token revocation, introspection/deny-list, policy check tại resource server, session termination hoặc containment khác theo hệ đích. Ghi rõ giới hạn kỹ thuật và thời điểm mất quyền thực tế.

## 10. Threat modeling và kiểm tra bảo mật của access request

Access request là một bề mặt đặc biệt nhạy cảm vì nó **có thể tạo ra đặc quyền mới**. Sai sót ở bước xác thực requester, chọn approver hoặc xử lý trạng thái có thể biến portal thành đường leo thang quyền.

### 10.1. Các tài sản cần bảo vệ

- **Danh tính và trạng thái nhân sự:** không được cho phép requester giả mạo người khác hoặc tự khai đang active.
- **Entitlement catalog:** không để client tự đặt role/permission tùy ý vượt danh mục.
- **Approval records:** không để requester tự sửa approvedBy hoặc trạng thái APPROVED.
- **Provisioning credential:** secret kết nối IdP/SCIM/API được giữ trong secret manager và có quyền tối thiểu.
- **Target account mapping:** không để thay subjectId/targetAccountId để cấp quyền cho người khác.
- **Audit trail:** không cho người không có quyền sửa hoặc xóa bằng chứng phê duyệt và fulfillment.
- **TTL và revoke jobs:** không để đổi expiresAt sau phê duyệt mà không được xét lại.

### 10.2. Ma trận mối đe dọa và kiểm soát

| Nguy cơ | Kịch bản lỗi | Kiểm soát |
| --- | --- | --- |
| **Self-approval** | Requester giả approverId trong body | Server xác định approver từ registry, kiểm tra authenticated principal |
| **IDOR/BOLA** | Đổi subjectId trong request để xin quyền cho người khác | Kiểm tra quan hệ requester–beneficiary và quyền hành động |
| **Role injection** | Client gửi entitlement SuperAdmin không có trong catalog | Allowlist entitlement + policy engine |
| **Scope escalation** | Duyệt tenant A nhưng adapter cấp toàn bộ tenant | Lưu scope được duyệt bất biến; readback chính xác scope |
| **Time manipulation** | Thay expiresAt để giữ quyền vô thời hạn | Max TTL, review khi sửa, expiry job có kiểm chứng |
| **Approval replay** | Reuse quyết định đã duyệt cho request mới | Approval gắn requestId, subject, scope, expiry, policy version |
| **Stale identity** | Leaver sau approval, job grant vẫn chạy | Kiểm tra trạng thái nguồn mới nhất trước thực thi/retry |
| **SoD bypass** | Tự tạo và duyệt payment bằng hai role | SoD tĩnh và động ở cấp nghiệp vụ |
| **Target drift** | Admin app cấp direct ACL ngoài portal | Đối soát ngược từ hệ đích và access review |
| **Connector compromise** | Credential provision có quyền admin rộng | Least privilege, secret rotation, audit, cảnh báo |
| **Audit tampering** | Sửa bản ghi approvedBy hoặc verifiedAt | Phân quyền, lưu log chống sửa trái phép, correlation ID |
| **Information disclosure** | Portal cho xem request của người khác | Object-level authorization trên API xem danh sách/chi tiết |

### 10.3. Checklist bảo mật endpoint

- [ ] API tạo request lấy requester từ authenticated context, không tin requesterId do client đưa lên.
- [ ] API xem/sửa/hủy request kiểm tra quyền theo object và vai trò, không chỉ login.
- [ ] API quyết định approval yêu cầu approver có thẩm quyền **ngay khi quyết định**.
- [ ] Không chấp nhận client tự đặt requestStatus, approvedBy, fulfillmentResult hay verifiedAt.
- [ ] Input entitlement, resource, scope được đối chiếu allowlist/catalog và nguồn đáng tin.
- [ ] Tham số thời gian có timezone, được xác minh theo chính sách TTL.
- [ ] Không bật quyền khi policy engine lỗi, thiếu dữ liệu thiết yếu hoặc kết quả không rõ.
- [ ] API phải phân biệt việc cấp quyền cho bản thân và **thay mặt người khác** có ủy quyền.
- [ ] Các thao tác grant/revoke có idempotency và kiểm tra quyền trước khi retry.
- [ ] Log không chứa password, raw access token, private key, thông tin cá nhân không cần thiết.

### 10.4. Tình huống kiểm thử vượt quyền

**Bài toán:** An đang yêu cầu CRM-Data-Export. Một người khác là Bình đổi subjectId của API tạo request thành EMP-LAB-017 và cố gửi request cho An.

Nếu chính sách của portal chỉ cho self-service, API phải trả kết quả **không được phép**, dù Bình đã đăng nhập hợp lệ. Nếu nghiệp vụ cho phép manager yêu cầu thay người khác, server phải xác minh **Bình thực sự là manager/sponsor được ủy quyền của An** từ nguồn đáng tin, không chỉ tin rằng Bình gửi trường managerId.

## 11. Liên kết access request với Joiner–Mover–Leaver

Mỗi request đều có **vòng đời phụ thuộc trạng thái identity**. Hệ thống nên re-evaluate chính sách tại các thời điểm quyết định và thực thi, thay vì chỉ xem tình trạng lúc submit.

### 11.1. Joiner: quyền cơ bản và quyền bổ sung

| Bước | Trạng thái người mới | Quy tắc access request |
| --- | --- | --- |
| HR xác minh người mới | Có subjectId, startAt, manager | Có thể chuẩn bị account/request theo chính sách |
| Trước effectiveAt | Chưa được truy cập dữ liệu thực | Không provision trước thời điểm cho phép |
| Tới effectiveAt | ACTIVE theo nguồn có thẩm quyền | Cấp role chuẩn; request quyền bổ sung vẫn qua approval |
| Joiner bị hủy | Không còn quan hệ hợp lệ | Hủy request pending, revoke quyền provision nhầm, đối soát |

Điều quan trọng là **Joiner không mặc nhiên được mọi quyền phục vụ công việc chỉ từ một role mơ hồ**. Quyền nhạy cảm như export, thanh toán hoặc deploy production có thể cần access request riêng, approval và expiry.

### 11.2. Mover: quyền mới không được tích lũy với quyền cũ

Khi An chuyển Support → Finance:

1. HRIS phát Mover có **sourceVersion** mới, thời điểm hiệu lực và thuộc tính mới.
2. Policy tính lại **desiredEntitlements** theo role/ABAC.
3. Request CRM-Data-Export còn pending phải được kiểm tra lại; nếu An không còn eligible, hủy hoặc từ chối.
4. Quyền export đã cấp trước Mover phải đi vào luồng thu hồi nếu không còn căn cứ, **không chờ hết expiresAt**.
5. Request Finance-Report-Viewer mới được xét theo policy hiện hành; xung đột SoD được kiểm tra.
6. Đối soát quyền hiệu lực ở CRM và Finance, bao gồm direct grant và token nếu cần.

### 11.3. Leaver: ngăn grant mới và thu hồi grant cũ

Khi HRIS xác nhận Leaver có hiệu lực:

- **Pending/Approved chưa provision:** hủy hoặc đặt trạng thái chặn; mọi job grant retry phải kiểm tra nguồn mới nhất trước khi chạy.
- **Provisioning đang chạy:** theo dõi những job chưa kết thúc, chặn/cancel nếu có thể và đối soát sau các job cạnh tranh.
- **FULFILLED:** phát sự kiện revoke; disable app account hoặc gỡ entitlement/ACL, xử lý token/phiên theo khả năng hệ đích và readback.
- **Tài khoản dịch vụ:** chuyển owner hoặc ngừng workload hợp lệ; không giữ token cá nhân Leaver làm đường truy cập cho pipeline.
- **Audit:** ghi thời điểm cần chặn, thời điểm thực sự mất quyền và target còn PARTIAL/UNKNOWN.

**Nguyên tắc:** request được APPROVED hôm qua không có quyền ưu tiên cao hơn trạng thái Leaver có hiệu lực hôm nay.

### 11.4. Quyền tự hết hạn và kết quả access review

Mỗi quyền tạm thời cần một trigger thu hồi được thực thi:

~~~mermaid
flowchart LR
    GRANTED["Access FULFILLED"] --> TRIGGER{"Expiry / Mover / Leaver / Review"}
    TRIGGER --> REVOKE["Revoke qua group / ACL / API"]
    REVOKE --> READBACK["Đọc lại effective permission"]
    READBACK -->|Mất quyền đúng scope| VERIFIED["REVOKED"]
    READBACK -->|Quyền còn hoặc chưa rõ| EX["FAILED/UNKNOWN + Owner"]
    EX --> REVOKE
~~~

Một quyền đã “hết hạn trên giấy” nhưng vẫn có hiệu lực trong ứng dụng là **quyền tồn dư**. Nếu policy yêu cầu thu hồi tức thời mà hệ đích không hỗ trợ, cần nêu độ trễ, cơ chế chặn và người chấp nhận rủi ro, không tự báo REVOKED.

### 11.5. Quyền của service account/workload

Với **workload identity**, requester có thể là một kỹ sư hoặc nền tảng tự động được ủy quyền, beneficiary là **service principal**, không phải nhân viên. Chính sách xác định owner, scope, môi trường, project, TTL và đường thu hồi. Nếu chủ sở hữu rời tổ chức, cần thay owner và rà soát credential; không mặc định xóa workload đang phục vụ hệ thống, nhưng cũng không giữ PAT cá nhân đã mất căn cứ.

## 12. Ma trận kiểm thử dự án

Tạo test data giả cho An, Bình, chủ dữ liệu CRM và một workload. Mỗi ca cần ghi **Input, Expected, Actual, PASS/FAIL, evidence reference**. Khi readback không có dữ liệu, ghi **UNKNOWN** thay vì coi việc gọi API đã thành công.

| ID | Tình huống | Kỳ vọng |
| --- | --- | --- |
| **AR-01** | An ACTIVE, gửi yêu cầu export đúng tenant/project/7 ngày | PENDING_APPROVAL; chưa có quyền trước approval |
| **AR-02** | An gửi lại cùng idempotency key và payload | Trả cùng request, không tạo trùng |
| **AR-03** | Cùng key nhưng payload khác | Từ chối reuse idempotency key |
| **AR-04** | An không thuộc project được đề nghị | Từ chối theo ABAC |
| **AR-05** | User đã đăng nhập nhưng đòi entitlement không có trong catalog | Từ chối; không provision |
| **AR-06** | Quyền có hạn vượt max TTL | Từ chối hoặc yêu cầu giảm hạn |
| **AR-07** | expiresAt không sau effectiveAt | Không chấp nhận request |
| **AR-08** | An tự bấm approve request của mình | Từ chối self-approval |
| **AR-09** | Bình không phải owner CRM nhưng cố approve | Từ chối vì không đủ thẩm quyền |
| **AR-10** | Chủ dữ liệu hợp lệ duyệt đúng scope | APPROVED, audit approver/policy |
| **AR-11** | Request mới APPROVED nhưng chưa provision | Quyền vẫn chưa hiệu lực; không báo FULFILLED |
| **AR-12** | Connector grant lỗi lần đầu | FAILED/PENDING, có retry/owner |
| **AR-13** | Retry connector sau lỗi tạm thời | FULFILLED khi readback khớp |
| **AR-14** | SCIM nhận request nhưng app chưa có role | PENDING_VERIFICATION |
| **AR-15** | App cấp role rộng hơn scope đã duyệt | Không FULFILLED, phát hiện drift |
| **AR-16** | Client sửa subjectId để xin cho người khác | Bị chặn nếu không có ủy quyền |
| **AR-17** | Client gửi approvedBy/status giả | Server bỏ qua/từ chối, không cấp |
| **AR-18** | Viewer cố gọi export endpoint | Backend DENY |
| **AR-19** | An export trong tenant đúng nhưng project sai | Backend DENY theo object/ABAC |
| **AR-20** | Quyền đã hết hạn | Revoke và readback, trạng thái REVOKED |
| **AR-21** | Revoke lỗi, direct ACL vẫn còn | EXPIRED_PENDING_REVOKE/FAILED, không REVOKED |
| **AR-22** | HR phát Mover sang Finance khi pending | Re-evaluate; hủy quyền CRM không còn hợp lệ |
| **AR-23** | Mover khi quyền export đang active | Revoke nếu không còn căn cứ, kiểm chứng |
| **AR-24** | Leaver sau approval nhưng trước provision | Không cấp quyền; request bị hủy/chặn |
| **AR-25** | Grant retry sau Leaver v18 từ request v17 | Không kích hoạt quyền; đối soát target |
| **AR-26** | Leaver nhưng app token export còn hiệu lực | Không khẳng định offboarding hoàn tất |
| **AR-27** | Admin cấp direct grant ngoài portal | Reconciler phát hiện drift |
| **AR-28** | Quyền tài chính xung đột SoD | Chặn hoặc xử lý ngoại lệ được duyệt |
| **AR-29** | Workload yêu cầu Deploy-Production quá rộng | Chặn theo scope và owner |
| **AR-30** | Manual task được tạo nhưng app chưa sửa quyền | Chưa VERIFIED; cần owner xác nhận |

### 12.1. Ví dụ báo cáo hai ca

~~~yaml
testCase: AR-08
subjectId: EMP-LAB-017
input: "Requester tries to approve own CRM-Data-Export request"
expected: "DENY approval, no provisioning"
actual: "DENY"
result: PASS
evidenceRef: "lab://audit/AR-08"
~~~

~~~yaml
testCase: AR-21
subjectId: EMP-LAB-017
input: "Expiry job fails to remove direct ACL"
expected: "Not REVOKED; exception with owner"
actual: "FAILED; CRM direct ACL still active"
result: PASS
exceptionOwner: "crm-application-owner"
evidenceRef: "lab://audit/AR-21"
~~~

Các trường **actual/result/evidenceRef** ở trên là ví dụ minh họa để người học biết cần ghi gì, **không phải xác nhận đã chạy test**. Khi thực hành, phải thay bằng quan sát thật trong lab được phép.

## 13. Runbook: xử lý yêu cầu chưa hoàn tất

Khi một access request không thể chuyển trạng thái theo dự kiến, đừng chỉ bấm retry nhiều lần. Cần biết **quyền thực tế đã tồn tại chưa** để tránh cấp vượt, xóa nhầm hoặc đóng sai yêu cầu.

### 13.1. Quy trình xử lý chung

1. **Xác định yêu cầu:** requestId, subjectId, entitlement, target, scope, status, effectiveAt/expiresAt, approver.
2. **Kiểm tra nguồn:** identity vẫn active? Có Mover/Leaver mới? Hợp đồng hoặc sponsor còn hiệu lực không?
3. **Kiểm tra quyết định:** approval đúng owner, không vi phạm SoD, policy version có còn áp dụng?
4. **Đọc lại target:** entitlement có thực sự tồn tại, scope/TTL có đúng không? Có đường cấp khác không?
5. **Phân loại lỗi:** tạm thời, sai mapping, thiếu quyền connector, target offline, approval không hợp lệ, policy stale hay quyền bị cấp ngoài workflow?
6. **Containment:** nếu đã cấp quá phạm vi, ưu tiên giảm/chặn quyền sai theo quy trình có thẩm quyền.
7. **Khắc phục:** retry idempotent, sửa mapping, phê duyệt lại, thu hồi grant sai hoặc giao manual task.
8. **Xác minh và đóng:** chỉ FULFILLED/REVOKED sau readback; các lỗi chưa rõ giữ trạng thái ngoại lệ có owner, hạn xử lý và bằng chứng.

### 13.2. Bảng xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân có thể | Đọc lại gì? | Hành động |
| --- | --- | --- | --- |
| Request APPROVED nhưng chưa có quyền | Job chưa chạy, lỗi SCIM/API, sai mapping | App user, role, group, target job | PENDING/FAILED; retry an toàn hoặc app owner |
| Adapter trả 200 nhưng role chưa xuất hiện | App bất đồng bộ hoặc gắn sai account | User ID/entitlement thực tế | PENDING_VERIFICATION, đối soát lại |
| Có role nhưng sai tenant/project | Mapping scope rộng hoặc lỗi policy | Effective entitlement và resource scope | Revoke/thu hẹp ngay theo rủi ro, điều tra |
| Requester tự duyệt được | Lỗi authorization hoặc owner registry | Audit authenticated principal và decision | Chặn đường approval, thu hồi grant sai, sửa kiểm soát |
| Request bị REJECTED nhưng quyền xuất hiện | Grant thủ công hoặc event cũ | Direct ACL, group, token scope | Điều tra grant path và revoke quyền không có căn cứ |
| Quyền hết hạn vẫn hoạt động | Scheduler lỗi, target revoke chưa xong, token cũ | Role, ACL, session/token | EXPIRED_PENDING_REVOKE và remediation |
| Mover xong nhưng quyền cũ còn | Role cũ/direct grant chưa gỡ | Effective permissions ở app cũ | Thu hồi và xác minh, không chỉ sửa HRIS |
| Leaver xong nhưng job cấp cũ retry | Lỗi kiểm tra sourceVersion/đồng thời | Job queue, nguồn HR, actual grant | Ngăn grant cũ, revoke lại, bổ sung kiểm thử |
| Manual task đã đóng nhưng app chưa đổi | Thiếu bằng chứng thực thi | Console/app API hoặc xác minh độc lập | Mở lại/escalate, không coi VERIFIED |
| App offline lúc cần revoke | Không có readback/đường thu hồi | Biện pháp chặn đang còn hiệu lực | Giữ PARTIAL/UNKNOWN và owner, containment khi cần |

### 13.3. Hai trạng thái cần phân biệt

**PENDING_VERIFICATION:** điều phối đã yêu cầu thay đổi, nhưng chưa biết trạng thái cuối. Không suy ra thất bại hay thành công nếu readback chưa có.

**FAILED/PARTIAL:** biết bước nào lỗi hoặc chỉ một phần target hoàn thành. Nếu một access package chứa cả CRM và Finance, một target VERIFIED không biến toàn request thành FULFILLED khi target kia còn FAIL. Lưu trạng thái **theo từng target**, không chỉ một cờ boolean toàn workflow.

### 13.4. Ví dụ phiếu ngoại lệ

~~~yaml
exceptionId: AR-EX-LAB-07
requestId: AR-LAB-2026-0041
subjectId: EMP-LAB-017
targetSystem: crm-lab
entitlement: CRM-Data-Export
expected: "Role scoped to PROJECT-LAB-07"
observed: "SCIM group updated; app role not yet visible"
workflowStatus: PENDING_VERIFICATION
owner: crm-application-owner
riskClass: HIGH
nextAction: "Read back app role and inspect group mapping"
dueAt: "2026-11-24T10:00:00+07:00"
verifiedAt: null
~~~

Đây chỉ là phiếu ví dụ. Khi sai lệch là **cấp quá quyền**, người trực cần ưu tiên chặn hoặc giảm scope theo runbook, thay vì chờ retry tự nhiên.

## 14. Audit trail, access review và chỉ số

Một access request có thể được xét lại nhiều tháng sau. Khi đó phải chứng minh: **ai yêu cầu, ai duyệt, quyền được duyệt cụ thể là gì, phiên bản chính sách nào áp dụng, lúc nào cấp, lúc nào đọc lại, khi nào hết hạn và ai thu hồi**.

### 14.1. Event audit tối thiểu

| Event | Dữ liệu quan trọng |
| --- | --- |
| REQUEST_SUBMITTED | requestId, requester, beneficiary, entitlement, scope, createdAt |
| POLICY_EVALUATED | sourceVersion, policyVersion, rule, result |
| APPROVAL_REQUESTED | approver role/owner, deadline, quyền và scope |
| APPROVAL_DECIDED | authenticated approver, decision, reason, decidedAt |
| PROVISION_REQUESTED | targetAccountId, action, correlationId, desired scope |
| PROVISION_ACKNOWLEDGED | API response class, retry count, time |
| ENTITLEMENT_VERIFIED | actual role/ACL/expiry, target, verifiedAt |
| EXPIRY_TRIGGERED | expiresAt, reason, target grants cần thu hồi |
| REVOCATION_VERIFIED | trạng thái hiệu lực cuối, verifiedAt |
| LIFECYCLE_CHANGED | JML eventId, sourceVersion, hành động hủy/thu hồi |
| EXCEPTION_OPENED/RESOLVED | target, owner, risk, deadline, closure evidence |

### 14.2. Ví dụ audit chuỗi sự kiện

~~~json
{
  "requestId": "AR-LAB-2026-0041",
  "subjectId": "EMP-LAB-017",
  "entitlementId": "CRM-Data-Export",
  "resourceScope": "TENANT-LAB-01/PROJECT-LAB-07",
  "requester": "EMP-LAB-017",
  "policyVersion": "iam-lab-v3",
  "sourceVersionAtApproval": 16,
  "approval": {
    "approver": "OWNER-CRM-LAB",
    "decision": "APPROVED",
    "decidedAt": "2026-11-23T10:00:00+07:00"
  },
  "provisioning": {
    "target": "crm-lab",
    "targetAccountId": "CRM-U-017",
    "result": "VERIFIED",
    "verifiedAt": "2026-11-24T09:02:00+07:00"
  },
  "expiry": "2026-12-01T09:00:00+07:00",
  "revocation": {
    "result": "VERIFIED",
    "verifiedAt": "2026-12-01T09:01:00+07:00"
  }
}
~~~

Đây là **bản ghi minh họa**, không phải kết quả đã chạy. Trong thực tế cần event log hoặc hệ lưu bằng chứng bảo vệ khỏi sửa trái phép và truy được **trạng thái trước/sau**; hạn chế lưu PII và không lưu password, raw PAT, access token, private key hoặc session cookie.

### 14.3. Access review không chỉ là nhấn nút xác nhận

Một đợt access review có thể kết luận:

- **KEEP:** quyền còn hợp lệ, tiếp tục tới lần rà soát sau.
- **REVOKE:** quyền không cần nữa; phải thực thi và readback.
- **REDUCE_SCOPE:** thu hẹp tenant/project, cập nhật grant thực tế.
- **REQUEST_EVIDENCE:** thiếu owner, business justification hoặc dữ liệu sử dụng quyền.

Đối với mọi quyết định **REVOKE**, cần nối từ reviewer decision tới **revocation job** và **verifiedAt**. Nếu reviewer đã từ chối quyền nhưng app vẫn cho phép sử dụng, chương trình access review chưa khắc phục được sai lệch.

### 14.4. Chỉ số theo dõi

| Chỉ số | Định nghĩa thực hành | Điểm cần chú ý |
| --- | --- | --- |
| **Request approval latency** | Thời gian từ SUBMITTED đến quyết định hợp lệ | Không gộp với thời gian provision |
| **Grant fulfillment latency** | Từ khi approved/đến mốc hiệu lực tới khi verified tại target | HTTP ACK chưa đủ |
| **Approval rejection rate** | Tỷ lệ yêu cầu bị từ chối theo policy/người duyệt | Nên phân nhóm lý do |
| **Excessive access rate** | Tỷ lệ target có quyền vượt scope/role được duyệt | Cần effective entitlement thực tế |
| **Expired grant count** | Quyền còn hiệu lực sau expiresAt | Không chỉ đếm ngày hết hạn trên request |
| **Mover stale entitlement** | Quyền cũ còn hiệu lực sau Mover và hạn xử lý | Kiểm tra cả direct grant |
| **Leaver outstanding requests** | Request pending/approved/provisioning chưa hủy hoặc đang cấp | Cần ngăn các job cũ |
| **Reconciliation drift** | Số sai lệch desired vs actual ở IdP/app | Phân biệt thiếu và thừa quyền |
| **Manual task overdue** | Task do app owner xử lý quá hạn | Đo cả khả năng đọc lại |
| **Exception remediation** | Tỷ lệ sai lệch đã thực sự xác minh khắc phục | Đóng ticket không thay verifiedAt |

Thiết kế mẫu số, thời điểm đo, phạm vi ứng dụng và SLA theo rủi ro. **Không có SLA chung** đúng cho mọi quyền, tổ chức hoặc ứng dụng.

## 15. Rubric chấm dự án và checklist bàn giao

Tự đánh giá theo thang **0–3**: **0** chưa có; **1** mới mô tả; **2** đã hiện thực nhưng chưa có kiểm chứng đầy đủ; **3** có kết quả, kiểm thử âm tính và bằng chứng rõ.

| Tiêu chí | Dấu hiệu đạt 3 điểm |
| --- | --- |
| **Request schema** | Trường có nguồn tin cậy, subjectId ổn định, scope, thời gian, idempotency |
| **Authentication/authorization portal** | Chặn gửi yêu cầu cho subject ngoài quyền; không tin client tự nhận vai trò |
| **Entitlement catalog** | Có role, owner, risk tier, TTL, policyVersion và đường revoke |
| **RBAC/ABAC** | Tính đúng quyền và giới hạn tenant/project; thiếu attribute thì không cấp |
| **Approval và SoD** | Chặn tự phê duyệt, owner sai, role xung đột và approval stale |
| **Provisioning** | Adapter thực thi đúng quyền, scope; có idempotency và readback |
| **JML hooks** | Joiner pre-hire, Mover reevaluate, Leaver chặn request và revoke |
| **Expiry/revocation** | Thu hồi thật, xử lý direct ACL/token và xác minh |
| **Lỗi phân tán** | Connector timeout/ACK chưa đồng bộ không tạo trạng thái FULFILLED giả |
| **Security tests** | Có ca từ chối IDOR, role injection, self-approval và cross-tenant |
| **Auditability** | Truy được request → decision → target → actual → revoke |
| **Tài liệu bàn giao** | Người khác có thể chạy dữ liệu giả và lặp lại bài test |

**Tổng tối đa minh họa: 36 điểm.** Đây là rubric tự học, không phải thước đo/chứng chỉ chính thức.

### 15.1. Checklist trước khi báo cáo hoàn thành

- [ ] Chỉ sử dụng dữ liệu giả và môi trường được phép.
- [ ] Requester lấy từ authenticated principal và được phép yêu cầu cho beneficiary.
- [ ] Client không thể tự đặt approver, approvalStatus, policyVersion hoặc verifiedAt.
- [ ] Entitlement được chọn từ catalog, đúng scope và TTL.
- [ ] RBAC/ABAC dựa trên nguồn có thẩm quyền, kiểm tra SoD.
- [ ] Quyền nhạy cảm được người có thẩm quyền **độc lập** duyệt.
- [ ] Trước khi grant hoặc retry, kiểm tra lại identity, sourceVersion và effectiveAt.
- [ ] Không provision khi request rejected, cancelled hoặc hết hạn.
- [ ] IdP/SSO không bị nhầm là nơi giữ mọi quyền ứng dụng.
- [ ] SCIM/API có mapping đúng user/group và kiểm tra role hiệu lực tại app.
- [ ] Có readback thực tế; API ACK không tự biến thành FULFILLED.
- [ ] Quyền chỉ có hiệu lực đúng scope/tenant/project; test ngoài phạm vi bị DENY.
- [ ] Expiry, Mover, Leaver và access review đều có trigger revoke.
- [ ] Thu hồi quyền từ mọi đường grant thuộc phạm vi, kể cả direct ACL.
- [ ] Token/session còn hiệu lực được kiểm tra theo khả năng ứng dụng.
- [ ] Retry/trùng request không tạo role hoặc account ngoài ý muốn.
- [ ] Leaver mới hơn chặn được grant từ request/Mover cũ.
- [ ] Lỗi connector hoặc manual task còn mở được gắn owner và deadline.
- [ ] Audit trail không chứa secret; có policy version, approver và verifiedAt.
- [ ] Có bộ test dương tính/âm tính và tài liệu giới hạn của mô phỏng.

### 15.2. Lỗi thiết kế thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Request tạo là cấp quyền ngay | Bỏ qua approval/SoD | State machine và quyền thực thi riêng |
| Approver ID do client gửi | Self-approval / leo thang quyền | Owner registry và authenticated approver |
| Lưu role mà không lưu resource scope | Vượt tenant/project | Entitlement + resource + action + context |
| Chỉ dùng nhóm IdP | Bỏ sót direct ACL và token | Reconciliation hai chiều ở app |
| APPROVED được ghi như hoàn tất | Cấp quyền có thể chưa chạy | Tách approval với verified fulfillment |
| Expiry chỉ là một cột trong database | Quyền vẫn còn sau hạn | Scheduler/revoker và readback |
| Request retry sau Leaver | Cấp lại cho người đã nghỉ | Source version check và điều phối an toàn |
| Mọi grant cùng entitlement là một cờ | Thu hồi request A làm mất quyền hợp lệ của request B | Theo dõi grant provenance và tính desired state hợp nhất |
| Thực thi kiểm tra quyền chỉ tại UI | API có thể bị gọi trực tiếp để vượt quyền | PEP/authorization tại backend |

**Điểm mở rộng quan trọng:** chương trình Java ở phần 8 coi một entitlement có một grant tương ứng. Nếu có **hai access request hợp lệ cùng cấp một entitlement**, khi request A hết hạn không được xóa quyền của request B nếu B vẫn còn căn cứ. Thiết kế production phải lưu **grant provenance** và tính quyền mục tiêu hợp nhất từ tất cả căn cứ còn hiệu lực, sau đó chỉ revoke đường grant khi không còn căn cứ nào phù hợp.

## 16. Bước mở rộng và tổng kết

Sau khi hoàn tất lab một entitlement, thử các yêu cầu nâng cao:

1. **Access package:** một request gồm CRM-Viewer và Finance-Report-Viewer, có trạng thái target riêng. Một target lỗi làm request PARTIAL, không FULFILLED toàn phần.
2. **Multi-stage approval:** manager xác nhận nhu cầu, chủ dữ liệu quyết định phạm vi, Security kiểm tra SoD; không cho requester can thiệp trình tự.
3. **Delegated request:** manager yêu cầu cho nhân viên, sponsor yêu cầu cho nhà thầu, Platform Owner yêu cầu cho workload; từng quan hệ được kiểm chứng từ nguồn tin cậy.
4. **Temporal policy:** quyền chỉ được mở sau effectiveAt và thu hồi sau expiresAt; xử lý scheduler trễ, dịch vụ restart và thời điểm có timezone.
5. **Grant provenance:** nhiều request cho cùng quyền, phân biệt quyền giữ hợp lệ với quyền cần thu hồi.
6. **Provisioning phân tán:** IdP group thành công nhưng SaaS role lỗi; retry/backoff, rate limit, idempotency và đối soát.
7. **Approver thay đổi:** owner chuyển bộ phận hoặc nghỉ việc trong lúc request chờ, workflow phải định tuyến lại người đủ thẩm quyền.
8. **JML race conditions:** event Mover cũ tới sau Leaver; approval cũ không làm sống lại quyền.
9. **Access review:** định kỳ chứng nhận quyền, chạy remediation khi owner yêu cầu revoke và kiểm tra verifiedAt.
10. **Service identity:** thay PAT cá nhân bằng workload identity có owner, scope/TTL và đường decommission.

### 16.1. Câu hỏi cuối dự án

Hãy tự trả lời:

- Một access request **được phê duyệt** khác gì với một entitlement **đã có hiệu lực**?
- Vì sao người tạo request không được tự đặt approver hoặc beneficiary tùy ý?
- Khi group SCIM đã được thêm nhưng app chưa thấy role, trạng thái đúng là gì?
- Nếu quyền hết hạn mà app vẫn còn direct ACL, bạn có thể ghi REVOKED không?
- Một người Mover hoặc Leaver khi request đang chờ, hệ thống phải làm gì trước retry?
- Nếu hai request cùng cấp một quyền, thu hồi một request có thể ảnh hưởng tới quyền hợp lệ còn lại thế nào?
- Bằng chứng nào đủ để người kiểm toán nối được requester, approver, policy, target và quyền thực tế?

### 16.2. Kết luận

Dự án **Tạo access request** cho thấy quản lý quyền không phải thao tác “thêm user vào group” đơn lẻ. Một luồng đáng tin phải giữ được quan hệ:

**Danh tính đáng tin → Nhu cầu và scope rõ → Policy RBAC/ABAC/SoD → Phê duyệt có thẩm quyền → Provision đúng target → Readback effective access → Thu hồi khi hết căn cứ → Kiểm toán.**

Trong IAM lifecycle, **Joiner** chuẩn bị quyền tối thiểu đúng thời điểm, **Mover** khiến các request và grant cũ phải được đánh giá lại, **Leaver** chặn request đang chờ và thu hồi quyền đã cấp. IdP/SSO hỗ trợ xác thực, SCIM/API hỗ trợ đồng bộ tài khoản và entitlement, còn đối soát giúp thấy **quyền thực tế** khác gì quyền được duyệt. Khi người học có thể minh họa cả **request thành công, bị từ chối, connector lỗi, quyền hết hạn và Leaver tới giữa quy trình** với bằng chứng xác minh, họ đã hoàn thành năng lực quan trọng nhất: **không chỉ tạo yêu cầu cấp quyền, mà còn kiểm soát được quyền từ lúc phát sinh đến lúc hết hiệu lực**.
