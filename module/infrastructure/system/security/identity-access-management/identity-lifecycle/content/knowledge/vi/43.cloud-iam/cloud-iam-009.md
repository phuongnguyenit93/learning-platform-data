# Cloud privilege escalation

**Chương:** Cloud IAM  
**Chủ đề:** Cloud privilege escalation (nâng đặc quyền trong môi trường đám mây)  
**Phạm vi:** Nhận diện, ngăn chặn, phát hiện, rà soát và xử lý các đường nâng quyền trực tiếp hoặc gián tiếp trên AWS, Microsoft Azure và Google Cloud; gắn với quản lý vòng đời danh tính **Joiner–Mover–Leaver (JML)**.

> Bài học tập trung vào **thiết kế phòng thủ, đánh giá quyền và kiểm toán**. Những tình huống mô tả khả năng nâng đặc quyền là mô hình rủi ro để rà soát, không phải quy trình khai thác hệ thống. Việc kiểm chứng chỉ thực hiện trên tài khoản, tài nguyên và môi trường được cho phép.

## 1. Cloud privilege escalation là gì?

**Privilege escalation** xảy ra khi một principal (người dùng, ứng dụng hoặc workload) có thể đạt được quyền **vượt quá phạm vi đã được phê duyệt** thông qua cấu hình IAM, mối quan hệ tin cậy, credential, service account, pipeline hoặc các thành phần khác của môi trường cloud.

Ví dụ: một tài khoản kỹ sư chỉ được phép quản lý ứng dụng development, nhưng có quyền chỉnh sửa cấu hình triển khai của một workload đang chạy bằng identity có quyền quản trị production. Khi ấy, người đó có thể ảnh hưởng tới môi trường production **gián tiếp**, dù role trực tiếp trên tài khoản kỹ sư không mang tên Administrator.

Cần phân biệt hai trường hợp:

1. **Nâng quyền được ủy quyền (authorized elevation):** Người trực vận hành yêu cầu quyền xử lý sự cố production, được phê duyệt, xác thực mạnh, có thời hạn và lưu audit; đây là hoạt động quản trị hợp lệ nếu tuân thủ chính sách.
2. **Nâng quyền trái phép hoặc ngoài phạm vi (unauthorized privilege escalation):** Chủ thể tự nhận thêm quyền, lợi dụng một đường tin cậy quá rộng hoặc thay đổi thành phần có quyền cao mà không được phê duyệt.

Cloud privilege escalation là vấn đề **Identity and Access Management (IAM)** vì quyền không chỉ được định nghĩa bằng một role name. Nó phụ thuộc vào **ai kiểm soát role, policy, credential, source code, tài nguyên đang mang identity và các điều kiện của phiên**.

### 1.1. Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt quyền trực tiếp, quyền gián tiếp, quyền hiệu lực và quyền có thể dẫn tới quyền khác.
- Nhận diện những nhóm rủi ro như sửa IAM policy, sửa trust, impersonation, quản lý credential, triển khai workload quyền cao và cross-account/cross-tenant access.
- Hiểu các khác biệt quan trọng giữa AWS IAM, Azure RBAC/Microsoft Entra và Google Cloud IAM.
- Thiết kế kiểm soát **least privilege, separation of duties (SoD), RBAC/ABAC, JIT/PAM** và federation an toàn.
- Kết nối các kiểm soát này với quy trình **Joiner–Mover–Leaver** của nhân viên, đối tác và service account.
- Đề xuất kiểm thử phòng thủ, tín hiệu phát hiện, cách xử lý sự cố và chứng cứ kiểm toán.

## 2. Các khái niệm nền tảng

| Khái niệm | Ý nghĩa | Cần kiểm tra điều gì? |
| --- | --- | --- |
| **Identity** | Danh tính được quản lý từ HRIS, IdP, cloud hoặc workload registry | Có hợp lệ, có owner, còn trong vòng đời không? |
| **Principal** | Chủ thể thực hiện yêu cầu được IAM đánh giá | Có thể là user, role session, service account hoặc managed identity |
| **Role** | Thực thể hoặc tập quyền theo mô hình provider | Có thể làm những action nào, tại resource nào? |
| **Permission / policy** | Quy tắc cho phép, từ chối hoặc giới hạn hành động | Có quyền quản trị quyền hoặc credential không? |
| **Trust** | Quy tắc xác định danh tính/issuer nào được nhận hoặc sử dụng quyền | Có đang chấp nhận principal nguồn quá rộng không? |
| **Role assignment / IAM binding** | Liên kết principal với role tại scope | Cấp trực tiếp hay kế thừa? Hạn dùng là gì? |
| **Credential/session** | Bằng chứng để sử dụng quyền trong một khoảng thời gian | Có thể làm mới, thu hồi và truy vết không? |
| **Impersonation / role assumption** | Chủ thể nguồn thực hiện hành động bằng principal/role khác khi được phép | Principal đích có quyền mạnh hơn hay không? |
| **Effective access** | Quyền thực tế sau khi xét các lớp chính sách và điều kiện | Có đường gián tiếp dẫn tới quyền lớn hơn không? |
| **Entitlement** | Quyền truy cập đang cấp cho danh tính | Có phù hợp chức trách và trạng thái JML không? |

**Role được gán** chưa chắc là **quyền hiệu lực**: deny policy, permissions boundary, scope hoặc điều kiện có thể chặn thao tác. Nhưng điều ngược lại cũng quan trọng: principal không có role Administrator trực tiếp vẫn có thể **đạt quyền quản trị qua đường gián tiếp**.

### 2.1. Ví dụ direct access và indirect access

Một principal có:

- Quyền trực tiếp: đọc log của dịch vụ Analytics.
- Quyền bổ sung: sửa cấu hình pipeline triển khai Analytics production.
- Pipeline đó sử dụng một workload identity có thể cập nhật ứng dụng production.

Trong sơ đồ quyền, năng lực sửa pipeline tạo một **đường ảnh hưởng gián tiếp** tới quyền của workload. Đây là tín hiệu cần kiểm tra **quyền sửa pipeline, approval, review mã nguồn, môi trường CI, trust và quyền của workload identity**.

Không nên kết luận tự động rằng bất kỳ người sửa repository nào cũng có mọi quyền của pipeline: còn phụ thuộc branch protection, workflow approval, điều kiện OIDC, runner isolation và cơ chế triển khai thực tế. Nhưng phải coi đó là **đường quyền tiềm năng** cần được phân tích.

## 3. Đồ thị quyền: từ principal đến hành động nhạy cảm

Một mô hình hữu ích cho security review là **đồ thị quyền (privilege graph)**. Nút biểu diễn principal, group, role, credential, service, resource; cạnh biểu diễn khả năng gán role, assume role, sửa policy, dùng service account hoặc sửa cấu hình workload.

~~~mermaid
flowchart TD
    U["User / workload nguồn"] --> G["Group / direct IAM grant"]
    G --> R["Role có quyền trực tiếp"]
    R --> API["Cloud API cho phép"]
    R --> P["Năng lực thay đổi IAM policy/trust"]
    R --> S["Năng lực sử dụng identity của workload"]
    R --> C["Năng lực truy cập credential nhạy cảm"]
    P -.-> HIGH["Principal / role đặc quyền cao"]
    S -.-> HIGH
    C -.-> HIGH
    HIGH --> PROD["Thao tác nhạy cảm production"]
    GUARD["Least privilege, boundaries, deny, approval, JIT"] -.-> P
    GUARD -.-> S
    GUARD -.-> C
~~~

Các cạnh nét đứt thể hiện **khả năng tạo đường truy cập** cần được kiểm tra, không có nghĩa IAM tự động cho phép mọi chuyển đổi đó.

### 3.1. Bốn câu hỏi của một phép đánh giá

1. **Principal hiện có gì?** Danh tính, group, role, policy, resource access và credential.
2. **Principal có thể thay đổi gì?** IAM grants, trust, workload configuration, service account, secret, pipeline.
3. **Nếu thay đổi được, quyền mới là gì?** Principal hoặc workload đích có quyền nào mà nguồn chưa được phê duyệt?
4. **Kiểm soát nào thực sự chặn được đường đó?** Phê duyệt độc lập, scope, điều kiện, deny, runtime isolation, tính toàn vẹn deployment hay cơ chế provider?

Một đánh giá chỉ liệt kê số role mà không trả lời câu hỏi thứ hai thường bỏ sót các đường nâng đặc quyền.

### 3.2. Ba lớp cần tách riêng

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Authentication** | Ai đang yêu cầu? | IdP, MFA, SAML, OIDC, instance identity |
| **Authorization** | Yêu cầu nào được phép? | AWS IAM policy, Azure RBAC, Google Cloud IAM |
| **Control plane / delegation** | Ai có quyền làm thay đổi danh tính, quyền hoặc workload thực thi? | Sửa trust, gán role, quản trị CI/CD |

Phòng thủ hiệu quả phải bao phủ cả ba. SSO tốt nhưng policy quá rộng vẫn rủi ro; policy hẹp nhưng pipeline hoặc workload identity bị chiếm cũng có thể gây sự cố.

## 4. Phân loại các đường nâng đặc quyền

