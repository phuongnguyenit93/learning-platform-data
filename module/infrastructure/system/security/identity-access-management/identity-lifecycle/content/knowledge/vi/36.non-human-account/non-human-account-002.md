# Robot account – quản trị tài khoản robot trong vòng đời danh tính IAM

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích **robot account** trong nhóm **Non-human account**, phân biệt tài khoản robot chạy **Robotic Process Automation (RPA)** với người dùng thật, service account, workload identity, API client và tài khoản đặc quyền.
- Phân biệt **attended robot** (có người điều khiển) và **unattended robot** (chạy không cần người hiện diện), hiểu ai là chủ thể thực hiện, ai chịu trách nhiệm và quyền nào phải được kiểm tra.
- Thiết kế đăng ký **robot identity** với owner, sponsor, purpose, process ID, environment, target systems, permissions, credential reference, thời hạn và evidence.
- Nêu nguyên tắc sử dụng **IdP/SSO, MFA, credential vault, PAM, SCIM, RBAC/ABAC/PBAC** cho robot tương tác UI/API mà không lách xác thực hoặc vi phạm điều khoản hệ thống.
- Thiết kế luồng tạo, phê duyệt, kích hoạt, vận hành, thay đổi, rotate, tạm khóa, thu hồi và xóa robot account có kiểm soát.
- Liên hệ thay đổi **Joiner–Mover–Leaver** của người sở hữu/điều khiển với vòng đời độc lập của robot account và rủi ro quyền tồn dư.
- Tổ chức **audit, session recording, job/run correlation, quyền hạn từng tác vụ, reconciliation, incident response** và kiểm thử để phát hiện tài khoản robot mồ côi hoặc bị lạm dụng.
- Thiết kế ví dụ tích hợp Java/Spring và các nguyên tắc an toàn cho hệ tự động chạy nền.

## 1. Robot account là gì?

**Robot account** là một **danh tính hoặc tài khoản được cấp để phần mềm tự động (robot/bot) thực hiện những công việc đã xác định**, thay vì một người dùng trực tiếp thao tác qua account cá nhân.

Trong doanh nghiệp, thuật ngữ thường xuất hiện ở **Robotic Process Automation (RPA)**: robot mở ứng dụng, đăng nhập, đọc dữ liệu, nhập biểu mẫu, kiểm tra hóa đơn, xuất báo cáo hoặc thực hiện tác vụ nhiều bước theo workflow. Ngoài RPA, các bot chạy tác vụ tự động có thể dùng account tương tự, nhưng **không phải mọi service principal đều là “robot account”**; thuật ngữ và loại identity cụ thể phụ thuộc nền tảng.

Ví dụ:

- Robot thu thập hóa đơn từ cổng nhà cung cấp rồi chuyển vào hệ thống kế toán.
- Robot kiểm tra trạng thái đơn hàng từ hệ thống ERP và cập nhật CRM.
- Robot chạy ban đêm để tổng hợp báo cáo nội bộ theo quyền được duyệt.
- Robot hỗ trợ tác vụ onboarding: kiểm tra yêu cầu và gọi connector IAM tạo account theo workflow.
- Robot đối chiếu tồn kho giữa hai hệ thống cũ chưa có API thống nhất.
- Robot xử lý ticket bằng cách tương tác với ứng dụng có giao diện người dùng.

**Robot account không phải “nhân viên ảo có thể được cấp mọi quyền như con người”**. Nó là non-human identity với **mục đích, chủ sở hữu, quyền, bằng chứng và vòng đời riêng**.

Trong module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, robot account liên kết với quản lý danh tính theo **Joiner–Mover–Leaver**: con người được xác minh và có trách nhiệm với bot, trong khi quyền bot được quản lý bằng **IdP/SSO, SCIM/API, RBAC/ABAC, PAM, audit, reconciliation** và các cơ chế hạn chế quyền truy cập tồn dư.

### 1.1. Bốn câu hỏi nền tảng

Một triển khai robot phải trả lời được:

1. **Robot nào?** Identity ổn định của chương trình hoặc tài khoản nào được dùng để truy cập?
2. **Ai chịu trách nhiệm?** Owner kỹ thuật, chủ sở hữu nghiệp vụ và người phê duyệt tài nguyên là ai?
3. **Được làm gì?** Chỉ những tác vụ, tài nguyên, phạm vi dữ liệu và khung thời gian nào?
4. **Khi nào phải dừng?** Khi quy trình bị hủy, dự án kết thúc, owner rời tổ chức hoặc credential bị lộ thì thu hồi như thế nào?

Chỉ biết tên account `rpa-finance-01` mà không trả lời được bốn câu hỏi này thì chưa đủ quản trị.

## 2. Robot account khác gì các loại danh tính khác?

| Loại danh tính | Chủ thể | Kiểu sử dụng | Kiểm soát nổi bật |
| --- | --- | --- | --- |
| **Human account** | Nhân viên/nhà thầu | Người đăng nhập và thao tác | Identity proofing, SSO/MFA, HRIS JML |
| **RPA robot account** | Bot/process automation | UI hoặc API theo kịch bản | Owner, bot/process ID, credential vault, run audit |
| **Traditional service account** | Dịch vụ/job/daemon | Nền, không tương tác | Scoped permissions, secret/key rotation |
| **OAuth client / workload identity** | Workload được issuer chứng thực | API-to-API | Issuer, audience, scopes, short-lived tokens |
| **Privileged/PAM account** | Quyền cao trên target | Quản trị theo phiên | JIT/JEA, approval, recording, revocation |
| **Break-glass account** | Cơ chế phục hồi khẩn cấp | Chỉ sự cố được phép | Custody độc lập, cảnh báo, hậu kiểm |
| **Shared human account** | Nhiều người dùng chung một username | Tương tác khó attribution | Nên tránh, không coi là robot được quản trị |
| **Device identity** | Máy/thiết bị được quản lý | Xác thực thiết bị | Certificate, posture, inventory, renewal |

Một robot RPA có thể **dùng service account để đăng nhập**, một bot gọi API có thể **dùng workload identity**, và một robot hiếm khi cần **đặc quyền** có thể phải đi qua PAM/JIT. Vì thế các loại account có thể giao nhau theo **cơ chế thực thi**, nhưng không đồng nhất về mục tiêu nghiệp vụ.

### 2.1. “Không phải người” không đồng nghĩa “không cần owner”

Một robot không có hồ sơ HRIS riêng như nhân viên; tuy nhiên phải có **sponsor hoặc đội chịu trách nhiệm**, người duyệt quyền và người xử lý khi bot ngừng chạy.

### 2.2. “Bot” không đồng nghĩa mọi AI agent

Tác vụ RPA theo quy tắc có thể rất xác định. Một agent có khả năng lựa chọn hành động linh hoạt cần **các rào chắn đặc biệt về thẩm quyền thực thi, approval, phạm vi công cụ và giám sát**. Dù công nghệ khác nhau, identity và quyền vẫn không nên dựa vào việc nó “chạy tự động” để được cấp rộng hơn.

## 3. Attended robot và unattended robot

### 3.1. Attended robot

**Attended RPA** được kích hoạt hoặc hỗ trợ bởi một nhân viên đang làm việc, ví dụ bấm nút trong desktop assistant để tự động điền trường trên hệ thống CRM.

Điểm cần thiết kế:

- Robot có thể thực thi **trong user session** hoặc nhận ủy quyền hợp lệ từ người dùng theo khả năng nền tảng.
- Quyền truy cập thường bị giới hạn bởi **quyền thực tế của user** và chính sách ứng dụng.
- Audit cần phân biệt **người khởi chạy** và **phần mềm tự động thực hiện thao tác**.
- Không để robot có quyền cao hơn user chỉ vì “chạy hộ”.
- Không lưu mật khẩu/refresh token của nhân viên trong script để chạy lại ngoài giờ nếu chưa có mô hình ủy quyền được phép.
- Nếu user Leaver, bot không được tiếp tục dùng user session/cookie/credential cũ.

### 3.2. Unattended robot

**Unattended RPA** chạy trên máy/VM/container hoặc dịch vụ điều phối, theo lịch, queue hoặc sự kiện, không cần người hiện diện trực tiếp.

Đặc điểm:

- Có **robot principal** hoặc account được quản trị riêng.
- Có **bot orchestrator, run ID, queue item, environment** và cấu hình cấp quyền.
- Truy cập target bằng credential/tokens được cấp theo cơ chế được hỗ trợ.
- Cần chính sách khi MFA, SSO hoặc captcha đòi người tương tác.
- Audit cần nối run ID với robot principal, target transaction và owner.
- Phải quản lý tài khoản khi bot ngừng, đổi môi trường hoặc process chuyển chủ.

### 3.3. Không tráo mô hình danh tính

Một attended robot xử lý một giao dịch thay user **không nên tự chuyển thành unattended job** bằng cách trích xuất cookie của người đó và chạy qua đêm. Đây là dạng tái sử dụng session sai ngữ cảnh, gây rủi ro bảo mật và vi phạm policy của ứng dụng.

### 3.4. Bảng so sánh

| Tiêu chí | Attended | Unattended |
| --- | --- | --- |
| Người khởi chạy | Thường có người | Scheduler, event, queue hoặc orchestrator |
| Danh tính gọi target | User context hoặc delegated identity theo chính sách | Robot/service/workload principal riêng |
| Cơ chế đăng nhập | Tận dụng phiên người dùng hợp lệ khi được cho phép | Non-interactive/bot-capable authentication |
| Thời gian chạy | Trong một user workflow | Có thể liên tục hoặc ngoài giờ |
| Attribution | User + robot/process | Robot + run + initiator/owner |
| Rủi ro JML | User Mover/Leaver | Owner/custodian Mover/Leaver và robot retirement |
| Recovery | Người dùng có thể kiểm tra trực tiếp | Cần alert, retry, dead-letter và runbook |

## 4. Tại sao không dùng account cá nhân cho robot chạy nền?

Một cách làm tắt là tạo bot bằng account của nhân viên, lưu password trong script và đặt lịch chạy hàng đêm. Thiết kế này tạo nhiều vấn đề:

- **Mất accountability:** log ghi nhân viên thực hiện nhưng thực tế robot chạy.
- **Leaver risk:** nhân viên nghỉ, account bị khóa và automation ngừng bất ngờ; hoặc secret cũ vẫn còn.
- **MFA/SSO policy:** script có thể không hoàn thành phương thức xác thực dành cho người.
- **SoD conflict:** bot thực hiện hành động ngoài phạm vi nhiệm vụ của nhân viên.
- **Secret duplication:** password/cookie bị sao chép vào scheduler, log, file cấu hình.
- **Quyền quá rộng:** account nhân viên có nhiều role không cần cho một process.
- **Khó rotate:** đổi password cá nhân làm robot lỗi và khuyến khích vô hiệu hóa kiểm soát.
- **Không rõ ownership:** khi người phụ trách đổi nhóm, không ai biết phải bàn giao bot.

**Lựa chọn ưu tiên** là identity riêng cho workload hoặc robot theo cơ chế target hỗ trợ. Nếu một ứng dụng legacy chỉ hỗ trợ human-style login, tổ chức phải đánh giá, cấp account bot có phân loại riêng khi nhà cung cấp cho phép, áp kiểm soát bù và lên kế hoạch thay thế bằng tích hợp an toàn hơn.

