# Workload role

**Chương:** Cloud IAM  
**Chủ đề:** Workload role  
**Phạm vi:** Thiết kế, cấp phát, sử dụng, giám sát và thu hồi vai trò cho ứng dụng, service account, máy ảo, container, pipeline CI/CD và các danh tính phi con người trong môi trường cloud. Nội dung đặt trong mô hình quản lý vòng đời danh tính **Joiner–Mover–Leaver (JML)**, kết nối IdP, SSO, SCIM, RBAC/ABAC, kiểm toán và giảm quyền truy cập tồn dư.

## 1. Workload role là gì?

**Workload** là một chương trình hoặc tác vụ thực thi: API server, batch job, container, serverless function, máy ảo, ứng dụng trên Kubernetes hoặc pipeline triển khai. Workload cần gọi API và truy cập tài nguyên cloud mà không có người dùng tương tác ở mỗi yêu cầu.

**Workload role** là cách tổ chức và cấp **quyền truy cập cho danh tính của workload**. Tên gọi và cơ chế cụ thể khác nhau theo nền tảng:

- **AWS:** Workload thường dùng **IAM role** và nhận **temporary credentials** qua môi trường thực thi hoặc Security Token Service (STS). Role có trust policy và permissions policy.
- **Microsoft Azure:** Workload có thể dùng **managed identity** hoặc service principal, rồi được cấp **Azure RBAC role assignment** ở subscription, resource group hoặc resource.
- **Google Cloud:** Workload dùng **service account** hoặc federated workload principal; quyền được cấp qua **IAM role bindings** tại project hoặc tài nguyên. Một số luồng cho phép service account impersonation.
- **Kubernetes:** Workload sử dụng Kubernetes **ServiceAccount** để nhận danh tính trong cluster; cloud access thường cần thêm liên kết/federation sang một principal hoặc role cloud. Kubernetes RBAC và cloud IAM là **hai hệ thống phân quyền riêng**.

Ví dụ: API xử lý đơn hàng cần đọc secret kết nối cơ sở dữ liệu, gửi sự kiện tới một queue và ghi một bucket nhất định. Workload role nên chỉ cho phép ba nhóm tác vụ này tại môi trường thích hợp. Nó **không cần** quyền tạo IAM administrator, xóa tất cả object hoặc đọc secret của ứng dụng khác.

Trong module **Identity Lifecycle**, một workload role cần được xem xét qua toàn bộ **Joiner – Mover – Leaver**:

1. **Joiner:** Workload được đăng ký, xác minh nguồn triển khai, gắn owner và nhận quyền tối thiểu.
2. **Mover:** Workload đổi repository, môi trường, team, tài nguyên, runtime hoặc nhiệm vụ; quyền và trust cũ được thu hồi.
3. **Leaver:** Workload bị ngừng, service bị xóa hoặc tích hợp hết hạn; role binding, credential và các đường truy cập không còn hợp lệ được vô hiệu hóa và xác minh.

**Mục tiêu học tập:** Phân biệt workload identity, role, trust và credential; chọn cơ chế xác thực ít phụ thuộc khóa tĩnh; viết yêu cầu quyền tối thiểu; vận hành role trên AWS/Azure/Google Cloud/Kubernetes; xây luồng JML và bằng chứng kiểm toán cho danh tính phi con người.

## 2. Các đối tượng phải phân biệt

| Đối tượng | Vai trò | Ví dụ |
| --- | --- | --- |
| **Workload** | Mã đang chạy hoặc tác vụ tự động | Payment API, cron job, CI pipeline |
| **Workload identity** | Danh tính nhận diện workload tại runtime/issuer | Service account, managed identity, workload principal |
| **Principal** | Chủ thể mà IAM đánh giá trong một yêu cầu | Role session, Azure managed identity, Google service account |
| **Role** | Thực thể hoặc tập quyền dùng để cấp phép | AWS IAM role, Azure RBAC role, Google IAM role |
| **Trust / federation** | Quy tắc quyết định nguồn danh tính nào được nhận hoặc đổi lấy quyền | OIDC issuer + subject; IAM role trust policy |
| **Permission / policy** | Action, resource và condition cụ thể | Đọc một secret, ghi một queue |
| **Credential** | Bằng chứng gọi API hoặc nhận phiên | Token ngắn hạn, STS credentials, certificate |
| **Role binding / assignment** | Liên kết principal với role ở phạm vi cụ thể | Managed identity có Storage Blob Data Reader |
| **Workload owner** | Đơn vị chịu trách nhiệm mục đích và vòng đời danh tính | Platform Team, service owner |
| **JML event** | Sự kiện đăng ký, thay đổi hoặc chấm dứt workload | Tạo service, chuyển repo, retire app |

**Không đồng nhất role với identity:** Service account có thể được gán nhiều role. Một role có thể được nhiều service cùng sử dụng, nhưng gắn chung role rộng cho các workload khác nhau làm khó việc giới hạn phạm vi và truy vết. Trong AWS, một IAM role thường đồng thời là principal của phiên và chứa liên kết policy/trust; trong Azure/Google Cloud, role thường là tập permissions được gán cho principal qua assignment/binding.

**Không đồng nhất xác thực với phân quyền:** Token hợp lệ chứng minh nguồn hoặc danh tính theo chính sách trust; còn quyền thực thi yêu cầu phụ thuộc role/policy của cloud target.

### 2.1. Ví dụ một yêu cầu truy cập

Một pod của dịch vụ báo cáo cần đọc object trong bucket báo cáo:

~~~text
Workload: reporting-api
Runtime identity: service account của pod
Federation: workload được chứng minh từ issuer đã duyệt
Cloud principal: reporting-reader
Role: đọc object trong bucket reporting-dev
Credential: token/phiên ngắn hạn
Request: storage.read(reporting-dev/object-123)
Decision: cloud IAM kiểm tra action + resource + principal + conditions
~~~

Nếu pod xác thực đúng nhưng role chỉ cho phép đọc bucket khác, yêu cầu phải bị từ chối. Nếu role cho phép đọc mọi bucket thì chính sách đã quá rộng so với mục đích, dù pipeline đăng nhập hoàn toàn hợp lệ.

## 3. Vì sao workload identity cần vòng đời riêng?

Danh tính người dùng thường có HRIS làm nguồn sự kiện. Workload không có hồ sơ nhân sự; nó được tạo và thay đổi bởi deployment, repository, workflow, CMDB, service catalog và đội sở hữu hệ thống.

Các nguồn kích hoạt đáng xem xét:

| Sự kiện | Dữ liệu có thẩm quyền | Tác động lên IAM |
| --- | --- | --- |
| Tạo service mới | Service catalog, yêu cầu triển khai đã phê duyệt | Tạo principal, chọn role, thiết lập trust |
| Thêm job định kỳ | Workflow/owner của dịch vụ | Cấp quyền độc lập nếu nhiệm vụ khác |
| Chuyển từ dev sang production | Quy trình thay đổi môi trường | Phê duyệt role production và tách trust |
| Đổi team sở hữu | Service ownership/CMDB | Chuyển owner, review và điều chỉnh scope |
| Đổi repository hoặc nhánh CI | Repo registry, pipeline config | Cập nhật subject/conditions trong trust |
| Di chuyển cloud account/project | Kế hoạch migration | Cấp quyền đúng đích mới, thu hồi đích cũ |
| Đóng tích hợp bên thứ ba | Hợp đồng/integration registry | Thu hồi federated principal, role và credential |
| Retire ứng dụng | Decommission ticket | Thu hồi role, binding, key, trust và kiểm chứng |

Khi lập trình viên nghỉ việc, **workload của ứng dụng vẫn có thể cần hoạt động**. Quy trình Leaver của con người phải chuyển giao ownership và kiểm tra những credential do người đó tạo/quản lý; không tự động xóa identity ứng dụng nếu dịch vụ vẫn hợp lệ.

### 3.1. Hai vòng đời liên quan nhưng độc lập

- **Vòng đời workload:** Requested → Registered → Active → Changed/Migrating → Retiring → Retired.
- **Vòng đời role definition và assignment:** Draft → Approved → Active → Reviewed → Replaced/Revoked; assignment cụ thể có owner, scope, ngày hiệu lực và ngày kết thúc.

