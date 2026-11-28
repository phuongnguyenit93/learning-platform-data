# Lab bảo mật mạng: Tạo subnet public, private và management có kiểm soát

## 1. Mục tiêu dự án và sản phẩm cần bàn giao

Trong dự án thực hành này, người học thiết kế và triển khai một mạng ảo được phân thành **ba vùng có mục đích khác nhau**: **public** cho điểm vào được công bố có chủ đích, **private** cho ứng dụng/dữ liệu không được nhận kết nối Internet trực tiếp, và **management** cho hoạt động quản trị được xác thực, ghi log và giới hạn nguồn. Từ đó ta kiểm tra được các mục tiêu cơ bản của bảo mật mạng: giảm bề mặt tấn công, hạn chế chuyển ngang (*lateral movement*), bảo vệ kênh quản trị và giữ khả năng điều tra.

Đây là một bài thực hành trong chương **Dự án thực hành bảo mật mạng** thuộc module **SECURITY_NETWORK_SECURITY**, kết hợp phân đoạn, firewall/security group, VPN/ZTNA, DNS, network telemetry, mô hình hóa mối đe dọa và xác minh các đường mạng ALLOW/DENY.

**Sản phẩm cuối bài** gồm sơ đồ mạng, bảng cấp phát CIDR, các route table, policy theo nguồn–đích–port–identity, mã Infrastructure as Code (IaC) minh họa, hồ sơ kiểm thử, bằng chứng telemetry, checklist cleanup và bản tóm tắt quyết định kiến trúc.

### 1.1. Điều gì được coi là hoàn thành?

Một lab đạt yêu cầu khi có thể chứng minh:

1. **Public subnet** có route ra Internet Gateway, nhưng **không mặc nhiên công bố mọi máy** bên trong.
2. **Private subnet** không chứa instance có public IP để nhận trực tiếp kết nối Internet; egress nếu cần đi qua cơ chế được kiểm soát.
3. **Management subnet** không có public ingress mặc định, chỉ có đường quản trị cụ thể được phê duyệt và có audit.
4. Các dịch vụ chỉ được nói chuyện qua **những luồng tối thiểu cần thiết**, không chỉ dựa vào nhãn subnet.
5. IPv4/IPv6, DNS, NAT, route nội bộ và nguồn quản trị được đánh giá để không tạo đường vòng.
6. Các **negative tests** cho Internet→private, public→management và private→management thất bại tại đúng điểm thực thi, trong khi các đường **positive** hợp lệ vẫn hoạt động.
7. Mỗi kết quả có **evidence từ đúng điểm đo**: cấu hình, route, security group/firewall, flow logs, kiểm thử từ nguồn thực sự và thời gian UTC.

### 1.2. Điều kiện tiên quyết

- Hiểu IPv4, CIDR, subnet mask, default route, DNS, NAT và TCP/UDP.
- Có một **sandbox cloud account/project** hoặc môi trường mô phỏng riêng được phê duyệt; không sử dụng mạng doanh nghiệp sản xuất để chạy thử tùy tiện.
- Có quyền tạo và xóa **chỉ tài nguyên lab được giao**, quota/budget giới hạn, người chịu trách nhiệm trả phí và quy trình dọn dẹp.
- Nếu dùng Terraform, đã có **CLI và provider được đội vận hành phê duyệt**, tài khoản đăng nhập tạm thời/least privilege.
- Có một máy/client kiểm thử được phê duyệt hoặc cơ chế reachability/flow analysis của cloud; **không cần mở SSH/RDP ra toàn Internet**.

> **An toàn và chi phí:** `10.42.0.0/16` là dải RFC 1918 minh họa; các IP `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24` là dải dành cho tài liệu. Mọi lệnh triển khai thực tế có thể phát sinh chi phí cloud (đặc biệt NAT Gateway, IPv4 public address, logs và endpoints). Chỉ chạy `apply` hoặc kiểm thử lưu lượng trên **sandbox có quyền, budget và phương án rollback**. Không sử dụng network scanning/flooding hoặc thay route/firewall của production.

## 2. Mô hình mạng đề xuất

### 2.1. Ba vùng, ba nhiệm vụ

| Vùng | Mục tiêu | Thành phần điển hình | Quy tắc thiết kế |
|---|---|---|---|
| **Public** | Điểm vào được phép công bố với Internet | Internet-facing load balancer, reverse proxy/WAF gateway, NAT Gateway trong một số cloud | Chỉ công bố đúng listener/port; không đặt database hoặc công cụ quản trị ở đây |
| **Private** | Chạy logic nghiệp vụ và lưu trữ không cần public ingress | Application servers, worker nodes, databases, internal APIs | Không public IP, chỉ inbound từ nguồn/identity được phê duyệt, egress giới hạn |
| **Management** | Truy cập vận hành, giám sát, configuration/backup theo thẩm quyền | Managed session endpoints, private management agents, monitoring collectors, jump service khi thực sự cần | Không tự mở SSH/RDP public; dùng SSO/MFA/ZTNA/VPN/private endpoints, PAM và audit |

Trong một số hệ thống thực tế, nên tách **database/data subnet** khỏi private application subnet hoặc tách management thành **nhiều vùng**. Bài dùng ba vùng để minh họa; đó là **đường cơ sở học tập**, không phải tuyên bố kiến trúc ba subnet luôn đủ cho mọi enterprise.

### 2.2. Sơ đồ logic

~~~mermaid
flowchart TB
    INTERNET["Internet / Approved external users"]
    IGW["Internet Gateway / Edge routing"]
    PUB["PUBLIC 10.42.10.0/24\nInternet-facing load balancer"]
    NAT["NAT Gateway\nOutbound IPv4 only"]
    PRIV["PRIVATE 10.42.20.0/24\nApplication / data workloads"]
    MGMT["MANAGEMENT 10.42.30.0/24\nPrivate admin/telemetry"]
    AUTH["Identity-aware admin access\nVPN / ZTNA / managed sessions"]
    LOG["Central audit, flow logs and monitoring"]
    INTERNET --> IGW
    IGW --> PUB
    PUB -->|"Approved app traffic only"| PRIV
    PRIV -->|"Approved outbound updates only"| NAT
    NAT --> IGW
    AUTH -->|"Private, authenticated path"| MGMT
    MGMT -->|"Approved management ports/identities"| PRIV
    PUB -. "Flow and change logs" .-> LOG
    PRIV -. "Flow and application logs" .-> LOG
    MGMT -. "Access audit" .-> LOG
~~~

**Sơ đồ biểu diễn ý định bảo mật, không phải routing rule tự động.** Đặc biệt, trong nhiều VPC (ví dụ AWS), tất cả subnet cùng VPC có **đường local nội bộ**, nên **chỉ tạo ba route tables không hề tạo default deny giữa ba vùng**. Muốn ngăn public subnet truy cập management subnet, phải áp **security groups/firewall/NACL hoặc workload policy** tại đúng điểm thực thi.

### 2.3. Public subnet không có nghĩa mọi host đều public

Trong AWS, một subnet thường được gọi là **public** khi route table liên kết có đường `0.0.0.0/0` tới Internet Gateway. Nhưng một EC2 instance **chỉ có private IP** và security group không cho phép inbound từ Internet **không tự được truy cập từ Internet**. Internet-facing load balancer cũng có address/listener/security-group policy riêng.

Tương tự, một private subnet có NAT để **khởi tạo kết nối outbound IPv4** không đồng nghĩa Internet có thể tự mở phiên inbound vào private instances qua NAT. Tuy nhiên NAT **không phải firewall least privilege**: ứng dụng có thể đi ra destination ngoài ý định nếu egress policies không giới hạn.

### 2.4. Management không nên được định nghĩa bằng tên subnet

Một subnet tên `management` nhưng có route Internet Gateway, VM public IP và port 22 mở `0.0.0.0/0` **không thể được coi là vùng quản trị an toàn**. Ngược lại, một subnet chỉ có **private routing và audited access** thông qua approved VPN/ZTNA hoặc managed session infrastructure mới thực hiện đúng ý định management plane.

## 3. Kế hoạch địa chỉ CIDR

### 3.1. Chọn một VPC CIDR đủ dư địa

Ta chọn mạng lab:

~~~text
VPC:            10.42.0.0/16
Public A:       10.42.10.0/24
Private A:      10.42.20.0/24
Management A:   10.42.30.0/24

Reserved growth:
Public B:       10.42.11.0/24
Private B:      10.42.21.0/24
Management B:   10.42.31.0/24
~~~

Các giá trị A/B là tên **nhóm ví dụ cho hai Availability Zones**, không phải các địa chỉ public của Internet. Các subnet không chồng nhau và đều nằm trong `10.42.0.0/16`.

### 3.2. Tính dung lượng subnet

Với IPv4 prefix `/p`, số địa chỉ lý thuyết:

\[
N = 2^{32-p}.
\]

Ví dụ `/24` có \(2^8=256\) IPv4 addresses. **Không được suy luôn có 254 addresses cấp được trong mọi cloud**: AWS giữ lại **5 địa chỉ IPv4 trong mỗi subnet** cho các chức năng nền, nên `/24` thường có **251 địa chỉ dùng cho ENI/host allocation** theo quy tắc đó. Các nhà cung cấp khác có tập địa chỉ dự trữ riêng; hãy dùng thông số của cloud thực tế.

| Prefix | Tổng số IPv4 addresses | Mục đích xem xét |
|---|---:|---|
| `/16` | 65.536 | VPC/address space tổng thể trong ví dụ |
| `/20` | 4.096 | Workload segment có nhiều IP/scale |
| `/24` | 256 | Lab subnet dễ quan sát, có khoảng trống |
| `/26` | 64 | Subnet nhỏ, cần kiểm tra reservations/quota |
| `/28` | 16 | Rất ít IP usable; cần chú ý endpoints/ENIs |

**Không chia CIDR chỉ theo số VM ngày đầu**. Load balancer nodes, NAT, interface endpoints, Kubernetes Pod networking, autoscaling và failover có thể cần thêm IP nhanh chóng. Cần xem **pod IP allocation model, ENI limits, reserve growth và secondary ranges**.

### 3.3. Nguyên tắc tránh chồng CIDR

1. Kiểm tra địa chỉ với **on-prem, VPN partners, các VPC/VNet khác và future peering/TGW**.
2. Tránh dùng dải phổ biến trong môi trường có nhiều VPN client nếu dễ trùng.
3. Đặt IPAM owner và bản ghi `CIDR → region/AZ → trust zone → lifecycle`.
4. Tách subnet route requirements theo khả năng cần attach firewall/route services.
5. Xem IPv6 plan ngay từ đầu; không giả định không có IPv6 nếu cloud có thể tự cấp.

Chồng CIDR không chỉ gây khó routing; nó có thể làm **NAT mappings, firewall policy, audit attribution và incident response** trở nên mơ hồ.

## 4. Trust boundary và threat model trước khi tạo tài nguyên

### 4.1. Tài sản cần bảo vệ

| Tài sản | Điểm nhạy cảm | Nguy cơ chính | Kiểm soát dự kiến |
|---|---|---|---|
| Public application entry | TLS private key/edge config, endpoint availability | Internet scanning, HTTP abuse, DDoS, origin bypass | Chỉ 443, WAF/rate limit khi cần, strict TLS, upstream protection |
| Private application server | Code, environment, API tokens, dữ liệu trong RAM | Lateral movement, compromised public tier, unapproved egress | SG inbound từ edge, workload identity, patch, secret control |
| Private database | Business data, credentials, backup | Unauthorized reads, credential theft, network path bypass | App-only source identity, no public IP, database auth/TLS, audit |
| Management endpoint | Privileged sessions, access logs | Password brute force, stolen admin token, lateral movement | Private-only ingress, MFA/PAM, JIT access, centralized audit |
| DNS and private resolver | Domain mappings, query telemetry | Poisoning, resolver bypass, outage | Controlled resolver paths, DNSSEC when applicable, split-horizon review |
| Routing/firewall control plane | Routes, SG/NACL, infrastructure APIs | Misconfiguration, privilege misuse, IaC drift | Least-privilege IAM, approval, IaC policy, CloudTrail/control-plane audit |
| Flow logs and evidence | Network activity, security findings | Log deletion/tampering, sensitive metadata leakage | Restricted log repository, retention, encryption, no-data alerts |

### 4.2. Đường tấn công cần xét

~~~mermaid
flowchart TD
    I["Internet attacker"] --> E["Public edge exposed service"]
    E -. "RCE / stolen service identity" .-> APP["Private application workload"]
    APP -. "Lateral attempt" .-> DB["Database / another service"]
    APP -. "Credential misuse" .-> ADMIN["Management API"]
    U["Compromised user VPN session"] -. "Excessive network reachability" .-> ADMIN
    X["Compromised cloud IAM role"] -. "Route / SG changes" .-> CP["Control plane"]
    CP -. "May invalidate network assumptions" .-> E
    CP -. "May invalidate network assumptions" .-> APP
~~~

Kiến trúc ba subnet phải trả lời được: **nếu public edge bị chiếm quyền, app/private và management có còn bị hạn chế không?** Không được đặt mọi server trong cùng security group `allow all within VPC` rồi gọi là microsegmentation.

### 4.3. Mục tiêu ALLOW/DENY trước khi triển khai

| Nguồn | Đích | Giao thức/port mẫu | Kỳ vọng | Lý do |
|---|---|---|---|---|
| Internet | Public load balancer | TCP/443 | ALLOW | Điểm nhận HTTPS có chủ đích |
| Public load balancer SG | Private app SG | TCP/8443 | ALLOW | Chỉ frontend gọi backend ứng dụng |
| Private app identity | Private DB | TCP/5432 | ALLOW có điều kiện | Chỉ ứng dụng được cấp quyền truy cập DB |
| Authorized admin session | App management endpoint | TCP/22 hoặc management API | ALLOW có điều kiện | Quản trị theo identity, chỉ private path |
| Private app | Approved update services | TCP/443 | ALLOW có kiểm soát | Cập nhật/phụ thuộc được phê duyệt |
| Internet | Private app / DB | Mọi cổng | DENY | Không public inbound |
| Internet | Management subnet | SSH/RDP/management APIs | DENY | Không công bố quản trị |
| Public edge | Management subnet | TCP/22, 3389 | DENY | Ngăn public tier pivot sang quản trị |
| Private app | Management subnet | Mọi cổng không khai báo | DENY | Ngăn lateral movement |
| Unapproved workload | Database | TCP/5432 | DENY | Không cấp quyền ngang vùng |
| Public tier | Arbitrary private workloads | Mọi cổng ngoài TCP/8443 | DENY | Thu hẹp blast radius |
| Management host | Internet | Mọi cổng nếu không có yêu cầu | DENY | Giảm exfil / quản trị ngoài policy |

Đây là **ma trận ý định**. Trong bản IaC tối thiểu bên dưới chưa tạo database, application load balancer hoặc managed admin connection; những hàng ALLOW cho workload tương ứng là **bài kiểm thử sau khi triển khai thêm thành phần được cấp phép**, không phải lời khẳng định tài nguyên đã tồn tại. Luồng cập nhật qua NAT cần có **egress filtering thực sự** nếu muốn chặn mọi đích không nằm trong allowlist.

### 4.4. Khác biệt giữa segmentation và authorization