| Nhóm rủi ro | Dấu hiệu cấu hình | Tác động tiềm năng |
| --- | --- | --- |
| **Policy mutation** | Principal có thể sửa/chèn policy cho chính mình hoặc role được sử dụng | Mở action/resource ngoài quyền được phê duyệt |
| **Role/assignment administration** | Có thể cấp role cao hơn cho user, group, service principal | Nhận hoặc chuyển quyền đặc biệt |
| **Trust expansion** | Có thể thay điều kiện issuer/principal được phép assume role | Cho nguồn không được duyệt nhận credential/role |
| **Impersonation/delegation** | Có thể hành động dưới một service account/role có quyền cao | Vượt giới hạn trực tiếp của principal nguồn |
| **Credential minting** | Có thể tạo key, token hoặc secret dùng identity mạnh hơn | Duy trì quyền truy cập ngoài đường thông thường |
| **Workload configuration control** | Có thể triển khai/sửa code hoặc runtime đang sử dụng identity mạnh | Ảnh hưởng resource bằng quyền của workload |
| **CI/CD supply-chain control** | Có thể sửa workflow/repository/runner có cloud role | Sử dụng quyền của pipeline ngoài quy trình được duyệt |
| **Cross-account/cross-tenant trust** | Trust hoặc resource policy chấp nhận nguồn quá rộng | Mở quyền vượt ranh giới tổ chức |
| **Resource policy manipulation** | Có thể sửa ACL/policy của bucket, key, secret, service | Tạo đường truy cập dữ liệu hoặc principal khác |
| **Recovery/break-glass misuse** | Credential khẩn cấp không có owner, review hoặc cảnh báo | Đi vòng quy trình phê duyệt thường ngày |

Đây là **nhóm kiểm tra phòng thủ**, không phải bằng chứng hệ thống có thể bị khai thác. Mức độ rủi ro cụ thể phải dựa trên cách provider đánh giá quyền, scope, điều kiện, role đích và khả năng thay đổi thành phần liên quan.

### 4.1. Vertical và horizontal escalation

**Vertical escalation** là tăng lên mức quyền cao hơn, ví dụ từ đọc log sang quyền quản trị IAM. **Horizontal escalation** là vượt qua ranh giới giữa những principal hoặc tài nguyên có mức quyền tương đương nhưng khác chủ sở hữu, ví dụ workload A dùng được credential của workload B.

Trong môi trường cloud, horizontal access có thể trở thành vertical escalation nếu principal bị truy cập ngang đang mang role mạnh hơn. Vì vậy cần phân tích **định danh đích và phạm vi quyền**, không chỉ mô tả loại hành vi.

## 5. Sai lầm: đánh giá quyền chỉ bằng role name

Một role tên **Reader** không cho biết đầy đủ rủi ro nếu không biết scope, các permission thực tế, quyền dữ liệu, điều kiện và các đường cấp quyền khác. Tương tự, một role tên **Deployer** có thể được phép sửa môi trường production đang gắn managed identity quyền cao.

### 5.1. Ma trận rủi ro theo năng lực

| Năng lực | Điểm cần xác minh |
| --- | --- |
| Đọc metadata | Có lộ cấu trúc hoặc dữ liệu nhạy cảm không? Scope có quá rộng không? |
| Đọc secret | Secret có cấp credential của principal mạnh hơn không? |
| Tạo/sửa workload | Workload có identity nào? Ai được thay runtime identity? |
| Gán/sửa role | Principal có thể tạo quyền cho chính mình không? |
| Sửa IAM trust | Có thể thêm issuer/principal ngoài danh sách được duyệt không? |
| Tạo service account key | Key thuộc service account có quyền gì? Ai giữ và xoay key? |
| Thay Git workflow hoặc runner | Có thể kích hoạt deployment role production không? |
| Thay cấu hình logging | Có thể che dấu hoạt động thay đổi quyền không? |

Đánh giá phải xem **tổ hợp permissions**. Một quyền quản lý workload tự nó có thể hợp lệ; một quyền sử dụng identity đặc quyền cũng có thể hợp lệ trong phạm vi khác; nhưng kết hợp hai quyền trong cùng một principal có thể làm xuất hiện đường quyền ngoài dự kiến.

### 5.2. Desired, assigned và effective access

~~~text
desiredAccess  = quyền được phê duyệt theo nhiệm vụ và trạng thái JML
assignedAccess = quyền gắn qua role, group, binding, trust, policy
effectiveAccess = quyền có thể thực thi sau khi xét scope, condition, deny
potentialEscalationPaths = khả năng thay đổi hoặc sử dụng principal/quyền khác

ReviewResult = compare(
    desiredAccess,
    assignedAccess,
    effectiveAccess,
    potentialEscalationPaths
)
~~~

Đây là **giả mã tư duy**, không phải công cụ tính quyền đa cloud. Một role có thể bị chặn bởi guardrail nhưng vẫn là grant cần quản trị; nếu guardrail bị đổi, grant có thể trở nên có hiệu lực.

## 6. Trust, federation và nguy cơ mở rộng quyền

**Federation** cho phép IdP hoặc workload issuer cung cấp bằng chứng danh tính để cloud cấp phiên hoặc ánh xạ principal. Quan hệ trust kém giới hạn có thể làm tăng số chủ thể có thể nhận một role mạnh, dù permissions policy không thay đổi.

### 6.1. Điều kiện trust cần hiểu

- **Issuer:** Token/assertion được phát bởi nguồn nào?
- **Audience/recipient:** Bằng chứng được phát cho dịch vụ nào?
- **Subject:** Người/workload nào được mô tả?
- **Claims bổ sung:** Repository, branch, environment, tenant, group hoặc thuộc tính khác.
- **Credential validity:** Chữ ký, thời hạn, correlation/replay controls phù hợp.
- **Cloud role mapping:** Principal được gắn/được phép nhận role nào tại scope nào?

**Token ký đúng không đồng nghĩa token có đủ tư cách nhận role**. Phải đánh giá issuer, audience, subject và điều kiện trust theo cơ chế provider, đồng thời bảo vệ hệ thống phát token và những nguồn thuộc tính được sử dụng.

### 6.2. Workforce và workload có đường rủi ro khác nhau

| Workforce federation | Workload federation |
| --- | --- |
| Người dùng được xác thực qua IdP/SSO, SAML hoặc OIDC | Job/Pod/runtime được xác thực qua issuer hoặc managed identity |
| Rủi ro do group mapping sai, guest hết hạn, thiếu MFA | Rủi ro do repo/branch/environment rộng, token trong runtime, runner bị chiếm |
| JML theo HRIS/contractor registry | JML theo service catalog, repository và deployment registry |
| Quyền tương ứng với công việc và phê duyệt | Quyền tương ứng với tác vụ của service/pipeline |
| Session người dùng cần được quản lý sau Leaver | Credential workload cần được thu hồi khi workload retire |

Khi một người đổi nhóm, không nên chỉ sửa IdP group rồi giả định cloud role assignment trực tiếp đã biến mất. Khi một pipeline đổi repository, không nên chỉ cấp trust mới mà giữ trust cũ vô thời hạn.

### 6.3. Confused deputy trong cross-account

Một dịch vụ bên thứ ba được khách hàng tin cậy để thực hiện tác vụ thay mặt nhiều tổ chức có thể vô tình thực hiện yêu cầu trong ngữ cảnh sai nếu không phân biệt khách hàng. Trong những quan hệ AWS cross-account phù hợp, **external ID** có thể là một cơ chế hỗ trợ giảm rủi ro confused deputy. Đây là vấn đề **kiểm tra trust và ngữ cảnh**, không thay thế least privilege ở role đích.

## 7. AWS: các nhóm quyền cần rà soát đặc biệt

Trong AWS, quyền có thể đến từ identity-based policy, resource-based policy, IAM role trust, STS session và một số lớp giới hạn như permissions boundary hoặc **AWS Organizations Service Control Policy (SCP)**.

**SCP và permissions boundary không tự cấp quyền.** Chúng đặt giới hạn theo mô hình đánh giá hỗ trợ. Trong các trường hợp áp dụng, **explicit deny** có thể chặn hành động dù nơi khác có Allow. Tuy nhiên effective permissions của AWS có các trường hợp đặc thù; cần dùng phân tích và tài liệu IAM chính thức phù hợp với dịch vụ và loại principal.

### 7.1. Policy và role administration

Những năng lực cần cảnh báo khi xuất hiện ở principal không có trách nhiệm quản trị IAM:

| Nhóm AWS IAM capability | Câu hỏi kiểm toán |
| --- | --- |
| Tạo/chỉnh policy hoặc thay default policy version | Principal có thể làm role đang dùng nhận quyền rộng hơn không? |
| Gắn/gỡ managed policy hoặc inline policy | Có thể cấp thêm quyền cho chính mình hoặc principal được kiểm soát không? |
| Sửa trust policy của role | Có thể mở principal được assume role không? |
| Thay permissions boundary | Có thể loại bỏ một lớp hạn chế quyền không? |
| Quản lý group/role membership | Có thể đưa user/workload không hợp lệ vào nhóm quyền cao không? |
| Quản lý credential | Có thể tạo hoặc thay access key của principal có quyền khác không? |

Không xem mọi quyền IAM administration đều là bất thường. Đội Platform Security có thể cần chúng để vận hành; vấn đề là **scope, chủ thể, approval, tách nhiệm vụ và bằng chứng thay đổi**.

### 7.2. IAM role, iam:PassRole và dịch vụ thực thi

Trong AWS, **iam:PassRole** là permission liên quan tới việc chuyển một role cho dịch vụ AWS hỗ trợ. Nếu principal vừa có quyền cấu hình/chạy một tài nguyên tính toán phù hợp, vừa có thể chuyển cho nó một role quyền cao, cần đánh giá khả năng workload sử dụng quyền của role đó.

**Điểm chính xác quan trọng:** iam:PassRole **không phải một API event độc lập**. Trong giám sát cần xem API tạo/sửa tài nguyên dịch vụ có trường role, hành động IAM liên quan và các event sử dụng role, thay vì chờ một CloudTrail event có tên PassRole.

Các lớp kiểm soát:

1. Giới hạn những role mà principal được phép pass theo resource và điều kiện được hỗ trợ.
2. Giới hạn service hoặc môi trường có thể nhận role.
3. Giới hạn quyền tạo/sửa workloads sử dụng role đặc quyền.
4. Ghi nhận approval khi gắn role production vào tài nguyên.
5. Kiểm tra cả identity của workload và role của người triển khai.

Không kết luận rằng chỉ có iam:PassRole là đủ để nhận toàn bộ quyền role; phải xét khả năng tạo/điều khiển dịch vụ đích và cơ chế sử dụng identity thực tế.

### 7.3. AssumeRole, role chaining và trust