## 5. Kiến trúc tham chiếu cho robot account

~~~mermaid
flowchart LR
    BIZ["Business process owner"] --> GOV["IAM/IGA: registration, approval, lifecycle"]
    TECH["Technical owner"] --> GOV
    GOV --> CATALOG["Robot identity inventory"]
    GOV --> IDP["IdP / Target account / OAuth client"]
    GOV --> VAULT["Vault / Secret manager / PAM"]
    CATALOG --> ORCH["RPA orchestrator"]
    VAULT --> ORCH
    ORCH -->|"Job/run context"| EXEC["Robot runtime"]
    IDP -->|"Approved identity / token"| EXEC
    EXEC -->|"UI / API / DB connector"| PEP["Target application / PEP"]
    PEP --> DATA["Business resource"]
    ORCH --> AUD["Audit / Run logs"]
    PEP --> AUD
    AUD --> REC["Reconciliation"]
    CATALOG --> REC
    GOV --> REC
~~~

Sơ đồ là **kiến trúc logic**, không phải bắt buộc mỗi tổ chức đều có tất cả sản phẩm. Đối với target chỉ có UI, robot có thể dùng phiên trình duyệt/desktop hợp lệ; target có API nên ưu tiên cơ chế **machine-to-machine** nếu đáp ứng yêu cầu nghiệp vụ và bảo mật.

### 5.1. Các ranh giới tin cậy

1. **Owner → Governance:** người xin tạo bot có thẩm quyền không?
2. **Governance → Orchestrator:** job nào được phép nhận identity nào?
3. **Orchestrator → Vault/Issuer:** runtime có thực là robot được đăng ký không?
4. **Robot → Target:** target xác thực account/token/cert đúng không?
5. **Target PEP → Resource:** bot có đúng action, data scope, tenant và thời gian không?
6. **Robot/Target → Audit:** có gắn robot principal và run ID để truy vết không?
7. **IAM → Reconciliation:** desired permissions có khớp observed/effective access không?

### 5.2. Dựa vào IP/hostname không đủ

Một bot chạy từ VM đã được cấp quyền mạng không có nghĩa mọi process trên VM đó đều được quyền chỉnh dữ liệu ERP. **Network location là tín hiệu**, không thay thế xác thực principal và authorization của target.

## 6. Các thành phần vận hành robot

| Thành phần | Trách nhiệm | Điều cần bảo vệ |
| --- | --- | --- |
| **Orchestrator** | Lập lịch, phân job, queue, credential reference | Ai sửa job và gán account |
| **Runtime/runner** | Thực thi script/workflow | Host isolation, process privilege, artifact integrity |
| **Robot account** | Principal đăng nhập target | Credential, scope, expiry |
| **Workload identity issuer** | Chứng thực runtime, cấp token/cert | Trust policy, audience, key |
| **Credential vault** | Quản lý secret, rotation và custody | Quyền đọc/use, audit, egress |
| **Target application** | Kiểm đăng nhập, quyền nghiệp vụ | Roles, SoD, object/tenant policy |
| **Approval/IGA** | Xác định purpose, owner, policy | Deny-by-default, review |
| **Log/SIEM** | Quan sát activity, failures, anomalies | Không lưu raw secret hoặc PII thừa |
| **Reconciliation engine** | So desired và observed rights | Độ mới, trạng thái UNKNOWN |
| **Incident/on-call** | Xử lý lỗi và lạm dụng | Runbook, escalation, privilege cleanup |

Một bot có thể truy cập nhiều ứng dụng, nhưng **không tự có một credential chung cho tất cả target**. Nên giới hạn per application/tenant/environment, đồng thời quản lý được các liên kết để phân tích quyền tổng hợp.

## 7. Threat model của robot account

### 7.1. Những rủi ro đặc thù

| Rủi ro | Kịch bản | Kiểm soát chủ đạo |
| --- | --- | --- |
| **Credential theft** | Password/token được nhúng vào script | Vault, rotation, short-lived credentials |
| **Bot impersonation** | Runtime giả danh robot đã đăng ký | Attestation, issuer trust, execution policy |
| **Overprivileged bot** | Một bot có quyền admin vì dễ tích hợp | Least privilege, approval và review |
| **Privilege creep** | Thêm target mới nhưng không gỡ quyền cũ | Change controls, recertification, reconciliation |
| **Orphaned account** | Bot đã xóa nhưng account còn | Retirement workflow, inventory |
| **Owner Leaver** | Người cũ biết secret/giữ quyền sửa bot | JML, transfer ownership, rekey khi cần |
| **Cross-tenant leakage** | Bot dùng chung credential cho hai khách hàng | Tenant-bound identity and authorization |
| **Automation misuse** | Thay job để chuyển dữ liệu ra ngoài | CI/CD integrity, review và egress controls |
| **Session reuse** | Dùng cookie của nhân viên để chạy sau giờ | Dedicated identity, supported auth flow |
| **Replay/duplicate jobs** | Retry tạo hai giao dịch hoặc cấp role hai lần | Idempotency, transaction guard |
| **Weak observability** | Chỉ thấy bot account, không biết job | Run ID, action log, ticket correlation |
| **Remote desktop capture** | Screenshot chứa dữ liệu nhạy cảm | Data minimization, protected evidence |
| **Runtime compromise** | Attacker dùng quyền có sẵn của bot | Isolation, detection, time-bound grants |

### 7.2. Bot mạnh vẫn có thể bị chiếm

Nếu attacker điều khiển **process đang giữ token hợp lệ**, họ có thể thực hiện các hành động mà token và policy cho phép. Short-lived token giảm thời gian lạm dụng sau khi đánh cắp nhưng **không tự ngăn hành động ngay trong runtime bị chiếm**.

### 7.3. UI automation có nguy cơ nhầm trạng thái

Robot đọc UI có thể nhầm vị trí nút, nội dung màn hình hoặc trang đã thay đổi. Nếu account có quyền xóa hàng loạt, một lỗi thao tác có thể thành sự cố dữ liệu. Cần giới hạn quyền, kiểm điều kiện trước/sau, dry-run và approval cho hành động có tác động lớn.

## 8. Inventory – hồ sơ robot account tối thiểu

Một robot cần **định danh ổn định và hồ sơ quản trị**.

| Thuộc tính | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **robotId** | `robot-invoice-import-prod` | ID của automation logic |
| **accountId** | `rpa-invoice-prod` | Principal hoặc target account |
| **principalType** | `ROBOT_RPA` | Phân biệt human/service |
| **executionMode** | `UNATTENDED` | Cách vận hành |
| **businessProcessId** | `invoice-reconciliation` | Mục đích nghiệp vụ |
| **businessOwner** | `finance-operations` | Chịu trách nhiệm quy trình |
| **technicalOwner** | `platform-automation` | Chịu trách nhiệm runtime |
| **resourceOwner** | `erp-finance-team` | Duyệt quyền trên target |
| **targetSystems** | `ERP`, `Invoice Portal` | Hệ đích |
| **environment/tenant** | `production/tenant-a` | Giới hạn phạm vi |
| **approvedPermissions** | `invoice.read`, `invoice.create` | Entitlement tối thiểu |
| **credentialRef** | `vault://robots/invoice-prod` | Tham chiếu, không phải secret |
| **issuer/clientRef** | `workload-invoice-prod` | Nguồn danh tính |
| **approvalRefs** | `access-approval-781` | Bằng chứng cấp quyền |
| **schedule/trigger** | `daily-batch` | Điều kiện thực thi |
| **createdAt / reviewDueAt** | Timestamp có timezone | Vòng đời, tái chứng nhận |
| **retirementTrigger** | `project-end` | Khi nào phải đánh giá thu hồi |
| **lastRun / lastUsed** | Timestamp và nguồn | Phát hiện bot không dùng |
| **riskTier / dataClass** | `HIGH`, `CONFIDENTIAL` | Kiểm soát theo rủi ro |
| **status** | `ACTIVE` | Trạng thái hiện hành |
| **policyVersion** | `robot-access/v3` | Quy tắc áp dụng |

### 8.1. JSON manifest minh họa

~~~json
{
  "robotId": "robot-invoice-import-prod",
  "principalType": "ROBOT_RPA",
  "executionMode": "UNATTENDED",
  "businessProcessId": "invoice-reconciliation",
  "businessOwnerTeam": "finance-operations",
  "technicalOwnerTeam": "platform-automation",
  "resourceOwnerTeam": "erp-finance-team",
  "tenantId": "tenant-a",
  "environment": "production",
  "targetSystems": ["erp-finance", "supplier-portal"],
  "approvedEntitlements": [
    {
      "resourceId": "erp-finance",
      "action": "invoice.create",
      "scope": "tenant-a",
      "expiresAt": "2027-03-31T23:59:59Z"
    }
  ],
  "credentialRef": "vault://robots/invoice-prod",
  "approvalRef": "access-approval-781",
  "lifecycleStatus": "ACTIVE",
  "reviewDueAt": "2027-01-15T00:00:00Z"
}
~~~

Đây là **dữ liệu minh họa**. Không có schema bắt buộc của mọi nền tảng. **Không lưu mật khẩu hoặc token thật** trong manifest.

### 8.2. Owner khác tài khoản đăng nhập

Robot account là principal kỹ thuật. **Business owner** xác nhận nhu cầu, **technical owner** quản lý thực thi, và **resource owner** phê duyệt quyền đích. Một người có thể giữ nhiều vai trò ở tổ chức nhỏ, nhưng các trường phải rõ ràng để hỗ trợ bàn giao và SoD.

## 9. Quy trình yêu cầu và phê duyệt robot

Một robot mới nên có **access request và risk review**, không chỉ tạo tài khoản từ script.

### 9.1. Luồng phê duyệt

~~~mermaid
sequenceDiagram
    autonumber
    actor BO as Business owner
    participant IGA as IAM / IGA
    participant SEC as Policy / Security
    participant RO as Resource owner
    participant RPA as Robot orchestrator
    participant IDP as IdP / Target account
    participant AUD as Audit / Reconciliation

    BO->>IGA: Register robot + process + target scope
    IGA->>SEC: Evaluate risk, SoD and lifecycle
    SEC-->>IGA: Eligible / denied / need review
    IGA->>RO: Request exact resource/action/expiry
    RO-->>IGA: Approve or reject
    alt Approved and policy satisfied
        IGA->>IDP: Provision robot account / client trust
        IGA->>RPA: Register scoped identity/credentialRef
        RPA->>AUD: Robot + run configuration evidence
        IDP->>AUD: Observed account / role
        AUD-->>IGA: Match / exception
    else Not approved
        IGA-->>BO: DENY or clarification
    end
~~~

### 9.2. Những thông tin owner phải duyệt

- Bot làm nhiệm vụ **gì và vì sao cần automation**?
- Principal nào sẽ dùng quyền, vào hệ thống nào?
- Quyền đọc, viết, duyệt, cấp role, export hay delete?
- Phạm vi dữ liệu, tenant, environment, schedule và thời hạn?
- Có ảnh hưởng dữ liệu cá nhân, tài chính hoặc hệ thống production không?
- Hành động nào phải có **human approval** ngay tại thời điểm thực thi?
- Có **separation of duties** giữa tạo và phê duyệt giao dịch không?
- Ai chịu trách nhiệm nếu robot tạo sai dữ liệu hoặc chạy ngoài lịch?
- Credential/runner có dùng chung với robot khác không?
- Khi process không còn, ai chịu trách nhiệm deactivate/deprovision?

