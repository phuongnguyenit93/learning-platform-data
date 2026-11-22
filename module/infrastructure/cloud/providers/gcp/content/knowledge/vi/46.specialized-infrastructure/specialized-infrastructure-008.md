# Google Cloud VMware Engine và mô hình vận hành

Một doanh nghiệp có hàng trăm máy ảo VMware có thể muốn chuyển khỏi trung tâm dữ liệu riêng nhưng chưa sẵn sàng sửa toàn bộ ứng dụng sang container hoặc dịch vụ cloud-native. **Google Cloud VMware Engine** giải quyết một phần nhu cầu đó: cung cấp môi trường VMware chạy trên phần cứng chuyên dụng ở Google Cloud, giữ các khái niệm vSphere, vCenter, vSAN và NSX quen thuộc. Tuy nhiên, đưa VM lên Google Cloud **không đồng nghĩa Google tự vận hành hệ điều hành khách, database và ứng dụng**.

Bài học thuộc chương **Hạ tầng chuyên biệt** trong module **CLOUD_PROVIDERS_GCP**. Module giới thiệu Google Cloud từ tổ chức project, IAM, VPC tới Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu; qua các tình huống triển khai, người học lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí. Với VMware Engine, trọng tâm là **chọn đúng mô hình trách nhiệm**, thiết kế kết nối và vận hành một private cloud VMware ổn định trong hệ sinh thái Google Cloud.

Sau bài học, bạn có thể:

- Phân biệt Google Cloud-managed VMware Engine và VMware solution on Google Cloud theo mô hình Bring Your Own License (BYOL).
- Mô tả ESXi, vCenter, vSAN, NSX, HCX, node, cluster, private cloud và VMware Engine network.
- Lựa chọn standard, single-node hoặc stretched private cloud theo mục tiêu HA, lab và chi phí.
- Thiết kế đường mạng giữa on-premises, VPC và VMware Engine mà không gây trùng CIDR, lỗi DNS hoặc route.
- Lập kế hoạch chuyển VM bằng VMware HCX hoặc các công cụ thay thế, xây dựng migration waves và rollback.
- Phân quyền đúng giữa Google Cloud IAM, VMware vCenter RBAC, NSX policy và quyền trong guest OS.
- Vận hành Day 0/Day 1/Day 2: provisioning, capacity, autoscale, lifecycle update, backup/DR, monitoring và FinOps.
- Biết khi nào nên giữ VM trên VMware Engine và khi nào nên hiện đại hóa sang Compute Engine, GKE hoặc Cloud Run.

**Phạm vi kỹ thuật:** nội dung mô tả mô hình và tính năng công khai hiện hành; phiên bản VMware, loại node, location, giá, giới hạn quota và điều kiện cấp phép có thể thay đổi. Hãy xác nhận tính sẵn có trên Google Cloud Console và tài liệu chính thức của location, hợp đồng và mô hình triển khai đã chọn.

## 1. VMware Engine là gì và không phải là gì?

VMware Engine cho phép chạy workload VMware trên **dedicated bare-metal nodes** tại các location của Google Cloud. Doanh nghiệp tiếp tục quản lý nhiều thao tác VM bằng vCenter/VMware tools, trong khi tài nguyên hạ tầng vật lý được Google Cloud cung cấp.

~~~mermaid
flowchart TD
    USER["Người quản trị VMware"]
    GC["Google Cloud console / VMware Engine API"]
    VC["vCenter Server"]
    NSX["NSX Manager"]
    CLUSTER["vSphere Cluster"]
    VM["VM ứng dụng và dữ liệu"]

    USER --> GC
    USER --> VC
    USER --> NSX
    GC --> CLUSTER
    VC --> CLUSTER
    NSX --> CLUSTER
    CLUSTER --> VM
~~~

Nên hiểu theo hai lớp:

- **Lớp tài nguyên/hạ tầng:** private cloud, node, cluster, VMware Engine network, kết nối với Google VPC và vận hành phần cứng.
- **Lớp workload:** VM, guest OS, application, database, user access, backup, antivirus, hiệu năng và dữ liệu nghiệp vụ.

VMware Engine **không phải**:

- Compute Engine VM thông thường: bạn không tạo một instance Compute Engine tương đương rồi quản lý nó bằng vCenter.
- Một Kubernetes cluster: GKE phù hợp cho container, còn VMware Engine giữ mô hình hạ tầng ảo hóa VMware.
- Giải pháp lift-and-shift tự động bảo đảm zero downtime: migration cần mạng, đồng bộ dữ liệu, tương thích phần mềm và kiểm thử.
- Một dịch vụ database được quản lý: PostgreSQL/SQL Server cài trong guest VM vẫn do nhóm vận hành workload chịu trách nhiệm.
- Một bản sao lưu mặc định cho mọi VM: cần tự thiết kế bảo vệ dữ liệu và kiểm tra restore.

### Khi nào có giá trị?

VMware Engine thường phù hợp khi:

1. Đang có nhiều VM VMware và cần rút khỏi datacenter trong một thời hạn ngắn.
2. Workload gắn với VM, driver, hệ điều hành hoặc sản phẩm chưa dễ refactor.
3. Muốn dùng tiếp VMware operational tooling, chính sách VM hoặc kỹ năng của đội vSphere.
4. Cần mở rộng hoặc dựng môi trường DR nhưng không muốn mua thêm máy chủ vật lý.
5. Có kế hoạch hiện đại hóa theo từng đợt, để workload cũ tạm chạy trong private cloud và workload mới dùng dịch vụ native.

## 2. Hai mô hình vận hành VMware trên Google Cloud

Tài liệu hiện hành của Google Cloud trình bày **hai lựa chọn có mô hình trách nhiệm khác nhau**. Không được đánh đồng chúng chỉ vì cùng dùng VMware trên Google Cloud.

| Tiêu chí | Google Cloud-managed VMware Engine | VMware solution on Google Cloud |
|---|---|---|
| Mục tiêu | Tiêu thụ private cloud VMware do Google quản lý | Tự quản lý VMware Cloud Foundation trên bare metal Google |
| License VMware | Được tích hợp vào dịch vụ theo model phù hợp | Bring Your Own License (BYOL) VCF |
| Provisioning VMware stack | Google triển khai/cấu hình stack được quản lý | Khách hàng triển khai và cấu hình VCF |
| Patching VMware ESXi/vCenter/NSX | Google quản vòng đời theo dịch vụ managed | Khách hàng lên lịch, kiểm thử và thực thi |
| Phần cứng/datacenter | Google Cloud | Google Cloud |
| Công cụ quản trị chủ đạo | Google Cloud console/API và vCenter/NSX | VMware SDDC Manager và vCenter cùng Google Cloud controls |
| Quyền quản trị VMware stack | Có giới hạn và cơ chế elevation khi cần | Khách hàng quản lý quyền cao hơn theo BYOL |
| Guest VM/OS/database/app | Khách hàng | Khách hàng |
| Backup workload VM | Khách hàng | Khách hàng |
| Độ phức tạp đội vận hành | Ít vận hành VMware stack hơn | Cần đội VMware platform và license management chuyên sâu |

Trong các mục nói về **managed private cloud** bên dưới, cụm "Google quản lý" chỉ áp dụng cho những thành phần thuộc ranh giới dịch vụ đã công bố. Không suy ra Google chịu trách nhiệm cài bản vá Windows/Linux, update SQL Server hoặc restore dữ liệu trong VM.

### 2.1. Chọn mô hình nào?

Chọn Google Cloud-managed khi:

- Ưu tiên triển khai private cloud nhanh và giảm công việc lifecycle VMware.
- Muốn sử dụng mô hình dịch vụ có giấy phép VMware tích hợp theo điều kiện hợp đồng.
- Có đội quản trị ứng dụng/VM nhưng không muốn tự vận hành toàn bộ VMware SDDC.

Cân nhắc VMware solution BYOL khi:

- Tổ chức có quyền sử dụng và chiến lược VCF license phù hợp.
- Cần kiểm soát sâu phiên bản/cấu hình và lịch update VMware stack.
- Có đội SDDC chịu trách nhiệm vận hành vSphere, NSX, vSAN và lifecycle.

**Không có một đáp án đúng cho mọi doanh nghiệp.** Cần so sánh quyền điều khiển, tính tương thích, license, tổng chi phí, phân chia trách nhiệm và mục tiêu migration.

