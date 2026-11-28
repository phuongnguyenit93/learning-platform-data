# Phân quyền IAM đối với thay đổi cấu hình mạng

> **Chương:** Bảo mật mạng cloud  
> **Mô-đun:** SECURITY_NETWORK_SECURITY  
> **Bối cảnh:** Kiến trúc phòng vệ nhiều lớp gồm phân đoạn mạng, firewall, VPN, IDS/IPS, DNS, Wi-Fi, bảo vệ cloud và phân tích lưu lượng.  
> **Trọng tâm:** Cấp quyền đúng người, đúng dịch vụ, đúng tài nguyên, đúng thao tác và đúng thời điểm cho **các thay đổi cấu hình mạng trên cloud**; kết hợp IAM/RBAC, tổ chức tài khoản/dự án, guardrail, Infrastructure as Code, logging, phát hiện sai lệch và xử lý sự cố.

## 1. Vì sao phân quyền thay đổi cấu hình mạng quan trọng?

Trong môi trường cloud, **cấu hình mạng là tài sản bảo mật**. Một tài khoản có quyền chỉnh **security group, network security group (NSG), firewall policy, route table, network peering, DNS, load balancer, VPN hoặc private endpoint** có thể ảnh hưởng trực tiếp đến những luồng truy cập mà tổ chức đã thiết kế để bảo vệ.

Ví dụ, một người vận hành chỉ có nhiệm vụ cập nhật cổng HTTPS cho ứng dụng thử nghiệm nhưng vô tình hoặc cố ý:

- Cho phép **0.0.0.0/0** tới SSH/RDP hoặc cổng quản trị nhạy cảm của máy chủ production.
- Thay route để traffic đi qua một gateway hoặc đường mạng ngoài dự kiến.
- Mở peering/transit giữa các VPC/VNet vốn phải được phân đoạn.
- Tắt cloud firewall hoặc xóa các nguồn **flow/security logs**.
- Đổi private DNS khiến ứng dụng kết nối sai endpoint; thay cấu hình egress tạo đường thoát dữ liệu.
- Chỉnh load balancer/listener để bypass WAF, mTLS hoặc yêu cầu xác thực.

Những thay đổi này có thể xảy ra qua **console, CLI, REST API, SDK, Terraform, CI/CD hoặc automation account**. Dùng một tài khoản có quyền quản trị toàn cloud để thực hiện việc nhỏ sẽ làm tăng **blast radius** nếu tài khoản, token hay pipeline bị xâm nhập.

**Identity and Access Management (IAM)** kiểm soát ai/ứng dụng nào có thể gọi **API quản lý cloud** và đối với tài nguyên nào. Với cấu hình mạng, mục tiêu là **đặc quyền tối thiểu (least privilege)** cho **control plane**, kết hợp guardrail ngăn những cấu hình nguy hiểm dù một người có quyền thay đổi mạng.

**Thông điệp chính:** Quyền *được sửa network policy* khác với việc một thiết bị *được đi qua network policy*. IAM kiểm soát người tạo/sửa/xóa luật; firewall/security group/route quyết định gói đi theo luật ấy. **Cần bảo vệ cả hai lớp**.

### Mục tiêu học tập

Sau bài, người học có thể:

1. Phân biệt **IAM control-plane authorization** với **data-plane network enforcement**.
2. Liệt kê các API/tài nguyên mạng có nguy cơ cao khi được quyền **create/update/delete/attach/associate**.
3. Thiết kế vai trò **read-only, operator, deployer, reviewer, network-security admin và break-glass**.
4. Hiểu những khác biệt chính giữa **AWS IAM/SCP**, **Azure RBAC/PIM/Policy** và **Google Cloud IAM/Organization Policy**.
5. Dùng phạm vi **account/subscription/project, resource, tag/condition, session duration** một cách thận trọng.
6. Kết hợp **Git, code review, IaC plan, policy-as-code, pipeline identity, approval và drift detection**.
7. Phát hiện, truy vết và xử lý sự cố thay đổi mạng vượt quyền từ audit logs, state/config inventory và flow telemetry.

## 2. Thuật ngữ và phạm vi

| Khái niệm | Ý nghĩa trong bài | Điều cần phân biệt |
|---|---|---|
| **IAM** | Chính sách xác thực và phân quyền principal gọi API cloud | Không trực tiếp thay packet-filtering khi data plane đã cấu hình |
| **Principal** | User, role, service principal, service account, workload identity hoặc automation identity | Principal không đồng nghĩa IP nguồn |
| **Action/permission** | API hoặc nhóm thao tác được cấp quyền | Read/List khác Create/Update/Delete/Attach |
| **Resource** | Security group, route table, firewall policy, VPC/VNet, DNS zone, LB, VPN gateway... | Quyền trên một resource không mặc định giới hạn được mọi hành vi phụ thuộc |
| **Scope** | Tài khoản, tổ chức, subscription, project, folder, resource group, resource | Scope càng rộng thì blast radius thường càng lớn |
| **Role** | Tập permission gán cho principal trong phạm vi | Tên role không thay việc đọc permission thực tế |
| **RBAC** | Phân quyền dựa trên vai trò | Role cần gắn đúng scope và lifecycle |
| **ABAC/condition** | Quyết định quyền dựa trên thuộc tính, tag, thời gian hoặc điều kiện hỗ trợ | Condition không được hỗ trợ đồng đều trên mọi API/resource |
| **Guardrail** | Cơ chế chặn cấu hình ngoài chuẩn, ví dụ explicit deny, org policy hoặc policy admission | Guardrail thường không tự cấp quyền |
| **Separation of duties** | Tách người đề xuất/phê duyệt/áp dụng và kiểm tra | Có thể bị vô hiệu nếu một tài khoản giữ tất cả quyền |
| **JIT/PIM/PAM** | Cấp quyền đặc biệt ngắn hạn, theo phê duyệt/điều kiện | Không thay audit hoặc bảo vệ credential |
| **IaC** | Mã khai báo hạ tầng như Terraform/OpenTofu, CloudFormation, Bicep | Plan và apply cần identity, approval, state security |
| **Drift** | Cấu hình cloud thực tế khác baseline/khai báo được phê duyệt | Drift có thể do sự cố, hotfix hợp lệ hoặc hành vi không được phép |
| **Break-glass** | Truy cập khẩn cấp có kiểm soát khi đường thông thường không dùng được | Không nên là quyền admin thường trực cho mọi nhân viên |

## 3. Control plane và data plane: hai lớp cần kiểm soát

**Control plane:** API/console dùng để tạo VPC/VNet, thay route, sửa firewall, thêm network peer, thay NAT gateway, bật/tắt log hoặc phân quyền cho service account.

**Data plane:** lưu lượng ứng dụng và packet đi qua LB, VPN, firewall, route và endpoint theo cấu hình đã được áp dụng.

~~~mermaid
flowchart TB
    U[Engineer / Admin / Automation] --> I{IAM / RBAC kiểm tra quyền API}
    I -- Deny --> X[Không thay được tài nguyên cloud]
    I -- Allow --> C[Cloud Network Control Plane]
    C --> S[Security Group / NSG / Firewall Policy]
    C --> R[Routes / Peering / Transit]
    C --> D[DNS / Private Endpoint / Load Balancer]
    S --> P[Data Plane: App traffic]
    R --> P
    D --> P
    C -. Admin audit events .-> A[Cloud Audit / SIEM]
    P -. Flow / WAF / Network logs .-> A
~~~

Một kỹ sư **không có quyền sửa firewall** vẫn có thể sử dụng dịch vụ qua firewall nếu data-plane policy cho phép. Ngược lại, kỹ sư **có quyền sửa firewall** không nhất thiết có thông tin đăng nhập vào máy ảo nằm phía sau nó.

### 3.1. Sai lầm cần tránh

Không coi **IAM role “Network Admin”** là chứng minh toàn bộ network đã an toàn. Người giữ role đó có thể cấu hình rule sai; phải kiểm tra **hiệu lực thực tế** bằng policy tests, reachability analysis, data-plane logs và defense in depth.

### 3.2. Nhìn cả đường phụ

Một security group được quản lý chặt có thể không đủ nếu tài nguyên còn accessible qua **public LB, secondary NIC, peering, private endpoint, VPN, IPv6 hoặc một đường route không đi qua firewall mong đợi**. IAM governance nên kết hợp kiểm thử mạng ở những đường phụ này.

## 4. Inventory: những thay đổi mạng nào nhạy cảm?

Trước khi tạo IAM role, cần biết **ai đang sở hữu từng loại tài nguyên** và hậu quả khi sửa.

| Tài nguyên/thao tác | Nguy cơ khi quyền quá rộng | Ví dụ mục tiêu giới hạn |
|---|---|---|
| **Security group/NSG/firewall rule** | Mở port quản trị/DB ra Internet hoặc cho nguồn trái quyền | Chỉ sửa rules thuộc app dev, không xóa baseline deny |
| **Route table, UDR, static/dynamic routing** | Chuyển traffic qua hop không kiểm soát, bypass inspection, mất kết nối | Chỉ update route hợp lệ trong sandbox |
| **VPC/VNet/subnet** | Mở rộng trust boundary, làm lộ workloads, trùng CIDR | Tách quyền create subnet với attach production |
| **VPC peering/Transit Gateway/VNet peering** | Nối các vùng trước đó được tách; route propagation quá rộng | Cần review liên nhóm và kiểm tra hai đầu |
| **Cloud VPN, dedicated interconnect** | Nối cloud với on-prem/partner, học route ngoài dự kiến | Tách peer onboarding và route approval |
| **Internet gateway, NAT, egress gateway** | Tạo đường vào/ra ngoài chính sách | Hạn quyền attach và policy egress |
| **Load balancer, listener, target group** | Bỏ TLS/WAF/mTLS, trỏ backend sai | Cho sửa target theo service, bảo vệ listener security |
| **DNS public/private zone, forwarding/resolver** | Chuyển hostname đến điểm sai, rò rỉ nội bộ, phá trust | Chỉ sửa record/zone được owner giao |
| **Private endpoint/VPC endpoint/service connection** | Tạo đường riêng đến service nhạy cảm, mở reachability không rõ | Giới hạn service, VPC, endpoint policy và approvals |
| **Cloud network firewall/WAF policy** | Tắt inspection, thêm allow-all, bỏ logging | Cần quyền security riêng, change approval |
| **Flow logs, audit exports, diagnostic settings** | Xóa khả năng quan sát hoặc thay log sink | Chỉ security platform role quản trị, guardrail chống tắt |
| **NACL, policy routes, global edge** | Gián đoạn luồng hoặc thay perimeter policy | Test scope, rollout và rollback |
| **Network resource IAM/ACL** | Tự cấp quyền sửa mọi network khác | Tách quyền chỉnh IAM khỏi quyền vận hành mạng |

**Cùng một API có thể tác động nhiều tài nguyên phụ thuộc.** Ví dụ tạo peering chỉ là một bước; route, firewall, DNS và IAM ở hai bên mới quyết định kết nối thực sự. Phân quyền phải kiểm tra **chuỗi thao tác hoàn chỉnh**, không chỉ tên action đơn lẻ.

## 5. Least privilege: ai, làm gì, trên tài nguyên nào, khi nào?

Một policy tốt cần trả lời ít nhất:

- **Principal**: người dùng/role/CI job/workload/đối tác đã xác thực?
- **Action**: List/Describe, Create, Update, Delete, Associate, Attach, Share, Enable logging?
- **Resource scope**: account/subscription/project, VPC/VNet, resource group, region, route table/security group cụ thể?
- **Condition**: yêu cầu MFA, short-lived session, tag, IP nguồn quản trị, approval/JIT hoặc attribute khác nếu nền tảng hỗ trợ?
- **Environment**: dev, staging, prod hoặc management/shared-services?
- **Time**: quyền cần trong bao lâu; có self-expire và review không?
- **Owner**: ai chịu trách nhiệm thay đổi và kiểm chứng?

### 5.1. Quyền đọc khác quyền sửa

Một kỹ sư phân tích sự cố có thể cần xem route và firewall policy ở nhiều region, nhưng không cần quyền **DeleteRoute, ReplaceRoute, AuthorizeSecurityGroupIngress hoặc sửa NSG**. Tách **read-only network observability** khỏi **mutation** giúp giảm rủi ro thao tác nhầm và account compromise.

### 5.2. Quyền tạo và quyền gắn/áp dụng khác nhau

Đối với tài nguyên có thể **tạo mới** rồi **gắn vào production**, một policy chỉ kiểm soát quyền Create có thể chưa đủ. Phải kiểm tra **Attach/Associate/Update/Apply**, IAM/resource policy ở các endpoint và action phụ thuộc. Một principal có quyền gắn firewall policy rỗng vào mạng quan trọng cũng có thể tạo tác động lớn dù không được sửa policy gốc.

### 5.3. Phạm vi rất hẹp chưa chắc đã bảo vệ được ý nghĩa rule

Nếu principal được phép sửa **chỉ security group sg-app-prod**, họ vẫn có thể thêm **0.0.0.0/0 TCP 22** nếu không có giới hạn khác. Scope theo resource giải quyết **đúng security group nào**, còn **rule-content validation** giải quyết **được phép viết giá trị gì**.

## 6. Quyết định IAM và guardrail: đừng giản lược quá mức

Mỗi cloud có mô hình đánh giá quyền riêng. Ở mức khái quát, cần phân biệt:

1. **Identity permissions**: role/user/service principal có khả năng gọi action không?
2. **Resource/scoped permissions**: tài nguyên và phạm vi nào chấp nhận action đó?
3. **Organizational guardrails / explicit denies**: tổ chức có ngăn các hành vi vượt chuẩn không?
4. **Session conditions**: MFA, nguồn truy cập, resource attributes và thời gian theo chính sách hỗ trợ?
5. **Dependent permissions**: API call có cần thêm quyền trên IAM role, subnet, log sink, certificate, key hoặc resource khác không?
6. **Service-specific authorization**: có policy độc lập ở private endpoint, firewall manager hoặc service được kết nối không?

~~~mermaid
flowchart TD
    A[Principal yêu cầu thay đổi network] --> B{Đã xác thực và session hợp lệ?}
    B -- Không --> X[Từ chối + audit]
    B -- Có --> C{IAM/RBAC cho action và resource scope?}
    C -- Không --> X
    C -- Có --> D{Org guardrail / explicit deny / policy constraint?}
    D -- Deny --> X
    D -- Pass --> E{Dependent permissions, conditions, approvals?}
    E -- Không --> X
    E -- Đạt --> F[Apply mutation có kiểm soát]
    F --> G[Audit config change + verify effective network policy]
~~~

Sơ đồ để **xây tư duy**, không thay tài liệu evaluation logic chính thức của AWS/Azure/GCP. Ví dụ, policy ở Azure có thể được kiểm tra ở nhiều scope và deny assignment có ngữ nghĩa riêng; AWS SCP/permission boundary cũng có logic khác Azure RBAC/GCP IAM. Không dùng một đoạn pseudocode để dự đoán mọi trường hợp cross-account hoặc resource policy.

### 6.1. Guardrail thường không cấp quyền

**AWS Service Control Policy (SCP), permissions boundary, Azure Policy, Google Cloud Organization Policy** chủ yếu định hình ranh giới/constraint, **không thay thế một IAM/RBAC allow hợp lệ**. Một resource **đạt policy compliance** chưa có nghĩa mọi thay đổi của nó được phê duyệt ở cấp nghiệp vụ.

### 6.2. Không mọi action hỗ trợ resource-level permissions

Một số cloud API chỉ có thể scope ở **account/project hoặc wildcard action/resource** tùy phiên bản/dịch vụ. Khi đó phải áp **org policy, conditions nếu hỗ trợ, isolated account/project, pipeline broker và policy-as-code**; không tạo policy trông hẹp nhưng provider thực tế không enforce.

## 7. Phân loại principal và rủi ro tương ứng

| Principal | Ví dụ công việc | Nguy cơ chính | Cơ chế bảo vệ |
|---|---|---|---|
| **Network viewer** | Troubleshooting, kiểm tra routes/rules | Xem dữ liệu cấu trúc mạng nhạy cảm | Read-only theo phạm vi, audit access |
| **App engineer** | Thay security group cho app dev | Mở cổng prod nếu chung quyền | Tách environment, role và scope |
| **Network operator** | Bảo trì VPN, route, LB được giao | Sai route ảnh hưởng toàn mạng | JIT, change review, rollback |
| **Network security admin** | Firewall, guardrails, inspection policy | Bỏ bảo vệ hoặc tắt log | MFA, approval kép, audit độc lập |
| **CI/CD deployer** | IaC apply theo repository đã phê duyệt | Pipeline compromise thay nhiều mạng | Short-lived workload federation, protected branches |
| **Managed service/vendor** | Bảo trì networking theo hợp đồng | Credential tồn tại lâu, khó kiểm soát | Scoped access, expiration, session audit |
| **Cloud service principal** | Tự động quản lý endpoint, DNS, NAT | Service role quá rộng hoặc bị impersonate | Trust policy, dependent-action review |
| **Break-glass admin** | Phục hồi emergency khi IAM/control plane lỗi | Toàn quyền khó kiểm soát | Quy trình riêng, nhiều kiểm soát, post-incident review |

### 7.1. User credential và workload credential khác nhau

Human access nên dùng **SSO/federation, MFA, session ngắn/JIT**, trong khi CI/CD nên dùng **workload identity federation/role assumption hoặc token ngắn hạn**. Không nhúng cloud access key có quyền quản trị mạng dài hạn vào repo, container image hoặc pipeline variables không kiểm soát.

### 7.2. Quyền tự mở rộng (privilege escalation)

Một principal tuy không có quyền sửa firewall trực tiếp nhưng có quyền:

- Gán một **IAM role có quyền cao** cho service/workload mà họ điều khiển.
- **Impersonate service account** hoặc assume role tin cậy quá rộng.
- Sửa chính sách trust/binding để thêm chính mình.
- Chỉnh CI/CD pipeline và chạy job dưới identity deployer mạnh hơn.
- Tạo VM/container rồi gắn privileged instance profile hoặc service account.

thì vẫn có thể **gián tiếp đạt quyền sửa network**. Đánh giá **chuỗi nâng quyền**, không chỉ liệt kê các network API trong policy của user.

## 8. Separation of duties và ma trận trách nhiệm

Một thay đổi network production nên có **requester, reviewer/approver, deployer, verifier** với trách nhiệm tách bạch theo mức độ rủi ro.

| Vai trò | Đọc inventory | Đề xuất IaC | Phê duyệt | Apply prod | Bảo vệ log/guardrail |
|---|---|---|---|---|---|
| **Developer** | Theo app/scope | Có, repo app | Không tự duyệt | Không trực tiếp | Không |
| **Network engineer** | Theo nhiệm vụ | Có, repo network | Peer review tùy risk | JIT/hạn chế | Không vô hiệu guardrail |
| **Security reviewer** | Read all cần thiết | Có thể đề xuất | Duyệt policy security | Tách khỏi reviewer khi cần | Review config/drift |
| **CI deployment role** | Chỉ state và scope cần | Không tự viết ý định | Không | Có theo pipeline | Không |
| **Security platform operator** | Theo owner | Có ở repo guardrail | Theo change board | Qua pipeline riêng | Có quyền riêng và audit |
| **Auditor/SOC** | Read-only + log | Không | Không | Không | Chỉ xem, điều tra |
| **Emergency operator** | Theo incident | Hotfix được duyệt | Quy trình emergency | Quyền tạm/ghi log | Có giám sát độc lập |

**SoD không chỉ là hai ô checkbox trong PR.** Nếu một người có thể sửa nhánh bảo vệ, tự approve và assume deploy role, thì không có phê duyệt độc lập. Cần bảo vệ **repo settings, CODEOWNERS, branch policies, CI secrets/identity và IAM permission to alter pipeline**.

### 8.1. RACI cho thay đổi lớn

- **Responsible:** Network engineering xây phương án và kế hoạch rollback.
- **Accountable:** Owner mạng/sản phẩm chịu trách nhiệm thay đổi.
- **Consulted:** Security/identity, SRE, application owner và đối tác kết nối.
- **Informed:** SOC/NOC, help desk, người bị ảnh hưởng.

Đối với **mở Internet access, thay default route, nối prod–partner hoặc tắt inspection/logging**, phải có quy trình approval tương xứng; không giao toàn bộ cho một người sở hữu tài khoản admin.

## 9. Ma trận quyền theo cấp độ rủi ro

| Nhóm thay đổi | Dev/Test | Production app zone | Shared network / Security perimeter | Gợi ý cấp quyền |
|---|---|---|---|---|
| Xem routes/SG/NSG | Read theo scope | Read theo scope | Read có giám sát | Viewer |
| Thêm rule HTTPS tới app | Operator theo owner | Qua IaC + review | Chỉ nếu approved | Scoped deployer |
| Mở SSH/RDP public | Không mặc định | Deny theo baseline | Deny/break-glass đặc biệt | Guardrail |
| Sửa default route | Limited sandbox | Change riêng | Rủi ro cao | Network operator + review |
| Sửa peer/transit | Sandbox có hạn | Approval nhiều owner | Rủi ro cao | Network core team |
| Sửa firewall/WAF allowlist | Test scope | Security review | Security owner | Security deploy role |
| Tắt Flow Logs/Audit export | Không mặc định | Deny | Chỉ security emergency process | Separate security role |
| Sửa IAM role deploy | Không | Không | Chỉ IAM/security admins | Segregated identity team |
| Xóa VPC/VNet/VPN gateway | Sandbox có kiểm soát | Approval/backup/rollback | Highly restricted | Short JIT emergency |
| Thay DNS private zone | Theo service dev | Ownership + change | Shared resolver impact review | DNS-specific scoped role |

**Hạn chế hành động nguy hiểm không chỉ bằng tên “admin”.** Tạo lớp policy riêng cho hoạt động **Create, Update, Delete, Attach, Associate, Share/Peering và DisableLogging**. Một role có thể thiếu quyền Delete nhưng vẫn làm hỏng mạng qua UpdateRoute.

## 10. AWS: IAM, Organizations và các thay đổi VPC

### 10.1. Các lớp bảo vệ chính

AWS có thể kết hợp:

- **IAM identity-based policies** cho role/user.
- **Role trust policy** quyết định ai có thể assume role.
- **AWS Organizations SCP** ở phạm vi tổ chức/account liên quan để giới hạn quyền tối đa theo mô hình áp dụng.
- **IAM permissions boundary, session policy và explicit deny**, tùy luồng cấp quyền.
- **Resource policies** ở các dịch vụ hỗ trợ, ví dụ endpoint hoặc service-specific resources.
- **IAM condition keys** khi API/action hỗ trợ; không đồng nhất khả năng lọc theo tag giữa mọi action.
- **CloudTrail, AWS Config, VPC Flow Logs** và các dịch vụ ghi nhận mạng/audit liên quan.

**SCP không tự cấp quyền** cho role, và cũng không thay IAM permissions. **Permissions boundary không tự cấp quyền**; nó có tác dụng giới hạn theo evaluation logic tương ứng. Khi thiết kế phải đánh giá cả **permissions được cấp thực, trust của role và con đường assume role**.

### 10.2. Những hành động EC2/VPC cần đặc biệt rà soát

Ví dụ API tên thường gặp (không phải danh sách đầy đủ):

| Nhóm | Ví dụ API/action | Tác động |
|---|---|---|
| Security group ingress | **ec2:AuthorizeSecurityGroupIngress**, **ec2:RevokeSecurityGroupIngress** | Thêm/bỏ luật inbound |
| Security group egress | **ec2:AuthorizeSecurityGroupEgress**, **ec2:RevokeSecurityGroupEgress** | Thay quyền đi ra |
| Routing | **ec2:CreateRoute**, **ec2:ReplaceRoute**, **ec2:DeleteRoute** | Đổi next hop/reachability |
| Route association | **ec2:AssociateRouteTable**, **ec2:ReplaceRouteTableAssociation** | Đổi route table được áp vào subnet/gateway |
| Network ACL | **ec2:CreateNetworkAclEntry**, **ec2:ReplaceNetworkAclEntry**, **ec2:DeleteNetworkAclEntry** | Đổi lọc stateless theo ACL |
| Peering | **ec2:CreateVpcPeeringConnection**, **ec2:AcceptVpcPeeringConnection** | Tạo trust/connectivity giữa VPC |
| Flow logging | **ec2:CreateFlowLogs**, **ec2:DeleteFlowLogs** | Bật/tắt khả năng quan sát VPC flows |
| IAM-dependent | **iam:PassRole** và các quyền liên quan khi API yêu cầu role | Cho phép service nhận role có thể quá mạnh |

Khả năng **resource-level scoping, request/resource tag conditions và dependent actions phải tra IAM service authorization reference** của từng API trước khi viết policy production. Không giả định chỉ vì thấy một ARN của security group thì mọi action nêu trên đều giới hạn được bằng ARN đó.

### 10.3. Ví dụ tư duy cấp quyền

Nhân viên ứng dụng cần đọc SG và đề xuất thay đổi rule dev. Không cấp **ec2:* trên mọi resource** chỉ vì cần sửa một rule. Thiết kế:

1. Role **ReadNetworkInventory** chỉ có các hành động Describe/List cần thiết.
2. IaC pipeline có **deployer role** được giới hạn vào tài khoản môi trường và loại tài nguyên phù hợp.
3. Guardrail kiểm soát **public SSH/RDP, overly broad egress, deletion of flow logging** theo khả năng thực thi.
4. Role dùng trong pipeline có **trust policy** chỉ cho phép đúng repo/ref/environment đã phê duyệt.
5. **CloudTrail/Config** theo dõi API mutations, **VPC Flow Logs** đo data-plane flows; hai nguồn không thay nhau.

### 10.4. Tag-based IAM không phải lời giải toàn diện

Một policy dựa trên tag như **Environment=dev** hữu ích khi resource/action hỗ trợ, nhưng cần giải quyết **ai được đặt/thay tag**, hành động tạo resource chưa có tag, tài nguyên dùng chung, các API không hỗ trợ tag condition và tài nguyên phụ thuộc. Một attacker có quyền sửa tag có thể tìm cách làm tài nguyên **trông giống dev** trước khi thay cấu hình nếu policy không bảo vệ điều đó.

## 11. Azure: RBAC, PIM và quản trị mạng theo scope

Trong Azure, quyền quản lý hạ tầng thường áp qua **Azure RBAC** trên các scope như management group, subscription, resource group và resource. Một role có các **Actions** control-plane; khả năng dữ liệu **DataActions** khác biệt theo tài nguyên/dịch vụ.

### 11.1. Role built-in phải đọc kỹ

**Network Contributor** là một role phổ biến cho quản lý tài nguyên mạng, nhưng **có thể quá rộng** nếu cấp ở scope subscription hoặc resource group chứa nhiều VNet, NSG, LB và routing resources. **Owner** còn có khả năng quản lý quyền truy cập trong scope; không gán Owner để "sửa network một lần".

Khi cần chỉ cho sửa một phần, có thể xem **custom role** với action/scope phù hợp; nhưng phải kiểm tra khả năng scope ở từng resource và các action phụ thuộc của ARM/provider. Không dựa vào tên role như lời đảm bảo giới hạn nội dung của NSG rule.