### 9.3. Approval không tự cấp quyền

`APPROVED` là quyết định governance; `PROVISIONED` là trạng thái connector thực hiện; `VERIFIED` là đọc lại quyền đích. Không kết luận robot đã được cấp đúng quyền vì một ticket có trạng thái Done.

## 10. Xác thực robot qua UI, API và ứng dụng legacy

### 10.1. Ưu tiên tích hợp được hỗ trợ

Nếu target có API machine-to-machine và đáp ứng nghiệp vụ, thường dễ cấp quyền hẹp và giám sát hơn việc mô phỏng thao tác UI. Có thể dùng **OAuth 2.0 client credentials, workload identity federation, mTLS hoặc service principal** tùy hệ.

Nếu target chỉ có UI:

- Xem vendor có **bot/RPA account type** và authentication flow chính thức không.
- Tạo identity bot có owner, role và purpose riêng.
- Bảo vệ password/secret trong vault hoặc broker được phép.
- Không sửa ứng dụng, CAPTCHA, MFA hoặc SSO để bí mật vượt cơ chế bảo vệ.
- Đánh giá điều khoản sử dụng, chính sách dữ liệu và mức độ hỗ trợ automation.
- Có phương án dừng robot khi challenge/authentication thay đổi.

### 10.2. MFA và unattended robot

**MFA thiết kế cho người dùng tương tác** có thể không phù hợp với unattended job. Giải pháp không phải lưu OTP seed trong script hoặc tắt MFA cho cả tổ chức.

Thay vào đó:

1. Xác định vendor hỗ trợ **non-interactive identity** hay delegated machine credential không.
2. Thiết kế **bot-specific authentication** phù hợp với policy và mức bảo vệ tương xứng.
3. Nếu cần human-in-the-loop, xác nhận và ghi quyết định của người thật vào workflow.
4. Áp điều kiện IP/device/runtime, credential rotation, hạn quyền và monitoring theo risk.
5. Nếu không có cách nào hợp lệ và an toàn, **không tự dựng cơ chế bypass**; yêu cầu thay đổi kiến trúc hoặc chọn tích hợp được hỗ trợ.

### 10.3. Cookie/session của nhân viên không phải robot credential

Một cookie SSO hoặc refresh token cá nhân không nên được chép sang runner để bot chạy lâu dài. Nếu một nhiệm vụ cần hành động thay user, phải có **delegation/on-behalf-of** và audit chủ thể theo khả năng nền tảng.

### 10.4. Cloud/OIDC và robot

Khi robot chạy trên Kubernetes/cloud, có thể sử dụng **managed/workload identity** để lấy token cho API thay vì cất credential tĩnh. Token phải được ràng buộc **issuer, subject, audience, scope, tenant và trust policy**; một account bot được phép gọi ERP API không tự có quyền cloud admin.

## 11. SSO/IdP và những giới hạn quan trọng

Một số SaaS tạo **user account** cho bot và cho đăng nhập qua IdP/SSO. Điều này có thể gây nhầm lẫn:

- Account có hình thức “user” không chứng minh có một người thật sở hữu trực tiếp.
- Không nên tạo hồ sơ nhân sự giả trong HRIS để “qua” chính sách.
- Phải gắn `principalType=ROBOT` hoặc phân loại tương đương trong registry.
- Nếu vendor buộc bot là user, cần có owner/sponsor, license và approval phù hợp.
- Policy SSO/MFA không được âm thầm nới lỏng cho tất cả users.
- Account bot không nên được cấp quyền truy cập self-service hoặc recovery channel dành cho người mà không có threat model.
- Reconciliation phải đọc role thực tế tại ứng dụng, không chỉ group IdP.
- Disable IdP không tự kết thúc mọi session/token còn hợp lệ ở SaaS.

### 11.1. Định danh liên kết

Dùng ID ổn định và kết nối mapping:

~~~text
robotId
  -> IdP/service principal ID
  -> targetAccountId
  -> bot orchestrator identity
  -> credentialRef
  -> business/technical owner
  -> resource approval
  -> runId / audit event
~~~

Không chỉ nối bằng email hoặc username, vì chúng có thể đổi, được tái sử dụng hoặc bị trùng giữa environment.

## 12. Quản lý credential trong vault hoặc PAM

Robot có thể cần password, SSH key, client certificate, API token hoặc delegated capability. Quy trình phải phù hợp với loại credential.

### 12.1. Nguyên tắc bảo vệ

- Không hardcode password hoặc API key trong code, config repository, container image, notebook, scheduler hay log.
- Dùng **credential reference** đến vault/issuer, không lưu raw value trong bot registry.
- Chỉ runtime/runner được phép mới có thể **retrieve/use** credential đó.
- Phân biệt quyền **read secret, invoke token issuance, rotate secret, administer vault**.
- Hạn chế credential theo target, purpose, environment và tenant.
- Ưu tiên short-lived token hoặc certificate khi ứng dụng hỗ trợ.
- Cấu hình **rotation/renewal** với overlap hợp lý để tránh downtime.
- Kiểm ai có thể tải/export bản sao credential ra khỏi hệ quản lý.
- Theo dõi credential không còn dùng hoặc bot không còn owner.

### 12.2. Secret rotation không đồng nghĩa revoke token

Nếu đổi password/service secret, session cookie hoặc token đã phát trước đó có thể vẫn sống theo cơ chế target. Cần kiểm **access token lifetime, revocation/introspection, target session invalidation và trust-policy state**.

### 12.3. Một bot dùng nhiều target

Nên tách credentials:

~~~text
Robot Invoice Import
  - supplier-portal-bot-credential
  - erp-invoice-scoped-api-client
  - reporting-readonly-token

Không nên:
  - one-global-admin-password-for-all-targets
~~~

Điều này giảm blast radius và giúp rotate/thu hồi theo từng target.

### 12.4. Khi credential lộ

Phải có incident response: chặn use khi khả thi, rotate/rekey, kiểm token/session cũ, rà target audit, đối chiếu quyền phát sinh và xem khả năng lạm dụng bởi runner khác.

## 13. Phân quyền robot bằng RBAC/ABAC/PBAC

**RBAC** phù hợp để gán role bot chuẩn; **ABAC** kiểm thêm owner, tenant, environment, thời gian, data classification; **PBAC** phối hợp nhiều điều kiện thành policy có thể audit.

### 13.1. Mẫu quyết định minh họa

~~~text
PERMIT invoice.create WHEN
    caller.principalType == ROBOT
    AND caller.robotId == "robot-invoice-import-prod"
    AND caller.lifecycleStatus == ACTIVE
    AND caller.environment == "production"
    AND caller.hasScope("invoice.create")
    AND caller.tenantId == invoice.tenantId
    AND caller.approval.validFor("erp-finance", "invoice.create", now)
    AND invoice.sourceWasVerified
    AND NOT caller.securityBlocked
ELSE DENY
~~~

Mã giả này không phải cú pháp một sản phẩm policy engine. Các thuộc tính cần lấy từ **trusted token, workload registry, PIP hoặc server-side context**, không tin body/header do bot gửi.

### 13.2. Role riêng theo hành động

| Robot | Quyền cần | Không nên có mặc định |
| --- | --- | --- |
| Import hóa đơn | Đọc input, tạo bản nháp | Duyệt chi tiền hoặc chuyển khoản |
| Đối soát đơn hàng | Đọc trạng thái order, ghi kết quả đối soát | Thay giá, tạo role admin |
| Tổng hợp báo cáo | Read-only trong dataset đã duyệt | Export toàn bộ PII ngoài scope |
| Onboarding connector | Tạo/disable account theo ticket hợp lệ | Tự duyệt và cấp superadmin cho chính mình |
| Monitor hệ thống | Đọc metrics và alert | Sửa cấu hình production |
| Deployment bot | Deploy trong environment được duyệt | Ghi vào production secret store toàn tổ chức |

### 13.3. Least privilege phải bảo vệ cả hành động gián tiếp

Một robot không được `payment.approve` nhưng có thể sửa dữ liệu nguồn khiến hệ thống tự approve cũng có thể gây vi phạm. Cần phân tích **chuỗi tác động nghiệp vụ** và kiểm ở business PEP, không chỉ xem tên permission.

## 14. Segregation of Duties và human-in-the-loop

**Segregation of Duties (SoD)** đặc biệt quan trọng khi robot thay thế nhiều bước thao tác của con người.

### 14.1. Ví dụ hóa đơn

Quy trình gồm:

1. Nhập hóa đơn.
2. Kiểm thông tin và đối chiếu đơn mua.
3. Phê duyệt thanh toán.
4. Thực hiện thanh toán.

Nếu một robot có cả `invoice.create` và `payment.approve`, lỗi logic hoặc bị chiếm có thể tạo hóa đơn giả rồi tự phê duyệt. Thiết kế tốt:

- Robot có thể chuẩn bị và đối chiếu dữ liệu.
- **Người có thẩm quyền hoặc một kiểm soát độc lập** duyệt quyết định rủi ro cao.
- Robot chỉ hoàn tất action khi có **approval artifact đúng scope**, còn hạn và không bị thu hồi.
- API thực thi kiểm identity của **actor robot** và thẩm quyền của approval.
- Audit ghi rõ **human approver khác robot executor**.
- Một job không được tự ký approval thay người.

### 14.2. Approval artifact mẫu

~~~json
{
  "approvalId": "approval-601",
  "approvedByIdentityId": "person-601",
  "robotId": "robot-invoice-import-prod",
  "resourceId": "invoice-2042",
  "approvedAction": "invoice.submit",
  "tenantId": "tenant-a",
  "expiresAt": "2026-12-05T12:00:00Z",
  "status": "APPROVED"
}
~~~

Đây là JSON minh họa. Server phải kiểm **approval thật từ nguồn tin cậy, không chỉ tin JSON do bot tạo ra**.

### 14.3. Khi auto-approval hợp lệ

Một số giao dịch ít rủi ro có thể auto-approve theo policy đã được owner duyệt trước. Điều đó khác với việc robot **tự tạo và tự chấp thuận một ngoại lệ không giới hạn**. SoD tùy mô hình rủi ro, không phải mọi bước tự động đều bắt buộc con người bấm.

## 15. Cấp tài khoản robot qua IdP, SCIM và API

Có thể provision robot account tại IdP, SaaS, ERP hoặc ứng dụng riêng. **SCIM** là giao thức quản lý identity ở hệ thống có hỗ trợ, thường có các tài nguyên Users/Groups; nó **không mặc định bao phủ mọi robot principal hoặc workload certificate**.

### 15.1. Luồng tổng quát

~~~text
Approved robot registration
  -> Create/enable principal in appropriate identity store
  -> Bind target account(s) to robotId
  -> Grant exact role/action/tenant
  -> Configure credential retrieval/trust
  -> Verify observed access
  -> Activate job schedule only after checks
~~~

### 15.2. Những giới hạn cần kiểm

- SaaS có cho bot-specific account hay chỉ human user?
- SCIM connector có quyền tạo/disable bot account không?
- Tài khoản có bị provisioning engine khác ghi đè status/owner không?
- Account deactivated có còn refresh token/session không?
- Nhóm được gán qua IdP có thực sự tương ứng với quyền ở ERP?
- Một target có API nội bộ khác SCIM để quản lý service clients không?
- Account legacy có được tạo thủ công ngoài IGA không?

