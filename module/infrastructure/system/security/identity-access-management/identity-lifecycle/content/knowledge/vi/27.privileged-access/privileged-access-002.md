# Privileged account: tài khoản đặc quyền trong quản lý vòng đời danh tính IAM

> **Chương: Privileged access.** **Privileged account** là tài khoản hoặc định danh được trao khả năng thực hiện những thao tác có tác động lớn tới hệ thống, dữ liệu hoặc các danh tính khác, chẳng hạn tạo tài khoản, cấp quyền, thay đổi cấu hình bảo mật, xem dữ liệu nhạy cảm, quản trị máy chủ, thay đổi hạ tầng cloud hoặc khôi phục dịch vụ. Quản lý tài khoản đặc quyền không chỉ là đặt mật khẩu mạnh: tổ chức phải biết **ai hoặc workload nào sở hữu quyền**, **vì sao được cấp**, **khi nào quyền có hiệu lực**, **ai phê duyệt**, **cách xác thực**, **cách giám sát phiên** và **cách thu hồi khi Joiner–Mover–Leaver**. Trọng tâm của bài là giảm đặc quyền thường trực và quyền truy cập tồn dư bằng IAM, IdP/SSO, SCIM, RBAC/ABAC và Privileged Access Management (PAM).

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **privileged account** và phân biệt với **privileged access**, **privileged role**, **privileged credential**, **privileged session** và account thông thường.
2. Nhận diện các loại account đặc quyền: **named admin, root/built-in, local admin, domain admin, cloud administrator, SaaS super-admin, service/workload, automation, vendor và break-glass**.
3. Thiết kế inventory và liên kết **human identity ↔ privileged account ↔ role/entitlement ↔ resource**, có owner, mục đích và ngày hiệu lực.
4. Áp dụng **least privilege**, tách account thường/đặc quyền, **JIT/JEA**, PAM/PIM, MFA chống phishing, credential vault, quản lý phiên và phê duyệt theo rủi ro.
5. Tổ chức các bước cấp, thay đổi, thu hồi và kiểm chứng quyền đặc quyền theo **Joiner–Mover–Leaver**, kể cả khi account đích, Group, session hoặc token đồng bộ chậm.
6. Phân biệt phạm vi trách nhiệm của **IdP, SSO, SCIM, RBAC/ABAC, PAM** và cơ chế quản trị workload identity.
7. Xây dựng ma trận kiểm thử, quy trình phản ứng sự cố, bằng chứng audit và các chỉ số đo quyền đặc quyền tồn dư.

## 1. Privileged account là gì?

Một tài khoản bình thường có thể đọc ticket được phân công hoặc chỉnh sửa dữ liệu cá nhân. Một tài khoản đặc quyền có thể **đổi quyền của người khác, quản trị tài nguyên, thay đổi bảo vệ an ninh hoặc tác động tới nhiều hệ thống**.

Ví dụ:

- Nhân viên **Lan** dùng account cá nhân để đọc tài liệu; khi cần bảo trì, Lan sử dụng một đường quản trị riêng đã được phê duyệt để thay đổi cấu hình production.
- **Cloud administrator** có quyền gán role, thay đổi network policy hoặc quản lý key.
- **Directory administrator** có thể reset tài khoản, sửa nhóm đặc quyền và thay đổi chính sách xác thực.
- **Database administrator** có thể đọc hoặc thay đổi dữ liệu vượt phạm vi người dùng ứng dụng.
- **Service identity** của công cụ triển khai có quyền thay image, tạo workload hoặc thay cấu hình hệ thống.
- **Break-glass account** được dự phòng cho tình huống khẩn cấp khi hệ thống xác thực hoặc luồng cấp đặc quyền thông thường gặp sự cố.

Tất cả đều có nguy cơ cao, nhưng **không nhất thiết là cùng một kiểu account**. Tài khoản đặc quyền có thể được tạo sẵn, liên kết trực tiếp với một người, dùng bởi workload hoặc chỉ được cấp quyền cao **trong một khoảng thời gian ngắn**.

### Những thuật ngữ không nên đồng nhất

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Privileged account** | Account/identity có khả năng hoặc đang được gán đặc quyền nhạy cảm. | admin-lan, root, cloud-deployer. |
| **Privileged role** | Tập quyền quản trị định nghĩa trong hệ thống. | OrganizationAdmin, DatabaseOperator. |
| **Privileged entitlement** | Quyền, membership, permission hoặc grant cụ thể. | Được phép rotate key trong project production. |
| **Privileged access** | Khả năng thực thi thao tác đặc quyền trong một bối cảnh. | Được đổi cấu hình firewall trong 30 phút. |
| **Privileged credential** | Chứng cứ xác thực hoặc bí mật cho account/quyền. | Private key, certificate, password, token. |
| **Privileged session** | Phiên tương tác hoặc phiên thực thi có khả năng dùng đặc quyền. | Phiên SSH qua PAM session broker. |
| **Privileged identity** | Chủ thể con người hoặc workload được xác định và quản trị như một thực thể. | Identity của Lan hoặc identity của CI runner. |

**Có account không đồng nghĩa đang có đặc quyền.** Một identity cloud có thể không giữ quyền admin thường trực nhưng được **activate** quyền trong thời hạn JIT. Ngược lại, một Group hoặc service principal có thể tạo hiệu ứng admin dù tên account không chứa chữ “admin”.

### Đặc quyền là thuộc tính của khả năng thực tế

Đừng chỉ tìm account có tên root hoặc administrator. Hãy xét những account có thể:

1. Cấp quyền hoặc đổi password/MFA của người khác.
2. Thay đổi chính sách bảo mật, logging hoặc monitoring.
3. Đọc dữ liệu nhạy cảm quy mô lớn hoặc thực hiện xuất dữ liệu hàng loạt.
4. Thay đổi hệ điều hành, hypervisor, Kubernetes, database, CI/CD hoặc mạng.
5. Tạo/thu hồi credential, secret, token và trust relationship.
6. Vô hiệu hóa các biện pháp kiểm soát hoặc khôi phục hệ thống từ backup.
7. Tự cấp cho mình quyền cao hơn thông qua **role delegation, service impersonation hoặc privilege escalation path**.

Một account chỉ có quyền sửa Group có thể **gián tiếp trở thành admin** nếu Group đó cấp quyền production. Đây là lý do cần đánh giá **effective privileges**, không chỉ danh sách role hiển thị.

## 2. Phân loại các tài khoản đặc quyền

| Loại account | Đặc điểm | Rủi ro điển hình | Hướng quản trị |
| --- | --- | --- | --- |
| **Named human admin** | Gắn với người được định danh; có thể là account quản trị tách riêng. | Bị phishing, cấp quyền quá rộng, không thu hồi khi Mover. | Owner rõ, MFA mạnh, JIT, audit theo người. |
| **Built-in/root account** | Tài khoản có sẵn với hệ điều hành hoặc nền tảng. | Mật khẩu chung, khó quy trách nhiệm, quyền rất rộng. | Hạn chế sử dụng trực tiếp, vault, rotation và session attribution. |
| **Local administrator** | Admin trong phạm vi máy/host cụ thể. | Lateral movement qua mật khẩu giống nhau, account không được kiểm kê. | Credential riêng theo endpoint, quản lý cấu hình, thu hồi local group. |
| **Directory/domain administrator** | Quản trị directory, danh tính và policy. | Có thể tác động nhiều account/hệ thống. | Phân tầng quản trị, đường truy cập bảo vệ, PAM/PIM. |
| **Cloud/tenant administrator** | Quản trị subscription, organization, tài nguyên và IAM policy. | Tự cấp quyền, tạo role/certificate, chiếm quyền lâu dài. | Scope nhỏ, eligible/JIT, kiểm tra trust và audit cloud. |
| **SaaS super-admin** | Quyền quản trị tối cao trong ứng dụng SaaS. | Có account cục bộ ngoài IdP/SCIM, bypass SSO. | Inventory, SSO nếu hỗ trợ, local credential và session revocation. |
| **Database/platform admin** | Quản trị database, cluster hoặc control plane. | Đọc/đổi dữ liệu hàng loạt, chỉnh audit. | Tách quyền quản trị và nghiệp vụ, command/session control. |
| **Service/workload identity** | Chạy không tương tác: daemon, pipeline, tích hợp. | Secret dài hạn, shared credential, owner mồ côi. | Federation/credential ngắn hạn, service owner, rotation. |
| **Automation/deployment bot** | Có thể deploy, chạy IaC hoặc thay cấu hình. | Supply-chain compromise gây thay đổi production. | Least privilege theo pipeline, environment binding, approval. |
| **Vendor/third-party admin** | Đối tác hỗ trợ hoặc vận hành có thời hạn. | Truy cập vượt hợp đồng, dùng account chung. | Named identity/sponsor, time bound, session recording khi phù hợp. |
| **Break-glass/emergency** | Dự phòng khi phương thức quản trị thường gặp sự cố. | Account ít dùng nhưng có quyền cực lớn, bị bỏ quên. | Thủ tục khẩn cấp, bảo quản độc lập, kiểm tra và hậu kiểm nghiêm ngặt. |

Một nền tảng cloud còn có thể dùng **assumed roles**, **temporary credentials** hoặc **federated sessions** thay vì tạo một user admin tồn tại lâu dài. Vẫn phải quản trị **identity, trust, role, session và quyền hiệu lực** dù không có một account cố định truyền thống.

### Interactive và non-interactive

- **Interactive privileged account:** do con người dùng để mở console, RDP, SSH, database client hoặc ứng dụng quản trị.
- **Non-interactive privileged identity:** workload, service principal, CI runner hoặc agent gọi API, thực thi lệnh theo chương trình.

Yêu cầu MFA tương tác cho người dùng không thể áp nguyên xi cho workload. Với danh tính máy cần **workload identity federation, khóa/chứng chỉ hoặc credential ngắn hạn**, ràng buộc môi trường, audience, scope và owner, cùng quy trình thu hồi riêng.

## 3. Vì sao privileged account cần quản lý chặt?

Đặc quyền mở rộng **blast radius**: một account bị chiếm đoạt có thể làm ảnh hưởng nhiều tài khoản, dữ liệu hoặc control plane hơn account thông thường.