### 11.2. Azure control và audit

| Lớp | Mục tiêu |
|---|---|
| **Azure RBAC** | Ai được phép gọi action quản lý tài nguyên ở scope |
| **Microsoft Entra ID** | Danh tính, đăng nhập, MFA, workload identities theo kiến trúc |
| **Privileged Identity Management (PIM)** | Quyền đặc biệt đủ thời gian/approval khi có cấu hình/licensing thích hợp |
| **Azure Policy** | Đánh giá/deny/modify/audit cấu hình theo policy effects tương ứng |
| **Resource locks** | Hạn chế một số thao tác xóa/sửa theo loại lock và hành vi ARM |
| **Activity Log** | Ghi control-plane events ở phạm vi liên quan |
| **Network Watcher/NSG flow logs, virtual network flow logs theo khả năng nền tảng** | Quan sát lưu lượng và troubleshoot network |
| **Diagnostic settings / Log Analytics** | Đưa telemetry được hỗ trợ tới sink được quản trị |

**Không mặc định resource lock hoặc Azure Policy thay được IAM RBAC.** Policy effect, exemption, assignment scope và quyền được miễn trừ cần có audit/approval riêng. Với log sources, phải xem **tính năng hiện hành và kế hoạch chuyển đổi** của từng dịch vụ thay vì mặc định một loại flow log tồn tại lâu dài như cũ.

### 11.3. Tình huống thực tế

Một đội ứng dụng cần thay backend pool của LB dev. Nếu được gán Network Contributor ở cả subscription production, họ có thể sửa các network resources ngoài nhiệm vụ. Cách tiếp cận tốt hơn là **scope resource/resource group phù hợp**, hoặc giao thay đổi qua pipeline được kiểm soát và review các action đặc quyền thực tế.

**Khả năng tạo role assignment không nên trộn với quyền thay đổi NSG/route**. Quyền quản lý IAM nếu cấp chung có thể tạo đường nâng quyền qua role assignment.

## 12. Google Cloud: IAM, Shared VPC và Organization Policy

Google Cloud phân quyền theo **organization → folder → project → resource** khi cấu hình tương ứng. IAM roles có thể là basic, predefined hoặc custom; quyền được kế thừa qua resource hierarchy theo mô hình áp dụng.

### 12.1. Nhóm quyền mạng thường gặp

| Nhu cầu | Ví dụ tiếp cận | Phải kiểm tra |
|---|---|---|
| Đọc cấu hình mạng | Viewer/custom read-only | Có xem được routes/firewall/addresses/flow logs cần thiết không? |
| Quản trị mạng | Role network administrator hoặc custom network role | Có quyền sửa production/shared networks ngoài mục tiêu không? |
| Quản lý firewall | Role security administrator hoặc policy-specific role theo product | Có quyền làm yếu firewall policies/priority không? |
| Quản trị DNS | DNS-specific role theo zone | Scope zone, private visibility, record-set changes |
| Shared VPC | Network permissions ở host project và service project | Service project identity có thể tác động host network tới mức nào? |
| Automation | Service account + workload federation | Ai có quyền impersonate/attach/actAs service account? |

Các role predefined như **roles/compute.networkAdmin** hoặc **roles/compute.securityAdmin** chỉ là ví dụ tên role để bắt đầu đánh giá, **không phải bản kê quyền bất biến**. Phải kiểm tra danh sách permission hiện hành và phạm vi của project/resource.

### 12.2. Shared VPC là ranh giới quan trọng

Trong Shared VPC, **host project** quản lý tài nguyên mạng dùng chung, còn **service projects** gắn workloads. Nếu cấp role quá rộng ở host project, một principal từ nhóm app có thể ảnh hưởng **nhiều service projects**. Cần tách **network governance trong host** khỏi **deploy workload ở service project** và hạn chế quyền liên quan **attach/use subnet/network** theo thiết kế.

### 12.3. Organization Policy và audit

- **Organization Policy** có thể áp constraints được hỗ trợ để giới hạn kiến trúc/chức năng cloud.
- **Cloud Audit Logs** ghi các loại hoạt động theo khả năng dịch vụ/cấu hình; chú ý sự khác nhau giữa administrative activity và data access logs.
- **VPC Flow Logs/Firewall Rules Logging** hỗ trợ data-plane analysis nhưng không thay audit ai đã thay firewall.
- **Cloud Asset Inventory** có thể giúp theo dõi cấu hình và drift; quyền đọc/asset exports cũng cần kiểm soát.

**Organization Policy không tự cấp IAM permissions**. IAM deny, conditions và tag mechanisms có giới hạn phạm vi/điều kiện riêng; không giả định một custom condition có thể chặn **mọi** thay đổi firewall rule hoặc route trên mọi loại tài nguyên.

## 13. So sánh mô hình ba cloud theo mục tiêu

| Mục tiêu | AWS | Azure | Google Cloud |
|---|---|---|---|
| Principal có quyền network API | IAM roles/policies | Azure RBAC roles | IAM roles/bindings |
| Tổ chức/phạm vi cấp quyền | Organizations/OU/account/resource theo support | Management group/subscription/resource group/resource | Org/folder/project/resource |
| Giới hạn tổ chức | SCP và guardrails khác | Azure Policy, deny assignments theo bối cảnh | Organization Policy, IAM deny theo hỗ trợ |
| Cấp quyền tạm | Role assumption/session, federation, approval workflow | Entra PIM/JIT workflows | Short-lived credentials, IAM workflow/JIT theo tổ chức |
| Human vs CI identity | Federated identities/role trust | Entra workload identity/service principal | Service account/workload identity federation |
| Audit thay đổi | CloudTrail/Config | Activity Log/resource change history | Cloud Audit Logs/Asset Inventory |
| Logs packet/flow | VPC Flow Logs và network telemetry | Flow/network telemetry phù hợp sản phẩm | VPC Flow Logs/Firewall Rules Logging |
| IaC | CloudFormation, Terraform/OpenTofu | Bicep/ARM, Terraform/OpenTofu | Terraform/OpenTofu, cloud-native tools |

**Điểm chung quan trọng hơn tên sản phẩm:** scope chính xác, quyền thao tác tối thiểu, bảo vệ identity dùng để deploy, guardrail kiểm tra **nội dung cấu hình**, audit độc lập và test data plane sau thay đổi.

## 14. IAM cho CI/CD và Infrastructure as Code

Một cách tổ chức hiệu quả là **con người đề xuất network change**, pipeline thực hiện bằng **identity được kiểm soát** sau khi code review và policy tests.

~~~mermaid
flowchart TD
    A[Engineer mở PR cấu hình mạng] --> B[Static checks + lint + security policy-as-code]
    B --> C[IaC plan / diff có artifacts]
    C --> D{Review + owner approval đúng scope?}
    D -- Không --> X[Từ chối deploy]
    D -- Có --> E[Protected workflow / short-lived cloud role]
    E --> F{IAM + org guardrail cho thay đổi này?}
    F -- Không --> X
    F -- Có --> G[Apply only approved plan]
    G --> H[Audit API mutations + drift/config snapshots]
    H --> I[Connectivity & segmentation tests]
~~~

### 14.1. Những quyền pipeline cần được bảo vệ

1. **Repo write/merge**: ai có thể thay IaC và file policy?
2. **Branch protection**: ai có thể bỏ review hoặc sửa CODEOWNERS?
3. **CI config**: ai có thể đổi workflow để chạy lệnh không được duyệt?
4. **Federated trust**: cloud role có ràng buộc đúng repo/org/ref/environment và audience/issuer được kiểm tra không?
5. **Plan artifact**: artifact đã duyệt có thực sự là thứ được apply, hay pipeline chạy plan mới không review?
6. **Cloud IAM**: deploy role chỉ có quyền đối với resources/actions liên quan, không có quyền mở rộng IAM của chính nó?
7. **IaC state**: state có thể chứa IP, topology, secrets và cần encryption/RBAC/audit/locking?
8. **Rollback**: route/firewall sau apply có được xác minh và có cách đảo an toàn không?

### 14.2. Không dùng credential tĩnh dài hạn nếu có lựa chọn tốt

Cloud federation/OIDC với **short-lived sessions** thường giúp giảm nguy cơ lộ khóa dài hạn trong repository/CI variables. Tuy nhiên nếu trust conditions quá rộng, một workflow từ branch/PR không được duyệt có thể assume **role production**. **Không chỉ bật OIDC rồi coi là an toàn**; phải kiểm tra claims, environment protection và role privilege.

### 14.3. Plan review phải đủ hiểu hậu quả

Một IaC plan chỉ cho thấy diff cấu hình được công cụ nhận diện, không chứng minh **route được đi qua firewall, traffic không thể bypass, hoặc một security rule không mở rộng reachability ngoài ý muốn**. Review cần thêm **effective routes, reachability analysis, blast radius, dependencies, return paths và application SLI**.

## 15. Guardrail chính sách mạng: chặn nội dung cấu hình nguy hiểm

Một số lỗi không thể xử lý chỉ bằng việc cho phép/sai quyền trên một resource: người có quyền thay **security group hợp lệ** vẫn có thể viết **rule nguy hiểm**.

### 15.1. Ví dụ nguyên tắc guardrail

| Guardrail | Mục tiêu | Ngoại lệ cần xem xét |
|---|---|---|
| Không mở SSH/RDP public tới workload production | Giảm exposure quản trị | Bastion/JIT có approval |
| Không tạo allow-all inbound cho DB/Management | Bảo vệ phân đoạn | Không cấp ngoại lệ tự động |
| Không gắn Internet gateway cho subnet nhạy cảm theo baseline | Giảm đường công khai ngoài dự kiến | Kiến trúc đã được review |
| Không tắt network/audit logging | Đảm bảo phát hiện và điều tra | Emergency theo quy trình độc lập |
| Không tạo route bypass firewall/inspection zone | Giữ kiến trúc bảo vệ | Routing exception có owner/expiry |
| Không tạo peering prod–partner ngoài allowlist | Giới hạn trust expansion | Multi-owner approval |
| Không cho phép IAM role deploy tự gán quyền cao hơn | Chống privilege escalation | Không miễn trừ tùy tiện |
| Không dùng public endpoint cho service chỉ cần private | Giảm attack surface | Thực sự có business justification |
| Mọi network change có tag/owner/change_id | Truy trách nhiệm và review | Lưu ý tag không thay control thực |

### 15.2. Policy-as-code là lớp bổ sung

Có thể dùng **OPA/Rego, Sentinel, Checkov, tfsec hoặc công cụ phù hợp** để đánh giá IaC plan trước apply. Nó cần kết hợp với **cloud-native guardrails**, vì một người có quyền console/API đủ mạnh có thể bypass pipeline nếu chỉ kiểm tra ở CI.

### 15.3. Ví dụ policy dạng pseudocode

~~~yaml
# PSEUDOCODE minh họa ý định. KHÔNG phải rule AWS/Azure/GCP chạy trực tiếp.
network_change_guardrails:
  environment: "production"
  default_result: "deny_unless_explicitly_approved"
  controls:
    - id: "NO_PUBLIC_ADMIN"
      resource_types: ["security_group_rule", "nsg_rule", "firewall_rule"]
      when:
        source_any: ["0.0.0.0/0", "::/0"]
        destination_ports_any: [22, 3389]
      result: "deny"

    - id: "PROTECT_SECURITY_LOGGING"
      resource_types: ["flow_log", "audit_export", "diagnostic_setting"]
      actions: ["delete", "disable", "replace_with_unapproved_sink"]
      result: "deny_except_emergency_process"

    - id: "PROTECT_DEFAULT_ROUTES"
      resource_types: ["route_table", "udr", "transit_route"]
      when:
        destination_any: ["0.0.0.0/0", "::/0"]
        next_hop_outside_approved_inventory: true
      result: "require_network_security_approval"

    - id: "PEERING_APPROVAL"
      resource_types: ["vpc_peering", "vnet_peering", "shared_vpc_attachment"]
      when:
        connects_trust_domains: true
      result: "require_both_network_owners_approval"

  evidence:
    require_change_id: true
    require_actor_and_deployer_identity: true
    require_policy_version: true
    require_post_change_reachability_tests: true
~~~

Đây là **điều kiện logic** để thảo luận, không phải lời hứa một provider có thể kiểm tra từng nội dung rule bằng IAM native. Một số guardrail cần **IaC policy, admission/custom validation hoặc công cụ kiểm soát bên ngoài**, cộng với cơ chế ngăn bypass.

## 16. Quản trị route, firewall và peering: IAM cho phép không đồng nghĩa mạng được duyệt

Một thay đổi network có thể tạo nhiều hệ quả gián tiếp:

~~~mermaid
flowchart LR
    A[Principal có quyền Create/Replace Route] --> R[New route to transit/peer/NAT]
    R --> F[Firewall/Inspection path]
    R --> B[App/DB/Management reachability]
    P[Principal có quyền sửa SG/NSG] --> B
    B --> T{Đúng baseline phân đoạn?}
    T -- Không --> X[Access ngoài phạm vi / Incident]
    T -- Có --> Y[Approved network path]
~~~

### 16.1. Default route có tác động đặc biệt

Đổi **0.0.0.0/0** hoặc **::/0** sang next hop khác có thể thay Internet egress, lọc DNS, inspection, NAT và khả năng giám sát. Trong cloud đa mạng, một route cụ thể hơn có thể thắng default route và tạo bypass ở **một subnet nhất định**, nên kiểm thử chỉ default route chưa đủ.

### 16.2. Peering không có nghĩa mọi subnet tự thông