## 3. Các thành phần VMware cốt lõi trong managed private cloud

Một private cloud VMware Engine bao gồm các thành phần:

| Thành phần | Vai trò | Người quản trị workload cần hiểu |
|---|---|---|
| VMware ESXi | Hypervisor trên dedicated bare-metal node | Host, VM placement, resource pools, khả năng tương thích guest |
| VMware vCenter Server | Quản lý inventory VM, clusters, permissions và vSphere HA/DRS | Tạo VM, template, resource pool, cluster monitoring |
| VMware vSAN | Software-defined storage sử dụng disk trên cluster | Capacity, storage policy, fault tolerance và rebuild |
| VMware NSX | Virtual networking, segments, gateway, firewall/security policy | VLAN/segment, routes, microsegmentation và NAT |
| VMware HCX | Hỗ trợ migration, workload mobility và mở rộng mạng trong các trường hợp phù hợp | Migration method, service mesh, network extension, cutover |
| VMware Engine network | Mạng kết nối private clouds với VPC và mạng bên ngoài | Peering, route exchange và DNS |
| Google Cloud console/API | Quản lý private cloud resources, nodes, quota, service operations | Provisioning, scaling, service-level changes, auditing |

~~~mermaid
flowchart TB
    subgraph PC["Managed VMware Engine private cloud"]
      VC["vCenter"]
      NSX["NSX Manager"]
      HCX["HCX Cloud Manager"]
      subgraph VSP["vSphere cluster: dedicated nodes"]
        E1["ESXi Node 1"]
        E2["ESXi Node 2"]
        E3["ESXi Node 3"]
      end
      SAN["vSAN datastore / policy"]
      SEG["NSX segments: application VMs"]
      VC --> VSP
      NSX --> SEG
      HCX --> VSP
      VSP --> SAN
      VSP --> SEG
    end
    SEG --> APP["Windows/Linux guest VM"]
~~~

### 3.1. Node, cluster, private cloud

- **Node:** đơn vị phần cứng bare-metal chuyên dụng, cung cấp CPU, RAM và khả năng storage theo node type.
- **Cluster:** một nhóm ESXi hosts được quản lý chung qua vCenter, có tài nguyên và storage policy.
- **Private cloud:** một môi trường VMware cô lập, có management domain và có thể chứa nhiều clusters.
- **VM workload:** máy ảo nghiệp vụ của khách hàng chạy trên cluster, không phải Google-native Compute Engine instance.

Các node trong cùng một cluster phải tương thích loại node theo giới hạn dịch vụ. Khả năng hỗ trợ mixed node families trong cùng private cloud không có nghĩa tự do trộn mọi node type trong cùng cluster.

## 4. Standard, single-node và stretched private cloud

Việc chọn private cloud type ảnh hưởng trực tiếp tới availability, capacity và chi phí.

| Loại | Kiến trúc | Phù hợp | Lưu ý |
|---|---|---|---|
| Standard | Cluster VMware chạy trong một zone của region | Production cần HA ở mức host, migration và vận hành thông thường | Có thể cần DR riêng cho zone/region |
| Single-node | Một node riêng cho private cloud | Proof of concept, lab, thử restore hoặc upgrade | Không có vSphere HA/DRS đầy đủ, không đủ node cho vSAN redundancy, không được bao phủ SLA production như cluster từ 3 node |
| Stretched | Các node được phân bố giữa hai data zones và một witness zone cùng region | Workload cần khả năng chịu lỗi zone ở mức VMware cluster | Tối thiểu 3+3 data nodes, quota/chi phí cao, không thay thế cross-region DR |

### 4.1. Standard private cloud

Với standard cluster, tài liệu khuyến nghị **ít nhất ba nodes** cho workload production. vSphere HA có thể tái khởi động VM khi một host hỏng nếu cluster còn khả năng đáp ứng; vSAN bảo vệ dữ liệu theo storage policy. Đây là HA theo phạm vi thiết kế cluster, **không bảo đảm** ứng dụng không bị gián đoạn.

### 4.2. Single-node private cloud

Single-node phù hợp PoC, nhưng không nên dùng cho workload quan trọng: vSAN policy có thể dùng FTT=0, một node hỏng có thể làm mất dữ liệu không được sao lưu. Điều kiện tồn tại, cập nhật, SLA và chuyển đổi sang cluster lớn có thể thay đổi theo chương trình/sản phẩm; xác minh hướng dẫn sản phẩm hiện hành trước khi lập lịch lab.

Không coi single-node là biện pháp cắt giảm chi phí production an toàn chỉ vì chạy được VM.

### 4.3. Stretched private cloud

Stretched cluster phân bổ data nodes giữa hai zones và dùng witness zone riêng trong **cùng region**. Đây là cấu trúc nhằm chịu lỗi zone, không phải multi-region disaster recovery.

~~~mermaid
flowchart LR
    A["Zone A: 3 ESXi nodes"]
    W["Witness zone"]
    B["Zone B: 3 ESXi nodes"]
    A <-->|"vSAN stretched traffic"| B
    A --> W
    B --> W
~~~

- Cấu hình tối thiểu minh họa: 3+3 data nodes.
- Cần chọn region có hỗ trợ stretched private cloud/node type đã chọn.
- Stretched được thiết kế để chịu một zone failure trong mô hình hỗ trợ.
- Không giả định có thể chuyển standard private cloud đã tạo sang stretched sau này; loại private cloud cần được chọn đúng từ ban đầu.
- Vẫn cần backup và kịch bản mất cả region, dữ liệu bị xóa nhầm hoặc ransomware.

## 5. Kiến trúc tổng thể từ on-premises đến Google Cloud

~~~mermaid
flowchart LR
    ON["On-prem VMware vCenter + VMs"]
    VPN["Cloud VPN / Cloud Interconnect"]
    VPC["Google Cloud VPC"]
    VEN["Standard VMware Engine Network"]
    PC["VMware Engine private cloud"]
    NAT["Google-native services: Cloud SQL, Storage, Cloud Run"]
    ON <-->|"Hybrid connectivity"| VPN
    VPN <--> VPC
    VPC <-->|"VPC Network Peering"| VEN
    VEN --> PC
    VPC --> NAT
~~~

Môi trường gồm **ít nhất ba miền quản trị**:

1. On-premises: ESXi/vCenter cũ và các hệ thống chưa chuyển.
2. Google Cloud: VPC, Cloud VPN/Interconnect, IAM, Cloud DNS và các dịch vụ native.
3. VMware Engine private cloud: management network, NSX segments, vCenter, vSAN và guest VMs.

Phải xác định **data path** và **management path** riêng, đồng thời kiểm tra cách DNS/route phục vụ cả hai. Management appliance không nên mở public tùy tiện để quản trị vCenter.

## 6. Mạng VMware Engine: Standard và Legacy

**Standard VMware Engine Network** là mô hình mạng hiện hành cho các project mới. Nó là tài nguyên mạng dùng để kết nối một hoặc nhiều private clouds với Google Cloud VPC hoặc on-premises, và dùng **VPC Network Peering** để kết nối với VPC.

**Legacy VMware Engine Network** là loại regional network của các project cũ (trước mốc hỗ trợ thay đổi năm 2023), dùng cách kết nối private services access khác với standard. Dự án mới không nên thiết kế theo Legacy trừ khi đang duy trì môi trường cũ cụ thể.

| Khía cạnh | Standard network | Legacy network |
|---|---|---|
| Phạm vi | Global VMware Engine network | Regional VMware Engine network |
| Kết nối VPC | VPC Network Peering | Private services access/private connection |
| Tính phù hợp | Môi trường mới | Môi trường cũ còn tồn tại |
| Quản lý | VMware Engine networks, peerings, DNS bindings | Legacy connection và DNS/route tương ứng |
| Chuyển traffic | Kiểm tra route/peering và return path | Kiểm tra PSA/route import-export |

**Không trộn lệnh hoặc giả định Legacy với Standard**: một private connection Legacy không tương đương VPC peering cho Standard.

### 6.1. VPC peering không phải transit router

VPC Network Peering không tự động cho phép truyền tuyến qua nhiều peering nối tiếp tùy ý. Khi VMware Engine network peer với VPC, không thể mặc định rằng nó sẽ nhìn thấy tất cả VPC khác vốn peer với VPC đó.

