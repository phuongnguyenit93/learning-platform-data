# Cloud policy

**Chương:** Cloud IAM  
**Bài học:** Cloud policy  
**Phạm vi:** Thiết kế, áp dụng, đánh giá, kiểm toán và duy trì chính sách truy cập tài nguyên đám mây theo vòng đời danh tính **Joiner–Mover–Leaver (JML)**; kết nối IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ và kiểm soát quyền truy cập tồn dư.

## 1. Cloud policy là gì?

**Cloud policy** là tập quy tắc chi phối cách một tổ chức sử dụng, cấu hình hoặc truy cập tài nguyên trên nền tảng đám mây. Trong phạm vi **Identity and Access Management (IAM)**, cloud policy chủ yếu diễn tả **principal nào được phép hoặc bị từ chối thực hiện action nào trên resource nào, trong điều kiện nào**. Các chính sách quản trị tổ chức cũng có thể áp những giới hạn rộng hơn cho cách tài nguyên được tạo và vận hành.

Ví dụ: kỹ sư được đọc log của ứng dụng trong môi trường development nhưng không được xóa log production; pipeline triển khai chỉ được sử dụng vai trò triển khai staging; một tài khoản dịch vụ chỉ được đọc một kho dữ liệu đã xác định. Các quy tắc này cần tồn tại dưới dạng chính sách có thể kiểm tra, truy vết, thay đổi và thu hồi.

Điều quan trọng là **policy khác với identity và role**:

- **Identity / principal:** Ai hoặc workload nào đưa ra yêu cầu?
- **Authentication / SSO:** Chủ thể đã được chứng minh danh tính bằng cách nào?
- **Role / entitlement:** Chủ thể được gán vai trò hoặc quyền nào?
- **Policy:** Các quy tắc nào cho phép, từ chối hoặc giới hạn việc sử dụng quyền?
- **Resource scope:** Quy tắc có hiệu lực tại tổ chức, account, subscription, project hay tài nguyên cụ thể nào?
- **Governance / lifecycle:** Ai phê duyệt, ai sở hữu, khi nào phải rà soát và thu hồi chính sách hoặc quyền gắn với nó?

Một người **đăng nhập SSO thành công** chưa chắc được đọc tài nguyên; IAM vẫn đánh giá policy. Tương tự, khi nhân viên nghỉ việc, **khóa IdP** có thể ngăn đăng nhập mới nhưng không bảo đảm các grant, token, session hoặc đường trust đã được thu hồi ngay.

### 1.1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt chính sách truy cập IAM với chính sách quản trị tài nguyên và chính sách đăng nhập.
2. Đọc và thiết kế điều kiện principal – action – resource – context – effect ở mức khái niệm.
3. Mô tả các lớp policy và giới hạn quyền điển hình trong AWS, Azure và Google Cloud.
4. Kết hợp policy với RBAC/ABAC, IdP, SSO, provisioning/SCIM, service account và workload federation.
5. Đưa các thay đổi policy và quyền vào Joiner–Mover–Leaver, phát hiện **privilege accumulation** và truy cập tồn dư.
6. Thiết lập quy trình **policy-as-code**, review, kiểm tra tác động, triển khai và lưu bằng chứng kiểm toán.

## 2. Phân loại cloud policy để tránh nhầm lẫn

Thuật ngữ “cloud policy” khá rộng. Khi trao đổi hoặc ghi một yêu cầu thay đổi, cần nêu rõ đang nói tới **loại chính sách nào**.

| Loại policy | Câu hỏi được giải quyết | Ví dụ |
| --- | --- | --- |
| **IAM access policy** | Principal được làm hành động nào trên resource? | Chỉ cho phép đọc object trong một bucket |
| **Trust / federation policy** | Danh tính bên ngoài hoặc principal nào được tin cậy để nhận quyền? | Chỉ pipeline từ repository đã duyệt được assume deployment role |
| **Resource-based policy** | Ai được truy cập tài nguyên cụ thể và trong điều kiện nào? | Bucket cho phép một role thuộc account đối tác đọc đối tượng |
| **Role assignment / IAM binding** | Principal được gắn tập quyền nào tại scope nào? | Nhóm vận hành nhận role Reader tại project dev |
| **Organization guardrail / restriction policy** | Những hành động hoặc cấu hình nào bị giới hạn trên phạm vi rộng? | Ngăn tạo tài nguyên ở vùng không được phê duyệt |
| **Conditional access / sign-in policy** | Khi đăng nhập, cần xác thực hoặc đáp ứng ngữ cảnh nào? | Yêu cầu MFA mạnh với quản trị viên |
| **Configuration / compliance policy** | Tài nguyên có đáp ứng tiêu chuẩn cấu hình không? | Bắt buộc logging hoặc mã hóa theo chính sách |
| **Data access / application policy** | Ai được thao tác với dữ liệu hoặc chức năng bên trong ứng dụng? | Chỉ người có vai trò được duyệt mới xem dữ liệu nhạy cảm |

**Một chính sách kiểm tra cấu hình không nhất thiết cấp quyền truy cập.** Ví dụ, Azure Policy dùng để quản trị trạng thái tài nguyên, còn Azure RBAC quản lý quyền thực hiện thao tác trên resource. Tương tự, yêu cầu MFA ở IdP ảnh hưởng đến đăng nhập nhưng không tự tạo IAM binding tại Google Cloud.

### 2.1. Policy, role và entitlement liên kết thế nào?

~~~mermaid
flowchart TD
    HR["HRIS / nguồn danh tính"] --> LC["Identity Lifecycle / IGA<br/>JML + phê duyệt"]
    LC --> IDP["IdP / Directory<br/>User, group, thuộc tính"]
    IDP --> FED["SSO / Federation<br/>SAML, OIDC"]
    FED --> P["Principal / cloud session"]
    LC --> GRANT["Provisioning / quản lý entitlement"]
    GRANT --> IAM["Role, assignment, binding, trust"]
    P --> EVAL["Cloud IAM policy evaluation"]
    IAM --> EVAL
    POL["Access policy + restrictions<br/>action, resource, condition"] --> EVAL
    EVAL --> RES["Tài nguyên cloud / API"]
    EVAL --> LOG["Audit log / theo dõi"]
    LC --> LOG
~~~

Sơ đồ cho thấy các quan hệ logic; từng nhà cung cấp có cách đặt tên, thứ tự đánh giá và loại policy khác nhau. Hệ thống thực tế cũng có thể không dùng SCIM cho cloud IAM mà dùng API hoặc cơ chế liên kết riêng.

## 3. Thành phần của một chính sách truy cập

Một quy tắc IAM có thể được mô tả bằng các thành phần:

| Thành phần | Nội dung | Câu hỏi kiểm tra |
| --- | --- | --- |
| **Principal** | User, group, role, service account hoặc workload principal | Chủ thể nào được áp quy tắc? Có đúng định danh ổn định không? |
| **Effect** | Allow hoặc Deny khi nền tảng hỗ trợ loại quy tắc tương ứng | Quy tắc cấp hay chặn quyền? |
| **Action / Permission** | API operation hoặc hành vi được bảo vệ | Chỉ đọc hay có cả sửa, xóa và quản trị IAM? |
| **Resource** | Tài nguyên được bảo vệ; có thể có wildcard hoặc phạm vi cha | Chính sách tác động đến tài nguyên nào? |
| **Condition** | Ngữ cảnh hoặc thuộc tính cần đúng | Có giới hạn môi trường, thời gian, nhãn, nguồn yêu cầu không? |
| **Scope / Attachment** | Vị trí policy/role/binding được áp dụng | Có kế thừa đến account/project/resource khác không? |
| **Owner / rationale** | Căn cứ nghiệp vụ, người phê duyệt | Ai được quyền giữ hoặc thay đổi chính sách? |

