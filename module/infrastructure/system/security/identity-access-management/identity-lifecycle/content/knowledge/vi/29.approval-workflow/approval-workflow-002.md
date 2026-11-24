# Approver trong Approval workflow: người phê duyệt quyền truy cập trong IAM Identity Lifecycle

> **Chương: Approval workflow.** Trong hệ thống **Identity and Access Management (IAM)**, **Approver** là người hoặc vai trò được tổ chức ủy quyền **ra quyết định chấp thuận hoặc từ chối một yêu cầu truy cập trong phạm vi thẩm quyền được giao**. Approver có thể là quản lý trực tiếp, chủ sở hữu ứng dụng, chủ sở hữu dữ liệu, người chịu trách nhiệm bảo mật hoặc một cấp phê duyệt đặc quyền. Vai trò này khác với người nộp yêu cầu, người sẽ sử dụng quyền và hệ thống thực hiện provisioning. Trong vòng đời **Joiner–Mover–Leaver**, xác định **đúng approver, đúng phạm vi, đúng thời điểm và đúng bằng chứng** là điều kiện quan trọng để cấp quyền tối thiểu, điều chỉnh quyền khi chuyển việc và không cấp lại quyền đã thu hồi.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **Approver** là gì, phân biệt người yêu cầu (requester), người hưởng quyền (beneficiary), approver, entitlement owner, workflow operator và hệ thống thực thi.
2. Xác định **ai có thẩm quyền phê duyệt** theo resource, action, mức nhạy cảm, tenant, loại danh tính và giai đoạn Joiner–Mover–Leaver.
3. Thiết kế cơ chế **approver resolution**, fallback, delegation, nhiều cấp phê duyệt, quorum, timeout và escalation mà không mở cửa tự phê duyệt.
4. Áp dụng **Separation of Duties (SoD)**, chống xung đột lợi ích, giới hạn thẩm quyền và phê duyệt có thời hạn.
5. Hiểu quyết định phê duyệt là **đầu vào cho authorization/provisioning**, không tự tạo ra quyền thực tế hoặc thay thế xác thực và kiểm tra policy.
6. Liên kết người phê duyệt với **HR, IAM/IGA, IdP, SSO, SCIM, RBAC/ABAC, PAM**, tài khoản dịch vụ và sự kiện JML.
7. Thiết kế kiểm thử, nhật ký kiểm toán, xử lý trường hợp bất đồng bộ và đối soát **requested–approved–provisioned–effective access**.

## 1. Approver là gì?

Giả sử nhân viên Lan cần quyền đọc báo cáo ngân sách trong ứng dụng Finance. Lan có thể tự mở biểu mẫu và gửi yêu cầu, nhưng **việc Lan cần quyền không đồng nghĩa Lan được tự cấp quyền**. Workflow có thể chuyển yêu cầu tới chủ sở hữu dữ liệu Finance để xem xét:

- **Lan** là người được cấp quyền nếu chấp thuận (**beneficiary**).
- **Người gửi biểu mẫu** có thể là Lan hoặc một nhân viên hỗ trợ thay mặt Lan (**requester**).
- **Finance data owner** là **approver** được ủy quyền cho loại dữ liệu đó.
- **IAM/IGA workflow** quản lý trạng thái yêu cầu và kiểm tra quy tắc phê duyệt.
- **SCIM connector hoặc API của ứng dụng** thực thi việc cấp entitlement sau khi đủ điều kiện.
- **Ứng dụng Finance** quyết định và thực thi quyền khi Lan thực sự gọi API.

Vì vậy, Approver **ra quyết định nghiệp vụ có thẩm quyền** trong một workflow cụ thể; họ không phải thành phần mặc định thay thế mọi quy tắc security hoặc trực tiếp thao tác account.

### Một quyết định có phạm vi cụ thể

Một phê duyệt hợp lệ cần đủ các chiều:

| Chiều | Ví dụ | Câu hỏi của Approver |
| --- | --- | --- |
| **Beneficiary** | IAM:ID-LAN-2041 | Ai thực sự được nhận quyền? |
| **Resource** | FinanceReports tại tenant-b | Quyền tác động vào hệ thống và dữ liệu nào? |
| **Action/entitlement** | report.read, không phải report.export | Mức quyền đã yêu cầu có cần thiết không? |
| **Business justification** | Đối soát chi phí dự án P-17 | Mục đích hợp lệ và còn cần thiết không? |
| **Time window** | 01–31/12/2026 | Quyền cần có từ khi nào và trong bao lâu? |
| **Risk/SoD** | Dữ liệu tài chính nhạy cảm | Có xung đột nhiệm vụ hoặc rủi ro khác không? |
| **Approver authority** | Finance data owner của tenant-b | Người duyệt có thực sự chịu trách nhiệm phạm vi này không? |
| **Policy version** | policy-finance-v12 | Phê duyệt dựa trên chính sách nào? |

Một cái bấm **Approve** không có nghĩa cho phép mọi hành động cùng hệ thống, mọi tenant hoặc mọi thời gian. Khi scope thay đổi đáng kể, cần đánh giá lại điều kiện phê duyệt.

## 2. Phân biệt những vai trò thường bị nhầm

| Vai trò | Công việc | Không được mặc nhiên làm |
| --- | --- | --- |
| **Requester** | Tạo yêu cầu và cung cấp lý do. | Tự duyệt chỉ vì mình tạo yêu cầu. |
| **Beneficiary / subject** | Danh tính sẽ sử dụng quyền sau khi được cấp. | Tự thay đổi policy hoặc được phép trước khi workflow hoàn tất. |
| **Approver** | Chấp thuận/từ chối trong phạm vi được giao; nêu lý do khi cần. | Duyệt mọi tenant, mọi quyền hoặc vượt hard security guard. |
| **Line manager** | Xác nhận nhu cầu công việc và quan hệ quản lý. | Mặc nhiên quyết định mọi quyền dữ liệu nhạy cảm. |
| **Application owner** | Xác nhận quyền theo ứng dụng/entitlement thuộc sở hữu. | Mặc nhiên xác minh identity proofing hoặc phê duyệt ngoại lệ an ninh. |
| **Data owner** | Xác nhận quyền đối với tập dữ liệu và phân loại. | Tự bỏ qua SoD, legal hold hoặc policy bắt buộc. |
| **Security/PAM approver** | Đánh giá rủi ro và yêu cầu đặc quyền theo phạm vi. | Cấp toàn quyền thường trực chỉ vì một lần xử lý sự cố. |
| **Workflow administrator** | Cấu hình luồng, khắc phục lỗi và quản lý queue. | Dùng quyền quản trị để approve thay mọi owner không có ủy quyền. |
| **Provisioning connector** | Gửi thao tác tạo account/Group/role ở đích. | Tự quyết định ai nên có quyền ngoài chính sách. |
| **Policy Decision Point (PDP)** | Đánh giá chính sách runtime theo thuộc tính hiện hành. | Tự coi một approval cũ là Permit cho mọi request. |
| **Policy Enforcement Point (PEP)** | Chặn/cho phép tại API hoặc tài nguyên. | Bỏ qua kết quả phân quyền vì workflow từng báo APPROVED. |

Ví dụ: quản lý của Lan xác nhận Lan được phân công dự án P-17; nhưng quyền **đọc dữ liệu lương** có thể còn cần **data owner approval** và policy của Security. Hai quyết định đánh giá **hai điều kiện khác nhau**, không thể thay thế tùy ý.

### Approval khác access certification

- **Access request approval:** đánh giá một yêu cầu mới hoặc thay đổi quyền trước khi cấp.
- **Access certification/attestation:** đánh giá định kỳ quyền **đã tồn tại** còn cần hay không; reviewer có thể khác approver ban đầu.
- **Emergency approval:** quyết định theo workflow khẩn cấp có phạm vi, thời hạn và kiểm soát bù.
- **Authorization Permit:** kết quả quyết định khi dùng một quyền trên tài nguyên; phải kiểm tra policy và context.

Một người có thể đảm nhiệm nhiều vai trong tổ chức, nhưng hệ thống phải kiểm tra **độc lập chức năng và xung đột lợi ích** ở từng yêu cầu.

## 3. Các loại Approver thường gặp

| Loại Approver | Yêu cầu phù hợp | Điểm kiểm soát |
| --- | --- | --- |
| **Manager approver** | Quyền cơ bản liên quan nhiệm vụ nhân viên. | Xác minh quan hệ quản lý và nhu cầu công việc hiện tại. |
| **Entitlement owner** | Quyền thuộc một application role hoặc permission cụ thể. | Hiểu ý nghĩa quyền và scope được cấp. |
| **Application/system owner** | Account hoặc chức năng quản trị của ứng dụng. | Phạm vi ứng dụng và tenant; không phải mọi dữ liệu bên trong. |
| **Data owner/steward** | Truy cập dữ liệu nhạy cảm hoặc export. | Mức phân loại, mục đích, data minimization, thời hạn. |
| **Project/resource owner** | Quyền vào dự án, môi trường, repository hoặc namespace. | Đúng project, expiry và trách nhiệm. |
| **Security/IAM approver** | Quyền đặc quyền, ngoại lệ an ninh, policy risk. | SoD, least privilege, điều kiện MFA/PAM, hard guards. |
| **Service/workload owner** | Quyền API của bot/service principal. | Service purpose, environment, secret owner, token scope. |
| **Sponsor của contractor/vendor** | Quyền bên thứ ba có thời hạn. | Hợp đồng, trách nhiệm nội bộ, người bảo trợ, endAt. |
| **Compliance/legal approver** | Quyền chịu ràng buộc quy định hoặc legal process. | Chỉ trong phạm vi quy tắc tổ chức có quy định rõ. |

**Không có quy tắc chung rằng Manager luôn là approver cuối cùng.** Tổ chức phải lập **approval authority matrix** theo loại quyền và mức rủi ro.