Security group có thể cho app server nói chuyện với database trên TCP/5432, nhưng **không kiểm tra người dùng có quyền đọc bản ghi nào**. TLS/mTLS chứng minh kênh và danh tính peer trong điều kiện đúng, nhưng **không thay application authorization**. Bài lab kiểm tra *đường mạng* trước; sau đó nên bổ sung database roles, service accounts, secret rotation, least privilege và request-level controls.

## 5. Route tables: khác biệt giữa có đường đi và được phép truy cập

### 5.1. Ba route tables trong thiết kế một Availability Zone

| Route table | Destination | Target | Ý nghĩa |
|---|---|---|---|
| `rt-public-a` | `10.42.0.0/16` | `local` | Kết nối nội VPC theo routing |
| `rt-public-a` | `0.0.0.0/0` | Internet Gateway (`igw-lab`) | Đường IPv4 ra Internet cho tài nguyên có điều kiện |
| `rt-private-a` | `10.42.0.0/16` | `local` | Kết nối nội VPC theo routing |
| `rt-private-a` | `0.0.0.0/0` | NAT Gateway (`nat-a`) | Initiated outbound IPv4 qua NAT theo policy |
| `rt-management-a` | `10.42.0.0/16` | `local` | Chỉ routing nội VPC trong bản lab tối thiểu |

Với quản trị qua VPN/ZTNA/tunnel/managed sessions, **phải bổ sung endpoint/route/identity được thiết kế rõ**; `rt-management-a` chỉ có route `local` **chưa đủ để một admin từ on-prem truy cập được**. Mô hình hiện tại cố ý để management **không có default Internet route**; khi cần update agent/OS, ưu tiên VPC endpoints/private package mirrors hoặc egress proxy kiểm soát.

### 5.2. Internet Gateway không tương đương một rule ALLOW

Internet Gateway cung cấp đường giao tiếp giữa VPC và Internet. Một instance có route tới IGW **còn cần public IPv4/IPv6 address theo kiểu kết nối, gateway/security policies và network path hợp lệ**. Security group/NACL có thể chặn ngay cả khi route tồn tại.

Ngược lại, **VPC local route** cho phép tìm đường tới subnet khác ngay trong VPC; không có Internet Gateway cũng **không bảo đảm traffic ngang VPC đã bị chặn**.

### 5.3. NAT Gateway cho outbound, không là kiểm soát danh tính

Với NAT Gateway public của AWS ở public subnet, private workload dùng route `0.0.0.0/0 → NAT Gateway` để khởi tạo **outbound IPv4** ra Internet, với IGW phía public. NAT không cho một client Internet tùy ý tự mở kết nối mới tới private VM qua IP của NAT. Tuy vậy:

- NAT **không thay SG/firewall egress allowlist**.
- NAT có thể trở thành chokepoint/cost/failure domain; dùng nhiều AZ cho production khi phù hợp.
- Không xem NAT như TLS inspection: nó không biết HTTP URL, user identity hoặc ciphertext payload.
- IPv6 có model khác: cân nhắc **egress-only Internet Gateway**, firewall hoặc IPv6 NAT/translation theo nhu cầu thật; không dùng route IPv4 NAT để suy IPv6 cũng bị giới hạn.
- Traffic tới cloud private services có thể qua **VPC endpoints** mà không cần NAT; phải quản lý endpoint policy và route/security rules.

### 5.4. Tại sao route table không là policy chặn lateral?

Trên AWS, mỗi VPC route table có một route `local` nội VPC (thông thường không xóa tùy ý như một ACL); mặc định các subnet trong cùng VPC có thể tìm đường tới nhau. **Đường mạng tồn tại không có nghĩa SG sẽ cho phép traffic**, nhưng việc gán management route table "chỉ local" vẫn cho phép tìm đường đến private/public subnet.

Nếu yêu cầu bắt buộc chặn **mọi kết nối giữa một số trust zones**, áp các controls phù hợp:

1. **Security groups theo workload identity**: stateful firewall cho ENIs/resources được hỗ trợ, tốt cho allowlist nguồn/đích.
2. **Network ACLs**: stateless ở subnet boundary, cần xem inbound và outbound kể cả ephemeral return ports; dùng như lớp bổ trợ khi cần.
3. **Central inspection/firewall**: đưa flows qua appliance/managed firewall theo routing có kiểm chứng, tránh asymmetric path.
4. **NetworkPolicy / service mesh AuthorizationPolicy** nếu workload Kubernetes, lưu ý semantics thực thi của CNI/mesh.
5. **Tách VPC/VNet** đối với isolation boundary mạnh hơn, kết hợp route propagation/firewall và IAM.

### 5.5. Route changes có thể làm mất kênh quản trị

Không sửa default route trên máy điều khiển từ xa hoặc trên production firewall để thử nghiệm. Một thay đổi route có thể làm rớt **management session, DNS, telemetry hoặc access path**. Luôn có **out-of-band recovery**, approval, configuration snapshot, rollback owner và success/abort criteria trước cutover.

## 6. Chính sách firewall/security group theo zero trust

### 6.1. Phân biệt những lớp chính

| Lớp | Phạm vi | Stateful? | Khi nào dùng |
|---|---|---|---|
| **Security group** trong AWS | ENI/resource được hỗ trợ | Có | Chính sách ingress/egress theo workload; source SG khi phù hợp |
| **Network ACL** trong AWS | Subnet boundary | Không | Lớp kiểm soát bổ trợ theo IPv4/IPv6, ports, hướng |
| **Host firewall** | Trên OS/VM | Tùy implementation | Defense-in-depth, giới hạn local services |
| **Managed network firewall** | Đường mạng được route qua PEP | Phụ thuộc policy/engine | Egress/domain/IPS hoặc inspection tập trung |
| **Application authorization** | User/service/action/resource | Không phải packet filter | Kiểm tra quyền nghiệp vụ sau kết nối |

Một rule của security group cho phép TCP/443 từ `0.0.0.0/0` **không có nghĩa** endpoint nhận Internet nếu subnet không có đường inbound/public address; ngược lại việc instance private có NAT không tạo inbound public listener.

### 6.2. Không tự động gán default allow giữa ba vùng

**Nguyên tắc cần đạt** cho lab:

- Public frontend chỉ nhận TCP/443 từ nguồn đã được phép (có thể là Internet trong lab public demo).
- Backend app chỉ nhận TCP/8443 từ **security group của frontend**.
- Database (nếu tạo) chỉ nhận DB port từ **SG app**, không từ cả CIDR private.
- Management zone không nhận public SSH/RDP; sử dụng quản trị có danh tính và audit.
- Egress app không được tự mặc định `allow all` nếu tổ chức yêu cầu kiểm soát đích; phải thiết kế firewall/proxy/endpoint controls tương ứng.

**Default deny** phải được xem theo *thực tế rule set*, không chỉ tên tài nguyên. Trong AWS, SG mới có mặc định quản lý egress khác tùy cách tạo/IaC provider; cần **kiểm tra rules sau apply**, không dựa vào giả định.

### 6.3. Quy tắc chặt cho SSH/RDP

Không dùng:

~~~text
Management ingress:
  TCP/22  source 0.0.0.0/0
  TCP/3389 source ::/0
~~~

Thay bằng **managed session agent qua private endpoints**, VPN/ZTNA private path có MFA, JIT access và approvals. Nếu buộc dùng bastion, đặt access source hẹp, logging, hardened host, session recording, patched OS và tách path để bastion không trở thành single point of lateral movement.

### 6.4. IPv6 không phải bản sao tự động của IPv4

Một security group rule `0.0.0.0/0` chỉ áp cho IPv4, không tự mở hoặc chặn `::/0`. Khi được cấp IPv6 và có route `::/0 → IGW`, một máy có IPv6 globally routable có thể nhận đường inbound mà **không cần public IPv4/NAT**, tùy firewall và route. Thiết kế phải có **IPv6 policy parity**, cả client/flow/logging và identity attribution.

## 7. Bản thực hành AWS Terraform: phạm vi và cấu trúc

Ví dụ dưới đây dùng **AWS VPC** để minh họa cụ thể việc tạo ba subnet. Đây là **mã hướng dẫn**, không phải một stack đã được chạy và kiểm chứng với tài khoản, provider hoặc version hiện tại của người học. Khi chuyển sang Azure VNet/GCP VPC/on-prem VLAN, **khái niệm tương đồng nhưng semantics routing, public/private addressing, managed NAT, firewall và subnet scope khác nhau**; không sao chép trực tiếp resource names hoặc cấu hình.

### 7.1. Lab tạo và không tạo gì?

**Tạo nếu áp dụng có phê duyệt:**

- Một VPC `10.42.0.0/16` trong một region.
- Ba subnets `/24` ở cùng một Availability Zone; **management subnet không có public IP**.
- Một Internet Gateway, một NAT Gateway public, một Elastic IP cho NAT.
- Ba route tables và associations tương ứng.
- Ba security groups `edge`, `app`, `management`, với rules minh họa tối thiểu.

**Không tạo:**

- EC2 instance, database, application load balancer hay Kubernetes cluster.
- SSH/RDP public listener; không tạo access keys hay public server.
- VPN/ZTNA, SSM private endpoints, flow logs hoặc centralized firewall; phần này sẽ có **thiết kế và kiểm thử tiếp theo**, cần triển khai riêng khi có quyền.

Do không tạo instances/ALB, **không thể thực hiện end-to-end TCP test chỉ bằng stack này**. Người học cần thêm *test workloads do lab owner cấp phép* để kiểm tra luồng ứng dụng, hoặc dùng **cloud-native reachability/config analysis**; không tuyên bố PASS cho các luồng chưa có endpoint.

### 7.2. Chi phí trước khi apply

**NAT Gateway, Elastic IP/public IPv4, CloudWatch logs, interface endpoints hoặc traffic egress** có thể bị tính phí ngay cả khi lab không có VM. Giá tùy region, thời điểm và hợp đồng; phải kiểm tra pricing chính thức từ tài khoản trước khi tạo. Bản lab **một AZ** giúp minh họa với ít tài nguyên hơn, **không phải kiến trúc HA cho production**.

Nếu chỉ cần học CIDR/route tables và không cần kiểm tra outbound thực tế, có thể **bỏ NAT Gateway và private default route** trong bản lab đã được reviewer chỉnh sửa; lúc đó private subnet sẽ không có Internet default egress. Không dùng `terraform apply` chưa kiểm tra plan, cost và account identity.

### 7.3. Các giả định cấu hình

~~~text
Cloud:               AWS (illustrative, one AZ)
Region default:      ap-southeast-1 (change to approved sandbox region)
VPC CIDR:            10.42.0.0/16
Public CIDR:         10.42.10.0/24
Private CIDR:        10.42.20.0/24
Management CIDR:     10.42.30.0/24
IPv6:                Not assigned by this example
Auto public EC2 IP:  Disabled on public subnet by default
Public listener:     None; no ALB/VM created
NAT:                 One public NAT Gateway (billable)
Management routing:  Local VPC only, no Internet default route
~~~

`map_public_ip_on_launch=false` đối với public subnet là lựa chọn **cố ý**: subnet được phân loại public dựa vào route table; instance muốn public IPv4 phải được cấu hình riêng có review, không được tự nhận public address chỉ vì đặt trong subnet.

## 8. Terraform HCL — VPC, subnets và Internet Gateway

**Đoạn này chỉ là nội dung tài liệu**, không tạo file `main.tf` trong workspace hiện tại. Khi thực hành trên sandbox cá nhân được cấp quyền, có thể lưu nội dung vào một IaC project riêng do người quản lý lab tạo và kiểm tra. Không copy lệnh có credential vào tài liệu hoặc source control.

~~~hcl
terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

variable "region" {
  description = "Approved sandbox region."
  type        = string
  default     = "ap-southeast-1"
}

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  prefix = "netsec-lab-003"
  az     = data.aws_availability_zones.available.names[0]
  tags = {
    Project     = "network-security-lab"
    Lab         = "003"
    Environment = "sandbox"
    ManagedBy   = "terraform"
  }
}

resource "aws_vpc" "lab" {
  cidr_block           = "10.42.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = merge(local.tags, { Name = "${local.prefix}-vpc" })
}

resource "aws_subnet" "public_a" {
  vpc_id                  = aws_vpc.lab.id
  cidr_block              = "10.42.10.0/24"
  availability_zone       = local.az
  map_public_ip_on_launch = false
  tags                    = merge(local.tags, { Name = "${local.prefix}-public-a", Zone = "public" })
}

resource "aws_subnet" "private_a" {
  vpc_id                  = aws_vpc.lab.id
  cidr_block              = "10.42.20.0/24"
  availability_zone       = local.az
  map_public_ip_on_launch = false
  tags                    = merge(local.tags, { Name = "${local.prefix}-private-a", Zone = "private" })
}

resource "aws_subnet" "management_a" {
  vpc_id                  = aws_vpc.lab.id
  cidr_block              = "10.42.30.0/24"
  availability_zone       = local.az
  map_public_ip_on_launch = false
  tags                    = merge(local.tags, { Name = "${local.prefix}-management-a", Zone = "management" })
}

resource "aws_internet_gateway" "lab" {
  vpc_id = aws_vpc.lab.id
  tags   = merge(local.tags, { Name = "${local.prefix}-igw" })
}
~~~

Các provider/resource arguments tương ứng với **AWS Terraform provider 5.x** trong ví dụ. Nếu môi trường chạy provider khác, cần xem documentation tương ứng, lockfile/module versions và thử `terraform validate` trong sandbox. Không xem văn bản minh họa là bảo đảm tương thích mọi version năm 2026.

### 8.1. Vì sao DNS support được bật?

VPC DNS resolver và private hostnames giúp quản lý service discovery; **DNS được bật không tự tạo private DNS endpoints** và không tự hạn chế truy vấn ra DNS ngoài. Với private subnet có yêu cầu không egress Internet, cần thiết kế private hosted zone, DNS forwarding và endpoint strategy; DNS traffic/metadata vẫn phải được bảo vệ theo quyền.

### 8.2. Kiểm chứng CIDR sau plan

Trong plan, kiểm tra:

~~~text
VPC: 10.42.0.0/16
Subnet public_a: 10.42.10.0/24, AZ selected in sandbox region
Subnet private_a: 10.42.20.0/24, same AZ
Subnet management_a: 10.42.30.0/24, same AZ
All three: map_public_ip_on_launch = false
No overlapping subnets and no unexpected IPv6 assignments
~~~

Nếu region/account không có AZ khả dụng trong kết quả data source hoặc bị **organization SCP/quota** hạn chế, không bỏ quyền bảo mật để chạy cho được; dùng approved region/AZ do người sở hữu sandbox chỉ định.

## 9. Terraform HCL — NAT Gateway và các route tables

Tiếp nối những resources của phần trước trong cùng **một cấu hình lab**:

~~~hcl
# A public IPv4 allocation and NAT Gateway can incur charges.
resource "aws_eip" "nat_a" {
  domain = "vpc"
  tags   = merge(local.tags, { Name = "${local.prefix}-nat-eip" })
}

resource "aws_nat_gateway" "nat_a" {
  allocation_id = aws_eip.nat_a.id
  subnet_id     = aws_subnet.public_a.id
  depends_on    = [aws_internet_gateway.lab]
  tags          = merge(local.tags, { Name = "${local.prefix}-nat-a" })
}

resource "aws_route_table" "public_a" {
  vpc_id = aws_vpc.lab.id
  tags   = merge(local.tags, { Name = "${local.prefix}-rt-public" })
}

resource "aws_route" "public_default_ipv4" {
  route_table_id         = aws_route_table.public_a.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.lab.id
}