Các thành phần trên là mô hình chung. Không phải mọi nhà cung cấp đều có trường **Principal** hoặc **Deny** trong cùng một tài liệu policy; nhiều nền tảng diễn đạt principal qua assignment/binding tách riêng.

### 3.1. Ví dụ policy ở mức khái niệm

~~~yaml
# Giả mã trung lập với nhà cung cấp: KHÔNG áp trực tiếp lên AWS/Azure/GCP
policyId: learning-dev-log-read
description: Cho phép đội Learning đọc log ở môi trường development
principal:
  type: group
  id: learning-developers
effect: allow
actions:
  - logs.list
  - logs.read
resources:
  - project: learning-dev
    service: learning-api
conditions:
  identityStatus: active
  environment: dev
owner: learning-platform
reviewCadence: quarterly
~~~

Ví dụ mô tả yêu cầu nghiệp vụ để chuyển thành cú pháp cụ thể. Hệ thống IAM thực tế có thể **không đánh giá trực tiếp** thuộc tính `identityStatus` từ HRIS hoặc `environment` từ nguồn tùy ý. Muốn dùng thuộc tính trong điều kiện bảo mật, phải xác nhận nó được nền tảng cung cấp, tin cậy và cập nhật đúng hạn.

### 3.2. Least privilege: ít quyền nhất theo ba chiều

**Least privilege** cần xem đồng thời:

1. **Hành động:** Chỉ những API cần dùng; tách đọc log khỏi xóa log và sửa IAM.
2. **Tài nguyên:** Chỉ account, project, bucket, secret hoặc service được giao.
3. **Thời gian/ngữ cảnh:** Quyền có thời hạn, ràng buộc phiên, môi trường, danh tính hoặc điều kiện phù hợp nếu nền tảng hỗ trợ.

Ví dụ, `storage.objects.read` trên một bucket báo cáo có phạm vi nhỏ hơn nhiều so với quyền quản trị toàn bộ dự án. Một policy có ít action nhưng gắn ở phạm vi toàn tổ chức vẫn có thể quá rộng.

### 3.3. Tránh dùng wildcard thiếu kiểm soát

Wildcard có thể xuất hiện trong action, resource hoặc điều kiện tùy provider. Một quy tắc dạng “mọi action trên mọi resource” có phạm vi cao và cần lý do đặc biệt; không nên là baseline cho người dùng, CI/CD hoặc workload.

Khi chưa xác định được permission tối thiểu, hãy bắt đầu bằng nhiệm vụ cụ thể, thử nghiệm trong môi trường kiểm soát và thu hẹp phạm vi. Không nên lấy một policy Administrator làm mẫu rồi xóa ngẫu nhiên vài action mà không hiểu các đường nâng đặc quyền.

## 4. Cloud IAM đánh giá policy như thế nào?

Tư duy an toàn thường là **không có quyền cho đến khi được cho phép theo cơ chế của nền tảng**. Với một yêu cầu, IAM sẽ kiểm tra principal, tài nguyên, action và các quy tắc có hiệu lực. Tuy nhiên, **cách kết hợp Allow, Deny, quyền kế thừa và policy hạn chế khác nhau giữa nhà cung cấp**.

Một mô hình khái niệm:

~~~text
request = {principal, action, resource, context}

if authenticationOrCredentialInvalid(request):
    reject

candidateRules = findApplicableRules(request)
decision = providerSpecificEvaluation(candidateRules)

if decision == PERMIT:
    performActionAndAudit()
else:
    rejectAndAudit()
~~~

Đây là giả mã để hiểu luồng, không thay thế thuật toán chính thức của AWS IAM, Azure RBAC hoặc Google Cloud IAM.

### 4.1. Implicit deny và explicit deny

**Implicit deny** là kết quả khi chưa có đường cho phép hợp lệ theo mô hình đánh giá của nền tảng. **Explicit deny** là một quy tắc chủ động từ chối, thường có ưu tiên đặc biệt trong những hệ thống hỗ trợ. Trong AWS, một explicit deny áp dụng thường chặn quyền ngay cả khi có allow tương ứng. Google Cloud cũng có cơ chế **IAM deny policies** riêng trong các phạm vi được hỗ trợ.

Không được áp dụng máy móc mô hình “Deny luôn thắng” cho mọi tài liệu policy của mọi nhà cung cấp: chẳng hạn **Azure RBAC deny assignments** có cơ chế và đối tượng quản lý riêng, không phải một trường Deny tùy ý trong mọi role definition.

### 4.2. Quyền được cấp chưa chắc là quyền hiệu lực

Một role assignment có thể được cấu hình nhưng vẫn bị giới hạn bởi guardrail, condition, chính sách khác, thời hạn phiên hoặc quyền trong dịch vụ dữ liệu. Ngược lại, người dùng có thể nhận quyền qua một đường khác ngoài assignment bạn vừa kiểm tra, như nhóm lồng nhau, quyền kế thừa, resource policy hoặc khả năng impersonate một principal mạnh hơn.

Vì vậy cần phân biệt:

- **Desired access:** Quyền doanh nghiệp đã phê duyệt theo chức trách và trạng thái danh tính.
- **Assigned access:** Quyền thực sự được gắn tại hệ thống cloud hoặc nguồn liên kết.
- **Effective access:** Quyền được IAM cho phép sau khi xét các lớp chính sách, scope, điều kiện và ngữ cảnh.

Chính sách chỉ an toàn khi cả ba trạng thái được kiểm tra trong bối cảnh thực tế.

## 5. AWS: các lớp IAM policy

AWS cung cấp nhiều loại policy có mục đích khác nhau. Khi giải quyết một yêu cầu bị từ chối hoặc rà soát truy cập tồn dư, cần biết **policy đang nằm ở lớp nào**.

| Cơ chế AWS | Vai trò chính | Điểm cần lưu ý |
| --- | --- | --- |
| **Identity-based policy** | Gắn permissions cho IAM user, group hoặc role | Giới hạn action/resource/condition; IAM role thường dùng cho người dùng federated và workload |
| **Resource-based policy** | Gắn quy tắc truy cập ngay trên tài nguyên hỗ trợ | Có thể cho phép principal phù hợp ở account khác; cần xem cả principal và resource |
| **Role trust policy** | Xác định principal nào có thể assume role | Trust không tự quyết định role được làm mọi thao tác |
| **Permissions boundary** | Giới hạn quyền tối đa của identity được áp boundary | Boundary **không tự cấp** quyền |
| **AWS Organizations Service Control Policy (SCP)** | Giới hạn quyền tối đa đối với principal/tài khoản thuộc phạm vi quản trị hỗ trợ | SCP **không tự cấp** quyền; có ngoại lệ và ngữ nghĩa đánh giá riêng |
| **Session policy** | Giới hạn thêm quyền của phiên tạm thời | Không mở rộng quyền vượt quá quyền nền của phiên |
| **Tag/condition-based controls** | Ràng buộc truy cập theo ngữ cảnh được IAM hỗ trợ | Kiểm tra nguồn tag và khả năng principal sửa tag |

Đối với một principal, IAM có thể xét nhiều loại policy đồng thời. **Policy gắn ở các lớp không luôn cộng quyền đơn giản**: một số lớp tạo quyền Allow, lớp khác đặt giới hạn hoặc Deny. Các trường hợp đặc biệt như resource-based access, root và service-specific authorization cần đối chiếu hướng dẫn đúng dịch vụ khi triển khai.

### 5.1. Trust policy và permissions policy khác nhau