**AssumeRole** hoặc federation qua SAML/OIDC có thể cấp **temporary credentials** cho role khi principal nguồn đủ điều kiện. Một đường từ principal thấp đến role cao cần được kiểm tra qua:

- Trust policy của role đích.
- Quyền của principal nguồn theo cơ chế cần thiết.
- Session policies, boundaries và các giới hạn liên quan.
- Đường cấp quyền hoặc role trung gian.
- Resource-based policy hoặc cross-account access đi kèm.

Trong review, phải phân biệt **trust được cấu hình** với **việc phiên thực sự có thể assume role**. Kiểm thử có kiểm soát hoặc công cụ phân tích provider cần được dùng để xác nhận.

### 7.4. Access key và credential management

IAM user access key dài hạn có thể tạo tồn dư nếu người tạo nghỉ việc hoặc repository bị xóa. Ưu tiên role/STS và identity do runtime quản lý khi phù hợp; song việc cấp temporary credentials vẫn phải giới hạn principal nguồn, role đích và scope.

Nếu một principal có quyền quản lý key của danh tính quyền cao, cần coi đó là đường rủi ro nâng quyền và áp phân quyền chặt. Không ghi key, session token hoặc secret access key vào audit log.

### 7.5. AWS workload review

EC2 instance profile, Lambda execution role, ECS task role, EKS IRSA/Pod Identity và CI/CD web identity đều cần được review:

| Thành phần | Kiểm tra |
| --- | --- |
| Instance/task/execution role | Ứng dụng có thực sự cần mọi action/resource không? |
| Role trust | Chỉ runtime/service/issuer được duyệt có thể nhận role không? |
| Deployment permissions | Ai sửa code/config của workload dùng role này? |
| Metadata endpoint | Workload có bị truy cập nhầm credential của node/instance không? |
| Cross-account delegation | Trust có scope và owner tương ứng hợp đồng không? |
| Audit | Role assumption và thay đổi cấu hình có được ghi và giám sát không? |

## 8. Azure: RBAC, Microsoft Entra và workload identity

Trong Azure, **role assignment** liên kết security principal, role definition và scope. Quyền có thể được kế thừa từ management group, subscription hoặc resource group xuống tài nguyên con.

~~~text
Azure RBAC assignment
    = (principal, roleDefinition, scope)

Kiểm tra đồng thời:
    Quyền trên management plane
    Quyền trên data plane
    Role ở scope cha được kế thừa
    Conditions / deny assignments khi được hỗ trợ
    Quyền ở Microsoft Entra và hệ thống ứng dụng liên quan
~~~

**Microsoft Entra directory roles** và **Azure RBAC roles** là hai hệ vai trò khác nhau, dù có một số mối liên hệ hoặc luồng quản trị giữa chúng. Không coi Global Administrator, Owner, Contributor, User Access Administrator là các quyền tương đương.

### 8.1. Role assignment administration

Những principal có quyền tạo/sửa Azure RBAC role assignment trong scope nhạy cảm cần được kiểm soát như đặc quyền cao. **Owner** hoặc **Role Based Access Control Administrator**, **User Access Administrator** theo phạm vi và điều kiện áp dụng có thể mang quyền quản lý việc phân quyền. Không nên cấp role này chỉ để một workload đọc dữ liệu hoặc triển khai một dịch vụ thông thường.

Khi review:

- Ai là principal có quyền quản lý assignment tại scope?
- Role assignment có ràng buộc điều kiện hoặc cơ chế PIM/JIT không?
- Ai có thể cấp quyền cho chính mình hoặc cho workload do mình kiểm soát?
- Có quyền kế thừa từ scope cha rộng hơn mục tiêu không?
- Có sự kiện tạo/xóa role assignment không đi qua quy trình approved IaC không?

### 8.2. Contributor không đồng nghĩa Owner

Azure **Contributor** có quyền quản lý nhiều tài nguyên ở scope được cấp nhưng thường **không có quyền gán Azure RBAC role trực tiếp** như Owner. Tuy nhiên, tùy dịch vụ và các permissions cụ thể, khả năng thay cấu hình ứng dụng/compute có thể liên quan tới identity của workload, dữ liệu hoặc cơ chế thực thi quyền cao.

Vì vậy không nên kết luận “Contributor chắc chắn được cấp mọi role”, nhưng cũng không kết luận “Contributor không có rủi ro nâng đặc quyền”. Phải phân tích **resource có managed identity, cơ chế triển khai và quyền của identity được gắn**.

### 8.3. Managed identity và service principal

**System-assigned managed identity** thường gắn với vòng đời một tài nguyên. **User-assigned managed identity** có vòng đời độc lập và có thể được sử dụng bởi nhiều resource được hỗ trợ.

Các câu hỏi phòng thủ:

1. Ai có thể gắn hoặc thay identity trên tài nguyên?
2. Identity được gắn có RBAC role nào và tại scope nào?
3. Ai có quyền sửa code, configuration hoặc extensions của workload đang dùng identity?
4. Application/service principal có client secret, certificate hay federated credentials còn hiệu lực không?
5. Khi workload retire, RBAC assignments và user-assigned identity có còn tồn tại không?

**Chia sẻ một user-assigned managed identity quyền rộng cho nhiều dịch vụ** có thể làm lan rộng blast radius. Tách identity theo nhiệm vụ thường giúp cô lập và thu hồi quyền dễ hơn.

### 8.4. Microsoft Entra application và federation

Quyền tạo/sửa application credentials, service principal hoặc federated identity credential có thể ảnh hưởng đường xác thực của một ứng dụng có đặc quyền. Review cần nối **quyền quản trị danh tính ở Entra** với **role và resource access của service principal** ở Azure.

Không kết luận một quyền quản trị application trong Entra mặc nhiên cho phép quản trị mọi Azure resource; đường rủi ro phụ thuộc **quyền thật của application/service principal đích** và quyền được quản trị ở directory.

### 8.5. Privileged Identity Management và Conditional Access

**Microsoft Entra Privileged Identity Management (PIM)** có thể hỗ trợ eligibility, activation có thời hạn, approval và các điều kiện cho những role được hỗ trợ. **Conditional Access** có thể quản trị yêu cầu xác thực, thiết bị hoặc ngữ cảnh đăng nhập theo cấu hình phù hợp.

**PIM/JIT không thay thế least privilege** và không mặc nhiên hủy ngay mọi token đã phát khi thời hạn activation kết thúc. Cần kiểm tra role assignment, thời hạn phiên, refresh và hành vi dịch vụ đích.

## 9. Google Cloud: IAM binding, service account và delegation

Google Cloud IAM dùng **role bindings** trên organization, folder, project hoặc resource hỗ trợ để cấp permissions cho principal. Ngoài role trực tiếp, cần xem cả **IAM Conditions, deny policies, Organization Policy constraints** và những giới hạn khác trong phạm vi áp dụng.

### 9.1. Quyền thay IAM policy

Nếu một principal có thể thay đổi IAM policy tại resource quan trọng, cần kiểm tra khả năng cấp role mới cho một principal được kiểm soát. Ví dụ quyền quản lý policy cần được bảo vệ riêng khỏi những workload chỉ cần đọc log.

Hãy review:

- Phạm vi set IAM policy: organization, folder, project hay resource?
- Principal có được phép thêm/bớt bindings và nâng role không?
- Policy version, điều kiện và guardrail có được bảo vệ không?
- Ai được phê duyệt và triển khai thay đổi policy qua IaC?
- Có log của policy update và readback sau thay đổi không?

### 9.2. Service account impersonation

Đây là đường gián tiếp quan trọng. Một principal nguồn có thể được gán quyền để **nhận token hoặc impersonate một service account** theo cơ chế hỗ trợ. Khi đánh giá, phải xét:

1. Quyền của principal nguồn để thực hiện hành vi impersonation cụ thể.
2. Service account đích có những role/bindings nào.
3. Resource scope và các điều kiện của quyền đích.
4. Ai được phép tạo hoặc thay đổi quyền impersonation.
5. Log phát token và sử dụng API bằng identity đích.

**Service Account Token Creator** và **Service Account User** là các role có ý nghĩa khác nhau. Quyền **Service Account User** hỗ trợ một số trường hợp gắn/chạy workload bằng service account; nó **không tự đồng nghĩa** quyền tạo access token như Token Creator. Nhưng nếu principal đồng thời có quyền cấu hình workload chạy dưới service account đó, có thể xuất hiện đường gián tiếp cần review.

### 9.3. Tạo service account key

User-managed service account key có thể tồn tại lâu và bị sao chép ngoài cloud. Nếu principal không có trách nhiệm quản trị credential mà có thể tạo key của một service account quyền cao, đây là rủi ro cần xử lý.

Biện pháp phòng thủ:

- Giới hạn người được quản lý service account credentials.
- Ưu tiên attached identity, workload federation hoặc impersonation bằng token ngắn hạn khi được hỗ trợ.
- Áp constraint/guardrail phù hợp để hạn chế tạo key nếu chính sách tổ chức cho phép.
- Phát hiện key mới, ghi owner, purpose và vòng đời rotation.
- Rà soát quyền của service account đích, không chỉ quyền của người tạo key.

### 9.4. Google Cloud Workload Identity Federation

Workload bên ngoài có thể được tin cậy qua pool/provider, attribute mapping và điều kiện. Tùy cấu hình, principal có thể nhận quyền trực tiếp hoặc impersonate service account.

Nếu trust cho một tập workload nguồn quá rộng hoặc claim có thể bị thao túng, principal không được duyệt có thể nhận quyền đích. Review cần giới hạn **issuer, audience, subject, attribute condition, principal set và scope binding**, kèm kiểm thử trường hợp nguồn không hợp lệ bị từ chối.

### 9.5. Permission inheritance và deny

Một binding cấp Organization Viewer có phạm vi rộng hơn nhiều so với cùng role cấp cho một project cụ thể. **Deny policies** và các giới hạn tổ chức có thể chặn quyền trong trường hợp hỗ trợ; nhưng deny/constraint **không tự cấp** entitlement.