Một peering/transit attachment được tạo chưa mặc nhiên mang lại đầy đủ connectivity; còn có **route tables, firewall/security group, DNS resolution, ingress/egress và các ràng buộc provider**. Tuy nhiên chính quyền tạo/kích hoạt peering vẫn nên được xem là **thay đổi trust boundary có rủi ro cao**, vì nó có thể mở đường cho các bước cấu hình tiếp theo.

### 16.3. Rule priority và trạng thái thực tế

Một firewall rule mới có thể bị rule ưu tiên cao hơn che, hoặc vô tình override kiểm soát đã có. IAM audit ghi **người đổi rule**, còn data-plane verification phải kiểm tra **effective security policy**, priority, direction, protocol, stateful/stateless semantics và dịch vụ đích.

### 16.4. IPv4 và IPv6 là hai mặt của cùng chính sách

Không chỉ ngăn mở **0.0.0.0/0** mà quên **::/0**. Một chính sách sản xuất có thể block public SSH ở IPv4 nhưng một automation role vẫn tạo IPv6 allow-all. Guardrail và kiểm thử phải bao gồm **IPv4/IPv6, subnet ULA/private ranges, DNS A/AAAA và return path**.

## 17. IAM đối với DNS, endpoint và đường truy cập riêng

Nhiều đội chỉ bảo vệ IAM của firewall và route mà bỏ qua **DNS, private endpoints và identity của các kết nối dịch vụ**. Một record DNS mới có thể đổi destination mà ứng dụng kết nối; một private endpoint có thể tạo reachability tới dịch vụ nhạy cảm theo đường không sử dụng egress proxy vốn được tổ chức giám sát.

### 17.1. DNS changes có thể ảnh hưởng bảo mật

| Thay đổi | Rủi ro | Phân quyền/kiểm soát đề xuất |
|---|---|---|
| Record A/AAAA/CNAME public | Chuyển traffic tới endpoint không kiểm soát, đổi nơi kết thúc TLS | DNS-specific role, zone/record owner review |
| Private DNS zone association | Tên nội bộ trả IP khác giữa VPC/VNet | Review tác động cross-network, log association |
| DNS forwarding/resolver rule | Chuyển truy vấn nội bộ tới resolver không mong đợi | Network/security approval, DNS query telemetry |
| DNSSEC/trust configuration | Lỗi validation hoặc thay trust boundary | Tách role quản lý khóa/chính sách với người thay record thường |
| Endpoint private DNS | App đi vào private endpoint hoặc sai đích | Kiểm tra DNS view, endpoint policy, certificate/hostname |
| Record dành cho API/WAF | Chuyển sang origin trực tiếp, bỏ qua WAF/CDN | Phải so DNS route với allowlist origin |

**DNS không tự cấp phép mạng**, nhưng một thay đổi DNS có thể làm app kết nối tới **IP được route/firewall cho phép mà không còn là dịch vụ mong đợi**. Vì vậy DNS mutation cần được xem xét trong threat model **kênh TLS, mTLS, DNS security và egress**.

### 17.2. Private endpoint không tự tạo Zero Trust

Một endpoint private có thể giảm phụ thuộc Internet public, nhưng vẫn cần **IAM trên service**, endpoint/resource policy nếu hỗ trợ, route, security group/NSG, DNS, workload identity và kiểm toán. **Private không đồng nghĩa authorized**. Tách người được phép tạo private endpoint, người phê duyệt kết nối vào service và người cấu hình DNS tương ứng nếu rủi ro cao.

### 17.3. DNS zone thường có quyền ảnh hưởng rộng hơn một record

Một operator được quyền sửa tất cả records trong zone shared-services có thể ảnh hưởng endpoint authentication, service discovery, private CA endpoint, VPN gateway hoặc API gateway. Nếu cloud không hỗ trợ granularity ở cấp record phù hợp, dùng **zone delegation/tách private zone, deployment broker và review** để giảm blast radius.

## 18. Cloud Network Firewall, WAF, LB và TLS: ai được thay kiểm soát?

Cấu hình mạng hiện đại không chỉ gồm port và IP. **Cloud Network Firewall, WAF, service mesh, API gateway, LB listeners và TLS termination** có thể quyết định traffic nào được xác thực, ghi log và chuyển đến backend.

### 18.1. Những thay đổi không nên gộp vào một role

- Đổi **TLS security policy, minimum protocol version, listener certificate, SNI/backend trust**.
- Đổi **WAF managed/custom rule mode** từ BLOCK sang COUNT, thêm bypass/exemption.
- Thay **LB target group/backend pool** tới service ngoài danh sách.
- Tắt **mTLS peer validation** hoặc thêm CA mới vào trust bundle.
- Cho phép **direct-origin access** bypass WAF qua public IP.
- Đổi firewall **priority, default action, inspection subnet hoặc policy route**.
- Tắt **flow/WAF/access logs** và thay log sink sang đích không được quản trị.

Những thay đổi đó có thể cần quyền cloud service khác với **network resource mutation** thông thường. Giải pháp là **permission inventory theo API thực**, owner của control và control-plane audit; không dùng network-wide administrator như mặc định cho một thao tác LB.

### 18.2. Xác minh đường end-to-end sau thay đổi

~~~mermaid
flowchart LR
    U[Internet / VPN Client] --> E[DNS + CDN/WAF]
    E --> L[LB TLS / mTLS]
    L --> F[Network Firewall / SG / NSG]
    F --> A[Approved API]
    E -. Direct-to-origin path must be blocked .-> X[Origin bypass]
    A --> D[Private DB]
    P[IAM / IaC network change] --> E
    P --> L
    P --> F
~~~

Một thay đổi LB có thể giữ HTTPS ở browser nhưng làm mất xác thực TLS ở đoạn edge–origin. Người phê duyệt network change phải có **kiểm tra luồng ứng dụng, certificate, identity của upstream và bảo mật đường đi**, không chỉ "listener vẫn up".

## 19. Tag, condition và resource ownership: dùng đúng giới hạn

**ABAC** là kỹ thuật dùng thuộc tính như environment, owner, cost center hoặc project để quyết định quyền. Trong cloud networking, tag/label hỗ trợ quản trị khi số tài nguyên lớn, nhưng là **dữ liệu có thể bị thay đổi** nếu IAM không bảo vệ quyền sửa tag.

### 19.1. Ví dụ owner-based control

~~~text
Principal: role/app-team-a-network-operator
Scope: subscription/project/account ứng dụng A
Resource ownership: Team=AppA, Environment=dev
Allowed intent: thay rule TCP 443 tới service dev đã đăng ký
Denied intent: sửa route prod, mở SSH công khai, xóa flow logs
Approver: AppA owner + Network reviewer cho rule ngoài baseline
~~~

Các field trên là **yêu cầu thiết kế**, không phải syntax thực thi của IAM bất kỳ. Cần xác minh provider hỗ trợ **resource/request-tag condition** trên đúng API và cách giới hạn tag mutation.

### 19.2. Bốn lỗ hổng ABAC thường gặp

1. **Tag tự sửa được:** principal đổi Environment=prod thành dev rồi chạy action.
2. **Create action thiếu resource tags:** một số tài nguyên chỉ xuất hiện sau khi tạo hoặc tag được gắn ở bước riêng.
3. **Shared resources:** một shared route table có thể phục vụ nhiều team, không thể xem tag Owner=TeamA là quyền sửa toàn bộ.
4. **Action không hỗ trợ condition:** một policy trông chặt nhưng permission thực chưa bị giới hạn như thiết kế.

**Thực hành:** cấm hoặc kiểm soát **TagResource/Untag/UpdateTags** tương đương theo cloud; enforce naming/tagging ở IaC và kiểm tra inventory thực; tách hạ tầng shared network ra scope riêng nếu cần.

### 19.3. IAM Conditions không phải data-plane firewall

Một condition như **chỉ cho thao tác tại region X** hoặc **chỉ trong phiên được yêu cầu MFA** là kiểm tra quyền API. Nó không bảo đảm traffic chỉ đi trong region X hoặc chặn kết nối ngang sau khi tài nguyên thay đổi. Vẫn cần **routing, VPC firewall, DNS và workload authorization**.

## 20. Policy mẫu: đọc mạng nhưng không có quyền sửa

Để phục vụ điều tra, một role có thể được cấp quyền đọc inventory thay vì quyền chỉnh sửa.

### 20.1. Ví dụ AWS IAM read-only giới hạn về loại action

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadNetworkInventory",
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeVpcs",
        "ec2:DescribeSubnets",
        "ec2:DescribeRouteTables",
        "ec2:DescribeSecurityGroups",
        "ec2:DescribeNetworkAcls"
      ],
      "Resource": "*"
    }
  ]
}
~~~

**Ý nghĩa:** cho phép một số API **Describe** để đọc cấu hình EC2/VPC, không có API mutation trong statement này. Với nhiều hành động Describe, AWS yêu cầu **Resource: "*"** theo service authorization model; điều này **không đồng nghĩa policy tự cấp quyền sửa bất kỳ network nào**.

**Giới hạn quan trọng:** đây là **mẫu học tập cho riêng một phần quyền đọc**. Identity có thể còn policy/role khác; không thể kết luận effective permissions chỉ bằng JSON trên. Nếu không muốn đọc toàn account, cần cân nhắc **account separation, region controls có hỗ trợ, inventory proxy hoặc data export được lọc**. Mẫu trên cũng chưa đủ quyền đọc CloudTrail/Config/flow telemetry.

### 20.2. Role design dạng trung lập cloud

~~~yaml
# Pseudocode policy contract, không dùng trực tiếp với AWS/Azure/GCP.
role: "dev-network-deployer"
owner: "Platform Security"
principal:
  type: "short-lived-ci-workload"
  repo: "network-iac"
  environment: "development"
scope:
  account_or_project: "app-dev"
  resource_groups: ["app-a-dev"]
allow_actions:
  - "read_network_inventory"
  - "create_or_update_approved_app_https_rule"
  - "create_app_subnet_within_approved_cidr"
deny_intents:
  - "modify_production_route_tables"
  - "open_public_ssh_or_rdp"
  - "disable_security_logging"
  - "create_external_peering"
  - "change_own_iam_permissions"
approval:
  protected_branch_required: true
  network_change_review_required: true
  approved_plan_digest_required: true
  short_session_required: true
validation:
  - "cloud_iam_effective_permissions"
  - "provider_native_guardrails"
  - "iac_policy_checks"
  - "post_deploy_reachability"
~~~

Các mục **deny_intents** mô tả **mục tiêu vận hành**, không phải một cú pháp IAM portable; cần triển khai bằng guardrail/provider action, môi trường tách biệt, policy-as-code và test thực.

## 21. Đường nâng quyền qua IAM, role attachment và pipeline

Threat model IAM phải xét **các hành động gián tiếp** có thể dẫn tới quyền quản lý network:

~~~mermaid
flowchart TD
    A[User có quyền sửa CI hoặc attach role] --> B{Có thể gọi workload/role đặc quyền?}
    B -- Không --> X[Không nâng quyền qua đường này]
    B -- Có --> C[Privileged Deploy Identity]
    C --> D{Có network mutation API?}
    D -- Có --> E[Thay SG/Route/Firewall/Logs]
    D -- Không --> F[Tiếp tục đánh giá quyền khác]
    E --> G[Potential security boundary change]
~~~

### 21.1. Các quyền không mang chữ "network" nhưng rất nhạy cảm

| Quyền/phạm vi | Vì sao có thể ảnh hưởng mạng |
|---|---|
| **Role trust/assumption/impersonation** | Có thể sử dụng network admin role gián tiếp |
| **PassRole/attach instance profile** | Workload có thể nhận role mạnh rồi gọi network API |
| **Role assignment/binding** | Có thể tự cấp Network Contributor hoặc quyền cao hơn |
| **Modify CI/CD workflow settings** | Chạy pipeline deploy đã có network permissions |
| **Update infrastructure template/state** | Chèn change vượt review nếu pipeline áp toàn bộ |
| **Manage policy exemptions** | Tạo ngoại lệ cho public ingress/default route |
| **Control audit sink/keys** | Che dấu thay đổi network, ngăn điều tra |
| **Edit DNS/identity endpoint** | Tác động nơi client kết nối hoặc credentials được thu thập |
| **Create service principal/credentials** | Tạo đường truy cập bền vững hoặc khó quy trách nhiệm |

### 21.2. Cách giới hạn privilege chaining

- Cấp quyền quản trị IAM riêng với network operator.
- Kiểm tra **ai có thể assume/impersonate role deploy** và các claims trust trong federation.
- Hạn chế **role assignment, PassRole, service account actAs**, và tình huống attach privileged identity theo provider.
- Bảo vệ CI config/branch approvals và credential của IaC runner.
- Theo dõi hành vi **grant rights ngay trước network change** bằng correlation audit.
- Không cho deployer tự tắt log hoặc sửa policy cấm chính thao tác nó thực hiện.

**Một IAM policy không có ec2:CreateRoute hoặc quyền tương đương vẫn chưa đủ để kết luận principal không thể đổi route**, nếu nó có thể điều khiển role có quyền ấy.

## 22. Privileged Access, JIT và break-glass

### 22.1. JIT thay quyền thường trực

Với hoạt động production rủi ro cao, yêu cầu **quyền tạm theo nhiệm vụ**:

1. Người vận hành đăng nhập qua SSO, MFA theo yêu cầu.
2. Tạo change request gắn **resource scope, action, justification, hạn thời gian**.
3. Approval phù hợp cấp rủi ro.
4. Cấp role/session ngắn hạn với quyền tối thiểu cần.
5. Ghi audit **activation, API calls, resource changes và deactivation**.
6. Tự chấm dứt quyền và kiểm tra entitlement đã thu hồi.