Một workload đã retire nhưng role definition dùng chung chưa chắc cần xóa. Tuy nhiên, **mọi entitlement được cấp riêng cho workload đó phải được rà soát và thu hồi**. Nếu role không còn principal nào hợp lệ sử dụng, có thể tiếp tục quy trình retire role theo chính sách tổ chức.

## 4. Kiến trúc truy cập cloud bằng workload role

~~~mermaid
flowchart TD
    SRC["Service catalog / IaC / CI-CD<br/>Workload ID, owner, lifecycle"] --> GOV["Identity Lifecycle / IGA<br/>Phê duyệt, JML, desired access"]
    GOV --> PROV["Provision role, trust, binding<br/>Qua API hoặc IaC"]
    SRC --> RUN["Runtime / pipeline<br/>VM, Pod, Function, CI job"]
    RUN --> ISS["Trusted identity source<br/>Managed identity hoặc OIDC issuer"]
    ISS --> EX["Federation / token exchange<br/>Xác minh token và trust"]
    EX --> CREDS["Cloud principal + temporary credential"]
    CREDS --> IAM["Cloud IAM<br/>Role, policy, scope, condition"]
    PROV --> IAM
    IAM --> RES["Cloud resources<br/>Storage, Queue, DB, Secret"]
    GOV --> REC["Reconciliation / audit"]
    ISS --> REC
    EX --> REC
    IAM --> REC
~~~

Mô hình minh họa **identity, trust, quyền và nguồn vòng đời**; không phải mọi runtime đều cần một dịch vụ token exchange độc lập. Managed identity hoặc instance role có thể được nền tảng cung cấp credential qua endpoint/agent chuyên trách.

### 4.1. Các bước điển hình

1. Workload được triển khai bằng một runtime identity xác định.
2. Runtime nhận bằng chứng danh tính từ nguồn đáng tin cậy hoặc metadata service do cloud quản lý.
3. Nếu dùng federation, cloud xác minh issuer, chữ ký, audience, subject, thời hạn và các điều kiện trust.
4. Nền tảng cấp session/credential ngắn hạn hoặc nhận diện principal đã được cấu hình.
5. Workload gọi cloud API; IAM đánh giá permissions, resource scope, điều kiện và giới hạn áp dụng.
6. Hệ thống ghi log token exchange/role assumption, sử dụng API và thay đổi quyền theo khả năng hỗ trợ.
7. Quy trình lifecycle so sánh quyền mong muốn với quyền thực tế, xử lý drift, thu hồi quyền khi workload thay đổi.

**Ranh giới an toàn:** Runtime chứng minh “đúng workload” không đồng nghĩa có quyền với mọi tài nguyên. Trust quyết định **ai có thể nhận vai trò**, còn permissions quyết định **vai trò đó được làm gì**.

### 4.2. Ai được quyền tạo workload role?

Tạo role, gán quyền và sửa trust là hành động nhạy cảm vì có thể dẫn đến nâng đặc quyền. Quy trình nên phân tách:

- **Service owner:** Xác định nhiệm vụ, dữ liệu cần truy cập và mức rủi ro.
- **Cloud IAM/security owner:** Phê duyệt quyền, trust và các ngoại lệ quan trọng.
- **Platform/automation:** Triển khai role/assignment theo chính sách và ghi audit.
- **Workload runtime:** Chỉ được nhận credential và thực thi những thao tác đã được phê duyệt.
- **Reconciliation:** Đọc lại role/permission tại hệ thống đích để xác minh.

Không nên để một pipeline vừa tự cấp quyền IAM Administrator vừa tự dùng quyền đó cho mọi deployment nếu không có kiểm soát độc lập.

## 5. Workload identity và credential: ưu tiên ngắn hạn

Cơ chế nhận credential có ảnh hưởng trực tiếp tới rủi ro của workload role.

| Mô hình | Cách hoạt động | Rủi ro cần theo dõi |
| --- | --- | --- |
| **Managed identity / instance role** | Cloud runtime cung cấp identity/temporary credential cho workload | Role quá rộng; SSRF/metadata endpoint bị lạm dụng; workload chia sẻ runtime |
| **OIDC workload federation** | Workload dùng token do issuer ký để đổi lấy credential cloud | Trust thiếu điều kiện issuer/audience/subject; issuer không được bảo vệ |
| **Kubernetes projected service account token** | Runtime cung cấp token có audience và thời hạn được cấu hình | Token bị đọc/đánh cắp trong pod; role binding quá rộng |
| **Service account impersonation** | Principal nguồn được phép nhận token của service account đích | Quyền impersonate mở đường nâng đặc quyền |
| **Client secret / access key dài hạn** | Ứng dụng mang secret/key độc lập để gọi API | Rò rỉ, không có rotation, tồn dư sau khi ngừng workload |
| **Chứng thư máy / mTLS trong hệ thống phù hợp** | Chứng thư xác nhận workload hoặc kênh giao tiếp | Cấp phát/thu hồi chứng thư, bảo vệ private key, ranh giới trust |

**Ưu tiên identity do nền tảng quản lý và credential có hạn ngắn** khi hệ thống hỗ trợ. Điều này giảm nhu cầu nhúng bí mật tĩnh vào repository, container image hoặc cấu hình CI/CD. Tuy nhiên, token ngắn hạn vẫn là credential nhạy cảm: bị đánh cắp trong thời gian hiệu lực vẫn có thể bị dùng nếu cơ chế bảo vệ không đủ.

### 5.1. Các trường bắt buộc trong trust

Với liên kết OIDC/JWT, cần thiết kế kiểm tra:

- **Issuer (iss):** Nguồn được tin cậy, thường gắn với khóa ký và metadata đã cấu hình.
- **Audience (aud):** Token được phát cho đúng bên tiêu thụ/token exchange.
- **Subject (sub):** Workload, repository, environment hoặc runtime identity cụ thể.
- **Expiration (exp) và thời gian liên quan:** Không chấp nhận token hết hạn hoặc ngoài khoảng hiệu lực.
- **Signature:** Chỉ tin token ký đúng với issuer và thuật toán được chấp nhận.
- **Claims bổ sung:** Chỉ dùng claim được issuer bảo đảm và cloud provider hỗ trợ kiểm tra.

**Không xác thực JWT bằng cách chỉ giải mã payload.** Payload có thể được tự tạo, trong khi tính xác thực phụ thuộc chữ ký và quan hệ tin cậy. Đừng mặc định mọi CI issuer đều bảo đảm cùng ngữ nghĩa của claim repository, ref hoặc environment.

### 5.2. Credential ngắn hạn không giải quyết trust quá rộng

Nếu role cho phép mọi pipeline trong tổ chức nhận credential, pipeline không được duyệt vẫn có thể liên tục đổi token lấy session mới. Phải vừa **giảm thời gian sống credential**, vừa **giới hạn điều kiện để được nhận credential** và **thu hẹp quyền của credential**.

## 6. AWS: IAM role cho workload

**AWS IAM role** có hai phần cốt lõi:

1. **Trust policy:** Xác định principal/dịch vụ/issuer nào được phép assume role và điều kiện liên quan.
2. **Permissions policy:** Quy định session của role có thể thực hiện API action nào trên tài nguyên nào.

Workload thường sử dụng **temporary credentials** do cơ chế runtime hoặc **AWS STS** cung cấp. Các cơ chế hạn chế bổ sung như permissions boundary, Service Control Policy (SCP), session policy hoặc resource policy có thể ảnh hưởng quyền hiệu lực theo ngữ nghĩa AWS.

### 6.1. Workload ở AWS EC2, Lambda và các dịch vụ quản lý

- **EC2 instance profile:** Gắn role vào EC2 instance; phần mềm trên instance có thể nhận temporary credentials qua metadata service theo cơ chế bảo vệ được cấu hình.
- **Lambda execution role:** Function chạy với quyền thực thi được role cấp. Nên tách role cho function có nhu cầu khác nhau.
- **Các dịch vụ tính toán khác:** Có cơ chế task role, service role hoặc execution role riêng tùy dịch vụ; cần phân biệt quyền **điều khiển dịch vụ** với quyền **mã ứng dụng khi chạy**.

Không nhúng IAM user access key vào image hoặc mã nguồn để thay thế instance/task/execution role nếu nền tảng đã có cơ chế role phù hợp.

### 6.2. EKS và quyền của Pod

Trên Amazon EKS, các mô hình như **IAM Roles for Service Accounts (IRSA)** hoặc **EKS Pod Identity** cho phép liên kết workload ở Kubernetes với IAM role theo cơ chế được hỗ trợ. Mục đích là tránh mọi Pod phải sử dụng chung quyền của node instance role.