Giả sử pipeline triển khai qua OIDC federation muốn dùng role `staging-deployer`.

~~~yaml
# Giả mã: không phải AWS IAM policy JSON triển khai trực tiếp
role: staging-deployer
trust:
  trustedIssuer: ci-approved.example
  allowedAudience: expected-sts-audience
  allowedSubject:
    repository: example-org/learning-api
    environment: staging
permissions:
  allow:
    - action: deployment.update
      resource: staging-learning-api
    - action: artifact.read
      resource: staging-artifacts
restrictions:
  noProductionScope: true
~~~

**Trust** trả lời “pipeline nào được nhận phiên role?”; **permissions** trả lời “phiên được thao tác gì?”. Giới hạn issuer, audience và subject phải được biểu diễn đúng theo loại IdP/OIDC và condition keys AWS hỗ trợ, không được coi các khóa trong giả mã này là cú pháp AWS chuẩn.

Nếu trust chỉ ghi “mọi repository trong tổ chức đều được assume”, một pipeline không được duyệt có thể nhận quyền. Nếu permissions vẫn cho phép quản trị production, một pipeline staging bị xâm nhập có thể tác động vượt môi trường. Cả hai phía cần giới hạn.

### 5.2. Ví dụ policy AWS dạng JSON

Ví dụ dưới đây minh họa **cấu trúc** một identity-based policy, sử dụng ARN và action giả định đã chọn cho một hệ thống mẫu; phải xác minh action, loại resource và ARN trước khi triển khai:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadSpecificLogEvents",
      "Effect": "Allow",
      "Action": [
        "logs:DescribeLogStreams",
        "logs:GetLogEvents"
      ],
      "Resource": "arn:aws:logs:ap-southeast-1:111122223333:log-group:/apps/learning/dev:*"
    }
  ]
}
~~~

Policy trên **chỉ là ví dụ cấu trúc**, không bảo đảm đủ mọi permission để duyệt log trong giao diện hoặc đáp ứng mọi API của ứng dụng. Với AWS cần kiểm tra từng action có hỗ trợ resource-level permissions không, ARN được phép, điều kiện và các quyền phụ trợ; dùng công cụ phân tích/simulation thích hợp trước khi áp production.

### 5.3. CloudTrail, Access Analyzer và công cụ kiểm tra

AWS có các công cụ ghi sự kiện API và phân tích truy cập như **CloudTrail** và **IAM Access Analyzer**. Khi review:

- Xác định policy/role nào đang được principal sử dụng hoặc trust đến principal nào.
- Kiểm tra quyền rộng, truy cập cross-account và đường truy cập public nếu tài nguyên hỗ trợ.
- Xem các event IAM liên quan tới tạo/sửa policy, trust, role và credential.
- Dùng thông tin sử dụng quyền để đề xuất thu hẹp, nhưng không coi **ít xuất hiện trong log** là bằng chứng quyền chắc chắn không cần nữa.
- Kiểm tra kết quả sau thu hồi tại account đích, nhất là phiên tạm thời còn hiệu lực.

## 6. Azure: RBAC, Azure Policy và Conditional Access

Trong hệ sinh thái Microsoft, ba cơ chế có tên liên quan tới “policy” nhưng khác mục đích:

| Cơ chế | Quản lý cái gì? | Ví dụ |
| --- | --- | --- |
| **Azure RBAC** | Quyền một principal được thực hiện trên tài nguyên Azure qua role assignment tại scope | Nhóm SRE nhận Reader trên một resource group |
| **Azure Policy** | Quy tắc quản trị trạng thái/cấu hình tài nguyên Azure | Đánh giá hoặc ngăn tạo tài nguyên không tuân thủ baseline |
| **Microsoft Entra Conditional Access** | Điều kiện truy cập/đăng nhập tại IdP khi đáp ứng các khả năng và cấu hình | Yêu cầu MFA hoặc điều kiện thiết bị khi vào ứng dụng |

**Azure Policy không cấp Azure RBAC role.** Một chính sách yêu cầu mã hóa hoặc giới hạn location không khiến nhân viên có quyền xem tài nguyên. Tương tự, Entra Conditional Access không thay thế việc gỡ role assignment của người nghỉ việc.

### 6.1. Azure RBAC role definition và assignment

Một assignment diễn tả:

~~~text
roleAssignment = (securityPrincipal, roleDefinition, scope)
~~~

**Role definition** gồm tập thao tác quản trị và/hoặc dữ liệu được cho phép theo cấu trúc role. **Scope** có thể là management group, subscription, resource group hoặc resource. Quyền có thể kế thừa từ scope cha theo cơ chế Azure RBAC.

Ví dụ:

~~~yaml
# Mô tả nghiệp vụ, không phải cú pháp triển khai Azure
principal: group:learning-developers
role: Reader
scope: subscription:dev-sub/resourceGroup:rg-learning-dev
approvedBy: learning-platform-owner
~~~

Một assignment Reader tại resource group có phạm vi khác Reader tại toàn subscription. Khi điều tra truy cập tồn dư, phải truy vấn **cả assignment gắn trực tiếp và assignment kế thừa**.

### 6.2. Azure Policy: guardrail cấu hình

Azure Policy dùng definition, assignment và các hiệu ứng quản trị phù hợp để đánh giá hoặc thực thi quy tắc đối với tài nguyên. Ví dụ doanh nghiệp muốn tài nguyên mới ở production có tag chi phí hoặc nằm trong vùng được phê duyệt.

~~~yaml
# Mục tiêu quản trị giả định, không phải Azure Policy definition JSON
policyObjective: prod-resource-governance
scope: production-subscription
rules:
  - requireTag: costCenter
  - allowedRegions:
      - southeastasia
  - requireApprovedResourceTypes: true
response:
  onViolation: evaluate-or-enforce-per-approved-design
~~~

Đối với các hiệu ứng như `audit`, `deny`, `modify` hoặc `deployIfNotExists` (khi hỗ trợ), cần hiểu tác động và quyền mà managed identity của assignment có thể cần. Không nên chuyển một quy tắc đang ở chế độ đánh giá thành chặn production mà chưa kiểm tra tác động lên tài nguyên và pipeline hiện hành.

### 6.3. Azure RBAC conditions và deny assignments

Azure có cơ chế **role assignment conditions** cho những trường hợp và dịch vụ được hỗ trợ; không phải permission nào cũng dùng được cùng một loại điều kiện. **Deny assignments** có ngữ nghĩa và quyền quản trị riêng, thường gắn với các chức năng do nền tảng quản lý. Không thể suy luận rằng mọi người quản trị có thể tự viết một biểu thức Deny vào mọi role assignment.

Một principal bị chặn bởi deny assignment hoặc restriction phù hợp có thể bị từ chối ngay cả khi có role assignment Allow. Khi đánh giá quyền cần xét **role, scope, kế thừa, condition, deny và dữ liệu đích**.

## 7. Google Cloud: allow, deny và tổ chức quản trị

**Google Cloud IAM allow policy** là tập **bindings** liên kết principal với **role** tại organization, folder, project hoặc resource hỗ trợ. Role chứa tập permissions. Đối với quyền đọc hoặc thay đổi tài nguyên, IAM sẽ xét các binding có hiệu lực và những hạn chế liên quan.

### 7.1. Allow policy và IAM Conditions

Ví dụ minh họa:

~~~yaml
# Mô hình policy rút gọn, không đảm bảo triển khai nguyên trạng
resource: projects/learning-dev
bindings:
  - role: roles/logging.viewer
    members:
      - group:learning-ops@example.org
~~~