**Không tuyên bố đã provision/revoke đầy đủ chỉ vì connector trả HTTP thành công.** Cần đọc lại và đối soát effective access.

## 16. State machine của robot account

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> REVIEWING: Owner + resource + risk review
    REVIEWING --> REJECTED: Policy DENY
    REVIEWING --> APPROVED: Approval valid
    APPROVED --> PROVISIONING: Create principal and target grants
    PROVISIONING --> READY: Readback + credential check PASS
    PROVISIONING --> EXCEPTION: Partial provisioning
    READY --> ACTIVE: Approved schedule/run enabled
    ACTIVE --> SUSPENDED: Security block / incident / maintenance
    SUSPENDED --> ACTIVE: Revalidation + approved resume
    ACTIVE --> CHANGING: New owner/target/scope
    CHANGING --> READY: Reapprove and verify
    ACTIVE --> RETIRING: Process ends / account no longer needed
    SUSPENDED --> RETIRING: Decommission ordered
    RETIRING --> REVOKING: Stop jobs + revoke trusts and roles
    REVOKING --> VERIFIED_REMOVED: Target evidence PASS
    REVOKING --> EXCEPTION: Residual access / unknown
    EXCEPTION --> REVOKING: Remediation
    VERIFIED_REMOVED --> [*]
    REJECTED --> [*]
~~~

Đây là state machine minh họa. Nền tảng có thể có tên trạng thái khác nhưng phải phân biệt **ngừng job, disable account, revoke credential, gỡ entitlement và xác minh không còn quyền hiệu lực**.

### 16.1. Những invariant quan trọng

- Không cho `REQUESTED → ACTIVE` khi thiếu approval và verification.
- Bot chưa có owner hoặc owner đã Leaver không được tự động gia hạn quyền production.
- Robot account đã `SUSPENDED` không được resume chỉ vì scheduler tự retry.
- `REVOKE_REQUESTED` không đồng nghĩa đã thu hồi ở target.
- Process đổi scope/tenant phải **re-approve** phần mở rộng; không tái dùng approval cũ.
- Bot đã retire không được tự tái cấp account vì một queue event cũ.
- Item `EXCEPTION` phải có owner, mức rủi ro và thời hạn xử lý.
- Không xóa audit sau khi principal decommission.

## 17. Lập lịch, môi trường chạy và quyền thao tác

Một bot được phân công đúng quyền vẫn có thể gây sự cố khi **chạy ở sai môi trường hoặc sai thời điểm**.

### 17.1. Những điều cần ràng buộc

- **Environment:** staging, test và production không dùng chung credential production.
- **Tenant:** bot tenant-a không được dùng target tenant-b.
- **Schedule:** chỉ kích hoạt theo lịch/trigger được duyệt, đặc biệt với action nhạy cảm.
- **Orchestrator role:** ai được sửa job definition, gán robot account và replay queue?
- **Runner identity:** runtime nào được phép lấy credential của bot?
- **Artifact version/digest:** script nào được phép chạy.
- **Change window:** tác vụ quản trị production có cần approval theo window?
- **Max duration:** robot treo không được giữ privileged session vô hạn.
- **Concurrent runs:** giới hạn để tránh double payment, duplicate account.
- **Output path:** dữ liệu và file báo cáo chỉ được ghi nơi có thẩm quyền.

### 17.2. Không chỉ dựa vào lịch ở scheduler

Nếu một actor có thể chạy job bằng API thủ công ngoài khung giờ, việc đặt lịch trên giao diện không bảo đảm policy. Với quyền rủi ro cao, **target PEP/PAM/authorization service** phải kiểm các ràng buộc phù hợp, không chỉ tin orchestrator UI.

### 17.3. Shared runners

Nhiều bot dùng chung VM/runner có thể chia sẻ filesystem, process memory hoặc quyền đọc credential nếu isolation yếu. Cần tách secret mounts, OS users/containers, egress và runtime permissions; tránh một bot ít quyền đọc secret của bot khác.

## 18. Truy vết danh tính robot qua từng lần chạy

Một robot có thể thực hiện hàng nghìn thao tác trong một lần chạy. Nếu audit chỉ ghi `rpa_user` đăng nhập lúc 01:00, rất khó xác định thao tác nào thuộc job nào.

### 18.1. Chuỗi attribution

~~~text
Business process / approved request
  -> robotId
  -> orchestrator jobId and runId
  -> artifact version/digest
  -> runtime instance ID
  -> authenticated target account/client ID
  -> action/resource/tenant
  -> target transaction ID/result
  -> human initiator/approver (nếu có)
  -> security/audit evidence
~~~

### 18.2. Run ID không phải credential

`runId` giúp tương quan nhưng **không chứng minh identity** vì bot có thể tự khai một chuỗi bất kỳ. Target cần tin authenticated principal, sau đó dùng runId từ kênh được bảo vệ hoặc correlation event có nguồn rõ.

### 18.3. Trace ở UI bot

Nếu robot tương tác GUI, có thể lưu **session events, ảnh chụp màn hình theo chính sách, target application audit và process logs**. Screenshot chứa dữ liệu khách hàng có thể nhạy cảm; cần data minimization, retention, mã hóa và quyền xem riêng.

## 19. Joiner: người mới được giao trách nhiệm với robot

Một **Joiner** là người mới vào tổ chức hoặc dự án. HRIS/identity proofing xác minh quan hệ làm việc của người đó; tuy nhiên bot có thể đã tồn tại từ trước.

### 19.1. Giao quyền quản trị robot cho Joiner

1. HRIS xác nhận identityId, relationshipId, workerType, manager, sponsor và ngày hiệu lực.
2. IdP cấp account cá nhân, phương thức xác thực và nhóm công việc theo chính sách.
3. IGA kiểm **eligibility** để người mới được quản trị robot nào.
4. Business/technical owner phê duyệt phạm vi: đọc log, sửa workflow, deploy, chạy job hay truy xuất credential.
5. Phân biệt quyền **operator** (chạy/giám sát) và **administrator** (đổi identity, credential, role, approval).
6. Áp SoD: người chỉnh robot có thể không được tự phê duyệt mọi thay đổi tài chính.
7. Cấp role theo **JIT/time-bound** khi rủi ro cao; ghi audit.
8. Kiểm người mới có training và runbook cần thiết.
9. Reconciliation xác minh không cấp quyền production trước effectiveAt.

### 19.2. Người mới không nhận password robot qua tin nhắn

Việc bàn giao bot nên qua **orchestrator, vault, IAM và tài liệu quy trình**. Người mới không cần biết raw password nếu hệ thống có thể sử dụng credential injection/broker hoặc token issuance. Tránh gửi bí mật qua email/chat trong onboarding.

### 19.3. Joiner khác tạo robot mới

Một nhân viên mới không tự tạo `robot-admin-01` với role production chỉ vì được giao viết automation. **Đăng ký workload và cấp target entitlements** vẫn là một quy trình quản trị riêng.

## 20. Mover: đổi chủ sở hữu hoặc phạm vi robot

**Mover** của người quản trị bot hoặc process owner thường là điểm xuất hiện **quyền tồn dư**.

### 20.1. Ví dụ

~~~text
Trước Mover:
  Employee A = technical owner của robot-invoice-prod
  A có quyền sửa workflow và vault policy
  Robot có role invoice.read + invoice.create

Sau Mover:
  A chuyển sang đội Data Science
  Technical owner chuyển cho Employee B
  Business process invoice vẫn hoạt động
~~~

Những thay đổi cần làm:

- Thu hồi role **robot admin/orchestrator/vault** của A nếu không còn nhiệm vụ.
- Chuyển accountable owner và escalation contact cho B/đội thích hợp.
- Rà credential mà A từng có thể xem, download hoặc mint.
- Xem xét rotation/rekey nếu có nguy cơ bí mật tồn dư; không đổi vô kế hoạch làm hỏng bot.
- Cập nhật approval scope và quyền trên target nếu process cũng thay đổi.
- Chuyển quyền sửa code/deployment/repository theo SoD.
- Kiểm account bot vẫn có purpose và owner hợp lệ.
- Reconcile cả **human access** và **robot effective access**.

### 20.2. Không tự tắt bot đang cần thiết

Người quản trị đổi vai trò **không có nghĩa bot sản xuất phải bị vô hiệu hóa**. Bot có vòng đời riêng. Tuy nhiên nếu business process không còn cần thiết sau Mover, phải chuyển robot sang trạng thái thay đổi/retire theo policy.

### 20.3. Mover của robot giữa hệ thống

Nếu một bot chuyển từ thao tác CRM sang tích hợp ERP, không chỉ thêm ERP quyền mới. Cần:

1. Xác minh business purpose và owner tại ERP.
2. Cấp identity/role cho target ERP trong scope đúng.
3. Bảo vệ khác biệt môi trường dev/prod, tenant và dữ liệu.
4. Thử nghiệm hành vi, logging và SoD.
5. Gỡ role CRM cũ khi không còn dùng.
6. Thu hồi credential/session cũ và reconcile để không có hai đường truy cập thừa.

## 21. Leaver: người sở hữu robot rời tổ chức

Khi owner, developer hoặc operator robot **Leaver**, hệ thống không thể chỉ disable SSO của người đó rồi kết luận offboarding đã hoàn tất.

### 21.1. Rủi ro còn lại

- Nhân viên cũ có thể đã lưu password/API key của robot.
- Người cũ còn là custodian của vault path.
- Git repo hoặc orchestrator còn quyền deploy/sửa job.
- Federation trust vẫn cho phép pipeline do người cũ kiểm soát.
- Robot account dùng email nhân viên và có recovery method hướng về người cũ.
- SIEM alert hoặc onboarding ticket vẫn gửi tới inbox của Leaver.
- Robot tiếp tục chạy production nhưng không ai chịu trách nhiệm.

### 21.2. Quy trình Leaver

~~~mermaid
flowchart TD
    HR["HRIS: Leaver event"] --> IGA["IGA: discover robot roles/custody"]
    IGA --> HUMAN["Revoke human orchestration/vault/admin grants"]
    IGA --> OWN["Transfer robot ownership and contacts"]
    IGA --> CRED["Assess known/copied credentials"]
    CRED --> ROT["Rotate/rekey/restrict when appropriate"]
    OWN --> CHECK["Validate process still needed"]
    CHECK --> KEEP{"Robot still authorized?"}
    KEEP -->|"Yes"| RUN["Continue under new owner + verify scope"]
    KEEP -->|"No"| RET["Stop scheduler; retire robot identity"]
    HUMAN --> REC["Reconciliation + audit"]
    ROT --> REC
    RUN --> REC
    RET --> REC
~~~

### 21.3. Leaver của owner không đồng nghĩa robot là Leaver

Một service robot có thể tiếp tục chạy để hoàn thành nghĩa vụ công ty. Phải **đổi owner, thu hồi người cũ, bảo vệ credential và xác minh quyền**. Ngược lại, nếu quy trình tự động hết mục đích, cần retire bot và xử lý toàn bộ account đích.

### 21.4. Người dùng từng khởi tạo attended run đã nghỉ

Một attended automation dựa trên user session phải mất quyền khi user Leaver theo chính sách. Không để scheduler lấy cookie hoặc token cũ rồi chạy mãi dưới danh tính người đã nghỉ.