Khi cấu hình:

1. Chọn Kubernetes namespace và ServiceAccount riêng cho workload cần quyền.
2. Cấu hình trust để chỉ runtime identity được duyệt nhận role.
3. Gắn permissions policy đủ hẹp cho API và tài nguyên cần dùng.
4. Giới hạn quyền sửa Pod, ServiceAccount và các cấu hình có thể đổi principal.
5. Kiểm tra không có đường truy cập ngoài dự kiến qua node role, metadata endpoint hoặc một identity khác.

**Rủi ro:** Nếu Pod có thể đọc credential của node hoặc mạo nhận ServiceAccount mạnh hơn, ranh giới role theo service có thể bị phá vỡ. Kubernetes RBAC, admission policy và cấu hình runtime cần phối hợp với IAM.

### 6.3. Workload ngoài AWS qua OIDC

CI/CD hoặc hệ thống bên ngoài có thể sử dụng OIDC token để assume IAM role qua **AssumeRoleWithWebIdentity**, nếu đã cấu hình issuer và trust phù hợp.

~~~yaml
# GIẢ MÃ yêu cầu nghiệp vụ, KHÔNG phải AWS IAM trust policy JSON
role: reporting-staging-deployer
source:
  issuer: ci-issuer-approved
  audience: cloud-token-exchange
  subject:
    repository: org/reporting-api
    environment: staging
destination:
  account: reporting-staging
permissions:
  - deploy: reporting-staging
  - read-artifact: reporting-release-artifacts
constraints:
  productionAccess: forbidden
  credentialDuration: short
owner: platform-reporting
~~~

Trong AWS thật, trust phải sử dụng **condition keys, ARN và claim mapping được hỗ trợ** theo issuer, còn permissions phải sử dụng tên action và resource hợp lệ. Đây chỉ là cấu trúc để thảo luận và review thiết kế.

### 6.4. Cross-account role

Workload tại account A có thể phải truy cập tài nguyên ở account B. Hãy xác minh:

- Principal nguồn và người sở hữu ở A có hợp lệ không?
- Trust của role đích ở B chỉ chấp nhận principal được duyệt không?
- Phía nguồn có quyền assume role trong trường hợp cần thiết không?
- Permissions role tại B chỉ cho phép resource cụ thể không?
- Có vấn đề **confused deputy** khi bên thứ ba được phép thực hiện hành động thay mặt nhiều khách hàng không? Trong tình huống phù hợp cần dùng điều kiện phân biệt ngữ cảnh, ví dụ external ID theo mô hình AWS hỗ trợ.
- Khi quan hệ hợp tác kết thúc, trust, assignment và phiên đã phát hành được xử lý ra sao?

Một role có trust chính xác nhưng permission quá rộng vẫn nguy hiểm. Ngược lại, permission chỉ đọc nhưng trust cho mọi principal bên ngoài vẫn không đáp ứng yêu cầu kiểm soát danh tính.

## 7. Azure: Managed identity, service principal và RBAC

Azure cấp quyền tài nguyên qua **Azure RBAC role assignment** với ba thành phần:

~~~text
roleAssignment = (securityPrincipal, roleDefinition, scope)
~~~

Principal của workload có thể là **managed identity** hoặc một service principal/ứng dụng được cấu hình phù hợp. **Role definition** quy định actions/data actions; **scope** có thể là management group, subscription, resource group hoặc resource.

### 7.1. System-assigned và user-assigned managed identity

| Loại | Đặc điểm | Khi phù hợp |
| --- | --- | --- |
| **System-assigned managed identity** | Danh tính gắn với vòng đời một tài nguyên Azure hỗ trợ; khi tài nguyên đó bị xóa, danh tính gắn riêng thường bị xóa theo cơ chế dịch vụ | Một ứng dụng/tài nguyên cần identity riêng, đơn giản về ownership |
| **User-assigned managed identity** | Danh tính là một tài nguyên Azure riêng, có thể gán cho nhiều resource được hỗ trợ | Các workload có nhu cầu chia sẻ identity hợp lệ hoặc cần quản lý vòng đời riêng |

**Cảnh báo:** User-assigned identity được chia sẻ cũng đồng nghĩa các workload sử dụng identity đó có thể nhận những quyền giống nhau. Không dùng một managed identity quyền cao cho tất cả ứng dụng chỉ vì dễ triển khai.

### 7.2. Ví dụ cấp quyền tối thiểu

Một API cần đọc object từ một storage account. Kiến trúc có thể:

1. Gắn một managed identity riêng với API.
2. Gán một **Azure RBAC data role** phù hợp ở scope storage/blob cần truy cập.
3. Không cấp Owner hoặc Contributor ở toàn subscription nếu API chỉ đọc dữ liệu.
4. Kiểm tra những thao tác đọc cần thiết thành công và thao tác ghi/xóa ngoài mục đích bị từ chối.
5. Ghi owner của identity, mã thay đổi và kỳ review.

**Phân biệt management plane và data plane:** Có quyền quản trị resource không đồng nghĩa có đúng quyền truy cập dữ liệu, và quyền đọc dữ liệu không đồng nghĩa được sửa IAM.

### 7.3. AKS Workload Identity và federation

Trong những kịch bản được hỗ trợ, **Microsoft Entra Workload ID trên AKS** sử dụng Kubernetes ServiceAccount và token OIDC được projected để liên kết tới một identity/ứng dụng đã cấu hình. **Federated identity credential** giới hạn quan hệ tin cậy bằng issuer, subject và audience phù hợp.

Luồng:

~~~mermaid
sequenceDiagram
    participant P as Pod / Kubernetes ServiceAccount
    participant K as AKS OIDC Issuer
    participant E as Microsoft Entra ID
    participant M as Azure Managed Identity / App
    participant R as Azure Resource API
    P->>K: Nhận projected service account token
    K-->>P: OIDC token đã ký
    P->>E: Đổi token theo federated credential
    E->>E: Kiểm tra issuer + subject + audience
    E-->>P: Token cho identity đích
    P->>R: Gọi API với token phù hợp
    R->>R: Đánh giá RBAC / data-plane permission
    R-->>P: Allow hoặc Deny
~~~

Sơ đồ là mức khái niệm; thư viện SDK, loại identity và cơ chế token exchange cụ thể phụ thuộc cấu hình dịch vụ. Đừng coi việc có một federated credential là tự động có RBAC role ở mọi resource.

### 7.4. Mover/Leaver trên Azure

Khi workload đổi namespace, repository, tenant hoặc môi trường, **subject/issuer mapping cũ** phải được xét thu hồi. Khi workload dừng, rà soát cả:

- Managed identity hoặc service principal còn hợp lệ không?
- RBAC assignments trực tiếp và kế thừa có còn cần không?
- Federated identity credentials nào vẫn cho phép nhận token?
- Secret/certificate của application đã tạo trước đó có còn tồn tại?
- Resource có owner mới hoặc dependencies cần bàn giao không?

Việc xóa một Pod không nhất thiết xóa user-assigned managed identity và RBAC assignments, vì chúng là những đối tượng có vòng đời riêng.

## 8. Google Cloud: service account và workload identity

Google Cloud IAM gán **roles** cho **principals** qua allow policy bindings trên tài nguyên. Workload thường sử dụng **service account** hoặc **federated principal**, với nhiều cách nhận credential tùy nơi thực thi.

### 8.1. Service account và role bindings

Service account đại diện cho ứng dụng hoặc workload. Nó có thể được gán role đọc bucket, ghi Pub/Sub topic hoặc truy cập dịch vụ khác tại scope phù hợp.

~~~yaml
# Mô hình minh họa binding, không thay cho lệnh triển khai thật
resource: projects/reporting-dev
bindings:
  - role: roles/storage.objectViewer
    members:
      - serviceAccount:reporting-runtime@example-project.iam.gserviceaccount.com
~~~

Ví dụ chỉ nêu cấu trúc để giải thích. Role chính xác, resource được phép và phạm vi binding phải được kiểm tra theo dịch vụ; không được hiểu rằng gán Object Viewer tại project luôn là phạm vi nhỏ nhất nếu chỉ cần một bucket.

### 8.2. Workload Identity Federation bên ngoài Google Cloud