### Ví dụ approval matrix

| Yêu cầu | Bước 1 | Bước 2 | Điều kiện bổ sung |
| --- | --- | --- | --- |
| Birthright entitlement ít rủi ro | Có thể cấp tự động theo policy. | Không cần người duyệt nếu chính sách cho phép. | Đúng JML, identity và điều kiện công việc. |
| Xem báo cáo dự án | Manager hoặc project owner theo policy. | Data owner nếu dữ liệu nhạy cảm. | Giới hạn project/tenant và endAt. |
| Xuất dữ liệu khách hàng | Manager xác minh nhu cầu. | Data owner phê duyệt. | Điều kiện compliance, export scope và logging. |
| Quyền quản trị sản xuất | Manager/resource owner. | Security/PAM approver độc lập. | SoD, JIT, MFA mạnh, session recording khi cần. |
| Quyền contractor | Internal sponsor. | Application/data owner theo mức rủi ro. | Hợp đồng còn hiệu lực, expiry không vượt endAt. |
| Workload deploy production | Service owner. | Platform/security owner theo policy. | Workload identity, môi trường, approval pipeline. |
| Emergency break-glass | Quy trình cấp cứu được phê duyệt sẵn. | Hậu kiểm và thông báo theo policy. | Scope, alert, tài liệu và giới hạn đặc biệt. |

Bảng chỉ minh họa cách phân công. Thực tế có thể dùng nhiều cấp khác nhau; không được dùng bảng làm căn cứ tự cấp quyền nếu tổ chức chưa phê duyệt.

## 4. Approver authority: thẩm quyền phải được xác minh

Một tài khoản có tên “Manager” hoặc “Admin” không tự chứng minh có quyền phê duyệt. **Approval authority** là quan hệ được quản trị giữa một danh tính và **phạm vi loại quyết định**, ví dụ:

~~~text
approverAuthority = {
    approverIdentityId,
    approvalType,
    resourceScope,
    tenantScope,
    maximumRiskLevel,
    validFrom,
    validUntil,
    delegationStatus,
    sourceVersion
}
~~~

Đây là mô hình khái niệm. Thẩm quyền có thể bắt nguồn từ:

- Sơ đồ quản lý nhân sự ở HR.
- Danh mục application/data/resource owner được quản trị.
- Chính sách IGA, phân quyền PAP hoặc quyền Workflow Approver.
- Quyết định ủy quyền hợp lệ, có thời hạn.
- Quy trình quản trị đặc quyền/bảo mật được phê duyệt.

### Những điều phải kiểm tra tại thời điểm bấm Approve

1. **Đúng identity:** người thao tác đã được xác thực và mapping với approverIdentityId.
2. **Còn hiệu lực:** approver không thuộc trạng thái TERMINATED hoặc SUSPENDED đối với nhiệm vụ duyệt.
3. **Đúng vai trò và scope:** thẩm quyền bao phủ đúng entitlement, resource, tenant, request risk.
4. **Độc lập theo SoD:** approver không phải người tự hưởng quyền hoặc có lợi ích xung đột theo policy.
5. **Đúng thời hạn:** quyền phê duyệt hoặc ủy quyền chưa hết hạn.
6. **Đúng authentication assurance:** loại quyết định nhạy cảm có thể yêu cầu xác thực lại/step-up.
7. **Đúng phiên bản yêu cầu:** scope, beneficiary, policy và approval route không bị thay đổi sau khi mở màn hình.
8. **Chưa hoàn tất:** yêu cầu chưa bị hủy, từ chối, hết hạn hoặc được quyết định hợp lệ.

**Không kiểm tra thẩm quyền chỉ lúc sinh approval task.** Trong thời gian task chờ duyệt, manager có thể chuyển bộ phận hoặc nghỉ việc; cần **kiểm tra lại ở thời điểm quyết định**.

### Identity và account mapping

~~~text
HR Manager        : HRIS:EMP-009
IAM Approver      : IAM:ID-009
IdP account       : issuer-a / sub-220
Workflow actor    : workflow-user-009

HR Beneficiary    : HRIS:EMP-2041
IAM Beneficiary   : IAM:ID-2041
Target SCIM user  : tenant-b / scim-user-881
~~~

Đây là các namespace riêng. Không so sánh bằng email hay displayName duy nhất để quyết định “approver không phải beneficiary”: một người có thể có nhiều admin account, email alias hoặc identity liên kết.

## 5. Approver được chọn như thế nào? Approver resolution

**Approver resolution** là quá trình tìm đúng người/nhóm có thẩm quyền nhận task từ **loại yêu cầu, entitlement, tài nguyên, owner, manager, rủi ro, tenant và policy phiên bản hiện hành**.

~~~mermaid
flowchart TD
    R["Request: beneficiary, action,<br/>entitlement, resource, tenant, endAt"] --> V["Validate identity + JML<br/>requester / beneficiary"]
    V --> P["Tìm policy approval<br/>theo entitlement + risk"]
    P --> S["Resolve authority<br/>manager / owner / security"]
    S --> C{"Nguồn + mapping<br/>đúng và đủ mới?"}
    C -->|Không| X["BLOCKED_RESOLUTION<br/>đưa về owner xử lý"]
    C -->|Có| D["SoD, scope, active status,<br/>delegation validity"]
    D --> E{"Có approver hợp lệ?"}
    E -->|Không| X
    E -->|Có| T["Tạo approval tasks<br/>đúng thứ tự/quorum"]
    T --> A["Approver xác thực,<br/>quyết định với request version"]
    A --> G["Aggregate decisions<br/>theo policy"]
    G --> F{"Đủ điều kiện approve?"}
    F -->|Có| W["Provision theo scope<br/>và kiểm tra readback"]
    F -->|Không| Z["DENIED / PENDING / EXPIRED<br/>không tự cấp quyền"]
~~~

### Các bước chọn người duyệt

1. Xác định **resource owner** và **entitlement owner** bằng ID từ danh mục có thẩm quyền.
2. Kiểm tra loại quyền cần **manager approval**, **owner approval**, **security approval** hoặc kết hợp.
3. Resolve từng vai trò thành **cá nhân đủ điều kiện** trong đúng tenant/phạm vi.
4. Loại bỏ beneficiary/requester hoặc người có xung đột theo SoD.
5. Áp ủy quyền hợp lệ nếu có, nhưng **không mở rộng scope** của người ủy quyền.
6. Kiểm tra người duyệt còn ACTIVE, còn chức trách và không vượt cấp độ rủi ro.
7. Sinh task kèm request version, deadline, policy version và evidence.
8. Nếu không resolve được, **không tự chọn bất kỳ manager nào hoặc tự approve**.

### Manager chain không phải cây luôn sạch

Dữ liệu HR có thể chứa:

- Manager ID rỗng cho CEO, account service hoặc vị trí đang trống.
- Manager đã Leaver nhưng HR chưa cập nhật.
- Chu kỳ quản lý A → B → A do dữ liệu lỗi.
- Manager và beneficiary là cùng một identity.
- Nhân viên matrix organization có nhiều quản lý dự án.
- Manager ở tenant/pháp nhân không được phê duyệt tài nguyên đích.

Cần **cycle detection, giới hạn độ sâu**, nguồn ưu tiên và lộ trình escalation có thẩm quyền. Không dùng mẹo “nếu manager trống thì requester tự approve”.

## 6. Quyền phê duyệt không phải quyền quản trị mọi thứ

Approver có thể **chấp thuận cấp quyền** mà không được trực tiếp thao tác tài khoản. Ngược lại, admin có thể quản trị workflow kỹ thuật mà **không có quyền quyết định nghiệp vụ**.

Ví dụ:

~~~text
Lan yêu cầu: CRM.CustomerExport trong tenant-b

Resource owner:
    được quyết định nghiệp vụ về quyền CustomerExport

Workflow operator:
    được sửa cấu hình notification, retry queue
    KHÔNG có mặc định quyền Approve thay resource owner

Provisioning service:
    được gọi SCIM/API theo service credential
    KHÔNG được tạo grant thiếu approval

CRM API:
    phải đánh giá quyền thực tế và resource policy
    không chỉ tin workflow state=APPROVED
~~~

**Nguyên tắc ủy quyền tối thiểu** áp dụng cho cả người phê duyệt: không cấp quyền rộng kiểu “Approve All Requests” chỉ để tiện cho người vận hành. Thẩm quyền có thể được giới hạn theo app, tenant, rủi ro, hành động và thời gian.

## 7. SoD: không tự duyệt và tránh xung đột lợi ích

**Separation of Duties (SoD)** là tập kiểm soát giúp tránh một người có quyền tự khởi tạo, tự phê duyệt và tự thực thi một hành động rủi ro, hoặc vừa tạo vừa duyệt cùng một giao dịch.

### Các trường hợp cần xem xét

| Trường hợp | Kiểm soát mong muốn |
| --- | --- |
| Beneficiary chính là approver của quyền nhạy cảm. | Từ chối self-approval, chuyển cấp duyệt độc lập. |
| Requester là approver, nhưng requester yêu cầu cho người khác. | Quyết định theo policy; với high risk có thể yêu cầu người duyệt độc lập. |
| Approver có nhiều tài khoản (normal/admin). | SoD đối chiếu theo **cùng IAM identity**, không chỉ username. |
| Approver và beneficiary là cùng người qua alias/tenant. | Resolve identity link và chặn nếu phạm vi SoD cấm. |
| Approver cũng là người thực thi cấp quyền bằng tay. | Tách nhiệm vụ hoặc kiểm soát bù/dual control tùy rủi ro. |
| Manager và resource owner trùng người. | Nếu chính sách yêu cầu **hai người độc lập**, một người không được tính hai phiếu. |
| Quyền cho phép sửa policy của hệ thống approval. | Cần hạn chế escalation và tự đổi route/phê duyệt. |