Không đánh đồng **MFA** với việc đã có chấp thuận nghiệp vụ; MFA xác minh người đăng nhập, còn approval đánh giá **phạm vi thay đổi**.

### 22.2. Break-glass khi control plane có sự cố

Ví dụ network firewall lỗi làm gián đoạn VPN tới production, IAM federation hoặc CI/CD cũng bị ảnh hưởng. Tổ chức có thể cần một **đường emergency được định nghĩa trước**, nhưng:

- Không sử dụng credential shared không thể quy trách nhiệm như mặc định.
- Giới hạn người giữ quyền, lưu và sử dụng credential theo quy trình.
- Có alert khi kích hoạt, ghi lại hành động qua audit độc lập khi khả thi.
- Có **post-incident review** và thu hồi quyền/rotate credentials sau khi dùng.
- Test định kỳ trong môi trường an toàn để biết đường khôi phục thực sự hoạt động.

### 22.3. Quyền tạm không ngăn đổi cấu hình vĩnh viễn

Một admin JIT có thể tạo route/security rule còn tồn tại **sau khi phiên quyền hết hạn**. Vì thế phải có **change expiration/cleanup**, IaC reconciliation và scan compliance sau JIT. Thu hồi role không tự đảo mọi network mutation.

## 23. Audit: phân biệt thay đổi cấu hình với lưu lượng qua mạng

**IAM/control-plane audit** và **data-plane network telemetry** có mục đích khác nhau.

| Câu hỏi điều tra | Nguồn chính | Nguồn bổ sung |
|---|---|---|
| Ai thêm public SSH rule? | Cloud API audit / change history | IaC PR, role session, ticket |
| Rule đã có hiệu lực ở subnet nào? | Configuration inventory/effective policy | Reachability analysis, packet test |
| Sau thay đổi có kết nối TCP tới port 22 không? | Flow/firewall/network logs | Bastion/host audit |
| Ai tắt flow logging? | Cloud control-plane audit | IaC diff, org policy violations |
| Ai tạo peering/route? | Control-plane API events | Route table snapshots, pipeline audit |
| Traffic đã thoát qua đâu? | Flow logs/NAT/firewall/IDS telemetry | DNS/proxy/app logs |
| Một policy đã được phê duyệt chưa? | Change ticket/PR approvals | Cloud API actor/version |
| Ai gán quyền cho principal trước thay đổi? | IAM/role assignment audit | IdP/PIM/CI logs |

### 23.1. JSON event chuẩn hóa minh họa

~~~json
{
  "schema_version": "1.0",
  "event_time": "2026-11-28T10:12:45.021Z",
  "event_type": "CLOUD_NETWORK_CONFIG_CHANGED",
  "cloud_provider": "example-cloud",
  "account_scope": "prod-network",
  "region": "region-a",
  "actor_type": "federated_ci_role",
  "actor_id": "network-iac-deployer",
  "session_id": "session-opaque-4d11",
  "api_action": "ReplaceRoute",
  "resource_type": "route_table",
  "resource_id": "rtb-demo-17",
  "change_id": "CHG-EXAMPLE-420",
  "approval_ref": "PR-EXAMPLE-42",
  "old_destination": "10.20.0.0/16",
  "old_next_hop": "inspection-gateway",
  "new_next_hop": "transit-gateway",
  "evaluation": "NEEDS_SECURITY_REVIEW",
  "audit_event_id": "audit-8f913"
}
~~~

Đây là **event chuẩn hóa giả định**, không phải bản ghi CloudTrail/Azure/GCP native và không cung cấp ID thật. **Audit log một API thành công** chưa xác nhận tất cả data-plane nodes đã áp cấu hình hoặc traffic thực đi theo route mới. Cần state/config snapshot và reachability tests.

### 23.2. Các trường nên tương quan

- **Cloud actor** được xác thực: user/role/service principal/service account, session, source/assumed identity.
- **API action/resource ID**; before/after config hoặc hash/diff được cho phép lưu.
- **Event time, ingest time, region/zone, account/project/subscription**.
- **Policy/role version, org guardrail result** khi có.
- **Change ticket/PR/pipeline run ID**, owner và approval.
- **Resource ownership, Environment, classification** từ inventory có kiểm soát.
- **Network flow, firewall, WAF, DNS và IDS/IPS** nếu cần đánh giá tác động.

Đừng dựa vào **user-agent string, X-Forwarded-For hay một source IP** để nhận diện người đã thay mạng khi audit platform đã có **federated principal/session identity** đáng tin hơn.

### 23.3. Audit log cũng cần được bảo vệ

Tách quyền sửa/xóa audit sink khỏi network deployer; cân nhắc **central log archive, immutable retention, encryption, IAM/RBAC read controls, detection tắt logging** theo yêu cầu. Không lưu **cloud credentials, access token, private key hoặc payload cấu hình có secret** trong ticket/log export.

## 24. Detection engineering cho thay đổi mạng trái chuẩn

SOC không thể đặt alert cho **mọi Write API** với cùng severity: một pipeline deploy rule HTTPS đúng giờ rất khác một principal bất thường xóa flow logs trước khi mở Internet ingress.

### 24.1. Những detection hữu ích

| Giả thuyết | Tín hiệu | Điều cần loại trừ |
|---|---|---|
| Public ingress quá rộng | Create/Update rule source 0.0.0.0/0, ::/0, port nhạy cảm | Public LB được phê duyệt, rule bị rule khác chặn |
| Route bypass inspection | ReplaceRoute/UDR đổi next hop của subnet nhạy cảm | Failover/DR đã duyệt, route chưa áp |
| Tắt security telemetry | Delete/Disable flow log, diagnostic sink, WAF log | Maintenance change và migration logging |
| Privilege chaining trước network change | IAM role grant/assume/impersonation rồi mutation | JIT hợp lệ đúng approval |
| Peering ngoài danh sách | Tạo/accept peering hoặc attach transit sai owner | Dự án network được phê duyệt |
| Network admin API từ context lạ | Session mới, source/region/time khác baseline | Di chuyển văn phòng/VPN hoặc on-call |
| Thay private DNS tới endpoint lạ | DNS change + TLS errors/egress shift | Planned cutover hoặc DR |
| Network resources không có owner | Newly created resources thiếu tag/CMDB owner | API tạo tag sau do service |
| IaC drift ngoài pipeline | Cloud API mutation không có PR/run ID | Emergency hotfix có ticket |
| IPv6 public exposure | Rule ::/0 hoặc IPv6 route mới | IPv6 rollout hợp lệ với firewall đầy đủ |
| Guardrail exception bất thường | Policy exemption/override được cấp không theo review | Sự cố cần break-glass |
| Lỗi IAM deny tăng | AccessDenied cho mutation lặp bất thường | Script sai version hoặc read permission thiếu |

### 24.2. Ví dụ alert chuẩn hóa

~~~json
{
  "alert_type": "UNAPPROVED_NETWORK_ROUTE_CHANGE",
  "severity": "high",
  "confidence": "needs_validation",
  "cloud_scope": "prod-network",
  "resource_type": "route_table",
  "resource_id": "rtb-demo-17",
  "actor": "network-iac-deployer",
  "audit_event_id": "audit-8f913",
  "change_ref": null,
  "reason": "Next hop changed outside approved baseline",
  "evidence": [
    "control_plane_mutation",
    "effective_route_diff",
    "missing_approved_change_reference"
  ],
  "triage": "Check emergency change registry and network reachability"
}
~~~

Một change thiếu PR mapping có thể đến từ **hotfix khẩn cấp hợp lệ, lỗ hổng telemetry mapping hoặc hành vi trái phép**. Alert phải nói rõ giả thuyết và độ tin cậy, không tự kết luận ác ý.

### 24.3. Correlation theo đường tấn công

Một chuỗi đáng chú ý có thể là **CreateNewPrincipal → Grant Network Role → Modify Firewall → Change Route → Disable Logs → Data Egress**. Nhưng các thành phần có thể xuất hiện trong **một hoạt động DR hợp lệ**; SOC cần so **principal, change approval, resource ownership, thời gian, network flows và hậu quả**.

## 25. Công cụ chẩn đoán chỉ đọc: AWS, Azure, Google Cloud

Các ví dụ sau chỉ minh họa **read-only inspection**. Chạy trên tài khoản/project của tổ chức với quyền được cấp và profile phù hợp. **Không dùng quyền admin rộng hơn chỉ vì một lệnh trả AccessDenied**, không ghi token/access key lên terminal chia sẻ hoặc ticket.

### 25.1. AWS CLI

~~~bash
# Xem identity đang được dùng, không hiển thị secret access key.
aws sts get-caller-identity

# Xem security groups và routes ở region được phép.
aws ec2 describe-security-groups --region us-east-1
aws ec2 describe-route-tables --region us-east-1

# Xem cấu hình VPC flow logs ở region được phép.
aws ec2 describe-flow-logs --region us-east-1

# Tìm audit events gần đây theo tên API (nếu có quyền/nguồn phù hợp).
aws cloudtrail lookup-events \
  --region us-east-1 --lookup-attributes AttributeKey=EventName,AttributeValue=AuthorizeSecurityGroupIngress
~~~

**Lưu ý:** CloudTrail Event History/LookupEvents có phạm vi loại events/thời gian/region và quyền riêng; không thay **organization-wide trails, CloudTrail Lake hoặc archival logs**. Tên region và tài khoản phải thay theo môi trường được phê duyệt. Output có thể tiết lộ topology/tags nên giữ đúng RBAC.

### 25.2. Azure CLI

~~~bash
# Hiển thị subscription/identity context, chỉ đọc.
az account show

# Xem role assignments trong phạm vi được phép (ví dụ subscription hiện tại).
az role assignment list --all

# Xem NSGs và route tables trong resource group đã được cho phép.
az network nsg list --resource-group example-network-rg
az network route-table list --resource-group example-network-rg

# Xem Activity Log trong scope được cấp quyền.
az monitor activity-log list --max-events 20
~~~

**Lưu ý:** lệnh list có thể trả nhiều tài nguyên nhạy cảm; trong thực tế nên giới hạn scope/filters phù hợp và kiểm tra entitlement trước khi chạy. Azure Activity Log khác data-plane flow telemetry và không bảo đảm capture toàn bộ chi tiết policy effect.

### 25.3. Google Cloud CLI

~~~bash
# Kiểm tra project đã chọn và identity hiện tại (không xuất tokens).
gcloud config get-value project
gcloud auth list

# Xem IAM policy của project được cấp quyền.
gcloud projects get-iam-policy example-project-id

# Danh sách firewall rules và routes của project.
gcloud compute firewall-rules list --project=example-project-id
gcloud compute routes list --project=example-project-id

# Tra admin activity logs đã được phép, giới hạn số record.
gcloud logging read \
  'logName:"cloudaudit.googleapis.com%2Factivity"' \
  --project=example-project-id --limit=20
~~~

**Lưu ý:** output/log filter và quyền đọc phụ thuộc sản phẩm và cấu hình. IAM Policy hiển thị **bindings**, không tự thể hiện mọi org/folder inheritance/deny/conditional logic; cần đánh giá **effective permissions** ở hierarchy thực.

### 25.4. Vì sao không đưa lệnh tạo rule vào bài kiểm tra IAM?

Các lệnh **CreateRoute, authorize ingress, change role assignment hoặc DeleteFlowLogs** có thể gây outage/lộ dữ liệu. Để chứng minh một principal bị từ chối mutation, nên dùng **IAM Policy Simulator/test-permissions API nếu phù hợp**, **IaC policy tests trong lab**, hoặc test tài nguyên staging đã cấp phép. Không thử sửa production security group chỉ để xem AccessDenied.

## 26. Kiểm tra quyền thực tế và những giới hạn của simulator

IAM policy JSON hay RBAC role definition chỉ cho biết **các statement được khai báo**. Muốn chứng minh một principal có thể hoặc không thể thực hiện network mutation, cần xét:

1. **Session thực** có đúng identity, MFA/context và scope không?
2. Các policy ở tổ chức/account/project/folder và resource-level có cùng hiệu lực không?
3. Action có hỗ trợ resource-level/conditions định sử dụng không?
4. Có **dependent permission** hoặc service permission cần thêm không?
5. Principal có đường **impersonate/assume/pass/assign** một role cao hơn không?
6. Service-specific rules, quotas hoặc policy validation có thể chặn dù IAM allow không?
7. Resource/tag/condition có thay đổi giữa **thời điểm plan và apply** không?

### 26.1. Policy simulator cho kết quả giới hạn

Một simulator có thể giúp đánh giá một tập IAM statements/context mô phỏng, nhưng **không phải lúc nào cũng bao quát mọi side effect của cloud API, service-specific auth, policy propagation hay network reachability**. Cần bổ sung **provider logs, staging negative tests, IaC policy-as-code và real effective config inspection**.

### 26.2. Kiểm thử deny không yêu cầu phá production

Có thể dùng:

- **Static policy review:** tìm wildcard actions, Resource "*", quyền sửa IAM, logging, routes và firewall.
- **Permission simulation:** khi provider cung cấp và đủ chính xác cho mục tiêu.
- **Staging account/project:** role được giới hạn thật, tài nguyên test và rollback độc lập.
- **Dry-run/plan** khi API/công cụ hỗ trợ, với giới hạn của từng sản phẩm.
- **Production canary có phép:** thay đổi hẹp, kiểm tra allow/deny dưới change control, không thử bypass không được duyệt.

### 26.3. Phân biệt IAM deny và network deny

Một kỹ sư cố sửa SG rồi bị **AccessDenied** là **IAM control-plane deny**. Một client không kết nối được TCP 5432 tới DB vì security group từ chối là **data-plane deny**. Hai nguồn phải log và test riêng.