resource "aws_route_table_association" "public_a" {
  subnet_id      = aws_subnet.public_a.id
  route_table_id = aws_route_table.public_a.id
}

resource "aws_route_table" "private_a" {
  vpc_id = aws_vpc.lab.id
  tags   = merge(local.tags, { Name = "${local.prefix}-rt-private" })
}

resource "aws_route" "private_default_ipv4" {
  route_table_id         = aws_route_table.private_a.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.nat_a.id
}

resource "aws_route_table_association" "private_a" {
  subnet_id      = aws_subnet.private_a.id
  route_table_id = aws_route_table.private_a.id
}

resource "aws_route_table" "management_a" {
  vpc_id = aws_vpc.lab.id
  tags   = merge(local.tags, { Name = "${local.prefix}-rt-management" })
}

# Management: NO 0.0.0.0/0 or ::/0 route in this example.
# The VPC-local route is automatically present.
resource "aws_route_table_association" "management_a" {
  subnet_id      = aws_subnet.management_a.id
  route_table_id = aws_route_table.management_a.id
}
~~~

### 9.1. Tại sao phải associate route table?

Tạo `rt-private` nhưng không gắn vào private subnet khiến subnet **tiếp tục dùng main route table** của VPC. Nếu main route table sau này bị thay đổi vì service khác, traffic có thể đi đường không mong đợi. Đặt **explicit associations** và kiểm tra sau apply để không phụ thuộc implicit behavior.

### 9.2. Ý nghĩa đường `local` mà Terraform không liệt kê

AWS VPC tự có local route cho CIDR VPC; tạo `aws_route_table` không cần thêm `aws_route` trỏ `local` trong ví dụ. Người kiểm thử phải xem **effective route table trong control plane**, không chỉ đếm các `aws_route` khai báo trong HCL.

### 9.3. Nếu bỏ NAT vì không cần Internet egress?

Trong sandbox, có thể thiết kế phương án **không NAT**: không tạo EIP/NAT resource và không tạo `private_default_ipv4`. Lúc đó private subnet có route nội VPC, không có default route ra Internet. Bất kỳ instance trong private subnet muốn cập nhật qua public repositories **sẽ không có Internet egress theo thiết kế**; cần private mirrors/endpoints hay đường đã được phê duyệt.

Không áp patch tự phát lên một state đã tạo NAT mà không kiểm tra tác động đến hệ thống dùng chung. Trong ví dụ này tất cả tài nguyên là **dedicated lab**.

### 9.4. Không mặc định đường IPv6 theo IPv4

Không có `assign_generated_ipv6_cidr_block=true` trên VPC và không có IPv6 subnet assignment trong ví dụ. Khi mở IPv6 thật, cần thêm IPv6 CIDR/subnets, SG/NACL rules IPv6, route `::/0` theo đúng intended boundary, flow logs và DNS AAAA coverage. Đừng mô tả `NAT IPv4` là hàng rào chặn IPv6.

## 10. Terraform HCL — security groups cho edge, app và management

Đây là phần bổ sung vào cùng Terraform root module phía trên. Nó **khai báo chính sách chờ được gắn vào workloads trong bài thực hành tiếp theo**. Một security group **không bảo vệ tài nguyên nào nếu chưa được attach**. Ví dụ chưa tạo EC2/ALB, vì vậy không được coi tạo security group xong là luồng đã được chặn thực tế.

~~~hcl
resource "aws_security_group" "edge" {
  name        = "${local.prefix}-sg-edge"
  description = "Allow HTTPS from clients, app backend only on 8443."
  vpc_id      = aws_vpc.lab.id
  tags        = merge(local.tags, { Name = "${local.prefix}-sg-edge" })
}

resource "aws_security_group" "app" {
  name        = "${local.prefix}-sg-app"
  description = "Application: backend port only from edge security group."
  vpc_id      = aws_vpc.lab.id
  tags        = merge(local.tags, { Name = "${local.prefix}-sg-app" })
}

resource "aws_security_group" "management" {
  name        = "${local.prefix}-sg-management"
  description = "No ingress/egress permissions until approved admin path."
  vpc_id      = aws_vpc.lab.id
  tags        = merge(local.tags, { Name = "${local.prefix}-sg-management" })
}