Nếu cần kết nối cloud services ở nhiều VPC, Shared VPC, private services access hoặc on-prem networks, phải thiết kế route, peering, custom routes và các trường hợp transitivity theo tài liệu từng mạng.

## 7. Quy hoạch IP, VLAN/NSX segment và DNS

### 7.1. Không được trùng CIDR

Trước khi tạo private cloud, lập bảng IP:

| Phạm vi | CIDR minh họa | Mục đích |
|---|---|---|
| On-prem workload | 10.20.0.0/16 | Guest VMs nguồn |
| GCP VPC | 10.40.0.0/16 | Cloud-native services |
| VMware management | 10.80.0.0/22 | vCenter, NSX, ESXi, vSAN management |
| VMware workload segment | 10.90.0.0/24 | VMs sau migrate |
| HCX network nếu cần | Dải không trùng, theo tính năng | Migration/interconnect services |

Các CIDR trên **chỉ là minh họa**. Management CIDR được dùng để tạo nhiều subnet phục vụ vSphere/vSAN, không phải dải IP chung để cấp tự do cho application VMs. Tài liệu private cloud managed yêu cầu dải quản lý có prefix từ /24 đến /20; phải kiểm tra thiết kế cụ thể và các dải IP bị cấm.

Không trùng với VPC, on-prem, services CIDR, VM segments, private DNS/management hoặc các network sẽ kết nối sau này.

### 7.2. Network segments và NSX

NSX cung cấp segments, firewall, gateways và khả năng network virtualization cho VMs. Với ứng dụng ba tầng, có thể tạo riêng:

- Web segment: chỉ nhận HTTPS từ proxy/load balancer cần thiết.
- App segment: chỉ nhận traffic từ web/worker.
- DB segment: chỉ nhận port PostgreSQL/SQL Server từ app.
- Management segment: giới hạn theo mạng quản trị, không dùng chung với workload.

Ví dụ policy:

| Source | Destination | Port | Trạng thái |
|---|---|---:|---|
| User/network ingress đã kiểm soát | Web | 443 | Allow |
| Web segment | App segment | 8080 | Allow |
| App segment | DB segment | 5432 | Allow |
| Internet bất kỳ | vCenter/NSX management | Any | Deny |
| DB segment | Internet bất kỳ | Any | Deny mặc định, mở theo yêu cầu |

Không đặt mọi VM trong cùng một flat L2 network và trông chờ private cloud tự tạo microsegmentation.

### 7.3. DNS

Private cloud có management DNS zone cho vCenter, NSX và HCX. Standard VMware Engine network có cơ chế DNS bindings với VPC; on-prem có thể cần conditional forwarding để resolve management hostnames.

Kiểm tra:

1. vCenter FQDN từ workstation quản trị.
2. NSX Manager/HCX endpoints trong private network.
3. Guest VM hostnames sang Google Cloud services.
4. Reverse DNS, domain controller, NTP và certificate hostname.
5. DNS failover và cache TTL nếu network đổi.

Không chỉ thử ping theo IP: nếu DNS khác nhưng certificate gắn FQDN cũ, đăng nhập vCenter hoặc HCX có thể lỗi.

## 8. Kết nối hybrid qua Cloud VPN hoặc Cloud Interconnect

Để di chuyển VMware VMs từ on-prem đến managed VMware Engine bằng HCX, phải thiết lập đường kết nối phù hợp. Google Cloud hướng dẫn dùng **Cloud VPN hoặc Cloud Interconnect** làm lớp hybrid connectivity.

Cần kiểm tra:

- CIDR on-prem/VPC/VMware Engine không chồng lấn.
- BGP route advertisements và return routes đúng.
- Có đường mạng tới HCX, vCenter, vMotion và management services theo port list được hỗ trợ.
- DNS, NTP, MTU/MSS, firewall hai chiều và TLS/certificate.
- Redundancy theo RTO/RPO mục tiêu.
- Băng thông đủ cho migration waves và dữ liệu thay đổi trong khi VM còn chạy.

### 8.1. Bandwidth và thời gian migrate

Ví dụ cần chuyển 4 TiB dữ liệu, đường truyền cho migration có **effective throughput** 500 Mbit/s, không tính dữ liệu đổi trong quá trình sao chép:

\[
4\ \text{TiB} = 4 \times 1024^4 \times 8\ \text{bit}
\]

\[
T_{\text{lý tưởng}} \approx \frac{4 \times 1024^4 \times 8}{500.000.000}
\approx 70.369\ \text{giây}
\]

Khoảng 19,5 giờ chỉ là **ước tính lý tưởng**. Thực tế còn có delta changes, nén/overhead, retransmission, network contention, storage I/O và thời gian cutover cuối.

Không dùng số liệu line rate của Interconnect làm tốc độ copy cam kết. Chạy throughput test và đánh giá rate of change của dữ liệu nguồn trước khi quyết định migration window.

## 9. VMware HCX và các phương thức di chuyển VM

VMware HCX hỗ trợ migration giữa môi trường VMware nguồn và private cloud đích. Managed private cloud có HCX Cloud Manager được triển khai cùng VMware stack theo mô hình dịch vụ.

Các phương thức thường cần cân nhắc:

| Phương án | Đặc điểm | Dùng khi |
|---|---|---|
| HCX migration | Tích hợp orchestration và mobility cho VMs | Nhiều VM cần chuyển theo waves, có kết nối hỗ trợ |
| HCX network extension | Có thể duy trì subnet/L2 trong giai đoạn chuyển tiếp | Ứng dụng khó đổi IP ngắn hạn |
| Backup/restore | Backup ở nguồn rồi restore vào VMware Engine | Giải pháp bảo vệ dữ liệu đã hỗ trợ đích |
| VMware PowerCLI | Tự động hóa tác vụ liên quan vSphere/vCenter | Có tooling/kiểm soát runbook riêng |
| ISO/template import | Tạo VM mới từ template hoặc media | Rebuild thay vì di chuyển VM nguyên trạng |
| NSX Layer 2 VPN | Mở rộng L2 phục vụ migration trong tình huống hỗ trợ | Cần network extension có kiểm soát |

HCX có nhiều khả năng mobility nhưng **không có một mode phù hợp mọi VM**. Chọn phương thức theo guest OS, vSphere compatibility, storage, thay đổi dữ liệu, bandwidth và downtime tolerance.

### 9.1. Những thứ phải khảo sát trước HCX

- Danh sách VM, CPU/RAM/disk và snapshot chain.
- vSphere/ESXi versions và compatibility matrix HCX.
- VMware Tools, guest OS, virtual hardware compatibility.
- Network mapping, VLAN, DHCP/static IP, DNS và firewall.
- Database transaction rate, disk I/O và delta change rate.
- License phụ thuộc MAC, hardware fingerprint hoặc IP.
- Backup và điểm phục hồi đã được kiểm chứng.
- VM có USB/PCI passthrough, physical device hoặc appliance hạn chế migration không.

Nếu ứng dụng có external database, đổi vị trí VM có thể làm tăng RTT với database. Phải kiểm tra **toàn bộ application dependency graph**, không chỉ migrate thành công guest VM.

## 10. Migration waves và cutover

Thực hiện migration theo waves giúp giảm blast radius:

| Wave | Workload | Mục tiêu |
|---|---|---|
| 0 | Một VM thử nghiệm, không chứa dữ liệu nhạy cảm | Kiểm tra HCX, DNS, network, monitoring |
| 1 | VM nội bộ không quan trọng | Kiểm tra quyền, backup/restore, rollback |
| 2 | Web/app stateless hoặc ít dữ liệu | Đánh giá performance, scaling |
| 3 | Ứng dụng cần database, nhiều integrations | Cutover theo runbook, data reconciliation |
| 4 | Workload quan trọng/được quản lý nghiêm | Go/No-Go và business sign-off |

### 10.1. Runbook cho một wave

1. Chốt inventory/owner, xác định RTO/RPO và downtime window.
2. Kiểm tra backup/recovery point, test restore nếu cần.
3. Xác minh HCX site pairing, route, DNS, IP plan, quotas và target capacity.
4. Chạy pilot migration với VM không quan trọng.
5. Kiểm tra ứng dụng trong target segment tách biệt, chặn side effects ngoài ý muốn.
6. Freeze/config change hoặc drain traffic theo loại workload.
7. Thực hiện final sync/cutover qua phương thức đã chọn.
8. Kiểm tra VM boot, guest service, latency, database consistency và business transaction.
9. Chuyển traffic/DNS, giám sát error rate/latency.
10. Xác nhận business sign-off; giữ source theo retention và rollback plan.