### 21.5. Nhiều quan hệ việc làm

Nếu một người kết thúc hợp đồng tại pháp nhân A nhưng vẫn có vai trò hợp lệ tại B, cần thu hồi **đúng các quyền robot liên quan A** theo relationship ID, tenant và scope. Không suy luận từ email trùng.

## 22. Vòng đời robot khi quy trình thay đổi hoặc nghỉ hoạt động

Không chỉ con người có JML. Robot cũng cần mô hình **Register–Operate–Change–Retire**.

### 22.1. Các mốc

| Sự kiện | Điều cần làm | Bằng chứng |
| --- | --- | --- |
| **Robot requested** | Xác minh purpose, owner, target, risk | Registration |
| **Robot approved** | Resource owner phê duyệt scope và SoD | Decision artifact |
| **Identity provisioned** | Tạo principal, vault ref và target accounts | Connector event/readback |
| **Ready for execution** | Test credential, target authorization và audit | Verification |
| **Job activated** | Bật schedule/queue cho artifact đã duyệt | Change/run event |
| **Process scope changed** | Rà action, target, tenant, approval | Policy version |
| **Owner changed** | Chuyển trách nhiệm, rà secret custody | Owner transfer |
| **Secret rotated** | Chuyển credential, verify token/session | Rotation record |
| **Robot suspended** | Ngừng job/cấp quyền khi incident | Suspension event |
| **Robot retired** | Dừng orchestrator, disable/revoke accounts | Retirement request |
| **Removal verified** | Readback actual/effective access | Reconciliation |

### 22.2. Thứ tự retirement

~~~text
Business confirms robot no longer needed
  -> Disable new job submissions/schedules
  -> Drain or stop in-flight runs safely
  -> Archive required audit/artifact metadata
  -> Revoke API clients/credentials/keys/trust
  -> Disable/delete target accounts/groups/roles
  -> Invalidate sessions/tokens when supported
  -> Remove runner/vault access and egress exceptions
  -> Read back target privilege state
  -> Close only when remaining exceptions tracked
~~~

**Dừng robot process không chứng minh account đã bị thu hồi.** Một tài khoản bị bỏ quên trong ERP vẫn có thể đăng nhập theo credential cũ dù orchestrator không chạy.

### 22.3. Cẩn trọng khi xóa ngay

Một bot có thể xử lý nhiệm vụ tài chính còn dở, queue chưa drained hoặc có nghĩa vụ lưu bằng chứng. Nên phân biệt **stop execution, revoke security access, retain evidence, delete artifacts** theo chính sách; không xóa log để đạt mục tiêu dọn tài khoản.

## 23. Privileged robot và PAM/JIT

Một số robot có quyền cấu hình production, cấp tài khoản, sửa IAM group, quản trị database hoặc triển khai ứng dụng. Chúng có thể cần **PAM, JIT/JEA và kiểm soát đặc quyền**.

### 23.1. Quyền đặc biệt phải có lý do

- Robot onboarding có thể được tạo account user trong scope; không nên tự cấp global admin.
- Robot deploy có thể ghi đúng namespace; không cần quyền sửa toàn cloud organization.
- Robot DB maintenance có thể thực hiện stored procedure cụ thể; không nhất thiết có quyền DBA thường trực.
- Robot quản lý vault nên có quyền dùng secret nhất định; không tự đọc tất cả secret.

### 23.2. Privileged activation

Một policy có thể yêu cầu:

~~~text
PERMIT robot.privilegedRun WHEN
    robot.lifecycleStatus == ACTIVE
    AND robot.ownerIsCurrent
    AND run.processId == approvedProcessId
    AND run.artifactDigest in approvedArtifactSet
    AND run.target in approvedTargets
    AND run.window isWithinApprovedWindow
    AND access.approvalValid
    AND privilege.ttl <= allowedMaximum
    AND runtime.attestationVerified
    AND NOT robot.securityBlocked
ELSE DENY
~~~

Đây là mã giả. Điều kiện phải được **PEP/PDP kiểm ở server** bằng dữ liệu đáng tin; không tin JSON mà runner tự điền.

### 23.3. Session recording không phải authorization

PAM có thể ghi terminal hoặc GUI của robot, nhưng recording không tự chặn lệnh. Với tác vụ quan trọng cần kiểm **command/transaction policy**, hạn quyền và kiểm kết quả thực. Nếu recorder không khả dụng, quy trình fail-safe hoặc ngoại lệ phải được định nghĩa trước.

### 23.4. Không cấp quyền thường trực để tránh lỗi bot

Khi một task thất bại vì thiếu role, cách sửa không phải luôn thêm `Administrator` cho account robot. Phải xác định chính xác action, resource, tenant, môi trường, policy và approval; chỉ mở quyền tối thiểu phù hợp.

## 24. Giao dịch nghiệp vụ và quyền dữ liệu của robot

Robot thường chạm dữ liệu nhạy cảm trong nhiều bước, vì thế cần quản trị **nội dung và tác động của thao tác**, không chỉ thông tin đăng nhập.

### 24.1. Tách action

| Action | Ví dụ | Điều kiện |
| --- | --- | --- |
| `invoice.read` | Đọc hóa đơn trong tenant | Scope dữ liệu và purpose |
| `invoice.draft.create` | Tạo bản nháp | Kiểm dữ liệu đầu vào |
| `invoice.submit` | Gửi hóa đơn | Có thể cần approval nghiệp vụ |
| `payment.approve` | Duyệt chi tiền | SoD/human review hoặc policy độc lập |
| `customer.export` | Xuất dữ liệu khách hàng | Data owner, DLP/privacy controls |
| `user.account.create` | Provision người dùng | IAM workflow/ticket hợp lệ |
| `role.grant` | Cấp entitlement | Kiểm người nhận, resource, expiry, SoD |
| `data.delete` | Xóa đối tượng | High-risk guard, audit, rollback/backup |
| `secret.read` | Truy xuất secret | Vault scope và runtime attestation |

### 24.2. Không tin output của UI làm bằng chứng duy nhất

Robot có thể thấy “Thành công” trên màn hình nhưng transaction chưa commit hoặc hệ backend xử lý bất đồng bộ. Cần **target audit, transaction ID hoặc API state readback**, đặc biệt khi sửa dữ liệu tiền tệ hay cấp quyền.

### 24.3. Dữ liệu cá nhân và privacy

Trong log/screenshot, không nên lưu toàn bộ hóa đơn hoặc thông tin khách hàng nếu chỉ cần chứng minh job đã chạy. Cần **minimization, masking, phân quyền xem, encryption, retention và deletion/hold** theo policy.

### 24.4. Luồng dữ liệu giữa các pháp nhân/tenant

Một robot có quyền đọc tenant-a không tự được ghi kết quả sang tenant-b. Mỗi hop qua ứng dụng/file/object storage cần **phạm vi và approval** tương ứng; chống cross-tenant leakage ở PEP và target ACL.

## 25. Phiên đăng nhập, token, cookie và thời hạn hoạt động

Unattended bot có thể chạy lâu hoặc nhiều lần. Không nên coi **“robot ACTIVE”** là cho phép một session/token không giới hạn.

### 25.1. Các mốc cần phân biệt

- **Robot registered:** có inventory.
- **Identity enabled:** principal có thể xác thực.
- **Credential valid:** secret/cert/token hiện được issuer chấp nhận.
- **Session active:** target đang có phiên.
- **Job active:** orchestrator đang chạy một run cụ thể.
- **Entitlement effective:** target PEP vẫn cho action.
- **Owner approved:** business purpose và scope còn hiệu lực.

Một job đã kết thúc không có nghĩa session/cookie đã bị hủy, cũng không có nghĩa credential của bot đã được thu hồi.

### 25.2. Hạn token và renewal

- Token nên có **audience/scope/expiry** phù hợp.
- Runner cache có kiểm soát, không chia sẻ token giữa tenant hoặc service.
- Refresh/reissue dựa vào credential được cấp đúng, không dùng user cookie không chính thức.
- Khi bot bị SUSPENDED hoặc RETIRED, chặn token issuance mới và áp chính sách với token đã phát.
- Theo dõi **concurrent sessions** và session idle timeout theo mức rủi ro.
- Khi owner Leaver hoặc security incident, đánh giá session/token/alternate keys còn tồn dư.

### 25.3. Không dùng anti-bot bypass làm chiến lược vận hành

Nếu target yêu cầu CAPTCHA, xác minh bằng người hoặc challenge MFA mà không có phương án automation được hỗ trợ, cần **làm việc với chủ hệ thống/vendor hoặc đổi integration pattern**. Không dựa vào script vô hiệu hóa kiểm soát, tái sử dụng trái phép session hoặc cách lách policy.

## 26. Reliability và lỗi tác vụ tự động

Robot account được quản trị tốt vẫn có thể gây lỗi nếu workflow tự động **retry thiếu kiểm soát**.

### 26.1. Các lỗi cần phân loại

| Nhóm lỗi | Ví dụ | Phản ứng |
| --- | --- | --- |
| **Authentication failure** | Token expired, password rotate | Dừng, lấy credential hợp lệ theo policy |
| **Authorization denial** | Bot không có quyền invoice.submit | Không tự nâng quyền, mở request/review |
| **Target unavailable** | ERP timeout hoặc 5xx | Retry giới hạn, backoff, theo dõi |
| **Unknown transaction outcome** | Timeout sau khi gửi create invoice | Readback/idempotency thay vì gửi lại mù |
| **Unexpected UI state** | Nút chuyển vị trí, form khác | Fail-safe, cảnh báo, không click bừa |
| **Data validation failure** | Invoice không khớp PO | Quarantine và human review |
| **Duplicate event** | Queue gửi lại item cũ | Dedupe by business key/version |
| **Policy changed** | Owner revoke entitlement giữa run | Reauthorize tại action quan trọng |
| **Credential compromise** | Secret xuất hiện trong log | Incident, containment và rotation |
| **Runner compromised** | Runtime bị điều khiển | Cách ly, dừng job, thu hồi quyền |

### 26.2. At-least-once delivery không có nghĩa exactly-once effect

Một queue có thể gửi cùng item nhiều lần; một HTTP request có thể thành công nhưng response bị mất. Cần bảo vệ bằng **business idempotency key, target transaction state, optimistic locking và kiểm tra trước/sau**, tùy khả năng ứng dụng.

### 26.3. Mã giao dịch và đối soát

~~~text
jobId = invoice-batch-2026-12-01
runId = run-10042
businessItemId = supplier-81/invoice-2041
idempotencyKey = tenant-a:invoice-2041

Before create:
  Check whether invoice-2041 already exists.

After create:
  Read target transaction ID and status.

On timeout:
  Query by idempotency/business key before retry.
~~~

Một `runId` mới không nên làm hệ thống nhập **lại một hóa đơn đã thành công**, hoặc cấp hai entitlement cho cùng một request.

## 27. Audit và session evidence cho Robot account

### 27.1. Tách ba loại sự kiện

| Nguồn | Sự kiện | Ý nghĩa |
| --- | --- | --- |
| **IAM/IGA** | Robot approved, role changed, owner reassigned | Bằng chứng quản trị |
| **Orchestrator/runtime** | Job scheduled, run started, artifact version, retries | Bằng chứng chạy automation |
| **Target system** | Login, action, resource, transaction committed | Bằng chứng thao tác thực |