### Các chuỗi rủi ro phổ biến

| Rủi ro | Tình huống | Tác động |
| --- | --- | --- |
| **Credential theft/phishing** | Kẻ tấn công có password/session của admin. | Truy cập console, chỉnh cấu hình hoặc cấp thêm quyền. |
| **Standing privileges** | Người dùng giữ admin 24/7 dù chỉ vận hành vài giờ mỗi tháng. | Tăng cửa sổ lạm dụng và tác động khi account bị chiếm. |
| **Shared accounts** | Nhiều người dùng một root password. | Khó quy trách nhiệm; thay nhân sự không biết ai giữ credential. |
| **Privilege escalation** | Account có quyền thay IAM policy hoặc assume role nhạy cảm. | Quyền thực tế lớn hơn danh sách quyền trực tiếp. |
| **Lateral movement** | Credential local admin dùng lại trên nhiều máy. | Một máy bị xâm phạm lan sang máy khác. |
| **Dormant/orphan admins** | Nhân viên nghỉ việc nhưng SaaS còn admin riêng. | Quyền tồn dư lâu dài không owner. |
| **Uncontrolled automation** | CI/CD bot có token production toàn quyền. | Mã build hoặc repository bị xâm phạm có thể thay hạ tầng. |
| **Session/token residue** | PAM grant bị rút nhưng session hoặc token cũ vẫn dùng được. | Tiếp tục thao tác ngoài thời gian được duyệt. |
| **Monitoring bypass** | Admin có thể tắt log và xóa chứng cứ. | Khó phát hiện và điều tra sự cố. |

**Mục tiêu không phải xóa sạch mọi account có quyền cao.** Nhiều hệ thống cần tài khoản quản trị để vận hành và khôi phục. Mục tiêu là **quyền tối thiểu, chỉ tồn tại khi cần, có chủ thể rõ, bị giám sát và thu hồi có kiểm chứng**.

## 4. Inventory: biết chính xác có những account đặc quyền nào

Không thể giảm quyền tồn dư nếu chỉ quản lý account nằm trong IdP mà bỏ quên:

- Local root/admin trên Linux, Windows và thiết bị mạng.
- Built-in emergency account trong cloud/IdP/SaaS.
- SaaS local administrator không bật SSO.
- Service principals, IAM roles, certificates và access keys.
- Kubernetes service accounts, cluster role bindings, secrets.
- Database superusers, automation users và tài khoản backup.
- PAT, API token hoặc SSH key có quyền đặc biệt nhưng không được liệt kê thành “admin account”.

### Inventory tối thiểu

| Thuộc tính | Ý nghĩa |
| --- | --- |
| **accountRef / resource ID** | Định danh duy nhất trong namespace hệ thống đích. |
| **system / tenant / environment** | Account thuộc đâu, production hay non-production. |
| **principal type** | Human, machine, built-in, shared, vendor, break-glass. |
| **identityId / serviceId** | Liên kết chủ thể thật trong IAM hoặc service registry. |
| **owner / sponsor / approver** | Ai chịu trách nhiệm và ai có quyền duyệt. |
| **purpose / business justification** | Tại sao account cần tồn tại và dùng quyền gì. |
| **roles / effective entitlements** | Quyền trực tiếp, kế thừa, delegation và trust. |
| **status** | Active, disabled, eligible, suspended, pending delete... |
| **startAt / endAt / lastUsedAt** | Cửa sổ hợp lệ và dấu hiệu không sử dụng. |
| **credential reference** | Tham chiếu secret/key/certificate, không lưu plaintext. |
| **MFA / session policy** | Mức xác thực, session broker, hạn phiên. |
| **review / evidence timestamps** | Lần xác minh chủ sở hữu và quyền gần nhất. |

Ví dụ bản ghi inventory **nội bộ**, không phải chuẩn SCIM:

~~~json
{
  "accountRef": "cloud:tenant-b:admin-lan",
  "principalType": "HUMAN_PRIVILEGED",
  "identityId": "IAM:ID-2041",
  "owner": "PlatformOperations",
  "system": "CloudControlPlane",
  "tenant": "tenant-b",
  "environment": "production",
  "accessModel": "JIT_ELIGIBLE",
  "eligibleRole": "PlatformOperator",
  "approvedScope": "project-payments",
  "credentialRef": "managed-by-identity-platform",
  "lifecycleStatus": "ACTIVE",
  "reviewedAt": "2026-12-01T08:30:00+07:00"
}
~~~

Không nên đặt **password, private key, recovery code hoặc access token** trong inventory hay ticket. CredentialRef chỉ là tham chiếu tới hệ thống lưu giữ có kiểm soát.

### Identity ↔ account khác nhau

~~~text
HR person        : HRIS:EMP-2041
IAM identity     : IAM:ID-2041
Normal IdP user  : issuer-a / sub-77
Privileged user  : cloud:tenant-b:admin-lan
Database login   : db-prod:ops-lan
PAM identity     : pam:subject-2041
~~~

Các ID này thuộc **namespace khác nhau**; không nên ghép theo email hoặc username duy nhất. Cần account correlation với bằng chứng đáng tin để **thu hồi đúng tất cả tài khoản** mà một người hoặc workload thực sự kiểm soát.

## 5. Vòng đời privileged account và quyền đặc quyền

Một account có thể tồn tại nhiều năm, nhưng quyền admin nên **được cấp và kích hoạt trong phạm vi, thời hạn phù hợp**. Vì vậy phải phân biệt:

1. **Account lifecycle:** tạo, xác minh owner, cho phép đăng nhập, khóa, xóa.
2. **Entitlement lifecycle:** đề nghị, phê duyệt, gán, thay đổi, hết hạn, thu hồi.
3. **Credential lifecycle:** phát hành, lưu giữ, xoay vòng, thu hồi, hết hạn.
4. **Session lifecycle:** xác thực, step-up, mở phiên, giám sát, kết thúc và invalidate.
5. **Identity lifecycle:** Joiner, Mover, Leaver hoặc vòng đời workload tương ứng.

### State machine khái niệm

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> APPROVED: Identity + nhu cầu + approval đạt
    REQUESTED --> REJECTED: Không đạt policy
    APPROVED --> PROVISIONED: Tạo hoặc liên kết account
    PROVISIONED --> ELIGIBLE: Account hợp lệ, chưa active admin
    ELIGIBLE --> ACTIVE_JIT: Request activation + MFA + JIT
    ACTIVE_JIT --> ELIGIBLE: Hết hạn quyền / kết thúc phiên
    ELIGIBLE --> SUSPENDED: Đình chỉ / rủi ro
    ACTIVE_JIT --> SUSPENDED: Thu hồi khẩn cấp
    ELIGIBLE --> REVOKED: Leaver / thu hồi toàn bộ
    SUSPENDED --> REVOKED: Kết thúc quan hệ / quyết định
    REVOKED --> VERIFIED: Readback account + quyền + session
    VERIFIED --> [*]
    REJECTED --> [*]
~~~

Đây là **mô hình giáo dục**, không phải trạng thái bắt buộc của một công cụ PAM/PIM. Một hệ thống có thể có account ACTIVE nhưng không có role admin thường trực; một hệ thống khác không có trạng thái ELIGIBLE. Điều cần giữ là phân biệt **khả năng được cấp quyền** với **quyền đang có thể sử dụng**.

### Standing privilege và JIT

| Mô hình | Cách hoạt động | Ưu điểm | Rủi ro/đánh đổi |
| --- | --- | --- | --- |
| **Standing privilege** | Account giữ quyền admin liên tục. | Đơn giản, ít bước khi cần thao tác. | Cửa sổ lạm dụng lớn, dễ tạo quyền lâu ngày không rà soát. |
| **Eligible/JIT activation** | User đủ điều kiện nhưng chỉ kích hoạt quyền khi cần trong một thời hạn. | Giảm thời gian quyền có thể sử dụng. | Cần quy trình phê duyệt, MFA, quản trị session và availability phù hợp. |
| **Ephemeral credential/session** | Cấp credential ngắn hạn cho phiên hoặc tác vụ. | Giảm bí mật dài hạn; tiện audit theo phiên. | Phải bảo vệ kênh cấp, quyền thực tế và kiểm soát token đã phát. |
| **Just Enough Administration (JEA)** | Chỉ cho phép tập thao tác nhỏ cần thiết. | Thu nhỏ blast radius dù có quyền vận hành. | Cần mô hình hóa command/API/resource cẩn thận. |
| **PAM broker/session manager** | Trung gian truy cập và kiểm soát phiên đặc quyền. | Hỗ trợ vault, approval, recording, attribution. | Phụ thuộc tính năng và việc mọi đường truy cập có thực sự đi qua broker. |

**JIT không tự động là least privilege.** Nếu một User kích hoạt role GlobalAdmin trong 15 phút để chạy một lệnh nhỏ, thời gian đã giảm nhưng **phạm vi quyền vẫn rất rộng**. Nên kết hợp JIT với JEA, resource scope và kiểm tra điều kiện.

## 6. Tách account thông thường và account quản trị

Một mẫu kiểm soát là **không dùng cùng một phiên/quyền thường trực** cho cả email, web browsing và quản trị production.

Ví dụ:

~~~text
identity: ID-LAN-2041
  normal account: lan@company.example
      - email, wiki, ticket
      - không có role quản trị production

  privileged access path:
      - account hoặc role admin được liên kết với ID-LAN-2041
      - yêu cầu MFA/step-up và phê duyệt khi cần
      - chỉ scope production đã được giao
      - JIT 30 phút, được audit
~~~

Đây là mẫu kiến trúc, không có nghĩa mọi nền tảng phải tạo hai username. Một số hệ thống có thể dùng **một subject được xác minh nhưng hai authentication contexts/session riêng** hoặc **role assumption có thời hạn**. Mục tiêu là phân tách **ngữ cảnh sử dụng quyền**, giảm credential exposure và đảm bảo trách nhiệm cá nhân.

### Các nguyên tắc vận hành

