# Provisioning nhiều hệ thống trong vòng đời danh tính IAM

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích **provisioning nhiều hệ thống** là gì và tại sao cấp tài khoản ở **Identity Provider (IdP)** chưa đủ để người dùng có đúng quyền tại mọi ứng dụng.
- Phân biệt **danh tính**, **tài khoản**, **group/role**, **entitlement**, **thông tin xác thực**, **phiên** và **trạng thái truy cập thực tế** tại từng hệ thống đích.
- Thiết kế luồng cấp phát từ nguồn có thẩm quyền thông qua điều phối IAM/IGA đến **directory, IdP, ứng dụng SaaS, cloud IAM, VPN và hệ thống nội bộ**.
- Lựa chọn cơ chế tích hợp như **SCIM, API đặc thù, directory/group synchronization, Just-in-Time provisioning và quy trình thủ công có kiểm soát**, hiểu giới hạn của từng cơ chế.
- Xử lý **Joiner–Mover–Leaver (JML)** khi một phần hệ thống thành công, một phần thất bại; kiểm soát sự kiện đến trễ/lặp, cấp quyền nhầm, quyền tích lũy và phiên tồn dư.
- Thiết kế **desired state, observed state, reconciliation, audit trail, giám sát và chỉ số** để chứng minh các quyền đã được thực thi đúng.

## 1. Provisioning nhiều hệ thống là gì?

**Account provisioning** là quá trình tạo, kích hoạt, cấu hình, cập nhật hoặc vô hiệu hóa tài khoản tại một hay nhiều hệ thống để phục vụ nhu cầu truy cập hợp lệ. **Provisioning nhiều hệ thống** (multi-system provisioning) mở rộng quá trình này tới một hệ sinh thái gồm nhiều ứng dụng, nền tảng và mô hình quyền, thường có **giao thức, API, danh mục tài khoản, thời gian xử lý và giới hạn kỹ thuật khác nhau**.

Ví dụ, nhân viên mới bắt đầu làm ở bộ phận tài chính có thể cần:

1. Danh tính doanh nghiệp đã được xác minh và một account tại IdP.
2. Email, lịch làm việc và công cụ cộng tác.
3. Tài khoản ERP và quyền xem hóa đơn của đơn vị đang phụ trách.
4. Quyền VPN phù hợp với thiết bị và điều kiện an toàn.
5. Quyền xem báo cáo trên nền tảng phân tích.
6. Một số quyền riêng theo dự án có phê duyệt và ngày hết hạn.

Việc tạo tài khoản ở IdP chỉ mới hoàn thành **một phần**. Nếu ERP không nhận được sự kiện tạo user, nhân viên vẫn không dùng được ERP. Nếu ERP tạo account nhưng nhầm role quản trị, việc đăng nhập thành công lại dẫn tới **truy cập quá mức**.

Trong module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, provisioning nhiều hệ thống phải liên kết **nguồn dữ liệu nhân sự, xác minh danh tính, quy tắc cấp quyền, đồng bộ IdP/SSO/SCIM, RBAC/ABAC, tài khoản dịch vụ và kiểm toán**. Điều quan trọng nhất là quản lý cùng một danh tính qua các lần **Joiner, Mover, Leaver** và hạn chế **quyền truy cập tồn dư**.

### 1.1. Những đối tượng cần phân biệt

| Đối tượng | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Identity** | Chủ thể là ai trong tổ chức? | Identity ID nội bộ của nhân viên |
| **Account** | Chủ thể có bản ghi tài khoản ở hệ thống nào? | IdP user, ERP user, VPN principal |
| **Authenticator/credential** | Chủ thể chứng minh quyền đăng nhập bằng cách nào? | Passkey, MFA, chứng chỉ, secret của workload |
| **Group/role** | Chủ thể được gán vào nhóm hoặc vai trò nào? | FinanceReader, ProjectContributor |
| **Entitlement** | Quyền cụ thể có thể thực thi là gì? | Đọc hóa đơn, truy cập repository, tạo báo cáo |
| **Session/token** | Phiên và chứng cứ truy cập đang tồn tại? | Phiên SaaS, OAuth access token |
| **Policy** | Vì sao được cấp/giữ/từ chối quyền? | RBAC, ABAC, SoD, approval |
| **Provisioning task** | Hành động cần thực thi ở đâu? | Create, update, assign, revoke, disable |
| **Observed state** | Hệ thống đích thực tế đang có gì? | User vẫn active, role cũ chưa bị gỡ |

Một **identity** có thể liên kết với nhiều account; mỗi account có nhiều entitlement. Account hợp lệ cũng có thể có quyền sai. Vì vậy, trạng thái “tài khoản đã được tạo” không đủ để kết luận provisioning hoàn tất.

### 1.2. Tại sao không thể giả định mọi hệ thống giống nhau?

Một ứng dụng có thể sử dụng group từ IdP để quyết định quyền. Ứng dụng khác có user và role độc lập. Một hệ thống hỗ trợ **SCIM** để tạo user nhưng yêu cầu API riêng để cấp license hoặc role. Có ứng dụng tạo account khi SSO đăng nhập lần đầu; có nền tảng cần chuẩn bị account trước đó. Một số hệ thống legacy chỉ hỗ trợ thao tác thủ công.

Điều phối provisioning phải biết **năng lực và giới hạn cụ thể của từng hệ thống đích** thay vì dùng một thao tác chung cho tất cả.

## 2. Kiến trúc tổng thể

~~~mermaid
flowchart TD
    A["HRIS / nguồn nhà thầu / service registry"] -->|"Sự kiện và thuộc tính JML"| B["Identity registry / IGA"]
    B --> C["Xác minh identity, policy, approval"]
    C --> D["Tính desired access và lập kế hoạch"]
    D --> E["Provisioning orchestrator"]
    E --> F["IdP / directory / groups"]
    E --> G["SaaS qua SCIM"]
    E --> H["Ứng dụng qua API riêng"]
    E --> I["Cloud / VPN / hạ tầng"]
    E --> J["Legacy: tác vụ có kiểm soát"]
    F --> K["Đọc observed state"]
    G --> K
    H --> K
    I --> K
    J --> K
    K --> L{"Desired = Observed?"}
    L -->|"Không"| M["Retry, exception, remediation"]
    M --> E
    L -->|"Có"| N["Xác minh, audit, đóng workflow"]
    C --> O["Audit / SIEM"]
    E --> O
    K --> O
~~~

Các thành phần có trách nhiệm khác nhau:

- **Nguồn có thẩm quyền:** HRIS hoặc nguồn quản lý hợp đồng cung cấp trạng thái, quan hệ việc làm, bộ phận, chức vụ, người quản lý và thời gian hiệu lực; service registry có thể là nguồn vòng đời workload.
- **Identity registry / Identity Governance and Administration (IGA):** liên kết chủ thể với account, theo dõi thay đổi JML, phê duyệt, tính toán và chứng nhận quyền.
- **IdP / directory:** quản lý định danh/tài khoản trong phạm vi của nó và xác thực; có thể là nguồn nhóm/claim cho một số ứng dụng.
- **Provisioning orchestrator:** phân rã mục tiêu thành thao tác theo từng hệ thống, theo dõi trạng thái, retry, phụ thuộc và ngoại lệ.
- **Connector/adapter:** chuyển ý định thành SCIM, API ứng dụng, lệnh quản trị cloud/directory hoặc nhiệm vụ thủ công.
- **Hệ thống đích:** lưu account, role, ACL, session và quyền hiệu lực của chính nó.
- **Reconciliation:** đọc lại trạng thái đích và so sánh với mục tiêu; không chỉ dựa trên phản hồi “đã nhận yêu cầu”.

**SSO không đồng nghĩa provisioning.** SSO (ví dụ qua OIDC/SAML) cho phép ứng dụng dựa vào kết quả xác thực từ IdP. Việc user có account và role phù hợp tại ứng dụng cần được giải quyết bằng cơ chế provisioning hoặc chính sách của ứng dụng.

## 3. Nguồn dữ liệu, định danh và liên kết tài khoản

### 3.1. Dữ liệu đầu vào tối thiểu

Trước khi cấp tài khoản tại nhiều hệ thống, cần biết **chủ thể nào**, **mối quan hệ với tổ chức**, **vai trò hiện tại**, **thời gian có hiệu lực** và **quyền nào được phê duyệt**.

| Trường | Mục đích | Rủi ro khi thiếu |
| --- | --- | --- |
| identityId | Định danh bền vững của chủ thể trong IAM | Nhầm người, account mồ côi |
| sourceSystem, sourceRecordId | Liên kết tới nguồn có thẩm quyền | Không biết ai chịu trách nhiệm |
| employmentRelationshipId | Phân biệt các quan hệ làm việc/pháp nhân | Gỡ nhầm hoặc giữ nhầm quyền |
| workerType | Phân biệt nhân viên, nhà thầu, khách mời | Cấp quyền mẫu quá rộng |
| lifecycleStatus | Biết Joiner, Mover, Leaver hoặc trạng thái hạn chế | Kích hoạt quyền khi không còn hợp lệ |
| effectiveAt | Thời điểm trạng thái/quyền phải có hiệu lực | Cấp quá sớm hoặc thu hồi muộn |
| department, jobFunction, project | Đầu vào RBAC/ABAC | Gán sai role hoặc quyền dữ liệu |
| managerId / sponsorId | Người chịu trách nhiệm xác nhận nhu cầu | Quyền không có owner/phê duyệt |
| sourceVersion / eventId | Bảo vệ khỏi sự kiện cũ, trùng | Cấp lại quyền đã thu hồi |

**Không nên dùng email hoặc display name làm khóa liên kết duy nhất**: chúng có thể đổi hoặc tái sử dụng. Mỗi hệ thống đích thường có accountId riêng; IAM cần bảng liên kết identityId → targetSystem + targetAccountId, kèm trạng thái và nguồn bằng chứng.

### 3.2. Bản đồ account

Ví dụ một danh tính đã được đối chiếu:

~~~yaml
identityId: "person-2048"
identityType: "HUMAN"
source:
  system: "HRIS"
  recordId: "employee-5310"
  version: 14
lifecycle:
  status: "ACTIVE"
  effectiveAt: "2026-11-23T08:00:00+07:00"
accountLinks:
  - targetSystem: "Enterprise-IdP"
    targetAccountId: "idp-user-981"
  - targetSystem: "ERP"
    targetAccountId: "erp-user-114"
  - targetSystem: "Analytics"
    targetAccountId: "analytics-user-772"
~~~

Đây là **schema minh họa**. Nếu chưa có targetAccountId khi tạo mới, hệ thống cần tạo account có kiểm soát, lấy ID thực tế và lưu liên kết. Khi phát hiện account đã tồn tại, không tự liên kết chỉ vì trùng email: cần bằng chứng và quy tắc xác minh chủ thể để tránh **account takeover**.

## 4. Phân tách provisioning tài khoản và cấp quyền

Một task provisioning nên mô tả rõ **đối tượng và loại hành động**, ví dụ:

| Task | Tác động | Điều kiện cần |
| --- | --- | --- |
| CREATE_ACCOUNT | Tạo user ở hệ thống đích | Identity hợp lệ, chưa có account liên kết chính xác |
| ACTIVATE_ACCOUNT | Mở account khi được phép | Đến effectiveAt, đủ proofing/approval |
| UPDATE_PROFILE | Đồng bộ thuộc tính, manager, department | Dữ liệu nguồn mới nhất, mapping hợp lệ |
| ADD_GROUP | Gán nhóm | Nhóm được phê duyệt và thuộc đúng tenant |
| GRANT_ENTITLEMENT | Cấp role/permission cụ thể | Policy, SoD, owner, hạn sử dụng |
| REVOKE_ENTITLEMENT | Gỡ quyền không còn hợp lệ | Căn cứ từ desired state mới nhất |
| SUSPEND_ACCOUNT | Chặn/giới hạn account theo chính sách | Tình huống nghiệp vụ/bảo mật có thẩm quyền |
| DEACTIVATE_ACCOUNT | Vô hiệu hóa account khi Leaver | Phạm vi hệ thống, thời điểm, phiên/token |
| DELETE_ACCOUNT | Xóa tài khoản nếu chính sách cho phép | Lưu giữ dữ liệu, phụ thuộc, bằng chứng |
| REVOKE_SESSION_TOKEN | Hủy phương thức truy cập còn hiệu lực | Cơ chế được hệ thống đích hỗ trợ |

**Cấp account ≠ cấp entitlement; vô hiệu hóa account ≠ tự động xóa mọi token/phiên.** Việc này cần được thể hiện trong nhiệm vụ và kiểm chứng riêng ở hệ thống hỗ trợ.

### 4.1. Quyền mong muốn

Một mô hình **desired state** có thể được tính dựa trên vai trò và thuộc tính:

~~~text
identity: person-2048
relationship: EMPLOYEE at Finance
lifecycleStatus: ACTIVE
approvedDesiredAccess:
  Enterprise-IdP:
    account: ENABLED
    groups: [Workforce, Finance]
  ERP:
    account: ENABLED
    entitlements: [InvoiceRead]
  Analytics:
    account: ENABLED
    entitlements: [FinanceDashboardRead]
  Cloud-Production:
    entitlements: []
~~~

Ví dụ trên không cấp quyền production cloud chỉ vì người đó thuộc Finance. Tập quyền là kết quả của **least privilege, RBAC/ABAC, phê duyệt và điều kiện môi trường**.