Kết quả phân tích quyền cần ghi rõ những policy thực sự có hiệu lực, chứ không chỉ đếm số role trên một project.

## 10. Kubernetes và ranh giới cloud IAM

Kubernetes có **ServiceAccount** và **RBAC** riêng để kiểm soát Kubernetes API. Cloud IAM sử dụng principal/role/binding theo provider. Khi một Pod chạy trong EKS, AKS hoặc GKE, cơ chế workload identity có thể liên kết ServiceAccount với quyền cloud.

| Mặt kiểm soát | Ví dụ câu hỏi |
| --- | --- |
| Kubernetes RBAC | Ai có thể tạo, sửa Pod hoặc gắn ServiceAccount trong namespace? |
| Admission và runtime | Ai được chạy privileged container, mount host path hoặc đọc token? |
| Workload federation | Issuer/subject nào được ánh xạ đến cloud role? |
| Cloud IAM | Role của Pod có thể đọc secret/bucket hoặc sửa IAM không? |
| Node/metadata boundary | Pod có thể tiếp cận credential cấp cho node/instance ngoài dự kiến không? |
| Deployment control | Ai có thể sửa image, command, environment và service account của Pod? |

Một Pod chỉ có Kubernetes RBAC đọc ConfigMap **vẫn có thể có cloud role rộng** nếu cloud trust cấu hình sai. Ngược lại, cloud role chỉ đọc không ngăn Pod sửa Kubernetes API nếu Kubernetes RBAC quá rộng.

### 10.1. Rủi ro theo capability

**Quyền triển khai/sửa Pod** có thể nhạy cảm khi namespace chứa workload dùng identity có quyền cloud lớn. **Quyền sửa ServiceAccount hoặc annotation/federation config** cũng có thể thay đổi danh tính mà workload sử dụng nếu các control plane khác cho phép.

Điểm cần kiểm tra:

- Dùng ServiceAccount riêng cho ứng dụng có nhiệm vụ khác nhau.
- Không cấp quyền cloud rộng cho ServiceAccount mặc định.
- Giới hạn ai có thể sửa Deployment, Pod, ServiceAccount và admission policy.
- Bảo vệ projected token, metadata endpoint và node credential.
- Tách các workload production nhạy cảm với workload phát triển hoặc untrusted.
- Kiểm tra cloud IAM binding và Kubernetes RBAC độc lập.

### 10.2. Platform-specific integration

- **AWS EKS:** IRSA hoặc EKS Pod Identity theo cơ chế được hỗ trợ.
- **Azure AKS:** Microsoft Entra Workload ID và federated identity credentials trong kịch bản phù hợp.
- **Google Kubernetes Engine:** Workload Identity Federation for GKE, có thể dùng principal trực tiếp hoặc liên kết service account theo kiến trúc hỗ trợ.

Không áp cấu hình của một provider cho provider khác. Cần đọc chính xác cơ chế token/trust và scope của môi trường đích khi triển khai.

## 11. CI/CD và infrastructure-as-code: đường quyền gián tiếp

Hệ thống CI/CD thường giữ khả năng **triển khai, tạo resource, sửa IAM hoặc điều khiển workload production**. Người sửa được workflow hoặc code nguồn được pipeline thực thi có thể ảnh hưởng tới những quyền mà pipeline sở hữu.

### 11.1. Mô hình đường quyền

~~~mermaid
flowchart LR
    USER["Người có quyền sửa repository"] --> BRANCH["Branch / workflow changes"]
    BRANCH --> CI["CI/CD runner"]
    CI --> TOKEN["OIDC token / workload identity"]
    TOKEN --> TRUST["Cloud federation trust"]
    TRUST --> ROLE["Deployment role có quyền cloud"]
    ROLE --> PROD["Production service / IaC resource"]
    APPROVAL["Branch protection + review + environment approval"] -.-> BRANCH
    BOUNDARY["IAM least privilege + trust conditions"] -.-> TRUST
    AUDIT["Run audit + role assumption logs"] -.-> CI
~~~

Đường này có thể bị chặn bởi review, protected branch, environment approval, phân quyền runner và điều kiện trust. Vì vậy phải **đánh giá và thử các lớp kiểm soát**, không suy đoán rằng mọi người có quyền đọc hoặc đề xuất mã đều có thể dùng deployment role.

### 11.2. Các câu hỏi review CI/CD

1. Workload role dùng ở build, staging và production có được tách không?
2. Issuer, audience, subject, repository, branch/environment có được trust ràng buộc đúng không?
3. Ai có quyền thay workflow, reusable workflow, runner image, variables và secrets?
4. Job nào cần phê duyệt độc lập trước khi được cấp credential production?
5. Pipeline có quyền sửa IAM mà không có cơ chế giới hạn và review không?
6. Có tài khoản robot hoặc key cũ nằm ngoài OIDC federation không?
7. Khi repo đổi owner hoặc bị archive, trust có được thu hồi không?

### 11.3. Sample policy requirement

~~~yaml
# Giả mã chính sách nghiệp vụ cho CI/CD, không phải file IAM provider
workload:
  id: analytics-staging-deployer
  repository: org/analytics-api
  environment: staging
identity:
  mode: oidc-federation
  trustedIssuer: approved-ci-provider
  expectedAudience: cloud-token-exchange
role:
  purpose: deploy-only-analytics-staging
  allowedScope: analytics-staging
  forbiddenCapabilities:
    - manage-cloud-iam
    - read-production-secrets
    - grant-privileged-roles
governance:
  owner: analytics-platform
  codeReviewRequired: true
  productionApprovalSeparate: true
~~~

Các trường là yêu cầu cần chuyển thành cấu hình cụ thể; không có tác dụng bảo mật chỉ vì chúng xuất hiện trong YAML ở repository.

## 12. Credential, token và phiên: nâng đặc quyền qua danh tính khác

Credential có thể là access key, certificate private key, OAuth access/refresh token, AWS STS session credentials hoặc secret chứa thông tin đăng nhập dịch vụ.

**Đọc được một credential đặc quyền** có thể tạo đường truy cập độc lập với role trực tiếp của principal đọc. Rủi ro phụ thuộc loại token, audience, resource, thời hạn và khả năng sử dụng.

### 12.1. Quy tắc bảo vệ

- Ưu tiên managed identity, workload identity federation và credential ngắn hạn khi có hỗ trợ.
- Không đưa key/token vào mã nguồn, image, log, crash dump hoặc CI artifacts.
- Tách quyền **đọc secret** khỏi quyền **quản trị secret** và quyền **thay IAM** khi khả thi.
- Giới hạn người được tạo, xoay hoặc tải xuống credential của identity đặc quyền.
- Lưu owner, nguồn tạo, hạn dùng, lần sử dụng và kế hoạch rotation cho credential còn cần.
- Có quy trình chặn tái cấp và xử lý credential/session đã phát khi người/workload Leaver.

### 12.2. Ngắn hạn không đồng nghĩa an toàn tuyệt đối

Temporary credential bị đánh cắp vẫn có thể được sử dụng khi còn hạn. Nếu trust hoặc source identity bị chiếm, bên không được phép còn có thể nhận credential mới liên tục. Do đó cần cả:

1. Bảo vệ nguồn/issuer và runtime.
2. Giới hạn trust và permissions.
3. Giới hạn TTL phù hợp với tác vụ.
4. Thu hồi entitlement, key/session theo khả năng provider.
5. Giám sát role assumption, token issuance và API action bất thường.

### 12.3. Không coi revoke một grant là revoke mọi phiên

Một phiên đã được phát hành trước thời điểm thay đổi role/group/trust có thể tiếp tục đến khi hết hạn hoặc bị ngăn theo cơ chế của dịch vụ. Với Leaver khẩn cấp, phải xác định loại credential nào đang tồn tại và phương án vô hiệu hóa phù hợp từng provider; ghi rõ rủi ro nếu không thể xử lý tức thời.

## 13. Least privilege và nguyên tắc phân tách quyền

**Least privilege** phải xem **action, resource, scope, principal, trust, điều kiện và thời hạn**. Quyền nhỏ trên một resource cụ thể khác với quyền tương tự cấp ở toàn organization.

### 13.1. Ma trận thiết kế

| Vai trò nghiệp vụ | Quyền nên có | Quyền cần tránh |
| --- | --- | --- |
| DevLogReader | Xem log ứng dụng dev tại scope cụ thể | Sửa IAM hoặc đọc secret production |
| StagingDeployer | Triển khai một service staging | Quản trị toàn subscription/account |
| ProdIncidentViewer | Đọc metric/log phục vụ incident | Gán role cao hoặc tắt audit |
| JITProdOperator | Thao tác được duyệt trong cửa sổ xử lý sự cố | Quyền vĩnh viễn hoặc ngoài service |
| IAMPolicyAuditor | Đọc policy, trust, bindings và lịch sử thay đổi | Tự sửa/grant IAM |
| WorkloadSecretReader | Đọc secret cần cho chính workload | Đọc secret của mọi ứng dụng |
| KeyRotationAutomation | Xoay key theo workflow được bảo vệ | Tạo credential cho principal ngoài phạm vi |

Tên role trong bảng là **ví dụ nghiệp vụ**, không mặc nhiên là tên role chuẩn của provider.

### 13.2. Separation of Duties (SoD)

SoD ngăn một chủ thể kiểm soát đồng thời những thao tác mâu thuẫn. Ví dụ:

- Người yêu cầu quyền production không tự phê duyệt quyền đó.
- Người duyệt thay IAM không thể trực tiếp bỏ qua review trên chính thay đổi của họ.
- Workload deploy không tự cấp quyền Owner cho service principal của nó.
- Người quản lý CI runner không mặc nhiên có quyền thay trust của cloud production.

SoD hiệu quả phải xét **đường gián tiếp**: nếu một người không thể gán role nhưng có thể sửa pipeline đang dùng role đó, chính sách phân tách nhiệm vụ có thể chưa đạt mục tiêu.