### Ví dụ vi phạm

~~~text
Request:
    requesterIdentity = ID-LAN-2041
    beneficiaryIdentity = ID-LAN-2041
    entitlement = GlobalAdmin

Resolved task:
    approverIdentity = ID-LAN-2041

Required:
    REJECT_APPROVER_ASSIGNMENT
    reroute to independent authorized approver
    do not treat login from admin-lan as a different human
~~~

### SoD tĩnh và động

- **Static SoD:** không được vừa giữ hai vai trò xung đột, ví dụ người cấp quyền và người kiểm soát mọi lần cấp đặc quyền của chính mình.
- **Dynamic SoD:** được giữ hai vai trò trong tổ chức nhưng không được thực hiện cả hai bước **trên cùng một request**, ví dụ requester và approver của cùng yêu cầu.

Không phải mọi workflow đều cần hai người phê duyệt. Nhưng nơi chính sách quy định độc lập, **quorum phải tính theo số người độc lập hợp lệ**, không phải số lần click hoặc số account.

## 8. Một hay nhiều Approver? Sequential, parallel và quorum

Workflow có thể có một người duyệt, nhiều người duyệt theo thứ tự hoặc nhiều người duyệt đồng thời.

| Kiểu | Cách hoạt động | Ví dụ | Rủi ro cần kiểm soát |
| --- | --- | --- | --- |
| **Single approver** | Một quyết định đủ khi thẩm quyền và policy đạt. | Truy cập dự án ít rủi ro. | Owner trống hoặc tự phê duyệt. |
| **Sequential** | Cấp 1 duyệt rồi mới mở task cấp 2. | Manager → data owner → Security. | Request thay đổi giữa các bước; cấp sau dựa vào snapshot cũ. |
| **Parallel, all-of** | Mọi approver bắt buộc đều cần chấp thuận. | Data owner và Security độc lập. | Người duyệt trùng, một người vắng mặt gây treo. |
| **Parallel, any-of** | Một trong nhóm có thẩm quyền duyệt là đủ. | Một trong các chủ sở hữu được ủy quyền của resource. | Phải chắc chắn mọi thành viên nhóm đều có authority tương đương. |
| **Quorum N-of-M** | Cần ít nhất N người hợp lệ, độc lập theo policy. | 2 trong 3 người thuộc hội đồng được giao. | Đếm duplicate accounts, approver hết authority, phiếu cũ. |
| **Risk-based route** | Route tăng khi quyền/rủi ro tăng. | Viewer: owner; Admin: owner + Security. | Phân loại sai risk để đi đường dễ. |

### Ví dụ sequential approval

~~~mermaid
sequenceDiagram
    actor Req as Requester
    participant WF as IGA / Workflow
    participant M as Manager
    participant O as Resource Owner
    participant S as Security Approver
    participant T as Target Application
    Req->>WF: Xin quyền production database.read
    WF->>WF: Resolve authority, SoD, scope và JML
    WF->>M: Task 1: xác minh nhu cầu công việc
    M-->>WF: Approve bước 1
    WF->>O: Task 2: xác minh dữ liệu và scope
    O-->>WF: Approve bước 2
    WF->>S: Task 3: xét rủi ro/đặc quyền
    S-->>WF: Approve bước 3
    WF->>WF: Revalidate policy, identity, approval versions
    WF->>T: Provision quyền được duyệt
    T-->>WF: Trạng thái kỹ thuật
    WF->>T: Readback quyền hiệu lực
    T-->>WF: Verified / partial failure
~~~

Một workflow nhiều cấp chỉ an toàn nếu nó nêu rõ **quy tắc từ chối, quorum, timeout, ai có thể ủy quyền và phiên bản yêu cầu**.

### Quy tắc tổng hợp phiếu

Ví dụ chính sách **all-of**:

~~~text
required = {managerApproval, dataOwnerApproval, securityApproval}

if any required decision == REJECTED:
    final = REJECTED
else if any required task is invalid, expired or untrusted:
    final = NOT_APPROVED
else if every required task == APPROVED:
    final = APPROVED
else:
    final = PENDING
~~~

Không dùng thuật toán trên cho mọi loại quorum; **any-of, N-of-M và các guard bắt buộc** cần logic riêng. Một phiếu “Approve” từ người thiếu thẩm quyền **không được tính vào quorum**.

## 9. Delegation: ủy quyền phê duyệt đúng phạm vi

Approver đi công tác hoặc nghỉ phép có thể cần **delegate** quyết định cho người khác. Ủy quyền phải là một quan hệ **có thể kiểm chứng**, không chỉ là chuyển tiếp email.

### Dữ liệu của một ủy quyền

~~~json
{
  "delegationId": "delegation-028",
  "delegatorIdentityId": "IAM:ID-OWNER-51",
  "delegateIdentityId": "IAM:ID-DEPUTY-62",
  "resourceScope": "finance-reports:tenant-b",
  "approvalTypes": ["REPORT_READ_ACCESS"],
  "maxRiskLevel": "MEDIUM",
  "validFrom": "2026-12-01T00:00:00+07:00",
  "validUntil": "2026-12-10T23:59:59+07:00",
  "approvedBy": "IAM:ID-GOVERNANCE-8",
  "status": "ACTIVE"
}
~~~

Đây là schema minh họa, không phải chuẩn SCIM hay API của một nhà cung cấp cụ thể. Giới hạn thời gian, scope và risk phải được so theo contract rõ, nhất là khi request có hiệu lực vượt thời hạn ủy quyền.

### Kiểm tra delegation

1. Người ủy quyền thực sự có authority gốc trong phạm vi yêu cầu.
2. Được phép ủy quyền **loại quyết định đó**; những phê duyệt đặc quyền có thể cấm delegation.
3. Người nhận ủy quyền còn ACTIVE, đã xác minh và không vi phạm SoD.
4. Không cấp phạm vi rộng hơn quyền của delegator và không vượt maxRiskLevel.
5. Trong thời hạn hợp lệ; chưa revoke; đúng nguồn/cấu hình được phê duyệt.
6. Có audit đồng thời về **actual actor** và **original authority/delegator**.
7. Không cho delegation lặp vô hạn hoặc tạo chuỗi vòng/đường tự phê duyệt.

**Không gán approve task cho mọi nhân viên trong team chỉ vì approver chính vắng mặt.** Nếu không có delegate hợp lệ, cần đi theo escalation route được phê duyệt.

### Delegator nghỉ việc giữa thời gian ủy quyền

Khi delegator mất authority vì Mover/Leaver, hệ thống cần đánh giá trạng thái delegation theo chính sách. Đừng mặc định delegated authority tồn tại vô hạn sau khi nguồn authority gốc bị rút. Tương tự, người nhận ủy quyền bị đình chỉ/Leaver không thể tiếp tục ra quyết định hợp lệ.

## 10. Escalation, SLA và trường hợp không có Approver

Một approval task có thể bị treo do manager vắng, thiếu owner, mất tích hợp IdP hoặc thời hạn chờ vượt SLA.

### Cách xử lý đúng

| Tình huống | Hành vi nên có |
| --- | --- |
| Approver không mở task đúng hạn | Nhắc việc; sau đó chuyển cấp theo escalation policy. |
| Manager không tồn tại/HR trống | Dừng auto-resolution và chuyển tới owner có thẩm quyền. |
| Resource owner đã Leaver | Tra cứu nguồn owner hiện hành, không tin danh sách cũ. |
| Người duyệt bị SUSPENDED | Không nhận quyết định; thay route theo policy. |
| Delegation hết hạn | Không cho delegate tiếp tục approve; reassign hợp lệ. |
| Task vượt deadline | Expire/cancel hoặc mở quy trình xét lại theo policy. |
| Requester yêu cầu urgent | Dùng luồng khẩn cấp được phê duyệt, không tự bỏ bước. |
| IdP/IGA không khả dụng | Không coi timeout là Approval; lưu trạng thái lỗi, phục hồi. |

**Auto-approve on timeout** là một anti-pattern nguy hiểm đối với quyền nhạy cảm. SLA là thời gian xử lý, không phải lý do để biến thiếu quyết định thành chấp thuận.

### Escalation không được tự nâng quyền

Ví dụ manager chưa duyệt sau 48 giờ. Workflow có thể chuyển task tới người thay thế được chỉ định hoặc cấp quản lý cao hơn theo cấu trúc HR đã xác minh. Nhưng “cấp cao hơn” **không mặc nhiên có quyền duyệt mọi dữ liệu**. Cần xác minh **approval type, tenant, resource scope và SoD** cho người nhận escalation.

### Phân biệt retry và escalation

- **Retry:** chạy lại thao tác kỹ thuật khi lỗi tạm thời, ví dụ gửi notification hoặc gọi API.
- **Escalation:** thay người/cấp chịu trách nhiệm ra quyết định theo chính sách.
- **Reassignment:** chuyển một task chưa hoàn tất cho approver có thẩm quyền khác.
- **Reapproval:** tạo quyết định mới vì request, policy, entitlement hoặc ngữ cảnh đã thay đổi.

Không dùng một sự kiện retry để tự tạo phiếu chấp thuận mới.

## 11. Quyết định Approve/Reject phải gắn với snapshot yêu cầu

**Điều approver nhìn thấy phải đúng với điều hệ thống dự định cấp.** Nếu request thay đổi sau khi người duyệt xem màn hình, không được mặc định phiếu cũ vẫn hợp lệ.

### Những dữ liệu cần được ràng buộc