### 4.2. Quyền thực tế

**Observed state** là dữ liệu đọc được tại từng đích. Nếu ERP vẫn có role InvoiceAdmin, dù desired là InvoiceRead, IAM phải phát hiện **EXTRA_ACCESS** và xử lý theo quy trình. Nếu tài khoản Analytics chưa được tạo, đó là **MISSING_ACCESS**. Hai loại sai lệch có mức độ rủi ro khác nhau và cần ưu tiên khác nhau.

## 5. Các cơ chế tích hợp provisioning

### 5.1. SCIM

**SCIM (System for Cross-domain Identity Management)** là tập tiêu chuẩn hỗ trợ quản lý tài nguyên như **Users** và **Groups** thông qua giao diện định nghĩa trước. Trong các triển khai tương thích, client có thể tạo user, đọc trạng thái, cập nhật thuộc tính, quản lý nhóm hoặc vô hiệu hóa bằng thao tác phù hợp.

Ví dụ tài nguyên User rút gọn **minh họa**:

~~~json
{
  "userName": "employee-5310@enterprise.example",
  "externalId": "person-2048",
  "name": {
    "givenName": "An",
    "familyName": "Nguyen"
  },
  "active": true
}
~~~

Không mặc định mọi ứng dụng hỗ trợ toàn bộ schema, Group, PATCH hay cơ chế xóa; cần xác minh **khả năng thực tế của SCIM provider**. Trường **active** trong tài nguyên SCIM nói về user/account tại hệ thống SCIM, không tự biểu thị mọi trạng thái HRIS. Việc cập nhật active hoặc Group **không bảo đảm** thu hồi role ngoài SCIM, phiên hoặc OAuth token đã phát hành.

### 5.2. API riêng của ứng dụng

Một số SaaS cung cấp REST/GraphQL/API quản trị hoặc endpoint đặc thù để cấp license, role, project membership. Connector phải:

- Ánh xạ chuẩn giữa đối tượng IAM và tài khoản/permission thực tế.
- Xác thực API bằng danh tính dịch vụ được bảo vệ, quyền tối thiểu.
- Xử lý phân trang, lỗi nghiệp vụ, giới hạn tốc độ và timeout.
- Kiểm tra kết quả ghi, tránh giả định HTTP 200/202 nghĩa là quyền đã có hoặc đã mất.
- Ghi request ID, trạng thái thao tác và mã lỗi an toàn.

Nếu một thao tác bất đồng bộ trả về mã tác vụ, orchestrator cần theo dõi tác vụ tới khi hoàn tất hoặc có lỗi rõ ràng, rồi đối soát.

### 5.3. Đồng bộ directory, group hoặc role

Một số ứng dụng lấy group từ directory/IdP và ánh xạ group sang role ứng dụng. Cần quản trị **group mapping**, nhóm lồng nhau, tenant, độ trễ đồng bộ và phân biệt thay đổi group với thay đổi quyền cuối.

Ví dụ nhóm **FinanceReportsReaders** ở IdP có thể được ánh xạ thành role ReportReader tại ứng dụng A nhưng thành quyền rộng hơn nếu cấu hình ứng dụng B sai. Đối soát phải xem **effective permission** theo từng ứng dụng.

### 5.4. Just-in-Time (JIT) provisioning qua đăng nhập

Một số ứng dụng tạo account ở lần đăng nhập SSO đầu tiên dựa trên các claim nhận được. JIT có thể giảm thao tác tạo account sớm, nhưng có điểm cần kiểm soát:

- Chỉ tài khoản có điều kiện nghiệp vụ và chính sách hợp lệ được phép tạo.
- Liên kết chủ thể cần dựa trên identifier tin cậy trong phạm vi issuer, tránh chỉ dùng email.
- Quyền mặc định phải tối thiểu; JIT không phải phê duyệt đặc quyền.
- Các account JIT vẫn phải được kiểm kê và đưa vào **Mover/Leaver**.
- Nếu người chưa từng đăng nhập, account có thể chưa tồn tại; đây có thể là trạng thái hợp lệ, tùy mô hình.

**JIT và SCIM là các cách tổ chức provisioning khác nhau**; có thể cùng tồn tại với phạm vi rõ ràng. Cần tránh hai luồng đồng thời tự tạo hai account cho một người.

### 5.5. Hệ thống legacy và thao tác thủ công

Nếu không có API, hệ thống có thể dùng ticket/manual task với người được ủy quyền. Quy trình vẫn phải có **SLA, owner, approval, bằng chứng hoàn tất và đối soát**.

Một ticket ghi “đã xử lý” không đủ nếu không xác minh account/role thực tế. Đối với quyền nhạy cảm, nên có kiểm tra độc lập hoặc kiểm soát bù trừ khi thao tác thủ công.

## 6. Điều phối nhiều hệ thống: từ sự kiện tới kết quả

~~~mermaid
flowchart TD
    A["Nhận sự kiện JML"] --> B{"Nguồn và identity hợp lệ?"}
    B -->|"Không"| X["Ngoại lệ: xác minh nguồn / chủ thể"]
    B -->|"Có"| C["Đọc trạng thái có thẩm quyền hiện hành"]
    C --> D["Tính desired access theo policy"]
    D --> E["So sánh observed access"]
    E --> F["Lập danh sách task và phụ thuộc"]
    F --> G["Thực thi connector theo hệ thống"]
    G --> H["Ghi request/result từng task"]
    H --> I["Đọc lại observed state"]
    I --> J{"Khớp desired state?"}
    J -->|"Chưa"| K["Retry, remediation, exception owner"]
    K --> I
    J -->|"Đúng"| L["Audit verifiedAt và đóng workflow"]
~~~

### 6.1. Bước 1 – Xác định hiện trạng và điều kiện

Nhận sự kiện từ HRIS, nguồn hợp đồng hoặc service registry. Xác minh nguồn, phiên bản, thời gian hiệu lực và mapping chủ thể. Nếu cùng một người có nhiều quan hệ việc làm, cần biết quyền nào thuộc quan hệ nào.

Khi event thiếu dữ liệu hoặc có dấu hiệu nhầm danh tính, không tự cấp quyền nhạy cảm. Chuyển cho owner dữ liệu hoặc người có trách nhiệm quyết định.

### 6.2. Bước 2 – Tính desired access

Chính sách quyền nên xem:

- Employment status và ngày có hiệu lực.
- Vai trò, bộ phận, đơn vị, dự án, người quản lý, loại lao động.
- Kết quả identity proofing, MFA và điều kiện đăng nhập khi liên quan.
- Phê duyệt được phép cho quyền đặc biệt.
- Quy tắc **Segregation of Duties (SoD)** để tránh tổ hợp quyền xung đột.
- Quyền có ngày hết hạn và **Just-in-Time (JIT)** nếu phù hợp.
- Các chặn bảo mật đang có hiệu lực; HRIS ACTIVE không được tự xóa một lệnh chặn bảo mật độc lập.