## 27. Baseline, drift detection và quyền sửa ngoài IaC

Cloud console/API và IaC thường cùng tồn tại. Nếu mọi người dùng console sửa production rồi pipeline sau đó ghi đè lại từ state, tổ chức có thể gặp **drift, outage hoặc hồi phục giả**.

### 27.1. Baseline bảo mật

Tạo baseline được review cho:

- Security group/NSG/firewall ingress/egress và rule priority.
- Route tables, default routes, firewall path, VPC/VNet peerings.
- DNS zones/resolvers/private endpoints và certificate/TLS entrypoints.
- NAT, VPN, load balancer/target groups, WAF policy.
- Flow/security logs, audit sinks và IAM role assignments.
- Owners, change ID, environment, tags/labels và compliance policy.

### 27.2. Các loại drift

| Loại | Ví dụ | Xử lý |
|---|---|---|
| **Unapproved** | Người không thuộc change window mở public SSH | Điều tra, áp deny/rollback theo incident |
| **Emergency hotfix** | On-call sửa route để khôi phục dịch vụ | Ghi change ID, merge về IaC, review hậu kiểm |
| **Provider-managed** | Cloud service điều chỉnh ENI/route/target phụ thuộc | Hiểu ownership trước khi xóa |
| **Automation conflict** | Hai controllers cùng sửa một SG | Tách ownership, tránh race |
| **Partial rollout** | Region A đã cập nhật policy, region B chưa | Theo dõi config revision/health/failover |
| **Tag drift** | Resource đổi Environment thành dev trái phép | Kiểm tra IAM, tag audit và compliance |
| **Log config drift** | Flow log destination đổi sang sink khác | Xác minh audit/retention và guardrail |

### 27.3. Không tự động rollback mọi drift

Nếu hệ thống phát hiện **mất default route**, auto revert có thể phá một **DR failover** đang diễn ra. Với thay đổi rủi ro thấp, tự reconcile có thể phù hợp. Với **transit, VPN, shared-network route, firewall global policy và IAM grants**, cần policy phân loại **an toàn tự sửa hay phải có xác nhận owner**.

### 27.4. Drift monitoring và audit phải bổ sung

Audit cho biết **ai gọi API**, còn drift cho thấy **state hiện tại khác baseline**. Audit event thiếu hoặc không đầy đủ không đồng nghĩa không có thay đổi; có thể do collector, provider-managed operations hoặc nguồn dữ liệu chưa được tích hợp. Dùng hai nhóm bằng chứng để có kết luận đáng tin hơn.

## 28. Đánh giá rủi ro và thiết kế change approval

Không phải mọi network change cần cùng cấp phê duyệt. Tuy nhiên **quyền IAM luôn phải giới hạn hành động**, kể cả khi change đã được duyệt ở quy trình nghiệp vụ.

### 28.1. Các yếu tố chấm rủi ro

| Yếu tố | Câu hỏi đánh giá | Ví dụ rủi ro cao |
|---|---|---|
| **Exposure** | Thay đổi có tạo đường Internet hoặc cross-trust không? | Public SSH/DB, mở 0.0.0.0/0 và ::/0 |
| **Asset criticality** | Đích có dữ liệu/đường quản trị nhạy cảm không? | Prod DB, backup, IAM/control plane |
| **Blast radius** | Thao tác ảnh hưởng một host hay toàn region/shared network? | Transit route/global firewall |
| **Permanence** | Có tự hết hạn/rollback không? | Peering/allow-all tồn tại vô hạn |
| **Identity assurance** | Actor và session có đủ kiểm soát không? | Shared credential không MFA |
| **Detection coverage** | Có audit, flow log và alert hay không? | Xóa log cùng lúc thay policy |
| **Change reversibility** | Có thể phục hồi mà không mất phiên/dữ liệu không? | Xóa VPN gateway, đổi CIDR/route rộng |
| **Dependencies** | DNS, IAM, cert, LB, WAF, VPN, failover có bị ảnh hưởng? | Chuyển route bỏ qua inspection |
| **Environment** | Dev, staging hay production, isolated hay shared? | Shared hub cho nhiều accounts/projects |
| **External trust** | Đối tác/Internet/network khác có được nối vào không? | Peering partner với prod transit |

### 28.2. Phân cấp thay đổi minh họa

- **Thấp:** read-only inventory, hoặc thay record/dịch vụ dev tách biệt có rule validation.
- **Trung bình:** mở một HTTPS service cho một source được duyệt, thay LB target staging với owner review.
- **Cao:** thay route production, peering, security group DB, network firewall hoặc private DNS zone dùng chung.
- **Rất cao:** mở quản trị công khai, tắt audit, thay guardrail, cấp IAM admin, đổi cloud transit/global egress ngoài inspection.

**Đây không phải công thức điểm số bắt buộc**. Tổ chức cần thiết lập risk appetite và approval matrix riêng. Không nên tự hạ mức rủi ro chỉ vì thay đổi được ghi bằng Terraform thay vì console.

### 28.3. Change record chuẩn

~~~yaml
# Pseudocode: bản ghi mô tả thay đổi, không phải quyền IAM tự thực thi.
network_change:
  change_id: "CHG-EXAMPLE-420"
  environment: "production"
  owner: "network-platform-team"
  requester_role: "network-engineer"
  deployer_role: "network-iac-deployer"
  affected_resources:
    - "route-table:rtb-demo-17"
    - "subnet:app-prod-a"
  proposed_action: "ReplaceRoute"
  reason: "Planned inspection gateway migration"
  approved_next_hops:
    previous: "inspection-gateway-a"
    target: "inspection-gateway-b"
  risk: "high"
  approvals:
    network_owner: "approved"
    security_reviewer: "approved"
  window:
    start: "2026-11-28T10:00:00Z"
    end: "2026-11-28T11:00:00Z"
  controls:
    - "reviewed_iac_plan"
    - "provider_iam_guardrail"
    - "ipv4_ipv6_reachability_validation"
    - "audit_and_flow_logging"
  rollback: "Reapply reviewed previous route after verification"
  expiration: "review_after_implementation"
~~~

Không ghi access token, private key, secret hoặc cấu hình khách hàng nhạy cảm vào change record. Các trường **approved** phải liên kết tới **nguồn phê duyệt đáng tin**, không phải do người tự khai trong IaC file.

## 29. Runbook triển khai phân quyền IAM cho thay đổi cấu hình mạng

### Bước 1 — Inventory quyền và tài nguyên

Liệt kê cloud accounts/subscriptions/projects, OU/folder/management groups, VPC/VNet, routing hub, shared-network services, firewall/WAF, DNS, VPN, LB, private endpoints và log sinks. Xác định ai đang có **IAM owner/admin/network roles**, kể cả CI identities và vendors.

**Bằng chứng:** bản phân loại resource owner, sensitivity, current role bindings và action catalog. Không chỉ xem group membership; cần effective permissions và đường assume/impersonate roles.

### Bước 2 — Vẽ trust boundaries

Đánh dấu ranh giới **Internet–edge, prod–dev, shared hub–spoke, cloud–on-prem, cloud–partner, cloud–management, workload–data**. Chỉ ra một mutation ở resource nào có thể thay đổi luồng qua boundary đó.

**Bằng chứng:** route topology, SG/NSG/firewall baseline, DNS, NAT, TLS endpoints và các điểm IDS/IPS/WAF quan sát được.

### Bước 3 — Định nghĩa role và SoD

Tạo ma trận **principal → action → resource → environment → JIT/session → reviewer**. Tách **view, propose, approve, deploy, emergency và audit**. Giới hạn quyền quản lý IAM, logging, org policy và security guardrails khỏi nhóm app operator.

**Bằng chứng:** role definitions được review, policy simulator/test, session trust và owner/expiry.

### Bước 4 — Áp guardrail và workflow

Đưa cấu hình mạng vào IaC, bảo vệ branches và pipeline role. Thực thi policy-as-code ngăn **public admin ports, unapproved default routes, logging disabled, peering/trust expansion**. Kết hợp org-native guardrail ở mức cloud để chống bypass pipeline.

**Bằng chứng:** linter/policy checks, plan artifacts, PR approvals, deployment trace.

### Bước 5 — Pilot tại scope cô lập

Dùng account/project/subscription lab hoặc network dev độc lập. Kiểm thử **đúng role được sửa tài nguyên được duyệt**, role ấy **không được sửa prod/shared resources**, không được tự nâng quyền và không thể vô hiệu log. Kiểm tra IPv4/IPv6 và quyền liên quan resource association.

### Bước 6 — Triển khai tăng dần

Canary theo team/region/resource group, giới hạn session và quan sát audit. Đảm bảo thay đổi quyền không làm automation quan trọng thất bại hoặc tạo hành vi work-around dùng admin key.

### Bước 7 — Kiểm chứng data plane

Sau mỗi network mutation quan trọng, chạy **allow/deny reachability tests**, xác minh firewall/inspection path, return route, DNS, TLS/mTLS, VPN, WAF và application SLI. **IAM allow thành công không chứng minh network policy an toàn**.

### Bước 8 — Review định kỳ và loại bỏ quyền thừa

Đối chiếu actual API usage với role permissions, xóa **unused/expired grants**, thu hồi vendor access, phát hiện privileged paths và cập nhật guardrail khi thêm cloud products mới. Điều tra mọi change ngoài IaC và map hotfix hợp lệ trở lại baseline.

~~~mermaid
flowchart TD
    A[Inventory principals + network resources] --> B[Trust boundaries + threat model]
    B --> C[Least-privilege IAM role matrix]
    C --> D[Org guardrails + IaC approvals]
    D --> E[Staging positive/negative tests]
    E --> F{IAM denies correctly AND allowed work succeeds?}
    F -- Không --> G[Fix role/condition/trust/dependent permissions]
    G --> C
    F -- Có --> H[Canary production rollout]
    H --> I[Effective config + network reachability tests]
    I --> J[Audit/drift/privileged access review]
    J --> B
~~~

## 30. Runbook khi phát hiện thay đổi mạng trái phép

### Tình huống

SOC nhận cảnh báo một principal đã **AuthorizeSecurityGroupIngress / thay NSG ingress** để cho phép kết nối quản trị từ Internet tới một VM production, rồi kiểm tra thấy security flow logs không còn cập nhật trên một subnet liên quan.

### Giai đoạn 1 — Xác nhận và phân loại

1. Ghi **incident ID, timestamp, cloud account/scope, resource ID, actor/session, API action**.
2. So sánh change với **ticket/PR/JIT activation và emergency change register** để phân biệt hotfix hợp lệ và trái phép.
3. Xác minh rule đã **thực sự áp dụng** và có đường tới VM từ Internet không: route, public IP/LB, IPv4/IPv6, NSG/SG, firewall priority, NACL, host firewall.
4. Xác định logging gap có do **DeleteFlowLogs/diagnostic setting** hay pipeline outage/retention thay đổi.
5. Lưu evidence theo quy trình: audit events, policy diff, role session, effective configuration, flow data hiện còn và deploy records.

**Không kết luận exfiltration đã xảy ra chỉ vì có rule mở**. Đánh giá đường kết nối thực, dấu hiệu session, app/host logs và network flows trước khi kết luận tác động.

### Giai đoạn 2 — Khoanh vùng quyền và traffic

- Với hành vi rõ trái phép hoặc có dấu hiệu account compromise, phối hợp IAM/SOC để **thu hồi session, vô hiệu/rotate credential, giới hạn assume/impersonation và khóa đường nâng quyền**.
- Áp **deny/rollback hẹp** tại điểm network đang mở, tránh xóa VPC/VNet hoặc làm gián đoạn toàn bộ hệ thống khi chưa cần.
- Nếu cloud policy guardrail bị sửa, khôi phục version được phê duyệt với owner của guardrail.
- Đảm bảo logs được ghi tới **sink được quản trị**; tránh mất thêm bằng chứng do thay đổi gấp.
- Phối hợp SRE/Network owner để giữ các luồng nghiệp vụ cần thiết và đường quản trị emergency an toàn.

### Giai đoạn 3 — Kiểm chứng khôi phục

Test **đích hợp lệ vẫn truy cập được**, public admin port bị deny, route/inspection path đúng, IPv6 không tạo bypass, logging và alert hoạt động. Kiểm tra ở nhiều region/gateway và sau failover nếu phạm vi ảnh hưởng.

### Giai đoạn 4 — Điều tra nguồn gốc

Các câu hỏi cần trả lời:

- Actor dùng **human role, CI role, vendor access hay service account**?
- Quyền được cấp trực tiếp hay qua **PassRole/impersonation/role assignment**?
- Có change ở **IAM, pipeline trust, repo settings, policy exemption, DNS hoặc logging** trước network mutation không?
- Tài nguyên và dữ liệu nào có thể reachable trong khoảng thời gian rule mở?
- Có session/bằng chứng truy cập thực, hay mới chỉ là **exposure**?
- Guardrail nào không chặn và vì sao: unsupported API condition, tag abuse, org policy exception hay monitoring gap?

### Giai đoạn 5 — Hậu kiểm và phòng ngừa

Khắc phục chính sách role/guardrail, bổ sung negative tests, bảo vệ deploy identity, rút ngắn session, review SoD và tăng detection. Gắn owner/expiry cho mọi ngoại lệ, lưu **timeline và mức độ chắc chắn**; không tự động suy diễn người có tên trong audit là người đã trực tiếp thao tác nếu credential có thể bị lộ.

## 31. Ma trận kiểm thử IAM và bảo mật mạng cloud

Mỗi phép thử sử dụng **tài nguyên và principal test do tổ chức quản lý**; IAM denial tests ưu tiên **simulator/lab/staging**. Không thử sửa production để "xem có bị chặn không" ngoài change plan được phê duyệt.