### 13.3. Permission boundaries, deny và organization guardrails

Cơ chế hạn chế ở cấp organization hoặc principal giúp giảm blast radius khi một role/policy vô tình rộng. Tuy nhiên cần phân biệt:

- **Allow grants:** Quy tắc tạo đường quyền hợp lệ.
- **Deny/restriction:** Quy tắc chặn hoặc giới hạn quyền trong phạm vi hỗ trợ.
- **Role scopes/conditions:** Giới hạn tài nguyên, ngữ cảnh và thời gian.
- **Identity and CI controls:** Chặn nguồn không được duyệt nhận hoặc sử dụng quyền.

Guardrail không thay thế việc giảm permissions gốc. Một role quyền rất rộng nhưng “hiện đang bị deny” vẫn cần review vì khi deny thay đổi, phạm vi quyền có thể mở rộng.

## 14. RBAC và ABAC trong ngăn nâng đặc quyền

**Role-Based Access Control (RBAC)** tổ chức quyền theo chức trách; **Attribute-Based Access Control (ABAC)** đánh giá thuộc tính của principal, resource hoặc request theo các cơ chế provider hỗ trợ.

### 14.1. RBAC không phải phép bảo đảm tự động

Role catalog tốt nên có:

- Tên và mục đích nghiệp vụ.
- Tập permissions, resource scope, môi trường.
- Người/nhóm/workload đủ điều kiện.
- Owner, người phê duyệt và kỳ access review.
- Phân loại rủi ro, những role hoặc duties xung đột.
- Điều kiện sử dụng, JIT/expiry nếu cần.

Nếu một vai trò “Developer” bị cấp thêm quyền chỉnh IAM production, RBAC vẫn có thể hoạt động đúng về mặt kỹ thuật nhưng **thiết kế role sai về mặt an toàn**.

### 14.2. ABAC cần thuộc tính đáng tin cậy

~~~yaml
# Giả mã quy tắc ABAC, không triển khai nguyên trạng trên cloud
principal:
  status: active
  team: analytics
  environment: dev
resource:
  ownerTeam: analytics
  environment: dev
request:
  action: logs.read
allowWhen:
  - principal.status == active
  - principal.team == resource.ownerTeam
  - principal.environment == resource.environment
  - request.action == logs.read
~~~

**Thuộc tính tạo quyền phải có nguồn được bảo vệ.** Nếu principal có thể tự đổi tag của resource hoặc claim của workload để khớp điều kiện, ABAC có thể mở đường quyền không được duyệt.

Ngoài ra, không phải cloud IAM nào cũng truy vấn trạng thái HRIS ở thời gian thực. Sự kiện JML phải cập nhật group/attribute/grant và **đối soát** đúng lúc.

## 15. Privileged Access Management và elevation được phê duyệt

Trong vận hành production, có những nhiệm vụ thật sự cần quyền cao. **PAM, PIM, Just-In-Time (JIT)** hoặc workflow phê duyệt có thời hạn có thể cung cấp đường nâng quyền hợp lệ và được kiểm soát.

### 15.1. Một luồng elevation hợp lệ

~~~mermaid
sequenceDiagram
    participant U as Người vận hành
    participant I as IdP / MFA
    participant P as Privileged access workflow
    participant A as Resource owner / approver
    participant C as Cloud IAM
    participant L as Audit
    U->>P: Yêu cầu role + resource + lý do + thời hạn
    P->>A: Phê duyệt theo rủi ro
    A-->>P: Approved hoặc Denied
    P->>I: Kiểm tra xác thực mạnh theo policy
    I-->>P: Đủ điều kiện xác thực
    P->>C: Kích hoạt quyền có thời hạn
    C-->>U: Phiên/entitlement phù hợp
    C->>L: Ghi thay đổi và sử dụng quyền
    P->>C: Thu hồi khi hết hạn hoặc bị dừng
    C->>L: Readback và trạng thái verification
~~~

Không phải mọi provider dùng cùng API hoặc cùng cơ chế JIT. Sơ đồ mô tả logic quản trị.

### 15.2. Nguyên tắc

1. Xác định **ai đủ điều kiện**, không cấp quyền thường trực cho tất cả nhân viên.
2. Ghi lý do và ticket/incident.
3. Phê duyệt độc lập khi mức rủi ro yêu cầu.
4. Kiểm tra MFA, thiết bị hoặc điều kiện phiên theo khả năng.
5. Cấp quyền tối thiểu theo resource và thời hạn.
6. Ghi hành động đã thực hiện khi quyền được kích hoạt.
7. Thu hồi entitlement, kiểm tra session/credential còn sống và lưu bằng chứng.

**Hết giờ JIT không nhất thiết làm tất cả token đã cấp hết hiệu lực ngay.** Cần quản lý riêng vòng đời credential/session.

### 15.3. Break-glass

Account hoặc role khẩn cấp giúp vận hành khi IdP/SSO hoặc cơ chế cấp quyền trung tâm hỏng. Nó cần được kiểm soát độc lập, bảo vệ credential, cảnh báo mỗi lần sử dụng và review định kỳ.

Không được biến break-glass thành đường truy cập hằng ngày hoặc bỏ qua logging. Việc ít dùng là bình thường; không tự xóa chỉ vì chỉ số last used thấp.

## 16. Joiner–Mover–Leaver cho người dùng và quyền đặc biệt

Quyền nâng đặc quyền liên quan trực tiếp đến quản lý vòng đời. Khi danh tính thay đổi công việc, **khả năng nhận hoặc tạo quyền cao** phải thay đổi theo.

| Sự kiện | Cần xác minh | Biện pháp |
| --- | --- | --- |
| **Joiner** | Người đã được xác minh, vai trò nghiệp vụ và approval hợp lệ? | Cấp role tối thiểu, không mặc nhiên có quyền privileged |
| **Mover** | Chuyển team/project có còn cần trust, IAM admin, service account impersonation cũ không? | Thu hồi role và đường gián tiếp cũ, xử lý SoD, cấp đúng quyền mới |
| **Leaver** | IdP/account/key/session/trust nào còn cho người đó truy cập? | Disable nguồn, thu hồi grants, credential, xác minh tại từng target |

### 16.1. Joiner: không suy quyền từ chức danh chung

Kỹ sư mới có chức danh Software Engineer không mặc nhiên cần quyền Owner trên toàn AWS account/Azure subscription/Google Cloud project. Role phải dựa trên **nhiệm vụ thực tế, scope và approval**.

Một quyền sửa IAM hoặc impersonate service account quyền cao phải có căn cứ rõ ràng; không tự động cấp theo nhóm chung chỉ vì việc đăng nhập SSO đã thành công.

### 16.2. Mover: tránh tích tụ quyền

Ví dụ, nhân viên chuyển từ Platform Security sang Data Analytics. Nếu chỉ thêm DataReader mà không gỡ IAM Policy Administrator, quyền cũ vẫn còn và có thể được dùng trực tiếp hoặc gián tiếp.

Quy trình:

1. Nhận sự kiện Mover từ HRIS/nguồn có thẩm quyền.
2. Tính **desired access** ở vị trí mới.
3. Truy vấn grants trực tiếp, qua nhóm, inherited role, cross-account trust, impersonation, key và quyền sửa pipeline.
4. Thu hồi entitlement cũ; giải quyết SoD và quyền xung đột.
5. Kiểm tra credential/session đã cấp theo khả năng provider.
6. Đọc lại quyền thực tế; đánh dấu VERIFIED hoặc ngoại lệ có owner.

### 16.3. Leaver: ngăn tái cấp và xử lý phiên cũ

Khi nhân viên nghỉ việc, disable IdP để ngăn đăng nhập mới chưa chắc đủ. Cần tìm:

- Role assignment hoặc binding trực tiếp còn tồn tại.
- Cloud-local IAM user và access key riêng.
- Guest account, liên kết external hoặc quyền cross-account.
- Quyền impersonate service account hoặc assume role.
- Secret/key mà người đó nắm giữ.
- Phiên tạm thời được cấp trước thời điểm Leaver.
- Repository, pipeline hoặc workload có owner cá nhân cần chuyển giao.

**Không xóa role definition dùng chung** chỉ vì một người rời đi. Thu hồi đúng quyền của người đó và đảm bảo role vẫn phục vụ những principal còn hợp lệ.

## 17. Joiner–Mover–Leaver cho workload

Workload không có HRIS; nguồn chuẩn có thể là service catalog, CMDB, CI/CD registry, môi trường Kubernetes hoặc hệ thống quản lý tích hợp.

### 17.1. Joiner của workload

Trước khi tạo role cho service mới:

- Có **workload ID ổn định**, owner chính và backup.
- Xác định runtime, issuer, subject và môi trường.
- Xác định action/resource tối thiểu.
- Kiểm tra khả năng sửa trust/policy, nhận credential hoặc impersonate.
- Chọn managed identity/federation để giảm secret tĩnh.
- Gắn log cấp phiên và API action phù hợp.
- Kiểm tra negative cases trước production.

### 17.2. Mover của workload

Workload có thể đổi repository, owner, cloud project, runtime identity hoặc chuyển staging sang production. Việc Mover phải:

1. Cấp quyền môi trường mới theo phê duyệt tương ứng.
2. Thay trust dựa trên issuer/subject mới.
3. Thu hồi grant ở scope cũ nếu không còn nhu cầu.
4. Giới hạn thời gian chạy song song và ghi owner ngoại lệ.
5. Xác minh không còn credential hoặc impersonation ngoài phạm vi.

### 17.3. Leaver của workload

Khi pipeline bị archive hoặc service retire, cần xóa/thu hồi **role assignment, IAM binding, trust, federated credential, key và identity riêng** nếu phù hợp, đồng thời kiểm tra session đã phát hành.

**Xóa Pod, VM hoặc repository không đồng nghĩa xóa mọi cloud IAM permission**. Ví dụ user-assigned managed identity, Google Cloud service account và IAM role có thể tồn tại độc lập với workload ban đầu.