Kết quả là **trạng thái muốn có ở từng đích**, có thể gồm cả các quyền cần thu hồi.

### 6.3. Bước 3 – Lập kế hoạch theo phụ thuộc

Ví dụ phải tạo account trước khi thêm group; nhưng account IdP và mailbox có thể được chuẩn bị song song nếu hệ thống hỗ trợ. Với việc thu hồi, thứ tự có thể cần ưu tiên chặn truy cập nhanh trước khi dọn cấu hình phụ.

**Không ép mọi hệ thống dùng một trình tự duy nhất.** Cần biểu diễn dependencies và tiêu chí hoàn tất bằng dữ liệu hoặc cấu hình theo đích.

### 6.4. Bước 4 – Thực thi và theo dõi từng task

Mỗi task có ID, hệ thống, account/role mục tiêu, trạng thái, số lần thử, thời điểm và lỗi. Một workflow có thể chứa hàng chục task. Nếu 9/10 task thành công nhưng ứng dụng nhạy cảm còn lỗi, toàn bộ workflow **không thể được đánh dấu VERIFIED chỉ vì đa số hoàn tất**.

### 6.5. Bước 5 – Đối soát trạng thái cuối

Sau ghi dữ liệu, đọc lại từ ứng dụng hoặc nguồn quan sát được chấp nhận. So sánh với desired state. Sai lệch được đưa vào **queue có owner**, có mức ưu tiên theo quyền thiếu hay quyền thừa, và có quy trình retry/manual remediation.

### 6.6. Bước 6 – Lưu audit và kết thúc

Đóng workflow khi các mục tiêu bắt buộc được xác minh hoặc ngoại lệ đã được giải quyết theo tiêu chí tổ chức. Lưu lý do, chính sách, approval, kết quả từng đích và thời điểm xác minh. Với thao tác còn pending, workflow cần thể hiện **PARTIAL/BLOCKED**, thay vì ghi thành công giả.

## 7. Mô hình trạng thái cho workflow và task

Sử dụng một cờ success duy nhất thường không đủ. Mô hình minh họa:

~~~mermaid
stateDiagram-v2
    [*] --> VALIDATING
    VALIDATING --> PLANNED: Nguồn và identity hợp lệ
    VALIDATING --> BLOCKED: Thiếu dữ liệu / phê duyệt
    PLANNED --> EXECUTING: Đến thời điểm hiệu lực
    EXECUTING --> VERIFYING: Task đã gửi hoặc chạy
    VERIFYING --> COMPLETED: Đích bắt buộc đúng
    VERIFYING --> PARTIAL: Một hoặc nhiều đích chưa đúng
    PARTIAL --> EXECUTING: Retry / xử lý ngoại lệ
    BLOCKED --> VALIDATING: Đã bổ sung điều kiện
    COMPLETED --> [*]
~~~

Một **task** có thể dùng trạng thái chi tiết hơn: PENDING, RUNNING, ACCEPTED, APPLIED, VERIFIED, RETRYABLE_ERROR, PERMANENT_ERROR, CANCELLED. **ACCEPTED** nghĩa là đích đã nhận yêu cầu; không đồng nhất với VERIFIED.

Lưu trạng thái theo **từng hệ thống đích** là yêu cầu quan trọng, nhất là khi một ứng dụng xử lý bất đồng bộ hoặc tạm ngừng hoạt động.

## 8. Joiner: tạo và cấp quyền ở nhiều hệ thống

Một Joiner tiêu biểu bắt đầu khi HRIS hoặc nguồn hợp đồng xác nhận ngày bắt đầu và quan hệ làm việc hợp lệ.

1. **Xác minh danh tính:** phân giải danh tính, kiểm tra không trùng/nhầm, proofing theo yêu cầu, xác định identityId.
2. **Tính thời điểm:** tài khoản nào được chuẩn bị trước, quyền nào chỉ mở tại effectiveAt.
3. **Tạo account IdP:** thiết lập điều kiện xác thực, MFA/passkey, không chia sẻ credential qua kênh không an toàn.
4. **Tạo hoặc đồng bộ user ở ứng dụng:** dùng SCIM/API/JIT theo capability từng hệ thống.
5. **Cấp quyền:** role/group/entitlement từ bộ quyền được phê duyệt, giới hạn theo RBAC/ABAC.
6. **Kiểm tra hệ thống đích:** tài khoản tồn tại đúng người, không dư đặc quyền, chính sách truy cập hoạt động.
7. **Lưu kết quả:** hoàn tất hoặc lập exception với owner và hạn xử lý.

**Ví dụ:** nhân viên mới cần email, ERP và Analytics. Email có thể provision thành công; ERP chờ phê duyệt dữ liệu nhạy cảm; Analytics nhận SCIM nhưng chưa cấp license. Hệ thống không nên đánh dấu Joiner hoàn tất toàn phần, cũng không nên cấp tạm ERP Admin chỉ để bỏ qua lỗi role mapping.

### 8.1. Preboarding và hủy nhận việc

Có thể tạo account hạn chế trước ngày bắt đầu theo chính sách. Khi ngày nhận việc bị lùi hoặc Joiner bị hủy, phải cập nhật lịch kích hoạt, thu hồi quyền/account đã tạo sớm và kiểm tra các hệ thống đích.

Nếu chỉ hủy workflow trong IGA nhưng không thu hồi account preboarding đã được tạo, tổ chức có thể để lại **tài khoản mồ côi** trước khi người đó từng chính thức bắt đầu làm việc.

## 9. Mover: tính lại quyền, thu hồi quyền cũ ở mọi đích

Mover là thay đổi vai trò, phòng ban, vị trí, nhóm dự án, pháp nhân hoặc điều kiện truy cập. Employment status vẫn có thể ACTIVE nhưng quyền phải thay đổi.

Ví dụ người dùng chuyển từ Support sang Finance:

| Hệ thống | Quyền trước | Desired sau Mover | Thao tác |
| --- | --- | --- | --- |
| IdP | Nhóm Support | Nhóm Finance | Gỡ Support, thêm Finance |
| CRM | SupportCustomerRead | Không còn | Thu hồi quyền và xem xét phiên |
| ERP | Không có | InvoiceRead | Cấp theo approval |
| VPN | BasicVPN | BasicVPN | Không cần đổi, vẫn đối soát |
| Analytics | SupportDashboard | FinanceDashboard | Gỡ dashboard cũ, cấp dashboard mới |

**Cách xử lý “chỉ thêm quyền mới” dễ gây privilege creep.** Bộ điều phối phải lấy **bộ quyền mong muốn hiện tại**, so với quyền đang có và **gỡ phần không còn hợp lệ**.