| ID | Kịch bản | Kết quả mong đợi | Bằng chứng |
|---|---|---|---|
| **T-01** | Viewer xem VPC/VNet/routes | ALLOW đúng read action | IAM audit/config listing |
| **T-02** | Viewer cố mutation ở lab | DENY | Simulator/API deny event |
| **T-03** | App deployer sửa rule HTTPS của app dev | ALLOW theo scope và nội dung được duyệt | IaC plan, audit, connectivity |
| **T-04** | App deployer sửa SG/NSG production | DENY | IAM/guardrail decision |
| **T-05** | Operator cố mở 0.0.0.0/0 port 22 trong staging | DENY theo guardrail | Policy-as-code/native guardrail |
| **T-06** | Operator cố mở ::/0 port 3389 | DENY theo dual-stack policy | IPv6 policy check |
| **T-07** | Network operator cập nhật route test đã duyệt | ALLOW | Audit/route diff/reachability |
| **T-08** | Operator đổi default route prod ngoài approval | DENY/JIT required | IAM/CI/guardrail |
| **T-09** | Người dùng có quyền tạo SG nhưng gắn SG khác zone | DENY nếu ngoài quyền | Resource association policy |
| **T-10** | App role tạo peering tới partner | DENY | Peering permission/audit |
| **T-11** | Team authorized tạo peering test hai đầu | ALLOW sau phê duyệt | Owner reviews, route/firewall tests |
| **T-12** | App role xóa flow logs/diagnostic export | DENY | Audit/security role policy |
| **T-13** | Security role triển khai log sink approved | ALLOW, logs còn đúng | Sink/retention validation |
| **T-14** | Principal sửa tag prod thành dev rồi mutate | Không vượt được ABAC | Tag permission + IAM evaluation |
| **T-15** | Resource tạo mới chưa có tag | Deny hoặc kiểm soát bootstrap theo thiết kế | Create/Tag flow audit |
| **T-16** | CI job từ branch không được duyệt yêu cầu prod role | DENY role assumption | Federation trust/CI logs |
| **T-17** | Protected CI job dùng short-lived deploy identity | ALLOW scoped apply | Session/PR/plan audit |
| **T-18** | Deployer tự sửa quyền chính nó | DENY | IAM permission checks |
| **T-19** | Deployer thử PassRole/attach privileged role ngoài scope | DENY | Dependent-action guardrail |
| **T-20** | Human admin dùng PIM/JIT approved | Có quyền chỉ trong thời hạn | Activation/deactivation audit |
| **T-21** | Quyền JIT hết hạn | API mutation tiếp theo bị deny | Effective permission retest |
| **T-22** | JIT admin tạo rule rồi rời phiên | Rule có expiration/reconciliation | Config inventory/drift |
| **T-23** | Policy guardrail bị yêu cầu bypass | DENY nếu không có exception hợp lệ | Policy exemption audit |
| **T-24** | Network hotfix ngoài IaC trong lab | Drift alert, phân loại owner | Audit + state diff |
| **T-25** | Thay private DNS zone association sai VPC | DENY hoặc cần multi-owner approval | DNS/control-plane audit |
| **T-26** | Tạo private endpoint test | ALLOW đúng service; backend auth vẫn bắt buộc | Route/DNS/IAM validation |
| **T-27** | Public origin trực tiếp bypass WAF | Bị chặn theo network policy | Reachability test |
| **T-28** | LB target thay tới backend ngoài allowlist | DENY theo policy/review | IaC plan + effective config |
| **T-29** | Service role có cert/mTLS nhưng IAM không đủ | Mutation bị deny | IAM/control-plane audit |
| **T-30** | AWS SCP/permissions boundary restrict role | Deny dù role có một allow khác | Effective policy evaluation |
| **T-31** | Azure RBAC scoped RG khác subscription rộng | Role không sửa resource ngoài scope | RBAC test lab |
| **T-32** | GCP Shared VPC service project không có host network admin | Không được chỉnh host-wide network | IAM binding review |
| **T-33** | IPv4/IPv6 firewall rules sau deploy | ALLOW/DENY đúng trên cả hai stacks | Flow/firewall/reachability |
| **T-34** | API mutation thành công nhưng effective path khác dự kiến | Kiểm tra data-plane, phát hiện mismatch | Route/inspection path tests |
| **T-35** | Flow log collector down | Health alert, không suy ra no traffic | Heartbeat/ingest lag |
| **T-36** | Multi-region failover giữa gateways | Guardrail và quyền đồng nhất | Regional audit/config checks |
| **T-37** | Audit event và IaC PR không mapping | Alert và triage change ownership | Change ID/actor/session |
| **T-38** | Break-glass được kích hoạt trong drill | Alert, audit, review và revoke sau drill | PIM/IAM/security logs |
| **T-39** | Partner/vendor access hết hạn | Quyền bị thu hồi đúng scope | Entitlement audit |
| **T-40** | Regression sau đổi IAM/guardrail | Quyền hợp lệ vẫn chạy, mutation nguy hiểm bị deny | Positive + negative tests |

### 31.1. Bắt buộc có test ALLOW và DENY

Nếu chỉ test **DENY**, policy có thể vô tình chặn luôn đội ứng dụng hoặc CI triển khai HTTPS hợp lệ. Nếu chỉ test **ALLOW**, role có thể còn đủ quyền mở public DB/SSH hoặc sửa prod routes. Cả **chức năng nghiệp vụ và mức bảo vệ** phải được chứng minh.

### 31.2. Phân biệt ba loại kết quả

- **IAM DENY:** principal không có quyền gọi API.
- **Policy/guardrail REJECT:** yêu cầu hoặc cấu hình không đạt chuẩn dù một lớp IAM có thể đã cho phép.
- **Data-plane DENY:** kết nối mạng sau thay đổi không được firewall/route policy cho phép.

Không viết một test "AccessDenied" chung cho cả ba vì cách khắc phục và ý nghĩa security khác nhau.

### 31.3. Kiểm thử failover và propagation

Một network control-plane change có thể được áp theo thứ tự giữa regions, gateways, route tables hoặc phụ thuộc cloud API eventual consistency. Nên kiểm tra **effective config, policy version, time window, client connectivity và rollback** tại những vị trí có tác động; không suy rằng một API success đảm bảo mọi instance đã áp ngay lập tức.

## 32. Mười hai tình huống thực tế

### Tình huống A — Developer được gán quyền Network Admin ở subscription production

**Quan sát:** team chỉ cần sửa rule app dev nhưng được cấp một role quản trị network ở scope bao gồm production.

**Rủi ro:** sai thao tác hoặc lộ credential có thể tác động route, NSG, LB và các network tài nguyên ngoài nhiệm vụ.

**Giải pháp:** tách môi trường, giảm scope, tách read/propose/apply, dùng IaC deployer có quyền hạn chế và policy checks. Kiểm thử **được sửa dev nhưng không sửa được prod**.

### Tình huống B — Một IAM policy chỉ cho SG app nhưng vẫn mở public SSH

**Quan sát:** principal chỉ có quyền một SG application, sau đó thêm source 0.0.0.0/0 TCP 22.

**Nguyên nhân:** resource-level least privilege **không kiểm soát nội dung rule**. Cần guardrail rule content, review kế hoạch và negative test ở API/CI hoặc enforcement phù hợp.

### Tình huống C — Automation role có quyền attach role khác

**Quan sát:** pipeline không có network admin action trực tiếp, nhưng có quyền gán một privileged IAM role cho compute/job mà nó điều khiển.

**Phân tích:** đây là **đường privilege chaining**. Giới hạn PassRole/actAs/role assignment, trust policy và quyền điều khiển pipeline; audit chuỗi từ credential tới network API.

### Tình huống D — AWS SCP chặn thay route nhưng đội vẫn khẳng định role cho phép

**Quan sát:** role policy có allow action nhưng API trả AccessDenied.

**Phân tích:** có thể có org guardrail, permissions boundary, session policy, resource condition hoặc deny khác. Đánh giá **effective permissions** và bối cảnh session; **không xóa SCP** để giải quyết khi chưa biết mục đích bảo vệ.

### Tình huống E — Azure Network Contributor được gán ở resource group chung

**Quan sát:** một resource group chứa cả LB application và NSG/route production dùng chung.

**Rủi ro:** role gán ở resource group có thể vượt nhu cầu app owner dù không cấp toàn subscription. Cân nhắc **tách resource group theo ownership**, dùng custom role nếu phù hợp và broker/pipeline có review.

### Tình huống F — GCP Shared VPC host project mở rộng quyền ngoài ý muốn

**Quan sát:** developer từ một service project được cấp quyền thay network firewall ở host project.

**Rủi ro:** ảnh hưởng nhiều service projects. Tách quyền quản trị host network, gắn quyền use subnet theo thiết kế và kiểm tra bindings kế thừa trong hierarchy.

### Tình huống G — Flow logs dừng sau thay policy

**Quan sát:** SOC thấy số flow records về 0 và có audit event thay logging config.

**Phân tích:** có thể là xóa/đổi sink, lỗi collector hoặc thực sự không có traffic. So **control-plane audit, producer/collector health, request/flow baseline**, khôi phục logging trước khi kết luận không có truy cập.

### Tình huống H — Thay DNS private khiến application đi sai backend

**Quan sát:** ứng dụng vẫn có route và firewall allow nhưng certificate hostname mismatch hoặc kết nối sang endpoint khác.

**Phân tích:** record/forwarder/private zone association thay đổi. So DNS audit, split DNS, TLS certificate, ingress và network flow. Giới hạn quyền DNS theo zone/service owner; không tắt hostname verification để "sửa".

### Tình huống I — CI/CD apply một plan khác bản đã duyệt

**Quan sát:** PR review cho phép sửa app HTTPS, nhưng pipeline tái tạo plan sau khi thêm resource mới và apply không qua phê duyệt.

**Rủi ro:** **time-of-check/time-of-use**; approval không còn gắn với artifact đã áp. Dùng protected workflows, artifact digest/plan ID, concurrency/locking, reapproval nếu plan thay đổi và IAM guardrail độc lập.

### Tình huống J — IPv4 deny đúng nhưng IPv6 public rule mở rộng

**Quan sát:** baseline kiểm soát 0.0.0.0/0 nhưng không kiểm tra ::/0, còn API gateway/host hỗ trợ IPv6.

**Xử lý:** bổ sung **dual-stack guardrail và reachability tests**, DNS AAAA/route validation, host firewall/SG/NSG parity. Không chỉ tắt IPv6 như phản ứng mặc định.

### Tình huống K — Partner peering đã được duyệt nhưng route mở sang DB

**Quan sát:** peering kết nối site đối tác tới môi trường đã có route propagation/SG quá rộng.

**Bài học:** IAM approval tạo peering không thay **scope route export/import, firewall, segmentation và application authorization**. Review cả hai đầu và giám sát các đường dữ liệu thực.

### Tình huống L — Break-glass khôi phục sự cố rồi để lại allow-all

**Quan sát:** on-call mở rule tạm cho khôi phục nhưng quên thu hồi sau khi phiên JIT hết hạn.

**Xử lý:** emergency change có **rule expiration, ticket, owner, log, post-incident drift review**, tự động nhắc cleanup hoặc reconcile theo risk policy. Quyền tạm không tự hoàn tác cấu hình.

## 33. Những ngộ nhận và lỗi thiết kế

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| **"IAM Network Admin làm toàn mạng an toàn."** | IAM chỉ quyết định ai được sửa; cấu hình đã tạo vẫn phải được kiểm chứng. |
| **"Control-plane IAM deny giống firewall deny."** | Một bên chặn API mutation; một bên chặn gói/flow. |
| **"Chỉ có quyền sửa một SG là an toàn."** | Có thể thêm rule mở mọi nguồn/port trong chính SG đó. |
| **"Cloud org guardrail tự cấp quyền cho role."** | SCP/Org Policy/Policy constraints không thay IAM allow. |
| **"Role có chữ viewer chắc không có mutation."** | Phải kiểm tra permission thực, custom roles và policy khác. |
| **"Tag Environment=dev đủ ngăn sửa prod."** | Phải bảo vệ quyền sửa tag, create flow và APIs hỗ trợ condition. |
| **"Permission simulator PASS là data plane đã an toàn."** | Chỉ đánh giá một phần authorization, không kiểm tra effective routing/firewall. |
| **"MFA đủ để cấp quyền Network Admin vĩnh viễn."** | MFA không thay JIT, scope, approval, SoD hoặc log. |
| **"CI chỉ dùng OIDC là khỏi cần kiểm soát."** | Trust claims, protected branches, role scope và workflow permissions vẫn quan trọng. |
| **"Plan review bảo đảm apply đúng y hệt."** | Cần gắn approved artifact, tránh plan/apply mismatch. |
| **"IAM policy không có network API thì không thể sửa mạng."** | Có thể impersonate/attach role hoặc điều khiển CI có quyền. |
| **"Tạo peering là tự cho toàn bộ VPC thông nhau."** | Route/firewall/DNS khác vẫn quyết định reachability, nhưng peering là thay đổi trust boundary. |
| **"Private endpoint luôn an toàn."** | Vẫn cần IAM, endpoint policy, DNS, security groups và backend authorization. |
| **"DNS chỉ là tên, không cần IAM security."** | DNS change có thể chuyển traffic, bypass edge và gây trust mismatch. |
| **"CloudTrail/Activity/Audit Logs bằng VPC Flow Logs."** | Control-plane audit khác data-plane flow telemetry. |
| **"Audit ghi API success nghĩa là traffic đã đi theo config mới."** | Phải xem effective config, propagation và reachability. |
| **"Ít security alerts nghĩa là ít thay đổi xấu."** | Có thể logging disabled, rule coverage thiếu hoặc ingestion lag. |
| **"Tắt log giúp đỡ tốn tiền mà không có rủi ro."** | Mất forensic evidence và detection; thay sink/retention cần review. |
| **"Chỉ chặn 0.0.0.0/0 là chặn public internet."** | IPv6 ::/0 và các CIDR rộng khác cũng cần đánh giá. |
| **"Xóa role JIT là các rule nó tạo tự hết."** | Network resources/rules thường còn tồn tại tới khi được thay/xóa. |
| **"Mọi drift đều là tấn công."** | Hotfix, autoscaling, cloud-managed changes và conflicts có thể tạo drift. |
| **"Một thay đổi network không cần security nếu chỉ là Terraform."** | IaC có thể áp cấu hình nguy hiểm nếu policy/approval sai. |