**Workload Identity Federation** có thể tin cậy token từ nguồn bên ngoài qua **workload identity pool/provider**, attribute mapping và condition. Tùy mô hình, workload có thể:

- Được cấp IAM access trực tiếp dưới dạng federated principal ở tài nguyên hỗ trợ; hoặc
- Được phép **impersonate một service account**, sau đó sử dụng quyền của service account đó.

**Giới hạn principal nguồn và quyền service account đích** đều quan trọng. Nếu federated workload được impersonate một service account sở hữu nhiều role rộng, việc chỉ gán một binding trực tiếp rất hẹp cho workload nguồn chưa đủ.

### 8.3. Workload Identity Federation for GKE

GKE có mô hình **Workload Identity Federation for GKE** cho phép workload Kubernetes sử dụng principal được liên kết với Google Cloud IAM, giảm nhu cầu đặt service account key vào Pod. Cấu hình có thể dùng quyền trực tiếp với principal Kubernetes hoặc liên kết tới một IAM service account theo cơ chế được hỗ trợ.

Khi thiết kế cần xác định:

1. Cluster, namespace và Kubernetes ServiceAccount được phép.
2. Principal hoặc service account Google Cloud đích.
3. Role/binding đúng project hoặc tài nguyên.
4. Quyền thay đổi Kubernetes ServiceAccount/Pod ở cluster.
5. Khả năng các workload khác mạo nhận hoặc dùng chung identity không mong muốn.

**Kubernetes ServiceAccount** và **Google Cloud IAM service account** là hai đối tượng khác nhau, dù đều mang tên “service account”. Liên kết giữa chúng là một quan hệ quản trị cần được kiểm tra và thu hồi khi thay đổi.

### 8.4. Tránh tạo service account key khi không cần

Service account key dạng file là một credential dài hạn dễ bị sao chép vào máy tính, image hoặc repository. Ưu tiên credential do runtime/federation cấp. Nếu dịch vụ cũ bắt buộc dùng key:

- Lưu trong secret manager thay vì commit vào Git.
- Hạn chế thời gian sử dụng, có owner, rotation và ngày hết hạn theo chính sách.
- Theo dõi lần sử dụng và phát hiện key mồ côi.
- Có kế hoạch chuyển khỏi key tĩnh khi nền tảng hỗ trợ.

## 9. Kubernetes: ServiceAccount, RBAC và cloud role

Kubernetes có cơ chế IAM riêng. **ServiceAccount** là danh tính cho các tiến trình chạy trong Pod; **Role/ClusterRole** và **RoleBinding/ClusterRoleBinding** của Kubernetes RBAC kiểm soát việc gọi **Kubernetes API**, không tự cấp quyền truy cập AWS S3, Azure Storage hoặc Google Cloud Storage.

### 9.1. Hai mặt phân quyền độc lập

| Câu hỏi | Kubernetes RBAC | Cloud IAM |
| --- | --- | --- |
| Pod có được đọc ConfigMap trong namespace không? | Có liên quan | Không trực tiếp |
| Pod có được tạo Deployment trong cluster không? | Có liên quan | Không trực tiếp |
| Pod có được đọc một AWS S3 bucket không? | Không trực tiếp | Có liên quan |
| Pod có được đọc một Azure Key Vault secret không? | Không trực tiếp | Có liên quan |
| Pod có được ghi một Google Cloud Storage bucket không? | Không trực tiếp | Có liên quan |

Một ServiceAccount có quyền Kubernetes API rất hẹp vẫn có thể có cloud IAM role rộng nếu federation cấu hình sai. Ngược lại, cloud role nhỏ nhất không ngăn Pod truy cập Kubernetes API nếu RBAC của cluster đang quá rộng.

### 9.2. Ví dụ ServiceAccount tối thiểu

~~~yaml
# Minh họa Kubernetes resource; cloud role federation cần cấu hình riêng
apiVersion: v1
kind: ServiceAccount
metadata:
  name: reporting-api
  namespace: reporting-dev
automountServiceAccountToken: false
~~~

Ở ví dụ này, tự động mount token của ServiceAccount bị tắt. Nếu workload cần token để thực hiện workload federation, phải **cấu hình projected token với audience và hạn dùng phù hợp** hoặc cơ chế cụ thể của nền tảng/SDK. Không sao chép cấu hình này nguyên trạng rồi kỳ vọng mọi luồng federation tự hoạt động.

Các kiểm soát Kubernetes thường cần:

- Dùng ServiceAccount riêng cho workload có mục đích khác nhau.
- Giới hạn quyền ai được sửa ServiceAccount, Pod, admission webhook và deployment.
- Không gắn cloud role nhạy cảm cho ServiceAccount mặc định của namespace.
- Giảm khả năng đọc credential của Pod khác hoặc metadata node.
- Hạn chế service account token không cần thiết và không lưu token trong log/image.
- Rà soát binding khi namespace, cluster hoặc workload đổi owner.

### 9.3. Không nhầm Pod identity với isolation

Việc gán role riêng cho Pod là một lớp kiểm soát IAM, **không tự đảm bảo cô lập hoàn toàn** khi node, container, network hoặc CI control plane bị xâm nhập. Ngăn privilege escalation còn cần cấu hình bảo mật container, quyền trên cluster, network policy, runtime và hệ thống quản trị secret phù hợp.

## 10. CI/CD workload role và OIDC federation

Pipeline CI/CD là workload có rủi ro cao: nó có thể triển khai ứng dụng, đọc artifact, sửa cấu hình và đôi khi sử dụng role production. Dùng **OIDC federation** có thể thay access key dài hạn bằng credential ngắn hạn, nhưng trust cần ràng buộc đúng job.

### 10.1. Hai lớp phải cùng an toàn

**Lớp identity/trust:** Issuer, audience, repository, branch/tag, workflow/environment hoặc thuộc tính khác được issuer bảo đảm phải phù hợp.

**Lớp authorization:** Role chỉ được triển khai đúng service, môi trường, tài nguyên và action; không tự nhận quyền quản lý IAM hay mọi account.

Ví dụ ma trận quyền:

| Workload | Nguồn tin cậy | Role | Scope | Quyền không được cấp |
| --- | --- | --- | --- | --- |
| Build job | CI của repo đã duyệt | ArtifactPublisher | Registry dev | Quản trị production |
| Staging deploy | Workflow staging đã duyệt | StagingDeployer | Staging account | Đọc production secret |
| Production deploy | Environment có approval | ProdServiceDeployer | Một dịch vụ production | Gán IAM Administrator |
| Security scan | Scanner có owner | ReadOnlyScanner | Repo/artifact được duyệt | Xóa hoặc sửa tài nguyên |

### 10.2. Trust ví dụ và các điều kiện cần kiểm thử

~~~yaml
# Giả mã ràng buộc OIDC; không phải chính sách của provider cụ thể
trust:
  issuer: https://ci.example.org
  audience: cloud-sts
  subject:
    repository: org/learning-api
    environment: staging
role:
  name: learning-staging-deployer
  scope: staging-service
  allowedActions:
    - deploy-approved-release
    - read-artifact
session:
  shortLived: true
owner: learning-platform
~~~

Các trường hợp kiểm thử cần có:

1. Token từ đúng repo, đúng environment và còn hạn → được phép nhận role.
2. Token từ repo khác, dù cùng organization → phải bị từ chối.
3. Token dành cho audience khác → phải bị từ chối.
4. Token hết hạn, chữ ký không hợp lệ hoặc issuer lạ → phải bị từ chối.
5. Workload hợp lệ dùng role để đọc production secret ngoài scope → phải bị từ chối.
6. Sau khi xóa trust, token mới từ job cũ không được đổi thành phiên mới.
7. Các session đã cấp trước khi thu hồi được xử lý theo thời hạn/cơ chế revoke thực tế.

Không cần dùng token giả mạo trên production để kiểm thử; có thể dùng môi trường kiểm soát, công cụ mô phỏng và kịch bản được duyệt.

### 10.3. Tránh quyền nâng đặc quyền qua pipeline

Nếu người dùng có thể sửa workflow production, họ có thể thực thi mã trong môi trường sở hữu deployment role. Vì thế cần **branch protection, review, approval môi trường, phân tách người duyệt và người triển khai** theo mức rủi ro.

Quyền trên Git repository và CI configuration là một phần của **đường sử dụng workload role**, dù cloud IAM không trực tiếp quản trị quyền sửa repository.