### 9.1. Vấn đề về thứ tự thu hồi và cấp mới

Với quyền nhạy cảm, chính sách có thể ưu tiên thu hồi quyền cũ trước khi cấp quyền mới để tránh tổ hợp SoD nguy hiểm. Với quy trình phục vụ kinh doanh, có thể cần một khoảng chuyển tiếp có phê duyệt. Quyết định phải dựa trên mức rủi ro, không mặc định cho phép mọi role cũ và mới cùng tồn tại.

### 9.2. Token/phiên khi thay đổi role

IdP đổi nhóm có thể ảnh hưởng những lần đăng nhập tương lai. Ứng dụng có thể vẫn giữ phiên hoặc token chứa claim cũ, hoặc cache quyền lâu hơn. Nếu chuyển vai trò cần gỡ truy cập tức thời, workflow phải có **task riêng cho session/token** và xác minh bằng khả năng đích hỗ trợ.

## 10. Leaver: vô hiệu hóa và thu hồi trên nhiều lớp

Leaver bắt đầu từ việc quan hệ làm việc chấm dứt hoặc hợp đồng hết hiệu lực, theo thời điểm và chính sách áp dụng. Mục tiêu là **không còn đường truy cập trái phép** của chủ thể đã rời tổ chức.

Các lớp cần rà soát:

| Lớp | Việc cần làm | Điểm thường bị bỏ sót |
| --- | --- | --- |
| IdP | Chặn đăng nhập mới, điều chỉnh nhóm/credential theo policy | Phiên ứng dụng độc lập |
| SaaS SCIM | Deactivate hoặc thao tác tương đương | Ứng dụng không thu hồi token hoặc role cục bộ |
| Ứng dụng API riêng | Disable user, thu hồi entitlement, ownership theo quy trình | Tài khoản tạo thủ công |
| Cloud/VPN | Gỡ role, access policy, khóa/cert có liên quan | Quyền lâu hạn cấp trực tiếp |
| Session/token | Revoke/terminate theo khả năng nền tảng | Refresh token còn hiệu lực |
| Quyền chia sẻ/ủy quyền | Thu hồi delegation, group và ACL | Quyền dự án không xuất hiện trong IdP |
| Service ownership | Bàn giao quyền quản lý workload của người nghỉ | Service principal vẫn do người cũ sở hữu |

**Khóa tài khoản ở IdP không tự động bảo đảm offboarding ở mọi hệ thống.** SCIM deactivation cũng không mặc nhiên xử lý mọi session, API key, SSH key hoặc role nội bộ. Cần đối soát từng đích và giữ workflow chưa hoàn tất khi còn quyền tồn dư cần xử lý.

Đối với dữ liệu cần bàn giao, phải phân biệt **giữ dữ liệu nghiệp vụ** với **duy trì quyền đăng nhập của người đã rời đi**.

## 11. Điều phối trong môi trường không có giao dịch chung

Nhiều SaaS và nền tảng hạ tầng **không chia sẻ một giao dịch nguyên tử**. Không thể giả định “tất cả cùng commit hoặc rollback” như trong một cơ sở dữ liệu.

Một số task có thể thành công trước khi task khác thất bại. Do đó orchestrator cần:

- **Lưu trạng thái riêng từng đích**, kèm request ID và kết quả.
- **Retry an toàn** khi lỗi tạm thời.
- **Compensating action** có chủ đích khi thao tác trước đó gây trạng thái không phù hợp.
- **Reconciliation** để biết có cần tiếp tục hay không.
- **Escalation** khi đích không thể tự xử lý.
- **Không tự khôi phục quyền cũ** nếu trạng thái nhân sự/chính sách mới nhất không còn cho phép.

Ví dụ, khi Mover cấp ERP InvoiceRead thành công nhưng gỡ CRM SupportRead thất bại, điều phối phải ưu tiên xử lý **EXTRA_ACCESS**. Rollback bằng cách gỡ InvoiceRead chưa giải quyết quyền CRM còn tồn dư và có thể làm nhân viên không thể làm việc.

### 11.1. Chiến lược xử lý lỗi theo nhóm

| Lỗi | Ví dụ | Phản ứng điển hình |
| --- | --- | --- |
| Lỗi tạm thời | Timeout, 429 rate limit, 5xx | Backoff, retry có giới hạn, quan sát lại |
| Lỗi dữ liệu | Thiếu manager, mapping department sai | Dừng task liên quan, gửi owner dữ liệu xử lý |
| Lỗi phê duyệt | Role nhạy cảm chưa có approval | Không cấp role, giữ trạng thái chờ |
| Lỗi quyền connector | Service principal thiếu quyền API | Cảnh báo đội quản trị, sửa scope với kiểm soát |
| Xung đột tài khoản | Username đã tồn tại nhưng không rõ chủ thể | Không tự nối account, kiểm tra identity |
| Hệ thống chưa hỗ trợ | Không thể revoke session qua API | Kiểm soát bù trừ/biện pháp thủ công có owner |
| Quyền bị sửa ngoài luồng | Admin ứng dụng cấp role trực tiếp | Phát hiện drift và xử lý theo policy |

Không retry vô hạn một lỗi 4xx có tính nghiệp vụ như “permission denied” hoặc “invalid mapping”. Phải phân loại để tránh gây tải, giấu lỗi thật hoặc tạo dữ liệu trùng.

## 12. Idempotency, sự kiện trễ và tính nhất quán

### 12.1. Idempotency

**Idempotency** là tính chất việc thực hiện lại cùng ý định không khiến trạng thái cuối bị sai. Khi cùng một sự kiện Joiner được gửi ba lần do mạng lỗi, không được tạo ba account hoặc nhân ba quyền.

Một task nên có **khóa nghiệp vụ ổn định**, chẳng hạn tổ hợp identityId + targetSystem + operation + entitlement + desiredVersion. Tùy API, có thể dùng idempotency key do đích hỗ trợ hoặc thực hiện **đọc trước/đọc sau, upsert có kiểm soát**.

### 12.2. Thứ tự sự kiện

Giả sử luồng nhận lần lượt:

~~~text
Event 21: Joiner -> ACTIVE
Event 22: Mover  -> Finance
Event 23: Leaver -> TERMINATED

Thứ tự giao đến thực tế:
  22, 23, 21 (Event 21 đến muộn)

Yêu cầu:
  - Event 21 không được tạo lại account sau Leaver.
  - Quyết định provisioning phải dựa trên trạng thái nguồn hiện hành.
  - Lưu event cũ để truy vết, đánh dấu IGNORED_STALE.
~~~

Cần lưu eventId, sourceVersion, effectiveAt và phiên bản desired state. **Không coi sự kiện đến sau là trạng thái nghiệp vụ mới nhất**.