### 17.4. Nhân viên chủ sở hữu workload nghỉ việc

Nếu kỹ sư nghỉ việc nhưng ứng dụng còn chạy, chuyển owner và rà soát quyền cá nhân trên Git/CI/Cloud. Workload nên dùng **identity riêng**, không phụ thuộc access key của nhân viên. Nếu trước đó dùng credential cá nhân, phải chuyển đổi, rotate/revoke và chứng minh không còn đường truy cập từ người đã rời tổ chức.

## 18. Access review theo góc nhìn privilege escalation

Rà soát quyền cloud nên trả lời không chỉ “có cần role này không?” mà còn **“role này có thể dẫn tới quyền nào khác?”**.

### 18.1. Bản ghi review tối thiểu

| Trường | Nội dung |
| --- | --- |
| Principal ID / loại | Employee, contractor, service account, workload |
| Identity source | HRIS, IdP, cloud-local, issuer hoặc workload registry |
| Role, scope, grant source | Quyền trực tiếp, qua nhóm, kế thừa, trust hoặc resource policy |
| Permissions nhạy cảm | Sửa IAM, gán role, tạo key, impersonate, sửa workload/CI |
| Đường quyền gián tiếp | Role/identity/workload đích và các điều kiện |
| Resource sensitivity | Production, dữ liệu nhạy cảm, secret, logging/backup |
| Business owner / security reviewer | Ai xác nhận nhu cầu và đánh giá rủi ro |
| Decision / approval | KEEP, MODIFY, REVOKE, EXCEPTION với lý do |
| Remediation state | REQUESTED, APPLIED, VERIFIED hoặc FAILED |
| Session/credential handling | Đã thu hồi hoặc còn hiệu lực tới khi nào |
| Evidence | Config diff, IAM readback, kiểm thử được phép và audit logs |

### 18.2. Review theo rủi ro

- **Rất cao:** IAM policy mutation, role assignment administration, sửa trust production, credential minting, impersonation principal quyền cao.
- **Cao:** Sửa CI/CD production, cross-account trust nhạy cảm, quyền đọc secret chứa credential, quyền thay workloads có identity mạnh.
- **Trung bình:** Quyền ghi hạn chế trên môi trường thử nghiệm hoặc dữ liệu nội bộ không nhạy cảm.
- **Thấp hơn:** Role chỉ đọc được giới hạn scope và dữ liệu ít nhạy cảm.

Đây là ví dụ phân nhóm, không phải tiêu chuẩn định lượng bắt buộc. Một quyền chỉ đọc có thể rất nhạy cảm nếu tài nguyên chứa dữ liệu được bảo vệ.

### 18.3. Không sử dụng last-used như bằng chứng duy nhất

Một privileged role phục vụ disaster recovery có thể ít được sử dụng nhưng vẫn cần tồn tại theo runbook được phê duyệt. Ngược lại, một role được dùng hàng ngày vẫn có thể quá rộng. Cần kết hợp **mục đích, owner, scope, khả năng nâng quyền và bằng chứng sử dụng**.

## 19. Phát hiện hành vi nâng đặc quyền qua log

Giám sát tốt cần phát hiện **thay đổi quyền** và **sử dụng quyền sau thay đổi**, không chỉ tập trung vào các lần đăng nhập thất bại.

### 19.1. Tín hiệu AWS

| Nhóm sự kiện | Ý nghĩa cần điều tra |
| --- | --- |
| Thay role trust policy | Principal/issuer nào mới được assume role? |
| Thêm/sửa/đổi policy version | Role hoặc user nhận thêm action/resource gì? |
| Gắn policy hoặc thay group membership | Có principal mới nhận quyền đặc biệt không? |
| Tạo/rotate IAM access key | Key thuộc identity nào, có owner và approval không? |
| STS role assumption | Source principal, role target và session context có phù hợp? |
| API tạo/sửa tài nguyên nhận execution role | Ai gắn role vào service, role đó có quyền gì? |
| Thay logging/security guardrails | Có dấu hiệu che giấu hoặc làm rộng quyền không? |

**CloudTrail** ghi nhiều thao tác API phù hợp theo cấu hình logging, nhưng việc thiếu event không tự chứng minh không có truy cập. Với **iam:PassRole**, kiểm tra API của dịch vụ mang role và mối liên hệ với IAM, không tìm một event PassRole độc lập.

### 19.2. Tín hiệu Azure/Microsoft Entra

- Role assignment được tạo, thay đổi hoặc xóa ở scope nhạy cảm.
- Sự kiện thay PIM eligibility/activation hoặc quản trị privileged role.
- Application/service principal credentials hoặc federated credential được tạo/sửa.
- Managed identity được gắn vào workload hoặc đổi cấu hình.
- Workload/deployment có RBAC cao được sửa bởi principal không thường thực hiện.
- Thay đổi chính sách Conditional Access hoặc quyền quản trị directory.
- Azure Activity, resource logs, Entra sign-in/audit logs có thay đổi bất thường.

Cần liên kết **directory identity, service principal và Azure resource scope** để thấy đường quyền, thay vì chỉ đọc một log source riêng lẻ.

### 19.3. Tín hiệu Google Cloud

- IAM policy bindings được thay đổi ở project/folder/organization hoặc resource nhạy cảm.
- Quyền impersonation của service account được cấp cho principal mới.
- Sự kiện tạo service account key hoặc phát access token theo API hỗ trợ.
- Workload Identity Federation provider/attribute mapping được mở rộng.
- Service account hoặc workload dùng API vượt mẫu hoạt động đã duyệt.
- Thay đổi organization constraints hoặc policy bảo mật liên quan.

**Cloud Audit Logs**, sự kiện IAM Credentials API và dữ liệu chính sách cần được thu thập theo loại log/dịch vụ được hỗ trợ. Không mặc định mọi sự kiện sử dụng token đều được ghi với cùng độ đầy đủ.

### 19.4. Correlation quan trọng hơn một sự kiện đơn

Ví dụ một chuỗi đáng điều tra:

~~~text
T0: Principal ít khi quản trị IAM được gán quyền sửa role.
T1: Trust hoặc permissions của một role production thay đổi.
T2: Role production được assume hoặc workload mang role đó thay đổi.
T3: Có API tác động tài nguyên nhạy cảm ngoài lịch triển khai.

Hành động:
  Đối chiếu change ticket, owner, approval, JML event.
  Kiểm tra principal nguồn và quyền đích.
  Xác định có hành vi được ủy quyền hay không.
  Ghi bằng chứng và xử lý theo mức rủi ro.
~~~

Một thay đổi quản trị có thể hoàn toàn hợp lệ. Phát hiện là **tín hiệu cần điều tra**, không tự động là kết luận bị xâm nhập.

## 20. Phòng ngừa theo nhiều lớp

**Defense in depth** dùng nhiều kiểm soát độc lập để khi một lớp sai, đường tăng quyền vẫn khó hình thành hoặc dễ được phát hiện.

### 20.1. Ma trận kiểm soát

| Lớp | Kiểm soát cần có | Giảm rủi ro |
| --- | --- | --- |
| Identity source | HRIS/registry chuẩn, owner và trạng thái JML | Danh tính mồ côi/đã nghỉ vẫn giữ quyền |
| Authentication | SSO/MFA phù hợp, OIDC issuer đáng tin | Mạo nhận principal |
| Role/policy | Least privilege, scope hẹp, custom role khi cần | Cấp action/resource quá rộng |
| Trust/federation | Issuer, audience, subject và điều kiện chặt | Workload/đối tác không hợp lệ nhận quyền |
| Privileged access | JIT/PAM/PIM, phê duyệt và thời hạn | Quyền cao tồn tại thường trực |
| SoD | Tách request, approval và IAM execution | Tự nâng quyền qua chuỗi nhiệm vụ |
| IaC/policy-as-code | Review diff, linter, pipeline được bảo vệ | Sửa IAM trực tiếp không kiểm soát |
| Runtime/CI | Pod isolation, metadata protection, runner hardening | Chiếm credential của workload quyền cao |
| Guardrails | Deny/boundary/org constraints theo provider | Giảm blast radius của grant lỗi |
| Detection/audit | Log tập trung, correlation và cảnh báo | Nâng quyền không bị phát hiện |
| Reconciliation | So desired, assigned, effective, readback | Residual access sau Mover/Leaver |

### 20.2. Chọn các kiểm soát có thể kiểm chứng

Một chính sách nói “chỉ được cấp quyền tối thiểu” cần được chuyển thành những điều có thể kiểm tra:

1. Roles nào được phép dùng trong production?
2. Ai có thể gán hoặc sửa chúng?
3. Scope/resource conditions cụ thể là gì?
4. Principal nào có quyền impersonation hoặc credential management?
5. Những thay đổi nào cần review bởi người khác?
6. Làm thế nào phát hiện direct grant ngoài IdP?
7. Khi quyết định REVOKE, API nào được gọi và bằng chứng nào chứng minh quyền đã mất?

Nếu thiếu đáp án, kiểm soát còn ở mức tuyên bố và khó dùng trong audit.

## 21. Policy-as-code và kiểm thử phòng thủ

Chính sách IAM, trust và role assignments nên được quản trị qua **Infrastructure as Code (IaC)** hoặc quy trình kiểm soát tương đương khi phù hợp. Diff giúp reviewer thấy một change mở quyền cho principal hoặc scope nào.

### 21.1. Quy trình thay đổi

~~~mermaid
flowchart TD
    R["Yêu cầu cấp/sửa quyền"] --> Q["Mô tả principal, role, action, resource, trust"]
    Q --> D["Policy/IaC diff"]
    D --> L["Lint + phân tích quyền nguy hiểm"]
    L --> T["Kiểm thử Allow/Deny và đường gián tiếp"]
    T --> A["Approval độc lập theo rủi ro"]
    A --> P["Triển khai có kiểm soát"]
    P --> V["Readback IAM + effective access"]
    V --> M["Giám sát drift, thay đổi và session"]
    V -->|Lỗi| F["Rollback/khắc phục theo quy trình"]
    F --> D