| Trường | Vai trò |
| --- | --- |
| **requestId, requestVersion** | Chống xác nhận trên yêu cầu đã thay đổi. |
| **beneficiary identityId** | Đúng danh tính nhận quyền. |
| **resourceId, tenantId, environment** | Đúng tài nguyên và phạm vi. |
| **requested entitlement/actions** | Không cấp quyền rộng hơn phiếu đã duyệt. |
| **startAt/endAt** | Không tự kéo dài quyền sau quyết định. |
| **business justification** | Có căn cứ công việc và audit. |
| **risk classification** | Chọn đúng route và assurance. |
| **policyVersion/approvalRouteVersion** | Biết quy tắc đang được áp dụng. |
| **actor identity, authority source** | Ai quyết định và quyền duyệt từ đâu. |
| **decision time, reason code** | Kiểm toán và xử lý kháng nghị. |

### Ví dụ request thay đổi giữa hai cấp

~~~text
Request version 7:
    entitlement = REPORT_READ
    tenant = tenant-b
    endAt = 2026-12-31

Manager Approves version 7.

Requester sửa request:
    entitlement = REPORT_EXPORT_ADMIN
    endAt = 2027-12-31
Request version 8.

Không hợp lệ:
    tái sử dụng manager approval(version 7) cho version 8.

Hợp lệ:
    re-evaluate route, risk, policy;
    yêu cầu reapproval theo thay đổi có ý nghĩa.
~~~

**Approval binding** là ràng buộc phiếu với chính xác phạm vi đã xem. Có thể dùng transaction version, optimistic locking và request hash/fingerprint của dữ liệu quan trọng; không cần in dữ liệu nhạy cảm vào log.

## 12. Approved chưa đồng nghĩa Provisioned hoặc Effective

Một kết quả **APPROVED** chỉ nói rằng các điều kiện phê duyệt đã đạt tại thời điểm đánh giá. Nó **không chứng minh** connector đã cấp role đúng hoặc ứng dụng đã cho phép quyền đúng phạm vi.

~~~mermaid
flowchart LR
    R["REQUESTED<br/>cần quyền"] --> A["APPROVED<br/>đủ quyết định"]
    A --> P["PROVISIONING<br/>SCIM/API/PAM"]
    P --> O["OBSERVED<br/>role/group/credential"]
    O --> E["EFFECTIVE<br/>API/Resource Server"]
    E --> V["VERIFIED<br/>theo policy"]
    A --> F["CANCELLED / SUPERSEDED<br/>nếu dữ liệu đổi"]
    P --> X["PARTIAL_FAILURE<br/>readback chưa đạt"]
    O --> X
~~~

### Bốn lớp cần phân biệt

| Lớp | Câu hỏi | Ví dụ lỗi |
| --- | --- | --- |
| **Requested** | Người dùng yêu cầu gì? | Scope request không rõ hoặc beneficiary sai. |
| **Approved** | Những Approver có thẩm quyền đã chấp thuận đúng phạm vi chưa? | Tự duyệt, thiếu second approval, approval hết hạn. |
| **Provisioned/observed** | Tài khoản/role/Group ở đích đã cập nhật? | SCIM timeout, mapping nhầm User, duplicate grant. |
| **Effective access** | Subject thực sự có thể thực hiện những hành động nào? | Local role, session/token cũ hoặc policy resource khác kết quả. |

Ngay sau khi có đủ phiếu, workflow vẫn phải **revalidate lifecycle state, approval validity, policy, sourceVersion và SoD** trước khi gửi grant. Một Leaver có hiệu lực trong lúc chờ approval có thể khiến mọi phiếu trước đó không còn được dùng để cấp quyền.

### Không nhầm Approved với Permit

Một người được duyệt quyền report.read hôm nay nhưng hệ thống API vẫn phải kiểm tra:

- Chủ thể đã xác thực hợp lệ chưa?
- Access token có đúng audience/scope không?
- Resource có đúng tenant và classification được phép không?
- Entitlement còn hiệu lực hay đã bị thu hồi sau Mover/Leaver?
- Có điều kiện ABAC/PBAC bổ sung như session assurance hoặc hạn sử dụng không?

**Phê duyệt là bằng chứng nghiệp vụ cho cấp quyền, không thay thế kiểm soát authorization runtime.**

## 13. Approver trong Joiner: đúng người, đúng thời điểm

**Joiner** là quá trình xác minh một người mới, chuẩn bị identity/account và cấp quyền cần thiết khi quan hệ công việc có hiệu lực. Một approver có thể duyệt quyền **trước ngày làm việc** để chuẩn bị, nhưng việc cấp account và **cho phép dùng quyền nghiệp vụ** là những thời điểm khác nhau.

### Ví dụ onboarding

~~~text
HR startAt            : 2026-12-01T09:00:00+07:00
Identity createdAt    : 2026-11-27
Access request raised : 2026-11-28
Manager approvedAt    : 2026-11-28
Data owner approvedAt : 2026-11-29

Approved grant:
    report.read tenant-b
    activation not before HR startAt
    endAt <= contract/policy boundary
~~~

Ở ví dụ này, phiếu hợp lệ có thể được lưu trước ngày kích hoạt, nhưng **không tự cho phép truy cập report.read từ ngày 28/11**. Workflow phải kiểm tra startAt, identity proofing, account binding và policy trước khi làm cho entitlement có hiệu lực.

### Approver cần xác minh điều gì?

1. Beneficiary đã được liên kết đúng với HR identity, không trùng người khác.
2. Manager/project owner được resolve từ nguồn có thẩm quyền, không chỉ dựa trên email trong biểu mẫu.
3. Role và entitlement thực sự phục vụ vị trí **sắp bắt đầu**, không sao chép mọi quyền của người tiền nhiệm.
4. Quyền birthright có cần human approval hay có thể cấp tự động theo policy; không tạo gánh nặng duyệt không cần thiết.
5. Quyền nhạy cảm được data/application/security owner duyệt ở đúng scope và thời hạn.
6. Pre-provisioning account không khiến ứng dụng mở quyền quá sớm.
7. Yêu cầu bị hủy nếu Joiner bị hủy tuyển dụng, dời ngày bắt đầu hoặc proofing không đạt theo chính sách.

### Khi ngày làm việc bị thay đổi

Nếu HR lùi startAt, **approver decision có thể vẫn là bằng chứng nghiệp vụ**, nhưng điều kiện kích hoạt phải được tính lại theo ngày mới. Nếu job cũ vẫn sử dụng startAt cũ, người dùng có thể được cấp quyền sớm. Thiết kế nên mang **HR sourceVersion/effectiveAt** vào điều kiện provisioning và kiểm tra lại trước lúc cấp.

## 14. Approver trong Mover: quyền của beneficiary và quyền duyệt đều thay đổi

**Mover** không chỉ thay department của người xin quyền; nó có thể thay **manager, owner và thẩm quyền approver**. Vì vậy phải xử lý hai trục độc lập:

1. **Quyền mà một người được nhận:** sau Mover, entitlement cũ có thể không còn hợp lệ; entitlement mới cần được phê duyệt theo role và rủi ro mới.
2. **Quyền phê duyệt mà một người nắm giữ:** một approver chuyển khỏi team hoặc mất ownership không được tiếp tục duyệt các yêu cầu ngoài thẩm quyền mới.

### Ví dụ thay đổi vai trò

Lan chuyển từ Support sang Finance lúc 09:00:

| Đối tượng | Trước Mover | Sau Mover | Workflow cần làm |
| --- | --- | --- | --- |
| Lan — beneficiary | Được quyền SupportTicketAdmin. | Chỉ được xem FinanceReports theo role mới khi đủ điều kiện. | Thu hồi quyền Support, mở request Finance theo route mới. |
| Manager của Lan | Support Manager. | Finance Manager. | Resolve lại manager approver từ HR hiệu lực. |
| Project owner | Support Project Owner. | Finance Data Owner. | Gửi request tới owner đúng dữ liệu. |
| Lan — nếu cũng là approver Support | Được duyệt một nhóm yêu cầu Support. | Không còn chức trách đó. | Thu hồi authority và reassign task đang pending. |
| Token/Group cũ | Có SupportAdmin claim hoặc membership. | Không còn căn cứ. | Reconcile IdP/SCIM/app và kiểm tra quyền runtime. |

### Pending approval khi manager đổi

Giả sử một request được chuyển tới manager cũ lúc 08:00 nhưng đến 09:00 quan hệ quản lý đổi. Trước khi manager cũ bấm Approve, workflow phải **kiểm tra authority theo thời điểm chính sách yêu cầu**. Có thể:

- Hủy task cũ và sinh task mới cho manager hiện hành.
- Giữ quyết định đã hoàn thành của một bước nếu policy cho phép và scope chưa đổi, đồng thời kiểm tra bước tiếp theo.
- Yêu cầu **reapproval** nếu bản chất công việc, owner hoặc rủi ro đã thay đổi.

Không nên quy định cứng rằng mọi quyết định từ manager trước Mover đều vô hiệu hồi tố. **Quyết định đã hợp lệ tại thời điểm nó xảy ra là dữ liệu audit lịch sử**; việc nó có còn đủ làm căn cứ cấp quyền mới là một câu hỏi policy khác.

### Tránh cấp thêm quyền mà không thu hồi quyền cũ

Một workflow Mover chỉ approve FinanceReader, không xử lý SupportAdmin cũ, có thể tạo **privilege accumulation**. Quy trình nên tính **desired access** mới, lập kế hoạch thu hồi quyền không phù hợp và cấp quyền mới theo policy. Approver chỉ được chấp thuận scope mới, không thể làm các entitlement cũ tự trở nên hợp lệ.

## 15. Approver trong Leaver: người duyệt rời tổ chức và người nhận quyền rời tổ chức

**Leaver** có hai tác động cần xem riêng:

- **Beneficiary Leaver:** mọi phê duyệt chưa cấp hoặc chưa còn phù hợp phải bị chặn; quyền đã cấp phải được thu hồi theo chính sách.
- **Approver Leaver:** thu hồi **approval authority**, delegation và khả năng ra quyết định mới; các task chưa hoàn tất phải được định tuyến lại hợp lệ.