### 10.2. Tránh split-brain

Nếu source VM và target VM cùng chạy và cùng ghi vào shared database hoặc nhận message từ queue, có thể tạo dữ liệu trùng. Phải đảm bảo **một writer chính thức tại thời điểm cutover** và có fencing/traffic control.

Nếu target đã nhận dữ liệu mới, rollback về source cũ không đơn thuần là bật VM nguồn: cần reconciliation hoặc phương án forward-fix/replication ngược đã được kiểm chứng.

## 11. Mô hình trách nhiệm vận hành: ai làm gì?

### 11.1. Google Cloud-managed VMware Engine

| Hạng mục | Google Cloud chịu trách nhiệm chính | Khách hàng chịu trách nhiệm chính |
|---|---|---|
| Datacenter, nguồn điện, bare metal | Cung cấp và xử lý sự cố hạ tầng | Chọn location và capacity phù hợp |
| ESXi host lifecycle | Quản lý VMware stack được hỗ trợ | Phối hợp maintenance window, hiểu ảnh hưởng tới VMs |
| vCenter/NSX/HCX management appliances | Triển khai và quản lý phần thuộc dịch vụ | Cấu hình sử dụng, RBAC, network segment và tích hợp |
| vSAN cấu hình mặc định | Thiết lập nền tảng | Chọn/đổi workload storage policy và quản lý capacity |
| Private cloud resources/nodes | Provisioning service-level | Yêu cầu, quota, scale và cost ownership |
| Guest VM và OS | Không trực tiếp quản OS ứng dụng | OS hardening, security patches, anti-malware |
| Database trong VM | Không quản lý data engine | SQL backup, patch, replication, consistency |
| App/business transaction | Không | CI/CD, performance, availability và data integrity |
| Backup workload | Backup management components thuộc dịch vụ | Backup/restore customer workloads và test DR |
| IAM và guest network policy | Cung cấp các control/tính năng | Gán role, secret rotation, NSX/firewall rule, auditing |
| Compliance của ứng dụng | Hạ tầng theo cam kết dịch vụ | Data classification, retention và ứng dụng phù hợp chính sách |

**Google quản lý môi trường VMware không có nghĩa Google quản lý các VM ứng dụng.** Đây là lỗi hiểu nhầm thường dẫn đến thiếu backup, thiếu patch guest OS hoặc không có disaster recovery plan.

### 11.2. VMware solution trên bare metal theo BYOL

Ở mô hình VMware solution on Google Cloud, khách hàng còn phải:

- Cung cấp license VCF và theo dõi entitlement/renewal.
- Cài và cấu hình SDDC stack, vSphere, vSAN và NSX.
- Lên lịch patch/upgrade VMware software.
- Quản trị SDDC Manager, vCenter/NSX và cấu hình hệ thống.
- Lập phương án khôi phục management plane/VCF lifecycle.

Google Cloud vẫn quản lý hạ tầng vật lý và bare-metal/network infrastructure theo ranh giới dịch vụ. Cần xem tài liệu shared responsibility riêng của **BYOL model**, không dùng bảng managed service thay thế.

## 12. Quyền truy cập: IAM khác vCenter RBAC

Hai mô hình authorization tồn tại song song:

| Lớp | Hệ thống phân quyền | Ví dụ |
|---|---|---|
| Google Cloud resource control | Google Cloud IAM | Tạo private cloud, xem nodes, thao tác VMware Engine API |
| VMware management | vCenter Single Sign-On/RBAC | Tạo/sửa VM, vSphere inventory, resource pool |
| NSX network | NSX roles và firewall/security policy | Tạo segment, chỉnh gateway/firewall |
| Guest OS | AD/Linux user/sudo/SSH/RDP | Login Windows/Linux VM |
| Application data | Database/application authorization | Quyền SELECT/UPDATE, truy cập dữ liệu |

### 12.1. IAM trên project

Google Cloud cung cấp các predefined roles liên quan VMware Engine, ví dụ VMware Engine Service Viewer/Service Admin. Hãy cấp role phù hợp nhu cầu; tránh dùng Owner/Editor rộng chỉ để xem private cloud.

IAM role với VMware Engine API **không tự cấp** quyền login Windows VM hoặc thay đổi vCenter inventory.

### 12.2. CloudOwner trong vCenter

Managed private cloud có user mặc định CloudOwner@gve.local với Cloud-Owner-Role. Đây là quyền đủ dùng cho nhiều tác vụ VMware, nhưng không tương đương root không giới hạn trên mọi thành phần do Google quản lý. Khi thao tác nâng cao cần elevation, dùng cơ chế và thời hạn được dịch vụ cho phép.

Không dùng cùng một shared admin account cho mọi kỹ sư. Ưu tiên identity source, role theo nhóm, MFA ở những lớp hỗ trợ, logging và breakglass được kiểm soát.

### 12.3. Bảo vệ management plane

- Giới hạn quyền truy cập vCenter/NSX/HCX qua private network hoặc VPN có kiểm soát.
- Tách management CIDR khỏi workload segments.
- Giám sát các thay đổi quyền và NSX firewall.
- Rotating credentials và tài khoản giải pháp khi cần.
- Dùng TLS/certificates, DNS và thời gian đồng bộ.
- Không đưa thông tin đăng nhập management vào Git hoặc lệnh CLI ghi log.

## 13. Day 0: thiết kế trước khi tạo private cloud

Day 0 là giai đoạn **quyết định những điều khó thay đổi sau này**.

Checklist:

1. BIA và mục tiêu RTO/RPO cho từng workload.
2. Chọn Managed hay BYOL model; xác nhận license và hợp đồng.
3. Chọn region/zone và node types được hỗ trợ.
4. Đặt project/folder, billing account, labels, quota và IAM.
5. Chọn standard hay stretched; dự trù số nodes cho HA.
6. Thiết kế management CIDR, workload NSX segments, HCX networks.
7. Quy hoạch VPN/Interconnect, BGP, Cloud Router, routes và DNS.
8. Tính compute/RAM/vSAN capacity, số VM và headroom khi host failure.
9. Chọn storage policy, external NFS datastore nếu phù hợp.
10. Lập kế hoạch backup, DR và security baseline.
11. Dự toán chi phí on-demand/commitment, connection egress và license.
12. Kiểm tra dịch vụ phụ trợ như AD/DNS/NTP, monitoring và log sink.

**CIDR trùng hoặc chọn sai model private cloud** thường tốn nhiều công sửa hơn nhiều so với việc tăng CPU cho một VM sau migrate.

## 14. Day 1: provisioning và đưa workload vào

Ở mô hình managed, Day 1 thường bao gồm:

1. Bật VMware Engine API, xác minh billing/quota và quyền.
2. Tạo Standard VMware Engine network hoặc dùng network đã được quản trị chấp thuận.
3. Tạo private cloud với location, cluster, node type, số node và management range.
4. Chờ provision hoàn thành; kiểm tra vCenter/NSX/HCX và trạng thái nodes.
5. Thiết lập peering với VPC, DNS bindings và hybrid route.
6. Tạo NSX segments và firewall theo ứng dụng.
7. Cấu hình vCenter RBAC/identity source, resource pools và folders.
8. Thiết lập backup, syslog, metrics, alerts và capacity thresholds.
9. Test VM nhỏ, network/backup/restore trước migration hàng loạt.
10. Di chuyển workload theo waves, nghiệm thu và bàn giao.

### 14.1. Thao tác Google Cloud CLI minh họa

Các lệnh kiểm kê **read-only** sau có thể dùng khi đã được cấp quyền:

~~~bash
PROJECT_ID="example-vmware-project"
LOCATION="asia-southeast1-a"
PRIVATE_CLOUD_ID="orders-vmware"

gcloud services list \
  --enabled \
  --project="$PROJECT_ID" \
  --filter="name:vmwareengine.googleapis.com"

gcloud vmware locations list \
  --project="$PROJECT_ID"

gcloud vmware private-clouds list \
  --project="$PROJECT_ID" \
  --location="$LOCATION"

gcloud vmware private-clouds clusters list \
  --project="$PROJECT_ID" \
  --location="$LOCATION" \
  --private-cloud="$PRIVATE_CLOUD_ID"