### 12.3. Eventual consistency

Một số đích mất thời gian từ khi API chấp nhận lệnh tới khi quyền thực tế thay đổi. Đối soát ngay lập tức có thể thấy trạng thái cũ mà không hẳn là lỗi vĩnh viễn.

Thiết kế nên có **cửa sổ chờ hợp lý, kiểm tra lặp với giới hạn, deadline theo mức rủi ro** và ngoại lệ nếu quá hạn. Với thu hồi quyền đặc quyền, thời gian chờ và biện pháp chặn bổ sung phải chặt hơn truy cập thông thường.

### 12.4. Mã giả điều phối

~~~text
onLifecycleEvent(event):
    verifySource(event)
    identity = resolveIdentity(event.subjectReference)
    current = readAuthoritativeState(identity)

    if isDuplicate(event.id):
        return loadExistingWorkflow(event.id)
    if isOlderThanCurrent(event, current):
        audit("IGNORED_STALE_EVENT", event.id)
        return NO_CHANGE

    desired = evaluatePolicy(current)
    observed = readTargetStates(identity)
    plan = calculateDiff(observed, desired)

    for each targetTask in topologicallyOrdered(plan):
        if missingApproval(targetTask):
            recordPendingApproval(targetTask)
            continue
        result = executeIdempotently(targetTask)
        recordExecutionResult(targetTask, result)

    verified = reconcileRequiredTargets(identity, desired)

    if verified.hasGaps:
        createExceptionsWithOwner(verified.gaps)
        return PARTIAL
    return COMPLETED
~~~

Đây là **mã giả giải thích ý tưởng**, không phải API SCIM chuẩn hoặc đoạn mã triển khai sẵn. Trong thực tế cần xử lý cạnh tranh workflow, dữ liệu thay đổi khi đang chạy, quản lý credentials của connector và cơ chế hủy/đổi kế hoạch.

## 13. Thiết kế task, dữ liệu và audit

Một tác vụ cần cho phép đội vận hành biết **đích nào, thao tác gì, vì sao, trạng thái thế nào, ai chịu trách nhiệm**.

Ví dụ JSON minh họa:

~~~json
{
  "workflowId": "jml-20261123-0091",
  "taskId": "jml-task-erp-004",
  "identityId": "person-2048",
  "targetSystem": "ERP",
  "targetAccountId": "erp-user-114",
  "operation": "GRANT_ENTITLEMENT",
  "entitlementId": "InvoiceRead",
  "desiredState": "PRESENT",
  "policyId": "finance-access-v4",
  "approvalRef": "approval-8721",
  "sourceVersion": 14,
  "effectiveAt": "2026-11-23T08:00:00+07:00",
  "status": "VERIFYING",
  "attempts": 2,
  "requestedAt": "2026-11-23T08:00:04+07:00",
  "appliedAt": "2026-11-23T08:00:09+07:00",
  "verifiedAt": null,
  "correlationId": "iam-event-5ac2"
}
~~~

**Lưu ý:** đây là mô hình dữ liệu ví dụ, không phải schema chuẩn hóa. Một task có thể không có targetAccountId cho tới khi account được tạo. Giá trị status tại thời điểm quan sát phải biểu thị chính xác điều đã biết.

### 13.1. Phân biệt các mốc thời gian

| Mốc | Ý nghĩa |
| --- | --- |
| eventOccurredAt / publishedAt | Sự kiện gốc được tạo hoặc phát |
| effectiveAt | Trạng thái nghiệp vụ cần có hiệu lực |
| receivedAt | Orchestrator nhận dữ liệu |
| requestedAt | Lệnh được gửi đến đích |
| acceptedAt | Đích xác nhận nhận yêu cầu, nếu có |
| appliedAt | Đích xác nhận đã áp dụng, nếu có |
| verifiedAt | Đọc lại cho thấy quyền/tài khoản đúng mục tiêu |

Không tự đặt appliedAt = requestedAt chỉ vì API trả 202 Accepted. Nếu hệ thống không cung cấp thời điểm thực thi chính xác, cần ghi rõ đó là **thời điểm quan sát/xác minh**, tránh diễn giải quá mức.

### 13.2. Audit trail

Một luồng nhiều hệ thống nên liên kết:

- Nguồn nhân sự/hợp đồng, mã sự kiện, phiên bản và ngày hiệu lực.
- Kết quả nhận diện danh tính/proofing và các account liên kết.
- Policy, thuộc tính dùng quyết định RBAC/ABAC, approval và SoD.
- Plan cấp/gỡ quyền, thứ tự task và điều kiện dependency.
- Từng lần gọi connector, mã lỗi, retry và người thực thi/khắc phục.
- Trạng thái quan sát tại đích, ngoại lệ, kết quả cuối và thời gian hoàn tất.

Bảo vệ log khỏi sửa trái phép, áp dụng phân quyền, retention phù hợp. **Không ghi access token, password, private key, recovery code hoặc dữ liệu HR không cần thiết vào audit log.**

## 14. Reconciliation: phát hiện và sửa lệch trên toàn hệ thống

**Reconciliation** là quá trình so sánh **desired state** do IAM phê duyệt với **observed state** tại các hệ thống đích, rồi xác định thiếu quyền, thừa quyền hoặc sai liên kết tài khoản.

### 14.1. Hai loại chênh lệch cơ bản

- **MISSING_ACCESS:** quyền hợp lệ chưa được cấp. Ảnh hưởng năng suất và quy trình kinh doanh.
- **EXTRA_ACCESS:** quyền không còn hợp lệ vẫn tồn tại. Đây thường là rủi ro bảo mật cần ưu tiên, đặc biệt sau Mover/Leaver.

Ngoài ra có thể có **UNLINKED_ACCOUNT** (account không ánh xạ được owner), **ATTRIBUTE_DRIFT** (thuộc tính khác HRIS), **STALE_SESSION** (phiên mang quyền cũ) và **UNKNOWN_ENTITLEMENT** (quyền ứng dụng chưa nằm trong mô hình governance).

### 14.2. Chu kỳ đối soát

- **Ngay sau task:** kiểm tra kết quả nhằm đóng workflow.
- **Theo sự kiện:** khi HRIS thay đổi, đích báo sự cố, role bị thay thủ công.
- **Định kỳ:** phát hiện drift tích tụ ở hệ thống có nhiều thao tác ngoài luồng.
- **Khi yêu cầu kiểm toán hoặc sự cố:** kiểm tra toàn bộ quyền của chủ thể/tài nguyên liên quan.

Không thể thay thế offboarding theo thời điểm bằng một cuộc rà soát hằng quý. Review định kỳ bổ sung kiểm soát nhưng **không xử lý kịp quyền của Leaver nếu chỉ chờ kỳ kiểm tra**.