### Khi beneficiary nghỉ việc

~~~mermaid
flowchart TD
    L["HR Leaver hiệu lực<br/>identityId + sourceVersion"] --> A["Đánh dấu identity không còn đủ điều kiện"]
    A --> B["Cancel/supersede pending requests<br/>và chặn cấp entitlement mới"]
    B --> C["Thu hồi quyền đã provision<br/>IdP, SCIM, PAM, app API"]
    C --> D["Revoke/giới hạn session<br/>token và credential theo policy"]
    D --> E["Readback ở target<br/>và kiểm chứng effective access"]
    E --> F{"Đạt revocation boundary?"}
    F -->|Có| G["VERIFIED + audit"]
    F -->|Không| H["PARTIAL_FAILURE<br/>owner, retry, containment"]
~~~

**Approval đã hoàn thành không có quyền cao hơn Leaver guard.** Một worker provisioning nhận được phiếu Approved từ hôm qua phải kiểm tra trạng thái hiện tại trước khi cấp quyền hôm nay. Quyền còn được dùng qua JWT, cookie, PAT hoặc local admin phải được xử lý riêng.

### Khi approver nghỉ việc

1. Chặn đăng nhập và thu hồi quyền phê duyệt mới theo identity lifecycle.
2. Hủy/revoke delegation phụ thuộc authority đã mất theo chính sách.
3. Tìm task pending, chuyển tới approver mới có authority và độc lập.
4. Không chuyển task tự động cho beneficiary hoặc người dùng bất kỳ.
5. Giữ lịch sử các decision đã được đưa ra hợp lệ để phục vụ audit.
6. Với request chưa provision, revalidate policy, risk, owner và approvals trước khi cấp.
7. Chuyển ownership của dữ liệu/ứng dụng và không để queue mồ côi.

**Không xóa tất cả quyền người khác chỉ vì approver trước đây đã nghỉ việc.** Phải xem các grant đã được phê duyệt hợp lệ có tiếp tục cần thiết hay không; kiểm tra owner hiện hành, review và policy. Ngược lại, cũng không mặc định sử dụng mọi approval cũ vô thời hạn để tạo grant mới.

### Leaver với request đang chờ callback

~~~text
v44: Joiner creates request REQ-7
v45: Manager approves REQ-7
v46: Leaver makes beneficiary TERMINATED

Late callback:
    Resource owner approves REQ-7 based on stale email

Required:
    request REQ-7 must not provision new access
    callback rejected/superseded or recorded as ineffective
    workflow audits v46 lifecycle decision
~~~

**Từ chối provisioning sau Leaver là điều kiện an ninh**, không chỉ là thay đổi giao diện request sang trạng thái CANCELLED.

## 16. Các trường hợp đặc biệt: rehire, contractor, owner thay đổi

### Rehire

Khi một người được tuyển lại, identity và account cũ có thể được liên kết theo chính sách nhưng **lịch sử approval không tự khôi phục quyền**. Phải xét role mới, quản lý mới, scope và thời hạn hiện tại. Quyền admin hoặc exception ở lần làm việc trước không tự bật lại.

### Contractor/vendor

Đối với nhà thầu hoặc đối tác, **internal sponsor** thường chịu trách nhiệm chứng minh nhu cầu truy cập, còn application/data owner kiểm tra scope. Approver cần xác nhận:

- Hợp đồng và sponsor còn hiệu lực.
- Quyền chỉ áp dụng cho dự án, tenant hoặc dữ liệu được giao.
- EndAt không vượt thời hạn hợp đồng hoặc giới hạn policy.
- Có phương án thu hồi khi sponsor thay đổi, contractor kết thúc nhiệm vụ hoặc mất liên hệ.
- User bên ngoài được nhận diện riêng, không chia sẻ account không quy trách nhiệm.

### Owner/manager thay đổi

Owner rời team có thể tạo **orphan approval queue**. Hệ thống nên có nguồn owner registry, phiên bản cập nhật và quy trình chuyển owner; không dựa vào tên nhóm tĩnh trong email notification. Nếu không tìm được owner đáng tin, trạng thái phải là **RESOLUTION_BLOCKED**, không phải auto-approve.

## 17. Approver cho privileged access, PAM/JIT và break-glass

Quyền như **GlobalAdmin, ProductionDeploy, SecretRotate, DatabaseRoot** có mức rủi ro cao hơn quyền đọc tài liệu thông thường. Approval có thể cần:

| Kiểm soát | Ví dụ |
| --- | --- |
| Resource owner approval | Platform owner xác nhận thao tác production cần thiết. |
| Security/PAM approval | Xác nhận policy đặc quyền, SoD, nguyên tắc tối thiểu. |
| Just-in-Time (JIT) | Chỉ kích hoạt quyền trong khoảng thời gian cần thiết. |
| Just Enough Administration (JEA) | Chỉ cho phép lệnh/action được duyệt. |
| Phishing-resistant MFA/step-up | Xác thực lại với assurance phù hợp trước phiên admin. |
| Session logging/recording | Có bằng chứng về tác động, theo luật/chính sách. |
| Post-use review | Kiểm tra quyền đã hết hạn, session/credential đã được xử lý. |

### Approver không thể thay thế PAM

Một quyết định Approve GlobalAdmin trong 30 phút **không bảo đảm** PAM tự hết quyền sau 30 phút hoặc vô hiệu hóa session cloud đã phát. PAM/Resource Server phải áp hạn, thu hồi token/role/session theo khả năng và ghi kết quả. Không đánh dấu hoàn thành chỉ vì request được duyệt.

### Break-glass

Emergency access có thể cần luồng quyết định khác khi IdP/PAM hoặc quy trình approver thông thường không khả dụng. Nhưng đó phải là **quy trình đã được thiết kế và phê duyệt trước**, có scope tối thiểu, cơ chế xác thực khả dụng trong tình huống sự cố, alert và hậu kiểm.

**Không viết quy tắc:** “PDP hoặc approver timeout thì tự cấp admin”. Tính sẵn sàng không được mua bằng việc bỏ tất cả ràng buộc bảo mật.

### Revoke authority của privileged approver

Người từng được phê duyệt cấp quyền production nhưng đã chuyển vai trò cần bị gỡ thẩm quyền, kể cả khi họ vẫn có SSO account và còn thuộc một Group cũ. Approval workflow phải tính **effective approver authority**, không chỉ role claim tại thời điểm đăng nhập cũ.

## 18. Approver cho service account và workload identity

Danh tính máy không có HR manager trực tiếp theo nghĩa một nhân viên. Workflow cấp quyền cho một service principal hoặc workload phải dựa trên **service owner, platform owner, security policy và trust của workload**.

Ví dụ, một CI pipeline muốn có quyền triển khai production:

~~~text
Beneficiary        = workload:payments-deployer
Requester          = team:PaymentPlatform
ServiceOwner       = IAM:ID-SERVICE-OWNER
ResourceOwner      = PlatformProductionOwner
RequestedAction    = deploy.update
RequestedResource  = production/payments-namespace
Authentication     = workload federation / controlled identity
EndAt              = theo vòng đời service/grant
~~~

### Câu hỏi Approver cần trả lời

1. Workload có trong service registry và còn hoạt động không?
2. Service owner được ủy quyền và còn trách nhiệm không?
3. Deployment từ environment/trust source nào; có rủi ro staging sang production không?
4. Quyền có thể giới hạn theo namespace, repository, queue hay API audience không?
5. Credential có thể dùng federation/short-lived token thay secret dài hạn không?
6. Có approval riêng cho production deployment và phân tách nhiệm vụ khi cần không?
7. Quyền/credential sẽ được thu hồi thế nào khi dịch vụ decommission?

**Khi service owner con người nghỉ việc**, không tự hủy production bot đang chạy hợp lệ, nhưng phải chuyển owner, rà soát grants, rotate credential mà người ấy từng biết và thu hồi quyền cá nhân đã hết điều kiện. Approver mới cần được xác định từ **service ownership hiện hành**, không từ HR manager của account máy.

## 19. IdP/SSO, SCIM, RBAC/ABAC và Approval workflow

Một workflow duyệt quyền thường tích hợp nhiều hệ thống; mỗi hệ thống chỉ chứng minh một phần:

| Hệ thống/lớp | Tham gia thế nào? | Không chứng minh điều gì? |
| --- | --- | --- |
| **HR/source of truth** | Cho biết manager, trạng thái, ngày hiệu lực JML. | Manager có thẩm quyền duyệt mọi dữ liệu. |
| **IAM/IGA** | Quản lý identity mapping, requests, approvals, SoD, review. | Một Grant đã đến đích và quyền đã hội tụ. |
| **IdP/SSO (OIDC/SAML)** | Xác thực approver, cung cấp session/assurance. | Người đăng nhập có quyền duyệt mọi request. |
| **SCIM User/Group** | Đồng bộ account và membership ở SaaS. | Phiếu đã được duyệt đúng hoặc mọi local role đã hết hiệu lực. |
| **RBAC** | Gán role/permission cho approver và beneficiary. | Role đúng không tự vượt scope, tenant, SoD. |
| **ABAC/PBAC** | Đánh giá policy, thuộc tính, context và các guard bắt buộc. | Decision áp dụng ở mọi resource nếu thiếu PEP. |
| **PAM/PIM** | Quản lý activation của quyền đặc quyền và phiên. | Mọi token/credential cũ tự thu hồi ngay. |
| **Resource Server/App** | Thực thi quyền theo token, role và policy hiện hành. | Trạng thái approval ban đầu luôn đủ cho mọi request sau đó. |

### Approver phải xác thực nhưng cũng phải được ủy quyền

Ví dụ approver đăng nhập bằng SSO và MFA. Hệ thống phải **xác minh token/SSO session đúng issuer, subject, audience và ngữ cảnh** theo giao thức. Sau đó kiểm tra **entitlement/authority approver**, không dùng riêng một claim trong request do browser tự gửi.