Binding trên cho thấy ý tưởng nhóm nhận vai trò xem log ở phạm vi project, nhưng quyền thực tế còn phụ thuộc các policy khác và cấu hình dịch vụ. Khi dùng **IAM Conditions**, có thể bổ sung điều kiện theo thuộc tính/ngữ cảnh được hỗ trợ; phải kiểm tra loại resource, permission và biểu thức áp dụng trước khi triển khai.

### 7.2. IAM deny policies và Organization Policy

Google Cloud có **IAM deny policies** để chặn một số quyền theo phạm vi và kiểu principal/permission được hỗ trợ. **Organization Policy Service** dùng để áp **constraints** quản trị hành vi tài nguyên của tổ chức. Hai cơ chế này khác IAM allow binding:

- **IAM allow policy:** Cấp đường quyền thông qua role binding.
- **IAM deny policy:** Chặn permission theo quy tắc và phạm vi được hỗ trợ.
- **Organization Policy:** Giới hạn cấu hình/cách dùng tài nguyên theo constraint, không tự gán IAM role.
- **Principal Access Boundary (khi dùng):** Một cơ chế bổ sung giới hạn phạm vi tài nguyên principal có thể truy cập theo mô hình và hỗ trợ của nền tảng.

Ví dụ, một nhóm được gắn role Editor ở project dev nhưng constraint cấp tổ chức có thể ngăn một số cấu hình hạ tầng. Khi tổng hợp quyền, cần đọc **đúng lớp policy** và hiểu lớp đó quyết định quyền hay giới hạn cấu hình.

### 7.3. Service account và impersonation

Trong Google Cloud, **service account** là principal có thể được gắn role để truy cập tài nguyên. Nếu người dùng hoặc workload có quyền tạo credential hoặc impersonate service account, họ có thể nhận quyền theo danh tính đó trong phạm vi cho phép.

Điều này tạo ra **đường nâng quyền gián tiếp**. Khi nhân viên đổi vai trò hoặc rời công ty, cần kiểm tra cả binding trên người đó và quyền dùng service account có đặc quyền. Không nên chỉ nhìn những role gắn trực tiếp với email người dùng.

## 8. RBAC, ABAC và điều kiện policy

**Role-Based Access Control (RBAC)** tổ chức quyền thành role và gán cho principal theo chức trách. **Attribute-Based Access Control (ABAC)** đưa thuộc tính của principal, tài nguyên hoặc request vào điều kiện ra quyết định. Cloud IAM có thể kết hợp hai mô hình tùy nhà cung cấp.

### 8.1. Ví dụ RBAC

Nhóm `learning-developers` nhận role `DevLogReader` tại project dev. Khi nhân viên chuyển đội, workflow JML cập nhật membership và entitlement ở cloud target. Ưu điểm là dễ quản lý theo nhóm, nhưng phải rà soát những grant trực tiếp và quyền kế thừa bên ngoài group.

### 8.2. Ví dụ ABAC theo thuộc tính được quản trị

~~~yaml
# Giả mã trung lập; chỉ dùng khi provider hỗ trợ nguồn thuộc tính này
principal:
  team: learning
  status: active
resource:
  team: learning
  environment: dev
request:
  action: logs.read
decision:
  allowWhen:
    - principal.status == active
    - principal.team == resource.team
    - resource.environment == dev
~~~

Điểm cần làm rõ:

1. **Thuộc tính phải đáng tin cậy:** Không để principal tự gắn nhãn “owner” lên tài nguyên nhạy cảm nếu nhãn đó tạo thêm quyền.
2. **Có nguồn cập nhật:** Team hoặc vai trò thay đổi từ HRIS/IGA phải lan truyền đến IdP và cloud đúng thời điểm.
3. **Giữ phân tách trách nhiệm:** Người thay đổi thuộc tính quyết định quyền không nên được tự phê duyệt quyền nhạy cảm.
4. **Thử nhiều trường hợp:** Thuộc tính thiếu, sai, hết hiệu lực, resource không gắn nhãn hoặc bị đổi nhãn.
5. **Vẫn cần thu hồi quyền cũ:** ABAC chỉ áp những quy tắc thực sự được đánh giá; grant trực tiếp ở nơi khác có thể còn nguyên.

### 8.3. Policy điều kiện không đồng nghĩa trust policy

Một điều kiện “chỉ khi resource.environment=dev” không cho biết **ai được tin cậy để assume role**. Với danh tính federated hoặc workload OIDC, phải xác thực issuer/audience/subject; sau đó kiểm tra permissions và scope. Bỏ sót một trong hai lớp có thể tạo đường truy cập trái phép.

## 9. Cloud policy trong Joiner–Mover–Leaver

Một policy có thể **tồn tại lâu dài như quy tắc của tổ chức**, nhưng entitlement áp dụng cho người hoặc workload phải thay đổi theo sự kiện JML. Cần phân biệt **vòng đời policy definition** với **vòng đời quyền phát sinh từ policy**.

| Giai đoạn | Dữ liệu đầu vào | Tác động đến policy/entitlement | Kiểm tra kết thúc |
| --- | --- | --- | --- |
| **Joiner** | Danh tính hợp lệ, vai trò, đơn vị, owner, ngày hiệu lực | Chọn role/policy chuẩn, cấp assignment hoặc trust tối thiểu và có phê duyệt | Principal làm được công việc cần thiết, không có quyền rộng ngoài dự kiến |
| **Mover** | Đổi nhóm, dự án, môi trường, mức nhạy cảm | Tính lại desired access, thu hồi grant theo vai trò cũ, cấp quyền mới đúng scope | Không còn binding/role/trust cũ ngoài ngoại lệ được duyệt |
| **Leaver** | Nghỉ việc, chấm dứt hợp đồng, thu hồi tư cách | Khóa IdP, thu hồi assignment, resource access, credential và session theo khả năng | Tại các cloud target không còn đường truy cập trái phép; có bằng chứng |

### 9.1. Joiner: chọn policy đúng trước khi cấp quyền

Ví dụ nhân viên **Lan** (identity ID `EMP-4017`) gia nhập đội Learning Backend. HRIS xác nhận hồ sơ và ngày hiệu lực; IGA đối chiếu danh mục role. Lan được cấp **DevLogReader** trên dự án learning-dev, không có quyền triển khai production.

Luồng kiểm soát:

1. Xác minh danh tính và chủ sở hữu phê duyệt.
2. Xác định công việc, action và resource thực sự cần.
3. Dùng role/policy đã được thẩm định hoặc đưa policy mới qua review.
4. Gắn role/entitlement vào đúng principal và scope thông qua IdP group hoặc API cloud.
5. Xác minh các hành động hợp lệ được phép, hành động ngoài phạm vi bị từ chối.
6. Ghi audit: nguồn sự kiện, ID, chính sách/phiên bản, grant, người duyệt và kết quả.

### 9.2. Mover: tính lại cả quyền mong muốn và quyền hiện có

Lan chuyển từ đội Backend sang Data Analytics. Chính sách mới có thể cho phép đọc dữ liệu phân tích ở development nhưng quyền triển khai dịch vụ backend không còn cần.

Nếu workflow chỉ **thêm quyền mới**, Lan vẫn giữ quyền cũ, tạo **privilege accumulation**. Bước bắt buộc của Mover là:

- Xác định **desired access** từ công việc mới và các ngoại lệ còn hiệu lực.
- Truy vấn **actual grants** gồm group membership, assignment/binding, identity-based policy, resource policy, trust và quyền kế thừa.
- Thu hồi grant không còn được duyệt, giải quyết xung đột **Separation of Duties (SoD)**.
- Cấp quyền mới đúng role/scope theo phê duyệt.
- Xác minh effective access tại cloud target và ghi trạng thái xử lý.

