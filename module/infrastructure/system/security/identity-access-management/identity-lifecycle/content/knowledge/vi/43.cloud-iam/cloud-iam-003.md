# Cloud role

**Chương:** Cloud IAM  
**Chủ đề:** Cloud role  
**Phạm vi:** Thiết kế, gán, sử dụng, rà soát và thu hồi vai trò truy cập tài nguyên đám mây trong vòng đời danh tính **Joiner–Mover–Leaver (JML)**.

## 1. Cloud role là gì và giải quyết vấn đề nào?

**Cloud role** là một cấu trúc của hệ thống **Identity and Access Management (IAM)** dùng để nhóm hoặc biểu diễn tập quyền truy cập. Tùy nhà cung cấp, role có thể là **một thực thể được principal đảm nhận để nhận quyền trong phiên** (ví dụ AWS IAM role), hoặc **một tập quyền được gán cho principal tại một phạm vi tài nguyên** (ví dụ Azure RBAC role, Google Cloud IAM role). Điểm chung là role giúp diễn đạt **được phép thực hiện hành động nào trên tài nguyên nào**, thay vì cấp từng quyền rời rạc cho từng nhân viên.

Ví dụ, đội hỗ trợ vận hành cần xem log của dịch vụ thanh toán trong môi trường production. Thay vì cấp cho từng người quyền quản trị toàn bộ cloud account, tổ chức định nghĩa vai trò **PaymentLogReader**, chỉ cho phép đọc log ở phạm vi cần thiết và gán cho những người có công việc tương ứng. Khi một người chuyển đội hoặc nghỉ việc, quyền liên quan phải được rà soát và thu hồi.

Cloud role là thành phần nền tảng của **Role-Based Access Control (RBAC)**, nhưng một role không thể tự chứng minh ai là người dùng và không tự hết hiệu lực khi dữ liệu nhân sự thay đổi. Toàn bộ quy trình cần liên kết:

- **Nguồn danh tính:** HRIS, hệ thống quản lý đối tác hoặc sổ đăng ký workload; xác định chủ thể và trạng thái hợp lệ.
- **IdP/SSO:** Xác thực người dùng; có thể phát SAML assertion hoặc OpenID Connect (OIDC) token cho federation.
- **Provisioning/SCIM:** Đồng bộ tài khoản và nhóm ở hệ thống đích có hỗ trợ; có thể hỗ trợ ánh xạ quyền tùy tích hợp.
- **Cloud IAM:** Đánh giá role, policy, phạm vi, trust và điều kiện khi truy cập tài nguyên.
- **Identity Governance / Lifecycle:** Quản lý Joiner–Mover–Leaver, phê duyệt, chứng cứ kiểm toán và rà soát quyền truy cập tồn dư.

Sau bài học, bạn cần phân biệt role với user/group/policy, mô tả cơ chế role ở AWS, Azure và Google Cloud, thiết kế danh mục role theo **least privilege**, giải thích cách role đi qua các bước JML, và xác minh được rằng một quyền cũ đã thực sự hết hiệu lực.

## 2. Phân biệt role, principal, policy và assignment

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Identity** | Ai hoặc workload nào tồn tại trong hệ thống? | Nhân viên có ID EMP-3021; service account của ứng dụng |
| **Principal** | Chủ thể nào đang thực hiện yêu cầu và được IAM đánh giá? | User, role session, workload principal |
| **Credential/session** | Chủ thể đã chứng minh danh tính bằng cách nào, trong khoảng thời gian nào? | SSO session, token ngắn hạn, managed identity |
| **Permission** | Thao tác nguyên tử nào được phép? | Xem log, đọc object, triển khai ứng dụng |
| **Policy** | Quy tắc cho phép hoặc từ chối trong điều kiện và phạm vi nào? | Quy tắc chỉ đọc log của project dev |
| **Role** | Tập quyền hoặc thực thể vai trò nào biểu diễn chức trách truy cập? | PaymentLogReader, DeploymentOperator |
| **Group** | Tập hợp chủ thể nào để quản lý membership? | Nhóm đội platform tại IdP |
| **Role assignment/binding** | Ai được gắn role nào, tại scope nào? | Nhóm platform được gán Reader ở một resource group |
| **Trust/assume-role relationship** | Principal nguồn nào được phép nhận quyền qua một role? | Pipeline CI/CD được tin cậy để assume deployment role |
| **Entitlement** | Quyền truy cập thực tế nào đang được cấp cho principal? | Thành viên nhóm, role assignment, IAM binding, access grant |

**Role không đồng nghĩa group.** Group tập hợp thành viên; role diễn tả khả năng truy cập hoặc tập quyền. Một group có thể nhận nhiều role; một role có thể được nhiều group hoặc principal sử dụng. **Role không đồng nghĩa policy**: ở một số nền tảng role có policy gắn với nó, ở nền tảng khác role chính là tập permissions được tham chiếu bởi binding.

**Một role được định nghĩa chưa có nghĩa người dùng có quyền đó.** Cần xét principal được gắn/được phép đảm nhận role hay không, phạm vi role, các điều kiện và lớp policy khác. Ngược lại, xóa một role assignment ở một nơi chưa chứng minh principal mất mọi quyền tương đương nếu vẫn có binding hoặc đường truy cập khác.

### 2.1. Ba lớp quyết định quyền

~~~mermaid
flowchart TD
    A["Danh tính người dùng / workload"] --> B["Xác thực: IdP, federation, token"]
    B --> C["Principal được cloud IAM nhận diện"]
    C --> D["Role / group / trust / assignment"]
    D --> E["Permissions + scope + điều kiện"]
    E --> F{"IAM cho phép yêu cầu?"}
    F -->|Có, không bị deny hoặc giới hạn khác| G["Thực hiện thao tác trên tài nguyên"]
    F -->|Không| H["Access denied và log"]
    I["JML / IGA / access review"] -.-> D
    J["Chính sách cấp tổ chức / boundary"] -.-> E
~~~

Sơ đồ mô tả kiểm soát logic, không phải thứ tự áp policy cố định của mọi nhà cung cấp. Một số hệ thống có **explicit deny**, hạn chế cấp tổ chức, quyền kế thừa hoặc policy tại tài nguyên. Cần hiểu cách các lớp đó kết hợp để đánh giá **effective permissions**.

### 2.2. Tư duy principal – action – resource – context

Một yêu cầu truy cập có thể được biểu diễn ở mức khái niệm:

~~~text
canAccess(principal, action, resource, context)
    = identityIsValid(principal)
      AND sessionOrCredentialIsValid(principal)
      AND applicablePolicyAllows(principal, action, resource, context)
      AND NOT blockedByApplicableRestrictions(...)