### 14.3. Truy vấn minh họa tìm quyền thừa

~~~sql
SELECT
    o.identity_id,
    o.target_system,
    o.entitlement_id
FROM observed_entitlements AS o
LEFT JOIN desired_entitlements AS d
  ON d.identity_id = o.identity_id
 AND d.target_system = o.target_system
 AND d.entitlement_id = o.entitlement_id
WHERE o.active = TRUE
  AND d.entitlement_id IS NULL;
~~~

Đây là SQL trên **cấu trúc bảng giả định**, chỉ minh họa nguyên lý tìm quyền có trong observed nhưng không có trong desired. Trong hệ thống thật phải xét **ngữ cảnh tenant, relationship, quyền kế thừa, role có thời hạn, thời điểm hiệu lực, dữ liệu stale, ngoại lệ được phê duyệt và các kiểu quyền ngoài bảng entitlement** để tránh báo sai.

## 15. Bảo mật connector và danh tính phi con người

Connector provisioning thường cần quyền quản trị user/group tại đích nên có thể trở thành mục tiêu tấn công.

Kiểm soát cần thiết:

1. **Danh tính dịch vụ riêng** cho connector/workload, có owner và mục đích rõ ràng.
2. **Least privilege** cho API scope; tránh quyền wildcard/tenant-wide nếu không cần.
3. **Quản lý secret** bằng cơ chế an toàn, ưu tiên credential ngắn hạn hoặc workload federation khi khả thi.
4. **Rotation và revoke** khi khóa lộ, hệ thống thay đổi hoặc owner nghỉ việc.
5. **Giới hạn egress/nguồn gọi**, kiểm soát cấu hình và theo dõi các thao tác quản trị nhạy cảm khi phù hợp.
6. **Audit theo connector và workflow**, để phân biệt thao tác tự động đúng chính sách với hành vi bất thường.
7. **Quy trình break-glass** có thẩm quyền, bảo vệ credential, lưu lý do và kiểm tra lại sau sự cố.

**Service account không có employment status như nhân viên**. Khi người phụ trách connector chuyển việc hoặc nghỉ việc, cần chuyển owner và rà soát quyền, secret, nhưng không xóa tùy tiện một workload vẫn cần cho sản xuất.

### 15.1. Ngăn thay đổi ngoài luồng

Admin tại một SaaS có thể cấp role trực tiếp mà IAM không biết. Hệ thống nên phát hiện thay đổi bằng log của đích, readback và reconciliation; xác định khi nào hành động thủ công hợp lệ, khi nào phải tự động thu hồi hoặc xin phê duyệt bổ sung.

## 16. Trường hợp thực tế: Joiner một phần thành công, Mover và Leaver

Giả sử nhân viên **Lan** gia nhập Finance với ngày bắt đầu **23/11/2026 lúc 08:00**, cần IdP, email, ERP và hệ thống báo cáo. Quyền mục tiêu: **FinanceReader**, không có quyền quản trị.

### 16.1. Joiner

| Thời điểm | Hệ thống | Thao tác | Kết quả |
| --- | --- | --- | --- |
| 08:00 | IAM | Xác minh HRIS ACTIVE, identity, approval | PASS |
| 08:01 | IdP | Kích hoạt account và chính sách MFA | VERIFIED |
| 08:02 | Email | Tạo mailbox | VERIFIED |
| 08:03 | ERP | Tạo user và cấp InvoiceRead | VERIFIED |
| 08:03 | Analytics | Tạo user qua SCIM | ACCEPTED, chưa thấy user |
| 08:05 | Analytics | Đọc lại user/role | MISSING_ACCESS |
| 08:09 | Analytics | Retry và xác minh | VERIFIED |

Tại 08:05, workflow là **PARTIAL**. Tại 08:09 mới có thể hoàn tất nếu các điều kiện khác trong scope đều đáp ứng. Audit phải giữ nguyên lịch sử lỗi và thời điểm thực tế.

### 16.2. Mover

Ba tháng sau, Lan chuyển sang Operations. HRIS cập nhật department nhưng vẫn ACTIVE. IAM tính desired mới:

~~~text
Before:
  ERP: InvoiceRead
  Analytics: FinanceDashboardRead

After:
  ERP: no access
  Analytics: OperationsDashboardRead

Required actions:
  revoke ERP.InvoiceRead
  revoke Analytics.FinanceDashboardRead
  grant Analytics.OperationsDashboardRead
  verify active sessions / tokens as required
~~~

Nếu Analytics cấp quyền mới thành công nhưng ERP không gỡ được quyền cũ, hệ thống cần ghi **EXTRA_ACCESS** và tiếp tục remediation, không kết luận Mover hoàn tất.

### 16.3. Leaver

Khi Lan nghỉ việc, IdP bị vô hiệu hóa đúng hạn. Tuy nhiên Analytics còn một phiên đã đăng nhập. Quá trình Leaver phải kiểm tra khả năng thu hồi phiên/token của Analytics, account/role cục bộ và quyền VPN/cloud nếu có. Nếu chưa xác minh được, phải giữ ngoại lệ còn mở.

**Bài học:** một danh tính có thể đi qua nhiều trạng thái và nhiều hệ thống trong cả vòng đời. Điều phối theo **desired/observed state** và kiểm tra từng đích mới giúp biết quyền có thực sự đúng sau mỗi thay đổi.

## 17. Các chỉ số vận hành

| Chỉ số | Cách hiểu | Mục đích |
| --- | --- | --- |
| **Provisioning completion rate** | Workflow đủ các đích bắt buộc được xác minh / tổng workflow thuộc phạm vi | Đo khả năng hoàn tất |
| **Time to access** | Từ thời điểm đủ điều kiện đến verifiedAt của quyền cần cấp | Đánh giá trải nghiệm Joiner |
| **Deprovision latency** | Từ effectiveAt của Mover/Leaver đến verifiedAt quyền bị thu hồi | Đo rủi ro quyền tồn dư |
| **Partial workflow rate** | Tỷ lệ workflow còn task thất bại/chưa xác minh | Phát hiện vấn đề tích hợp |
| **Extra access count** | Quyền ở đích không thuộc desired access hợp lệ | Đo privilege creep và drift |
| **Unlinked/orphan account count** | Account không đối chiếu được với identity/owner hợp lệ | Phát hiện tài khoản ngoài quản lý |
| **Connector error and retry rate** | Lỗi theo đích, loại lỗi, số lần thử | Cải thiện độ tin cậy connector |
| **Unknown permission count** | Quyền thực tế chưa có mapping quản trị | Mở rộng phạm vi governance |
| **Stale event rejection rate** | Event cũ/lặp được phát hiện và ngăn tác động | Kiểm tra event ordering |
| **Service identity ownership coverage** | Tỷ lệ connector/workload có owner hợp lệ | Giảm rủi ro danh tính phi con người |