- Không dùng account admin thường xuyên cho email, chat hoặc duyệt web thông thường.
- Không chia sẻ named admin credential giữa nhiều người.
- Phân tách production và non-production; không tự đồng nhất credential và quyền.
- Tài khoản có thể quản trị IdP, khóa tài khoản hoặc thay trust cần được bảo vệ mạnh hơn account thường.
- Đảm bảo admin không tự phê duyệt yêu cầu cấp đặc quyền của chính mình khi SoD yêu cầu tách vai trò.
- Duy trì đủ đường khôi phục hợp lệ nếu IdP/PAM gặp lỗi, nhưng không biến đường khôi phục thành tài khoản không kiểm soát.

## 7. Cấp privileged account: từ đề nghị tới xác minh

Quy trình cấp một account/quyền admin nên có căn cứ và bằng chứng.

~~~mermaid
flowchart TD
    A["Nhu cầu nghiệp vụ / Joiner / Mover"] --> B["Resolve identity + proofing<br/>hoặc service/workload owner"]
    B --> C["Chọn role, action, resource,<br/>tenant, environment, start/end"]
    C --> D["Risk + SoD + approval checks"]
    D --> E{"Đủ điều kiện?"}
    E -->|Không| N["REJECTED / REVIEW<br/>không cấp quyền"]
    E -->|Có| F["Provision account / eligible role<br/>qua đúng connector"]
    F --> G["MFA / credential / device controls"]
    G --> H["JIT activation khi cần<br/>session policy"]
    H --> I["Readback local account,<br/>role, trust và effective rights"]
    I --> J{"Khớp scope/time được duyệt?"}
    J -->|Có| K["VERIFIED + audit"]
    J -->|Không| L["PARTIAL_FAILURE<br/>reconcile, owner, compensation"]
~~~

### Đề nghị quyền cần những thông tin gì?

| Trường | Ví dụ | Vì sao cần |
| --- | --- | --- |
| Requester / identity | IAM:ID-2041 | Quy được hành động về một người hoặc workload. |
| Resource owner | Platform Lead | Người chịu trách nhiệm phạm vi cấp quyền. |
| Privileged role/permissions | KubernetesNamespaceOperator | Tránh cấp GlobalAdmin nếu chỉ cần namespace. |
| Resource scope | prod-cluster / payments namespace | Giới hạn tác động. |
| Business justification | Khắc phục sự cố batch payment | Có căn cứ nghiệp vụ và audit. |
| StartAt / EndAt | 09:00–09:30 theo timezone rõ | Quyền tự hết hiệu lực. |
| Approval/SoD result | ticket/approval reference | Tránh tự phê duyệt hoặc đặc quyền vượt nhiệm vụ. |
| Authentication requirements | phishing-resistant MFA, reauth | Phòng chiếm phiên và phishing. |
| Monitoring/session requirements | audit, command log/recording | Phát hiện thao tác nhạy cảm. |

Việc **provision thành công** chỉ là một kết quả kỹ thuật. Cần đọc lại quyền, kiểm tra account đúng identity/tenant, đúng scope và **không có đường escalation** vượt ngoài phạm vi đã duyệt.

## 8. Least privilege, RBAC, ABAC và policy đặc quyền

### RBAC: cấp đúng role

Role quản trị nên được thiết kế **theo nhiệm vụ**, không gộp tất cả công việc vào một vai trò SuperAdmin:

| Nhiệm vụ | Quyền minh họa | Không nên tự bao gồm |
| --- | --- | --- |
| Đọc cấu hình production | config.read trong project | Thay đổi IAM policy hoặc xóa workload. |
| Rotate secret ứng dụng | secret.rotate trên secret được giao | Đọc mọi secret của tenant. |
| Triển khai một service | deploy.update trong namespace | Gán role admin toàn cluster. |
| Hỗ trợ reset user | user.resetCredential theo phạm vi | Tự mở khóa và cấp admin cho chính mình. |
| Xem audit security | audit.read | Xóa hoặc tắt audit. |

Phải kiểm tra cả **quyền gián tiếp**: một role chỉ có quyền “edit role bindings” có thể tương đương quyền admin nếu nó tự gán quyền cao hơn cho chính chủ thể.

### ABAC/PBAC: giới hạn theo bối cảnh

Một policy minh họa:

~~~text
PERMIT production.service.restart KHI
    subject.lifecycleState == ACTIVE
    AND subject.hasApprovedRole("ServiceOperator")
    AND subject.tenantId == service.tenantId
    AND service.projectId in subject.approvedProjectIds
    AND privilegedGrant.isActiveAt(now)
    AND privilegedGrant.approvedAction includes "service.restart"
    AND session.authenticationProfile meets resource.privilegedProfile
    AND session.isWithinPAMPolicy
ELSE: NO_PERMIT
~~~

Các điều kiện này kết hợp **RBAC + ABAC + PBAC**, với thời hạn và assurance. Không phải policy syntax chuẩn của một nền tảng cụ thể.

### Deny tường minh và hard guards

~~~text
DENY privileged.* KHI identity.lifecycleState == TERMINATED
DENY privileged.* KHI identity.lifecycleState == SUSPENDED
DENY production.* KHI resource.tenantId khác subject.tenantId
DENY access.assignRole KHI requester tự phê duyệt trái SoD
DENY privileged.* KHI JIT grant đã hết hạn
~~~

Một **Permit theo role** không được bỏ qua các điều kiện hard Deny. Cần xác định combining semantics, PEP thực thi và xử lý dữ liệu không đủ tin cậy theo chính sách.

## 9. Xác thực mạnh và bảo vệ phiên admin

Tài khoản đặc quyền là mục tiêu có giá trị cao của phishing, đánh cắp cookie, session hijack và đánh cắp credential.

### MFA cho privileged account

- Dùng **phương thức MFA đáp ứng mức rủi ro và chính sách**, ưu tiên cơ chế **phishing-resistant** cho đặc quyền quan trọng khi được hỗ trợ.
- **Passkey/WebAuthn/FIDO2** triển khai đúng kiểm tra relying party/origin có khả năng chống phishing mạnh hơn cơ chế nhập OTP/chấp thuận push thông thường.
- **Push number matching** giảm phê duyệt nhầm nhưng không mặc nhiên chống phishing thời gian thực.
- **TOTP và SMS OTP** có thể bị phishing/chuyển tiếp; không tự coi là bảo đảm ngang passkey.
- Có thể yêu cầu **reauthentication/step-up** khi chuyển từ phiên thường sang phiên admin.
- Bảo vệ **enrollment, reset MFA và recovery**; helpdesk reset yếu có thể trở thành lối vào account admin.

### Privileged session

Một phiên đặc quyền nên được quản lý riêng:

| Kiểm soát | Câu hỏi cần làm rõ |
| --- | --- |
| **Session establishment** | Ai mở phiên, từ thiết bị nào, qua broker/trust nào? |
| **Session scope** | Chỉ được thao tác trên host/resource nào, lệnh nào? |
| **Idle timeout / absolute timeout** | Bao lâu không hoạt động hoặc tối đa bao lâu thì phiên kết thúc? |
| **Step-up** | Những action nào buộc xác thực mạnh hoặc phê duyệt bổ sung? |
| **Recording/logging** | Ghi loại hành động nào, ai được xem, thời gian lưu giữ? |
| **Concurrent session limit** | Có giới hạn bao nhiêu phiên admin đồng thời không? |
| **Revocation** | Sau Mover/Leaver, có đóng được phiên SSH/RDP/console hiện có không? |
| **Credential exposure** | Người dùng có thấy secret trực tiếp hay qua injection/broker? |

**Hết JIT grant không tự bảo đảm phiên SSH hoặc token cloud đã mở trước đó lập tức bị hủy.** Cần kiểm tra khả năng thu hồi phiên/credential/token của từng nền tảng và ranh giới thời gian được chấp nhận.

### Thiết bị quản trị và nơi thực hiện

Với quyền nhạy cảm, tổ chức có thể sử dụng **Privileged Access Workstation (PAW)**, host quản trị chuyên biệt, mạng quản trị được giới hạn hoặc session broker. Điều đó giúp tách hoạt động admin khỏi môi trường duyệt web/email rủi ro hơn.

Không xem một kiểm tra device posture đơn lẻ là bảo đảm tuyệt đối; tín hiệu posture có thể trễ hoặc bị giả mạo nếu nguồn không đủ tin cậy. Phải kết hợp identity, thiết bị, phiên, action và resource.

## 10. Quản lý credential và secret của privileged account

**Credential** thường là một trong những đường tấn công trực tiếp nhất. Các loại thường gặp:

- Password của local/root/built-in account.
- SSH key, certificate hoặc khóa ký dùng cho truy cập admin.
- Cloud API key, service principal secret, token của công cụ deploy.
- Recovery code và emergency credential.
- PAM vault credential được checkout/inject theo phiên.
- Short-lived certificate/token được phát từ workload federation.

### Quy tắc quản lý

1. **Không lưu bí mật trong code, ticket, wiki công khai hoặc log.**
2. Dùng secret store/vault hoặc cơ chế identity federation phù hợp, có phân quyền truy cập và audit.
3. Ưu tiên credential ngắn hạn và được ràng buộc đúng audience, role, host, environment, service khi kiến trúc hỗ trợ.
4. Với credential tĩnh phải có quy trình rotate/revoke, nhất là sau sự cố, thay người quản trị hoặc lộ secret.
5. Không cho các host dùng cùng một local administrator password nếu có thể quản lý riêng để giảm lateral movement.
6. Xác định credential nào thuộc người, thuộc workload, thuộc account built-in và thuộc vendor.
7. Kiểm thử secret checkout, rotate và thu hồi thực tế, không chỉ kiểm tra secret manager đã đổi một field.

### Vault không tự giải quyết mọi vấn đề

Nếu một account có password được vault quản lý nhưng còn một **SSH key không kiểm kê**, một **API token cũ** hoặc **session hiện hữu**, người không còn được cấp quyền vẫn có thể truy cập qua đường khác. Vault phải nằm trong **inventory credential và đường truy cập**, kết hợp chính sách PEP/PAM và kiểm chứng đích.

### Tránh làm gián đoạn hệ thống khi rotate