~~~

Dùng location là zone cho standard private cloud; stretched private cloud là resource theo region. Chọn loại location theo resource thực tế và hướng dẫn CLI tương ứng. Các lệnh trên không tạo, xóa hoặc đổi tài nguyên.

### 14.2. Vì sao lab không tự tạo private cloud?

Một private cloud production sử dụng nhiều dedicated bare-metal nodes, có chi phí đáng kể và điều kiện quota/license. Vì vậy bài này cung cấp **quy trình có thể review và thao tác kiểm kê**, không yêu cầu người học tự chạy lệnh create ba node trên project production.

Khi được phê duyệt, tạo qua Google Cloud Console hoặc gcloud vmware theo runbook của tổ chức; kiểm tra đúng node type, CIDR, quota và dự toán **trước khi bấm Create**.

## 15. Day 2: vận hành thường xuyên

Sau cutover, nhiệm vụ không kết thúc. Một lịch vận hành tối thiểu:

| Chu kỳ | Công việc | Bằng chứng |
|---|---|---|
| Hằng ngày | Kiểm tra health nodes, clusters, vSAN, alarm, backup jobs | Dashboard, ticket, alert |
| Hằng tuần | Kiểm tra guest OS patches, capacity trend, failed backup, NSX policy drift | Report và action items |
| Hằng tháng | Review VMware/Google security advisories, cost, utilization, inventory, quota | Change review |
| Hằng quý | Restore drill, failover tabletop, IAM review, penetration/security review theo policy | DR report, sign-off |
| Sau mỗi migration wave | Reconcile VM inventory, NSX routes, DNS, backup policies | Migration evidence |
| Trước thay đổi lớn | Snapshot/backup, kế hoạch rollback và maintenance window | Approved change record |

Đặt rõ owner cho VMware platform, network, guest OS, app/database, security, monitoring và FinOps. Không đùn đẩy sự cố guest VM lên Google Cloud operations nếu vấn đề xuất phát từ cấu hình OS hoặc ứng dụng.

## 16. Capacity planning: vCPU, RAM, storage và HA headroom

Đánh giá máy ảo nguồn:

- Allocated vCPU/RAM so với actual P95/P99 usage.
- Peak CPU ready time, memory ballooning/swapping.
- Provisioned vs used disk và IOPS/latency.
- VM reservations, resource pools, affinity/anti-affinity.
- Số lượng VM theo tier và giờ cao điểm.
- License phụ thuộc core hoặc socket.
- Tăng trưởng dữ liệu 6–24 tháng.
- Capacity cần thiết để survive host failure hoặc bảo trì.

### 16.1. Không cộng raw storage là usable capacity

Giả sử private cloud có 3 nodes, mỗi node 19,2 TB raw storage (con số minh họa theo một node type, không phải cam kết mọi location). Tổng raw là:

\[
3 \times 19,2 = 57,6\ \text{TB raw}
\]

Dung lượng usable **nhỏ hơn** do vSAN FTT/RAID policy, metadata, dedup/compression ratio, slack/rebuild và overhead của management VMs. Không lấy 57,6 TB làm mức dữ liệu có thể lưu cho application.

Một bảng sizing cần có:

| Nhu cầu | Giá trị minh họa | Cần xác minh |
|---|---:|---|
| 60 VMs | Inventory hiện tại | Boot order, reservation |
| CPU P95 | 900 GHz-hour hoặc metric phù hợp | Quy đổi theo loại node thực |
| RAM allocated | 4 TiB | Active/consumed memory và headroom |
| Disk used | 20 TiB | FTT policy, vSAN usable |
| Storage IOPS P95 | Theo đo source | Node/storage policy latency |
| HA reserve | N+1 hoặc policy đã duyệt | Sống sót khi 1 node lỗi |
| Growth | 20%/năm | Quota, storage expansion |

Đừng tính CPU chỉ bằng vCPU count vì overcommit và tính chất workload khác nhau. Nên chạy assessment và thử nghiệm hiệu năng sau migration.

## 17. Autoscale và mở rộng cluster

Managed VMware Engine hỗ trợ autoscale cluster theo metric CPU, RAM và storage utilization khi đáp ứng điều kiện dịch vụ. Có thể cấu hình min/max nodes, scale-out threshold, scale-in threshold, số node mỗi đợt và cool-off period.

Một số giới hạn:

- Không áp dụng cho **single-node cluster**.
- Không áp dụng cho cluster có storage-only nodes trong trường hợp tài liệu autoscale nêu.
- Việc scale thêm nodes vẫn bị giới hạn **quota và capacity trong location**.
- Autoscale không đồng nghĩa với việc VM guest tự scale out theo request/giây.
- Scale-in phải tính vSAN rebuild, DRS và HA capacity; không nên hạ xuống sát ngưỡng để tiết kiệm chi phí.

### 17.1. Ví dụ policy minh họa

| Tham số | Giá trị ví dụ | Giải thích |
|---|---:|---|
| Min nodes | 3 | Sàn để giữ HA standard |
| Max nodes | 6 | Giới hạn ngân sách |
| Scale-out threshold | CPU 75% kéo dài | Tránh saturate lâu |
| Scale-in threshold | CPU thấp hơn 40% kéo dài | Tránh thu nhỏ khi còn load |
| Cool-off | Theo policy và tài liệu | Tránh dao động node count |
| Reserve for failure | N+1 | Đảm bảo placement sau node failure |

Threshold chỉ mang tính ví dụ. Google Cloud autoscale sử dụng điều kiện sustained utilization theo thuật toán của dịch vụ, có thể quan sát CPU, memory và storage với logic khác nhau cho scale-out/scale-in. Cần test trên môi trường thật và tránh đưa workload quan trọng vào cluster mà quota không đủ để mở rộng khi có sự cố.

## 18. Storage: vSAN và external datastores

vSAN sử dụng storage gắn với các ESXi nodes để tạo datastore cho workload. Storage policy (FTT, layout và khả năng chịu lỗi) ảnh hưởng usable capacity, hiệu năng và recovery.

Khi nhu cầu storage tăng nhanh hơn CPU/RAM, bổ sung full compute nodes chỉ để lấy thêm dung lượng có thể không hiệu quả. VMware Engine còn hỗ trợ lựa chọn **external NFS datastores** với các dịch vụ tương thích như Filestore hoặc Google Cloud NetApp Volumes theo điều kiện sản phẩm.

| Phương án | Khi cân nhắc | Lưu ý |
|---|---|---|
| vSAN mặc định | VM cần hiệu năng/hợp nhất compute-storage | FTT, capacity headroom, vSAN health |
| Storage-only nodes khi được hỗ trợ | Cần thêm storage mà không tăng compute tương ứng | Node family, cluster policy và autoscale limits |
| External NFS datastore | Workload có nhu cầu storage riêng, tier-2/3, backup | Throughput/latency, network, security và failure domain |
| Guest-level storage riêng | Database/app cần giao thức khác | Quản lý bằng hệ điều hành/app và backup riêng |

Không phải mọi Filestore/NetApp volume đều mount trực tiếp cho mọi cluster: phải xác nhận service tier, region, network peering và tính năng NFS datastore đã được hỗ trợ.

## 19. Maintenance và VMware software lifecycle

Ở **Google Cloud-managed** VMware Engine, Google chịu trách nhiệm lifecycle updates và security patches của VMware software thuộc dịch vụ. Các đợt cập nhật có thể gồm patch, minor update hoặc major upgrade.

Khách hàng vẫn cần:

- Theo dõi maintenance notifications/Update Center và lịch triển khai.
- Kiểm tra compatibility của agent, backup vendor, guest OS và application.
- Xác định maintenance window cho workload nhạy cảm.
- Bảo đảm DRS/HA/vSAN có đủ headroom để di chuyển VM khi host cần bảo trì.
- Test service-level application response sau update.
- Chuẩn bị change record và phương án liên hệ support khi sự cố.

Một số bản security patch có thể được áp dụng theo chính sách dịch vụ mà khách hàng không tùy chọn trì hoãn như bản version update thông thường. Không được tự patch ESXi/vCenter của managed private cloud bằng quy trình dành cho VMware tự quản lý.

Với mô hình **BYOL VCF**, chính khách hàng chịu trách nhiệm patch/upgrade VMware stack. Lịch và công cụ lifecycle phải nằm trong SDDC runbook riêng.