~~~

### 21.2. Những bài kiểm thử cần có

| Kịch bản kiểm tra | Kỳ vọng |
| --- | --- |
| Developer đọc log dev đã phê duyệt | Allow |
| Developer thay IAM trust production | Deny |
| Workload staging truy cập secret production | Deny |
| Workload từ OIDC subject/issuer không được duyệt | Không nhận được cloud credential |
| Người chỉ có role đọc thử gán role cao | Deny |
| Pipeline hợp lệ triển khai đúng service staging | Allow |
| Pipeline dev thử sử dụng identity production | Deny |
| Mover đã thu hồi quyền cũ | Không còn đường cấp quyền cũ |
| Leaver với cloud-local key còn tồn tại | Phải phát hiện và xử lý, không VERIFIED |
| Role/session còn sống sau revoke | Ghi chính xác trạng thái và xử lý theo TTL/revoke hỗ trợ |

Không triển khai thử nghiệm phá hoại hoặc khai thác nâng quyền trên production. Dùng **policy simulation, staging, test principal và API read-only** theo phạm vi được phép; mọi phép thử thay đổi cấu hình phải qua review và rollback plan.

### 21.3. Drift và thay đổi ngoài pipeline

Một policy có thể được sửa trực tiếp trong cloud console. Khi đó IaC không còn phản ánh trạng thái thật. Cần so **desired config** với **actual config**, cảnh báo những thay đổi nhạy cảm, xác định actor/ticket và đưa về trạng thái được duyệt. Không tự động rollback mù quáng nếu có incident response hoặc thay đổi khẩn cấp hợp lệ đang diễn ra.

## 22. Ứng phó sự cố nghi nâng đặc quyền

Khi có dấu hiệu principal nhận quyền cao ngoài dự kiến, phải phân biệt **chặn lạm dụng ngay** với **điều tra đầy đủ**:

1. **Xác định phạm vi:** Principal nguồn, principal/role đích, account/subscription/project, dữ liệu và action đã sử dụng.
2. **Bảo vệ bằng chứng:** IAM configuration snapshot, audit logs, CI run, IdP event, STS/token metadata; không lưu raw secret vào ticket.
3. **Xác minh phê duyệt:** Có change ticket, JIT activation, approver hợp lệ hoặc sự kiện khẩn cấp được duyệt không?
4. **Giảm rủi ro:** Thu hồi grant/trust không được phép, chặn source identity hoặc workload bị nghi chiếm, giảm permissions theo công cụ provider.
5. **Xử lý credential:** Vô hiệu hóa/rotate key tĩnh, xử lý session/temporary credential còn hiệu lực theo khả năng hỗ trợ.
6. **Tìm các đường khác:** Direct role, group, resource policy, impersonation, service account key, CI pipeline, cross-account trust.
7. **Xác minh:** Đọc lại cloud IAM và kiểm tra quyền có còn sử dụng được trong phạm vi được phép không.
8. **Khắc phục nguyên nhân:** Sửa role catalog, trust, owner, SoD, CI controls hoặc lỗi JML; bổ sung test và cảnh báo.

**Không tự giả định mọi session đã bị hủy ngay** sau khi gỡ role assignment. Trường hợp chưa thể thu hồi tức thời phải có owner, hạn token và biện pháp giảm thiểu ghi rõ.

### 22.1. Quyết định incident không đồng nghĩa quyết định lifecycle

Đội ứng cứu có thể phải tạm khóa một workload quan trọng để bảo vệ hệ thống. Sau sự cố, owner và IAM team cần xác định **trạng thái quyền mong muốn lâu dài**, đảm bảo dịch vụ hợp lệ được khôi phục bằng identity an toàn thay vì dùng lại credential cũ bị nghi lộ.

## 23. Tình huống xuyên suốt: từ quyền đọc đến đường nâng quyền gián tiếp

Giả sử công ty có ứng dụng **Learning Platform** trên ba cloud:

- AWS account phục vụ backend production.
- Azure subscription chứa môi trường phát triển và một pipeline quản lý deployment.
- Google Cloud project phục vụ báo cáo dữ liệu.

Nhân viên **An**, identity ID **EMP-8402**, chuyển từ đội Platform Operations sang đội Data Analytics. Cùng lúc, pipeline **learning-staging-deployer** đổi repository và một workload báo cáo đã ngừng hoạt động.

### 23.1. Trạng thái ban đầu

| Principal | Quyền phát hiện | Rủi ro |
| --- | --- | --- |
| EMP-8402 | Đọc log AWS production | Có thể còn hợp lệ tạm thời theo bàn giao |
| EMP-8402 | Có khả năng sửa cấu hình pipeline Azure đang dùng identity triển khai production | Đường quyền gián tiếp cần review |
| EMP-8402 | Quyền đọc dữ liệu Google Cloud analytics-dev | Có thể cần cho nhiệm vụ mới |
| learning-staging-deployer | Trust cho OIDC subject của repo cũ và repo mới | Bề mặt nhận role rộng hơn dự kiến |
| learning-report-exporter | Được impersonate một service account dữ liệu nhưng workload đã retire | Quyền tồn dư phi con người |

Tên và quyền trong bảng là **dữ liệu giả định**. Không có kết luận xâm nhập khi chưa kiểm tra quyền thật, approval và các lớp kiểm soát bổ sung.

### 23.2. Review theo Mover

IGA nhận Mover từ HRIS. Desired access mới cho phép An đọc dữ liệu analytics-dev nhưng không mặc nhiên giữ quyền quản lý pipeline production. Platform owner cần đánh giá quyền sửa pipeline và các approval protection.

Quy trình có thể chọn:

- **KEEP** một quyền đọc phù hợp tại analytics-dev.
- **REVOKE** quyền sửa pipeline production nếu công việc mới không cần.
- **MODIFY** quyền đọc log AWS thành quyền tạm có hạn nếu bàn giao còn hiệu lực và được duyệt.
- **ESCALATE** nếu phát hiện An có đường cấp IAM Administrator ngoài role đã đăng ký.

Sau mỗi quyết định, phải truy vấn lại cloud target. Việc đổi nhóm ở IdP chưa chứng minh direct IAM binding hoặc quyền sửa CI đã mất.

### 23.3. Sửa trust CI/CD

Pipeline chuyển sang repository mới. Team Platform cập nhật subject/condition, đồng thời thu hồi trust của repository cũ sau khi hoàn tất migration. Quy trình kiểm tra token từ nguồn không còn được duyệt bị từ chối khi xin phiên mới; phiên cũ được xử lý theo TTL và khả năng revoke.

### 23.4. Retire workload báo cáo

Workload learning-report-exporter đã ngừng. Quyền impersonation và service account binding liên quan cần được gỡ nếu không còn owner hoặc dependency hợp lệ. Nếu service account dùng chung cho workload khác, không được xóa mù quáng; phải xác định principal nào thực sự cần quyền và tách phạm vi nếu cần.

### 23.5. Luồng kiểm chứng

~~~mermaid
flowchart TD
    E["HRIS Mover + workload lifecycle changes"] --> DES["Tính desired access"]
    DES --> INV["Thu thập direct/inherited grants + trust + CI controls"]
    INV --> RISK["Phân tích đường quyền trực tiếp/gián tiếp"]
    RISK --> REV["Business owner + IAM/Security review"]
    REV --> FIX["Gỡ grant cũ, hạn trust, cập nhật owner"]
    FIX --> CHECK["Cloud readback + negative tests"]
    CHECK --> Q{"Còn quyền không được duyệt?"}
    Q -->|Có| EX["EXCEPTION / FAILED + owner"]
    EX --> FIX
    Q -->|Không| VERIFIED["VERIFIED + audit evidence"]
~~~

### 23.6. Bản ghi kiểm toán minh họa

~~~json
{
  "eventId": "JML-MOVER-8402",
  "principalId": "EMP-8402",
  "eventType": "mover",
  "findingType": "potential-indirect-privilege-escalation",
  "source": "HRIS-and-IAM-review",
  "target": "azure-production-deployment",
  "riskPath": "repository-editor-to-privileged-workload",
  "decision": "REVOKE_OR_NARROW",
  "owner": "platform-security",
  "status": "verification_pending",
  "occurredAt": "2026-11-23T07:00:00Z"
}
~~~

Đây là bản ghi **giả định**, không phải chứng cứ rằng một sự cố đã xảy ra. Trạng thái **verification_pending** nghĩa là chưa kết luận quyền ngoài dự kiến đã bị loại bỏ. Cần readback, xác minh và ghi kết quả tương ứng.

## 24. Đối soát quyền và bằng chứng kiểm toán

Một quy trình hoàn chỉnh phải tách:

~~~text
REQUESTED   Yêu cầu cấp/sửa/thu hồi quyền đã được tạo
APPROVED    Đã có quyết định theo chính sách
APPLIED     API hoặc hệ thống đích báo thay đổi thành công
VERIFIED    Đã kiểm chứng trạng thái quyền mong muốn tại target
FAILED      Thao tác hoặc kiểm chứng không thành công
EXCEPTION   Còn rủi ro với owner, hạn và biện pháp giảm thiểu
~~~

**APPLIED không đồng nghĩa VERIFIED.** Một quyền có thể còn qua nhóm, role kế thừa, trust khác, resource policy hoặc session đã phát hành.

### 24.1. Giả mã reconciliation

~~~text
event = getAuthorizedLifecycleEvent(principalId)
targets = discoverCloudTargetsAndTrustEdges(principalId)