Với account dịch vụ, rotation phải xét dependency: pipeline, daemon, agent, secret sync, certificate chain và cách refresh credential. Nên quản lý thay đổi theo phiên bản, kiểm tra ứng dụng đã sử dụng credential mới và thu hồi credential cũ đúng lúc. Không xóa toàn bộ secret production chỉ vì owner nhân sự nghỉ việc mà chưa có phương án thay thế dịch vụ.

## 11. PAM/PIM, JIT và đường truy cập đặc quyền

**Privileged Access Management (PAM)** là tập thực hành/công cụ để quản lý, cấp và kiểm soát truy cập đặc quyền, thường bao gồm **credential vault, session brokering, approval, recording, rotation và revocation**. **Privileged Identity Management (PIM)** thường nhấn mạnh quản lý **eligibility/activation** của role đặc quyền theo thời gian. Tên tính năng và ranh giới phụ thuộc nhà cung cấp; hai khái niệm có thể chồng lấn.

### Luồng JIT điển hình

~~~mermaid
sequenceDiagram
    actor U as Admin đã định danh
    participant IdP as IdP / MFA
    participant PAM as PAM / PIM
    participant IGA as IAM / IGA Policy
    participant Target as Production Target
    participant Audit as Audit
    U->>PAM: Yêu cầu quyền/service/action + thời hạn
    PAM->>IGA: Kiểm tra identity, lifecycle, owner, SoD, approval
    IGA-->>PAM: Được phép / từ chối theo policy
    PAM->>IdP: Yêu cầu reauthentication/step-up khi cần
    IdP-->>PAM: Authentication context đáng tin
    PAM->>Target: Cấp role/credential/session giới hạn
    PAM->>Audit: Ghi kích hoạt, scope, thời hạn
    U->>Target: Thực hiện thao tác trong phạm vi cho phép
    PAM->>Target: Hết hạn hoặc thu hồi quyền/phiên
    Target-->>PAM: Readback trạng thái
    PAM->>Audit: Kết quả verify và residual access
~~~

Luồng minh họa không có nghĩa công cụ PAM nào cũng tự ngắt mọi phiên, rotate mọi credential hoặc nhận đầy đủ dữ liệu HR. Trước khi dựa vào một tính năng, phải **thử nghiệm ở hệ thống đích**.

### Just in Time khác Just Enough Administration

- **JIT:** *khi nào* quyền được kích hoạt và bao lâu tồn tại.
- **JEA:** *được phép làm gì* khi quyền đang hiệu lực.
- **PAM session controls:** *đường truy cập nào, giám sát ra sao và thu hồi thế nào*.

Kết hợp cả ba cho ví dụ: Lan chỉ được restart dịch vụ Payments trong 30 phút, trên namespace được giao, qua một phiên có MFA mạnh và audit; Lan không được thay IAM policy của toàn cluster.

## 12. Privileged account trong Joiner

**Joiner** là lúc tài khoản và quyền đặc quyền có thể bị cấp quá sớm hoặc quá rộng, nhất là khi tự động sao chép quyền của người tiền nhiệm.

### Quy trình Joiner

1. Nhận hồ sơ từ **HR/nguồn hợp đồng có thẩm quyền**, có identity key và ngày bắt đầu.
2. Thực hiện identity proofing, đối chiếu chống trùng và liên kết account theo chính sách.
3. Xác định chức danh/nhiệm vụ có thật sự cần quyền đặc quyền hay không; mặc định **không cấp admin** cho mọi nhân viên kỹ thuật.
4. Resource owner/IGA phê duyệt phạm vi role, tenant, environment, thời hạn và kiểm tra SoD.
5. Tạo hoặc liên kết đường quản trị; ưu tiên eligible/JIT thay vì standing admin khi phù hợp.
6. Enrollment MFA và thiết bị quản trị theo mức rủi ro; không dùng recovery yếu.
7. Không để account pre-provisioned sử dụng quyền nghiệp vụ/production **trước thời điểm hiệu lực**.
8. Readback quyền tại đích, kiểm tra có thể đăng nhập đúng cách **và không có quyền ngoài phạm vi**.

### Pre-provisioning và kích hoạt

~~~text
HR startAt            = 2026-12-01 09:00 +07:00
IAM identity created  = 2026-11-29
Privileged account    = pre-provisioned, disabled/eligible-only
Admin activation      = sau startAt + approval + MFA/step-up

Không hợp lệ:
    account đã tạo => production admin được dùng từ 29/11
~~~

Một account có thể chuẩn bị trước để giảm độ trễ onboarding, nhưng phải có biện pháp **chặn truy cập hiệu lực ở IdP, role/JIT và ứng dụng đích**, không chỉ một trạng thái hiển thị trong IAM.

### Sai lầm Joiner thường gặp

- Sao chép toàn bộ nhóm admin của người quản lý/nhân viên tiền nhiệm.
- Dùng account admin chia sẻ vì “chưa kịp tạo account cá nhân”.
- Đăng ký MFA bằng email/điện thoại chưa xác minh chủ thể.
- Cấp quyền production trong khi nhân viên vẫn ở trạng thái PENDING_ACTIVATION.
- Gán role GlobalAdmin cho mục đích onboarding một ứng dụng nhỏ.
- Không kiểm chứng account đã được liên kết đúng identity, tenant và resource.

## 13. Privileged account trong Mover

**Mover** có thể là chuyển team, chức danh, tenant, project, nhiệm vụ vận hành hoặc thay chủ sở hữu service account. Rủi ro lớn là **tích lũy đặc quyền**.

### Ví dụ chuyển vai trò

Lan là SupportAdmin rồi chuyển sang FinanceOps:

| Quyền | Trước Mover | Sau Mover mong muốn | Hành động |
| --- | --- | --- | --- |
| SupportConsoleAdmin | Có | Không | Thu hồi. |
| ProductionSSH-OldProject | Có theo JIT | Không | Gỡ eligibility, đóng/review phiên. |
| FinanceReportReader | Không | Có nếu được duyệt | Cấp role có scope. |
| PayrollAdmin | Không | Không nếu chưa được duyệt | Không tự thêm. |
| Shared root password từng biết | Có thể đã truy cập | Không còn | Rotate/revoke hoặc bảo vệ đường truy cập theo đánh giá rủi ro. |
| Local vendor admin tại SaaS | Có thể tồn tại | Không | Đối soát đường local auth và thu hồi. |

**Không dùng phép hợp quyền “oldRoles ∪ newRoles”** làm trạng thái mặc định sau Mover. Phải tính **desired access hiện hành**, giữ ngoại lệ hợp lệ có căn cứ, và gỡ quyền không còn phù hợp.

### Những câu hỏi quan trọng

- Có role admin nào được gán trực tiếp ngoài IGA/SCIM không?
- Group cũ đã bị gỡ ở IdP nhưng session, JWT hoặc cookie vẫn mang quyền cũ không?
- Người chuyển vai trò còn biết shared credential hoặc giữ SSH key/secret trước đây không?
- Những JIT eligibility, delegation/assume-role trust, API token và certificate cũ còn sử dụng được không?
- Role mới có yêu cầu MFA mạnh hơn, PAM, SoD hay phê duyệt khác không?
- Thay đổi quyền đã được **readback ở Resource Server/target** chưa?

### Không cần đăng ký lại mọi thứ một cách máy móc

Mover không nhất thiết phải xóa identity hoặc toàn bộ authenticator nếu chính chủ thể và thiết bị vẫn hợp lệ. Nhưng phải **đánh giá lại authentication assurance** khi chuyển sang phạm vi nhạy cảm hơn, và buộc step-up/credential mới nếu chính sách yêu cầu.

## 14. Privileged account trong Leaver

**Leaver** là trường hợp phải xử lý đặc quyền như **một tập đường truy cập**, không chỉ một account IdP.

### Danh mục đường truy cập cần thu hồi

1. **IdP sign-in** và những session xác thực trung tâm.
2. **Named privileged accounts** tại directory, cloud, SaaS, database và host.
3. **Role/Group/JIT eligibility** và entitlement được cấp trực tiếp.
4. **PAM checkout/activation** đang mở, broker session hoặc credential đã phát.
5. **App-local admin sessions**, console session, SSH/RDP session.
6. **Access/refresh tokens**, PAT, API keys, SSH keys, certificate và trust được quản trị riêng.
7. **Shared/built-in credential** mà người rời đi từng biết hoặc có thể lấy được.
8. **Vendor/sponsor associations** và quyền quản trị gián tiếp.
9. **Service account ownership** và secret liên quan tới cá nhân rời đi.

### Quy trình Leaver

~~~mermaid
flowchart TD
    A["Leaver từ nguồn HR<br/>effectiveAt + sourceVersion"] --> B["Resolve identity<br/>và tất cả privileged paths"]
    B --> C["Chặn sign-in và cấp quyền mới<br/>ở IdP/PAM/IGA"]
    C --> D["Disable named admins<br/>revoke eligible/active roles"]
    D --> E["Đóng/revoke sessions,<br/>tokens, credentials khi hỗ trợ"]
    E --> F["Thu hồi Group/local role<br/>SCIM/API, SSH key, PAT"]
    F --> G["Đánh giá shared secrets,<br/>rotation và service ownership"]
    G --> H["Readback account/role/session<br/>kiểm thử quyền ở đích"]
    H --> I{"Đã đạt policy boundary?"}
    I -->|Có| J["REVOKED_VERIFIED<br/>audit + evidence"]
    I -->|Chưa| K["PARTIAL_FAILURE<br/>owner, retry, containment"]
~~~

Trong thực tế, nhiều bước cần chạy **song song** ngay khi Leaver có hiệu lực để giảm thời gian tồn dư; sơ đồ chỉ giúp kiểm tra **không bỏ sót lớp**.

### Disable IdP khác revoke quyền tại API

Một User đã bị IdP vô hiệu hóa vẫn có thể có:

- Cookie session ở SaaS không tích hợp logout.
- JWT access token còn hạn được API kiểm offline.
- PAT/SSH key được hệ thống đích quản lý riêng.
- Account admin cục bộ không qua SSO.
- Khả năng dùng shared password chưa được rotate.

Do vậy, **SCIM active=false**, **IdP disabled** hoặc **PAM role revoked** chỉ chứng minh những thay đổi trong phạm vi của các hệ thống ấy. Muốn tuyên bố hoàn tất Leaver, cần kiểm chứng **effective privileged access** ở những đường được yêu cầu bởi chính sách.