Một ID token OIDC hoặc SAML assertion **không phải** giấy phép phê duyệt mọi entitlement. Authentication assurance cao giúp bảo vệ quyết định nhạy cảm, nhưng không thay thế authority/scope.

### SCIM không mang “approved” như bảo đảm toàn hệ thống

Khi yêu cầu đã được duyệt, SCIM connector có thể thêm User vào Group. Tuy nhiên:

- Local SCIM User ID có thể khác IAM identityId.
- Group có thể là dữ liệu tổ chức, không nhất thiết là quyền.
- App có thể có direct roles và local sessions bên ngoài SCIM.
- Token phát trước Mover/Leaver có thể chứa quyền cũ.

Workflow phải kiểm tra **đúng beneficiary/target Group/tenant**, rồi đối soát quyền sau khi provision, thay vì tự coi HTTP 200/204 là quyền đã đúng.

## 20. State machine và xử lý đồng thời cho approval task

Vòng đời request và vòng đời từng approval task cần được tách riêng.

### Các trạng thái request minh họa

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> PENDING_APPROVAL: Submit và validate
    PENDING_APPROVAL --> APPROVED: Đủ phiếu hợp lệ / policy đạt
    PENDING_APPROVAL --> REJECTED: Bị từ chối theo workflow policy
    PENDING_APPROVAL --> EXPIRED: Quá hạn / chính sách
    PENDING_APPROVAL --> CANCELLED: User/owner hủy hoặc Leaver
    PENDING_APPROVAL --> RESOLUTION_BLOCKED: Không tìm được approver đáng tin
    RESOLUTION_BLOCKED --> PENDING_APPROVAL: Resolve mới hợp lệ
    APPROVED --> PROVISIONING: Revalidate và gửi cấp quyền
    APPROVED --> SUPERSEDED: Request/JML/policy thay đổi
    PROVISIONING --> VERIFIED: Readback và quyền đạt yêu cầu
    PROVISIONING --> PARTIAL_FAILURE: Target chưa hội tụ
    PARTIAL_FAILURE --> VERIFIED: Reconcile thành công
    PARTIAL_FAILURE --> CANCELLED: Rút yêu cầu và xử lý thu hồi
    VERIFIED --> [*]
    REJECTED --> [*]
    EXPIRED --> [*]
    CANCELLED --> [*]
    SUPERSEDED --> [*]
~~~

Các tên là **state nội bộ minh họa**, không phải enum bắt buộc trong sản phẩm IGA. Một hệ thống có thể có trạng thái sâu hơn như PENDING_REASSIGNMENT, POLICY_REVIEW hoặc PARTIALLY_APPROVED.

### Rủi ro concurrency

| Race | Hậu quả có thể gặp | Kiểm soát |
| --- | --- | --- |
| Hai approver cùng bấm quyết định trên task. | Duplicate decisions hoặc overwrite. | Transaction/version check, terminal state và idempotency key. |
| Người duyệt bấm Approve đúng lúc requester sửa scope. | Approval áp vào quyền khác đã xem. | Request version/hash binding; reject stale decision. |
| Manager Mover khi task đang chờ. | Người không còn authority vẫn duyệt. | Revalidate JML/authority lúc commit. |
| Beneficiary Leaver khi request gần đủ phiếu. | Phát grant cho người đã nghỉ. | Leaver guard trước grant, version checks. |
| Duplicate callback/email action. | Task bị đếm nhiều phiếu. | Idempotent decision store, distinct identity count. |
| Async job cấp quyền sau khi request bị hủy. | Cấp lại quyền trái policy. | Recheck current state và sourceVersion ở worker. |
| API timeout sau khi cấp quyền. | Retry tạo quyền trùng hoặc báo thất bại sai. | Readback, idempotency, compensation. |

**Không chỉ khóa giao diện nút Approve** rồi giả định race đã hết. Server phải bảo vệ transaction và xác thực actor/authority trong mỗi yêu cầu quyết định.

## 21. Mô hình dữ liệu, pseudocode và API minh họa

### Request và decision được ràng buộc

~~~json
{
  "requestId": "REQ-801",
  "requestVersion": 7,
  "requesterIdentityId": "IAM:ID-2041",
  "beneficiaryIdentityId": "IAM:ID-2041",
  "entitlement": "FinanceReports.Read",
  "resourceRef": "finance-reports:tenant-b:project-17",
  "startAt": "2026-12-01T09:00:00+07:00",
  "endAt": "2026-12-31T23:59:59+07:00",
  "riskLevel": "MEDIUM",
  "policyVersion": "iga-access-v12",
  "approvalRoute": [
    {"step": 1, "approvalType": "MANAGER"},
    {"step": 2, "approvalType": "DATA_OWNER"}
  ],
  "status": "PENDING_APPROVAL"
}
~~~

Một quyết định:

~~~json
{
  "decisionId": "DEC-1901",
  "requestId": "REQ-801",
  "requestVersion": 7,
  "taskId": "TASK-902",
  "actorIdentityId": "IAM:ID-OWNER-51",
  "authorityType": "DATA_OWNER",
  "authorityRef": "finance-reports:tenant-b",
  "decision": "APPROVE",
  "reasonCode": "BUSINESS_NEED_VERIFIED",
  "decidedAt": "2026-12-01T08:45:00+07:00",
  "authenticationProfile": "APPROVED_POLICY_LEVEL",
  "correlationId": "request-801-step-2"
}
~~~

Đây là **mô hình dữ liệu minh họa**, không phải chuẩn API IAM/IGA. Các trường có thể khác trong sản phẩm thật. Không đưa mật khẩu, access/refresh token, cookie hoặc bí mật MFA vào decision record.

### Pseudocode kiểm tra khi Approver ra quyết định

~~~text
decideApproval(taskId, actorAuthn, submittedRequestVersion, action):
    actor = validateSessionAndResolveIamIdentity(actorAuthn)
    if actor is unresolved:
        return UNAUTHENTICATED_OR_DENIED

    with transactionalLock(taskId):
        task = loadCurrentApprovalTask(taskId)
        request = loadCurrentAccessRequest(task.requestId)

        if task is not PENDING or request is not PENDING_APPROVAL:
            return CONFLICT_OR_IDEMPOTENT_PRIOR_RESULT
        if submittedRequestVersion != request.version:
            return STALE_REQUEST_REAPPROVAL_REQUIRED

        beneficiary = loadTrustedLifecycle(request.beneficiaryIdentityId)
        approver = loadTrustedLifecycle(actor.identityId)
        if beneficiary is not eligible for requested access:
            cancelOrBlockRequest(request)
            return DENY
        if approver is not eligible to approve:
            reassignAccordingToPolicy(task)
            return DENY

        authority = resolveCurrentApprovalAuthority(
            actor.identityId, task.approvalType,
            request.resourceRef, request.entitlement, request.riskLevel
        )
        if not authority.validAt(now):
            return DENY
        if violatesSoD(actor, request, task.approvalPolicy):
            return DENY
        if not actorAuthn.meets(task.requiredAssurance):
            return REQUIRE_STEP_UP

        result = saveDecisionIdempotently(
            task, request.version, actor.identityId, action,
            authority.reference, policyVersion = currentPolicyVersion
        )
        updateAggregatedWorkflowState(request)
        writeImmutableAuditReference(result)
        return result
~~~

Pseudocode không mô tả chi tiết transaction isolation, distributed locks, đặc tả lỗi hay semantics một sản phẩm IAM. Trong triển khai thật, cần chống **TOCTOU** giữa authority validation và decision commit; nếu phụ thuộc bên ngoài không thể transaction cùng, dùng version/freshness contract và xử lý bù.

### Pseudocode cấp quyền sau đủ phiếu

~~~text
provisionApprovedRequest(requestId):
    request = loadCurrentRequestWithVersion(requestId)
    if request.status != APPROVED:
        return NO_ACTION

    current = loadCurrentTrustedLifecycle(request.beneficiaryIdentityId)
    if current is not eligible or request.endAt <= now:
        markSupersededAndBlockGrant(request)
        return DENY

    approvals = loadAllDecisionsBoundTo(request.id, request.version)
    if not quorumAndIndependentAuthoritySatisfied(approvals, request):
        return DENY
    if not allMandatorySecurityGuardsSatisfied(request, current):
        return DENY

    scope = intersect(
        request.approvedEntitlementsAndResourceScope,
        currentAllowedPolicyScope
    )
    if scope empty:
        return DENY

    outcome = applyIdempotentTargetGrant(
        beneficiaryTargetMapping = verified,
        scope = scope,
        validUntil = min(request.endAt, current.contractEndAt)
    )
    observed = readBackTargetEntitlements(outcome)
    auditWithoutSecrets(request, approvals, outcome, observed)
    return VERIFIED if observed matches scoped grant else PARTIAL_FAILURE
~~~

**Quan trọng:** Nếu beneficiary là workload, thay phần lifecycle của HR bằng **vòng đời workload/service registry** và kiểm tra approval theo service owner. Không dùng máy móc employmentStatus của một user bất kỳ làm điều kiện tồn tại của service principal.

## 22. Kiểm toán và chỉ số của Approver

### Bằng chứng nên lưu