**Lưu ý:** Một policy dùng chung cho hàng chục nhân viên không nên bị xóa chỉ vì Lan đổi đội. Nên gỡ entitlement riêng của Lan. Chỉ thay policy definition nếu yêu cầu nghiệp vụ hoặc phân tích rủi ro thay đổi.

### 9.3. Leaver: xử lý đầy đủ đường truy cập

Khi Lan nghỉ việc, quy trình cần:

1. Vô hiệu hóa đăng nhập tại IdP và đồng bộ trạng thái account đích theo tích hợp có sẵn.
2. Thu hồi quyền gắn qua nhóm, trực tiếp, role assignment, IAM binding, trust hoặc resource policy có liên quan.
3. Kiểm tra tài khoản cloud-local, guest và tài khoản bên thứ ba được liên kết.
4. Vô hiệu hóa/thu hồi access key, personal token, secret hoặc credential còn sở hữu; xoay credential dùng chung nếu cần.
5. Xử lý session/temporary credentials đã phát hành: dùng cơ chế revoke được hỗ trợ, rút ngắn hiệu lực khi khả thi và ghi rõ trường hợp phải chờ hết hạn.
6. Chuyển ownership service account, pipeline, tài nguyên và policy quan trọng nếu người đó là owner.
7. Đọc lại trạng thái quyền và thử kiểm tra truy cập theo quy trình được phép; lưu bằng chứng kỹ thuật.

Một API thu hồi trả về thành công **chưa chứng minh toàn bộ quyền đã mất**. Cần xác định quyền có thể tồn tại qua chính sách kế thừa, credential độc lập hoặc phiên cũ.

### 9.4. Đồng bộ SCIM và quyền trên cloud

**SCIM** thường được dùng để quản lý user/group và thuộc tính ở dịch vụ hỗ trợ. **SSO** xác thực người dùng. **Cloud IAM policies** kiểm soát action trên tài nguyên. Không nên đồng nhất ba khái niệm này:

| Tác vụ | Thành phần thường phụ trách |
| --- | --- |
| Xác thực và điều kiện đăng nhập | IdP, SSO, MFA, Conditional Access |
| Tạo/sửa/vô hiệu hóa user/group ở dịch vụ hỗ trợ | SCIM hoặc provisioning API |
| Cấp/thu hồi quyền cloud | Cloud IAM role assignment, binding, policy/trust qua API hoặc tích hợp |
| So sánh quyền được duyệt và quyền thực tế | IGA/lifecycle + inventory/reconciliation |
| Ghi bằng chứng kiểm toán | Logging, audit, SIEM hoặc hệ thống JML |

Khi một cloud không hỗ trợ SCIM cho đối tượng quyền cần quản lý, hệ thống JML phải dùng công cụ/đường tích hợp khác, đồng thời có cách kiểm tra trạng thái thực tế.

## 10. Policy cho workload và service account

Cloud IAM không chỉ phục vụ tài khoản người dùng. Một ứng dụng, container, máy ảo, function, service account hoặc CI/CD pipeline cũng cần danh tính riêng và policy đúng nhiệm vụ.

| Workload | Mô hình nhận danh tính thường dùng | Quy tắc policy quan trọng |
| --- | --- | --- |
| Compute chạy trên AWS | IAM role/instance profile và credential tạm thời | Action/resource nhỏ nhất, không dùng access key gắn cứng |
| Ứng dụng trên Azure | Managed identity + RBAC assignment | Chỉ cho phép truy cập đúng service/resource ở scope cần thiết |
| Workload trên Google Cloud | Service account hoặc Workload Identity Federation | Rà soát bindings và quyền impersonation |
| CI/CD bên ngoài cloud | OIDC federation khi có hỗ trợ | Trust giới hạn issuer, audience, repository, nhánh, môi trường |
| Hệ thống cũ dùng secret | Key trong secret manager với owner và rotation | Hạn dùng, giám sát lộ lọt, quyền tối thiểu và kế hoạch chuyển đổi |

### 10.1. Policy phải ràng buộc cả danh tính nguồn

Ví dụ pipeline chỉ triển khai staging. Nếu policy cấp quyền triển khai hẹp nhưng **trust** cho phép mọi repository trong organization assume role, một pipeline ngoài dự kiến vẫn có thể nhận quyền. Cần kiểm tra:

- Issuer ký token và cơ chế kiểm tra chữ ký.
- Audience token dành cho hệ thống đổi quyền tương ứng.
- Subject/claims chứng minh đúng repository, workflow, branch hoặc environment được cho phép khi provider hỗ trợ.
- Quyền phiên chỉ dành cho staging, không mặc định truy cập production.
- Thời hạn credential, cảnh báo và audit cho thao tác deployment.

### 10.2. Vòng đời policy của workload

**Joiner:** Đăng ký workload với owner, mục đích, môi trường; tạo principal và policy qua workflow/IaC.  
**Mover:** Khi pipeline đổi repository, ứng dụng đổi project hoặc workload đổi owner, cập nhật trust/scope và thu hồi credential hoặc policy cũ.  
**Leaver:** Khi workload ngừng hoạt động, xóa binding/trust/credential liên quan, kiểm tra rằng không còn đường truy cập API hợp lệ.

Không nên gắn credential hoạt động của ứng dụng với **user cá nhân**; người đó nghỉ việc không được khiến hệ thống production mất vận hành hoặc giữ lại quyền trái phép.

## 11. Chính sách đặc quyền và ngăn nâng quyền

Policy có quyền sửa IAM, tạo role, quản trị key, thay trust, đọc secret hoặc thay pipeline production cần được kiểm soát như **privileged access**. Một principal không có tên role “Administrator” vẫn có thể tự tạo quyền quản trị nếu được sửa policy hoặc impersonate principal mạnh hơn.

### 11.1. Những đường nâng đặc quyền gián tiếp

| Năng lực có trong policy | Nguy cơ | Kiểm soát |
| --- | --- | --- |
| Sửa policy hoặc gán role | Tự cấp quyền vượt công việc | Tách nhiệm vụ IAM administration, approval độc lập, policy boundary |
| Thay role trust | Cho bên ngoài đảm nhận role có quyền mạnh | Kiểm soát và audit thay trust; giới hạn người được phép sửa |
| Tạo token/impersonate service account | Hành động dưới principal có quyền cao | Giới hạn impersonation và audit phiên cấp token |
| Đọc secret của workload | Có thể sử dụng credential để truy cập ngoài role trực tiếp | Quyền đọc secret tối thiểu, rotation và giám sát |
| Thay pipeline hoặc IaC của production | Tự tạo thay đổi hoặc dùng role của pipeline | Branch protection, review, phân tách người duyệt và người triển khai |
| Tắt logging/giám sát | Che giấu hành vi sau khi có quyền | Guardrail, quyền riêng và lưu log độc lập |

**Phân tách nhiệm vụ (SoD)** cần được xem ở góc **khả năng cuối cùng**. Ví dụ người duyệt quyền không nên tự cấp quyền quản trị cho chính mình; người có quyền thay đổi pipeline production có thể gián tiếp sử dụng quyền của pipeline.

### 11.2. Quyền có thời hạn và phê duyệt

Với thao tác rủi ro cao, nên áp dụng **just-in-time access**, **Privileged Identity Management (PIM)** hoặc workflow PAM nếu nền tảng và kiến trúc hỗ trợ:

1. Principal đủ điều kiện theo chính sách.
2. Yêu cầu nêu lý do, ticket và resource scope.
3. Có người phê duyệt độc lập khi cần.
4. Xác thực mạnh và kiểm soát thiết bị phù hợp.
5. Cấp quyền trong khoảng thời gian xác định.
6. Hết hạn hoặc xử lý xong thì thu hồi và xác minh.
7. Lưu log phiên, thay đổi IAM và kết quả hoạt động.

Quyền khẩn cấp **break-glass** cần có đường sử dụng được kiểm soát khi IdP/SSO gặp sự cố, cơ chế bảo vệ riêng và cảnh báo khi sử dụng. Không dùng như quyền vận hành hằng ngày.

## 12. Policy-as-code: quản lý thay đổi như mã nguồn

**Policy-as-code** lưu nội dung policy và các thay đổi có thể tái tạo trong hệ thống quản lý phiên bản, thường kết hợp Infrastructure as Code (IaC), pipeline kiểm tra và quy trình phê duyệt. Mục tiêu là giảm cấu hình thủ công khó truy vết và phát hiện policy drift.

### 12.1. Quy trình thay đổi policy an toàn

~~~mermaid
flowchart TD
    R["Đề xuất nhu cầu quyền<br/>principal + action + resource + owner"] --> D["Soạn policy / role binding qua mã nguồn"]
    D --> V["Kiểm tra cú pháp và cấu trúc"]
    V --> S["Phân tích semantic<br/>wildcard, scope, privilege escalation"]
    S --> T["Thử nghiệm Allow/Deny cần thiết"]
    T --> A["Review + phê duyệt"]
    A --> P["Triển khai có kiểm soát"]
    P --> C["Readback + xác minh thực tế"]
    C --> O["Audit + theo dõi drift"]
    C -->|Lỗi| X["Khắc phục/rollback theo kế hoạch"]
    X --> D
~~~

Mỗi bước cần tạo bằng chứng tương ứng:

- **Đề xuất:** Lý do nghiệp vụ, account/project/subscription ID, principal, owner, thời hạn.
- **Thay đổi:** Diff có thể review, tác giả, mã ticket, phiên bản policy.
- **Kiểm tra:** Kết quả linter/validator, phân tích quyền rộng, kiểm thử hành vi được phép và bị từ chối.
- **Phê duyệt:** Người chịu trách nhiệm tài nguyên/dữ liệu và IAM/security khi rủi ro cao.
- **Triển khai:** Danh tính triển khai, phạm vi, timestamp, kết quả API.
- **Kiểm chứng:** Cấu hình đọc lại, effective access hoặc kết quả thử theo công cụ hỗ trợ.
- **Vận hành:** Log thay đổi ngoài pipeline, drift và thời điểm access review.

### 12.2. Đánh giá tác động trước triển khai

Với policy có thể chặn truy cập (deny, guardrail, condition mới), cần xác định **blast radius**: những user, workload, account và API nào bị ảnh hưởng. Có thể dùng mô phỏng/chế độ audit hoặc kiểm thử trên phạm vi nhỏ nếu nhà cung cấp hỗ trợ.

Ví dụ khi định chặn tạo tài nguyên ở vùng chưa duyệt, phải kiểm tra pipeline tạo môi trường thử nghiệm, dịch vụ quản lý tự động và tài nguyên hiện hữu có cần thay đổi không. Rollback phải được chuẩn bị và kiểm soát vì đảo một policy sai có thể tạo lỗ hổng nếu làm rộng quyền quá mức.

### 12.3. Một bài kiểm thử policy có ý nghĩa

Với yêu cầu “Developer chỉ đọc log ở project dev”, bộ tình huống cần ít nhất:

| Yêu cầu thử nghiệm | Kỳ vọng |
| --- | --- |
| Principal hợp lệ đọc log dự án dev | Allow |
| Principal hợp lệ xóa log dev | Deny |
| Principal hợp lệ đọc log production | Deny |
| Principal không thuộc nhóm được duyệt đọc log dev | Deny |
| Token/credential đã hết hiệu lực thực hiện thao tác | Không được chấp nhận |
| Principal chuyển đội, grant cũ đã thu hồi, thử đọc log dev | Deny |
| Principal dùng đường grant trực tiếp ngoài group | Phát hiện được và xử lý theo policy |

Không viết kiểm thử chỉ xác nhận rằng policy chứa chuỗi ký tự “Allow”; cần kiểm tra **quyền thực sự được cho hoặc bị từ chối** theo các kịch bản nghiệp vụ.

## 13. Phát hiện policy drift và quyền truy cập tồn dư

**Policy drift** là chênh lệch giữa cấu hình mong muốn đã được phê duyệt và cấu hình hiện có trên cloud, ví dụ một quản trị viên sửa policy trực tiếp trong console nhưng không cập nhật repository/IaC.

**Residual access** là quyền còn tồn tại khi danh tính, vai trò hoặc workload không còn đủ điều kiện sử dụng; có thể phát sinh bởi drift, lỗi provisioning, quyền trực tiếp, trust ngoài ý muốn hoặc session chưa hết hạn.

### 13.1. Đối soát desired và actual

~~~text
event = getAuthorizedLifecycleEvent(identityId)
targets = discoverAllRelevantCloudTargets(identityId)

for target in targets:
    desired = calculateApprovedAccess(identityId, target)
    actual = enumerateAssignmentsPoliciesTrustAndCredentials(identityId, target)
    staleGrants = normalize(actual) - normalize(desired)

    for grant in staleGrants:
        revokeWithAudit(grant)

    effective = verifyAccessUsingSupportedMethods(identityId, target)
    if effectiveMatchesPolicy(effective, desired):
        markVerified(event, target)
    else:
        escalateWithOwner(event, target, effective)
~~~

Đây là **giả mã khái niệm**. Phép trừ đơn giản chỉ hợp lý khi đã chuẩn hóa đầy đủ principal, source group, role, scope, điều kiện và hạn dùng. Một role trên organization không tương đương role cùng tên trên một project. **Effective access** có thể không được liệt kê đầy đủ chỉ qua một API; đôi khi cần kết hợp phân tích IAM và kiểm thử truy cập có kiểm soát.

### 13.2. Những nguồn phải kiểm tra

| Nguồn quyền | Dấu hiệu quyền tồn dư |
| --- | --- |
| IdP và nhóm liên kết | User đã đổi team nhưng vẫn nằm trong nhóm cấp role cũ |
| IAM assignment/binding trực tiếp | Quyền vẫn gắn với principal dù group đã được thu hồi |
| IAM policy/trust | Một role khác vẫn cho principal hoặc issuer nguồn đảm nhận quyền |
| Resource policy | Bucket/secret/database còn chấp nhận principal hoặc account không còn hợp lệ |
| Cloud-local identity | User hoặc key độc lập với SSO vẫn hoạt động |
| Service account impersonation | Người dùng cũ còn đường dùng service account có quyền rộng |
| Credential/session | Token hoặc key chưa hết hạn; session không được thu hồi phù hợp |
| Policy drift | Thay đổi trực tiếp không có approval hoặc không xuất hiện trong IaC |

### 13.3. Không nhầm request với kết quả

Một workflow cần phân biệt trạng thái:

~~~text
REQUESTED   Yêu cầu cấp hoặc thu hồi quyền đã được tạo
APPROVED    Người có thẩm quyền đã duyệt
APPLIED     Thao tác thay đổi được hệ thống đích báo thành công
VERIFIED    Đã đọc lại/truy vấn hiệu lực và chứng minh đạt yêu cầu
FAILED      Thao tác hoặc xác minh thất bại
EXCEPTION   Ngoại lệ có owner, lý do và thời hạn xử lý
~~~