~~~

Đây là **giả mã khái niệm**, không phải thuật toán thay thế IAM của nhà cung cấp. “Identity còn active” là một tín hiệu quan trọng, nhưng không phải mọi cloud service tự truy vấn HRIS tại thời điểm gọi API. Vì thế quy trình cấp/thu hồi quyền cần thực thi ở IdP và các hệ thống cloud đích, đồng thời xem xét session hoặc credential đã phát hành.

## 3. Role có hai góc nhìn vòng đời

Khi nói “quản lý vòng đời cloud role”, cần tách:

1. **Vòng đời định nghĩa role (role definition lifecycle):** Thiết kế quyền, phê duyệt, xuất bản, thay đổi phiên bản, rà soát và ngừng sử dụng vai trò. Ví dụ nâng cấp role LogReader khi ứng dụng chuyển sang dịch vụ log khác.
2. **Vòng đời gán role cho principal (role entitlement lifecycle):** Cấp role khi có nhu cầu, thay đổi scope/role khi chuyển nhiệm vụ, thu hồi khi hết nhu cầu hoặc nhân viên nghỉ việc.

Hai vòng đời này liên quan nhưng không giống nhau. **Xóa role definition** khi một nhân viên nghỉ việc có thể làm gián đoạn những người khác đang sử dụng role. Trong sự kiện Leaver, thông thường phải thu hồi **assignment/binding, trust và credential liên quan đến người đó**, còn role dùng chung vẫn tồn tại nếu doanh nghiệp còn nhu cầu.

### 3.1. Mẫu hồ sơ quản trị một role

| Trường | Nội dung nên quản lý | Ví dụ minh họa |
| --- | --- | --- |
| Role ID | ID kỹ thuật ổn định | cloud.role.payment-log-reader |
| Tên hiển thị | Dễ hiểu theo chức năng | Payment Log Reader |
| Mục đích | Tác vụ được role hỗ trợ | Điều tra lỗi dịch vụ thanh toán |
| Provider và scope | Nơi role có ý nghĩa | AWS account prod-payments / log resources |
| Permissions | Action và tài nguyên được cho phép | Chỉ đọc log cần thiết |
| Principal đủ điều kiện | Nhóm người hoặc workload được phép nhận | Nhóm Payment Operations |
| Owner | Chịu trách nhiệm nội dung role | Platform Security |
| Người phê duyệt | Căn cứ cấp quyền | Payment Service Owner |
| Điều kiện | MFA, thiết bị, môi trường, thời hạn nếu được hỗ trợ | Quyền đặc biệt tối đa trong cửa sổ trực |
| Risk level | Độ nhạy của quyền | Medium |
| Version/review | Lịch sử thay đổi và kỳ xem xét | v2, review hàng quý |
| Trạng thái | Draft, active, deprecated, retired | active |

Tên role nên thể hiện ý nghĩa nghiệp vụ và phạm vi. Tránh các tên mơ hồ như “SuperUser2”, “AllDeveloper” khi thực chất cấp quyền ghi trên dữ liệu production. Tên dễ hiểu giúp owner xác nhận đúng nhu cầu trong các đợt rà soát.

## 4. Role trong AWS IAM

**AWS IAM role** là một IAM identity có **trust policy** xác định ai có thể đảm nhận role và **permissions policies** quyết định phiên đảm nhận role có thể làm gì. Principal được chấp nhận có thể dùng **AWS Security Token Service (STS)** để nhận thông tin xác thực tạm thời. Role khác với IAM user: role thường không có mật khẩu đăng nhập cố định hay access key dài hạn gắn trực tiếp theo kiểu IAM user.

### 4.1. Trust policy và permissions policy phải tách bạch

| Thành phần | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| **Trust policy** | Ai được phép assume role và phải đáp ứng điều kiện nào? | Một role CI/CD đã định danh, hoặc issuer OIDC có subject phù hợp |
| **Permissions policy** | Sau khi assume role, phiên này có thể thực hiện action nào trên resource nào? | Ghi artifact vào một bucket triển khai |
| **Session policy/tags** | Có hạn chế hoặc ngữ cảnh bổ sung cho phiên không? | Giới hạn quyền trong session, nhãn môi trường |
| **SCP / permissions boundary và cơ chế hạn chế liên quan** | Quyền tối đa bị giới hạn thế nào trong account/organization? | Cấm một số hành động quản trị dù policy role rộng |

Ví dụ mô hình triển khai một ứng dụng (giả mã, **không phải JSON policy có thể áp trực tiếp**):

~~~yaml
role:
  name: app-staging-deployer
  account: staging-app
trust:
  issuer: approved-ci-provider
  audience: expected-cloud-token-audience
  subject:
    repository: example-org/app
    environment: staging
permissions:
  allow:
    - action: application.deploy
      resource: staging-service
    - action: deployment-artifact.read
      resource: staging-artifacts
session:
  lifetime: short
owner: application-platform
~~~

Mục đích ví dụ là cho thấy **cùng lúc cần kiểm soát danh tính nguồn và phạm vi quyền**, không hàm ý các khóa YAML trên được AWS IAM hiểu nguyên trạng. Trong hệ thống thật, điều kiện trust của OIDC cần dùng claim key và condition operator mà AWS hỗ trợ cho từng issuer; action/resource phải dùng tên API và ARN chính xác.

### 4.2. Người dùng đảm nhận role và IAM Identity Center

Doanh nghiệp thường cho nhân viên đăng nhập qua IdP/SSO rồi chọn quyền được cấp cho các AWS account. **AWS IAM Identity Center** có thể dùng **permission sets** để cung cấp quyền truy cập account; hệ thống tạo và quản lý các IAM role liên quan trong account đích. Người quản trị cần phân biệt permission set/assignment ở lớp quản lý tập trung với IAM role và policy thực tế trong account.

Ví dụ: nhóm IdP **finance-auditors** được phép dùng permission set chỉ đọc trên account tài chính. Khi nhân viên rời nhóm, quá trình deprovision/đồng bộ và điều chỉnh assignment phải được xác minh, kể cả quyền cấp trực tiếp hoặc tài khoản địa phương nằm ngoài mô hình trung tâm.

### 4.3. Cross-account assume role

Một workload trong AWS account A cần đọc dữ liệu từ AWS account B. Khi thiết kế, thường phải:

1. Xác định principal nguồn hợp lệ ở A.
2. Thiết lập trust policy của role đích ở B cho phép đúng principal nguồn, kèm điều kiện cần thiết.
3. Bảo đảm bên nguồn có quyền thực hiện thao tác assume role khi cơ chế đánh giá yêu cầu.
4. Giới hạn permissions của role đích theo tài nguyên và action được phép.
5. Ghi nhận owner hai bên, thời hạn và kiểm tra lại khi quan hệ hợp tác thay đổi.