| Dữ liệu | Mục đích |
| --- | --- |
| Request ID/version, approval task ID | Truy vết quyết định trên đúng yêu cầu. |
| Requester, beneficiary và actor identityId | Phân biệt ai xin, ai hưởng, ai duyệt. |
| Entitlement/resource/tenant/time window | Chứng minh phạm vi thực sự được phê duyệt. |
| Approver type, authority source/version | Chứng minh người duyệt có thẩm quyền. |
| Delegator/delegate, delegation ID | Kiểm toán quyết định được ủy quyền. |
| SoD/independence/quorum result | Ngăn tự duyệt và đếm phiếu trùng người. |
| Authentication assurance/reauthentication context | Xác định mức bảo vệ quyết định. |
| Decision, reason, decidedAt | Giải thích chấp thuận/từ chối. |
| Policy version, approval route version | Tái dựng quy tắc tại thời điểm duyệt. |
| HR/JML sourceVersion, effectiveAt | Bảo đảm decision và grant gắn với lifecycle. |
| Provisioning/readback result | Đo khoảng cách giữa approved và effective access. |
| Correlation ID và owner | Nối sự kiện giữa IGA, IdP, SCIM, ứng dụng. |

### Ví dụ sự kiện audit

~~~json
{
  "eventType": "IAM_ACCESS_APPROVAL_DECISION",
  "requestId": "REQ-801",
  "requestVersion": 7,
  "taskId": "TASK-902",
  "actorIdentityId": "IAM:ID-OWNER-51",
  "beneficiaryIdentityId": "IAM:ID-2041",
  "entitlement": "FinanceReports.Read",
  "resourceRef": "finance-reports:tenant-b:project-17",
  "authorityType": "DATA_OWNER",
  "authoritySourceVersion": 33,
  "decision": "APPROVE",
  "policyVersion": "iga-access-v12",
  "sodResult": "PASS",
  "decisionAt": "2026-12-01T08:45:00+07:00",
  "correlationId": "request-801-step-2"
}
~~~

Log minh họa không phải schema chuẩn. Với thông tin HR, lý do cấp quyền hoặc metadata nhạy cảm, áp **data minimization, access control, retention và bảo vệ tính toàn vẹn**. Không log nội dung bearer token, session cookie, mật khẩu, seed MFA hoặc secret.

### Chỉ số cần quan sát

| Chỉ số | Giúp phát hiện |
| --- | --- |
| **Approval turnaround time** | Yêu cầu bị tắc ở bước/người duyệt nào. |
| **Overdue approval tasks** | SLA chậm, route hoặc owner không phù hợp. |
| **Orphan task/owner count** | Task không có approver hợp lệ do dữ liệu manager/owner thiếu. |
| **SoD violation attempts** | Thử tự duyệt hoặc người duyệt không độc lập. |
| **Delegation usage/expiry violations** | Ủy quyền quá hạn hoặc vượt scope. |
| **Stale authority decisions blocked** | Manager/owner đã Mover/Leaver vẫn cố duyệt. |
| **Reapproval rate** | Tần suất request hoặc policy đổi trước khi grant. |
| **Approval without verified provisioning** | Phiếu đã duyệt nhưng cấp quyền đích chưa xác minh. |
| **Provisioned without required approval** | Đường cấp entitlement bypass workflow. |
| **Approved access after beneficiary Leaver** | Lệnh cấp dựa trên phiếu cũ sau offboarding. |
| **Privileged approval compliance** | Đủ multi-level approval, SoD, MFA/JIT hay không. |
| **Residual access after revoke** | Token/role/session vẫn dùng được sau ngày phải thu hồi. |

**Tỷ lệ approve cao không phải KPI chất lượng đơn lẻ.** Nếu tất cả yêu cầu đều được duyệt trong vài giây mà không có kiểm tra nhu cầu, scope, SoD, đó có thể là dấu hiệu phê duyệt hình thức.

## 23. Kiểm thử Approval workflow và Approver

Một bộ test phải kiểm tra **authority, policy, request version, JML, xung đột và việc cấp quyền thực tế**. Dùng identity và hệ thống thử nghiệm trong phạm vi được phép, không cần thử tài khoản người thật ngoài quyền.

### Ma trận kiểm thử

| ID | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| AP-01 | Manager ACTIVE, đúng scope, beneficiary hợp lệ. | Phiếu manager được ghi nhận trong request version đúng. |
| AP-02 | Người dùng không có approval authority cố bấm Approve. | Bị từ chối, không tăng quorum. |
| AP-03 | Beneficiary tự duyệt quyền GlobalAdmin qua account phụ. | SoD chặn theo IAM identity, không chỉ username. |
| AP-04 | Manager và data owner là cùng một người, policy cần hai cá nhân. | Không tính hai phiếu độc lập. |
| AP-05 | Delegation hợp lệ, đúng resource/tenant/time. | Delegate được quyết định, audit cả delegator và actor. |
| AP-06 | Delegation hết hạn hoặc delegator mất authority. | Không cho duyệt; route lại. |
| AP-07 | Không tìm được owner vì dữ liệu thiếu. | RESOLUTION_BLOCKED; không auto-approve. |
| AP-08 | Task quá hạn SLA, không có phản hồi. | Escalate/expire theo policy; không tự cấp quyền. |
| AP-09 | Request đổi từ read sang export sau phiếu đầu tiên. | Old decision không dùng cho request version mới. |
| AP-10 | Manager Mover trước khi quyết định pending task. | Authority revalidated và reassignment khi cần. |
| AP-11 | Approver Leaver giữa workflow. | Không ra decision mới; task định tuyến lại. |
| AP-12 | Beneficiary Leaver sau khi đã có một phiếu Approve. | Không cấp quyền mới; pending request bị chặn. |
| AP-13 | Joiner request được duyệt trước startAt. | Không có business access trước ngày kích hoạt hợp lệ. |
| AP-14 | Mover sang Finance, SupportAdmin cũ còn ở SaaS. | Phát hiện và thu hồi quyền cũ; không chỉ cấp quyền mới. |
| AP-15 | Rehire có lịch sử approve của lần làm trước. | Không tự phục hồi entitlement/grant cũ. |
| AP-16 | Contractor endAt trước requested endAt. | Scope/time bị giới hạn hoặc từ chối theo policy. |
| AP-17 | Workload không có service owner hợp lệ. | Không tự chọn HR manager ngẫu nhiên hoặc approve. |
| AP-18 | Quyền admin thiếu Security/PAM approval. | Không provision privileged entitlement. |
| AP-19 | Có các phiếu Approve nhưng hard SoD/tenant guard không đạt. | Không cấp hoặc sử dụng quyền trái policy. |
| AP-20 | Hai callback giống nhau cho cùng task. | Một quyết định hợp lệ, không đếm phiếu trùng. |
| AP-21 | Hai quyết định trái chiều cùng gửi trong race. | Transaction xác định kết quả nhất quán; không overwrite terminal state. |
| AP-22 | Request bị cancel nhưng job provisioning cũ retry. | Không tái cấp entitlement. |
| AP-23 | SCIM/API báo cấp thành công nhưng Group/role sai User. | Không VERIFIED; sửa mapping và thu hồi sai. |
| AP-24 | Session JWT còn quyền cũ sau Leaver. | Kiểm thử effective access theo revocation policy. |
| AP-25 | PDP/IdP/IGA bị timeout trong phê duyệt đặc quyền. | Không fallback sang Permit/Approve tất cả. |
| AP-26 | Approver có MFA thông thường nhưng policy đòi phishing-resistant step-up. | Chưa được quyết định cho đến khi đạt yêu cầu. |
| AP-27 | Một approver chỉ được duyệt tenant A cố duyệt tenant B. | Bị từ chối theo authority scope. |
| AP-28 | Thay đổi policy version trước provisioning. | Revalidate, reapproval hoặc block theo chính sách. |

### Given–When–Then

~~~gherkin
Feature: Approver decisions are authorized and lifecycle-aware

  Scenario: Approved request is not granted before Joiner activation
    Given a verified Joiner is pending activation
    And the manager and resource owner approved a valid access request
    When the workflow attempts to provision the access
    Then no business access becomes effective before the approved start time
    And the grant is revalidated against current lifecycle

  Scenario: Beneficiary cannot approve own privileged access
    Given a user requested GlobalAdmin for the same IAM identity
    And the user signs in through a second administrator account
    When the user attempts to approve the task
    Then the decision is rejected by separation of duties
    And the task is not counted toward approval quorum

  Scenario: Leaver blocks stale approved provisioning
    Given an access request was fully approved at version 7
    And an authoritative Leaver event for the beneficiary became effective
    When an old provisioning job retries
    Then no new entitlement is granted
    And the workflow audits the lifecycle policy decision

  Scenario: Changed request requires reevaluation
    Given a data owner approved report.read at request version 7
    And the requester changed the entitlement to report.export at version 8
    When the workflow evaluates version 8
    Then the old approval cannot authorize report.export
    And the new approval route is evaluated
~~~

### Test không dừng ở HTTP status

Trong một test Approve bị từ chối, cần xác nhận:

- Không có decision hợp lệ được ghi sai vào quorum.
- Không có entitlement/Group/role hoặc admin session được cấp ở đích.
- Log phản ánh lý do đã từ chối nhưng không rò rỉ dữ liệu nhạy cảm.
- Job retry hoặc callback đến muộn không thể biến request thành Approved.
- Nếu lệnh đã được gửi trước khi chặn, đối soát và thu hồi những thay đổi trái phép.

**Một HTTP 403 không đủ** nếu database/workflow đã ghi Approve hoặc connector đã cấp quyền trước khi trả lỗi.

## 24. Tình huống thực hành

### Tình huống A — Manager tự duyệt quyền của mình

**Bối cảnh:** Lan là quản lý một nhóm và gửi yêu cầu GlobalAdmin cho chính mình. Workflow lấy managerId của Lan nhưng dữ liệu HR cấu hình Lan tự quản lý, nên task được giao lại cho Lan.

**Câu hỏi:** Cần xử lý thế nào?

**Gợi ý:** Phát hiện self-manager/SoD theo IAM identity; không cho self-approve. Chuyển tới cấp độc lập có authority theo policy hoặc đưa vào exception review. Không tự approve vì manager chain lỗi.

### Tình huống B — Manager vừa đổi sau Mover