## 11. Thiết kế role theo least privilege và RBAC/ABAC

Một role tốt bắt đầu từ **tác vụ**, sau đó xác định action/resource/condition. Không nên sao chép role Administrator làm mẫu cố định cho mọi workload.

### 11.1. Ma trận công việc và quyền

| Workload | Cần làm | Role nên hướng tới | Tránh cấp |
| --- | --- | --- | --- |
| Reporting API | Đọc một bucket báo cáo | Object reader ở bucket/scope cụ thể | Storage Admin toàn project |
| Payment worker | Gửi message tới một queue | Queue producer cho queue đích | Queue admin toàn account |
| Notification service | Đọc một secret và gửi email qua API | Secret reader + API action đúng dịch vụ | Quyền đọc mọi secret |
| Backup job | Ghi bản sao lưu tại đích quy định | Backup writer có chính sách bảo vệ dữ liệu | Quyền tắt logging hoặc sửa IAM |
| CI staging deployer | Triển khai bản build đã duyệt | Service deployer scope staging | Owner/Admin production |
| Security inventory job | Đọc metadata IAM | Role chỉ đọc phục vụ inventory | Quyền gán/sửa role |

Ngoài permissions, phải xét **scope và thời gian**. Một role đọc dữ liệu ở toàn organization có thể rủi ro hơn role ghi giới hạn trên một tài nguyên thử nghiệm.

### 11.2. RBAC và ABAC

**RBAC** cấp quyền qua role: ví dụ role QueueProducer cho một worker. **ABAC** sử dụng thuộc tính principal, tài nguyên và ngữ cảnh khi nền tảng hỗ trợ: ví dụ tài nguyên có nhãn team=analytics và workload cũng thuộc team=analytics.

~~~yaml
# Giả mã ABAC, không sử dụng trực tiếp với một cloud provider
principal:
  workloadId: reporting-api
  team: analytics
  environment: dev
resource:
  team: analytics
  environment: dev
request:
  action: reports.read
decision:
  allowWhen:
    - principal.team == resource.team
    - principal.environment == resource.environment
    - request.action == reports.read
~~~

ABAC phụ thuộc **nguồn thuộc tính tin cậy**. Nếu workload có thể tự sửa nhãn resource hoặc claim mà cloud tin cậy để tăng quyền, điều kiện ABAC có thể bị vượt qua. Các thuộc tính ảnh hưởng quyết định bảo mật cần được quản lý bởi chủ thể có thẩm quyền.

### 11.3. Những quyền đặc biệt nguy hiểm

Khi review workload role, đừng chỉ nhìn số lượng permissions. Những action sau có thể dẫn đến nâng đặc quyền:

- Tạo/sửa role hoặc policy, tự gán role cao hơn.
- Sửa trust cho phép principal khác assume role.
- Được impersonate service account có quyền quản trị.
- Đọc hoặc xuất secret chứa credential của principal mạnh.
- Sửa pipeline/IaC mà một principal production sẽ thực thi.
- Tắt log/giám sát hoặc thay cấu hình bảo mật.
- Tạo key dài hạn cho service account hoặc user khác.

Một workload role “chỉ có 5 permissions” vẫn có thể quá nguy hiểm nếu 1 permission trong số đó cho phép tạo credential của một account đặc quyền.

## 12. Joiner–Mover–Leaver cho workload role

Vòng đời danh tính không chỉ áp cho nhân viên. Với workload, **nguồn chuẩn** có thể là service catalog hoặc registry được đồng bộ từ hạ tầng/CI/CD. Quyền phải phản ánh trạng thái workload thực tế.

| Giai đoạn | Đầu vào | Hành động IAM | Bằng chứng hoàn tất |
| --- | --- | --- | --- |
| **Joiner** | Workload ID, owner, mục đích, runtime, môi trường, yêu cầu đã duyệt | Tạo identity, trust, role/binding tối thiểu, chọn credential | Workload thực hiện tác vụ đúng; thử quyền ngoài scope bị từ chối |
| **Mover** | Đổi owner, runtime, repository, namespace, môi trường, tài nguyên | Tính lại desired access, cập nhật trust và bindings, thu hồi quyền cũ | Không còn đường truy cập vai trò/môi trường cũ không được duyệt |
| **Leaver** | Retire service, xóa pipeline, hết hợp đồng tích hợp | Thu hồi trust/role bindings, disable identity/key, xử lý session và owner dependencies | Đích không còn chấp nhận truy cập ngoài dự kiến; có audit |

### 12.1. Joiner: onboarding workload

Một service mới nên có hồ sơ trước khi nhận quyền:

1. **Workload ID ổn định** và tên sản phẩm/dịch vụ.
2. **Owner chính và dự phòng**, đơn vị chịu trách nhiệm bảo mật và vận hành.
3. **Runtime** (EC2, Lambda, AKS/GKE/EKS, Azure Function, CI pipeline, external service).
4. **Issuer/identity source** và cách chứng minh đúng workload.
5. **Danh sách action/resource** có căn cứ; môi trường dev/staging/prod.
6. **Trust/role mapping**, phạm vi, ngày bắt đầu và ngày review/hết hạn.
7. **Log và kiểm chứng** quyền tối thiểu.

Ví dụ service catalog:

~~~yaml
# Ví dụ metadata cho quản trị vòng đời, không phải API cloud
workloadId: learning-api-staging
application: learning-platform
ownerTeam: platform
backupOwnerTeam: sre
runtime: kubernetes
environment: staging
sourceRepository: org/learning-api
identity:
  provider: workload-federation
  subject: namespace:learning-staging/serviceaccount:learning-api
access:
  - action: secrets.read
    resource: learning-staging/database-password
  - action: queue.send
    resource: learning-staging/events
reviewCadence: quarterly
state: active
~~~

Mỗi thông tin quyết định quyền cần được kiểm tra với hệ thống thực tế. Metadata không tự có hiệu lực: quy trình provisioning phải biến nó thành cấu hình cloud IAM và xác minh được cấu hình đó.

### 12.2. Mover: thay đổi workload

Những thay đổi có thể kích hoạt Mover: chuyển nhóm quản lý, đổi cluster, namespace, repository, môi trường, account hoặc phương thức xác thực.

Ví dụ chuyển service từ staging sang production:

- Quyền staging hiện tại chỉ áp dụng cho staging.
- Role production phải được phê duyệt theo mức rủi ro riêng.
- Trust phải ràng buộc identity của runtime production, không dùng chung issuer/subject quá rộng với staging.
- Sau migration, thu hồi quyền staging không còn cần, kiểm tra khóa cũ và phiên đã cấp.
- Nếu service vẫn chạy song song ở hai môi trường trong thời gian chuyển, ngoại lệ phải có owner, hạn dùng và kế hoạch thu hồi.

**Sai lầm thường gặp:** Thêm grant ở account mới mà không xóa grant ở account cũ. Điều đó làm tăng số điểm có thể bị lợi dụng sau một lần workload bị xâm nhập.

### 12.3. Leaver: retire workload

Quy trình retire nên:

1. Xác nhận service/pipeline đã ngừng, không còn dependency hoặc dữ liệu cần chuyển giao.
2. Đóng đường cấp token mới: xóa trust hoặc federated credential không còn hợp lệ.
3. Gỡ role assignment/IAM binding, quyền impersonation và resource policy liên quan.
4. Disable/delete identity của workload khi thích hợp; thu hồi và xoay static secrets/keys có liên quan.
5. Kiểm tra session và temporary credentials đã phát hành theo cơ chế của provider.
6. Đọc lại trạng thái cloud target; ghi mọi exception nếu còn phiên chưa hết hạn.
7. Lưu log và bằng chứng theo chính sách trước khi xóa môi trường chứa log.

Khi retire một workload, **không xóa role definition dùng chung** nếu những service khác vẫn dùng đúng quyền. Cần thu hồi **assignment/trust/credential cụ thể** của workload hết vòng đời.

### 12.4. Leaver của con người có ảnh hưởng workload thế nào?

Nếu engineer là owner khai báo của một pipeline nhưng nghỉ việc, JML nhân sự phải kích hoạt **owner transfer** và review những tài sản liên quan. Một pipeline hợp lệ có thể tiếp tục hoạt động với owner mới; những API key hoặc token do người đó lưu giữ phải được xem xét rotation/revocation. Tránh để workload mất kiểm soát hoặc phụ thuộc vào tài khoản cá nhân của người đã rời tổ chức.