**Trust cho phép đảm nhận role không đồng nghĩa role có quyền quản trị toàn account.** Quyền thực thi phụ thuộc policy của role, các giới hạn liên quan và policy tài nguyên. Khi ngừng tích hợp, cần thu hồi cả đường trust/grant và xử lý phiên hoặc credential đã phát hành theo khả năng nền tảng.

## 5. Role trong Microsoft Azure

**Azure Role-Based Access Control (Azure RBAC)** quản lý quyền truy cập tài nguyên Azure bằng cách gán một **role definition** cho **security principal** tại một **scope**.

~~~text
Azure RBAC assignment
    = (security principal, role definition, scope)
~~~

Ví dụ, một nhóm người dùng từ Microsoft Entra ID được gán role **Reader** tại một resource group. Nhóm này có quyền đọc các tài nguyên thuộc phạm vi theo khả năng của role, bao gồm quyền kế thừa xuống tài nguyên con; người dùng không mặc nhiên có quyền tương tự trên các subscription khác.

| Khái niệm Azure | Ý nghĩa |
| --- | --- |
| **Role definition** | Tập actions, notActions và các quyền dữ liệu tương ứng theo cấu trúc role |
| **Built-in role** | Role do Azure cung cấp, ví dụ Reader, Contributor, Owner |
| **Custom role** | Role do tổ chức định nghĩa khi built-in role quá rộng hoặc thiếu quyền cụ thể |
| **Role assignment** | Liên kết principal + role definition + scope |
| **Scope** | Management group, subscription, resource group hoặc resource |
| **Data plane vs management plane** | Quyền quản trị tài nguyên khác với quyền đọc/ghi dữ liệu của dịch vụ; cần kiểm tra riêng |

**Microsoft Entra directory roles** (ví dụ các quyền quản trị thư mục) là một hệ vai trò khác với Azure RBAC trên tài nguyên. Không được đánh đồng quản trị IdP/tenant với quyền trên mọi resource trong subscription, dù một số đường nâng quyền hoặc cơ chế quản trị đặc biệt có thể tồn tại và phải được kiểm soát.

### 5.1. Quyền kế thừa và phạm vi

Một assignment tại management group/subscription có thể bao phủ nhiều resource group; assignment tại một resource chỉ áp dụng ở phạm vi được gán. Vì vậy “cấp Contributor cho đội phát triển” chưa đầy đủ nếu không chỉ rõ scope.

Role **Owner** có thể quản lý truy cập tại phạm vi tương ứng nên rủi ro cao hơn những vai trò chỉ quản trị tài nguyên thông thường. Khi dùng **Privileged Identity Management (PIM)** theo khả năng và cấu hình phù hợp, tổ chức có thể kiểm soát activation có thời hạn, phê duyệt và yêu cầu xác thực bổ sung đối với vai trò đủ điều kiện.

### 5.2. Ví dụ gán role Azure ở mức khái niệm

~~~yaml
# Giả mã nghiệp vụ, không phải định dạng API Azure
principal: group:platform-developers
roleDefinition: Reader
scope: subscription:sub-learning/resourceGroup:rg-learning-dev
approval: standard-role-policy
reviewOwner: platform-team
expiresOn: review-required
~~~

**Chỉ đổi group ở IdP không bảo đảm mọi Azure role assignment trực tiếp đã biến mất.** Trong Mover/Leaver, phải truy vấn quyền tại các scope có liên quan, kể cả quyền kế thừa, quyền trực tiếp và các hệ thống dữ liệu có cơ chế phân quyền riêng.

## 6. Role trong Google Cloud IAM

Trong **Google Cloud IAM**, role là **tập permissions**; principal được cấp một role thông qua **IAM allow policy binding** trên organization, folder, project hoặc tài nguyên có hỗ trợ. Một binding có thể chứa các member và điều kiện (IAM Conditions) tùy khả năng của chính sách và dịch vụ.

Google Cloud có những loại role thường gặp:

- **Basic roles:** Owner, Editor, Viewer; thường rộng, cần cân nhắc kỹ vì quyền có thể vượt nhu cầu tối thiểu.
- **Predefined roles:** Role do Google Cloud cung cấp cho dịch vụ hoặc chức năng cụ thể; thường là điểm khởi đầu phù hợp.
- **Custom roles:** Tập permissions do tổ chức định nghĩa, phù hợp khi không có role sẵn đáp ứng nguyên tắc ít quyền nhất và permissions được hỗ trợ cho custom role.

### 6.1. Role và binding trong Google Cloud

~~~yaml
# Ví dụ mô hình YAML diễn giải IAM binding; kiểm tra cú pháp API khi triển khai
resource: projects/analytics-dev
bindings:
  - role: roles/logging.viewer
    members:
      - group:analytics-ops@example.org
~~~

Ví dụ trên thể hiện ý tưởng: nhóm analytics-ops được gắn quyền xem log ở project analytics-dev. **Tên nhóm và project chỉ là dữ liệu giả định.** Cần xác minh chính xác role, scope, điều kiện và chính sách kế thừa thực tế trong triển khai.

Không nên mô tả Google Cloud IAM role như thể bất kỳ người dùng nào cũng phải “assume role” theo đúng cách AWS STS. Mô hình cơ bản của Google Cloud là **binding role với principal trên resource**; đối với workload, có các cơ chế như **service account impersonation** hoặc **Workload Identity Federation** để nhận quyền được cấp cho danh tính đích.

### 6.2. Service account và quyền impersonation

Service account là principal riêng, có thể được cấp quyền trên tài nguyên. Một người hoặc workload có quyền impersonate service account có thể thực hiện hành động dưới danh tính đó trong phạm vi quyền được cấp; quyền tạo token hoặc dùng service account phải được rà soát như một đường nâng đặc quyền.

Ví dụ: pipeline được phép sử dụng service account triển khai cho project staging nhưng không được dùng service account production. Khi pipeline bị xóa, cần thu hồi trust và các binding liên quan; nếu còn principal khác có quyền impersonation, chỉ xóa liên kết pipeline không đủ để khẳng định danh tính đích đã được quản trị an toàn.

## 7. Xây dựng danh mục role theo chức trách

Một danh mục role hiệu quả cần phản ánh **công việc cụ thể**, đủ chi tiết để hạn chế quyền, nhưng không tạo hàng nghìn role khó duy trì. Người thiết kế nên bắt đầu từ tác vụ, tài nguyên và ngữ cảnh rồi mới chọn built-in/custom role.