Cần **tương quan** cả ba, không chỉ đọc một bảng task log của orchestrator.

### 27.2. Audit event minh họa

~~~json
{
  "eventType": "ROBOT_BUSINESS_ACTION",
  "robotId": "robot-invoice-import-prod",
  "principalId": "rpa-invoice-prod",
  "principalType": "ROBOT_RPA",
  "orchestratorJobId": "invoice-batch-2026-12-01",
  "runId": "run-10042",
  "artifactRevision": "workflow-v17",
  "targetSystemId": "erp-finance",
  "tenantId": "tenant-a",
  "action": "invoice.draft.create",
  "resourceId": "invoice-2041",
  "businessOwnerTeam": "finance-operations",
  "humanApproverRef": "approval-601",
  "credentialRef": "vault://robots/invoice-prod",
  "authorizationResult": "PERMIT",
  "executionResult": "COMMITTED",
  "targetTransactionRef": "txn-8842",
  "occurredAt": "2026-12-01T01:15:00Z",
  "traceId": "trace-10442"
}
~~~

Đây là **schema minh họa**. `credentialRef` chỉ là tham chiếu không chứa bí mật. Không ghi raw password, OTP, session cookie, token hoặc dữ liệu khách hàng thô.

### 27.3. Decision không đồng nghĩa execution

~~~text
Authentication = SUCCESS
Authorization  = PERMIT
UI button click = SENT
Target operation = FAILED
Business transaction = NOT_COMMITTED
~~~

Tương tự, `role.revoked` trong IGA không tự chứng minh token cũ hoặc account đích đã hết quyền.

### 27.4. Chống chỉnh sửa bằng chứng

Có thể áp immutable/audit append-only, hash/manifest, tách quyền writer và reviewer, truy vết export, encryption và retention theo policy. **Hash không tự chứng minh bot đã thu đủ mọi thao tác**; completeness cần đối soát với target.

### 27.5. Người xem video bot cũng có quyền nhạy cảm

Session recording RPA có thể cho thấy tài khoản, dữ liệu khách hàng hoặc giao diện quản trị. Quyền replay/export phải được cấp riêng, có audit và giảm phạm vi nhạy cảm khi chia sẻ.

## 28. Reconciliation – phát hiện Robot account và quyền tồn dư

**Reconciliation** so sánh **desired state** từ robot registry/approval với **observed state** tại IdP, orchestrator, vault, SaaS/ERP, cloud IAM và cuối cùng **effective access**.

### 28.1. Trạng thái ba lớp

~~~text
DESIRED:
  robot-invoice-import-prod ACTIVE.
  Owner = finance-operations.
  Allowed on tenant-a: invoice.read, invoice.draft.create.
  No payment.approve.
  Credential scoped to ERP only.

OBSERVED:
  ERP account enabled.
  ERP roles: invoice.read, invoice.create, payment.approve.
  Old API client still active.
  Orchestrator has an unused legacy job.

EFFECTIVE:
  Can robot still approve payments?
  Can old token call ERP API?
  Can a former owner retrieve credential from vault?
~~~

### 28.2. Drift cần xử lý

| Phân loại | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| **ORPHAN_ROBOT** | Account còn, không có owner/process | Triage và thu hồi có kiểm soát |
| **EXTRA_ENTITLEMENT** | Bot có quyền payment.approve ngoài approval | Gỡ quyền và kiểm audit |
| **MISSING_ENTITLEMENT** | Bot thiếu quyền đọc đã được duyệt | Xác minh policy/target trước khi cấp |
| **STALE_CREDENTIAL** | Secret cũ vẫn dùng được sau rotation | Revoke/rekey, kiểm token |
| **RETIRED_ACCOUNT_ACTIVE** | Bot đã retire, ERP account còn enabled | Disable/revoke và readback |
| **WRONG_ENVIRONMENT** | Bot dev dùng credential prod | Chặn trust, tách môi trường |
| **CROSS_TENANT_GRANT** | Bot tenant-a có role tenant-b | Thu hẹp entitlement |
| **OWNER_LEAVER** | Owner/custodian rời tổ chức | Bàn giao, thu hồi human access |
| **ORCHESTRATOR_BYPASS** | Runner trực tiếp gọi target ngoài job policy | Chặn đường bypass, kiểm network/identity |
| **SESSION_RESIDUAL** | Job kết thúc nhưng target session còn | Terminate theo policy |
| **UNKNOWN_ACCESS** | Target API không trả quyền thực | Exception, không tự ghi PASS |
| **AUDIT_GAP** | Không nối runId với target action | Bổ sung event/correlation |

### 28.3. Khi nào bot retirement được coi VERIFIED?

Khi chứng cứ đủ chứng minh:

1. Không còn schedule, queue job hoặc authorized run mới.
2. Principal/certificate/token issuance không còn hợp lệ theo scope cần xóa.
3. Target account đã disable hoặc xóa và các role đã thu hồi.
4. Secrets/keys/alternate authentication methods đã xử lý.
5. Session/token còn hiệu lực được chặn hoặc hết hạn theo strategy được kiểm chứng.
6. Role local, API key, cloud trust, DB account và network exceptions đã được đối soát.
7. Audit/evidence được giữ lại đúng retention.
8. Những trạng thái UNKNOWN/residual có owner và remediation deadline.

**Không xóa record robot trong registry trước khi xác minh và lưu dấu vết**, vì mất dữ liệu để dò các tài khoản đích mồ côi.

## 29. SQL minh họa để tìm quyền robot thừa và thiếu

Giả định hệ quản trị có các bảng snapshot:

- `desired_robot_entitlement(robot_id, resource_id, entitlement_id)` chứa quyền được phê duyệt còn hiệu lực.
- `observed_robot_entitlement(robot_id, resource_id, entitlement_id)` chứa quyền thực tế tại target.
- Các bảng đã **đồng nhất định danh**, thời gian chụp snapshot, tenant và trạng thái trước khi so sánh.

### 29.1. Tìm quyền EXTRA

~~~sql
SELECT
    o.robot_id,
    o.resource_id,
    o.entitlement_id
FROM observed_robot_entitlement AS o
LEFT JOIN desired_robot_entitlement AS d
    ON d.robot_id = o.robot_id
   AND d.resource_id = o.resource_id
   AND d.entitlement_id = o.entitlement_id
WHERE d.robot_id IS NULL;
~~~

### 29.2. Tìm quyền MISSING

~~~sql
SELECT
    d.robot_id,
    d.resource_id,
    d.entitlement_id
FROM desired_robot_entitlement AS d
LEFT JOIN observed_robot_entitlement AS o
    ON o.robot_id = d.robot_id
   AND o.resource_id = d.resource_id
   AND o.entitlement_id = d.entitlement_id
WHERE o.robot_id IS NULL;
~~~

**Đây là truy vấn minh họa**, chưa phải hệ thống reconciliation production. Cần thêm khóa **tenant, environment, effectiveAt, snapshots, role expansion, grants qua group, deny rules, owner relationship và eventual consistency**. Không kết luận quyền đã hết khi target chưa đọc được hoặc có token/session còn hiệu lực.

## 30. Incident response khi robot bị lạm dụng hoặc nhiễm mã độc

### 30.1. Dấu hiệu

- Bot đăng nhập ngoài lịch hoặc từ runner không nằm trong inventory.
- Token/password xuất hiện trong logs, chat, source repository.
- Runner chạy artifact khác phiên bản được phê duyệt.
- Tăng đột biến số lần tạo/xóa dữ liệu hoặc export.
- Bot gọi target/tenant không nằm trong purpose.
- Một principal robot có nhiều phiên đồng thời không giải thích được.
- Bot đã retire nhưng vẫn có API call.
- Owner hoặc nhóm quyền bot bị thay không có change approval.
- Screenshot/session recording thiếu hoặc bị xóa ngoài chính sách.

### 30.2. Quy trình

1. Xác định robotId, principalId, runId, target, dữ liệu và thời gian.
2. Đánh giá mức độ ảnh hưởng tới nghiệp vụ; phối hợp SOC và business owner.
3. **Suspend robot execution** tại orchestrator khi cần.
4. **Contain credential/principal**: chặn token issuance, revoke roles/keys/certs hoặc network path phù hợp.
5. Ngăn job retry tự kích hoạt lại quyền trái policy.
6. Bảo vệ run logs, target audit, artifact version, session recording và custody evidence.
7. Kiểm transaction thật, duplicate jobs, quyền đã cấp cho principal khác và exfiltration.
8. Rotate/reissue credential sau khi runtime được làm sạch.
9. Rebuild/redeploy artifact từ nguồn đã được xác minh, đánh giá approval và SoD.
10. Reconcile desired/observed/effective access, hậu kiểm và chỉ resume khi được duyệt.

### 30.3. Không nhầm suspend scheduler với revoke security

Một attacker đã lấy được credential của bot có thể truy cập target trực tiếp ngay cả khi scheduler đã dừng. **Phải kiểm credential/role ở hệ đích**, không chỉ trạng thái của job.

### 30.4. Giữ bằng chứng và privacy

Không chia sẻ raw screenshots/logs chứa dữ liệu khách hàng qua kênh rộng. Áp quyền xem, retention, redaction có provenance và chain of custody theo quy trình.

## 31. Mẫu Java/Spring: chính sách trước khi chạy bot

Một kiến trúc Java có thể cung cấp **Robot Execution API** chịu trách nhiệm kiểm identity, policy, trạng thái bot và scope trước khi kích hoạt một run. Ví dụ sau dùng các class giả định để giải thích, **không phải ứng dụng độc lập có thể build ngay**.

### 31.1. Mô hình quyết định

~~~text
requestRun(authenticatedActor, robotId, target, jobDefinition):
    robot = registry.readCurrent(robotId)

    require actor is authorized to invoke this robot
    require robot.lifecycle == ACTIVE
    require robot.ownerIsCurrent
    require robot.policyVersionIsAccepted
    require jobDefinition.digestIsApproved
    require target within approved target set
    require requested actions within entitlements
    require environment/tenant matches robot policy
    require schedule/change window satisfied
    require high-risk approvals and SoD satisfied
    require robot not security blocked

    run = createUniqueRunIdAndStateGuard()
    enqueue run with immutable identity/target/scope references
    return run reference
~~~

Điều kiện policy phải lấy từ **backend có thẩm quyền**, không nhận `approved=true` từ request JSON.

### 31.2. Java service skeleton

~~~java
// Mẫu định hướng: các interface, class là abstraction minh họa.
@Service
class RobotRunService {

    private final RobotRegistry registry;
    private final RobotPolicy policy;
    private final RobotRunRepository runs;
    private final RobotRunOutbox outbox;

    @Transactional
    public RunResult requestRun(
            AuthenticatedActor actor,
            String robotId,
            RunRequest request) {

        RobotIdentity robot = registry.getCurrent(robotId);

        if (!robot.isActive() || !robot.hasCurrentOwner()) {
            return RunResult.denied("ROBOT_NOT_ELIGIBLE");
        }

        if (!policy.mayInvoke(actor, robot, request)) {
            return RunResult.denied("RUN_NOT_AUTHORIZED");
        }

        RobotRun run = runs.createPending(
            robot.id(),
            robot.policyRevision(),
            request.targetId(),
            request.tenantId(),
            request.artifactDigest()
        );

        outbox.appendRunRequested(run.id(), run.stateVersion());
        return RunResult.accepted(run.id());
    }
}
~~~