Khi Leaver ở trạng thái APPLIED nhưng còn role assignment trực tiếp hoặc credential độc lập, sự kiện **chưa hoàn tất**. Nếu một phiên tạm thời không thể vô hiệu hóa ngay, phải ghi rõ giới hạn và biện pháp giảm rủi ro cùng thời điểm hết hiệu lực theo thực tế.

## 14. Tình huống thực tế: chuyển vai trò và policy còn sót

Giả sử doanh nghiệp vận hành ứng dụng Learning trên ba môi trường:

- **learning-dev:** Kỹ sư được xem log và triển khai thử nghiệm.
- **learning-staging:** Pipeline CI/CD được triển khai sau khi qua quy trình review.
- **learning-prod:** Chỉ người trực vận hành được duyệt có quyền xử lý sự cố production.

Nhân viên **Lan**, ID `EMP-4017`, ban đầu thuộc đội Learning Backend. Mỗi môi trường nằm trong phạm vi cloud riêng theo kiến trúc tổ chức.

### 14.1. Joiner

Workflow JML xác minh Lan đang active tại HRIS, tạo/đồng bộ account IdP và đưa vào nhóm Learning Developers. Qua policy chuẩn, Lan được quyền `logs.read` tại learning-dev. Lan không được sửa IAM hoặc dùng deployment role production.

Kết quả kiểm tra:

~~~text
EMP-4017 + logs.read + learning-dev     -> ALLOW
EMP-4017 + logs.delete + learning-dev   -> DENY
EMP-4017 + deploy + learning-prod       -> DENY
~~~

Đây là kết quả kỳ vọng theo yêu cầu nghiệp vụ, không phải output của một API cloud cụ thể.

### 14.2. Mover

Lan chuyển sang đội Data Analytics. Desired access mới cho phép đọc một tập dữ liệu đã phân loại tại analytics-dev, nhưng không còn quyền đọc log learning-dev.

Hệ thống sửa IdP group đúng, song trong cloud vẫn còn **assignment trực tiếp** cho Lan tại learning-dev. Ngoài ra, một resource policy của bucket log được tạo trước đó còn tham chiếu principal cũ. Nếu chỉ kiểm tra group, workflow sẽ báo hoàn tất sai.

~~~mermaid
flowchart LR
    HR["HRIS: Mover"] --> DES["Desired access mới"]
    DES --> IDP["IdP group đã cập nhật"]
    IDP --> AUD["Reconciliation"]
    GR["Direct role assignment còn sót"] --> AUD
    RP["Resource policy còn sót"] --> AUD
    AUD --> FIX["Thu hồi grant và cập nhật policy"]
    FIX --> VERIFY["Verify effective access"]
    VERIFY --> DONE["Verified + bằng chứng"]
~~~

Khi xóa grant trực tiếp và đường resource policy không còn hợp lệ, hệ thống kiểm tra lại quyền đã bị từ chối và ghi người phê duyệt, resource ID, trước/sau, thời điểm và kết quả.

### 14.3. Leaver

Một thời gian sau, Lan nghỉ việc. IdP disable tài khoản; cloud target thu hồi role/binding còn lại. Nhóm kiểm toán kiểm tra IAM, trust, session và credential liên quan. Nếu Lan sở hữu một pipeline, ownership phải được chuyển giao và credential dùng chung được xoay khi cần.

Ví dụ bản ghi kiểm toán (dữ liệu giả định):

~~~json
{
  "eventId": "JML-LEAVER-0417",
  "identityId": "EMP-4017",
  "eventType": "leaver",
  "source": "HRIS",
  "target": "learning-dev",
  "policyReference": "learning-dev-log-read",
  "operation": "revoke_stale_entitlements",
  "status": "verification_pending",
  "approvedChange": "IAM-2026-0417",
  "occurredAt": "2026-11-23T07:00:00Z"
}
~~~

Trạng thái `verification_pending` **không phải bằng chứng đã thu hồi**. Chỉ sau khi kiểm tra trạng thái cloud target, hệ thống mới có thể đánh dấu verified hoặc ghi exception/failed với owner xử lý.

### 14.4. Policy dùng chung có bị xóa không?

Không nên xóa policy `learning-dev-log-read` nếu những kỹ sư khác vẫn dùng nó hợp lệ. Phải tách **policy definition** khỏi **assignment của Lan**. Ngược lại, nếu policy được tạo riêng cho một tích hợp đã ngừng sử dụng, cần retire policy và thu hồi mọi đường phụ thuộc, theo quy trình thay đổi có kiểm chứng.

## 15. Các anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Cấp `Action: "*"`, `Resource: "*"` hoặc quyền Administrator cho automation | Workload bị xâm nhập có toàn quyền trên phạm vi lớn | Role riêng, action/resource tối thiểu, credential ngắn hạn |
| Chỉ xét role name, bỏ qua scope | “Reader” bị gắn ở cấp tổ chức thay vì project | So principal – role – scope – conditions khi phê duyệt |
| Chỉ kiểm tra IdP group | Bỏ sót direct grants, local user và resource policy | Inventory quyền từ mọi cloud target |
| Trust federation quá rộng | Token từ nguồn không được duyệt có thể nhận role | Ràng buộc issuer, audience, subject và môi trường |
| Dùng tag người dùng tự sửa làm điều kiện bảo mật | Chủ thể thao túng thuộc tính để vượt quyền | Quản lý nguồn thuộc tính, hạn chế quyền sửa tag |
| Xem SCP/permissions boundary là cơ chế cấp quyền | Hiểu sai Allow/Deny và điều tra thất bại | Xác định lớp nào cấp quyền, lớp nào giới hạn |
| Nhầm Azure Policy với Azure RBAC | Có baseline nhưng không kiểm soát principal | Tách governance policy và IAM role assignment |
| Nhầm ID token với access token | API kiểm tra sai đối tượng và mục đích token | Xác thực token đúng loại, issuer, audience, thời hạn |
| Chỉ review policy definition, không review assignment | Role chuẩn an toàn nhưng được cấp sai người | Review entitlement theo người, owner, scope, hạn dùng |
| Xóa role/policy dùng chung khi một người nghỉ | Làm gián đoạn người và dịch vụ khác | Thu hồi assignment/credential của principal cụ thể |
| Tin API revoke thành công là đã an toàn | Quyền khác hoặc session vẫn còn | Đọc lại actual/effective access và lưu kết quả |
| Chỉnh production console không qua quản lý phiên bản | Policy drift và thiếu audit | Policy-as-code, giám sát thay đổi và đối soát |
| Dùng key tĩnh lâu dài cho CI/CD | Secret rò rỉ hoặc còn sau khi kết thúc pipeline | Federation, secret manager, rotation và owner |
| Không kiểm thử Deny | Policy cấp đúng thao tác cần nhưng vẫn quá rộng | Kiểm thử cả đường Allow mong muốn và Deny bắt buộc |

## 16. Chỉ số vận hành và kiểm toán

| Chỉ số | Cách dùng |
| --- | --- |
| **Tỷ lệ policy có owner, mục đích và kỳ review** | Đánh giá mức độ kiểm soát danh mục policy |
| **Số policy hoặc role cấp quyền rộng** | Ưu tiên thu hẹp wildcard và quyền đặc biệt |
| **Số stale grants sau Mover/Leaver** | Đo quyền truy cập tồn dư theo cloud target |
| **P95 thời gian thu hồi entitlement** | Từ lúc sự kiện JML có hiệu lực đến khi xác minh đã thu hồi |
| **Tỷ lệ JML hoàn tất VERIFIED** | Tránh tính những yêu cầu chỉ được gửi hoặc áp một phần |
| **Số sự kiện policy drift** | Xác định thay đổi ngoài pipeline/IaC hoặc sai khác cấu hình |
| **Tỷ lệ privileged access có thời hạn** | Đo mức độ kiểm soát quyền cao |
| **Số trust cross-account/federation chưa có owner** | Phát hiện đường truy cập ngoài dự kiến |
| **Số service accounts/key chưa được rà soát** | Giảm credential mồ côi và quyền workload tồn dư |
| **Tỷ lệ thay đổi policy có kết quả kiểm thử** | Đánh giá chất lượng quy trình thay đổi |