## 20. Backup và Disaster Recovery của workload VMs

Google có thể quản lý backup/restore của **management services**, nhưng workload VM và dữ liệu nghiệp vụ vẫn thuộc trách nhiệm khách hàng.

Có thể dùng Google Cloud Backup and DR hoặc sản phẩm backup VMware tương thích để bảo vệ:

- Guest VM configuration và virtual disks.
- Database-aware backups (SQL Server, Oracle, PostgreSQL...).
- Application-specific state, transactions và secrets.
- File share và external datastore nếu có.
- Runbook khôi phục tại một private cloud khác hoặc region khác.

~~~mermaid
flowchart TD
    VM["Workload VMs<br/>managed VMware Engine"]
    BK["Backup product + backup policy"]
    REPO["Backup repository<br/>Cloud Storage / NFS / phù hợp"]
    TARGET["Restore target<br/>private cloud / hạ tầng dự phòng"]
    TEST["DR drill + business validation"]

    VM --> BK --> REPO
    REPO --> TARGET --> TEST
~~~

### 20.1. HA khác DR

- vSphere HA có thể khởi động lại VM nếu node lỗi, nhưng không sửa dữ liệu bị xóa nhầm.
- vSAN replication/FTT giúp chịu lỗi thành phần nhưng không phải backup lịch sử sạch.
- Stretched cluster giúp chịu zone outage trong một region, không tự tạo DR khi cả region không truy cập được.
- Backup/restore hoặc replication sang vùng độc lập mới có thể phục vụ kịch bản mất region.
- RPO/RTO là mục tiêu cần kiểm chứng qua restore drill, không phải lợi ích mặc định của việc có nhiều node.

### 20.2. RTO/RPO theo workload

Ví dụ Orders DB chạy trên VM có mục tiêu:

| Kịch bản | RPO mục tiêu | RTO mục tiêu | Phương án cần đánh giá |
|---|---:|---:|---|
| Một ESXi node lỗi | Ít nhất theo transaction durability | ≤ 30 phút | vSphere HA + đủ capacity |
| Xóa nhầm bảng dữ liệu | 15 phút | 2 giờ | Database PITR/backup riêng |
| Mất một zone | Theo policy | ≤ 1 giờ | Stretched nếu region hỗ trợ, hoặc DR |
| Mất cả region | ≤ 1 giờ | ≤ 8 giờ | Cross-region backup/replica và runbook |

Các giá trị là ví dụ nghiệp vụ, không phải SLA VMware Engine. Cần ghi actual recovery point và actual recovery time từ bài diễn tập có dữ liệu nhất quán.

## 21. Observability và khả năng phản ứng sự cố

Một dashboard tốt cần theo dõi từ Google Cloud tới vCenter và guest OS.

| Lớp | Tín hiệu | Công cụ |
|---|---|---|
| Google Cloud project | Private cloud operations, node events, audit logs | Google Cloud Logging/Monitoring, Essential Contacts |
| VMware cluster | CPU/memory/vSAN capacity, HA/DRS events | vCenter, VMware Aria Operations |
| Network | NSX firewall drops, gateway health, latency | NSX Manager, syslog, network telemetry |
| HCX/migration | Migration tasks, transfer status, error | HCX Manager/vCenter |
| Guest OS | CPU/memory/disk, patch level, antivirus | Guest monitoring agent và OS tooling |
| Application | 5xx, P95/P99 latency, throughput, transaction errors | Application tracing/APM, logs |
| Database | Connections, query latency, replication lag, backup results | DB-native metrics và backup dashboard |

Google Cloud VMware Engine có service alerts/logs; có thể tạo log-based alerting. Để đưa metrics vCenter/VMware vào Cloud Monitoring, tài liệu mô tả tích hợp qua standalone agent/BindPlane; metrics forwarding cần cấu hình cho từng private cloud và có thể phát sinh phí metric ingestion.

### 21.1. Alerting ưu tiên

- Node failure hoặc vSAN health degradation.
- vSAN disk utilization và capacity/rebuild headroom.
- CPU ready time hoặc memory contention kéo dài.
- HCX migration failure, stuck tasks hoặc network extension issue.
- DNS/route/TLS failures tới vCenter/NSX/HCX.
- Backup job failure hoặc restore point quá cũ.
- Guest OS disk full, services down, patch compliance.
- Application latency, 5xx, failed transactions.
- Chi phí và node count tăng ngoài budget.

Tách sự kiện service-level do Google xử lý với lỗi application-level mà khách hàng phải khắc phục. Runbook cần có **owner và escalation path** cho từng loại alert.

## 22. Kết nối dịch vụ Google Cloud-native

Một lợi ích của VMware Engine là giữ VM cũ nhưng cho phép ứng dụng sử dụng dịch vụ Google Cloud mới.

Ví dụ:

~~~mermaid
flowchart TD
    VM["VMware Engine: Java app VM"]
    VEN["VMware Engine network"]
    VPC["Google Cloud VPC"]
    SEC["Secret Manager / Cloud KMS"]
    CS["Cloud Storage"]
    SQL["Cloud SQL"]
    NATIVE["Cloud Run / GKE services"]

    VM --> VEN --> VPC
    VPC --> SEC
    VPC --> CS
    VPC --> SQL
    VPC --> NATIVE
~~~

Các bước tích hợp cần chú ý:

1. Đảm bảo VPC/route/DNS hợp lệ, không giả định mọi API public có private route.
2. Xác định workload identity/cơ chế cấp short-lived credentials cho VMs, tránh key JSON hardcoded.
3. Cấp IAM role tối thiểu tới bucket, secret, database hoặc API.
4. Với Cloud Storage, kiểm tra network egress, object operations và access control.
5. Với Cloud SQL, cân nhắc latency, connection pooling và network topology.
6. Với Cloud Run service private, thiết kế authentication/ingress và network đúng, không chỉ ping IP.
7. Ghi nhận chi phí giữa VMware Engine và các dịch vụ native.

VMware Engine là một **giai đoạn chuyển tiếp chiến lược**, không có nghĩa mọi workload phải giữ trên VMware mãi. Có thể modernize dần các ứng dụng phù hợp.

## 23. Automation và cấu hình có kiểm soát

Vận hành nhiều private clouds thủ công dễ tạo sai khác về IAM, network, storage policy và backup. Nên xác định cấu hình mong muốn bằng IaC/automation được tổ chức phê duyệt, trong giới hạn API được hỗ trợ.

Các nhóm automation:

| Thành phần | Công cụ hoặc ý tưởng | Cần tránh |
|---|---|---|
| VMware Engine resources | Google Cloud CLI/API/Terraform provider khi hỗ trợ | Apply phá private cloud đang chạy |
| vCenter inventory/VM | VMware PowerCLI, vSphere automation | Tạo VM không theo naming/backup policy |
| NSX segments/firewall | NSX policy API hoặc configuration management | Mở Any/Any kéo dài sau migration |
| Guest OS | Ansible/SCCM/patch automation | Patch hàng loạt không có canary |
| Backup | Backup policy-as-code/scheduling | Coi backup job success là restore proof |
| Monitoring | Dashboard/alerts as code | Không có owner/notification |
| DR | Runbook, test workflows, IaC cho recovery site | Hai primary nhận writes cùng lúc |

**Sự khác biệt quan trọng:** Terraform/apply vào Google Cloud VMware Engine resource không thay thế VMware API để cấu hình từng VM/NSX object. Cần phân ranh ownership rõ và quản lý drift giữa các control planes.

## 24. FinOps: tính tổng chi phí chứ không chỉ giá node

Chi phí VMware Engine thường được quyết định bởi node type, số nodes và thời gian sử dụng, nhưng dự toán còn gồm nhiều mục.

| Thành phần | Động lực chi phí |
|---|---|
| VMware Engine nodes | Node-hour, node type, số lượng, location |
| Pricing model | On-demand, commitment, license included hoặc portable/BYOL phù hợp |
| HA headroom | Nodes dự phòng hoặc capacity không dùng 100% |
| Storage | vSAN capacity, external NFS datastore, backup repositories |
| Network | VPN/Interconnect, peering topology, data transfer, NAT |
| Backup/DR | Backup software, vault/storage, replication, recovery drills |
| Logging/Monitoring | Custom metrics, log ingestion, storage/retention |
| Guest OS/database license | Windows Server, SQL Server, vendor licensing |
| Nhân sự vận hành | VMware/OS/security/network on-call |
| Hybrid overlap | Datacenter nguồn và GCP chạy song song khi migrate |