## 34. Checklist triển khai an toàn

- [ ] Có inventory cloud networks, IAM principals, app owners, shared resources và trust boundaries.
- [ ] Tách rõ control-plane mutations và data-plane traffic controls.
- [ ] Xác định **ai có quyền xem, tạo, cập nhật, xóa, gắn, peering, tắt logging**.
- [ ] Dùng quyền read-only cho người điều tra không cần mutation.
- [ ] Không cấp network admin rộng cho app team chỉ sửa một service.
- [ ] Giới hạn scope theo môi trường và owner: account/subscription/project/resource phù hợp.
- [ ] Rà soát những API không hỗ trợ resource-level/conditional IAM.
- [ ] Không để principal tự sửa tag/label để vượt ABAC.
- [ ] Bảo vệ IAM role assignment, trust policy, PassRole/actAs/impersonation và CI identities.
- [ ] Human admin dùng SSO/MFA, JIT/PIM khi cần, session và approval có thời hạn.
- [ ] Vendor/partner permissions có owner, scope, expiry và session audit.
- [ ] Có break-glass được bảo vệ, cảnh báo và hậu kiểm; không dùng làm đường thường ngày.
- [ ] Tách người yêu cầu, review, deploy và audit cho thay đổi nhạy cảm.
- [ ] Protected branches, CODEOWNERS và CI workflow không bị bypass bởi cùng một người.
- [ ] IaC plan đã được phê duyệt thực sự là artifact được apply hoặc được reapprove khi thay đổi.
- [ ] CI dùng identity ngắn hạn khi có thể, không lưu network admin keys dài hạn.
- [ ] State/plan/logs của IaC được bảo vệ, không lộ secrets/topology cho người ngoài.
- [ ] Có guardrail chặn public SSH/RDP/DB, cả IPv4 và IPv6 theo chuẩn tổ chức.
- [ ] Kiểm soát default route, inspection path, firewall priority và route propagation.
- [ ] Peering/transit/VPN kết nối trust domains cần multi-owner approval.
- [ ] DNS/private endpoint policies và zone ownership được rà soát IAM.
- [ ] WAF/LB/TLS/mTLS thay đổi có owner và security review riêng theo risk.
- [ ] Không cho deployer tự tắt flow/security/audit logs hoặc sửa log sink ngoài approval.
- [ ] Org-native guardrails bổ sung cho IaC policy-as-code để ngăn console bypass.
- [ ] AWS SCP/permissions boundary, Azure RBAC/Policy/PIM và GCP Org Policy được kiểm tra đúng semantics.
- [ ] Có inventory IAM effective permissions và đường assume/impersonate trong role graph.
- [ ] Mọi change có ticket, owner, before/after, policy version, plan và rollback.
- [ ] Canaries, negative tests và reachability verification được thực hiện theo change plan.
- [ ] Test network path sau thay đổi: firewall, DNS, VPN, NAT, TLS, IPv4/IPv6, failover.
- [ ] Cloud API mutation events được gửi đến audit store có IAM/RBAC/retention phù hợp.
- [ ] Data-plane flow logs được giám sát nhưng không nhầm với config change audit.
- [ ] Có alert cho logging disabled, route bypass, public ingress và privilege chaining.
- [ ] Có monitoring ingestion gaps, drift, config revisions và quyền hết hạn.
- [ ] Hotfix ngoài IaC được review và đưa trở lại baseline; không rollback máy móc gây outage.
- [ ] Không chạy mutation thử trên production ngoài phạm vi được cấp phép.

## 35. Câu hỏi tự kiểm tra

**1. Vì sao IAM đối với network thay đổi là một biện pháp bảo mật riêng so với firewall?**  
IAM quyết định ai được phép gọi API tạo/sửa/xóa cấu hình mạng. Firewall/security group quyết định lưu lượng nào được đi qua theo các rule đang có. Cả quyền thay đổi lẫn nội dung rule đều cần bảo vệ.

**2. Vì sao cấp quyền sửa một security group cụ thể vẫn chưa đủ least privilege?**  
Principal có thể thêm rule cho nguồn/cổng nguy hiểm trong chính SG ấy; cần guardrail kiểm tra nội dung rule và process approval phù hợp.

**3. SCP trong AWS có tự cấp quyền không?**  
Không. SCP giới hạn quyền tối đa theo cơ chế AWS Organizations áp dụng; IAM permissions/trust/session vẫn phải cho phép action phù hợp.

**4. Azure RBAC scope quan trọng thế nào khi gán Network Contributor?**  
Gán ở resource group/subscription rộng có thể cho phép thay đổi nhiều network resources ngoài nhiệm vụ. Cần kiểm tra role actions và scope thực tế.

**5. Vì sao Shared VPC ở GCP đòi tách quyền giữa host project và service project?**  
Host project sở hữu network dùng chung; quản trị network ở đó có thể ảnh hưởng nhiều service projects, dù workload chỉ thuộc một app.

**6. Thêm role từ CI/CD có thể tạo rủi ro gì nếu quyền trực tiếp của developer không có CreateRoute?**  
Developer có thể điều khiển pipeline/deploy role có quyền CreateRoute hoặc quyền tương đương. Cần kiểm tra đường trust/impersonation/role attachment và CI branch protection.

**7. Tại sao quyền JIT hết hạn không đồng nghĩa các firewall rules tạm cũng hết hạn?**  
JIT giới hạn session IAM; các network resources đã thay đổi tồn tại độc lập. Cần cleanup/expiration và drift reconciliation.

**8. Tag-based policy có thể bị vượt bằng cách nào?**  
Nếu principal được sửa Environment/Owner tags, có thể làm tài nguyên trông như thuộc scope thấp hơn; hoặc action không hỗ trợ điều kiện tag nên guardrail không có hiệu lực mong đợi.

**9. Có thể dùng CloudTrail/VPC Flow Logs thay thế nhau không?**  
Không. CloudTrail ghi API/control-plane activities theo cấu hình; VPC Flow Logs ghi metadata flows ở data plane. Cần cả hai để kết luận ai sửa và traffic nào thực xảy ra.

**10. Vì sao một peering được duyệt chưa chắc cho phép mọi luồng?**  
Connectivity còn phụ thuộc route tables, firewall/SG/NSG, DNS, source/destination policies và hạn chế của provider. Nhưng quyền tạo peering vẫn là thay đổi ranh giới tin cậy.

**11. Một IaC plan PASS có chứng minh network an toàn không?**  
Không. Plan cho thấy những thay đổi dự kiến; cần policy validation, cloud guardrails, effective routes/firewall checks và tests sau apply.

**12. Vì sao không nên cho network deploy role xóa flow logs?**  
Principal có thể che dấu đường mạng trước/sau thay đổi; cần phân quyền quản lý telemetry riêng, audit và guardrail chống tắt.

**13. Vì sao bảo vệ IPv4 mà bỏ IPv6 làm chính sách thiếu?**  
IPv6 có route/cidr/allow rules độc lập. ::/0 có thể mở public ingress dù 0.0.0.0/0 đã bị chặn.

**14. Khi thấy AccessDenied trong CLI, nên làm gì thay vì xóa guardrail?**  
Xác minh active principal, session, scope, IAM role, boundaries/SCP/Org Policy, conditions và dependent permissions; hỏi owner approval nếu cần thay quyền.

**15. Tại sao thay private DNS có thể là sự kiện an ninh mạng?**  
DNS có thể đưa ứng dụng đến endpoint khác hoặc bypass CDN/WAF/inspection; cần review zone ownership, trust/TLS và route khi đổi DNS.

**16. Nếu Flow Logs giảm về 0 sau thay cấu hình, có kết luận không có traffic không?**  
Không. Có thể collector mất kết nối, sink bị tắt hoặc dữ liệu đến muộn. Cần đối chiếu audit, producer heartbeat, ingress metrics và network paths.

**17. Thay IAM role trong cloud có cần phê duyệt như thay firewall không?**  
Nếu quyền mới cho phép network mutation hoặc impersonation, tác động có thể tương đương mở firewall. Cần SoD, review và audit theo risk.

**18. Test nào chứng minh một least-privilege role vừa dùng được vừa an toàn?**  
Test **ALLOW** cho action/resource được duyệt và **DENY** cho tài nguyên ngoài scope, nội dung rule nguy hiểm, quyền IAM self-escalation và tắt logging; kiểm tra thêm data-plane sau change.

**19. Khi phát hiện một public SSH rule, cần xem gì trước khi kết luận có xâm nhập?**  
Rule có active/effective không, VM có public path không, firewall/host kiểm soát gì, traffic/session logs và thời gian exposure. Rule mở là rủi ro, chưa tự chứng minh truy cập thực.

**20. Điểm mấu chốt của thay network production được duyệt là gì?**  
Principal đúng quyền ngắn hạn, plan đúng mục tiêu, owner/reviewer phê duyệt, guardrail không bị bypass, audit ghi rõ, data-plane test cả allow/deny và có rollback/expiration.

## 36. Tài liệu tham khảo

- [NIST SP 800-53 Rev. 5 — Security and Privacy Controls](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final): access control, least privilege, audit, change management và security monitoring.
- [NIST SP 800-207 — Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final): hạn chế tin cậy dựa trên vị trí mạng, kiểm tra identity và quyền tài nguyên.
- [NIST SP 800-190 — Application Container Security Guide](https://csrc.nist.gov/pubs/sp/800/190/final): ranh giới quyền workload/container và môi trường triển khai.
- [NIST SP 800-92 — Guide to Computer Security Log Management](https://csrc.nist.gov/pubs/sp/800/92/final): thu thập, bảo vệ và phân tích logs.
- [AWS IAM — Policies and Permissions](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies.html): mô hình IAM policies và evaluation.
- [AWS Service Authorization Reference](https://docs.aws.amazon.com/service-authorization/latest/reference/reference.html): tài nguyên, actions và condition keys thực sự được hỗ trợ.
- [AWS Organizations — Service Control Policies](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps.html): tổ chức guardrails và giới hạn quyền.
- [AWS CloudTrail](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-user-guide.html): API events và audit.
- [AWS VPC Flow Logs](https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs.html): network flow telemetry.
- [Microsoft Learn — What is Azure RBAC?](https://learn.microsoft.com/en-us/azure/role-based-access-control/overview): roles và scopes của Azure.
- [Microsoft Learn — Azure Policy](https://learn.microsoft.com/en-us/azure/governance/policy/overview): constraints/audit/deny và policy effects.
- [Microsoft Learn — Privileged Identity Management](https://learn.microsoft.com/en-us/entra/id-governance/privileged-identity-management/pim-configure): JIT và quản trị đặc quyền.
- [Microsoft Learn — Azure Activity Log](https://learn.microsoft.com/en-us/azure/azure-monitor/essentials/activity-log): control-plane activity telemetry.
- [Google Cloud — IAM Overview](https://cloud.google.com/iam/docs/overview): resource hierarchy, principals, roles và permissions.
- [Google Cloud — Organization Policy](https://cloud.google.com/resource-manager/docs/organization-policy/overview): tổ chức constraints và governance.
- [Google Cloud — Shared VPC Overview](https://cloud.google.com/vpc/docs/shared-vpc): network host/service projects và quyền sử dụng mạng chung.
- [Google Cloud — Cloud Audit Logs](https://cloud.google.com/logging/docs/audit): audit events và khả năng ghi nhận.
- [Google Cloud — VPC Flow Logs](https://cloud.google.com/vpc/docs/using-flow-logs): data-plane flow metadata.
- [HashiCorp Terraform — Plan](https://developer.hashicorp.com/terraform/cli/commands/plan): review thay đổi hạ tầng dự kiến.
- [Open Policy Agent — Documentation](https://www.openpolicyagent.org/docs): định nghĩa rule kiểm tra hạ tầng và CI theo policy-as-code.
- [OWASP Infrastructure as Code Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Infrastructure_as_Code_Security_Cheat_Sheet.html): kiểm soát quyền và review cấu hình hạ tầng.
- [CIS Controls v8](https://www.cisecurity.org/controls/v8): asset/config/account management, secure configuration và audit controls.

**Ghi nhớ:** Phân quyền IAM đối với thay đổi cấu hình mạng cloud phải trả lời **ai có thể thay đổi điều gì, ở scope nào, bằng identity nào, trong bao lâu và dưới những guardrail nào**. Một role bị giới hạn theo resource vẫn có thể tạo rule nguy hiểm; một pipeline dùng IaC vẫn có thể bị lạm dụng nếu quyền deploy quá rộng; và một API mutation thành công **không chứng minh luồng mạng sau thay đổi là an toàn**. Hãy kết hợp **least privilege, SoD, JIT/MFA, IAM trust-chain review, org guardrails, policy-as-code, protected IaC workflow, audit logs, drift detection và kiểm thử cả ALLOW/DENY trên data plane** để giảm rủi ro lâu dài.