## 13. Inventory và owner cho danh tính phi con người

Khó khăn lớn nhất của workload IAM thường là **không biết tất cả identity đang tồn tại và ai chịu trách nhiệm**. Những danh tính phi con người được tạo trong console, pipeline, môi trường test hoặc bởi ứng dụng bên thứ ba dễ bị bỏ quên.

### 13.1. Trường inventory nên có

| Trường | Ý nghĩa |
| --- | --- |
| Workload ID và identity/principal ID | Khóa liên kết ổn định giữa registry và cloud target |
| Loại runtime | EC2, Pod, function, CI job, external workload |
| Owner và backup owner | Người/nhóm chịu trách nhiệm JML và review |
| Repository, artifact, deployment | Chứng cứ nguồn vận hành |
| Issuer, subject, trust reference | Xác định ai có thể nhận credential |
| Role/binding và scope | Tập quyền thực tế gắn với workload |
| Credential type và expiration | Nhận diện key tĩnh và phiên có hạn |
| Môi trường, dữ liệu nhạy cảm | Đánh giá rủi ro và mức ưu tiên |
| Ngày tạo, lần dùng, lần review | Phát hiện quyền không còn nhu cầu |
| Decommission ticket và trạng thái | Chứng minh đã kết thúc vòng đời |

Không nên dùng email của một cá nhân làm **owner duy nhất**. Dùng nhóm chịu trách nhiệm ổn định, kèm người liên hệ thực tế và quy trình đổi owner.

### 13.2. Phát hiện orphan workload identity

Một identity có quyền IAM nhưng không còn bản ghi registry, repository hoặc service owner là tín hiệu **orphan identity**. Cách xử lý:

1. Thu thập role, trust, key, log sử dụng và tài nguyên phụ thuộc.
2. Xác định nguồn tạo/owner qua lịch sử deployment và thay đổi IAM.
3. Nếu còn workload hợp lệ, đưa vào registry và giảm quyền theo nhu cầu thực tế.
4. Nếu không còn nhu cầu, thực hiện retire có kiểm soát và kiểm chứng.
5. Nếu có nghi ngờ lộ credential, kích hoạt quy trình ứng phó theo mức rủi ro.

Lần sử dụng gần nhất là một tín hiệu, **không phải bằng chứng duy nhất**: cron job có thể chạy theo quý; hệ thống phục hồi thảm họa có thể ít dùng nhưng vẫn phải được quản trị.

## 14. Bảo vệ credential, token và phiên

### 14.1. Các loại thông tin cần quản trị

- **Role session / STS temporary credentials:** Có thời hạn, dùng để gọi API theo role.
- **OIDC token:** Chứng minh nguồn/identity nhằm đăng nhập hoặc token exchange theo mục đích được phép.
- **Service account access token:** Cho phép API đánh giá dưới danh tính service account.
- **Static access key / client secret / certificate private key:** Có thể tồn tại lâu, cần lưu trữ và xoay an toàn.
- **Refresh token (nếu cơ chế có dùng):** Có thể cho phép lấy access token mới; rủi ro khác access token ngắn hạn.

**Không ghi raw bearer token, access key, private key hoặc assertion vào log** chỉ để phục vụ kiểm toán. Nên ghi credential ID, principal/session correlation ID, issuer, thời gian, resource và kết quả.

### 14.2. Thu hồi quyền và xử lý phiên

Khi Leaver xảy ra, xóa role assignment hoặc chặn issuer có thể ngăn **lần cấp quyền mới**. Nhưng **session đã cấp** có thể tiếp tục hoạt động đến khi hết hạn hoặc bị thu hồi theo công cụ được hỗ trợ.

~~~mermaid
sequenceDiagram
    participant J as Workload Lifecycle
    participant I as Issuer / Runtime
    participant C as Cloud IAM / STS
    participant R as Resource API
    J->>I: Retire workload / chặn phát token mới
    J->>C: Gỡ trust, role binding, grant
    C-->>J: Đã áp thay đổi
    J->>C: Kiểm tra session/credential còn hiệu lực
    alt Có thể revoke theo nền tảng
        J->>C: Thu hồi hoặc giới hạn phiên
    else Không thể revoke tức thời
        J->>J: Ghi thời hạn + giảm rủi ro + giám sát
    end
    J->>R: Kiểm chứng quyền còn hiệu lực theo kịch bản được phép
    R-->>J: Kết quả xác minh
    J->>J: VERIFIED hoặc EXCEPTION
~~~

**Request thu hồi thành công chưa đồng nghĩa quyền thực tế đã hết.** Khi không thể hủy ngay session, cần ghi hạn hiệu lực, chủ sở hữu ngoại lệ và hành động giảm thiểu theo mức độ rủi ro.

### 14.3. Credential rotation và thay đổi trust

Rotation cần đảm bảo service vẫn hoạt động nhưng không để key cũ tồn tại vô hạn:

1. Phát hành credential mới theo chính sách.
2. Cập nhật nơi sử dụng một cách kiểm soát.
3. Xác minh service hoạt động bằng credential mới.
4. Vô hiệu hóa credential cũ sau khoảng chuyển đổi đã duyệt.
5. Xác nhận không còn sử dụng key cũ, ghi audit.

Với federation, cần có quy trình **issuer key/certificate rollover** để thay khóa ký đúng cách, tránh gián đoạn dịch vụ hoặc vô tình tin nguồn không hợp lệ.

## 15. Những tấn công và lỗi cấu hình thường gặp

| Rủi ro | Biểu hiện | Biện pháp |
| --- | --- | --- |
| **Role quá rộng** | Service đọc mọi secret, sửa IAM hoặc dùng Admin | Action/resource/scope tối thiểu, review role |
| **Trust không hạn chế subject** | Mọi pipeline cùng issuer có thể assume role | Ràng buộc subject, audience, claim và issuer chính xác |
| **Credential trong Git/image** | Access key bị sao chép và tồn tại lâu | Federation/managed identity; secret scanning và rotation |
| **Chia sẻ identity giữa nhiều app** | Khó thu hồi riêng và phân biệt audit | Identity/role theo workload, giảm sharing |
| **ServiceAccount mặc định quyền cao** | Pod bất kỳ có thể dùng quyền ngoài dự kiến | KSA riêng, hạn chế RBAC và IAM binding |
| **Quyền impersonate service account rộng** | Workload nhận quyền của principal mạnh hơn | Hạn chế impersonation và review quyền đích |
| **Metadata endpoint bị lạm dụng** | Workload nhận credential của node/instance ngoài dự kiến | Cấu hình runtime/network/IMDS và isolation |
| **CI workflow bị sửa trái phép** | Người sửa pipeline dùng deployment role | Branch protection, approval và review |
| **Cross-account trust mơ hồ** | Bên thứ ba truy cập qua đường không phù hợp | Principal cụ thể, điều kiện chống confused deputy nếu cần |
| **Không giới hạn token audience** | Token dành cho hệ thống khác bị chấp nhận | Validate aud và claim đúng mục đích |
| **Workload mồ côi** | Role/key tồn tại sau khi service ngừng | Inventory, owner, deprovision và readback |
| **Không đọc lại IAM sau Mover** | Quyền ở môi trường cũ vẫn còn | Reconciliation desired/actual/effective |
| **Không phân biệt quyền Kubernetes và cloud** | Cluster RBAC bị coi là đủ bảo vệ bucket/secret | Kiểm tra cả hai lớp IAM |
| **Tin rằng keyless đồng nghĩa an toàn tuyệt đối** | Token tạm bị lộ vẫn dùng được trong TTL | Cấu hình trust hẹp, TTL ngắn, runtime bảo mật |

### 15.1. Chống confused deputy

Một hệ thống bên thứ ba có quyền assume role thay nhiều khách hàng có thể bị lợi dụng để truy cập nhầm tài nguyên của khách hàng khác nếu trust không phân biệt ngữ cảnh yêu cầu.

Trong tình huống hỗ trợ, hãy dùng cơ chế ràng buộc **principal và customer/request context**, ví dụ **external ID** trong các quan hệ AWS cross-account với bên thứ ba. Đây là một lớp kiểm soát bổ sung cho loại trust tương ứng, không thay thế việc giới hạn permissions của role.

## 16. Đối soát desired access và effective access

Một hệ thống JML hoàn chỉnh phải biết:

- **Desired access:** Quyền được phê duyệt cho workload theo nhiệm vụ và trạng thái hiện tại.
- **Assigned access:** Role, policy, trust, binding, impersonation và credential đang tồn tại.
- **Effective access:** Những action thực sự có thể thực hiện sau khi cloud IAM xét các chính sách, điều kiện và giới hạn liên quan.

Ví dụ giả mã:

~~~text
event = getAuthorizedWorkloadLifecycleEvent(workloadId)
targets = discoverCloudAccountsProjectsAndTrust(workloadId)

for target in targets:
    desired = calculateApprovedEntitlements(workloadId, target)
    actual = enumerateRoleTrustBindingsKeysAndSessions(workloadId, target)
    stale = compareNormalizedAccess(actual, desired)

    for grant in stale:
        revokeWithAudit(grant)

    verification = evaluateEffectiveAccessWithSupportedMethods(workloadId, target)
    if verification.matchesApprovedState:
        markVerified(workloadId, target, event)
    else:
        raiseExceptionWithOwner(workloadId, target, verification)
~~~

Giả mã minh họa luồng nghiệp vụ. Phải chuẩn hóa theo **principal, issuer, subject, role, resource scope, conditions, thời hạn và quyền kế thừa**. Một IAM role trên account khác có thể mang tên giống nhưng quyền thực tế khác. Thử quyền hiệu lực cần công cụ mô phỏng và/hoặc bài kiểm tra được phép theo provider.

### 16.1. Những đường cấp quyền dễ bỏ sót

1. Role được gán trực tiếp với workload principal.
2. Quyền có được qua service account impersonation.
3. Cross-account role trust hoặc resource-based policy.
4. Kubernetes ServiceAccount liên kết sai với cloud role.
5. Credential/key cũ không còn dùng trong source mới nhưng vẫn hoạt động.
6. Azure user-assigned managed identity tiếp tục tồn tại sau khi tài nguyên gốc bị xóa.
7. CI provider trust cho cả organization thay vì workflow cụ thể.
8. Phiên cloud đã phát hành trước khi xóa trust.
9. Quyền kế thừa từ project, folder, management group hoặc account cấp trên.
10. Workload có tài khoản fallback local hoặc secret trong hệ thống bên thứ ba.

### 16.2. Trạng thái yêu cầu và kết quả

~~~text
REQUESTED   Có yêu cầu cấp/sửa/thu hồi quyền
APPROVED    Có phê duyệt theo chính sách
APPLIED     API/config change báo thành công
VERIFIED    Quyền thực tế tại target đạt trạng thái mong muốn
FAILED      Thao tác hoặc xác minh bị lỗi
EXCEPTION   Có ngoại lệ được owner nhận và có hạn xử lý
~~~

Một event ở trạng thái **APPLIED** chưa đủ để kết luận giảm quyền tồn dư. Có thể vẫn còn một binding ở nơi khác hoặc session cũ. Cần lưu bằng chứng **VERIFIED**, hoặc một **EXCEPTION** với trách nhiệm xử lý.

## 17. Policy-as-code, review và thử nghiệm workload role

Định nghĩa role/trust qua **Infrastructure as Code (IaC)** hoặc policy-as-code giúp giảm drift do sửa tay trong console.

### 17.1. Quy trình thay đổi

~~~mermaid
flowchart TD
    A["Workload owner đề xuất quyền"] --> B["Mô tả principal, trust, action, resource"]
    B --> C["Tạo thay đổi IaC / policy-as-code"]
    C --> D["Lint, validate, privilege analysis"]
    D --> E["Kiểm thử allow/deny và tác động"]
    E --> F["Review và phê duyệt"]
    F --> G["Triển khai qua pipeline có kiểm soát"]
    G --> H["Readback target + verify effective access"]
    H --> I["Giám sát log / drift / access review"]
    H -->|Không khớp| X["Ghi lỗi, rollback/khắc phục có kiểm soát"]
    X --> C
~~~

Policy review cần xem **hai nhóm thay đổi**:

- **Trust changes:** Ai sẽ được phép nhận session/credential?
- **Permissions changes:** Khi đã nhận session, principal có thể thực thi thêm hành động gì?

Một thay đổi chỉ thêm một repository vào trust có thể mở rộng nhiều workload đủ điều kiện, dù permissions policy không đổi. Một thay đổi role từ bucket cụ thể sang wildcard có thể mở quyền cho workload hiện tại mà không thay trust.

### 17.2. Bộ kiểm thử có ý nghĩa

| Kịch bản | Kỳ vọng |
| --- | --- |
| Workload đúng issuer/subject/audience nhận role | Được phép nếu còn hiệu lực |
| Workload từ issuer khác | Từ chối |
| Workload có subject sai | Từ chối |
| Workload có token hết hạn hoặc chữ ký không hợp lệ | Từ chối |
| Principal đúng đọc resource được duyệt | Cho phép |
| Principal đúng sửa IAM ngoài phạm vi | Từ chối |
| Principal đúng truy cập production ngoài scope | Từ chối |
| Workload sau Mover dùng trust cũ | Không còn cấp phiên mới |
| Workload đã retire thử đổi token mới | Từ chối |
| Role được thu hồi nhưng session cũ vẫn sống | Được phát hiện, xử lý theo TTL/revoke của provider |

Các bài kiểm thử nên kiểm tra **kết quả quyền**, không chỉ kiểm tra file có một chuỗi Allow hay Deny. Khi không thể kiểm thử production, sử dụng simulation, môi trường staging và kiểm soát thay đổi phù hợp.

## 18. Tình huống thực tế: từ development đến production rồi retire

Doanh nghiệp quản lý dịch vụ **Learning Report API** qua Kubernetes và cloud IAM. Đội Platform quản lý ứng dụng; CI/CD triển khai hai môi trường staging và production. Dịch vụ cần đọc object báo cáo và ghi log.

### 18.1. Joiner

Đội Platform đăng ký workload **learning-report-api** với owner, namespace, repository và môi trường staging. Pipeline triển khai có một role riêng; runtime API có một workload identity khác.

| Principal | Mục đích | Quyền được cấp |
| --- | --- | --- |
| learning-report-api-runtime | Ứng dụng đang chạy | Đọc bucket báo cáo staging, ghi telemetry |
| learning-report-api-deployer | CI/CD | Triển khai service staging, đọc artifact được duyệt |
| platform-engineer | Người vận hành | Xem log theo quyền cá nhân; yêu cầu nâng quyền riêng khi cần |

Tách **deployment identity** khỏi **runtime identity** là quan trọng: API không cần quyền deploy; pipeline không cần đọc dữ liệu người dùng khi chỉ triển khai mã.

### 18.2. Mover

Ứng dụng được nâng lên production. Tổ chức tạo role đích phù hợp, phê duyệt quyền đọc dữ liệu production cần thiết; trust của CI production ràng buộc workflow và environment đã được bảo vệ. Nếu deployment sang production thành công, các grant staging không còn cần được thu hồi theo kế hoạch.

Giả sử một trust cũ vẫn cho repository thử nghiệm assume staging role. Dù role này không có quyền production, trust đó vẫn là quyền tồn dư cần xử lý và kiểm chứng.

### 18.3. Một engineer nghỉ việc

Người viết pipeline nghỉ việc. HRIS phát Leaver cho người đó; IdP disable user, gỡ quyền Git/CI/Cloud cá nhân và rà soát token họ từng quản lý. **Workload vẫn tiếp tục chạy** bằng danh tính của chính nó; owner chuyển sang một nhóm hợp lệ. Nếu từng có access key cá nhân được dùng trong pipeline, cần xoay hoặc loại bỏ ngay theo mức rủi ro.

### 18.4. Leaver của workload

Sản phẩm thay thế Learning Report API. Decommission workflow thu hồi role/binding/trust của runtime và pipeline, vô hiệu hóa secret cũ, kiểm tra các account/project có liên quan và lưu bằng chứng. Không được đánh dấu hoàn tất chỉ vì Deployment và Pod đã bị xóa.

Ví dụ bản ghi audit giả định:

~~~json
{
  "eventId": "WORKLOAD-JML-2026-0042",
  "workloadId": "learning-report-api",
  "eventType": "leaver",
  "source": "service-catalog",
  "target": "learning-production",
  "principal": "learning-report-api-runtime",
  "operation": "revoke-role-and-trust",
  "status": "verification_pending",
  "owner": "platform-team",
  "occurredAt": "2026-11-23T07:00:00Z"
}
~~~