### 24.1. Bài toán node-hour giả định

Giả sử một standard private cloud có 3 nodes, sử dụng liên tục 730 giờ/tháng. Đơn giá **hoàn toàn giả định** là 5 USD/node-hour:

\[
C_{\text{nodes}} = 3 \times 730 \times 5 = 10.950\ \text{USD/tháng}
\]

Chưa gồm license/loại pricing model phù hợp, network, backup, external storage, taxes và discounts. Không coi số 5 USD là giá public thực tế.

Nếu thêm một node cả tháng:

\[
\Delta C = 730 \times 5 = 3.650\ \text{USD/tháng}
\]

Ví dụ cho thấy tại sao không nên mặc định "thêm node để có storage" là rẻ nhất mà chưa so sánh storage-only nodes hoặc external NFS datastore.

### 24.2. Commitments và lifecycle

On-demand thuận tiện khi migration chưa chắc thời hạn, nhưng chi phí có thể cao nếu giữ cluster lâu. Commitments 1 hoặc 3 năm có thể giảm chi phí theo SKU/hợp đồng, đồng thời giảm linh hoạt nếu số node/workload thay đổi.

Trước khi cam kết:

- Dùng assessment đo đúng CPU/RAM/storage và HA reserve.
- Phân nhóm VM theo khả năng modernize trong 6–24 tháng.
- Kiểm tra điều kiện CUD, license, portability và node family.
- Tính overlap cost của datacenter và cloud.
- Lập kịch bản scale-up/scale-down và capacity/quota.
- Gắn budget alerts, billing labels và owner.

**Không tự cam kết số node theo số VM được cấp phát**, vì overprovisioning và headroom có thể làm sai dự toán.

## 25. Case study: ứng dụng ba tầng trong VMware Engine

Doanh nghiệp có:

- Web: 4 Windows/Linux VMs.
- App: 6 Java/Spring Boot VMs.
- Database: 2 SQL Server VMs.
- AD, DNS, NTP và hệ thống backup on-prem.
- Yêu cầu RTO 4 giờ, RPO 30 phút cho giao dịch nghiệp vụ.

### 25.1. Kiến trúc đích

~~~mermaid
flowchart LR
    USERS["Người dùng"]
    EDGE["HTTPS edge / network firewall"]
    subgraph GCVE["VMware Engine private cloud"]
      WEB["Web VMs / NSX segment"]
      APP["Java app VMs / NSX segment"]
      DB["SQL Server VMs / NSX segment"]
      WEB --> APP --> DB
    end
    VPC["Google VPC / peering"]
    DC["On-prem AD/DNS + hybrid link"]
    BACKUP["Backup repository + DR plan"]
    USERS --> EDGE --> WEB
    GCVE --> VPC
    VPC <--> DC
    GCVE --> BACKUP
~~~

### 25.2. Migration stages

1. Assessment: xác định owner, CPU/RAM/IOPS, services, network, SQL dependency.
2. Chọn model managed private cloud và standard/stretched theo RTO.
3. Thiết kế CIDR, on-prem Cloud VPN/Interconnect, DNS/AD, NSX segments.
4. Tạo private cloud, vCenter roles, backup và monitoring.
5. Pilot migrate hai VMs không quan trọng và thử ứng dụng end-to-end.
6. Migrate web/app theo waves; không chuyển database mà không có kế hoạch nhất quán giao dịch.
7. Chuyển SQL Server với backup/replication hoặc phương thức migration phù hợp; write freeze/cutover khi cần.
8. Thử authentication, order transaction, reports, failover, latency và cost.
9. Chuyển traffic, theo dõi hypercare rồi decommission nguồn sau approval.

### 25.3. Rủi ro chính

| Rủi ro | Hậu quả | Biện pháp |
|---|---|---|
| Trùng CIDR | Routing lỗi | IP address plan trước provisioning |
| NSX segment mở quá rộng | Lateral movement | Microsegmentation và policy review |
| App và DB khác nơi, RTT tăng | SQL transaction chậm | Dependency map, co-location theo wave |
| Thiếu HA reserve | Host failure gây thiếu capacity | N+1 headroom, stress test |
| Backup chưa restore | Mất dữ liệu khi cutover | Restore drill, recovery point validation |
| License theo core thay đổi | Budget vượt dự kiến | License inventory và vendor approval |
| SSO/AD/DNS chưa sẵn | Không đăng nhập được | Test identity path từ target VMs |
| HCX migration stuck | Trễ cutover | Preflight network, checkpoint, rollback |

## 26. Bài thực hành đề xuất: thiết kế trước, không phát sinh node cost

Bài lab này có thể hoàn thành **mà không tạo private cloud mới**, để người học hiểu cách thiết kế và vận hành.

### Bước 1: lập inventory

Tạo bảng minh họa:

| VM | Role | OS | vCPU | RAM | Used disk | Target |
|---|---|---|---:|---:|---:|---|
| web-01 | Web | Linux | 4 | 8 GiB | 60 GiB | Web segment |
| app-01 | Java API | Linux | 8 | 16 GiB | 150 GiB | App segment |
| db-01 | DB | Windows | 16 | 64 GiB | 1 TiB | DB segment |
| ad-01 | Identity | Windows | 4 | 16 GiB | 80 GiB | Management/identity design |

Xác định hard dependencies của từng VM và failover/backup requirements.

### Bước 2: chọn mô hình

Trả lời:

- Managed hay BYOL và vì sao?
- Standard hay stretched?
- Production cần ít nhất bao nhiêu nodes theo chính sách HA?
- Có thể dùng single-node cho PoC không?
- Cần storage policy/FTT nào và headroom bao nhiêu?

### Bước 3: thiết kế IP và route

Vẽ:

- Management CIDR không trùng với workload/VPC/on-prem.
- Standard VMware Engine network và VPC peering.
- Cloud VPN/Interconnect tới datacenter.
- DNS forwarding/bindings và vCenter FQDN.
- NSX segments cho Web/App/DB.
- Một đường đi từ web VM đến dịch vụ Google Cloud-native.

### Bước 4: chạy lệnh inventory read-only nếu có environment

~~~bash
gcloud vmware locations list --project=PROJECT_ID

gcloud vmware private-clouds list \
  --project=PROJECT_ID \
  --location=LOCATION

gcloud vmware private-clouds clusters list \
  --project=PROJECT_ID \
  --location=LOCATION \
  --private-cloud=PRIVATE_CLOUD_ID
~~~

Thay các placeholder bằng project/location thật đã được cho phép. Nếu không có environment hoặc quyền, ghi kết quả giả định thay vì tạo tài nguyên.

### Bước 5: viết runbook migration

Có các cột: Wave, VM group, source/destination segments, HCX/migration method, downtime, rollback point, business owner, validation, sign-off.

### Bước 6: đo readiness

Bài đạt yêu cầu khi người học có thể giải thích:

- Ai patch ESXi/vCenter và ai patch guest OS?
- Ai tạo backup của database guest VM?
- Vì sao VPC peering không tự tạo mọi route transitive?
- Vì sao single-node không phù hợp production HA?
- RTO/RPO đo ở đâu và rollback tránh split-brain thế nào?
- Cần thêm gì để VM truy cập Cloud SQL/Cloud Storage một cách an toàn?