### Leaver và race condition

~~~text
v41 JOINER: tạo admin eligibility
v42 MOVER : gỡ project-A, thêm project-B
v43 LEAVER: revoke mọi privileged access

Thứ tự thực thi:
    v43 hoàn tất trước
    job v41 retry sau timeout

Yêu cầu:
    v41 không được kích hoạt lại eligibility sau Leaver
~~~

Đặt guard cho mọi thao tác **cấp đặc quyền**: kiểm tra lifecycle state mới nhất, nguồn và phiên bản sự kiện, thời điểm hiệu lực, phê duyệt còn hạn và idempotency. Không chỉ kiểm tra ở bước nhận event rồi để worker cũ ghi đè trạng thái mới.

## 15. Suspend, rehire, contractor và vendor

### Suspend

Đình chỉ tạm thời cần chính sách riêng về thời điểm chặn và điều kiện khôi phục. Có thể giữ account để bảo toàn dữ liệu/audit nhưng không cho tạo phiên mới; những phiên/credential đã cấp cần xử lý theo rủi ro. **Suspend không mặc nhiên là xóa account.**

### Rehire

Nếu một nhân viên trở lại với vị trí mới, không được **tự khôi phục toàn bộ quyền admin, token, JIT eligibility hoặc ngoại lệ** trước đây. Phải xác minh đúng người, liên kết lại identity theo policy, làm mới credential/enrollment nếu cần và cấp quyền theo công việc hiện tại.

### Contractor/vendor

Với nhà thầu/đối tác:

- Có **sponsor/owner nội bộ** và ngày hết hợp đồng.
- Dùng account định danh riêng khi có thể; không chia sẻ root password để hỗ trợ tiện.
- Giới hạn tenant, tài nguyên, lệnh, giờ hỗ trợ và session.
- Buộc phê duyệt/step-up đúng policy và thu hồi khi hợp đồng hết hoặc sponsor thay đổi.
- Đối soát tài khoản cục bộ do vendor tạo và credential còn nằm ngoài IdP.

### Đường break-glass sau thay đổi nhân sự

Khi người từng biết emergency credential rời tổ chức, cần xem xét rotate/đổi người quản lý bí mật theo chính sách mà **không làm mất khả năng khôi phục khẩn cấp**. Việc kiểm chứng đường khẩn cấp phải có ghi nhận và được thực hiện an toàn, tránh thử nghiệm bừa bãi trên production.

## 16. Break-glass và emergency privileged account

**Break-glass** là khả năng truy cập khẩn cấp khi luồng quản trị thông thường không khả dụng, ví dụ lỗi IdP liên kết, lỗi PAM/PIM hoặc sự cố thay đổi policy khiến admin bị khóa ngoài.

Nó **không** nên là một đường tắt được dùng hàng ngày và không đồng nghĩa bypass mọi điều kiện an ninh.

### Thiết kế căn bản

| Yêu cầu | Mục đích |
| --- | --- |
| Tách biệt hợp lý với phụ thuộc có thể lỗi | Đảm bảo đường khôi phục hoạt động trong tình huống IdP/PAM gặp sự cố đã dự liệu. |
| Số lượng tối thiểu và owner rõ | Giảm tài khoản emergency không được kiểm soát. |
| Credential/hardware được bảo quản an toàn | Hạn chế bị lấy cắp hoặc lạm dụng. |
| Cảnh báo khi dùng | Phát hiện mọi lần emergency login nhanh chóng. |
| Phê duyệt/justification nếu quy trình cho phép | Tránh sử dụng vì tiện. |
| Time-bound hậu kiểm | Xác định ai dùng, đã làm gì và vì sao. |
| Rotate/reseal sau sử dụng theo chính sách | Ngăn bí mật bị tiếp tục khai thác. |
| Diễn tập có kiểm soát | Xác nhận đường khẩn cấp còn hoạt động khi cần. |

Một giải pháp chỉ có admin JIT phụ thuộc hoàn toàn vào một IdP duy nhất có thể gây **lockout risk** khi IdP lỗi. Cần thiết kế resilience theo rủi ro, song không dùng điều đó để tạo một super-admin bí mật không owner hoặc không được audit.

### Trạng thái emergency cần được tách

Không nhất thiết mọi tài khoản break-glass đều có cùng MFA hoặc SSO với account thường, vì một mục tiêu có thể là khôi phục khi phụ thuộc bị lỗi. **Các biện pháp bù** phải được thiết kế có chủ đích, ví dụ bảo quản credential ở vị trí độc lập, yêu cầu nhiều người tiếp cận, alert và hậu kiểm. Không mặc định “không MFA” là an toàn hay bắt buộc; phụ thuộc nền tảng và threat model.

## 17. Service account, workload identity và quyền máy

Một **non-human privileged account** có thể quản lý hạ tầng nhiều hơn con người. Ví dụ CI pipeline có quyền deploy production, secret rotation service có quyền quản lý credential và backup service có thể đọc snapshot nhạy cảm.

### Đặc thù khác account người dùng

| Khía cạnh | Human admin | Workload/service identity |
| --- | --- | --- |
| Chủ thể | Cá nhân được HR/IAM quản lý. | Dịch vụ, job hoặc workload có owner kỹ thuật. |
| Xác thực | MFA, passkey, session, PAM theo chính sách. | Federation, client credentials, mTLS, certificate, workload token. |
| Vòng đời | Joiner–Mover–Leaver của người. | Tạo, thay đổi owner/scope, deploy, decommission của dịch vụ. |
| Quyền | Nhiệm vụ con người và phê duyệt. | API/action/resource theo service purpose. |
| Credential | Password, device authenticator, key. | Token, signing key, certificate, secret hoặc trust assertion. |
| Thu hồi | Gỡ account/role, session, credential. | Revoke principal, trust, token, role, secret và dependency. |

### Nguyên tắc an toàn

1. Mỗi workload cần **service owner**, mục đích và inventory.
2. Ràng buộc identity với cluster/environment/service khi có thể; không tái dùng credential production ở staging.
3. Cấp đúng audience, scope, resource và thời hạn.
4. Ưu tiên **federated/ephemeral identity** thay secret dài hạn khi nền tảng hỗ trợ.
5. Quản lý key/certificate và token lifecycle riêng; không dùng chung password giữa nhiều job.
6. Khi service owner nghỉ việc, **chuyển owner và rotate credential do người đó biết**, không xóa mù workload đang phục vụ.
7. Khi workload decommission, thu hồi trust, service principal, role và credential, kiểm tra không còn API access.

### Client credentials và refresh token

Với OAuth 2.0 **client_credentials** thông thường, client có thể xác thực với Authorization Server để xin access token mới; **refresh token thường không được cấp** trong mô hình này. Không thêm một bearer refresh token dài hạn cho workload chỉ vì muốn giảm số lần gọi token endpoint.

Một workload có thể dùng token API còn hạn sau khi owner đã nghỉ việc; vì thế chủ sở hữu **của workload** và trạng thái hoạt động của dịch vụ phải được theo dõi độc lập với employmentStatus của một người.

## 18. IdP/SSO, SCIM, RBAC/ABAC và PAM phối hợp ra sao?

| Lớp | Vai trò chính | Giới hạn cần nhớ |
| --- | --- | --- |
| **HR/contract source** | Sự kiện Joiner/Mover/Leaver của người. | Không nhất thiết biết mọi local admin, secret hay IAM role tại đích. |
| **IAM/IGA** | Identity correlation, desired access, approval, SoD, review. | Desired state không tự chứng minh quyền đích đã hội tụ. |
| **IdP/SSO** | Xác thực, session, authentication context, federation. | Chặn login IdP không tự chấm dứt local session/PAT. |
| **SCIM/connector** | Provision/disable User, Group theo hỗ trợ của ứng dụng. | Không có chuẩn chung tự thu hồi mọi admin credential hoặc session. |
| **RBAC/ABAC/PBAC** | Quyết định quyền dựa trên role, thuộc tính, policy. | Phải có PEP thật ở ứng dụng để cưỡng chế. |
| **PAM/PIM** | Vault, privilege activation, session brokerage, revocation theo tính năng. | JIT expiry không tự hủy mọi token/phiên cũ nếu không tích hợp. |
| **Resource/API** | Thực thi operation với account/role và token thực tế. | Có thể có direct admin role, local accounts và cache riêng. |
| **Audit/reconciliation** | Kiểm tra thay đổi, phát hiện quyền tồn dư và sai lệch. | Log gửi thành công không chứng minh target đã chặn truy cập. |

### Một câu hỏi phải đặt khi tích hợp

**Ứng dụng đích chấp nhận đặc quyền theo con đường nào?** Ví dụ:

- Token OIDC/OAuth có scope admin.
- Session web SaaS có role SuperAdmin.
- SSH key/SSH certificate ở máy chủ.
- Group trong directory/SCIM được ánh xạ sang admin role.
- Local password/built-in account.
- Kubernetes RoleBinding/ClusterRoleBinding.
- Cloud policy/trust cho phép assume role.

Nếu một hệ thống có nhiều đường, **quy trình Leaver/PAM phải bao phủ chúng**, không chỉ một giao thức.

## 19. Quyền hiệu lực và đường leo thang đặc quyền

Không phải lúc nào role name phản ánh được toàn bộ khả năng. **Effective privilege** có thể đến từ:

1. Role được gán trực tiếp.
2. Group membership, nested group hoặc inherited permission.
3. Delegation, role assumption, trust policy.
4. Quyền thay đổi chính sách cấp quyền, tạo credential hoặc impersonate service.
5. Secret/token được checkout hoặc giữ từ trước.
6. Local admin account hoặc quyền qua application service account.
7. Session đã được mở trước khi grant bị thu hồi.

### Ví dụ quyền gián tiếp

~~~text
User có quyền:
    iam.rolePolicy.write

Mặc dù không có GlobalAdmin trực tiếp,
nếu User có thể sửa policy của role mà họ tự assume,
họ có thể tự tạo đường tới quyền cao hơn.

=> Đánh giá cả delegated permissions và khả năng thay đổi trust/policy.
~~~

### Inventory privilege path