**Bối cảnh:** Request của Minh gửi cho manager Support ngày 01/12, nhưng Minh chuyển sang Finance ngày 02/12. Manager cũ bấm duyệt vào ngày 03/12.

**Câu hỏi:** Phiếu còn hiệu lực không?

**Gợi ý:** Tùy authority/effectiveAt và policy. Trước khi commit, phải kiểm tra manager hiện hành, request scope và route; có thể cần reassignment/reapproval. Không dùng quan hệ quản lý cũ chỉ vì task đã được gửi email.

### Tình huống C — Hai cấp Approve nhưng chỉ một người

**Bối cảnh:** Policy yêu cầu approval từ manager và data owner độc lập. Cùng một người nắm cả hai vai và bấm Approve hai lần.

**Câu hỏi:** Quorum đã đạt chưa?

**Gợi ý:** Nếu policy yêu cầu hai **cá nhân độc lập**, chưa đạt. Workflow phải tính theo distinct verified IAM identities, không theo số task/role/account.

### Tình huống D — Ủy quyền vượt phạm vi

**Bối cảnh:** Data owner ủy quyền duyệt REPORT_READ tenant B cho người thay thế, nhưng delegate dùng phiếu này để duyệt REPORT_EXPORT_ADMIN tenant A.

**Câu hỏi:** Lỗi ở đâu?

**Gợi ý:** Delegation vượt action, tenant và risk. Phải xác minh scoped authority tại thời điểm quyết định; không chỉ kiểm tra delegationId tồn tại.

### Tình huống E — Approved trước khi HR hủy Joiner

**Bối cảnh:** Một người mới đã được manager và app owner duyệt quyền, nhưng HR hủy ngày nhận việc sau đó. Provisioning job chạy lại từ queue.

**Câu hỏi:** Có được cấp quyền theo phiếu cũ không?

**Gợi ý:** Không. Revalidate lifecycle/sourceVersion trước grant; approval lịch sử không thắng trạng thái Joiner bị hủy.

### Tình huống F — SaaS Group cập nhật nhưng quyền chưa đúng

**Bối cảnh:** Request có đủ approval và SCIM trả 204, nhưng User tại CRM vẫn còn role khác do cấp trực tiếp, hoặc Group được thêm cho nhầm User có email trùng.

**Câu hỏi:** Có thể đánh dấu VERIFIED không?

**Gợi ý:** Không. Phải resolve local User ID/tenant đúng, readback Group và role, xác minh effective permission. Trạng thái có thể là PARTIAL_FAILURE hoặc MAPPING_CONFLICT.

### Tình huống G — Approver nghỉ việc giữa workflow

**Bối cảnh:** Resource owner nghỉ việc sau khi duyệt một bước; những request khác đang pending ở queue của họ.

**Câu hỏi:** Phải xóa toàn bộ approval lịch sử không?

**Gợi ý:** Không xóa bằng chứng hợp lệ hồi tố. Thu hồi authority cho tương lai, reassign task pending, revalidate grant chưa provision theo policy và thay owner registry.

### Tình huống H — Request quyền máy không có manager HR

**Bối cảnh:** Một service account muốn quyền deploy namespace production. Workflow không có managerId nên chọn default IT director và tự tạo task.

**Câu hỏi:** Đây có phải route an toàn?

**Gợi ý:** Không nếu director không được giao authority cho workload. Cần service owner/resource owner và security route theo environment, scope, trust và policy.

### Tình huống I — Deadline Approver bị bỏ qua

**Bối cảnh:** Yêu cầu admin không có người phản hồi trong 48 giờ. Một quy tắc auto-approve được thiết kế để đạt SLA.

**Câu hỏi:** Tại sao đây là rủi ro?

**Gợi ý:** Timeout không phải bằng chứng đủ điều kiện cấp đặc quyền. Nên gửi nhắc/escalate có kiểm soát hoặc expire; không biến sự vắng mặt thành chấp thuận.

### Tình huống J — Emergency production outage

**Bối cảnh:** Hệ thống quản lý approval không hoạt động khi đội vận hành cần khôi phục production.

**Câu hỏi:** Có nên cấp GlobalAdmin không hạn cho mọi kỹ sư?

**Gợi ý:** Không. Dùng quy trình break-glass đã được phê duyệt, người được chỉ định, scope nhỏ, credential/session được bảo vệ, alert và hậu kiểm độc lập.

## 25. Câu hỏi tự kiểm tra

**1. Approver và requester khác nhau thế nào?**

Requester tạo yêu cầu; Approver ra quyết định trong phạm vi authority được giao. Một người có thể mang nhiều vai, nhưng phải kiểm tra SoD trước khi duyệt.

**2. Vì sao manager không mặc nhiên là approver mọi entitlement?**

Manager xác nhận nhu cầu công việc nhưng data/application owner hoặc Security có thể là bên có thẩm quyền đối với dữ liệu/quyền đặc thù.

**3. Có thể xác định approver chỉ bằng email không?**

Không nên. Email có thể đổi hoặc trùng; cần identityId, issuer/account mapping và nguồn authority đáng tin.

**4. Vì sao phải kiểm tra lại thẩm quyền ở thời điểm Approve?**

Vì manager/owner có thể Mover, Leaver, bị đình chỉ hoặc hết delegation trong lúc task chờ.

**5. Hai phiếu của hai tài khoản có luôn tính là hai approver độc lập không?**

Không. Hai account có thể thuộc cùng một IAM identity; quorum theo số người độc lập phải kiểm tra identity link và SoD.

**6. Delegation có thể cho người nhận quyền lớn hơn delegator không?**

Không theo nguyên tắc phạm vi được giao. Cần kiểm tra action, tenant, risk, thời hạn và approval policy cụ thể.

**7. Task quá SLA có được mặc định approve không?**

Không. Quá hạn cần nhắc, escalate hoặc expire theo workflow; thời gian chờ không tạo ra thẩm quyền.

**8. Vì sao requestVersion quan trọng khi Approve?**

Để bảo đảm người duyệt xác nhận đúng entitlement, resource, beneficiary, scope và thời hạn đã nhìn thấy, không bị áp vào request được sửa sau đó.

**9. Approved có chứng minh SCIM Group đã được thêm đúng User không?**

Không. Cần provisioning và readback tại ứng dụng, đúng local User ID và tenant.

**10. Sau Mover, điều gì xảy ra với một approver không còn là resource owner?**

Thu hồi authority ngoài phạm vi mới, định tuyến lại pending tasks, revalidate quyết định mới và quản trị quyền lịch sử theo policy.

**11. Khi beneficiary Leaver sau khi request đã APPROVED nhưng trước provisioning thì sao?**

Không cấp quyền; cần áp lifecycle guard mới nhất và đánh dấu superseded/cancel theo policy, xử lý mọi grant đã lỡ cấp.

**12. Khi approver Leaver, có phải xóa mọi approval họ từng đưa ra không?**

Không. Decision hợp lệ trước đây có thể cần giữ làm bằng chứng. Nhưng quyền ra quyết định mới bị thu hồi và grant chưa provision phải được đánh giá lại khi cần.

**13. Approver cho service principal nên tìm từ đâu?**

Từ service/workload registry, service owner, resource owner và chính sách Security, không tự tìm HR manager của một tài khoản máy.

**14. Vì sao MFA mạnh chưa đủ để cho phép một người approve?**

MFA xác thực người dùng; approval còn đòi quyền phê duyệt, scope, SoD, policy và trạng thái vòng đời hợp lệ.

**15. Quorum N-of-M nên đếm điều gì?**

Số người/quyết định hợp lệ, độc lập theo policy, trong đúng scope và request version; không đơn thuần đếm số lần bấm nút.

**16. Khi nào cần reapproval?**

Khi beneficiary, entitlement, risk, resource, thời hạn, approval policy hoặc các điều kiện có ý nghĩa thay đổi tới mức phiếu cũ không còn đủ căn cứ.

**17. Approver duyệt quyền production trong 30 phút có tự đảm bảo token hết hạn sau 30 phút không?**

Không. PAM/target phải thực thi TTL, token/session controls và readback theo chính sách.

**18. Dấu hiệu nào cho biết workflow chỉ duyệt hình thức?**

Tự duyệt, không kiểm SoD, approver không biết scope, mọi task auto-approve, thiếu authority evidence hoặc không xác minh quyền thực tế.

## Ghi nhớ

- **Approver** là danh tính/role được ủy quyền **quyết định yêu cầu trong phạm vi cụ thể**, khác requester, beneficiary, workflow admin và provisioning connector.
- **Chọn đúng người duyệt** cần dựa trên nguồn manager/resource/data owner đáng tin, approval matrix, tenant, entitlement, rủi ro và thẩm quyền còn hiệu lực; thiếu owner thì **không tự approve**.
- **SoD, chống self-approval, quorum độc lập, delegation có scope/time và escalation đúng authority** là các kiểm soát cốt lõi.
- **Decision phải gắn với request version, beneficiary, entitlement, resource, thời hạn, policy và actor**; khi các điều kiện thay đổi đáng kể phải đánh giá lại thay vì tái sử dụng phiếu cũ.
- **Joiner** có thể được duyệt trước nhưng không mở quyền sớm; **Mover** phải xét lại entitlement và authority của approver; **Leaver** phải chặn cấp quyền mới, thu hồi quyền đang có và chuyển task pending.
- **IdP/SSO xác thực, IGA quản trị approval, SCIM/PAM provisioning và RBAC/ABAC/PEP cưỡng chế quyền** là các trách nhiệm khác nhau. **Approved không đồng nghĩa Provisioned hoặc Effective**.
- **Readback, idempotency, sourceVersion, audit và kiểm thử các tình huống race/JML** giúp giữ quyết định phê duyệt có căn cứ và giảm quyền truy cập tồn dư xuyên suốt vòng đời danh tính IAM.