## 27. Troubleshooting vận hành

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không mở được vCenter URL | Thiếu VPN/peering/DNS/firewall hoặc account | Test FQDN, route, ACL, identity source |
| GCP VM không tới workload VMware | VPC peering, custom route, NSX policy sai | VPC route, VEN peering, return path, NSX |
| On-prem không vào VMware Engine | BGP/Cloud VPN/Interconnect, DNS, firewall | Tunnel/BGP health, CIDR, route import-export |
| HCX không kết nối | Thiếu ports, sai site pairing, MTU/certificate | HCX appliance logs, connectivity, version compatibility |
| VM migrate xong không truy cập DB | IP/segment/firewall, DB hardcoded host | DNS, NSX rule, DB listener, app config |
| vSAN gần đầy | Workload tăng, FTT overhead hoặc rebuild | vSAN capacity health, storage policy và node plan |
| CPU ready time cao | Oversubscription, contention hoặc placement | vCenter performance, DRS và capacity |
| Autoscale không thêm node | Quota/capacity hoặc policy threshold | Quotas, sustained usage, autoscale eligibility |
| Không thấy vCenter metrics trong Cloud Monitoring | Chưa cấu hình agent/forwarder | BindPlane/standalone agent, export và permissions |
| Backup job thành công nhưng restore lỗi | Chưa thử recovery, credentials/target thiếu | Restore drill trên isolated target |
| Tăng chi phí đột ngột | Thêm node, commitment hết, egress hoặc logs | Cloud Billing by SKU/node usage |
| Guest OS chưa patch nhưng host đã update | Hiểu sai shared responsibility | OS patch inventory và app owner |
| Network extension gây bất ổn | L2 stretch quá dài, latency/broadcast loop | NSX/HCX network design và cutover plan |

## 28. Checklist production readiness

- [ ] Mô hình Google Cloud-managed hay BYOL VCF đã được chọn và ghi rõ trách nhiệm.
- [ ] Location và node types được hỗ trợ, quota/capacity đã được xác nhận.
- [ ] Standard/single-node/stretched được chọn phù hợp failure domain và RTO/RPO.
- [ ] Có số node và headroom để chịu host failure theo chính sách.
- [ ] Management CIDR, workload segments và on-prem/VPC CIDR không chồng lấn.
- [ ] VMware Engine network, VPC peering và hybrid routing đã kiểm tra hai chiều.
- [ ] DNS cho vCenter/NSX/HCX và guest workloads hoạt động.
- [ ] NSX segmentation, firewall, TLS và identity access đáp ứng least privilege.
- [ ] Google Cloud IAM và vCenter RBAC được quản lý riêng, có audit và breakglass.
- [ ] VMware lifecycle/maintenance process đúng với Managed hoặc BYOL.
- [ ] Guest OS, database, middleware và app có owner/patching process.
- [ ] Capacity/FTT/vSAN usable size, IOPS và storage policy đã sizing.
- [ ] HCX/migration waves có test, bandwidth assessment và rollback.
- [ ] Không có hai writer cùng ghi dữ liệu tại cutover.
- [ ] Backup workload độc lập và restore drill PASS.
- [ ] DR scenarios zone/region/data corruption được tài liệu hóa.
- [ ] Logs, metrics, alerts, syslog và notification contacts có người nhận.
- [ ] Cloud Billing/commitment/license/network/backup cost có budget alerts.
- [ ] Các VM cần modernize sang GKE/Cloud Run/Compute Engine có roadmap rõ ràng.
- [ ] Business owner đã ký nghiệm thu về availability, data integrity và hiệu năng.

## 29. Câu hỏi tự kiểm tra

**1. Google Cloud VMware Engine khác Compute Engine VM như thế nào?**

VMware Engine cung cấp dedicated hardware và một VMware stack với ESXi, vCenter, vSAN, NSX và HCX để vận hành VM theo VMware tooling. Compute Engine cung cấp máy ảo Google Cloud-native với model quản trị khác.

**2. Google Cloud-managed và VMware solution BYOL khác nhau ở đâu?**

Managed service do Google quản lifecycle VMware stack, có license theo dịch vụ; BYOL cho khách hàng tự triển khai/quản lý VCF và license trên bare-metal Google Cloud. Cả hai đều để khách hàng quản guest workloads.

**3. Vì sao không dùng một node cho production quan trọng?**

Single-node thiếu đủ thành phần cho HA/DRS/vSAN redundancy, không có fault tolerance tương đương cluster nhiều node. Nó phù hợp PoC hơn.

**4. Standard VMware Engine Network kết nối VPC bằng gì?**

Bằng VPC Network Peering. Legacy network có mô hình private services access riêng cho môi trường cũ; không được trộn cấu hình của hai loại.

**5. HCX có làm migration không cần chuẩn bị mạng không?**

Không. HCX cần connectivity giữa VMware nguồn và VMware Engine, các route, port, DNS và tương thích stack phù hợp. Cloud VPN/Interconnect là lớp kết nối hybrid được hướng dẫn.

**6. Google quản lý vCenter có nghĩa tự backup Windows VM không?**

Không. Backup/DR cho customer workload và database guest VM là trách nhiệm khách hàng. Google quản management services trong ranh giới managed service.

**7. Tại sao vSAN raw 60 TB không đồng nghĩa usable 60 TB?**

FTT, storage policy, metadata, overhead, management VMs và spare capacity làm giảm usable storage. Cần đo theo policy trên cluster thật.

**8. VPC peering có thể được dùng như router transit giữa mọi VPC không?**

Không. Peering không tự động transitive. Cần kiểm tra network topology, route advertisement và giới hạn của các peerings.

**9. Sự khác nhau giữa failover ở stretched cluster và multi-region DR?**

Stretched cluster giúp chịu lỗi zone trong một region theo mô hình hỗ trợ. Multi-region DR cần môi trường và dữ liệu dự phòng ngoài region, traffic routing và runbook riêng.

**10. Khi nào nên hiện đại hóa sang Cloud Run hoặc GKE?**

Khi ứng dụng đã có thể stateless/containerized và cần autoscaling/CI/CD cloud-native, đồng thời chi phí, migration risk và tính tương thích cho phép. VMware Engine là một lựa chọn trong chiến lược, không phải đích bắt buộc của mọi VM.

## 30. Tài liệu tham khảo

- [VMware Engine documentation](https://cloud.google.com/vmware-engine/docs)
- [Google Cloud VMware Engine overview](https://cloud.google.com/vmware-engine/docs/overview)
- [Compare VMware Engine operating models](https://cloud.google.com/vmware-engine/docs/vmware-solution/compare-models)
- [VMware solution on Google Cloud BYOL overview](https://cloud.google.com/vmware-engine/docs/vmware-solution/overview)
- [VMware solution on Google Cloud shared responsibility](https://cloud.google.com/vmware-engine/docs/vmware-solution/shared-responsibility)
- [Managed VMware Engine shared responsibility](https://cloud.google.com/vmware-engine/docs/shared-responsibility)
- [About VMware Engine private clouds](https://cloud.google.com/vmware-engine/docs/concepts-private-cloud)
- [About private cloud VMware components](https://cloud.google.com/vmware-engine/docs/concepts-vmware-components)
- [Creating a VMware Engine private cloud](https://cloud.google.com/vmware-engine/docs/private-clouds/howto-create-private-cloud)
- [Stretched private clouds](https://cloud.google.com/vmware-engine/docs/concepts-stretched-private-cloud)
- [About VMware Engine networks](https://cloud.google.com/vmware-engine/docs/networking/vmware-engine-network)
- [Networking requirements](https://cloud.google.com/vmware-engine/docs/quickstart-networking-requirements)
- [VPC peering to VMware Engine](https://cloud.google.com/vmware-engine/docs/networking/peer-vpc-network)
- [Connecting on-premises networks](https://cloud.google.com/vmware-engine/docs/networking/howto-connect-to-onpremises)
- [Workload VM migration options](https://cloud.google.com/vmware-engine/docs/workloads/howto-migrate-workloads)
- [Migrating VMs using HCX](https://cloud.google.com/vmware-engine/docs/workloads/howto-migrate-vms-using-hcx)
- [vSphere permission model](https://cloud.google.com/vmware-engine/docs/concepts-permission-model)
- [Managing VMware Engine IAM roles](https://cloud.google.com/vmware-engine/docs/iam)
- [Managing autoscale](https://cloud.google.com/vmware-engine/docs/howto-autoscale)
- [Private cloud maintenance and updates](https://cloud.google.com/vmware-engine/docs/concepts-maintenance-updates)
- [Backup workload VMs](https://cloud.google.com/vmware-engine/docs/concepts-backup-vms)
- [VMware Engine data protection recommendations](https://cloud.google.com/vmware-engine/docs/data-protection-recommendations)
- [Monitoring VMware Engine](https://cloud.google.com/vmware-engine/docs/concepts-monitoring)
- [VMware Engine security best practices](https://cloud.google.com/vmware-engine/docs/best-practices-security)
- [VMware Engine storage practices](https://cloud.google.com/vmware-engine/docs/best-practices-storage)
- [Google Cloud VMware Engine pricing](https://cloud.google.com/vmware-engine/pricing)