~~~mermaid
flowchart LR
    U["Human identity ID-2041"] --> N["Named admin / IdP subject"]
    N --> G["Group / role eligibility"]
    G --> J["JIT active grant"]
    J --> T["Cloud resource / API"]
    N --> S["SaaS local session"]
    S --> T2["SaaS administrative action"]
    U --> V["Known shared credential<br/>or checked-out secret"]
    V --> H["Built-in/local admin"]
    H --> T3["Host / database"]
    W["Workload identity"] --> K["Trust policy + scope"]
    K --> T
~~~

Sơ đồ nêu các đường có thể phát sinh, **không hàm ý mọi người đều có shared credential**. Trong một hệ thống an toàn, những đường không cần thiết nên bị loại bỏ, và các đường cần thiết phải được gắn owner/audit/thời hạn.

## 20. Đối soát privileged account: desired vs observed vs effective

Một hệ thống IAM có thể ghi “Lan không còn role admin” trong khi API đích vẫn chấp nhận token cũ. Vì vậy nên quản trị ba lớp:

- **Desired access:** quyền phải có theo HR, role, approval, policy và thời điểm hiệu lực.
- **Observed configuration:** tài khoản, Group, role, key, trust và trạng thái đang được hệ thống đích báo cáo.
- **Effective access:** hành động mà account/session/token thực sự có thể thực hiện khi được kiểm tra ở resource.

| Desired | Observed | Effective | Kết luận |
| --- | --- | --- | --- |
| Có quyền operator theo JIT | Role active đúng scope | Chỉ restart service được duyệt | MATCH/VERIFIED. |
| Không còn SupportAdmin sau Mover | Group SupportAdmin vẫn còn | Có thể sửa ticket admin | PRIVILEGE_DRIFT. |
| Leaver không được access | IdP disabled | SaaS local session vẫn dùng được | RESIDUAL_ACCESS. |
| Role đã revoke | Role vắng ở directory | JWT cũ vẫn cho API admin | TOKEN/SESSION_RESIDUE. |
| Service còn hoạt động | Credential rotate thành công | CI pipeline chạy bình thường với scope mới | VERIFIED sau kiểm thử thích hợp. |
| Không còn account | API inventory thiếu trang/lỗi | Chưa thể kiểm tra | UNKNOWN, không được báo VERIFIED. |

### Đối soát có hệ thống

1. Liệt kê identity/service và mọi account/credential/role trực tiếp hoặc kế thừa.
2. Xác định nguồn có thẩm quyền của từng entitlement và approval.
3. Thu thập **observed** từ IdP, PAM, cloud, SaaS, host, directory, secret manager trong phạm vi được giao.
4. Chuẩn hóa namespace, tenant và identity mapping; không suy từ tên.
5. Tính tập **missing/excess grants** trong phạm vi connector thực sự sở hữu.
6. Đánh giá đường đặc quyền gián tiếp, session/token còn hiệu lực và quyền được gán thủ công.
7. Thu hồi/cấp điều chỉnh có idempotency, version guard và readback.
8. Test hành động phù hợp trong môi trường được phép để xác minh **effective access**.
9. Những đích không thể xác minh phải ghi **UNKNOWN/PARTIAL_FAILURE**, có owner và biện pháp bù.

**Không biến lỗi đọc inventory thành “không có admin”.** Một API trả thiếu trang hoặc một token inventory thiếu quyền đọc không chứng minh tài khoản không tồn tại.

## 21. Pseudocode quản lý yêu cầu quyền đặc quyền

Pseudocode dưới đây trình bày một **hợp đồng quyết định** chứ không phải code production:

~~~text
requestPrivilegedAccess(subjectRef, targetRef, action, duration):
    identity = resolveTrustedIdentity(subjectRef)
    target = resolveTrustedTarget(targetRef)
    if identity is unresolved or target is unresolved:
        return DENY_AND_REVIEW

    lifecycle = loadAuthoritativeLifecycle(identity.sourceKey)
    if lifecycle is unavailable or lifecycle.status != ACTIVE:
        return DENY
    if lifecycle.endAt exists and now() >= lifecycle.endAt:
        return DENY

    requestedScope = normalizeActionResourceTenant(
        action, target, duration
    )
    if requestedScope exceeds organizationRiskPolicy:
        return DENY

    approval = findCurrentAuthorizedApproval(
        identity,
        requestedScope
    )
    if approval is absent or approval.expired or violatesSoD:
        return DENY

    session = verifyPrivilegedAuthentication(
        identity,
        approvedAuthenticationProfile
    )
    if not session.meetsPolicy:
        return REQUIRE_STEP_UP

    grant = activateMinimalPrivilegeAtomically(
        identity,
        requestedScope,
        maxEndAt = min(approval.endAt, lifecycle.endAt, policyMaxEndAt)
    )
    recordAuditWithoutSecrets(grant, approval, lifecycle.version)

    if not readBackExactPrivilege(grant):
        revokeOrContain(grant)
        return PARTIAL_FAILURE

    return ALLOW_FOR_GRANT_SCOPE_AND_TIME
~~~

Điểm cần nhớ: **xác thực thành công, phê duyệt đúng và một API grant trả 200** là ba tín hiệu khác nhau. Muốn cho phép thao tác, cần xác minh grant thật sự đúng scope và không được tiếp tục tồn tại trái lifecycle.

### Thu hồi Leaver với version guard

~~~text
onLeaver(event):
    assert isAuthoritativeSource(event.source)
    identity = resolveIdentity(event.sourceKey)
    assert event.version is valid for this identity/source

    markLifecycleTerminatedAt(identity, event.effectiveAt)
    blockNewPrivilegeActivations(identity)

    for path in inventoryAllPrivilegedAccessPaths(identity):
        enqueueIdempotentRevocation(
            identityId = identity.id,
            pathId = path.id,
            lifecycleVersion = event.version,
            correlationId = event.correlationId
        )

    for target in allRequiredTargets(identity):
        result = readBackAccessAndSessions(target, identity)
        recordVerifiedOrPartialFailure(target, result)

onGrantRetry(task):
    current = loadLatestLifecycle(task.identityId)
    if task.sourceVersion < current.authoritativeVersion:
        return SUPERSEDED_WITHOUT_GRANT
    if current.status != ACTIVE:
        return DENY
    return continueWithCurrentApprovalAndPolicy(task)
~~~

**Không giả định mọi nguồn có một version tăng toàn cục.** Cần xác định thứ tự sự kiện theo identity/source và có xử lý trường hợp phiên bản không so sánh được hoặc event đến chậm. Thu hồi quyền đặc quyền phải **ưu tiên an toàn nhưng không xóa nhầm** tài nguyên hợp lệ của workload khác.

## 22. Xử lý lỗi, xung đột và tình huống bất đồng bộ

### Những trạng thái cần thể hiện

| Trạng thái vận hành | Ý nghĩa |
| --- | --- |
| **PENDING_APPROVAL** | Chưa đủ cơ sở cấp quyền. |
| **APPROVED_NOT_PROVISIONED** | Được duyệt nhưng target chưa nhận grant. |
| **ELIGIBLE_NOT_ACTIVE** | Có khả năng xin JIT, chưa được dùng quyền admin. |
| **ACTIVE_VERIFIED** | Grant đúng scope và được đọc lại. |
| **REVOKE_PENDING** | Đã yêu cầu thu hồi nhưng chưa có readback. |
| **REVOKED_VERIFIED** | Đã xác minh các đường trong phạm vi không còn quyền. |
| **PARTIAL_FAILURE** | Một số target/credential/session chưa xử lý xong. |
| **MAPPING_CONFLICT** | Không chắc account gắn với identity nào. |
| **UNKNOWN_EFFECTIVE_ACCESS** | Không thể kiểm tra quyền thực sự ở đích. |
| **SUPERSEDED** | Job/version cũ không còn được phép ghi. |

Đây là taxonomy nội bộ minh họa, không phải trạng thái chuẩn của PAM hoặc SCIM.

### Lỗi phổ biến và biện pháp

| Lỗi | Rủi ro | Biện pháp |
| --- | --- | --- |
| API timeout sau lệnh cấp quyền | Grant có thể đã được tạo, retry tạo trùng. | Readback theo target/grant ID trước khi retry; idempotency. |
| Hai người cùng sửa role | Quyền bị ghi đè hoặc mở rộng. | If-Match/versioning, serialized updates, audit. |
| Leaver tới khi session admin đang mở | Session có thể tiếp tục dùng quyền. | Chặn quyền mới, revoke session/credential theo khả năng, test residual access. |
| PAM có role revoke nhưng target chưa nhận | Standing quyền còn ở đích. | Reconciliation, owner, retry và containment. |
| HR source và IdP khác trạng thái | Cấp quyền theo dữ liệu cũ. | Field ownership, effectiveAt, sourceVersion, freshness. |
| Secret rotation xong nhưng worker chưa cập nhật | Mất dịch vụ hoặc worker quay lại key cũ. | Phối hợp dependency, readback cấu hình và health check. |
| Group quản trị lồng nhau | Member được cấp quyền gián tiếp không thấy ở danh sách trực tiếp. | Tính effective membership/delegation theo mô hình target. |
| Break-glass account không được kiểm thử | Khi sự cố thật có thể không đăng nhập được. | Diễn tập có kiểm soát, cảnh báo và hậu kiểm. |

### Hành vi khi hệ thống PAM/IdP lỗi

Không nên xây dựng một fallback kiểu:

~~~text
if PAM_or_IdP_unavailable:
    grant_global_admin_to_every_operator()
~~~

Một cơ chế phục hồi hợp lệ phải được phê duyệt trước, có account/credential khẩn cấp riêng, giới hạn người dùng, tài nguyên và logging, và được kiểm thử. Không mở thêm standing administrator quyền rộng chỉ để che lỗi availability của hệ thống đặc quyền.

## 23. Ma trận kiểm thử privileged account

Kiểm thử cần dùng identity/account và môi trường **được phép**, không thử đăng nhập bằng credential thật của người khác, không tạo bulk admin trên production để kiểm tra. Cần kiểm tra **positive, negative, lifecycle và sự cố phân tán**.