### 7.1. Quy trình thiết kế

1. **Liệt kê tác vụ:** Ví dụ xem log, đọc metric, triển khai staging, khôi phục backup, xoay secret, thay đổi IAM.
2. **Xác định nhóm chủ thể:** Nhân viên thường, SRE, ứng dụng, CI/CD, nhà thầu, đối tác, kiểm toán.
3. **Xác định tài nguyên và môi trường:** Account/subscription/project, resource group, database, bucket, service, production hay development.
4. **Xác định thao tác tối thiểu:** Đọc, ghi, xóa, quản trị quyền; lưu ý một API có thể kéo theo nhiều permissions phụ trợ.
5. **Kiểm tra quyền phân tách:** Một người có nên vừa phê duyệt vừa triển khai không? Quyền có tạo hoặc gán quyền cao hơn không?
6. **Chọn role:** Ưu tiên role dựng sẵn với scope phù hợp; dùng custom role khi role có sẵn rộng hơn cần thiết và nền tảng hỗ trợ.
7. **Xác định owner, phê duyệt, thời hạn:** Tài liệu hóa ai được nhận role, ở đâu, vì sao và khi nào review.
8. **Thử nghiệm:** Kiểm tra các hành động cần thiết được phép và những hành động nhạy cảm ngoài phạm vi bị từ chối.

### 7.2. Ví dụ ma trận role

| Role nghiệp vụ | Đối tượng | Phạm vi | Hành động tiêu biểu | Giới hạn |
| --- | --- | --- | --- | --- |
| DevLogReader | Developer/SRE | Project dev của đội | Đọc log và metric | Không quản trị IAM hoặc đọc secret |
| StagingDeployer | Pipeline đã được duyệt | Staging của một dịch vụ | Triển khai phiên bản mới | Trust ràng buộc repository và môi trường |
| ProdIncidentViewer | Người trực vận hành | Log/metric production | Xem telemetry phục vụ điều tra | Phiên hạn chế, không thay đổi dịch vụ |
| ProdOperatorElevated | Người trực đã phê duyệt | Một service production | Thao tác xử lý sự cố được phép | MFA mạnh, thời hạn, audit, phê duyệt |
| CloudIAMAuditor | Security auditor | Những scope được duyệt | Đọc IAM policy và lịch sử thay đổi | Không gán quyền hoặc thay đổi policy |
| SecretRotator | Automation | Một nhóm secret được quản lý | Thay phiên bản secret theo workflow | Không đọc secret khác hoặc thay role |

Đây là **vai trò nghiệp vụ mẫu**, không phải tên role chuẩn của AWS, Azure hoặc Google Cloud. Khi triển khai cần ánh xạ thành chính sách, permission set, assignment hoặc binding cụ thể.

### 7.3. RBAC kết hợp ABAC và các điều kiện

**RBAC** cấp quyền theo role; **Attribute-Based Access Control (ABAC)** đánh giá thuộc tính của principal, tài nguyên hoặc ngữ cảnh. Hai mô hình có thể kết hợp:

~~~yaml
# Giả mã điều kiện, không áp trực tiếp vào cloud provider
role: log-reader
principal:
  employmentStatus: active
  department: platform
resource:
  environment: dev
  owningTeam: platform
decision:
  allowWhen:
    - principal.employmentStatus == active
    - principal.department == resource.owningTeam
    - resource.environment == dev
~~~

ABAC đòi hỏi thuộc tính từ nguồn đáng tin cậy và được cập nhật đúng hạn. Nếu người dùng có thể tự thay nhãn “team=platform” trên một resource, dùng nhãn đó làm điều kiện bảo mật có thể mở đường vượt quyền. Thuộc tính không thay thế việc phát hiện và thu hồi các role đã gán trực tiếp.

## 8. Cloud role trong Joiner–Mover–Leaver

**Joiner–Mover–Leaver** là cơ chế làm cho entitlement theo kịp tư cách thực tế của người dùng. Mục tiêu không đơn thuần là thay danh sách nhóm: sau mỗi sự kiện, phải so sánh **desired access** với **actual access** tại những cloud target liên quan.

| Sự kiện | Điều kiện đầu vào | Hành động trên role và entitlement | Bằng chứng hoàn tất |
| --- | --- | --- | --- |
| **Joiner** | Danh tính đã xác minh, trạng thái hợp lệ, công việc và ngày hiệu lực | Chọn role tối thiểu; phê duyệt; gán theo group/assignment/binding hoặc trust được duyệt | Principal truy cập được tác vụ cần thiết và không có quyền ngoài phạm vi |
| **Mover** | Đổi vai trò, team, dự án, môi trường hoặc cấp nhạy cảm | Tính lại role; thu hồi entitlement cũ; cấp role mới; xử lý quyền xung đột | Quyền cũ được xác minh đã thu hồi, quyền mới đúng phạm vi |
| **Leaver** | Nghỉ việc, hết hợp đồng, tài khoản bị đình chỉ | Chặn đăng nhập; thu hồi mọi assignment/binding, trust, key và session có thể thu hồi | Không còn đường truy cập được xác định; có kết quả từ đích |

### 8.1. Joiner: từ công việc đến role

Ví dụ kỹ sư mới gia nhập nhóm Platform. HRIS xác nhận ID **EMP-3021**, người quản lý và ngày bắt đầu. Hệ thống IAM xác định nhóm Platform Developers được cấp role chỉ đọc log và triển khai dev tại đúng project. Nếu người đó cần quyền production, workflow phải yêu cầu phê duyệt bổ sung và thời hạn phù hợp.

Các thông tin cần ghi: identity ID ổn định, source event, account/project/subscription ID, role ID, scope, owner, lý do cấp, phê duyệt, hiệu lực, hạn dùng nếu có, mã yêu cầu và bằng chứng sau cấp.

Việc có cùng chức danh “Software Engineer” **không mặc nhiên** cho mọi nhân viên quyền sửa production. Role catalog và policy phải phân biệt môi trường, dịch vụ và nghĩa vụ công việc.

### 8.2. Mover: thu hồi trước khi quyền cũ thành tồn dư

Một người chuyển từ đội Payment Operations sang đội Analytics. Nếu chỉ thêm role DataReader cho môi trường mới, người đó vẫn có quyền thao tác account thanh toán cũ. Tình trạng này là **privilege accumulation**.

Quy trình Mover phù hợp:

1. Nhận sự kiện thay đổi có ngày hiệu lực từ HRIS hoặc hệ thống có thẩm quyền.
2. Tính lại danh sách role/assignment hợp lệ theo công việc mới và những ngoại lệ đang được phê duyệt.
3. Truy vấn role hiện tại ở các cloud account, project, subscription, nested group, local principal và trust có liên quan.
4. Thu hồi quyền không còn hợp lệ, đồng thời điều phối thứ tự cấp quyền mới để hạn chế gián đoạn nghiệp vụ và xung đột **Separation of Duties (SoD)**.
5. Kiểm tra hiệu lực tại hệ thống đích, kể cả quyền có được từ đường gán khác.
6. Ghi nhận quyền tạm thời ngoại lệ cùng owner và thời hạn, tránh biến ngoại lệ thành quyền vĩnh viễn.

**Quan trọng:** Tên role có thể giữ nguyên nhưng scope đổi. “Reader trên project dev” và “Reader trên organization” không tương đương. Khi đối soát phải so cả role, principal và phạm vi.

### 8.3. Leaver: thu hồi role không có nghĩa kết thúc mọi session

Khi nhân viên nghỉ việc, IdP thường khóa danh tính để ngăn đăng nhập mới. Tuy nhiên, quyền tại cloud có thể còn qua:

- Role assignment/binding trực tiếp tại nhiều account hoặc project.
- Nhóm lồng nhau hoặc role được cấp qua account phụ.
- Tài khoản cloud-local không được liên kết đúng với IdP.
- Credential dài hạn, API key hoặc token do người đó nắm giữ.
- Session/temporary credentials đã phát hành trước thời điểm thu hồi.
- Quyền được người đó sử dụng để impersonate service account hoặc assume một role khác.

Thực hiện Leaver theo thứ tự có kiểm soát: vô hiệu hóa danh tính nguồn, thu hồi entitlement trên từng target, xử lý credential/session theo cơ chế của provider, chuyển giao service account hoặc pipeline do người đó sở hữu và xác minh trạng thái cuối. **Một session đã phát hành có thể chưa bị hủy tức thì chỉ vì assignment gốc thay đổi**; cách thu hồi cụ thể tùy provider, thời hạn token và cơ chế dịch vụ.

### 8.4. Không xóa role dùng chung khi một người nghỉ việc

Giả sử role **PlatformLogReader** đang phục vụ 40 kỹ sư. Nếu một kỹ sư nghỉ việc, hành động đúng là loại principal đó khỏi những đường được cấp role (group, assignment, trust hoặc binding). Xóa role definition sẽ ảnh hưởng 39 người còn lại và có thể làm ngừng automation.

Chỉ retire role definition khi **toàn tổ chức không còn nhu cầu** hoặc đã có vai trò thay thế, với kế hoạch di chuyển mọi principal phụ thuộc và kiểm tra quyền sau chuyển đổi.

## 9. Provisioning, SSO, SCIM và role mapping

Khi hệ thống danh tính doanh nghiệp quản lý quyền cloud, cần phân biệt các luồng:

| Thành phần | Vai trò chính | Điều không thể mặc nhiên giả định |
| --- | --- | --- |
| **IdP** | Lưu user, group, thuộc tính; xác thực và áp điều kiện đăng nhập | Không tự cấp role đúng trong mọi cloud account |
| **SSO qua SAML/OIDC** | Chuyển bằng chứng xác thực đến bên tin cậy | Không đồng nghĩa đã provision account hoặc thu hồi session cũ |
| **SCIM** | Quản lý user/group qua API tại hệ thống hỗ trợ | Không phải API phổ quát để tạo mọi cloud role/assignment |
| **IGA/JML workflow** | Phê duyệt, tính quyền mong muốn, điều phối cấp/thu hồi | Không nên coi request thành công là bằng chứng đã thực thi tại đích |
| **Cloud IAM** | Áp role/policy/trust/scope cho truy cập tài nguyên | Không phải lúc nào cũng tự hiểu trạng thái nhân sự |
| **Reconciliation** | Đọc lại trạng thái quyền thực tế, phát hiện chênh lệch | Không thể chỉ dựa vào lịch sử request đã gửi |

### 9.1. Luồng cập nhật role sau thay đổi nhân sự

~~~mermaid
sequenceDiagram
    participant HR as HRIS
    participant L as Lifecycle / IGA
    participant ID as IdP / Groups
    participant C as Cloud IAM
    participant A as Audit / Reconciliation
    HR->>L: Mover: thay đổi role nghiệp vụ
    L->>L: Xác định desired entitlements
    L->>ID: Cập nhật thuộc tính và membership
    L->>C: Thu hồi grant cũ, cấp grant được duyệt
    C-->>L: Kết quả API
    L->>C: Đọc lại assignment, role, scope và trust
    C-->>L: Actual entitlements
    L->>A: So sánh actual với desired
    alt Không còn lệch quyền
        A-->>L: Verified
    else Có lệch hoặc lỗi
        A-->>L: Escalate + retry có kiểm soát
    end
~~~

Một hệ thống có thể dùng đồng bộ membership từ IdP để gián tiếp cấp role; một hệ thống khác phải gọi API cloud IAM riêng. **Thiết kế cần xác định rõ nguồn của từng entitlement và cách thu hồi tại đích**, không mặc định SCIM sẽ giải quyết toàn bộ.

### 9.2. Idempotency và lỗi từng phần

Trong JML tự động, một request có thể thành công tại AWS nhưng thất bại ở Azure. Nên:

1. Có khóa tương quan cho mỗi sự kiện, identity và target để chống tạo assignment trùng khi retry.
2. Đặt trạng thái rõ: pending, applied, verified, failed hoặc exception.
3. Chỉ đánh dấu verified sau khi đọc lại quyền tại cloud target.
4. Cảnh báo ưu tiên với lỗi thu hồi quyền production/privileged role.
5. Có owner xử lý ngoại lệ, thời hạn khắc phục và ghi nhận lý do.

Nếu source event bị gửi lặp, workflow không được tạo hai con đường cấp quyền khác nhau. Nếu một cloud target không phản hồi, trạng thái phải phản ánh **chưa xác minh**, không tự suy ra đã an toàn.

## 10. Privileged role, quyền có thời hạn và quyền nâng cao

Một role có quyền thay đổi IAM, truy cập secret, xóa backup, tắt audit log hoặc quản trị tổ chức có rủi ro cao. **Privileged Access Management (PAM)** và các cơ chế như JIT/just-in-time elevation hoặc PIM có thể giúp giới hạn thời gian và tăng khả năng kiểm soát.

Quy trình cấp quyền cao nên có:

- **Eligibility:** Ai đủ điều kiện yêu cầu quyền và tại phạm vi nào?
- **Reason:** Cần thao tác nào, ticket/incident nào, trong bao lâu?
- **Approval:** Ai xác nhận độc lập nếu rủi ro yêu cầu?
- **Strong authentication:** MFA chống phishing khi khả thi và chính sách thiết bị phù hợp.
- **Activation:** Quyền có hiệu lực trong thời gian xác định, kèm session/audit.
- **Expiration/revocation:** Quyền được thu hồi khi hết thời gian hoặc sự kiện thay đổi.
- **Verification:** Đối soát assignment, grant và phiên có liên quan sau khi kết thúc.

Ví dụ người trực vận hành chỉ được **đọc production thường xuyên**. Khi có incident nghiêm trọng, họ yêu cầu quyền **ProdOperatorElevated** cho một dịch vụ cụ thể trong 45 phút, được phê duyệt theo quy trình. Hết thời gian, quyền nâng cao phải được kết thúc và kiểm chứng.

### 10.1. Đường nâng đặc quyền gián tiếp

Một principal không có role Administrator vẫn có thể nguy hiểm nếu có quyền:

- Tạo hoặc sửa role/policy và tự gán quyền.
- Gán role cao cho principal khác.
- Impersonate service account có quyền mạnh.
- Thay trust policy để principal bên ngoài đảm nhận role.
- Đọc secret/credential của workload có đặc quyền.
- Thay đổi automation/pipeline triển khai đang nắm role production.

**Đánh giá rủi ro role phải xét quyền có thể dẫn tới quyền khác**, không chỉ xét role name hoặc số lượng permissions.

### 10.2. Break-glass role

Tài khoản hoặc role khẩn cấp giúp xử lý khi IdP/SSO hoặc cơ chế cấp quyền thường xuyên gặp sự cố. Thiết kế cần xác định:

- Người chịu trách nhiệm và cách bảo quản phương thức truy cập khẩn cấp.
- Điều kiện kích hoạt, cảnh báo và lưu dấu mọi lần sử dụng.
- Tách biệt với đường truy cập thường ngày, giới hạn người đủ thẩm quyền.
- Kiểm tra khả năng sử dụng có kiểm soát và rà soát sau mỗi lần kích hoạt.

Không dùng quyền khẩn cấp như giải pháp thay thế lâu dài cho role catalog bị thiết kế thiếu.

## 11. Role cho service account và workload

Cloud IAM không chỉ phục vụ nhân viên. Một service, máy ảo, container, function hoặc pipeline CI/CD cần role phù hợp để gọi API. **Workload identity** nên là principal được quản lý riêng, có owner và phạm vi quyền rõ ràng.

| Trường hợp | Cách cấp quyền nên cân nhắc | Kiểm soát |
| --- | --- | --- |
| VM/compute trong AWS | Instance profile gắn IAM role, nhận credential tạm thời qua nền tảng | Role riêng từng workload, ít quyền, không lưu key dài hạn |
| Workload trong Azure | Managed identity + Azure RBAC role assignment tại scope cần thiết | Owner, scope, quyền không vượt nhu cầu ứng dụng |
| Service trong Google Cloud | Service account được gán IAM roles phù hợp | Quyền impersonation, service account key và owner |
| CI/CD nằm ngoài cloud | OIDC/Workload Identity Federation khi phù hợp | Giới hạn issuer, audience, subject, repository/nhánh/môi trường |
| Tích hợp kế thừa dùng secret tĩnh | Secret manager, rotation và quy trình hết hạn | Lộ secret, chia sẻ, owner mồ côi, thời hạn sử dụng |

**Không chạy ứng dụng production bằng tài khoản cá nhân của lập trình viên.** Khi người đó rời công ty, ứng dụng có thể bị gián đoạn hoặc secret của họ còn nằm trong pipeline. Workload cần danh tính và role riêng, với ownership chuyển giao được.

Vòng đời JML cho workload:

- **Joiner:** Đăng ký workload, owner, mục đích, tạo principal, role/trust và audit thông qua workflow/IaC được duyệt.
- **Mover:** Khi đổi team, project, repository hoặc môi trường, cập nhật trust và role, rút quyền cũ rồi xác minh.
- **Leaver:** Khi service/pipeline ngừng hoạt động, thu hồi binding, trust, credential, key và kiểm tra không còn đường truy cập hợp lệ.

Một role không còn được ứng dụng sử dụng nên được đánh giá để thu hồi; **không chỉ dựa vào số lần gọi API gần đây** vì job định kỳ có thể ít khi chạy nhưng vẫn cần quyền trong thời gian hợp lệ.

## 12. Rà soát role và quyền truy cập tồn dư

Trong kiểm toán IAM, cần phân biệt:

- **Desired access:** Entitlement hợp lệ theo chức trách, trạng thái danh tính, chính sách, phê duyệt và phạm vi công việc.
- **Assigned access:** Role assignment, binding, membership, policy hoặc trust thực sự đang được cấu hình.
- **Effective access:** Quyền thực tế được đánh giá sau khi xét kế thừa, deny, boundary, resource policy và các điều kiện có liên quan.

Ví dụ sau là **giả mã**, không phải code dùng trực tiếp trên AWS/Azure/GCP:

~~~text
sourceEvent = getAuthorizedLifecycleEvent(identityId)
targets = discoverAccountsAndProjects(identityId)

for target in targets:
    desired = calculateApprovedEntitlements(identityId, target)
    actual = enumerateCurrentGrantsAndTrust(identityId, target)
    stale = normalize(actual) - normalize(desired)

    for grant in stale:
        revokeGrant(grant)

    verify = evaluateRemainingEffectiveAccess(identityId, target)
    if verify.matchesDesiredAccess:
        recordVerified(sourceEvent, target)
    else:
        createEscalation(sourceEvent, target, verify.diff)
~~~

Phép trừ chỉ có ý nghĩa sau khi chuẩn hóa cùng **principal, role, scope, điều kiện, thời hạn và nguồn quyền**. Một binding tại organization và binding tại project không thể coi là giống nhau dù cùng tên role. Quyền kế thừa hoặc được cấp qua group cần được đánh giá bằng cách thích hợp của cloud provider.

### 12.1. Mẫu báo cáo access review