# Public edge would accept HTTPS if a permitted listener were attached.
resource "aws_vpc_security_group_ingress_rule" "edge_https" {
  security_group_id = aws_security_group.edge.id
  description       = "Approved public HTTPS entry point."
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

# Edge can contact application ONLY on the intended backend port.
resource "aws_vpc_security_group_egress_rule" "edge_to_app" {
  security_group_id            = aws_security_group.edge.id
  description                  = "Backend HTTPS from edge to app."
  referenced_security_group_id = aws_security_group.app.id
  ip_protocol                  = "tcp"
  from_port                    = 8443
  to_port                      = 8443
}

# App only accepts backend traffic initiated from the edge SG.
resource "aws_vpc_security_group_ingress_rule" "app_from_edge" {
  security_group_id            = aws_security_group.app.id
  description                  = "Only approved edge workloads."
  referenced_security_group_id = aws_security_group.edge.id
  ip_protocol                  = "tcp"
  from_port                    = 8443
  to_port                      = 8443
}

# Optional lab baseline for outbound HTTPS via NAT; still NOT destination-allowlisted.
resource "aws_vpc_security_group_egress_rule" "app_outbound_https" {
  security_group_id = aws_security_group.app.id
  description       = "Outbound TCP 443; narrow with an egress PEP for production."
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

# No ingress or egress rules are declared for SG management.
# Inspect resulting effective rules in cloud before relying on zero access.

output "lab_vpc_id" {
  value = aws_vpc.lab.id
}

output "lab_subnet_ids" {
  value = {
    public     = aws_subnet.public_a.id
    private    = aws_subnet.private_a.id
    management = aws_subnet.management_a.id
  }
}

output "lab_security_group_ids" {
  value = {
    edge       = aws_security_group.edge.id
    app        = aws_security_group.app.id
    management = aws_security_group.management.id
  }
}
~~~

### 10.1. Security groups có trạng thái

Với AWS Security Group, phản hồi cho luồng đã được SG cho phép thường được chấp nhận nhờ **connection tracking/stateful behavior**, không cần tự thêm một inbound rule cho mọi ephemeral client port. Nếu chèn **stateless NACL** ở subnet boundary, cách xử lý return traffic khác và cần xét cả hai hướng; không áp cùng giả định của SG cho NACL.

### 10.2. Không trộn hai mô hình quản lý SG rules trong Terraform

Đoạn code sử dụng các resource riêng `aws_vpc_security_group_ingress_rule` và `aws_vpc_security_group_egress_rule`. Không thêm cùng các rules như nested `ingress`/`egress` blocks trong `aws_security_group` ở một IaC module khác vì có thể tạo **drift/xung đột ownership**. Nếu dùng module khác, phải thống nhất một chiến lược quản lý và kiểm tra **effective rules** sau apply.

### 10.3. Default SG và default egress không phải mô hình bảo mật

AWS tạo một **default security group** cùng VPC, vốn có default behavior riêng. Các SG tùy chỉnh trong bài không được phép kế thừa rule chỉ vì tên giống vùng; instance nào gắn **default SG hoặc nhiều SG khác** có thể được ALLOW nhiều hơn ý định. Về logic, **effective permissions của nhiều SG được cộng hợp**: một SG hạn chế không phủ quyết một SG khác cho phép.

Trong nhiều cách tạo SG trên AWS, tồn tại egress allow-all ban đầu; Terraform AWS provider có cơ chế quản lý mặc định egress khi tạo custom SG, nhưng **không coi điều đó là chứng cứ** nếu chưa kiểm tra. Với `sg-management`, sau apply phải xem effective ingress/egress; nếu còn default allow-all do phương pháp tạo/drift, phải **điều chỉnh policy có chủ đích** trước khi attach management instances.

### 10.4. Security group không là URL allowlist

Rule `app_outbound_https` cho `0.0.0.0/0:443` **vẫn cho phép app kết nối tới nhiều Internet destinations**, dù đi qua NAT. Nó giới hạn protocol/port, **không giới hạn domain, HTTP path hay chủ sở hữu đích**. Nếu một tổ chức bắt buộc egress allowlist, cần:

- SG tới một **egress proxy/firewall** được kiểm soát, hoặc approved endpoint CIDRs khi khả thi.
- Domain/URL-aware enforcement ở lớp phù hợp, xử lý DNS/DoH/QUIC policy.
- Không bỏ qua private link/VPC endpoint policies, IAM và workloads tự tạo alternative route.
- Logs từ firewall/proxy cộng với positive/negative tests để chứng minh egress control.

### 10.5. Management chưa hoạt động là trạng thái an toàn của blueprint

Trong stack cơ sở, management subnet và SG **có thể nhận tài nguyên về sau**, nhưng chưa có administrative ingress hay outbound permissions cụ thể. Điều đó là chủ ý để tránh mở rộng quyền trước khi xây access design. Để sử dụng quản trị an toàn, cần **bổ sung managed sessions qua private endpoints, VPN/ZTNA hoặc private peering** với routing/identity/SG/endpoint policies được thiết kế và test riêng.

## 11. Cách kiểm tra Terraform trước khi cấp quyền triển khai

**Lệnh bên dưới chạy trong một thư mục lab IaC được người quản lý cấp**, không phải trong repository bài học. `terraform init` có thể tải provider modules vào filesystem; `plan` có thể gọi cloud API, đọc state và ghi plan nếu được yêu cầu. **Không tự chạy `apply` trên tài khoản không xác nhận danh tính/budget**.

~~~bash
# 1. Xác nhận đúng cloud identity/region/account theo runbook nội bộ.
aws sts get-caller-identity

# 2. Tại root thư mục lab chỉ chứa cấu hình được phê duyệt:
terraform init
terraform fmt -check
terraform validate
terraform plan
~~~

Nếu dùng remote Terraform state, xem trước **workspace/backend, state lock, IAM và encryption**. Terraform state có thể chứa resource identifiers và **secrets** của nhiều tài nguyên; không upload state/plan chứa dữ liệu nhạy cảm lên chat hoặc ticket công khai.

### 11.1. Review plan như một thay đổi bảo mật

Kiểm tra:

| Hạng mục | Giá trị mong đợi |
|---|---|
| VPC CIDR | `10.42.0.0/16` |
| Subnet CIDRs | `10.42.10.0/24`, `10.42.20.0/24`, `10.42.30.0/24` |
| Public subnet route | `0.0.0.0/0` → Internet Gateway |
| Private subnet route | `0.0.0.0/0` → NAT Gateway |
| Management subnet route | Chỉ local trong blueprint |
| EC2 public IP auto-assign | False cả ba subnet |
| IPv6 | Chưa bật trong blueprint |
| Public SSH/RDP | **Không có rule** |
| Edge HTTPS | Có inbound TCP/443 IPv4 trong SG mẫu |
| App ingress | TCP/8443 chỉ từ SG edge |
| Management SG | Không khai báo ingress/egress; phải kiểm tra effective state |
| Data workloads/ALB | Chưa được tạo |
| Cost-bearing resources | NAT Gateway, public IPv4/EIP; ghi owner/cost approval |

### 11.2. Sau approval mới tạo resources

~~~bash
# KHÔNG chạy trừ khi đã có explicit approval và đúng sandbox.
terraform apply

# Chỉ đọc outputs/state của đúng Terraform workspace sau triển khai.
terraform output
terraform show
~~~

Đây là các lệnh minh họa cho người thực hành được cấp quyền. Chúng **không được chạy như một phần biên soạn bài**. Với production, cần workflow PR/review, signed artifacts khi áp dụng, policy-as-code scan, plan approval và state ownership.

### 11.3. Chặn lỗi "apply nhầm tài khoản"

1. Kiểm tra `aws sts get-caller-identity`, profile, role và account ID dự kiến.
2. Xác nhận region phù hợp, account quota/budget và workspace/backend.
3. Chỉ định resource tags/naming tránh trùng.
4. So `terraform plan` với **khung tài nguyên đã duyệt**; không chấp nhận xóa/thay các tài nguyên ngoài lab.
5. Có reviewer và rollback owner, đặc biệt vì NAT/IGW/routing có thể tạo kết nối mới.

Không lưu access key tĩnh trực tiếp vào HCL. Ưu tiên IAM roles/SSO sessions và credentials ngắn hạn theo chính sách.

## 12. Xem cấu hình AWS thực tế bằng thao tác chỉ đọc

Trong sandbox được phép và sau khi có tài nguyên, **không kết luận từ HCL mà không đối chiếu control plane**. Các lệnh ví dụ dưới đây chỉ đọc API, vẫn tạo audit/API activity và có thể chịu rate limits; không dùng để dò tìm tài khoản không thuộc quyền.

~~~bash
# Thay các ID bằng outputs từ Terraform của đúng sandbox.
# Các lệnh không mở cổng, không thay route hoặc security group.
aws ec2 describe-vpcs --vpc-ids vpc-EXAMPLE

aws ec2 describe-subnets \
  --filters Name=vpc-id,Values=vpc-EXAMPLE

aws ec2 describe-route-tables \
  --filters Name=vpc-id,Values=vpc-EXAMPLE

aws ec2 describe-security-groups \
  --filters Name=vpc-id,Values=vpc-EXAMPLE

aws ec2 describe-nat-gateways \
  --filter Name=vpc-id,Values=vpc-EXAMPLE
~~~

Chuỗi như `vpc-EXAMPLE` là **placeholder**, không phải resource ID hợp lệ. Điền ID từ **authorized outputs** rồi so:

- Subnet `SubnetId`, `VpcId`, `CidrBlock`, `AvailabilityZone`, `MapPublicIpOnLaunch`.
- Route tables `Routes`, `Associations`, route `local` và target type (`igw-...`, `nat-...`).
- Security group `IpPermissions`, `IpPermissionsEgress`, source SG references, IPv4/IPv6 CIDRs.
- NAT `State`, public subnet association và các public IP allocations.

### 12.1. Đừng nhầm subnet route table với bảng chính

Nếu một subnet không có explicit association, nó **dùng main route table**. Trong bài, mỗi subnet phải gắn route table riêng như thiết kế. Lưu lại mapping:

~~~text
subnet-public-a      -> rt-public-a
subnet-private-a     -> rt-private-a
subnet-management-a  -> rt-management-a
~~~

Việc gắn đúng route table là **bằng chứng cấu hình**, chưa là bằng chứng traffic thực tế. Để chứng minh security outcome cần reachability analysis hoặc kiểm thử ở endpoints khi chúng được triển khai.

### 12.2. Các trường cần quan sát khi có drift

Một reviewer nên lưu:

~~~yaml
# Evidence template, chưa thực hiện.
assessment_id: NETLAB-003
time_utc: pending
account_id_reference: approved-redacted-identifier
region: pending
vpc_id: pending
route_associations:
  public: pending
  private: pending
  management: pending
default_routes:
  public: pending
  private: pending
  management: pending
effective_security_groups:
  edge: pending
  app: pending
  management: pending
unexpected_public_ip_associations: pending
reviewer: pending
result: INCONCLUSIVE_UNTIL_VERIFIED
~~~

Không đưa account ID, public IP của hệ thống thật hoặc raw cloud credentials vào bài tập chung. Evidence thực cần lưu trong restricted repository.

## 13. Thiết kế đường quản trị: VPN/ZTNA hay managed sessions?

### 13.1. Điều kiện chọn giải pháp

Ta đã có management subnet **không public route**. Bây giờ phải chọn một đường **quản trị có xác thực**:

| Phương án | Điểm mạnh | Điều kiện phải kiểm |
|---|---|---|
| **Managed session agent qua private endpoints** | Không cần public SSH port hoặc inbound user-to-VM | Agent/OS hỗ trợ, IAM, session logs, private endpoint dependencies và endpoint SG |
| **VPN / ZTNA vào private network** | Quản trị theo identity và private routes, có thể dùng nhiều tools | MFA/device posture, least privilege, route/DNS, ACL/SG và monitoring |
| **Private bastion / jump host** | Phù hợp legacy SSH/RDP tools | Hardened bastion, approved source, PAM/JIT, session recording, patched OS |
| **Out-of-band console** | Recovery khi network route/agent lỗi | Authorized emergency access, audit, dual control và break-glass policy |

Trong AWS, một managed session service điển hình là **Systems Manager Session Manager** với agent, IAM role và private connectivity thích hợp. Với subnet **không có Internet default route**, thường cần VPC interface endpoints cho các dịch vụ liên quan theo region/agent/version (như `ssm`, `ssmmessages` và trong một số bối cảnh `ec2messages`), cùng đúng **private DNS, endpoint security group, IAM permissions, time sync và audit/logging**. Không giả định chỉ bật role là session thành công.

### 13.2. Mô hình quản trị không cần public SSH

~~~mermaid
flowchart LR
    ADMIN["Approved admin identity"]
    IAM["SSO / MFA / role policy"]
    CP["Managed session control plane"]
    VEP["Private interface endpoints"]
    AGENT["Managed agent in management/private subnet"]
    TARGET["Authorized target / service"]
    LOG["Central session and audit logs"]
    ADMIN --> IAM
    IAM --> CP
    CP --> VEP
    VEP --> AGENT
    AGENT -->|"Scoped action / identity"| TARGET
    CP -. "Session creation / access logs" .-> LOG
    AGENT -. "Activity telemetry where configured" .-> LOG
~~~

Sơ đồ là logic. Với Systems Manager, luồng kết nối thực có **agent chủ động kết nối service endpoints**, không phải console tự mở một inbound TCP/22 tới private VM. Session recording/command audit coverage thay đổi theo loại session, nền tảng và cấu hình; phải kiểm chứng **loại dữ liệu nào được ghi**, không mặc định mọi port-forwarded session đều có nội dung được ghi đầy đủ.

### 13.3. Những điều phải chặn

- Internet tới management TCP/22/3389/HTTPS admin: **DENY**.
- Public edge workload tới management SG: **DENY**, trừ dependency được thiết kế riêng.
- User VPN/ZTNA không có role tới protected management: **DENY**.
- Session token/credential bị revoke vẫn giữ access vượt policy: **FAIL**.
- Management instance tùy ý truy cập mọi private service hoặc Internet: **DENY** nếu không có use case.
- Privileged cloud API không MFA/approval/audit: không đạt policy.

### 13.4. Break-glass không phải cửa hậu vĩnh viễn

Break-glass account/console cần có **owner, thời hạn, strong auth, restricted scope, sealed credential procedure và post-use review**. Nếu đường khôi phục dùng public SSH mở `0.0.0.0/0` "cho tiện", nó tạo permanent attack surface trái với mục tiêu của lab.

## 14. DNS và private endpoints

### 14.1. Ba loại DNS flows

1. **Public DNS resolution:** user Internet tìm IP của public application hostname.
2. **Private service discovery:** app/management giải private hostnames trong VPC/private zone.
3. **Management service endpoint discovery:** agent tìm FQDN của service quản trị và đi qua approved private endpoints.

Cần test DNS theo đúng **client/zone/resolver/network path**. Một hostname có thể trả A/AAAA khác nhau trong split-horizon DNS; không vì cùng tên mà suy cùng route hoặc cùng TLS termination.

### 14.2. DNS không bảo đảm egress policy

Cho phép DNS resolver trong VPC không tự giới hạn app đến approved external domains. Ngược lại chặn UDP/53 **không đủ** kiểm soát DoH/DoT hoặc client đã có IP cache. Thiết kế egress nên phối hợp:

- Host/browser/device DNS configuration và managed resolver policy.
- Route/NAT, proxy/firewall và SG/CNI policy.
- DNS query logs theo quyền, bảo vệ thông tin cá nhân.
- App dependency inventory và tests khi DNS resolver unavailable.

### 14.3. Private cloud service access

Khi management subnet cần truy cập object storage, artifact repository, managed session hoặc secret service, **VPC gateway/interface endpoints** có thể giảm nhu cầu default Internet route. Tuy nhiên:

- **Gateway endpoints** và **interface endpoints** có semantics khác nhau về route tables, DNS, security groups và endpoint policies.
- Interface endpoints tạo ENIs/SG dependencies và có thể phát sinh chi phí.
- Endpoint policy, IAM, resource policy, DNS và TLS certificate validation **đều cần đúng**, không phải endpoint tồn tại là an toàn.
- Một số API hoặc third-party services không hỗ trợ private endpoint tại region/tenant; cần kiểm tra alternatives, không tự mở Internet egress.

### 14.4. DNS/endpoint test matrix

| Test | Kỳ vọng |
|---|---|
| Private workload resolve private application name | Đúng private target, không bị public DNS leakage |
| Management agent resolve private service endpoint | Đúng endpoint/DNS policy trong sandbox |
| Unapproved workload access management endpoint SG | DENY |
| Interface endpoint reachability from authorized agent | ALLOW với TLS/identity correct |
| DNS resolution absent/incorrect | Không tự fallback ra unapproved public Internet |
| Cloud endpoint IAM role without permission | DENY dù TCP/TLS kết nối được |

## 15. Một hay nhiều Availability Zones?

### 15.1. Vì sao blueprint dùng một AZ?

Một AZ đủ để mô tả CIDR, route table và SG trong lab, nhưng **không chịu lỗi vùng sẵn sàng (AZ outage)**. NAT Gateway trong một AZ cũng là dependency cho private egress; nếu AZ đó hoặc NAT lỗi, app ở AZ khác dùng cross-AZ NAT có thể mất kết nối hoặc tăng chi phí.

### 15.2. Mở rộng thiết kế production

~~~text
VPC 10.42.0.0/16

AZ A                        AZ B
Public:      10.42.10/24    Public:      10.42.11/24
Private:     10.42.20/24    Private:     10.42.21/24
Management:  10.42.30/24    Management:  10.42.31/24

IGW shared at VPC level
NAT-A in public AZ A; NAT-B in public AZ B
Private-A route 0/0 -> NAT-A
Private-B route 0/0 -> NAT-B
Management-A/B: local/private endpoints/approved connectivity only
~~~

Đây là **pattern xem xét**, không phải bảo đảm HA tự động. Application còn cần multi-AZ deployment, health checks, DB replication, IAM availability, route failover, DNS behavior và DR testing.

### 15.3. Các lỗi khi mở rộng

- Quên route association của subnet mới, rơi vào VPC main route table.
- Private subnet AZ B vẫn đi qua NAT AZ A, tạo single-AZ egress dependency.
- Quota ENI/IP cạn khi autoscaling, NAT/endpoint thêm địa chỉ.
- SG của workload B không theo đúng source identity hoặc IPv6 policy.
- Monitoring chỉ kiểm một AZ/route nên bỏ sót lỗi certificate/flow ở AZ còn lại.
- Flow logs không đủ để phân biệt source subnet/AZ, làm điều tra khó.

### 15.4. Không nhầm multi-AZ với multi-region

AZ resilience chủ yếu xử lý các sự cố trong một region. Multi-region thường yêu cầu **routing/DNS failover, data consistency, application state replication, PKI/trust, logging và data residency**; cost và blast radius lớn hơn. Chọn dựa **RTO/RPO và risk appetite**, không mặc định mọi lab phải multi-region.

## 16. Hai mức kiểm thử: cấu hình tĩnh và kết nối thực

Để tránh kết luận sai, chia verification làm **Level A: configuration verification** và **Level B: traffic/effective enforcement verification**.

### 16.1. Level A — chưa cần tạo máy

Sau khi có VPC/subnets/route tables/SG, có thể:

- So `aws ec2 describe-*` với expected IaC state.
- Kiểm tra CIDR overlap, AZ, IP allocation, route associations.
- Chứng minh public route target là IGW, private route là NAT, management **không có default route**.
- Phân tích security group rules, source-SG references, IPv4/IPv6 CIDRs.
- Xác định có public IP–ENI–LB bị tạo ngoài scope hay không.
- Dùng cloud **reachability/configuration analysis** nếu service hỗ trợ và đã chọn đúng source/destination model.

**Điểm giới hạn:** trong blueprint, SG edge/app chưa attach vào workload, không có listener nào hoạt động. Static validation có thể xác nhận **policy intent**; nó không chứng minh một request HTTPS 200, quản trị thành công hoặc Internet bị chặn tại runtime.

### 16.2. Level B — cần endpoints được phép

Chỉ sau khi owner phê duyệt, thêm:

1. Một **managed load balancer hoặc test service** trên đường public, với SG `edge`.
2. Một **private app test endpoint** với SG `app`, listener TCP/8443 và TLS certificate do lab sở hữu.
3. Một **management test endpoint** được kết nối qua managed session/private endpoints hoặc VPN/ZTNA, với SG phù hợp được kiểm tra.
4. Có thể thêm DB giả lập **không chứa dữ liệu thật**, protected bằng SG riêng nếu test thêm luồng.
5. Một **client được phê duyệt** ở Internet và một client bên trong trust zone khác để chạy negative tests, không dùng port scan toàn mạng.

Thử lần lượt từng đường, giới hạn số requests. Nếu chưa tạo endpoints, ghi kết quả `NOT_RUN`, không ghi `PASS`.

### 16.3. Kiểm thử bị chặn ở lớp nào?

| Lớp từ chối | Dấu hiệu | Cách diễn giải |
|---|---|---|
| DNS | Tên không phân giải hoặc trả IP khác | Chưa thể khẳng định SG/firewall deny |
| Routing | Không có route/target không khả dụng | Có thể traffic chưa đến PEP |
| Network SG/NACL/firewall | Logs/reachability cho thấy deny tại intended boundary | Bằng chứng mạnh hơn timeout đơn lẻ |
| TLS | Certificate/handshake failure | TCP có thể đã thông, nhưng identity/encryption fail |
| Application | HTTP 401/403 hoặc app-specific denial | Network đã đến endpoint, authorization từ chối |
| Service unhealthy | TCP refused, timeout, HTTP 503 | Không tự tính là negative policy test PASS |

**Một kết nối timeout không chứng minh firewall hoạt động đúng** nếu server đã tắt trước khi test. Phải có **positive control** tới cùng healthy destination từ nguồn được phép và evidence từ đúng policy boundary.

## 17. Bộ lệnh kiểm tra được giới hạn trong lab

Các lệnh sau **chỉ dùng với endpoints và routes thuộc quyền quản lý**, từ **máy test đã được phê duyệt**, không thử toàn bộ dải CIDR và không sinh traffic làm gián đoạn hệ thống.

### 17.1. Xem địa chỉ, interface và route trên Linux client

~~~bash
# Read-only observation on a managed lab Linux client.
ip -brief address
ip route show
ip -6 route show
ip rule show

# Shows the routing decision to one approved destination address.
ip route get 10.42.20.10
~~~

`ip route get` trả lời kernel của **client hiện tại sẽ chọn route nào** tại thời điểm query; không chứng minh firewall cho phép hoặc destination thực sự nhận packet. Với VPC cloud, network route nằm ngoài OS/instance cũng ảnh hưởng đường đi.

### 17.2. Truy vấn private DNS theo phạm vi

~~~bash
# Use only authorized lab FQDN.
dig +time=2 +tries=1 app.lab.example.test A
dig +time=2 +tries=1 app.lab.example.test AAAA
~~~

Kết quả cần ghi resolver/address family, timestamp, TTL và câu trả lời. Việc nhận A record `10.42.20.10` không chứng minh có host tại IP đó. **Không chọn IP mẫu rồi coi là thật** trước khi inventory hoặc lab owner cấp.

### 17.3. Một HTTPS request có verify TLS

~~~bash
# One bounded request to an authorized lab endpoint, not production.
curl --silent --show-error \
  --connect-timeout 3 --max-time 8 \
  --output /dev/null \
  --write-out 'http=%{http_code} remote=%{remote_ip} total=%{time_total}s\n' \
  https://app.lab.example.test/health
~~~

Không thêm `-k`/`--insecure` để kết quả giả thành công. Khi private app chỉ listen TCP/8443, URL phải dùng `:8443` và FQDN/certificate hợp lệ **nếu lab thật thiết kế như vậy**. Một HTTPS response `200` từ test client đúng chưa xác minh người dùng không được phép bị deny; đó là phép thử riêng.

### 17.4. Kiểm tra một TCP port đã được phép thử

~~~bash
# Explicit host/port only. Never replace with a subnet-wide scan.
nc -z -v -w 3 app.lab.example.test 8443
~~~

`nc` có biến thể CLI giữa các OS; phiên bản GNU/OpenBSD/BusyBox có thể khác syntax. TCP port test **không kiểm TLS, app auth hoặc identity**. Nếu bị firewall drop có thể timeout; nếu port không có process nghe có thể `connection refused`, không nên đánh đồng.

### 17.5. Kiểm tra app không trực tiếp dùng Internet

Nếu một private test endpoint **không có public IP** và VPC route chỉ NAT outbound, từ external client không thể thực hiện direct inbound qua NAT theo cơ chế thông thường. Nhưng để chứng minh:

- So metadata ENI/instance, public IPv4/IPv6 assignment và route.
- Kiểm tra không có **public LB, port forwarding, proxy hoặc alternate route** gắn vào instance.
- Test từ external source chỉ với **đích được phép**, không dò trùng IP của người khác.
- Xem security group rules và flow logs để phân biệt deny với host không tồn tại.

**NAT EIP không phải địa chỉ SSH vào mọi private VM.** Không dùng IP NAT như một địa chỉ public đại diện cho từng instance.

## 18. Reachability Analyzer và tính giới hạn của phân tích tĩnh

Nhiều cloud cung cấp công cụ phân tích đường đi (chẳng hạn network reachability analyzer) dựa vào route tables, security groups, NACLs, gateways và một số mô hình kết nối. Chúng có giá trị tìm **misconfiguration** trước khi tạo tải thật, nhưng thường:

- Mô hình hóa **một phần đường network/control** chứ không thay app response.
- Không chứng minh HTTP handler, database authentication hoặc TLS SAN đúng.
- Có thể không hỗ trợ mọi resource, overlay, appliance, service mesh hoặc trạng thái động.
- Có thể cần **source/destination ENI/resource cụ thể**; blueprint không có VM chưa chắc cung cấp đủ điểm đầu-cuối để phân tích.
- Kết quả phụ thuộc quyền API, topology snapshot và tool version.

Sử dụng mô hình **configuration audit → reachability analysis → bounded runtime test → application/identity verification** thay vì chỉ dựa một màn hình xanh.

### 18.1. Đường ALLOW mẫu

~~~text
Source:  approved public HTTPS client
Via:     Internet -> public entry
Target:  edge listener TCP/443
Next:    edge identity/SG -> app listener TCP/8443
Expect:  network ALLOW, TLS valid, application health response

Evidence:
  public route + edge SG + app SG + flow decision logs
  test client timestamp and output
  app access log / request ID
~~~

### 18.2. Đường DENY mẫu

~~~text
Source:  unapproved workload in public zone
Target:  management listener TCP/22
Expect:  network DENY at management SG/firewall

Precondition:
  management endpoint is healthy from an authorized management path
  route/source identity correctly modeled

Evidence:
  SG/firewall effective rule + accepted/denied flow observations
  independently verified source/target and UTC time
~~~

Vì blueprint chưa có management listener, ví dụ là **test specification**, không phải hành động đã thực hiện.

## 19. VPC Flow Logs và giám sát sự phân đoạn

### 19.1. Nên quan sát gì?

Một kiến trúc bảo mật mạng cần ít nhất ba nhóm telemetry:

1. **Control-plane audit:** ai tạo/sửa subnet, route, IGW/NAT, SG/NACL và IAM policies; config revision/change ID.
2. **Data-plane visibility:** flow records theo ENI/subnet/VPC scope, addresses/ports/protocol, bytes/packets, action (`ACCEPT`/`REJECT`) theo semantics của nguồn.
3. **Application/identity telemetry:** reverse proxy/access logs, EDR process/socket, Session Manager/ZTNA auth events, TLS/application request IDs.

VPC Flow Logs không phải PCAP; chúng **không cung cấp toàn bộ packet payload hoặc HTTP URL**, và fields/aggregation/sampling/record completeness phụ thuộc cấu hình/platform.

### 19.2. Quan sát từ nhiều phía

~~~mermaid
flowchart LR
    PUB["Public edge ENI"] --> APP["Private app ENI"]
    APP --> NAT["NAT Gateway"]
    ADM["Authorized management channel"] --> MGMT["Management ENI"]
    PUB -. "Flow / SG evidence" .-> LOG["Restricted log repository"]
    APP -. "Flow / process evidence" .-> LOG
    MGMT -. "Access / audit events" .-> LOG
    NAT -. "Cloud route / NAT counters" .-> LOG
    LOG --> SOC["Lab reviewer / SOC"]
~~~

Nên gắn asset identity/ENI/Pod UID với IP theo **event time**, không dùng IP hiện tại để quy kết quá khứ. Với NAT, source IP/port trước và sau NAT có thể cần log bổ sung để nhận dạng workload nguồn.

### 19.3. Những điều Flow Logs không nói chắc được

- `ACCEPT` ở một lớp mạng **không chứng minh** ứng dụng đã xử lý HTTP thành công.
- `REJECT` không nhất thiết do **SG bạn đang kiểm**; có thể từ NACL hoặc lớp khác.
- Không có flow record **không chứng minh không có traffic**, nếu pipeline bị tắt, sampling/aggregation hoặc dữ liệu chưa ingest.
- Một flow có bytes outbound không chứng minh **exfiltration dữ liệu cụ thể** nếu payload được TLS mã hóa.
- Traffic đi qua service-specific networking hoặc resolver nội VPC có thể có observability đặc thù.

### 19.4. No-data là trạng thái riêng

Giám sát nên có các trạng thái:

~~~text
HEALTHY:      expected probes and logs arrive, tests meet policy
VIOLATION:    observed traffic/policy contradicts expected rules
DEGRADED:     logs delayed, sampling/packet loss, or partial path coverage
UNKNOWN:      no telemetry or tester cannot reach a valid observation point
~~~

Không hiển thị **0 deny events = an toàn** nếu flow logging đã dừng hoặc không có nguồn test. Đánh giá independent **heartbeat/last-ingested-time, permission, storage quota và alert delivery**.

### 19.5. Privacy, retention và chi phí

Flow logs, DNS logs và management session records có thể tiết lộ user identity/IP, thời gian kết nối hoặc hostname nội bộ. Giới hạn **log scope, retention, reader roles, encryption và export** theo quy định. Logging có thể phát sinh đáng kể **storage/ingest/egress cost**; tính trước khi bật toàn VPC với retention dài.

## 20. NACL, stateless filtering và return traffic

### 20.1. Security group và NACL khác nhau

Với AWS, **security groups stateful** kiểm soát kết nối của ENI/resource được hỗ trợ. **Network ACLs stateless** được áp ở subnet boundary và kiểm tra từng hướng; rule numbers/priorities/allow–deny semantics khác SG.

~~~text
Client (TCP source port 51000) -> App (TCP 8443)

Forward packet:
  Source 10.42.10.10:51000
  Dest   10.42.20.10:8443

Return packet:
  Source 10.42.20.10:8443
  Dest   10.42.10.10:51000
~~~

Nếu NACL cho forward TCP/8443 nhưng không cho phép return traffic đến **ephemeral client port**, TCP handshake có thể thất bại. Không copy một SG rule sang NACL rồi kỳ vọng behavior tương đồng.

### 20.2. Khi nào bổ sung NACL?

NACL có thể hữu ích như một lớp **subnet-wide guardrail**, ví dụ deny nguồn/đích ngoài zone hoặc chặn một số protocols rõ ràng. Nhưng cần tránh:

- Rule quá rộng chặn DNS, health checks hoặc return traffic.
- Rule priorities xung đột, log/trace khó hiểu.
- Chỉ kiểm IPv4 mà quên IPv6.
- Tự coi NACL bảo vệ traffic intra-subnet giống traffic qua subnet boundary.
- Đánh đồng `ACCEPT` tại một point với end-to-end success.

**Bản lab tối thiểu không tạo custom NACL** để tránh phát sinh cấu hình stateless dễ sai trong bước đầu. Nếu yêu cầu NACL deny layer, thêm như một **bài mở rộng có bảng return ports và negative tests rõ**; kiểm tra default NACL/effective subnet association thực tế.

### 20.3. Anti-pattern: dùng NACL làm quản lý danh tính

NACL xử lý CIDR/protocol/ports, **không hiểu user, IAM role, mTLS workload identity hoặc business authorization**. Với quyền quản trị, phải kết hợp **IAM, SSO/MFA, PAM/session recording, SG/host firewall**. Một subnet management không trở nên zero-trust chỉ vì NACL chặn toàn Internet.

## 21. IPv6: thiết kế riêng trước khi enable

### 21.1. Vì sao IPv6 cần một quyết định độc lập?

Trong AWS, một instance có thể dùng địa chỉ IPv6 globally routable khi subnet/VPC có IPv6 allocation và route phù hợp, **không cần NAT IPv4**. Nếu tổ chức tạo policy chỉ cho `0.0.0.0/0`, traffic IPv6 có thể đi theo rules khác hoặc không được giám sát đầy đủ.

Để mở dual-stack:

1. Chọn VPC/subnet IPv6 CIDR allocation được cloud hỗ trợ.
2. Xác định public IPv6 ingress (nếu thực sự cần) qua IGW và SG/NACL IPv6.
3. Với private IPv6 egress, xem **egress-only Internet Gateway** hoặc egress firewall theo architecture.
4. Management IPv6 không có public inbound; kiểm tra đúng private access path.
5. Kiểm tra AAAA records, resolver, TLS SAN/reference names, flow logs và endpoint agents.
6. Test IPv4/IPv6 positive và negative flows riêng.

### 21.2. Không tự sao chép route table

~~~text
IPv4 public default:       0.0.0.0/0 -> IGW
IPv4 private default:      0.0.0.0/0 -> NAT Gateway
IPv4 management default:   none

IPv6 public default:       ::/0 -> IGW        (ONLY if approved)
IPv6 private default:      ::/0 -> egress-only IGW / approved PEP
IPv6 management default:   none              (baseline intent)
~~~

Đây là **thiết kế định hướng**, không phải cấu hình có thể apply ngay. Một IPv6 egress-only gateway vẫn **không tự thực hiện domain-aware filtering**, chỉ xử lý hướng kết nối theo semantics của cloud.

### 21.3. IPv6 privacy addresses và attribution

IPv6 endpoints có thể dùng nhiều addresses/suffixes thay đổi theo thời gian. Khi điều tra, map **ENI/asset identity, device/Pod UID, source IP theo UTC time**; không suy IPv6 address luôn là định danh user cố định.

## 22. Windows/Linux/cloud-specific network behavior

### 22.1. Host firewall vẫn cần có

Cloud SG/NACL bảo vệ ở network boundary, nhưng OS vẫn có **listeners, local firewall, container port mapping, reverse proxy và agent-based policy**. Nếu bật SSH/RDP trên OS rồi gắn SG sai, service có thể bị phơi bày.

Checklist host:

- Chỉ chạy services cần thiết, bind đúng interface/port.
- SSH dùng key-based auth/identity-aware access theo policy; không public SSH mặc định.
- RDP qua private managed access, MFA/PAM, NLA và host hardening khi phù hợp.
- TLS certificate SAN/chain hợp lệ cho ứng dụng, không bypass verify.
- Agent/logging/patching có đường riêng và retention.
- Không lưu cloud credentials trong startup scripts hoặc environment dumps.

### 22.2. Kubernetes làm ranh giới phức tạp hơn

Pod IPs, service cluster IPs, node-level NAT, overlay CNI và NetworkPolicy có thể khiến **AWS SG của node** chỉ là một phần của kiểm soát. Khi thêm Kubernetes:

- Xem CNI có thực thi NetworkPolicy/SG-for-Pods hay không.
- Standard Kubernetes NetworkPolicy **cho phép cộng dồn** giữa policies chọn cùng Pod, không có deny policy tuyệt đối theo mô hình mặc định.
- `hostNetwork` và node-level services có thể ở path khác Pod overlay.
- Service mesh mTLS không tự thực thi authorization cho toàn bộ traffic nếu dataplane bị bypass hoặc policy permissive.
- Pod IP tái sử dụng làm attribution sai khi không ghi Pod UID/time.

Không coi private subnet của worker nodes là bằng chứng mọi Pods được isolation theo yêu cầu.

### 22.3. Cloud platform khác nhau

| Khái niệm | AWS minh họa | Azure / GCP và lưu ý |
|---|---|---|
| Network boundary | VPC và AZ-scoped subnets | Azure VNet subnets và NSGs; GCP VPC subnets thường regional |
| Internet egress | IGW/NAT Gateway theo routing | NAT gateway/cloud NAT và route/firewall semantics khác |
| Instance firewall | SG/NACL | NSG, VPC firewall rules, hierarchical policies tùy cloud |
| Public entry | ALB/NLB/IGW | Load balancer/application gateway và public IP specifics |
| Private service access | VPC endpoints | Private Link/Private Endpoint/Private Service Connect |
| Management | Session Manager/private endpoint | Bastion/Arc/managed identity access theo dịch vụ |
| Flow visibility | VPC Flow Logs | Network watcher/flow logs/cloud logging theo product |

Không map **AWS public/private subnet** từng dòng một sang GCP hoặc Azure: **GCP subnet không tự có "public route table" riêng theo cùng nghĩa AWS**, và cách firewall/route phân phối có thể ở phạm vi VPC/project. Chuyển cloud cần bắt đầu từ **security intent** rồi thiết kế lại các resource native.

## 23. Bảng lỗi phổ biến trong lab và cách phân biệt

| Triệu chứng | Nguyên nhân có thể | Xác minh an toàn |
|---|---|---|
| Public subnet có IGW nhưng không truy cập được VM | Không có public IP/listener, SG deny hoặc DNS sai | ENI/public IP, route, SG, listener |
| Private app không cập nhật OS qua Internet | NAT chưa ready, route sai, SG egress thiếu hoặc DNS issue | NAT state, route association, allowed HTTPS test |
| Private app truy cập public app nội VPC được dù không muốn | VPC local route và SG khác vẫn allow | Effective SG rules, attachments, flow logs |
| Management SG vẫn truy cập outbound | SG khác gắn vào ENI hoặc default egress chưa được xử lý | Effective attached SG union, route + egress logs |
| Management không vào được qua SSM | Thiếu IAM/agent/private endpoints/DNS/SG/clock | Session audit, endpoint services và permissions |
| VPC endpoint tạo xong nhưng app không kết nối | Endpoint SG/policy/IAM/private DNS sai | Effective endpoint SG, DNS và API permission |
| Private app có public IPv6 | Dual-stack/route `::/0`, IPv6 SG mở | ENI IPv6, routes, SG IPv6 |
| NAT báo available nhưng app HTTPS fail | App SG, DNS, target outage hoặc firewall egress | Test request, flow logs, NAT metrics |
| NAT Gateway bị lỗi deployment | EIP/quota/subnet/IGW availability | Resource status và account quota |
| Route table được tạo nhưng subnet không đi theo | Thiếu explicit route association | Subnet association/effective main route |
| App SG có ingress chỉ từ edge nhưng test từ máy khác PASS | Gắn SG bổ sung hoặc test qua proxy khác | ENI attached SGs, source identity, alternate path |
| NACL chặn hợp lệ | Quên ephemeral return ports | Inbound/outbound NACL rules và flow |
| DNS trả private IP nhưng curl timeout | Host không tồn tại, route/SG/listener/TLS | Inventory, listener logs và request path |
| Flow Logs không có records | Collector off, delay, sampling, destination/permissions | No-data metrics, log config và time window |
| Flow `ACCEPT` nhưng HTTP 403 | Network allowed, app authz deny | App access log và role policy |
| Flow `REJECT` từ test deny | SG/NACL khác chặn, chưa chắc rule mong đợi | Effective rule/PEP attribution |
| Multi-AZ private egress đi NAT AZ khác | Route associations hoặc NAT placement sai | Route per subnet/AZ, NAT AZ |
| IaC plan muốn xóa tài nguyên ngoài lab | Wrong workspace/backend/account/state import | STOP; verify account/state/plan ownership |
| Chi phí tăng dù không tạo VM | NAT/EIP/endpoints/logging vẫn tính phí | Resource inventory, cost explorer/budget |
| Terraform `validate` PASS nhưng app không hoạt động | Validate chỉ kiểm syntax/provider schema, không vận hành | Config review, plan, runtime tests |
| TLS error bị gán nhầm network deny | TCP thông nhưng certificate/CA/hostname sai | Strict client TLS diagnostics |
| Port timeout bị ghi PASS của DENY | Destination down, DNS sai hoặc test sai source | Positive control, PEP logs, exact asset mapping |

### 23.1. Thứ tự chẩn đoán từng lớp

1. **Đúng tài khoản/vùng/VPC/subnet/asset chưa?**
2. Địa chỉ/hostname, DNS A/AAAA và protocol/port đúng chưa?
3. Source/destination ENI identities, public/private IP mapping theo thời điểm đúng không?
4. Route table/association/IGW/NAT/endpoint state có đúng ý định?
5. Security groups **effective union** và NACL hai hướng có cho hay chặn?
6. OS listener/host firewall/TLS handshake có bình thường?
7. Application authorization và database privileges có đúng?
8. Flow logs, session audit, app logs và monitoring coverage có dữ liệu thật?
9. Khi sửa, ghi IaC diff/approval, kiểm **positive + negative** và rollback.

Không xử lý mọi lỗi bằng cách thêm `0.0.0.0/0` inbound hoặc gán public IP cho private instance.

## 24. Case study 1 — Private subnet nhưng backend vẫn bị truy cập ngang

### 24.1. Tình huống giả định

Một kỹ sư triển khai public load balancer ở `10.42.10.0/24` và app ở `10.42.20.0/24`. App không có public IP; kỹ sư kết luận app "không thể bị truy cập từ vùng khác". Sau đó nhóm kiểm thử lab phát hiện một VM nằm trong public subnet **có thể trực tiếp gọi TCP/8443 tới private app**, dù nó **không phải load balancer được phê duyệt**.

Điều tra cho thấy app instance được attach **hai security groups**:

~~~text
sg-app-restricted:
  ingress TCP/8443 source sg-edge

sg-legacy-default:
  ingress TCP/8443 source 10.42.0.0/16

Effective SG permissions:
  union of both allow rules
~~~

Tất cả tên, cổng và sự kiện ở đây là **case giả định**, không phải môi trường đang tồn tại.

### 24.2. Tại sao private subnet chưa đủ?

Trong VPC có **local route** giữa public và private CIDRs; route tới private subnet không đi qua Internet Gateway hay NAT. Nếu một SG khác mở `10.42.0.0/16`, bất kỳ source nào trong CIDR phù hợp có thể được phép đi thẳng tới app, tùy các controls còn lại. **Không có public IP** chỉ chặn một nhóm đường inbound trực tiếp từ Internet, không xóa tất cả các đường *east–west*.

### 24.3. Cách kiểm chứng

1. Xác định app ENI/instance ID, tất cả SGs gắn vào ENI tại thời điểm test.
2. Xem **effective union** của ingress rules, không chỉ `sg-app-restricted`.
3. So association route của source public subnet, target private subnet và `local` route.
4. Tạo hai **source test identities** được phê duyệt: một đại diện edge SG, một non-edge SG.
5. Positive: edge SG → app TCP/8443 **ALLOW**, TLS/application health đạt.
6. Negative: non-edge public VM → app TCP/8443 **DENY**, xác minh ở SG/PEP.
7. Loại SG legacy theo change control; kiểm tra thêm application authorization và egress.

### 24.4. Bảng trước/sau giả định

| Phép thử | Trước sửa | Sau sửa kỳ vọng |
|---|---|---|
| Edge LB → app:8443 | ALLOW | ALLOW |
| Unapproved public VM → app:8443 | ALLOW sai policy | DENY |
| Internet → app private IP trực tiếp | Không có route public trực tiếp theo thiết kế | Vẫn không được mở |
| Management VM → app admin port | Tùy old SG; chưa chắc chắn | Chỉ authorized access |
| App → unapproved outbound destination | Có thể ALLOW qua NAT/443 | Phải theo egress policy thực tế |

### 24.5. Bài học

**Trust zone là tập hợp route, identity, firewall và application controls**, không phải nhãn `private`. Khi gắn nhiều SG, **một allow rộng có thể mở quyền ngoài ý định**; positive/negative tests từ đúng nguồn là bắt buộc.

## 25. Case study 2 — Management subnet không Internet nên agent mất kết nối

### 25.1. Tình huống giả định

Đội platform tạo management subnet chỉ có route local. Họ cài managed session agent trên một instance nội bộ, rồi thử mở session từ console và nhận lỗi **target not connected**. Một người đề xuất:

~~~text
Emergency workaround:
  Add 0.0.0.0/0 -> Internet Gateway to management subnet
  Assign a public IPv4 address
  Open TCP/22 from 0.0.0.0/0
~~~

Đề xuất này **mở một đường quản trị công khai không cần thiết** và phá mục tiêu thiết kế.

### 25.2. Nguyên nhân có thể

- Agent chưa được cài hoặc không chạy, OS chưa hỗ trợ.
- IAM instance profile/role không có quyền đúng.
- Management subnet không có route tới **VPC interface endpoints** của service quản trị.
- Private DNS/endpoint resolution sai.
- Endpoint SG không cho agent outbound TLS connect và return traffic phù hợp.
- Organization policy/service endpoint/region không hỗ trợ như giả định.
- Agent time sync, endpoint certificates hoặc control-plane permissions lỗi.
- Người quản trị đăng nhập console nhưng thiếu IAM authorization để mở session.

### 25.3. Thiết kế khắc phục an toàn

~~~mermaid
flowchart TB
    ADMIN["Admin with SSO/MFA"]
    SERVICE["Managed session service"]
    ENDP["Private VPC interface endpoints"]
    AGENT["Management instance agent"]
    APP["Private application, limited management access"]
    LOG["Central IAM/session audit"]
    ADMIN --> SERVICE
    SERVICE --> ENDP
    ENDP --> AGENT
    AGENT -->|"Approved identity/port"| APP
    SERVICE -. "Session metadata" .-> LOG
~~~

Triển khai **chỉ các endpoint services cần thiết** theo region/agent/version, endpoint policies, private DNS, IAM, SG và TLS. Giữ **management subnet không có default Internet route** nếu yêu cầu; không gắn public IP chỉ để sửa agent connection.

### 25.4. Kiểm thử kết quả

| Test | Kỳ vọng |
|---|---|
| Approved admin với role hợp lệ | Có thể tạo managed session qua private path |
| Admin không thuộc nhóm | IAM/session creation DENY |
| Target agent đến service endpoint | TLS/identity connection ALLOW |
| Internet → management TCP/22 | DENY |
| Management → unapproved private service | DENY |
| Revoke admin role/session | Session behavior phù hợp policy, logged |
| Session service unavailable | Có break-glass/OOB plan được phê duyệt |

### 25.5. Bài học

Khi một subnet quản trị bị cắt Internet, **đường private service và IAM** phải được thiết kế chủ động. "Không quản trị được" không phải lý do hợp lệ để mở public SSH cho cả Internet.

## 26. Case study 3 — NAT một AZ, ứng dụng hai AZ và route không nhất quán

### 26.1. Bối cảnh giả định

Doanh nghiệp mở rộng từ một AZ sang hai AZ, tạo thêm:

~~~text
AZ A: public 10.42.10.0/24, private 10.42.20.0/24
AZ B: public 10.42.11.0/24, private 10.42.21.0/24
~~~

Nhưng subnet private B **vẫn dùng NAT-A**, nằm ở AZ A. Khi AZ A/NAT-A có sự cố, application B vẫn xử lý requests nội bộ nhưng không thể gọi approved external API/updates. Ngoài ra, subnet management B chưa có explicit route table association nên theo main table bất ngờ.

### 26.2. Mô hình failure domain

~~~mermaid
flowchart LR
    APP_A["App AZ A"] --> NATA["NAT AZ A"]
    APP_B["App AZ B"] --> NATA
    NATA --> IGW["Internet Gateway"]
    FAIL["AZ A / NAT A unavailable"] -. "Egress outage both AZs" .-> APP_B
~~~

### 26.3. Bản thiết kế điều chỉnh

| Thành phần | Trước | Sau kỳ vọng |
|---|---|---|
| Private A default IPv4 route | NAT-A | NAT-A |
| Private B default IPv4 route | NAT-A | NAT-B ở AZ B |
| Management B route association | Main RT | RT-management-B rõ ràng |
| App deployment | Multi-AZ | Multi-AZ và kiểm external dependency |
| NAT failure detection | Chỉ nhìn app uptime | Đo egress success từng AZ |
| Cost | Một NAT, cross-AZ traffic | Hai NAT, so thêm phí/availability |

Tạo NAT-B có **chi phí và quota bổ sung**; không thay route sản xuất mà không kiểm tra plan, owner và risk. Nếu cần yêu cầu "không Internet egress", giải pháp không phải tạo NAT-B mà là xem **private endpoints/mirrors** phù hợp.

### 26.4. Các test xác nhận

1. Kiểm subnet associations và target NAT theo **AZ của private subnet**.
2. Từ app A/B authorized clients, test bounded HTTPS đến một test endpoint **được phép**.
3. Đo DNS, route, TLS, app response và egress/NAT metrics theo từng AZ.
4. Tabletop hoặc diễn tập có phê duyệt về mất NAT-A, xác nhận app B theo SLO.
5. Kiểm tra management B không có default public route, SG không mở public admin.
6. Đánh giá chi phí NAT/egress/cross-AZ, tránh tối ưu "HA" bằng cấu hình tạo bill shock.

### 26.5. Bài học

**Nhiều AZ chỉ giúp resilience khi dependencies được phân tán tương xứng**. Việc có hai app nodes nhưng cùng phụ thuộc một NAT AZ tạo single failure domain ẩn.

## 27. Case study 4 — IPv6 tạo đường vào ngoài ý định

### 27.1. Bối cảnh giả định

Một nhóm mở IPv6 cho VPC để thử dual-stack. Họ giữ IPv4 private app route qua NAT và security group inbound IPv4 rất chặt. Nhưng khi áp automation từ template khác, một instance nhận **IPv6 address**, subnet có `::/0 → IGW` và một SG phụ có IPv6 inbound `::/0` TCP/8443.

Từ một IPv6-capable external client có quyền trong lab, nhóm kiểm thử thấy endpoint app có thể được truy cập **trực tiếp bằng IPv6**.

### 27.2. Vì sao NAT IPv4 không bảo vệ IPv6?

NAT Gateway IPv4 không nằm trên đường IPv6 trực tiếp đến address globally routable. IPv6 route/SG được xét riêng; **không có public IPv4** không bảo đảm host không có externally reachable IPv6.

### 27.3. Quy trình điều tra

- Inventory VPC/subnet IPv6 CIDRs, ENI IPv6 addresses và actual routes.
- Xem tất cả SGs gắn vào ENI, `::/0` inbound và NACL IPv6.
- Xác định instance/container listener trên IPv6 socket.
- Kiểm tra IPv6 DNS AAAA và hostname certificate path.
- Gỡ public IPv6 route/rules **theo approval và rollback** để phù hợp intended zone.
- Đặt IPv6 parity tests trong IaC policy và continuous audit.

### 27.4. Kết luận

**Subnet private là một tính chất của effective network reachability**, không chỉ tên và cấu hình IPv4. IPv6, multi-homed interfaces và proxy routes phải được xét trong threat model.

## 28. Ma trận 50 phép kiểm thử của lab

Bảng dưới đây là **test specification**, không phải báo cáo đã chạy. Nhóm `CID` và một số `RTE` có thể kiểm **chỉ từ IaC/control-plane state** sau khi có tài nguyên; các test về **traffic, TLS, app auth, management** cần endpoints/service dependencies được lab owner triển khai và được phê duyệt riêng. Nếu chưa có test workload, kết quả phải ghi `NOT_RUN`, không tự chuyển sang PASS.

| Test ID | Mục tiêu | Phương pháp/nguồn chứng cứ | PASS khi |
|---|---|---|---|
| **CID-01** | VPC CIDR đúng scope | HCL/describe-vpcs | `10.42.0.0/16`, đúng sandbox |
| **CID-02** | Public CIDR đúng | Describe subnet và IPAM | `10.42.10.0/24`, không overlap |
| **CID-03** | Private CIDR đúng | Describe subnet và IPAM | `10.42.20.0/24`, không overlap |
| **CID-04** | Management CIDR đúng | Describe subnet và IPAM | `10.42.30.0/24`, không overlap |
| **CID-05** | AZ/region đúng | Account/AZ/subnet inventory | Tất cả nằm vùng đã duyệt |
| **CID-06** | Không tự gán public IPv4 | Subnet auto-assign flags | `map_public_ip_on_launch=false` cho ba subnet |
| **CID-07** | Không có public ENI/IPv6 ngoài kế hoạch | ENI/instances/LB/IP metadata | Không có asset với đường public ngoài scope |
| **RTE-01** | Public subnet có IGW default | Effective route table + association | `0/0 → IGW` tại public subnet |
| **RTE-02** | Private subnet dùng NAT theo plan | Effective route, NAT state | `0/0 → NAT`, NAT trong public route đúng |
| **RTE-03** | Management không default Internet | Effective route table | Không có `0/0` hoặc `::/0` public route |
| **RTE-04** | Ba associations explicit | Route associations | Không phụ thuộc main RT ngoài ý định |
| **RTE-05** | Có local route nội VPC | Effective routes | Biết rõ nội subnet/VPC paths còn reachable |
| **RTE-06** | NAT thực hiện outbound IPv4 | Controlled private lab test + flow logs | Approved outbound request thành công |
| **RTE-07** | NAT không tạo inbound public vào private | Inventory/public mapping + approved test | Không có direct inbound path |
| **RTE-08** | Multi-AZ expansion không cùng failure domain | Per-AZ route review/tabletop | NAT targets/availability theo design |
| **SG-01** | Edge chỉ công bố HTTPS được duyệt | SG rules + assigned edge listener | Chỉ intended inbound listener ALLOW |
| **SG-02** | App chỉ nhận edge SG TCP/8443 | SG attachment + positive source | Edge-to-app ALLOW |
| **SG-03** | Non-edge public client không vào app | Negative source + target healthy | DENY ở SG/firewall |
| **SG-04** | Internet không vào management | Effective SG/routes + permitted test | DENY, không public SSH/RDP |
| **SG-05** | SG union không mở quyền rộng | ENI attached SG inventory | Không có legacy/default allow trái intent |
| **SG-06** | Unapproved app→management bị chặn | Negative test source + flow logs | DENY ở đúng PEP |
| **SG-07** | Egress app theo policy thật | SG/egress PEP/proxy evidence | Không coi NAT là destination allowlist |
| **SG-08** | NACL return ports không phá ALLOW | Positive TCP/TLS test + NACL review | Stateful success phù hợp yêu cầu |
| **ADM-01** | Approved admin có role hợp lệ | SSO/IAM + managed session audit | Admin connect theo đúng private path |
| **ADM-02** | Non-entitled admin bị deny | IAM negative test trong lab | DENY ở identity layer |
| **ADM-03** | Management agent có private endpoint path | Route/DNS/IAM/endpoint SG | Agent tới đúng service endpoint |
| **ADM-04** | Không cần public SSH | Public IP/SG/listeners review | Không có 22/3389 public bypass |
| **ADM-05** | Quyền quản trị resource được giới hạn | IAM policy + approved/denied target tests | Không truy cập mọi targets |
| **ADM-06** | Session revocation hoạt động | Tabletop/lab authorized test | Session/token behavior đúng policy |
| **ADM-07** | Có out-of-band recovery | Runbook/controlled drill | Không buộc mở public admin |
| **DNS-01** | Private DNS phân giải đúng | Authorized private resolver query | A/AAAA target theo zone |
| **DNS-02** | DNS public không lộ private-only name | Resolver zone config + scoped query | Không lộ thông tin ngoài intent |
| **DNS-03** | DoH/alternate resolver policy | Managed client DNS config | Không có bypass ngoài policy |
| **DNS-04** | VPC endpoint policy và DNS đúng | Endpoint reachability + IAM checks | Authorized service request ALLOW |
| **DNS-05** | Endpoint không cấp quyền IAM tự động | Unapproved role test | DENY dù TLS/connect reachable |
| **OBS-01** | Network flow logs đúng source | Flow log setup and sample records | Có source/target/time/action phù hợp |
| **OBS-02** | Control-plane changes audit | Authorized route/SG change event | Actor, UTC, change ID traceable |
| **OBS-03** | Positive/negative logs tương ứng | Join test ID/time/PEP decision | Không chỉ suy từ timeout |
| **OBS-04** | No-data alarm hoạt động | Lab log-forwarder interruption/tabletop | UNKNOWN/alert, không false green |
| **OBS-05** | IP/NAT attribution theo thời gian | DHCP/ENI/NAT identity mapping | Đúng workload và UTC window |
| **OBS-06** | Privacy/retention đúng | Access/encryption/retention review | Evidence hạn chế đúng đối tượng |
| **OPS-01** | IaC account/workspace đúng | STS/region/backend review | Không động vào production khác |
| **OPS-02** | Terraform fmt/validate/plan review | CI/read-only plan | Không có unexpected changes |
| **OPS-03** | Không để credential trong IaC/state export | Secret/role governance review | Không lộ key/token trong report |
| **OPS-04** | NAT/public IPv4 cost được quản lý | Budget and resource inventory | Owner, threshold, cleanup plan rõ |
| **OPS-05** | Failure of NAT/IGW có runbook | Tabletop/canary approved exercise | Tác động/rollback biết trước |
| **OPS-06** | IPv6 controls theo intended zone | IPv6 address/route/SG review | Không có public management bypass |
| **OPS-07** | Critical service positive/negative outcomes | Authorized canary test | ALLOW đúng, DENY đúng và app healthy |
| **OPS-08** | Drift detection và policy review | IaC diff + cloud inventory | Không có route/SG drift bất ngờ |
| **OPS-09** | Cleanup an toàn và billing dừng | Approved destroy plan + post-inventory | Chỉ xóa lab, không còn chargeable leftovers |

### 28.1. Phân loại kết quả

| Trạng thái | Khi nào ghi |
|---|---|
| **PASS** | Có evidence đủ từ đúng asset, path, điểm thực thi và thời gian chứng minh kỳ vọng |
| **FAIL** | Luồng trái policy ALLOW, luồng hợp lệ DENY do cấu hình, credential/secret lộ, hoặc có phát hiện thực tế trái yêu cầu |
| **INCONCLUSIVE** | Đường test không chạm đúng PEP, target down, source identity không chắc, logs thiếu hoặc cloud API chưa đủ |
| **NOT_RUN** | Chưa triển khai endpoint, chưa được phép, hoặc test có rủi ro chưa được approval |
| **N/A** | Điều kiện không áp dụng; có reviewer, lý do và policy reference |

**PASS của bài lab không đồng nghĩa kiến trúc sản xuất đạt tiêu chuẩn pháp lý hoặc HA**. Blueprint một AZ còn có dependencies/chi phí/management access cần xây trước khi sử dụng thực.

### 28.2. Mẫu hồ sơ test

~~~yaml
# Chưa thực hiện. Thay placeholders bằng evidence khi test thật.
lab_id: NETSEC-LAB-003
test_id: SG-03
status: NOT_RUN
time_utc: pending
source:
  role: non-edge-public-workload
  asset_identity: pending
  subnet: 10.42.10.0/24
target:
  role: private-test-app
  asset_identity: pending
  subnet: 10.42.20.0/24
  tcp_port: 8443
preconditions:
  - target-healthy-from-approved-edge-source
  - source-and-target-correctly-identified
  - no-extra-unreviewed-security-groups
expected:
  approved_edge_to_app: allow
  unapproved_public_to_app: deny
evidence_required:
  - effective-routes-and-sg-attachments
  - flow-decision-at-enforcement-point
  - client-test-time-and-exit-status
  - positive-control-at-same-destination
observed: pending
reviewer: pending
~~~

### 28.3. Thử từ đúng nguồn quan trọng hơn số lượng tests

Một test gửi từ **inside app subnet** không thay thế test từ **Internet**, vì route/Security Group và NAT behavior khác. Một test gửi từ VM **có SG edge** không đại diện nguồn public không có quyền. Trong biên bản, phải ghi **source identity, network location, protocol, destination, route và effective permissions**.

### 28.4. Không chạy stress test hoặc quét mạng ngoài scope

Kiểm thử có thể dùng **1–3 kết nối có giới hạn** đến endpoint lab được phép, IaC diff và cloud-native reachability analysis. Không cần port-scan toàn VPC, brute-force credentials, DoS traffic hoặc tắt firewall trên production để chứng minh ý tưởng.

## 29. Runbook triển khai, xác minh và thu hồi lab

Runbook dành cho **sandbox riêng** có chủ sở hữu, chi phí được phê duyệt và IaC backend/state rõ. Nó không cấp quyền can thiệp hệ thống thật. Nếu các giả định ban đầu không đúng, ưu tiên dừng tại **preflight** và trình người quản lý lab thay vì tự sửa account security controls.

### Giai đoạn A — Chuẩn bị trước deployment

**Bước 1: Xác định scope.** Ghi cloud account/project, IAM role, region, AZ, VPC CIDR, owner, contact và budget alert. Đối chiếu IPAM/peering/VPN routes để loại **CIDR overlap**.

**Bước 2: Phê duyệt security intent.** Có bảng public/private/management, authorized sources/destinations/ports, NAT/IPv6 policy, private management path và data classification.

**Bước 3: Review IaC.** Code review phải kiểm Terraform root module/provider version, remote state, SG rules, route associations, source references, resource tags và những tài nguyên tạo chi phí.

**Bước 4: Confirm identity.** Check SSO/IAM session, account/region/workspace, budget và quyền xóa đúng resources. Không tiếp tục nếu `plan` chứa thay đổi ngoài sandbox.

### Giai đoạn B — Tạo network skeleton

**Bước 5: Deploy VPC/subnets.** Xác nhận CIDRs và AZ, disable auto public IP. Không deploy workloads trước khi route/security policies được review.

**Bước 6: Deploy IGW/NAT/routes.** Kiểm các associations và NAT status. Với management không tạo default public route; nếu không cần private outbound, cân nhắc blueprint không NAT trước khi apply.

**Bước 7: Deploy SG policies.** Review edge→app source-SG references, app outbound policy và management default deny thực tế; xác minh không có unexpected SG attachments/default allow.

**Bước 8: Set observability.** Bật controlled audit/flow logs/alerts theo budget và data policy khi có quyền, ghi nơi lưu, retention và quyền reader.

### Giai đoạn C — Xác minh nền tảng trước khi có workloads

**Bước 9: Configuration review.** So effective route, SG, NACL, subnet/public IP settings với ma trận, không chỉ `terraform validate`.

**Bước 10: Threat and cost review.** Xác nhận đường tới Internet và management không vô tình mở, NAT còn charge, không có IPv6 route nếu chưa duyệt.

**Bước 11: Báo trạng thái đúng.** Kết quả network skeleton đạt `CONFIGURATION_VERIFIED`; traffic tests chưa có endpoints là `NOT_RUN`, không "production-ready".

### Giai đoạn D — Test workloads có kiểm soát

**Bước 12: Có approval riêng.** Chỉ thêm load balancer/VM/test service nếu scope cho phép, không dùng credentials/dữ liệu kinh doanh thực.

**Bước 13: Positive tests trước.** Edge HTTPS và edge→app backend health, management path với authorized identity, outbound updates nếu yêu cầu.

**Bước 14: Negative tests sau.** Internet→private/management, non-edge→app, app→management và IPv6/alternate path theo test plan.

**Bước 15: Correlate evidence.** Đối chiếu client exit codes, network PEP logs, route/SG decisions, app/TLS logs và UTC; **timeout không tự chứng minh DENY**.

**Bước 16: Failure mode exercises.** Khi được cho phép, tabletop về NAT unavailable, log pipeline broken, management endpoint fail, AZ outage, IAM compromise; không dùng chaos testing trực tiếp trên production.

### Giai đoạn E — Kết thúc và dọn dẹp

**Bước 17: Niêm phong evidence.** Lưu bài học, IaC plan/diff, route/SG screenshots/exports nếu cần, test IDs, kết luận và hạn chế quan sát. Không giữ raw credentials trong artifact.

**Bước 18: Xem destroy plan.** Đảm bảo **mọi resource nằm trong state đều chỉ thuộc lab** và không có resource nào bị các nhóm khác dùng. Với state trộn nhiều systems hoặc shared workspace, **không chạy destroy**.

**Bước 19: Dọn theo phê duyệt.** Với một lab Terraform chuyên dụng, sau review:

~~~bash
# CHỈ chạy trong đúng isolated lab IaC root, sau owner approval.
# Không chạy trên production/shared Terraform state.
terraform plan -destroy
terraform destroy
~~~

**Bước 20: Kiểm tồn dư và billing.** Xác minh NAT Gateway/EIP, endpoints, load balancer, ENI, log destinations, volumes, IAM temporary roles và billable resources không còn ngoài intent. Một số logs hoặc state được giữ theo retention/legal hold, không xóa chứng cứ đang cần điều tra.

### 29.1. Tiêu chí dừng khẩn cấp

Ngừng triển khai hoặc test và chuyển escalation khi:

- Account/region/workspace hoặc state không đúng scope.
- Plan muốn xóa/sửa route, SG hay IAM resource bên ngoài lab.
- Public management SSH/RDP hoặc private data service bị expose ngoài ý định.
- CIDR overlap tạo xung đột với on-prem/partner.
- Kết quả test trái chính sách security nhưng không có rollback owner.
- NAT/IPv4/public resource phát sinh chi phí ngoài budget đã duyệt.
- Không thể phân biệt traffic fail do policy với host down nhưng người khác yêu cầu công bố PASS.

### 29.2. Recovery không bằng "allow all"

Nếu app không kết nối, dùng trình tự **DNS → route → SG/NACL → listener/TLS → application/identity**, rồi sửa đúng nguyên nhân. Đừng thêm inbound `0.0.0.0/0` cho app/management hay egress `all protocols/all ports` chỉ để vượt bài test. Nếu có emergency exception, phải có **narrow scope, approval, expiry, owner và post-change negative tests**.

### 29.3. Mẫu handoff

~~~yaml
lab_id: NETSEC-LAB-003
state: CONFIGURATION_VERIFIED_NOT_PRODUCTION_READY
environment: approved-sandbox
vpc_cidr: 10.42.0.0/16
subnets:
  public: 10.42.10.0/24
  private: 10.42.20.0/24
  management: 10.42.30.0/24
routing:
  public_default: IGW
  private_default: NAT_Gateway
  management_default: absent
security:
  edge_https: planned
  app_from_edge: planned
  management_access: no-public-ingress
test_summary:
  static_review: pending-evidence
  runtime_positive: NOT_RUN
  runtime_negative: NOT_RUN
  management_session: NOT_RUN
observability:
  flow_logs: pending
  change_audit: pending
cost_and_cleanup:
  nat_gateway_billable: yes-if-created
  owner: pending
  destroy_approval: pending
limitations:
  - single-availability-zone-example
  - no-test-workloads-created-by-blueprint
  - no-automatic-logging-or-private-endpoints
  - no-production-security-certification
~~~

Khi có test thật, reviewer cần thay **`pending/NOT_RUN` bằng nguồn chứng cứ**, không suy ra kết quả từ template. Trong tài liệu này không có Terraform command nào đã được chạy trên tài khoản người học.

## 30. Bài tập và câu hỏi tự kiểm tra

### Bài 1 — Dung lượng một subnet `/24`

Subnet `10.42.20.0/24` có bao nhiêu IPv4 addresses về lý thuyết? Với AWS giữ lại năm địa chỉ mỗi subnet thì còn bao nhiêu có thể cấp theo quy tắc đó?

*Đáp án:* \(2^{32-24}=256\) địa chỉ tổng; theo AWS, thông thường còn \(256-5=251\) địa chỉ có thể dùng cấp trong subnet. Không đem con số usable AWS áp cho cloud khác.

### Bài 2 — Kiểm tra CIDR overlap

Ba subnet `10.42.10.0/24`, `10.42.20.0/24`, `10.42.30.0/24` có chồng nhau không? Chúng có thuộc `10.42.0.0/16` không?

*Đáp án:* không overlap, cùng thuộc `/16`. Để chắc chắn với các subnet khác của tổ chức, cần IPAM/route inventory và kiểm trong mọi VPC/VPN/peering có liên quan.

### Bài 3 — Public hay private theo route

Một subnet có `0.0.0.0/0 → IGW` nhưng mọi instances chỉ có private IPv4 và không có public ingress SG. Có thể từ Internet tùy ý SSH tới chúng không?

*Đáp án:* không. Có IGW route không tự cấp public IP, mở OS listener hay SG inbound.

### Bài 4 — NAT outbound

Một private instance có route `0.0.0.0/0 → NAT Gateway`. Điều này cho phép Internet chủ động SSH vào instance không?

*Đáp án:* không. NAT Gateway public hỗ trợ các luồng outbound IPv4 được private host khởi tạo; không cung cấp inbound public port forwarding tùy ý.

### Bài 5 — NAT có phải firewall allowlist?

Một app instance chỉ cho outbound TCP/443 tới `0.0.0.0/0`, đi qua NAT. Liệu nó đã hạn chế destination tới approved update repositories chưa?

*Đáp án:* chưa. Rule chỉ giới hạn port, không giới hạn domain/đích. Cần approved proxy/firewall/endpoint policy và kiểm tra bypass.

### Bài 6 — Local route

Management route table chỉ có `10.42.0.0/16 → local`. Nó có tự ngăn management kết nối sang private subnet `10.42.20.0/24` không?

*Đáp án:* không. Local route cung cấp đường nội VPC; SG/NACL/firewall và workload policies quyết định ALLOW/DENY.

### Bài 7 — SG union

App gắn `sg-restricted` chỉ cho edge SG và `sg-legacy` cho TCP/8443 từ cả VPC. Kết quả effective permission có còn restricted không?

*Đáp án:* không. Security group rules cộng hợp; `sg-legacy` mở thêm nguồn ngoài intended edge.

### Bài 8 — Default SG

Kỹ sư chỉ kiểm tra `sg-app`, nhưng instance còn attach default SG. Có thể kết luận effective rules là những gì `sg-app` cho phép không?

*Đáp án:* không. Phải xem **tất cả SGs gắn vào ENI** và các ingress/egress rules có hiệu lực.

### Bài 9 — NACL stateless

Client dùng source TCP port 51000 tới app TCP/8443. Vì sao NACL chỉ allow destination port 8443 ở chiều đến có thể làm phiên TCP thất bại?

*Gợi ý:* return traffic dùng destination port 51000; NACL stateless cần quy tắc hai chiều phù hợp, khác SG stateful.

### Bài 10 — Security group không thay application authorization

Edge có thể gọi app TCP/8443. Nếu edge bị chiếm và dùng bearer token sai, app có tự được quyền cho operation admin không?

*Đáp án:* không. Network ALLOW chỉ mở kênh; app vẫn cần kiểm tra user/service identity, authorization và token/session policy.

### Bài 11 — Quản trị không public SSH

Management subnet không Internet route nhưng cần managed session agent. Những cấu phần phải có để agent kết nối service mà không mở public IP?

*Gợi ý:* IAM role, agent, private endpoints/route/DNS, endpoint SG, time sync, service compatibility, session permissions và audit, tùy nền tảng.

### Bài 12 — Test IAM negative

Một admin không có quyền vẫn truy cập được app qua VPN. Có thể kết luận quyền quản trị được enforce vì tunnel TLS/mTLS đang mã hóa không?

*Đáp án:* không. VPN/mTLS network authentication khác IAM/app authorization; phải kiểm approved vs unapproved identities.

### Bài 13 — Route association

Đã tạo route table private nhưng chưa associate với private subnet. Subnet sẽ dùng gì?

*Đáp án:* thường dùng **main route table** của VPC trong AWS cho tới khi có association rõ. Phải kiểm effective association.

### Bài 14 — Private endpoints

Một VPC interface endpoint cho Secrets Manager đã tồn tại nhưng instance IAM role không được phép đọc secret. Có thể request thành công chỉ vì TCP/443 reachable không?

*Đáp án:* không. Network reachability không thay IAM, endpoint/resource policy và application authorization.

### Bài 15 — IPv6

Instance không có public IPv4, nhưng nhận IPv6 globally routable, subnet `::/0 → IGW`, SG IPv6 mở TCP/22 từ `::/0`. Nó còn được coi là management-private theo intent không?

*Đáp án:* không. Có đường public IPv6 vào port quản trị nếu các điều kiện hiệu lực; phải đóng đường/rules theo policy.

### Bài 16 — Multi-AZ NAT

App ở AZ B đi ra Internet qua NAT ở AZ A. Khi NAT-A hỏng, app B có thể vẫn xử lý nội bộ nhưng mất egress. Nên điều chỉnh gì?

*Gợi ý:* route private B tới NAT-B tại AZ B khi requirement có egress và budget/architecture phù hợp; kiểm các dependency khác và test failover.

### Bài 17 — Flow logs

Flow Logs ghi `ACCEPT` cho một TCP connection. Có thể kết luận HTTP request trả 200 hoặc dữ liệu đã được server ghi không?

*Đáp án:* không. Flow-level action khác TLS/application status; cần app/access logs và client result.

### Bài 18 — No-data

Dashboard không có `REJECT` logs trong 24 giờ nhưng log pipeline ngừng từ hôm qua. Có thể coi negative tests đã PASS không?

*Đáp án:* không. Phải xác nhận collector health/capture coverage và ghi `UNKNOWN/INCONCLUSIVE`.

### Bài 19 — Port timeout

Unapproved source không kết nối được TCP/8443, nhưng target instance đã tắt. Có thể ghi firewall deny PASS không?

*Đáp án:* không. Cần positive control từ allowed source đến target healthy và flow/PEP evidence.

### Bài 20 — Public LB

Terraform lab chỉ tạo subnet, routes, NAT và SG; không tạo load balancer/instances. Một báo cáo ghi "HTTPS Internet→app PASS" có hợp lệ không?

*Đáp án:* không. Chưa có endpoint/listener; có thể ghi **configuration verified, runtime tests NOT_RUN**.

### Bài 21 — VPC Flow Logs và bảo mật dữ liệu

Logs có source IP, device details và timestamps. Có nên đưa raw logs vào public GitHub repo để minh họa không?

*Đáp án:* không. Cần redaction, access control, retention và chỉ dùng synthetic examples cho tài liệu công khai.

### Bài 22 — IaC nhầm account

`terraform plan` cho biết sẽ delete một VPC chưa từng được nhóm lab tạo. Hành động đúng?

*Đáp án:* **STOP**, kiểm AWS account/role, region, backend/workspace, resource ownership và state history. Không apply/destroy trước khi giải quyết.

### Bài 23 — Cost của lab không có VM

Đã xóa toàn bộ test EC2 nhưng NAT Gateway và Elastic IP vẫn tồn tại. Vì sao hóa đơn có thể tiếp tục tăng?

*Gợi ý:* NAT Gateway và public IPv4/EIP allocations có thể tính phí theo resources/time/usage dù không có VM; cần cleanup có review.

### Bài 24 — Chuyển sang Azure/GCP

Có thể copy nguyên AWS route table pattern `public-subnet → IGW` sang GCP và coi semantics giống nhau không?

*Đáp án:* không. Cloud native routing, subnet scope và firewall constructs khác; cần map **security intent** sang resource semantics của cloud đó.

### Bài 25 — Thiết kế tổng hợp

Bạn phải xây sandbox có **Internet-facing HTTPS service, app private, management restricted, hai AZ, IPv6 nếu được cấp phép, logging và cloud-native session access**. Hãy trình bày:

- CIDR plan và non-overlap/IPAM considerations.
- Mỗi subnet route tables, IGW/NAT/private endpoints/failover.
- Security group/host firewall policies cho **4 luồng ALLOW và 6 luồng DENY**.
- Management IAM/SSO/MFA, session recording và break-glass.
- Positive/negative tests có source/target/PEP/evidence, gồm IPv6.
- Chi phí NAT/endpoint/logging, DR/cleanup và `NOT_RUN` states.

*Gợi ý:* Internet→edge443, edge→app8443, authorized admin→management/private app, private app→approved service là các đường ALLOW có điều kiện; Internet→private, Internet→management, non-edge→app, public→management, unapproved app→DB và IPv6 direct management là các DENY. Đặt egress allowlist ở enforcement phù hợp; đừng coi NAT là chặn destination. Chỉ tuyên bố kết quả sau khi có endpoints và kiểm thật.

## 31. Checklist cuối lab

### 31.1. Chuẩn bị và quyền hạn

- [ ] Account/project là sandbox riêng được phê duyệt; biết đúng **account, region, IAM role và Terraform workspace/backend**.
- [ ] Có owner của tài nguyên, người phê duyệt apply/destroy, budget, time window và liên hệ hỗ trợ.
- [ ] Không sử dụng static access keys trong HCL/Git/logs; dùng identity ngắn hạn theo policy.
- [ ] Không triển khai workload thật, database chứa PII hoặc Internet-facing admin tools trong lab không được duyệt.
- [ ] Đã review NAT/public IPv4/EIP, endpoints, logs, LB/VM **đều có thể phát sinh chi phí**.
- [ ] Có kế hoạch cleanup, xác minh tài nguyên khác không dùng chung state.

### 31.2. Thiết kế mạng và CIDR

- [ ] VPC CIDR rõ ràng; không chồng với on-prem/VPN/peering hoặc reserve tương lai.
- [ ] Public `10.42.10.0/24`, private `10.42.20.0/24`, management `10.42.30.0/24` không overlap.
- [ ] CIDR/usable IP capacity xét cloud reservations, load balancer, NAT và interface endpoints.
- [ ] Subnets nằm đúng AZ/region đã duyệt; multi-AZ nếu có phải có route design riêng.
- [ ] Public/default routes tới **IGW** chỉ ở vùng được phép.
- [ ] Private `0/0` tới **NAT** hoặc không có default route nếu egress không được phép.
- [ ] Management **không có default public route** trong baseline.
- [ ] Ba subnets có route table **explicit associations**, không vô tình phụ thuộc main RT.
- [ ] Đã hiểu **VPC-local route không chặn lateral movement**.
- [ ] Public subnet không auto-assign public IPv4 cho mọi instances.
- [ ] Không có IPv6 allocation/`::/0` ngoài ý định; IPv6 rules được review riêng khi bật.

### 31.3. Firewall, identity và data security

- [ ] Edge SG chỉ cho inbound HTTPS cần thiết; không mở SSH/RDP public.
- [ ] App SG chỉ cho port ứng dụng từ approved edge identity/SG.
- [ ] App không gắn SG legacy/default có allow rộng ngoài intended trust zone.
- [ ] Management SG có effective deny mặc định; không gắn extra SG mở Internet/admin.
- [ ] Mọi rule có **owner, business justification và review/TTL** khi là ngoại lệ.
- [ ] SG stateful behavior và NACL stateless return ports được hiểu chính xác.
- [ ] NAT không được dùng như egress allowlist; kiểm outbound destination policy nếu có yêu cầu.
- [ ] Database/service-to-service access theo identity/source/port, có authorization riêng.
- [ ] Host firewall, patching, TLS, secret management và workload identity được đánh giá.
- [ ] CNI/NetworkPolicy, service mesh mTLS và Pod/ENI flows được kiểm thêm nếu có Kubernetes.

### 31.4. Management plane

- [ ] Không có public IP hoặc `0.0.0.0/0`/`::/0` inbound quản trị trái chính sách.
- [ ] Đã chọn một cơ chế có danh tính: **managed sessions, VPN, ZTNA hoặc private bastion** khi cần.
- [ ] Có IAM/SSO/MFA, PAM/JIT, scope targets và logging phù hợp.
- [ ] Nếu quản trị qua private endpoints, có đủ **endpoint DNS, endpoint SG, IAM, agent và service reachability**.
- [ ] Không đánh đồng việc có access path với quyền thao tác trên mọi resource.
- [ ] Có break-glass/OOB plan và cách thu hồi role/session được kiểm tra.
- [ ] Management subnet không tự động egress Internet chỉ để cài package.

### 31.5. Kiểm thử cấu hình và vận hành

- [ ] Terraform format/validation/plan được review từ đúng workspace; plan không sửa tài nguyên ngoài scope.
- [ ] Sau apply, effective routes, SG attachments, NAT/IGW state và subnets được kiểm qua cloud API.
- [ ] Đã tách **configuration VERIFIED** khỏi **application traffic NOT_RUN** nếu chưa có workloads.
- [ ] Positive tests có target khỏe, đúng source identity và TLS/application verification.
- [ ] Negative tests có PEP evidence và positive control, không suy DENY chỉ từ timeout.
- [ ] Có ít nhất một kiểm tra direct-to-private, direct-to-management, non-edge-to-app và IPv6 bypass khi áp dụng.
- [ ] Flow logs và control-plane audit có dữ liệu, time sync UTC, source/target/rule details cần thiết.
- [ ] `UNKNOWN/INCONCLUSIVE/NOT_RUN` được hiển thị đúng khi monitoring hoặc endpoint thiếu.
- [ ] Test traffic nằm trong scope, có rate limit và không quét cả VPC/production.
- [ ] Các lỗi được chẩn đoán theo **DNS → route → firewall → listener/TLS → app/identity**, không nới mọi quyền.

### 31.6. Resilience, evidence và cleanup

- [ ] Đã ghi **single-AZ limitation** của lab, không tuyên bố HA production.
- [ ] Khi mở multi-AZ, route NAT và dependencies của mỗi AZ đã được kiểm.
- [ ] NAT/control plane/management endpoint outage có runbook hoặc tabletop.
- [ ] Logs và test outputs được lưu restricted, không có keys/tokens/PII trong báo cáo chung.
- [ ] Evidence inventory ghi UTC, tool/provider version, asset IDs, config revision và kết quả test.
- [ ] Có reviewer độc lập hoặc peer review cho security outcome theo scope.
- [ ] Destroy plan được duyệt, state không chứa tài nguyên ngoài lab.
- [ ] Sau cleanup, xác minh không còn billable NAT Gateway/EIP/endpoints/VM/LB ngoài ý định.
- [ ] Retained evidence/state được bảo vệ theo retention/legal hold, không xóa nếu còn nghĩa vụ.

### 31.7. Những dấu hiệu cần dừng trước khi công bố kết quả

Không công bố lab đạt security khi:

1. **Chỉ tạo ba subnets** nhưng chưa kiểm route associations, SG effective policy.
2. Public, private và management đều attach cùng một security group allow-all.
3. Management bị buộc mở public SSH do session agent chưa có private endpoint.
4. NAT route được xem là bằng chứng mọi outbound destinations bị kiểm soát.
5. IPv6 hoặc interface phụ tạo ingress ngoài intended trust boundary.
6. Negative test timeout do target down, không có positive control hoặc PEP decision log.
7. File IaC/state/report chứa cloud credentials hoặc private key.
8. Terraform workspace có shared production resources và destroy plan chưa được duyệt.

**Kết luận:** ba subnet chỉ là **khung địa chỉ và định tuyến**. Một kiến trúc mạng có phòng vệ phải kết hợp **đúng CIDR, đúng route, đúng security groups/firewall, quản trị theo danh tính, kiểm soát outbound, observability và kiểm thử positive/negative có bằng chứng**. Public không có nghĩa mọi instance công khai; private không có nghĩa không thể bị truy cập ngang; management không có nghĩa an toàn nếu quyền truy cập rộng. Bản lab một AZ/Terraform trên đây cung cấp nền tảng để học và kiểm chứng cấu hình, còn các hành vi ứng dụng/SSM/HA cần **mở rộng có phê duyệt và đo thực tế** trước khi đánh giá cao hơn.

## 32. Tài liệu tham khảo và mở rộng

Những nguồn dưới đây cung cấp kiến thức nền và documentation để **đối chiếu trước khi triển khai trên phiên bản cloud/provider cụ thể**. Bản bài không khẳng định đã chạy Terraform, tạo subnet hoặc đo network production.

### 32.1. Địa chỉ IP, routing và segmentation

- [RFC 1918 — Address Allocation for Private Internets](https://www.rfc-editor.org/rfc/rfc1918): các dải IPv4 private.
- [RFC 4632 — Classless Inter-domain Routing (CIDR)](https://www.rfc-editor.org/rfc/rfc4632): địa chỉ/prefix và route aggregation.
- [RFC 8200 — Internet Protocol Version 6 (IPv6)](https://www.rfc-editor.org/rfc/rfc8200): IPv6 packet model và khái niệm địa chỉ.
- [NIST SP 800-41 Rev. 1 — Guidelines on Firewalls and Firewall Policy](https://csrc.nist.gov/pubs/sp/800/41/r1/final): thiết kế firewall policy và rule lifecycle.
- [NIST SP 800-207 — Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final): policy enforcement, identity và least privilege.
- [NIST SP 800-125B — Secure Virtual Network Configuration for Virtual Machine Protection](https://csrc.nist.gov/pubs/sp/800/125/b/final): cách tiếp cận bảo vệ các mạng ảo/VM.

### 32.2. AWS VPC và Terraform

- [AWS VPC — What is Amazon VPC?](https://docs.aws.amazon.com/vpc/latest/userguide/what-is-amazon-vpc.html): VPC, subnets và route concepts.
- [AWS VPC — Subnet CIDR blocks](https://docs.aws.amazon.com/vpc/latest/userguide/subnet-sizing.html): địa chỉ dùng được và reservations.
- [AWS VPC — Route tables](https://docs.aws.amazon.com/vpc/latest/userguide/VPC_Route_Tables.html): route associations, main/local/default routes.
- [AWS VPC — Internet Gateways](https://docs.aws.amazon.com/vpc/latest/userguide/VPC_Internet_Gateway.html): public IPv4/IPv6 connectivity.
- [AWS VPC — NAT Gateways](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-nat-gateway.html): NAT outbound, route behavior và availability.
- [AWS VPC — Security groups](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html): stateful allow rules và SG references.
- [AWS VPC — Network ACLs](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-network-acls.html): stateless subnet-level filtering.
- [AWS VPC — VPC Flow Logs](https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs.html): traffic visibility và limitations.
- [AWS VPC — Interface endpoints](https://docs.aws.amazon.com/vpc/latest/privatelink/create-interface-endpoint.html): private connectivity, SG và DNS.
- [AWS Systems Manager — Session Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager.html): managed sessions, prerequisites và audit.
- [Terraform AWS Provider documentation](https://registry.terraform.io/providers/hashicorp/aws/latest/docs): resource/provider semantics; đối chiếu với version đã pin.
- [Terraform — Plan](https://developer.hashicorp.com/terraform/cli/commands/plan): review proposed changes trước khi apply.
- [Terraform — State](https://developer.hashicorp.com/terraform/language/state): state ownership và bảo vệ thông tin nhạy cảm.

### 32.3. Application security, logging và incident readiness

- [Kubernetes — Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/): Pod traffic policies và CNI support.
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): secure transport và peer authentication.
- [NIST SP 800-92 — Guide to Computer Security Log Management](https://csrc.nist.gov/pubs/sp/800/92/final): log retention, access và analysis.
- [NIST SP 800-61 Rev. 3 — Incident Response Recommendations](https://csrc.nist.gov/pubs/sp/800/61/r3/final): incident handling và recovery.
- [OWASP — Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html): TLS verification và cấu hình bảo mật.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): bảo vệ event logs và tránh ghi dữ liệu bí mật.