| ID | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| PA-01 | Named admin đúng identity, có approval, MFA đủ và JIT chưa hết hạn. | Chỉ thao tác được trong scope được cấp. |
| PA-02 | User ACTIVE nhưng không có business justification. | Không tự cấp admin. |
| PA-03 | Cố dùng account thường để thực hiện admin action. | Bị từ chối nếu không có quyền hiện hành. |
| PA-04 | User có role Operator nhưng chưa JIT activation. | Không có effective admin access. |
| PA-05 | JIT hết hạn khi session vẫn mở. | Hành vi theo revocation/session policy; không bỏ qua residual access. |
| PA-06 | Admin cố thay IAM policy để tự gán quyền vượt scope. | Bị chặn theo JEA/SoD hoặc cảnh báo rủi ro. |
| PA-07 | User chưa đạt phishing-resistant MFA theo policy admin. | Không cho phép privileged action; step-up nếu hỗ trợ. |
| PA-08 | Joiner đã pre-provision nhưng chưa startAt. | Không kích hoạt quyền admin production sớm. |
| PA-09 | Mover gỡ team SupportAdmin. | Role/group/eligibility cũ bị thu hồi và readback. |
| PA-10 | Mover sang nhóm admin cao hơn nhưng thiếu approval. | Không cấp scope mới. |
| PA-11 | Leaver khi admin session còn mở. | Chặn login/grant mới, xử lý phiên cũ và đo residual access. |
| PA-12 | Leaver có PAT/SSH key độc lập với IdP. | Credential bị xử lý theo scope; không coi IdP disabled là đủ. |
| PA-13 | Leaver rồi Joiner job cũ được retry. | Không tạo lại privileged account/grant. |
| PA-14 | Rehire với account cũ. | Không tự phục hồi admin role/credential lịch sử. |
| PA-15 | SaaS super-admin chỉ có local auth. | Có owner, inventory, MFA/credential và revoke path phù hợp. |
| PA-16 | Cloud role có permission gián tiếp tự gán admin. | Phát hiện escalation path; không báo least privilege giả. |
| PA-17 | Service account owner nghỉ việc. | Service được bàn giao/rotate an toàn, không xóa nhầm workload sống. |
| PA-18 | Workload staging dùng credential gọi API production. | Deny theo trust/environment/audience. |
| PA-19 | Built-in root credential được dùng trái lịch. | Audit/cảnh báo, attribution và response theo chính sách. |
| PA-20 | Break-glass được sử dụng trong bài diễn tập cho phép. | Có sự kiện alert, justification, kiểm tra tác động và hậu kiểm. |
| PA-21 | PAM API trả thành công nhưng target role chưa thay. | Không đánh dấu VERIFIED; đối soát lỗi. |
| PA-22 | Inventory thiếu một page hoặc thiếu quyền đọc. | UNKNOWN; không kết luận không còn admin. |
| PA-23 | Two-person approval theo SoD nhưng requester tự duyệt. | Không cấp quyền. |
| PA-24 | PAM broker không hoạt động. | Không tự fallback sang unrestricted admin. |
| PA-25 | Token JWT admin còn hạn sau revoke refresh token. | Kiểm thử đúng revocation boundary ở API. |
| PA-26 | Credential local admin bị sao chép sang nhiều host. | Đánh giá khả năng phân tách/rotate và lateral movement. |

### Test Given–When–Then

~~~gherkin
Feature: Privileged accounts follow identity lifecycle

  Scenario: Joiner cannot activate admin rights too early
    Given a verified Joiner identity is pending activation
    And a privileged account is pre-provisioned
    When the identity requests a production admin operation
    Then the operation is denied
    And no effective production privilege is activated

  Scenario: Mover loses obsolete privileged group
    Given an active user has SupportAdmin eligibility
    And an authoritative Mover event removes that eligibility
    When the old account tries a SupportAdmin-only action
    Then the action is denied after the required convergence boundary
    And other approved roles remain within their scope

  Scenario: Leaver cannot reuse an existing privileged session
    Given a named admin has a valid privileged session
    And an authoritative Leaver event becomes effective
    When the admin session attempts an administrative action
    Then the action is denied according to the revocation policy
    And remaining credential and session paths are reconciled

  Scenario: Workload remains controlled after its owner leaves
    Given a production workload has an approved service identity
    And its human owner has left the organization
    When the service ownership workflow runs
    Then a valid new service owner is established
    And exposed human-known credentials are rotated as required
    And the workload retains only approved service privileges
~~~

### Đừng chỉ assert status code

Một API trả **403** có thể vẫn có side effect nếu policy được kiểm tra quá muộn. Với thao tác thay role, deploy, restart hay xóa dữ liệu, test phải đọc lại trạng thái tài nguyên; với secret, phải xác minh credential cũ thật sự không còn được chấp nhận. Khi API không cung cấp khả năng kiểm chứng, ghi trạng thái **UNVERIFIED** và xác định kiểm soát bù.

## 24. Audit và giám sát tài khoản đặc quyền

### Dữ liệu audit tối thiểu

| Trường | Ý nghĩa |
| --- | --- |
| **identityId / serviceId** | Chủ thể thật hoặc workload thực hiện. |
| **privilegedAccountRef** | Account cụ thể tại host/cloud/SaaS. |
| **target, tenant, environment** | Resource có thể bị tác động. |
| **role/entitlement/action** | Quyền được kích hoạt và hành động đã làm. |
| **approval/justification/SoD result** | Căn cứ cấp quyền. |
| **authn context / step-up method** | Kiểm tra mức xác thực theo policy. |
| **startAt/endAt/activatedAt** | Xác định JIT window và sự kiện quá hạn. |
| **sessionRef/grantRef** | Nối phiên và quyền mà không ghi secret. |
| **JML event/sourceVersion/effectiveAt** | Gắn quyền với vòng đời hiện hành. |
| **result/readback/verifiedAt** | Chứng minh thao tác đã áp dụng và đúng scope. |
| **correlationId / owner** | Phục vụ điều tra đầu-cuối và xử lý lỗi. |

### Ví dụ event

~~~json
{
  "eventType": "PRIVILEGED_ACCESS_REVOKE_VERIFICATION",
  "identityId": "IAM:ID-2041",
  "privilegedAccountRef": "cloud:tenant-b:admin-lan",
  "targetSystem": "CloudControlPlane",
  "targetScope": "project-payments",
  "role": "PlatformOperator",
  "lifecycleEvent": "LEAVER",
  "sourceVersion": 43,
  "effectiveAt": "2026-12-01T17:00:00+07:00",
  "operation": "REVOKE_ACTIVE_AND_ELIGIBLE_ROLE",
  "observedResult": "REVOKED_VERIFIED",
  "verifiedAt": "2026-12-01T17:00:18+07:00",
  "correlationId": "leaver-2041-v43"
}
~~~

Đây là **schema nội bộ minh họa**, không phải chuẩn SCIM/OIDC/PAM. Không ghi password, private key, OTP, refresh/access token nguyên vẹn, cookie hoặc secret vào log. Session recording có thể chứa dữ liệu nhạy cảm; cần xác định phạm vi ghi, quyền xem và thời hạn lưu giữ theo chính sách.

### Chỉ số cần theo dõi

| Chỉ số | Câu hỏi |
| --- | --- |
| **Standing admin count** | Có bao nhiêu account còn đặc quyền thường trực? |
| **Privileged accounts without owner** | Account admin mồ côi ở hệ thống nào? |
| **Dormant privileged accounts** | Account ít dùng nhưng vẫn có quyền rộng? |
| **JIT activation duration** | Thời gian kích hoạt có vượt nhu cầu? |
| **Privileged MFA/assurance coverage** | Bao nhiêu đường admin đáp ứng xác thực mạnh được yêu cầu? |
| **Break-glass usage rate** | Có account khẩn cấp bị dùng thường xuyên hoặc trái quy trình? |
| **Credential rotation/revocation age** | Bao lâu rồi shared/static credential chưa được xử lý? |
| **Privileged session revocation lag** | Từ revoke/Leaver tới lúc phiên không thể dùng nữa? |
| **Entitlement drift after Mover** | Bao nhiêu role cũ còn ở đích? |
| **Residual privilege after Leaver** | Bao nhiêu đường admin vẫn thực sự hoạt động? |
| **Unverified target coverage** | Những hệ thống nào chưa thể xác nhận quyền thực tế? |
| **Direct privilege grants outside IGA** | Có local grant nào không nằm trong workflow? |
| **Privilege escalation paths** | Có trust/delegation nào dẫn tới quyền vượt phạm vi? |

Không lấy **số lượng account admin ít nhất** làm mục tiêu duy nhất: một super-admin quyền cực rộng có thể rủi ro hơn nhiều account operator hẹp, định danh rõ và dùng JIT. Cần đo **phạm vi, thời hạn, chủ thể, khả năng kiểm soát và quyền hiệu lực**.

## 25. Những sai lầm thường gặp

1. **Chỉ tìm account có tên admin/root.** Bỏ sót service principal, Group inheritance, trust và IAM policy có thể tự tăng quyền.
2. **Dùng account quản trị cho công việc hàng ngày.** Tăng nguy cơ phishing/session theft.
3. **Cho tất cả nhân viên IT standing GlobalAdmin.** Quyền rộng hơn nhiệm vụ và tồn tại quá lâu.
4. **Dùng chung password cho nhiều quản trị viên.** Khó attribution và thu hồi khi nhân sự thay đổi.
5. **Bật JIT nhưng không giảm scope.** Role vẫn quá rộng dù thời gian ngắn.
6. **Dựa vào OTP/push MFA thường và coi là phishing-resistant.** Cần đánh giá phương thức đúng policy.
7. **Tin rằng IdP disable hoặc SCIM active=false là xong Leaver.** Local account, session, PAT và secret có thể vẫn hợp lệ.
8. **Chỉ revoke role, bỏ qua admin session đang hoạt động.** Quyền có thể tồn dư.
9. **Không quản lý credential do vendor hoặc automation giữ.** Owner rời đi nhưng token còn sử dụng được.
10. **Đồng nhất owner nghỉ việc với xóa service account.** Có thể làm gián đoạn workload production mà chưa giải quyết credential exposure.
11. **Không bảo vệ đường enrollment/recovery.** Helpdesk reset yếu có thể cho kẻ tấn công đăng ký phương thức admin mới.
12. **Không kiểm chứng quyền thực tế.** Connector trả 200/204 nhưng ứng dụng vẫn có local role hoặc token cũ.
13. **Không có sourceVersion guard.** Retry Joiner/Mover cũ có thể bật lại đặc quyền sau Leaver.
14. **Giữ break-glass account không owner, không audit và không diễn tập.** Vừa tạo cửa hậu vừa có nguy cơ không thể khôi phục khi cần.
15. **Chỉ kiểm quyền trên UI.** API, job nền và token độc lập có thể bỏ qua PEP.