| Dữ liệu kiểm toán | Vì sao cần? |
| --- | --- |
| Principal ID, loại danh tính, trạng thái nguồn | Phân biệt nhân viên, đối tác, guest, service account |
| Role/permission set ID và phiên bản | Biết chính xác tập quyền đang đánh giá |
| Account/project/subscription và resource scope | Không bỏ sót quyền rộng hoặc quyền kế thừa |
| Nguồn cấp quyền | Group, trực tiếp, federation, resource policy, impersonation |
| Role owner và business owner | Có người đủ thẩm quyền xác nhận nhu cầu |
| Căn cứ phê duyệt, thời gian hiệu lực và hạn dùng | Loại bỏ quyền tạm thời tồn quá lâu |
| Kết quả sử dụng nếu có | Hỗ trợ tìm quyền thừa; cần xét bối cảnh |
| Quyết định review và kết quả thực thi | Phân biệt “đã yêu cầu thu hồi” với “đã thu hồi” |
| Trạng thái xác minh tại đích | Chứng minh không còn đường truy cập ngoài ý muốn |

### 12.2. Trạng thái review cần có ý nghĩa

~~~text
REQUESTED    Yêu cầu cấp/thu hồi đang chờ xử lý
APPROVED     Quyết định nghiệp vụ được ghi nhận
APPLIED      API hoặc tác vụ thay đổi đã báo thành công
VERIFIED     Đã đọc lại target và xác minh trạng thái mong muốn
FAILED       Thao tác lỗi và có hành động khắc phục
EXCEPTION    Có ngoại lệ rõ owner, lý do và hạn hết hiệu lực
~~~

Chỉ trạng thái **VERIFIED** mới cho biết có bằng chứng kỹ thuật rằng thay đổi ở đích đạt yêu cầu được kiểm tra. Khi session cũ không thể thu hồi tức thì, báo cáo cần ghi rõ độ trễ hoặc hạn hiệu lực và biện pháp giảm rủi ro.

## 13. Tình huống xuyên suốt: kỹ sư chuyển từ Dev sang SRE

Giả sử công ty có IdP tập trung và ba môi trường: **learning-dev**, **learning-staging**, **learning-prod**. Nhân viên **Minh**, có ID nội bộ **EMP-3021**, ban đầu là lập trình viên của sản phẩm Learning.

### 13.1. Joiner

HRIS xác nhận Minh gia nhập. IGA tạo hoặc liên kết tài khoản IdP và gán nhóm dev. Tổ chức duyệt quyền **DevLogReader** và **DevDeployer** chỉ tại môi trường learning-dev. Minh có thể xem log và triển khai dev, nhưng không thể thay IAM production.

### 13.2. Mover

Minh chuyển sang SRE, cần quan sát production và có khả năng nhận quyền xử lý sự cố tạm thời. Desired access mới là **ProdIncidentViewer** thường trực; **ProdOperatorElevated** chỉ có thể kích hoạt theo approval và thời hạn. Workflow phải thu hồi role triển khai dev nếu công việc mới không cần, đồng thời rà soát mọi assignment trực tiếp hoặc role session còn tồn tại.

~~~mermaid
flowchart LR
    HR["HRIS: Mover"] --> D["Tính desired roles"]
    D --> OLD["Thu hồi DevDeployer khi không còn cần"]
    D --> NEW["Cấp ProdIncidentViewer"]
    NEW --> ELEV["ProdOperatorElevated: chỉ JIT + approval"]
    OLD --> CHECK["Đọc lại IAM thực tế"]
    NEW --> CHECK
    ELEV --> CHECK
    CHECK --> AUD["Verified / Exception + Audit"]
~~~

### 13.3. Leaver

Khi Minh nghỉ việc, IdP khóa account theo ngày hiệu lực. Hệ thống thu hồi role assignments/bindings ở các môi trường, xem xét quyền qua nhóm và trực tiếp, xử lý credential/session theo provider, và chuyển giao ownership của automation mà Minh quản lý. Role definition **ProdIncidentViewer** vẫn được giữ nếu các SRE khác còn sử dụng.

Một bản ghi kiểm toán minh họa:

~~~json
{
  "eventId": "JML-MOVER-0207",
  "identityId": "EMP-3021",
  "eventType": "mover",
  "target": "learning-dev",
  "role": "DevDeployer",
  "scope": "project:learning-dev",
  "operation": "revoke_assignment",
  "approvalReference": "ROLE-CHANGE-0207",
  "status": "verification_pending",
  "occurredAt": "2026-11-23T07:00:00Z"
}
~~~

Trạng thái **verification_pending** có nghĩa chưa được khẳng định quyền đã hết hiệu lực. Sau khi đọc lại cloud IAM và xác nhận không còn assignment hoặc đường truy cập tương đương, workflow mới chuyển trạng thái verified, lưu thời điểm và bằng chứng.

### 13.4. Vì sao role name không đủ?

Giả sử ở dev và prod đều có một role tên **Reader**, nhưng gán ở scope organization cho Minh sẽ tạo phạm vi truy cập rộng hơn nhiều so với dự kiến. Quy trình đối soát phải dùng **định danh role, provider, scope và nguồn cấp quyền**. Tài liệu “đã gỡ Reader ở dev” không đủ nếu Minh vẫn được kế thừa Reader từ organization.

## 14. Những lỗi thiết kế và cách phòng tránh

| Lỗi | Điều có thể xảy ra | Biện pháp kiểm soát |
| --- | --- | --- |
| Role quá rộng hoặc cấp ở scope cha | Người dùng truy cập dữ liệu và dịch vụ ngoài công việc | Chọn permissions tối thiểu và gán ở scope hẹp |
| Chỉ thêm role mới sau Mover | Quyền của đội cũ tích tụ | Tính desired vs actual, thu hồi role cũ có xác minh |
| Dựa hoàn toàn vào IdP group | Bỏ qua role assignment trực tiếp, local user hoặc resource policy | Inventory mọi nguồn cấp quyền trên cloud target |
| Cho phép trust từ principal quá rộng | Bên ngoài có thể assume role hoặc dùng workload principal trái dự kiến | Khóa issuer/audience/subject, principal và điều kiện phù hợp |
| Quyền sửa IAM bị xem nhẹ | Người dùng tự nâng đặc quyền hoặc gán role cho người khác | Phân tách IAM administration, giới hạn policy mutation |
| Dùng key tĩnh cho role/workload | Key vẫn sống sau khi người tạo nghỉ việc | Credential ngắn hạn/federation, rotation và owner rõ |
| Xóa role definition khi một người nghỉ | Làm gián đoạn nhiều người hoặc workload khác | Thu hồi assignment cụ thể, giữ role dùng chung nếu còn nhu cầu |
| Tin rằng API revoke thành công là đủ | Actual access vẫn còn do lỗi đồng bộ, cache hoặc đường quyền khác | Đọc lại và xác minh quyền hiệu lực |
| Bỏ qua session đã cấp | Quyền tồn tại đến khi token/session hết hạn | Cơ chế revoke phù hợp, giới hạn thời gian và cảnh báo |
| Không có owner của role | Không ai chịu trách nhiệm review, phê duyệt và retire | Role catalog, owner và kỳ review bắt buộc |
| Không phân biệt role Azure với role Entra | Phê duyệt sai quyền quản trị thư mục/tài nguyên | Lập tài liệu mô hình quyền riêng và kiểm tra scope |
| Chỉ xét role IAM, bỏ qua quyền truy cập dữ liệu | IAM cho phép gọi dịch vụ nhưng cơ chế dữ liệu còn quyền riêng hoặc ngược lại | Kiểm tra quyền ở cả management plane và data plane |