Khi báo cáo, cần xác định rõ **phạm vi các hệ thống đích**, mức rủi ro, loại chủ thể và cách tính timestamp. Không đánh đồng yêu cầu đã được gửi với quyền đã được thực thi.

## 18. Bảng kiểm tra triển khai provisioning nhiều hệ thống

| Câu hỏi kiểm tra | Bằng chứng mong đợi |
| --- | --- |
| Có nguồn nhân sự/hợp đồng hợp lệ cho từng chủ thể không? | Mã nguồn, trạng thái, effectiveAt và owner |
| Account ở từng hệ thống đã liên kết đúng identity chưa? | Bảng account linking, quy tắc chống trùng |
| Có tách account với entitlement không? | Task tạo user, gán/gỡ role tách biệt |
| Có mô hình desired access theo từng đích không? | Policy RBAC/ABAC, approval, SoD |
| Có phân biệt SSO với provisioning không? | Tài liệu kiến trúc và trách nhiệm từng connector |
| Mỗi hệ thống có mô tả capability thật không? | Hỗ trợ SCIM/API/JIT/manual, session revoke, limitation |
| Tác vụ có idempotency và version guard không? | Event ID, desired version, retry logic |
| Có xử lý ngày hiệu lực/hủy Joiner không? | Lịch kích hoạt, kiểm tra nguồn hiện hành, cleanup |
| Mover có gỡ quyền cũ tại mọi đích liên quan không? | Revoke tasks, trạng thái observed và SoD |
| Leaver có thu hồi phiên/token khi cần không? | Task độc lập và evidence của hệ thống |
| Workflow có trạng thái partial/failed không? | Kết quả theo từng task, owner và deadline |
| Có đối soát quyền được cấp thủ công không? | Phát hiện drift, xử lý ngoại lệ |
| Credential connector có được bảo vệ không? | Least privilege, secret manager, rotation |
| Có đo được thời gian và chất lượng thu hồi không? | effectiveAt, verifiedAt và báo cáo KPI |
| Có log đủ phục vụ kiểm toán mà không lộ bí mật không? | Correlation ID, chính sách, approval, execution và verification |
| Có kế hoạch khi SaaS không hỗ trợ API thu hồi không? | Tác vụ thủ công, kiểm soát bù trừ, SLA |

## 19. Những nhầm lẫn thường gặp

1. **“Tạo user ở IdP là đã tạo user ở mọi ứng dụng.”** Nhiều ứng dụng có account, role và điều kiện riêng.
2. **“SSO đăng nhập được thì quyền đã đúng.”** SSO xác thực; authorization và entitlement vẫn cần kiểm tra ở đích.
3. **“SCIM thành công là mọi phiên/token đã thu hồi.”** Phạm vi SCIM tùy ứng dụng; session/credential thường cần cơ chế riêng.
4. **“Chỉ cần cấp quyền mới khi nhân viên chuyển bộ phận.”** Mover phải gỡ quyền cũ không còn phù hợp.
5. **“Chỉ cần một trạng thái success cho cả workflow.”** Nhiều hệ thống có thể thành công một phần; phải lưu kết quả theo đích.
6. **“Retry bao nhiêu lần cũng không sao.”** Không có idempotency có thể tạo account hoặc quyền trùng.
7. **“Nhận event sau thì đó là trạng thái mới nhất.”** Event có thể đến trễ; phải kiểm tra source version và trạng thái có thẩm quyền.
8. **“Chỉ cần review quyền định kỳ là đủ để xử lý Leaver.”** Thu hồi theo sự kiện có hiệu lực vẫn là yêu cầu thiết yếu.
9. **“Chuyển đổi role trong IdP luôn thay đổi role ở ứng dụng tức thì.”** Mapping, caching, token và đồng bộ có thể gây độ trễ.
10. **“Service account có thể quản lý hoàn toàn bằng HRIS.”** Workload cần owner và vòng đời kỹ thuật riêng.

## 20. Câu hỏi tự đánh giá

1. Một nhân viên có account IdP và đăng nhập SSO thành công nhưng chưa có account ERP. Vấn đề nằm ở lớp nào?
2. Vì sao cần bảng liên kết identityId với accountId riêng của từng ứng dụng?
3. Một ứng dụng hỗ trợ SCIM Users nhưng không hỗ trợ role provisioning. Điều phối nên xử lý thế nào?
4. Workflow gồm năm ứng dụng, bốn thành công còn một ứng dụng giữ quyền cũ. Có được đánh dấu hoàn tất không?
5. Khác nhau giữa desired entitlement và observed entitlement là gì? Chênh lệch nào nguy hiểm hơn sau Leaver?
6. Vì sao sự kiện Joiner đến trễ sau Leaver có thể tạo lỗ hổng? Cần những cơ chế nào để chặn?
7. Khi HTTP 202 Accepted được trả về, những bước nào cần thực hiện trước khi kết luận provisioning đã hoàn tất?
8. Nếu cấp role trong cloud thành công nhưng gỡ role cũ ở CRM thất bại trong Mover, vì sao rollback role cloud chưa giải quyết gốc vấn đề?
9. Kết quả SCIM active = false có đủ chứng minh session SaaS đã hết hiệu lực không?
10. Một service account dùng để gọi API provisioning mất owner do người phụ trách nghỉ việc. Cần xử lý những thành phần nào mà không làm gián đoạn dịch vụ?
11. Khi nào nên dùng provisioning trước ngày nhận việc và cách ngăn quyền bị mở sớm?
12. Nêu những trường và bằng chứng tối thiểu giúp kiểm toán kết luận Leaver đã thu hồi quyền tại từng đích.

## 21. Ghi nhớ

**Provisioning nhiều hệ thống** là bài toán điều phối một danh tính qua nhiều tài khoản, role và cơ chế tích hợp. Quy trình đáng tin phải xác định **nguồn có thẩm quyền, định danh ổn định, quyền mong muốn theo chính sách, thao tác cấp/thu hồi theo từng hệ thống, trạng thái thực tế và bằng chứng hoàn tất**.

Trong vòng đời **Joiner–Mover–Leaver**, IdP và SSO hỗ trợ xác thực, SCIM/API và các connector xử lý cấp phát, còn RBAC/ABAC cùng approval quyết định quyền nào hợp lệ. **Idempotency, version guard, reconciliation, ngoại lệ có owner, kiểm toán và quản trị service identities** giúp xử lý sự cố khi một phần hệ thống thất bại. Chỉ khi đã xác minh quyền đúng người, đúng vai trò, đúng thời điểm ở các đích cần thiết, IAM mới có cơ sở kết luận provisioning hoàn tất và giảm được nguy cơ **quyền truy cập tồn dư**.