## 26. Tình huống thực hành

### Tình huống A — Admin tách riêng nhưng quyền đứng mãi

**Bối cảnh:** Lan có account thường và admin-lan riêng. Admin-lan giữ quyền OrganizationAdmin trong mọi thời điểm dù Lan chỉ bảo trì vài lần mỗi tháng.

**Câu hỏi:** Tách account đã đủ an toàn chưa?

**Gợi ý:** Chưa. Nó giảm một số rủi ro dùng chung phiên nhưng không giải quyết **standing privilege**. Xem xét JIT, JEA, giới hạn resource/tenant, approval, MFA mạnh và session audit.

### Tình huống B — Leaver ở IdP nhưng local super-admin còn đăng nhập

**Bối cảnh:** HR phát Leaver, IdP User disabled. Một SaaS vẫn còn local super-admin password của người nghỉ việc.

**Câu hỏi:** Đã hoàn thành offboarding chưa?

**Gợi ý:** Chưa. Local auth là một đường truy cập khác. Cần inventory, khóa account/rotate credential, chấm dứt session và kiểm tra effective access. Không dựa duy nhất vào kết quả SCIM.

### Tình huống C — Mover giữ token production cũ

**Bối cảnh:** Lan chuyển khỏi PlatformOps. PAM role đã bị thu hồi, nhưng SSH certificate phát trước Mover vẫn còn hạn trên một host.

**Câu hỏi:** Quyền còn tồn ở đâu?

**Gợi ý:** Token/certificate và điểm xác thực host vẫn có thể chấp nhận quyền nếu không có revocation/TTL phù hợp. Cần đo residual access ở target, quản lý credential ngắn hạn và kiểm soát thu hồi theo policy.

### Tình huống D — Service account owner nghỉ việc

**Bối cảnh:** Một developer sở hữu CI bot có quyền deploy production nghỉ việc. CI bot đang phục vụ khách hàng và có static API key.

**Câu hỏi:** Xóa bot ngay có phải phương án tối ưu?

**Gợi ý:** Không tự động. Cần bàn giao service owner, kiểm tra bot còn cần thiết, giảm scope và rotate/revoke key mà người nghỉ việc biết; lên kế hoạch tránh outage và xác minh quyền hiệu lực.

### Tình huống E — Break-glass chưa từng kiểm thử

**Bối cảnh:** IdP gặp lỗi, mọi JIT role activation thất bại. Đội vận hành có account emergency nhưng không ai chắc nó đăng nhập được.

**Câu hỏi:** Kiểm soát nào bị thiếu?

**Gợi ý:** Thiếu kiểm thử đường khôi phục, ownership và quy trình sử dụng có giám sát. Cần diễn tập phù hợp, cảnh báo, phân quyền tiếp cận credential và hậu kiểm.

### Tình huống F — Vai trò không ghi Admin nhưng có quyền tự cấp

**Bối cảnh:** Một workload có quyền sửa IAM role policy của chính role mà workload có thể assume, nhưng dashboard không liệt kê nó trong nhóm Administrators.

**Câu hỏi:** Có nên coi đây là account đặc quyền?

**Gợi ý:** Có nguy cơ **privilege escalation path**. Đánh giá khả năng thay role/trust và quyền thực tế thay vì chỉ nhìn tên role.

### Tình huống G — PAM báo revoked nhưng phiên RDP còn mở

**Bối cảnh:** Quyền admin hết hạn trong PAM, nhưng một phiên RDP đã mở vẫn cho sửa cấu hình server.

**Câu hỏi:** Có nên báo REVOKED_VERIFIED?

**Gợi ý:** Không nếu chính sách yêu cầu ngừng hành động đặc quyền khi hết hạn. Phải kiểm tra session revocation/target enforcement và quyền tồn dư; ghi PARTIAL_FAILURE nếu chưa thể thu hồi.

### Tình huống H — Nhà thầu dùng chung account với nhân viên

**Bối cảnh:** Vendor hỗ trợ lỗi production qua account root chung với quản trị viên nội bộ, không có session attribution.

**Câu hỏi:** Rủi ro và cách cải thiện?

**Gợi ý:** Không phân biệt được ai làm gì, khó thu hồi theo hợp đồng và tăng rủi ro lộ secret. Dùng danh tính riêng, PAM broker khi phù hợp, phê duyệt theo phiên, session logging, hạn truy cập và kiểm soát credential chung.

### Tình huống I — Thiếu approval nhưng SSO vẫn thành công

**Bối cảnh:** Một người đăng nhập console quản trị bằng passkey, nhưng chưa có approval cho action rotate production key.

**Câu hỏi:** Có được Permit vì MFA mạnh không?

**Gợi ý:** Không. MFA xác thực người dùng; authorization còn yêu cầu role, scope, approval, SoD, JIT và điều kiện resource.

## 27. Câu hỏi tự kiểm tra

**1. Privileged account khác privileged role như thế nào?**

Account là đối tượng/định danh dùng để truy cập; role là tập quyền có thể gán/kích hoạt cho account. Một account không luôn giữ role admin và một role có thể được cấp tạm thời.

**2. Vì sao phải quản trị cả service identity, PAT và SSH key khi kiểm kê account đặc quyền?**

Vì chúng có thể tạo đường truy cập quản trị độc lập với named account/SSO và tồn tại sau khi quyền người dùng bị gỡ.

**3. Standing privilege và JIT khác nhau ở điểm nào?**

Standing privilege tồn tại liên tục; JIT kích hoạt theo nhu cầu và thời hạn. JIT nên kết hợp scope nhỏ/JEA để giảm blast radius.

**4. Một account có tên Operator thay vì Admin có thể là account đặc quyền không?**

Có. Cần xét quyền hiệu lực, delegation và khả năng tự tăng quyền, không chỉ tên.

**5. Mover có nên giữ nguyên mọi Group và role cũ rồi cộng thêm role mới?**

Không. Phải tính desired access hiện hành, gỡ quyền không hợp lệ và giữ ngoại lệ chỉ khi còn căn cứ được phê duyệt.

**6. IdP disabled sau Leaver có chứng minh mọi session/token admin tại SaaS hết hiệu lực không?**

Không. Cần kiểm chứng local accounts, app sessions, PAT, SSH key, access token và Resource Server.

**7. Vì sao một credential được vault quản lý vẫn chưa đủ để bảo đảm thu hồi?**

Vì có thể tồn tại credential khác, secret đã checkout, token phát trước đó hoặc phiên đang hoạt động ngoài vault.

**8. Break-glass có nên được dùng như đường quản trị thường xuyên không?**

Không. Đây là cơ chế khẩn cấp được bảo vệ, giám sát, diễn tập và hậu kiểm riêng.

**9. Service account owner nghỉ việc thì phải xóa service ngay không?**

Không mặc định. Cần quản trị vòng đời workload, chuyển owner, rotate/revoke credential cá nhân biết và giảm quyền theo rủi ro.

**10. Một user có MFA mạnh nhưng thiếu phê duyệt admin có được thực hiện thao tác production không?**

Không. Authentication assurance không thay thế authorization, SoD, approval và scope.

**11. Sau khi PAM báo role revoked, cần readback gì?**

Tùy hệ thống: account role/Group, JIT eligibility, active sessions, credential/token còn dùng được và quyền hiệu lực tại target.

**12. Vì sao sourceVersion/effectiveAt quan trọng với Leaver?**

Để ngăn tác vụ cấp quyền cũ retry hoặc sự kiện sai thứ tự tự kích hoạt lại quyền đã thu hồi.

**13. Privileged Access Management có bắt buộc là một công cụ duy nhất không?**

Không. PAM là tập thực hành và capability có thể phân bố giữa vault, IdP, policy engine, session broker, cloud IAM và hệ thống audit; cần kiểm tra khả năng thực tế.

**14. Nếu inventory API trả thiếu trang thì có được kết luận account admin không còn không?**

Không. Đó là bằng chứng chưa đầy đủ; cần trạng thái UNKNOWN/UNVERIFIED, retry hoặc biện pháp kiểm soát bù.

## Ghi nhớ

- **Privileged account** là account/định danh có khả năng sử dụng quyền nhạy cảm; phải kiểm tra cả **effective privileges, credential, session và các đường leo thang**, không chỉ tên admin.
- **Named admins, root/local admins, cloud/SaaS admins, service identities, vendor và break-glass** có rủi ro và vòng đời khác nhau; tất cả cần owner, inventory, mục đích, giới hạn và audit.
- **Least privilege, tách ngữ cảnh admin, JIT/JEA, MFA mạnh, PAM/PIM, secret management và kiểm soát phiên** giúp giảm thời gian/phạm vi đặc quyền có thể bị lạm dụng.
- **Joiner** chỉ cấp admin đúng người, đúng ngày và đúng approval; **Mover** gỡ quyền cũ, rà soát credential/session; **Leaver** phải chặn mọi đường admin còn hiệu lực và chống job cũ tái cấp.
- **IdP/SSO, SCIM, RBAC/ABAC/PBAC, PAM và Resource Server** có trách nhiệm khác nhau. Disable account hoặc revoke một role **không tự chứng minh** tất cả token, session, PAT, SSH key và local admin đã hết hiệu lực.
- **Danh tính máy** cần service owner, trust, scope, credential rotation và vòng đời workload độc lập; khi owner con người nghỉ việc phải bàn giao an toàn, không xóa mù dịch vụ.
- **Readback, kiểm thử dương/âm, đối soát desired–observed–effective, kiểm toán và đo quyền tồn dư** là điều kiện để quản lý privileged account đúng trong toàn bộ vòng đời IAM.