Thực tế cần **authorization trước mỗi hành động quan trọng**, transaction/outbox đúng cách, authentication, CSRF theo loại client, validation, concurrency guard, idempotency và audit. Việc API request được chấp nhận không tự bảo đảm job đã chạy hoặc đã thành công ở target.

### 31.3. Worker cần kiểm lại sau khi lấy job

~~~java
// PSEUDOCODE: nguyên tắc revalidation tại thời điểm thực thi.
void executePending(RobotRun run) {
    RobotIdentity robot = registry.getCurrent(run.robotId());

    if (!robot.isActive()
            || !policy.mayExecuteNow(robot, run)
            || run.isCanceled()
            || run.isStale()) {
        runs.markDenied(run.id(), "STATE_CHANGED");
        return;
    }

    CredentialHandle handle = credentialBroker.forRobot(
        robot.id(),
        run.targetId()
    );

    try {
        TargetOutcome outcome = targetConnector.execute(
            handle,
            run.approvedAction(),
            run.resourceScope(),
            run.idempotencyKey()
        );

        audit.recordRunOutcome(run.id(), outcome);
    } finally {
        handle.close();
    }
}
~~~

`CredentialHandle` không nhất thiết chứa password trong bộ nhớ app; có thể đại diện cho broker hoặc token ngắn hạn. Không log credential hoặc đưa nó vào exception. Cần kiểm việc target action có thực sự **được phép tại thời điểm gọi**.

### 31.4. Trường hợp identity là user trong ứng dụng

Nếu target bắt buộc bot user với password tương tác, backend nên yêu cầu **credential broker do tổ chức phê duyệt**, không đưa `username/password` xuống client JS hoặc lưu trong job payload. Không dựng logic bypass MFA/CAPTCHA.

## 32. Delegated robot: chạy thay người dùng

Một robot có thể được người dùng yêu cầu **thực hiện nghiệp vụ thay họ**. Khi đó có ít nhất hai chủ thể:

- **Human subject:** người có quyền trên tài nguyên.
- **Robot actor:** workload thực hiện thao tác kỹ thuật.

### 32.1. Kiểm đồng thời

~~~text
PERMIT delegated_report.export WHEN
    humanSubject.isAuthenticatedOrValidlyDelegated
    AND humanSubject.lifecycleStatus == ACTIVE
    AND humanSubject.mayExport(report)
    AND robotActor.isAuthenticated
    AND robotActor.isAllowedFor("report.export")
    AND delegation.validFor(
        humanSubject, robotActor, report, now
    )
    AND report.tenantId == humanSubject.tenantId
ELSE DENY
~~~

Không chỉ kiểm quyền của bot rồi cho phép export mọi báo cáo thay người; đó có thể là **confused deputy**.

### 32.2. Claim user không được tự khai

Một header như `X-Acting-User=person-101` không thể trở thành chứng cứ ủy quyền nếu client tự gửi. Cần cơ chế **delegated token, token exchange hoặc signed trusted context** theo khả năng hệ thống và policy.

### 32.3. User Mover/Leaver giữa workflow

Một batch được mở lúc nhân viên còn ACTIVE có thể tiếp tục sau khi họ nghỉ. Cần xác định:

- Nhiệm vụ có thể tiếp tục do **business owner của robot** không?
- Quyền còn dựa vào user riêng hay đã chuyển sang một job chính thức của tổ chức?
- Approval có đúng action/expiry không?
- Có cần cancel, change owner, hoặc reauthorize?
- Có dữ liệu cá nhân/token của người cũ đang được dùng?

**Không tự giả định mọi job phải hủy hoặc mọi job được phép tiếp tục**; phân biệt business workflow độc lập và quyền ủy quyền từ người dùng.

## 33. Case study: robot xử lý hóa đơn nhà cung cấp

Giả sử tổ chức có ERP, cổng nhà cung cấp SaaS, IdP SSO, vault, RPA orchestrator và IAM/IGA.

### 33.1. Joiner – triển khai robot mới

Đội Finance đăng ký `robot-invoice-import-prod` để nhập bản nháp hóa đơn:

- Business owner xác định mục đích: giảm nhập liệu thủ công.
- ERP owner duyệt `invoice.read` và `invoice.draft.create` chỉ tenant-a.
- Security kiểm dữ liệu cá nhân, SoD và giới hạn không được payment approve.
- Technical owner tạo bot workflow v1, lưu credentialRef trong vault.
- IdP/ERP provision account bot được phân loại non-human.
- Orchestrator chỉ cho runner production được phép lấy credential.
- Test chạy trên dữ liệu thử, xác minh target audit và idempotency.
- Reconciliation đọc lại ERP roles, không phát hiện quyền thừa.

### 33.2. Tác vụ có người duyệt

Robot đọc dữ liệu hóa đơn, phát hiện khớp PO, tạo bản nháp. Khi cần submit/payment approval:

- Robot tạo yêu cầu phê duyệt cho một người có thẩm quyền.
- Người duyệt xác thực SSO/MFA theo policy.
- Approval gắn đúng hóa đơn, action và expiry.
- PEP kiểm SoD: người tạo dữ liệu không tự approve nếu policy cấm.
- Robot có thể tiếp tục bước đã duyệt trong đúng phạm vi.

### 33.3. Mover – owner chuyển bộ phận

Technical owner ban đầu chuyển sang đội mới:

- Gỡ quyền sửa workflow/vault/repo của người cũ.
- Chuyển owner và alert contact.
- Rà credential đã từng xem, rotate nếu rủi ro.
- Không tắt bot khi Finance vẫn cần.
- So approved scope của robot với role ERP thực tế.

### 33.4. Leaver – người duyệt nghỉ việc

Một human approver đã Leaver. Robot không được tái dùng approval cũ ngoài scope hoặc sau expiry; approval workflow định tuyến tới approver hiện hành. Token của người nghỉ không được đưa vào runner.

### 33.5. Bot retire

Finance chuyển sang ERP API integration mới, RPA không còn cần:

- Chặn schedule và queue mới; hoàn tất hoặc xử lý in-flight jobs.
- Gỡ bot credentials, client registrations, ERP role và orphan session.
- Kiểm quyền không tồn dư trong ERP và vault.
- Lưu audit theo retention.
- Cập nhật owner inventory và đóng process.

### 33.6. Incident: double invoice

Một lần kết nối timeout làm orchestrator retry. Nếu target đã tạo hóa đơn trước timeout, retry có thể tạo duplicate. Quy trình xử lý đúng là **query theo business idempotency key**, đối chiếu transaction và không tự tiếp tục trên trạng thái không chắc chắn.

## 34. KPI cho quản trị robot account

| KPI | Ý nghĩa | Sai lầm cần tránh |
| --- | --- | --- |
| **Robot identity ownership coverage** | Robot có business/technical owner hợp lệ | Đếm account không có owner |
| **Approved entitlement coverage** | Quyền có resource approval, scope, expiry | Chỉ kiểm role đã tồn tại |
| **Orphaned robot account count** | Account không còn process/job/owner | Giữ role mãi vì không ai phản hồi |
| **Credential age / rotation success** | Secret/cert được quản lý đúng chính sách | Chỉ đo job rotate đã chạy |
| **Unattended bot account reuse** | Số robot dùng chung principal quá mức | Mất attribution |
| **Production/staging identity separation** | Tách account và trust theo environment | Copy prod credential sang test |
| **Privileged robot access duration** | Thời gian quyền cao có hiệu lực | Quyền admin thường trực |
| **Job-to-target attribution coverage** | Run có liên kết target transaction | Chỉ lưu tên bot |
| **Authorization denial anomalies** | Bot gọi ngoài scope/tenant | Coi tất cả DENY là lỗi UX |
| **Retirement-to-revocation latency** | Từ retire tới effective access bị chặn | Chỉ dừng scheduler |
| **Residual credential/role count** | Token, key, local role còn sau revoke | Không readback |
| **Robot security incident response latency** | Phát hiện và containment | Có alert nhưng không ai nhận |
| **Reconciliation completeness** | Có dữ liệu target, UNKNOWN được phân loại | Tự đánh dấu PASS khi API lỗi |
| **Duplicate business transaction rate** | Job retry gây tác động trùng | Chỉ đo HTTP thành công |
| **Owner JML handover latency** | Khi owner Mover/Leaver có bàn giao | Disable IdP là đủ |
| **Review/SoD exception age** | Item quyền nhạy cảm chưa xử lý | Gia hạn vô hạn |

Một dashboard chỉ đo **số job hoàn thành** không cho biết hệ thống có an toàn. Cần theo dõi **quyền, owner, credential, hiệu lực thu hồi và chất lượng evidence**.

## 35. Ma trận kiểm thử âm tính

| Ca kiểm thử | Điều kiện | Kỳ vọng |
| --- | --- | --- |
| Bot chưa có owner | Request tạo production account | DENY/OWNER_UNRESOLVED |
| Người tạo bot chưa được duyệt | Tự thêm ERP admin role | DENY |
| Account cá nhân được dùng làm unattended bot | Scheduler yêu cầu lưu user password | Chặn hoặc chuyển sang mô hình được phê duyệt |
| Attended bot chạy sau user Leaver | Dùng lại session/cookie cũ | DENY hoặc invalidated |
| Unattended bot cần MFA tương tác | Không có flow bot được hỗ trợ | Không bypass MFA/CAPTCHA |
| Robot scope READ gọi `payment.approve` | Role không đủ | DENY |
| Bot tenant-a truy cập tenant-b | Sai tenant | DENY |
| Robot dev gọi ERP prod | Môi trường không phù hợp | DENY |
| Bot bị SUSPENDED | Scheduler retry job | Không chạy |
| Robot đã RETIRED | Queue message cũ | Không tái provision |
| Owner Leaver | Account bot vẫn ACTIVE | Handover + credential assessment |
| Owner cũ vẫn có vault read | Đã Mover | Thu hồi và verify |
| Runner không được phép | Yêu cầu lấy secret bot | DENY |
| Script artifact bị thay | Digest khác approved | Không execute, alert |
| Hai run tạo cùng hóa đơn | Retry không chắc trạng thái | Idempotency/readback ngăn duplicate |
| ERP báo timeout | Không rõ transaction outcome | Không retry mù |
| Target UI đổi bất ngờ | Form/nút không khớp | Fail-safe, human review |
| SSO login bot bị policy deny | Người quản trị muốn tắt MFA toàn tenant | Không chấp nhận bypass rộng |
| Robot có access key dài hạn lộ trong log | Incident | Contain, rotate, check tokens |
| Stop scheduler nhưng API key còn hoạt động | Retire | RESIDUAL_ACCESS |
| SCIM disable bot nhưng cookie còn | Session cache | Revoke/invalidate/TTL strategy |
| Bot không có job 6 tháng | Account vẫn role admin | Access review/retire |
| Client OAuth issuer đúng nhưng audience sai | Token API-X sang API-Y | Reject |
| Identity spoof bằng HTTP header | Gửi `X-Robot-Id=admin` | Không tin header untrusted |
| Bot dùng approval ngoài resource | Invoice khác với approved invoice | DENY |
| Người vừa tạo hóa đơn tự phê duyệt qua bot | SoD conflict | DENY hoặc independent approval |
| Bot xuất dữ liệu ngoài vùng cho phép | Egress/file ACL không phù hợp | DENY và alert |
| Credential được rotate nhưng secret cũ vẫn dùng được | Old key active | Revoke/reconcile |
| Orchestrator logs có runId nhưng target không ghi principal | Missing attribution | Audit gap exception |
| Target API không trả observed roles | Không thể verify | UNKNOWN, không tự PASS |
| Bot nối trực tiếp target ngoài PAM | Direct privileged access | Block hoặc cảnh báo ngoại lệ |
| Service account quá rộng từ legacy | Đang cần migration | Phân quyền lại và review |
| Người không có quyền replay video | Truy cập session recording | DENY và audit |
| Bot tạo user qua IAM không có ticket hợp lệ | Process xin `user.create` | DENY |
| Target account bị xóa trước log retention | Cần điều tra | Evidence vẫn truy xuất theo policy |