**verification_pending** nghĩa là đã ghi nhận yêu cầu nhưng chưa có bằng chứng quyền thực tế bị thu hồi. Khi readback tại target cho kết quả đúng, sự kiện mới chuyển VERIFIED, hoặc ghi EXCEPTION nếu còn session/credential cần theo dõi.

### 18.5. Minh họa quyền còn sót

~~~mermaid
flowchart TD
    A["Service catalog: Workload retired"] --> B["Desired access = none"]
    B --> C["Thu hồi trust và role bindings"]
    C --> D["Đọc lại AWS/Azure/GCP targets"]
    D --> E{"Còn grant hoặc credential?"}
    E -->|Không| F["Kiểm tra effective access / session"]
    E -->|Có| G["Thu hồi bổ sung, xoay key"]
    G --> D
    F --> H{"Đã đạt trạng thái mong muốn?"}
    H -->|Có| I["VERIFIED + Audit"]
    H -->|Không| J["EXCEPTION + Owner + Deadline"]
    J --> F
~~~

## 19. Giám sát, kiểm toán và các chỉ số

### 19.1. Log cần thu thập

| Log | Mục đích |
| --- | --- |
| Workload registration/owner changes | Biết nguồn và vòng đời danh tính |
| Role/trust creation and policy diff | Biết ai mở rộng hoặc thu hẹp quyền |
| Federation token exchange | Biết issuer, principal nguồn, role đích và kết quả |
| IAM role assumption / principal access | Phát hiện sử dụng role khác thường |
| Cloud API audit | Xác định action và resource đã được truy cập |
| Credential creation/rotation/revocation | Phát hiện key tồn dư và secret mới |
| JML events và approvals | Gắn thay đổi kỹ thuật với căn cứ nghiệp vụ |
| Reconciliation verification | Chứng minh trạng thái thực tế ở đích |

Nên dùng correlation ID, workload ID, role/session ID và resource ID để liên kết các sự kiện. **Không lưu credential thô** trong log.

### 19.2. Chỉ số theo dõi

| Chỉ số | Ý nghĩa |
| --- | --- |
| **Tỷ lệ workload identities có owner** | Phát hiện danh tính mồ côi |
| **Tỷ lệ role được gán scope tối thiểu** | Đánh giá least privilege |
| **Tỷ lệ workload dùng credential ngắn hạn** | Theo dõi tiến trình loại key tĩnh |
| **Số role/trust quá rộng** | Phát hiện nguồn có thể nhận quyền ngoài dự kiến |
| **P95 thời gian deprovision workload** | Từ lúc retire có hiệu lực đến VERIFIED |
| **Số stale grants sau Mover/Leaver** | Đo quyền tồn dư |
| **Số privileged workload principals** | Ưu tiên review đường nâng quyền |
| **Tỷ lệ JML events VERIFIED** | Tránh nhầm API success với hoàn tất |
| **Số credential chưa rotation hoặc hết owner** | Phát hiện secret/key tồn tại quá lâu |
| **Số thay đổi role/trust ngoài IaC** | Theo dõi policy drift |

Chia chỉ số theo provider, môi trường production/non-production, loại workload, owner và mức đặc quyền. Một role CI có quyền sửa IAM production cần được ưu tiên hơn một role chỉ đọc dữ liệu thử nghiệm.

## 20. Checklist triển khai workload role

1. **Danh tính đúng:** Mỗi workload có ID ổn định, owner và nguồn tạo có thẩm quyền.
2. **Runtime đúng:** Xác định VM, Pod, function, pipeline hoặc external workload và issuer tương ứng.
3. **Trust đúng:** Kiểm tra issuer, audience, subject, chữ ký, hạn token và điều kiện phù hợp.
4. **Quyền đúng:** Role giới hạn action/resource/scope theo nhiệm vụ, tránh quyền sửa IAM không cần thiết.
5. **Tách môi trường:** Staging và production có identity/role/trust phù hợp ranh giới rủi ro.
6. **Tách công việc:** Runtime identity và deployment identity độc lập khi nhu cầu khác nhau.
7. **Credential an toàn:** Ưu tiên federation/managed identity; loại key tĩnh khi khả thi.
8. **Kubernetes an toàn:** ServiceAccount, RBAC, token projection và cloud role mapping được rà soát.
9. **Ngăn nâng quyền:** Xét quyền impersonate, sửa trust, đọc secret và thay pipeline.
10. **JML có nguồn:** Joiner/ Mover/Leaver kích hoạt từ service catalog, CI, CMDB hoặc quy trình đã duyệt.
11. **Owner thay đổi có kiểm soát:** Người nghỉ việc không để lại workflow không chủ hoặc credential cá nhân.
12. **Readback bắt buộc:** So sánh desired/actual/effective access sau mỗi thay đổi và khi retire.
13. **Policy-as-code:** Review trust và permissions, kiểm thử trường hợp allow/deny và theo dõi drift.
14. **Kiểm toán:** Ghi nguồn, owner, approval, role ID, scope, credential metadata và trạng thái VERIFIED.
15. **Ngoại lệ rõ ràng:** Session/credential chưa thể thu hồi có owner, ngày hết hiệu lực và biện pháp giảm rủi ro.

## 21. Bài tập tự kiểm tra

### Bài 1. API đang dùng access key của nhân viên

**Tình huống:** Một API production dùng AWS access key được tạo từ IAM user cá nhân của kỹ sư. Kỹ sư nghỉ việc.

**Phân tích:** Đây là phụ thuộc sai vòng đời. Cần chuyển sang role/credential gắn với workload (ví dụ service execution role hoặc federation phù hợp), giảm permissions, chuyển ownership, thu hồi key cá nhân và xác minh ứng dụng vẫn hoạt động với identity mới.

### Bài 2. Workload identity có token hợp lệ nhưng không được nhận role

**Tình huống:** CI token ký đúng, chưa hết hạn; trust chỉ cho environment staging nhưng job phát token cho environment dev.

**Kết quả mong đợi:** Token bị từ chối theo điều kiện trust. Chữ ký hợp lệ không có nghĩa subject/claims đúng chính sách.

### Bài 3. Service account có quyền impersonation

**Tình huống:** Một federated workload có binding đọc log rất hẹp, nhưng đồng thời được phép impersonate một Google Cloud service account có quyền Editor.

**Phân tích:** Workload có đường quyền gián tiếp rộng hơn binding trực tiếp. Cần rà soát và giới hạn quyền impersonation và các role của service account đích.

### Bài 4. Kubernetes RBAC và cloud IAM

**Tình huống:** Pod có Kubernetes RBAC chỉ đọc ConfigMap, nhưng Pod vẫn có thể xóa object trong cloud storage.

**Giải thích:** Kubernetes RBAC kiểm soát Kubernetes API, còn xóa object ở cloud do cloud IAM quyết định. Cần kiểm tra cloud role/binding, trust và identity mà Pod đang nhận.

### Bài 5. Retire một pipeline

**Tình huống:** Repository đã được archive; role federated trên cloud vẫn có trust cho toàn tổ chức CI/CD và không có owner.

**Hướng xử lý:** Đóng trust và assignment không còn hợp lệ, kiểm tra các job khác phụ thuộc, thu hồi key, xem session còn hiệu lực và lưu kết quả đọc lại ở cloud target.

## 22. Tổng kết

**Workload role** tổ chức quyền cho ứng dụng và automation thay vì con người. Tùy nền tảng, quyền được biểu diễn bằng **AWS IAM role**, **Azure RBAC assignment cho managed identity/service principal**, hoặc **Google Cloud IAM role binding cho service account/federated principal**. Với Kubernetes và CI/CD, cần thêm lớp ràng buộc **runtime identity – issuer – trust – cloud principal**.

Trong quản lý vòng đời danh tính, bảo mật workload là sự kết hợp của **IdP/federation hoặc identity nguồn**, **RBAC/ABAC và least privilege**, **credential ngắn hạn**, **kiểm soát ownership**, **JML cho workload**, và **đối soát quyền thực tế**. Các sự kiện **Joiner–Mover–Leaver** chỉ hoàn tất khi role, trust, binding, key và phiên không còn hợp lệ đã được xử lý tại cloud target, **quyền truy cập tồn dư được xác minh và kết quả có bằng chứng kiểm toán**.