for target in targets:
    desired = approvedEntitlements(principalId, target)
    actual = enumerateRolesBindingsTrustCredentialsAndCIPrivileges(principalId, target)
    paths = analyzePotentialPrivilegePaths(principalId, actual)

    findings = compareDesiredWithActualAndPaths(desired, actual, paths)
    decisions = obtainRiskApprovals(findings)
    applyIdempotentRemediation(decisions, target)

    verified = readBackAndAssessEffectiveAccess(target, principalId)
    if verified.matchesDesiredState:
        recordVerified(event, target, verified.evidence)
    else:
        recordExceptionWithOwnerAndDeadline(event, target, verified.diff)
~~~

Đây là **giả mã nghiệp vụ**, không phải thư viện tính quyền đa cloud. Việc phân tích đường quyền cần chuẩn hóa principal, issuer, subject, role, scope, điều kiện, resource policy, quyền kế thừa và cách provider thực thi. Không phải mọi cloud có API liệt kê tất cả phiên còn sống; phải nêu rõ giới hạn của bằng chứng.

### 24.2. Audit evidence nên lưu

| Bằng chứng | Mục đích |
| --- | --- |
| Source JML event + principal ID | Liên kết trạng thái nhân sự/workload |
| Role/policy/trust trước và sau | Chứng minh thay đổi phạm vi quyền |
| Business justification + approval | Phân biệt thao tác hợp lệ và trái phép |
| Resource scope + cloud target | Xác định chính xác ảnh hưởng |
| Actor và execution metadata | Biết ai hoặc automation nào đổi IAM |
| Cloud audit log reference | Truy vết role assumption, credential issuance và API action |
| Readback + hiệu lực | Chứng minh entitlement/grant đã thay đổi |
| Token/session handling | Những credential đã thu hồi hoặc còn hiệu lực |
| Exception/risk owner | Có người chịu trách nhiệm khi chưa thể xử lý hết |

Không lưu raw token, secret hoặc private key trong log để làm bằng chứng. Dùng correlation ID, resource ID, thời điểm và metadata cần thiết.

## 25. Chỉ số vận hành cho quản lý rủi ro nâng đặc quyền

| Chỉ số | Ý nghĩa |
| --- | --- |
| **Số principal có quyền sửa IAM tại production** | Quy mô nhóm có thể thay đổi quyền nhạy cảm |
| **Số đường impersonation tới privileged service account** | Mức độ phơi nhiễm từ quyền gián tiếp |
| **Số role trust cross-account/cross-tenant không có owner** | Phát hiện quan hệ tin cậy mồ côi |
| **Tỷ lệ privileged roles có JIT/expiry/review** | Chất lượng kiểm soát quyền cao |
| **Số CI/CD deployment roles có trust quá rộng** | Rủi ro workload ngoài dự kiến nhận quyền |
| **Số service account keys hoặc credentials dài hạn** | Rủi ro credential tồn dư |
| **Số IAM policy drift events** | Thay đổi ngoài nguồn được duyệt |
| **P95 thời gian thu hồi privileged grants sau Leaver** | Tốc độ xử lý quyền rủi ro cao |
| **Tỷ lệ Mover/Leaver được VERIFIED** | Có readback thay vì chỉ gửi API |
| **Số SoD conflicts chưa xử lý** | Tổ hợp quyền có thể tự phê duyệt/tự triển khai |
| **Tỷ lệ cảnh báo nâng quyền được điều tra đúng hạn** | Hiệu quả phát hiện và phản ứng |
| **Số quyền tồn dư xuất hiện lại** | Chỉ ra lỗi provisioning hoặc source-of-truth |

Nên phân nhóm theo **AWS/Azure/Google Cloud, production/non-production, workforce/workload, rủi ro đặc quyền và owner**. Một đường có thể quản trị IAM production cần ưu tiên hơn quyền chỉ đọc sandbox được giới hạn.

## 26. Bài tập tự kiểm tra

### Bài 1. Quyền của người triển khai

**Tình huống:** Kỹ sư có thể sửa cấu hình triển khai một application chạy với managed identity được gán role Owner tại subscription production.

**Câu hỏi:** Có thể kết luận kỹ sư chỉ có quyền Deploy nên không có rủi ro quản trị IAM không?

**Đáp án:** Không. Cần đánh giá quyền thực sự sửa/chạy workload, quyền của identity đích, cơ chế isolation/approval và liệu kết hợp này tạo đường tác động gián tiếp không. Biện pháp có thể gồm thu hẹp role managed identity, tách deployment identity và bảo vệ pipeline.

### Bài 2. AWS iam:PassRole

**Tình huống:** Một báo cáo giám sát đang chờ sự kiện API tên PassRole trong CloudTrail để phát hiện việc role được gắn cho dịch vụ.

**Đáp án:** Phương pháp đó chưa đúng: iam:PassRole là permission, không phải thao tác API độc lập. Cần theo dõi API tạo/sửa resource của dịch vụ có tham chiếu role, kèm quyền/trust và log sử dụng role.

### Bài 3. Google Cloud Service Account User

**Tình huống:** Reviewer tuyên bố mọi principal có Service Account User đều tự tạo được OAuth access token cho service account.

**Đáp án:** Không thể kết luận như vậy. Phải phân biệt quyền dùng/gắn service account trong một số kịch bản với quyền mint token (chẳng hạn Token Creator); đồng thời rà soát khả năng triển khai workload dùng service account.

### Bài 4. Contributor và Azure RBAC

**Tình huống:** Một principal có Contributor trên resource group chứa workload chạy bằng user-assigned managed identity đặc quyền cao.

**Đáp án:** Contributor thường không có quyền gán Azure RBAC role trực tiếp, nhưng vẫn phải xét quyền cấu hình resource, workload identity và khả năng sửa code/runtime. Thu hẹp identity, resource scope và quyền triển khai nếu cần.

### Bài 5. Pipeline đổi repository

**Tình huống:** CI/CD đã đổi repository; cả subject cũ và subject mới đều được trust để nhận production role.

**Đáp án:** Nếu thời gian chuyển đổi đã kết thúc, trust cũ là quyền tồn dư. Cần xác minh dependency, thu hồi trust cũ, kiểm tra phiên đã phát và test rằng token từ repo cũ không thể nhận session mới.

### Bài 6. Leaver đã disable SSO

**Tình huống:** Người dùng rời công ty, IdP disable nhưng một IAM role assignment trực tiếp và một key vẫn còn.

**Đáp án:** Leaver chưa đạt trạng thái VERIFIED. Phải thu hồi grant/key, rà soát đường khác, xử lý session theo hỗ trợ và ghi bằng chứng tại target.

### Bài 7. Break-glass ít dùng

**Tình huống:** Role khẩn cấp production không được dùng trong 90 ngày. Có nên xóa tự động không?

**Đáp án:** Không chỉ vì không được sử dụng. Cần đối chiếu runbook DR, owner, phương thức bảo vệ, cảnh báo và kiểm tra định kỳ; chỉ retire nếu không còn nhu cầu được phê duyệt.

## 27. Checklist kiểm soát cloud privilege escalation

1. **Định danh đúng:** Principal nguồn và đích có stable ID, issuer, owner và trạng thái JML.
2. **Quyền trực tiếp:** Review action/resource/scope/conditions, không chỉ role name.
3. **Quyền gián tiếp:** Kiểm tra sửa IAM, trust, role assignment, credential, impersonation, deployment, CI/CD.
4. **Trust:** Giới hạn issuer, audience, subject, external principal và điều kiện phù hợp.
5. **Service identity:** Managed identity/service account có quyền tối thiểu và vòng đời riêng.
6. **Quyền credential:** Ai tạo/đọc/rotate key, token hoặc secret của principal đặc quyền?
7. **Phân tách nhiệm vụ:** Request, approval, execution và review không bị một principal kiểm soát trọn vẹn khi rủi ro cao.
8. **JIT/PAM/PIM:** Quyền production nhạy cảm có thời hạn, xác thực mạnh và audit khi phù hợp.
9. **CI/CD:** Repository, branch, workflow, runner, environment approval và cloud role được bảo vệ.
10. **Kubernetes:** Phân biệt RBAC cluster và cloud IAM, hạn chế quyền sửa identity/Pod.
11. **Cross-boundary:** Account, tenant, partner trust và resource policy có owner và review.
12. **Guardrails:** Deny/boundaries/org policies được kiểm tra nhưng không thay thế least privilege.
13. **JML con người:** Mover rút quyền cũ; Leaver thu hồi role, key, session và direct grants.
14. **JML workload:** Đổi repository/owner/môi trường phải đổi trust; retire phải gỡ grant và credential.
15. **Detection:** Log IAM changes, token issuance, role assumption, deployment và dấu hiệu quyền gián tiếp.
16. **Policy-as-code:** Có diff, test negative cases, approval và kiểm soát drift.
17. **Verification:** Đọc lại cloud target và kiểm tra effective access sau remediation.
18. **Audit/exception:** Lưu đủ bằng chứng; phiên chưa thể hủy ngay có owner và hạn xử lý.

## 28. Tổng kết

**Cloud privilege escalation** không chỉ là việc một principal được gán role Administrator. Rủi ro thường xuất hiện từ **tổ hợp quyền**: sửa IAM policy hoặc trust, quản lý role assignment, dùng service account, tạo credential, sửa workload/CI/CD hoặc đi qua ranh giới cross-account/cross-tenant. AWS, Azure và Google Cloud có cơ chế riêng, nhưng đều cần đánh giá **danh tính nguồn – quyền trực tiếp – đường ủy quyền – resource scope – điều kiện thực thi**.

Trong quản lý vòng đời danh tính, **Joiner–Mover–Leaver** phải thu hồi cả quyền cũ **và khả năng nhận quyền mới qua đường gián tiếp**. Kết hợp IdP/SSO/SCIM hoặc provisioning, RBAC/ABAC, least privilege, SoD, PAM/JIT, workload identity, policy-as-code, logging và access review giúp giảm blast radius. Kết quả remediation chỉ được coi là hoàn tất khi **quyền thực tế tại cloud target đã được xác minh**, credential và phiên còn hiệu lực được xử lý theo khả năng provider, và mọi ngoại lệ có owner cùng bằng chứng kiểm toán.