Đo theo **provider, môi trường production/non-production, loại principal và độ nhạy cảm quyền**. Một quyền sửa IAM tồn dư trên production nghiêm trọng hơn quyền chỉ đọc hạn chế ở sandbox.

### 16.1. Bằng chứng audit nên lưu

- Nguồn sự kiện JML và identity ID ổn định; trạng thái và ngày hiệu lực.
- Policy/role/binding ID, phiên bản, scope, principal, owner và người phê duyệt.
- Nội dung trước/sau và lý do thay đổi, ticket, kết quả policy validation.
- Ai/automation nào triển khai, thời điểm, kết quả API, log thao tác.
- Kết quả readback, kiểm tra effective access, thời gian verified.
- Ngoại lệ, phạm vi tác động, owner khắc phục, hạn cuối và lịch sử đóng ngoại lệ.
- Dữ liệu phục vụ điều tra được giữ theo chính sách lưu trữ và quyền truy cập phù hợp.

Không nên ghi token, private key hoặc secret thô vào log chỉ để tạo bằng chứng. Lưu định danh/metadata đủ để truy vết thay đổi và bảo vệ dữ liệu nhạy cảm trong log.

## 17. Bài tập thực hành và câu hỏi tự kiểm tra

### Bài tập 1: Policy chỉ đọc tài nguyên development

Yêu cầu: Một nhóm nhà phát triển cần đọc log của một ứng dụng tại project dev và bị chặn đọc log production.

Hãy xây một tài liệu chính sách nghiệp vụ gồm principal, action, resource, điều kiện, owner, thời hạn review và các bài thử Allow/Deny. Sau đó chọn cơ chế tương ứng trong cloud provider mục tiêu. Cần giải thích cách xử lý khi người dùng chuyển đội.

**Gợi ý:** Nhóm qua IdP chỉ là một đường cấp; rà soát grant trực tiếp, quyền kế thừa và resource policy. Kết quả đúng phải cho phép tác vụ cần và từ chối những hành động ngoài phạm vi.

### Bài tập 2: SCP có cấp quyền không?

Một AWS account áp SCP cho phép một tập hành động, nhưng role của người dùng không có identity policy cho thao tác tương ứng. Người quản trị khẳng định SCP đã cấp quyền.

**Đáp án:** Kết luận đó sai. SCP đóng vai trò giới hạn quyền tối đa trong phạm vi hỗ trợ và **không tự tạo quyền Allow** cho principal. Cần có đường quyền hợp lệ từ các loại policy liên quan, đồng thời không bị chặn bởi giới hạn hoặc explicit deny áp dụng.

### Bài tập 3: Azure Policy và Azure RBAC

Subscription production có Azure Policy yêu cầu tag `costCenter`. Một kiểm toán viên cần xem cấu hình VM nhưng không được sửa hoặc xóa VM. Có thể chỉ tạo Azure Policy để cấp quyền cho họ không?

**Đáp án:** Không. Azure Policy quản trị trạng thái tài nguyên; cần Azure RBAC role assignment phù hợp tại scope được duyệt, ví dụ quyền đọc thích hợp, rồi xác minh những hành động ghi bị từ chối.

### Bài tập 4: Pipeline bị xóa nhưng trust còn tồn tại

Repository CI/CD cũ đã bị vô hiệu hóa, nhưng cloud role vẫn tin cậy issuer/subject quá rộng; một repository khác có thể nhận token hợp lệ.

**Hướng xử lý:** Thu hẹp hoặc xóa trust không còn nhu cầu, thu hồi credential liên quan, kiểm tra role permissions và thực hiện thử nghiệm truy cập theo quy trình. Đóng vòng đời pipeline phải bao gồm policy và trust của workload.

### Bài tập 5: Policy drift trong production

Pipeline IaC định nghĩa role đọc log. Một kỹ sư đã sửa role trong console để thêm quyền xóa log. Sự kiện Mover sau đó chỉ đối soát group membership.

**Câu hỏi:** Hệ thống đã an toàn chưa?

**Đáp án:** Chưa. Cần xác định drift so với bản policy được duyệt, kiểm tra ai sửa/đã sử dụng quyền mới, khôi phục hoặc thay đổi qua quy trình có phê duyệt, rồi đối soát effective access và lưu audit.

## 18. Checklist thiết kế và vận hành cloud policy

1. **Đúng loại policy:** Đang xử lý IAM access, trust, guardrail, Conditional Access hay resource configuration?
2. **Đúng principal:** Có identity ID ổn định, owner và nguồn thẩm quyền phù hợp cho người/workload?
3. **Đúng action:** Quyền được giới hạn cho tác vụ cần thực hiện; kiểm tra đường nâng đặc quyền.
4. **Đúng resource/scope:** Xác định account, subscription, project và tài nguyên cụ thể; xem quyền kế thừa.
5. **Đúng condition:** Chỉ dùng thuộc tính/ngữ cảnh có nguồn tin cậy và khả năng kiểm tra trên cloud provider.
6. **Đúng trust:** Với federation, kiểm soát issuer, audience, principal và subject/claims phù hợp.
7. **Đúng JML:** Joiner cấp quyền đã duyệt; Mover thu hồi quyền cũ; Leaver xử lý mọi đường truy cập liên quan.
8. **Đúng workload:** Service account, managed identity, pipeline có policy và vòng đời độc lập với nhân viên.
9. **Đúng phê duyệt:** Có owner, lý do nghiệp vụ, review và hạn dùng cho quyền nhạy cảm.
10. **Đúng thay đổi:** Policy-as-code, kiểm tra cú pháp/semantics, test Allow/Deny, review và rollback.
11. **Đúng kiểm chứng:** Readback cấu hình và kiểm tra effective access; theo dõi drift và lỗi triển khai từng target.
12. **Đúng kiểm toán:** Lưu người thực thi, diff trước/sau, kết quả thực tế, ngoại lệ và bằng chứng thu hồi.

## 19. Tổng kết

**Cloud policy** giúp diễn đạt và thực thi quy tắc truy cập tài nguyên cloud, nhưng mỗi nền tảng có những loại và lớp chính sách riêng. **AWS IAM** kết hợp identity/resource policies, trust và các giới hạn như permissions boundary hoặc SCP; **Azure** phân biệt Azure RBAC với Azure Policy và Entra Conditional Access; **Google Cloud** dùng IAM allow bindings cùng những cơ chế deny và giới hạn tổ chức phù hợp.

Trong quản lý vòng đời danh tính, chính sách phải gắn với **nguồn danh tính đáng tin cậy**, cơ chế **IdP/SSO/SCIM hoặc provisioning**, cách tổ chức quyền theo **RBAC/ABAC**, và vòng đời **service account/workload**. Mọi sự kiện **Joiner–Mover–Leaver** phải dẫn đến trạng thái quyền đúng tại cloud target. Đặc biệt, để giảm **quyền truy cập tồn dư**, cần phát hiện policy drift, grant/trust không còn hợp lệ, credential và phiên còn hiệu lực; chỉ kết luận hoàn tất khi **quyền thực tế đã được xác minh và có bằng chứng kiểm toán**.