## 15. Chỉ số quản trị cloud role

| Chỉ số | Ý nghĩa và cách diễn giải |
| --- | --- |
| **Số stale role assignments** | Entitlement còn tồn tại sau khi tư cách hoặc nhiệm vụ đã thay đổi |
| **P95 thời gian thu hồi role sau Leaver** | Khoảng từ thời điểm Leaver có hiệu lực đến lúc target xác minh quyền đã thu hồi |
| **Tỷ lệ privileged roles có hạn dùng/review** | Mức độ kiểm soát quyền cao thay vì cấp vô thời hạn |
| **Số principal có đường nâng đặc quyền** | Bao gồm quyền sửa IAM, role impersonation, trust và secret nhạy cảm |
| **Tỷ lệ role có owner và mô tả mục đích** | Chất lượng danh mục role phục vụ phê duyệt và rà soát |
| **Tỷ lệ JML events được VERIFIED** | Tỷ lệ sự kiện có kết quả đối soát thật tại đích |
| **Số role không còn sử dụng hoặc trùng chức năng** | Cơ hội thu gọn catalog và giảm sai sót |
| **Tỷ lệ workload dùng credential ngắn hạn** | Mức độ giảm phụ thuộc access key/secret lâu dài |

Các chỉ số cần phân loại theo **production/non-production, người dùng/workload, mức đặc quyền và provider**. Một stale privileged role trên production phải được ưu tiên hơn quyền đọc hạn chế trên sandbox.

## 16. Bài tập áp dụng

### Bài tập 1: Xây role tối thiểu

Yêu cầu: Nhóm kiểm toán cần xem cấu hình IAM và log liên quan ở một môi trường production, không được sửa policy hoặc triển khai mã.

Hãy xác định principal/group đủ điều kiện, scope tài nguyên, role/permissions cần đọc, người phê duyệt, cách xác thực, thời hạn và cách xác minh quyền ghi bị từ chối.

**Gợi ý:** Role “Owner/Administrator” quá rộng. Xem xét role chỉ đọc cụ thể theo dịch vụ và phạm vi; kiểm tra quyền đọc dữ liệu nhạy cảm có nằm ngoài mục đích kiểm toán không.

### Bài tập 2: Tìm quyền tồn dư

Một nhân viên vừa chuyển từ nhóm A sang B. Hệ thống IdP đã xóa họ khỏi nhóm A, nhưng Azure subscription production vẫn có **Contributor assignment trực tiếp** và Google Cloud project vẫn có **IAM binding kế thừa**.

**Câu hỏi:** Có thể đánh dấu sự kiện Mover là hoàn tất chưa?

**Đáp án:** Chưa. Phải xác định entitlement nào còn hợp lệ, thu hồi quyền không được duyệt tại các scope đích, kiểm tra quyền còn hiệu lực qua những đường cấp khác và lưu bằng chứng sau thu hồi.

### Bài tập 3: Role cho pipeline CI/CD

Pipeline chỉ được triển khai staging nhưng đang dùng access key có quyền quản trị toàn cloud account. Hãy đề xuất cấu hình tốt hơn.

**Gợi ý đáp án:** Dùng một principal/role triển khai riêng, ưu tiên OIDC federation hoặc identity do nền tảng quản lý để cấp credential ngắn hạn; giới hạn issuer/audience/subject tương ứng repository và môi trường; permissions chỉ cho tác vụ deployment trên tài nguyên staging; kiểm soát owner, log và vòng đời thu hồi khi pipeline bị xóa.

## 17. Checklist thực hành khi cấp hoặc thu hồi cloud role

1. **Nhận dạng:** Biết chính xác principal, identity ID ổn định và loại danh tính.
2. **Nhu cầu:** Role có mô tả công việc, owner và căn cứ phê duyệt.
3. **Phạm vi:** Xác định rõ AWS account, Azure subscription/resource scope hay Google Cloud project/resource.
4. **Ít quyền:** Chọn permissions nhỏ nhất; xem cả các đường nâng đặc quyền gián tiếp.
5. **Tin cậy:** Với federation/assume role, giới hạn principal, issuer, audience và điều kiện.
6. **Xác thực:** Áp SSO/MFA hoặc workload federation/managed identity phù hợp.
7. **Thời gian:** Quyền nhạy cảm ưu tiên phiên/ngày hết hạn và review.
8. **JML:** Joiner cấp đúng role; Mover thu hồi role cũ; Leaver xử lý assignments, trust, credential và session.
9. **Thực thi:** Đồng bộ bằng API/SCIM khi có hỗ trợ, retry an toàn và ghi nhận lỗi từng target.
10. **Kiểm chứng:** Đọc lại quyền thực tế; lưu bằng chứng và owner của mọi ngoại lệ.
11. **Workload:** Service account, pipeline, CI/CD role có owner và vòng đời độc lập với nhân viên.
12. **Kiểm toán:** Có lịch sử định nghĩa role, người nhận, phê duyệt, thay đổi, review và thu hồi.

## 18. Tổng kết

**Cloud role** giúp nhóm quyền thành vai trò có thể quản lý, nhưng cách biểu diễn khác nhau giữa nhà cung cấp: **AWS IAM role** là thực thể có trust policy và permissions policy, thường được đảm nhận để nhận credential tạm thời; **Azure RBAC role** là tập quyền gắn cho principal tại một scope; **Google Cloud IAM role** là tập permissions được cấp qua IAM binding tại tài nguyên.

Trong quản lý vòng đời danh tính, cần quản lý đồng thời **định nghĩa role** và **entitlement gán cho principal**. Kết nối HRIS, IdP, SSO, SCIM/provisioning, RBAC/ABAC và cloud IAM giúp các sự kiện **Joiner–Mover–Leaver** dẫn đến quyền đúng tại tài nguyên. Tổ chức chỉ có thể kết luận đã giảm được quyền truy cập tồn dư khi những role assignment, binding, trust và credential không còn hợp lệ đã được thu hồi, **quyền thực tế được xác minh** và có bằng chứng kiểm toán.