### 35.1. Kiểm thử end-to-end

~~~text
Business owner request
  -> robot registry + resource approval
  -> principal provisioning + vault/issuer
  -> orchestrator trusted runner + artifact
  -> target authentication + authorization
  -> runId + business transaction evidence
  -> owner/process change or retirement
  -> deactivate/revoke at target
  -> reconcile observed/effective access
  -> audit and closure
~~~

**Test login success không đủ**. Hãy kiểm thêm trường hợp wrong role, wrong tenant, owner Leaver, token cũ, job replay, credential compromise và retirement.

## 36. Checklist triển khai Robot account

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Robot có ID riêng và phân loại non-human? | Registry/principal type |
| Đã phân biệt attended và unattended? | Execution mode và auth model |
| Business owner, technical owner, resource owner được xác minh? | Owner registry |
| Có mô tả purpose, target, schedule, environment, tenant? | Registration |
| Permission được phê duyệt theo action/scope/expiry? | Resource approval |
| Có SoD giữa bot executor và người duyệt? | Business policy và test |
| Có ngăn dùng account cá nhân cho bot nền? | Account policy và scan |
| Có xác thực theo flow vendor hỗ trợ? | IdP/SSO/API design |
| Có tránh bypass MFA/CAPTCHA? | Approved authentication pattern |
| Credential/secret có nằm ngoài code/log? | Vault/issuer configuration |
| Runner được chứng thực trước khi dùng secret? | Runtime attestation/access logs |
| Có tách credential per target và tenant? | Secret inventory |
| Có rotation và token/session follow-up? | Credential lifecycle |
| SCIM/API connector biết xử lý loại account này? | Capability matrix |
| Target group/role đã được đọc lại sau provision? | Reconciliation |
| Có policy runtime cho action/resource? | PEP/PDP tests |
| Bot privileged có JIT/PAM/recording phù hợp? | Privileged workflow |
| Có cơ chế khi user Mover/Leaver? | HRIS-IGA event mapping |
| Owner Leaver có bàn giao và kiểm secret từng biết? | Handover audit |
| Robot retire có gỡ account, token, vault grants? | Revocation readback |
| Có giới hạn concurrent jobs và idempotency? | Retry/duplicate tests |
| Artifact/job changes có approval và version? | Deployment attestation |
| Có audit robot principal và runId ở target? | Correlation trace |
| Có tách authorization PERMIT và transaction COMMITTED? | Event schema |
| Screenshot/recording được bảo vệ và lưu theo hạn? | Privacy/retention policy |
| Có cảnh báo bot chạy ngoài giờ/target/tenant? | SOC detection rules |
| Có phân loại UNKNOWN khi target unavailable? | Reconciliation exceptions |
| Có phát hiện orphaned account/unused bot? | Inventory report |
| Có case study/diễn tập compromised credential? | Incident runbook |
| Có kiểm endpoint ngoài orchestrator/PAM? | Bypass tests |
| Có owner và SLA cho mọi residual access? | Remediation tracking |

## 37. Những nhầm lẫn thường gặp

1. **“Robot account là một nhân viên ảo.”** Nó là non-human identity, có owner và scope riêng.
2. **“Bot tự động nên không cần phê duyệt.”** Automation vẫn cần quyền đúng mục đích.
3. **“Dùng account người viết script là nhanh và an toàn.”** Gây lỗi JML, attribution và credential.
4. **“Attended robot và unattended robot có cùng mô hình xác thực.”** Ngữ cảnh user delegation khác identity nền.
5. **“Bot không cần MFA thì cứ tắt MFA toàn hệ thống.”** Phải dùng flow được vendor/policy hỗ trợ.
6. **“CAPTCHA hiện ra thì cứ lách bằng script.”** Thay thế bằng integration được cho phép.
7. **“Một account admin dùng cho mọi robot dễ quản trị.”** Tăng blast radius và mất phân tách.
8. **“Robot chỉ có permission READ thì không thể làm sai.”** Read có thể bao gồm dữ liệu nhạy cảm hoặc export.
9. **“Robot tạo và duyệt hóa đơn cũng được vì nó không phải người.”** SoD vẫn áp dụng.
10. **“Orchestrator báo SUCCESS thì giao dịch target đã commit.”** Cần transaction readback.
11. **“Stop job nghĩa revoke account.”** Account/credential vẫn có thể hoạt động.
12. **“Disable account IdP nghĩa token và session SaaS hết ngay.”** Tùy cơ chế target.
13. **“SCIM quản lý được mọi robot principal.”** Có target chỉ hỗ trợ API native hoặc OAuth client.
14. **“Rotate password nghĩa key/token cũ không dùng được nữa.”** Cần kiểm từng loại credential.
15. **“Owner Leaver thì xóa robot production.”** Cần chuyển owner và giữ workload hợp lệ.
16. **“Robot không phải người nên không cần access review.”** Có thể có quyền cực cao và bị bỏ quên.
17. **“Tên robot trong header chứng minh caller.”** Phải xác thực principal.
18. **“Một token đúng issuer có thể dùng cho mọi target.”** Kiểm audience, scope và tenant.
19. **“Chỉ cần audit login của bot.”** Cần runId và target action/transaction.
20. **“Một screenshot là bằng chứng đủ mọi hành động.”** Phải đối chiếu target audit.
21. **“Chạy lại job luôn an toàn.”** Có thể gây giao dịch trùng.
22. **“Bot có thể giữ quyền cũ sau khi chuyển process.”** Mover của robot phải rà lại.
23. **“Owner approval hợp lệ thì policy DENY không còn tác dụng.”** Không được vượt security constraints.
24. **“Có vault nghĩa bí mật không bao giờ bị lộ.”** Runner/memory/log vẫn có nguy cơ.
25. **“Robot idle nhiều tháng thì khỏi cần kiểm.”** Dễ tạo account mồ côi.
26. **“Xóa account thì có thể xóa luôn audit.”** Retention và chain of custody có vòng đời khác.
27. **“Quota hoàn thành job là KPI bảo mật.”** Cần ownership, privilege, rotation, residual rights.

## 38. Câu hỏi tự đánh giá

1. Robot account là gì và vì sao thuộc nhóm non-human account?
2. Attended và unattended RPA khác nhau về identity và authentication như thế nào?
3. Vì sao không nên dùng password của nhân viên để chạy bot ban đêm?
4. Một robot cần business owner, technical owner và resource owner để làm gì?
5. Phân biệt robotId, accountId, runtime instance và orchestrator runId.
6. Tại sao runId không phải bằng chứng xác thực danh tính?
7. Các dữ liệu nào cần ghi trong robot registry và không nên ghi loại bí mật nào?
8. Nếu target không hỗ trợ machine-to-machine auth, cần thiết kế thế nào?
9. Vì sao lách CAPTCHA/MFA không phải mô hình ổn định cho unattended robot?
10. Một bot có role invoice.create nhưng không payment.approve: SoD cần kiểm gì?
11. Approval có thể bị bỏ qua nếu tài khoản robot đã được provision không?
12. Trong Joiner của nhân viên, điều kiện nào trước khi họ được quản trị robot?
13. Mover của technical owner khác thay đổi quyền truy cập của bot ra sao?
14. Khi người từng giữ password robot Leaver, việc gì cần làm ngoài disable IdP?
15. Khi bot chuyển CRM sang ERP, tại sao phải gỡ role CRM cũ?
16. Thứ tự retire bot để không mất chứng cứ nhưng thu hồi quyền là gì?
17. Khi bot dùng JIT admin để sửa hệ thống, policy cần kiểm những trường nào?
18. Vì sao session recording không thay thế API authorization?
19. Bot chạy từ production runner có thể được phép dùng credential staging không?
20. Retry request tạo hóa đơn sau timeout có thể gây rủi ro gì?
21. Idempotency key khác với runId như thế nào?
22. Phân biệt authentication success, authorization PERMIT và business COMMITTED.
23. Một bot dùng token đã rotate có thể vẫn gọi API không? Vì sao?
24. Ba loại sự kiện nào nên nối để điều tra hoạt động robot?
25. Screenshot UI của robot có các rủi ro bảo mật/quyền riêng tư nào?
26. Nêu các trường audit để xác định ai duyệt và bot nào thực hiện một giao dịch.
27. Reconciliation phân biệt DESIRED, OBSERVED và EFFECTIVE quyền robot thế nào?
28. Một tài khoản ERP còn enabled sau khi job bị xóa là loại drift gì?
29. Khi phát hiện runner bị chiếm, tại sao chỉ suspend scheduler chưa đủ?
30. Nêu ba negative tests cho owner Leaver, wrong tenant và retired account.
31. Một attended robot muốn export báo cáo thay user cần kiểm những chủ thể nào?
32. Hãy thiết kế KPI đo chất lượng thu hồi quyền robot, không chỉ số lượng job thành công.

## 39. Ghi nhớ

**Robot account** là **tài khoản/danh tính dành cho phần mềm tự động thực hiện tác vụ đã được định nghĩa**, đặc biệt trong RPA, thuộc nhóm **Non-human account**. Robot có thể là **attended** sử dụng ngữ cảnh người dùng hợp lệ hoặc **unattended** chạy bằng identity riêng; không nên dùng lại password/session của người thật, không nên dùng một account toàn quyền cho nhiều bot và không được lách cơ chế MFA/SSO mà ứng dụng yêu cầu. Mỗi robot cần **business purpose, owner, resource approval, scope/action/tenant/environment, credential quản trị an toàn, trạng thái vòng đời và audit theo run ID**.

Trong IAM **Joiner–Mover–Leaver**, **HRIS/identity proofing** quản lý danh tính người chịu trách nhiệm; **IdP/SSO, SCIM/API** quản lý phần account và provisioning mà target hỗ trợ; **RBAC/ABAC/PBAC và PEP** giới hạn quyền khi robot hoạt động; **PAM/JIT** bảo vệ tác vụ đặc quyền; **reconciliation** xác minh quyền thực tế và rủi ro tồn dư. **Owner Leaver không tự biến robot thành Leaver; dừng job không tự thu hồi account; đổi secret không tự vô hiệu mọi token; quyết định REVOKE không chứng minh quyền đã bị chặn tại target.** Mục tiêu là robot **đúng danh tính, đúng nhiệm vụ, đúng quyền, đúng thời điểm, có người chịu trách nhiệm và không giữ quyền sau khi nhu cầu kết thúc**.
