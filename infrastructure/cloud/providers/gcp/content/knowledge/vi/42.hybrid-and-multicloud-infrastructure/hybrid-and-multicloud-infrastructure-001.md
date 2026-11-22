# Mô hình hybrid cloud và multicloud với Google Cloud

Một doanh nghiệp hiếm khi chuyển toàn bộ hệ thống lên một đám mây trong một lần. Dữ liệu giao dịch có thể vẫn nằm tại trung tâm dữ liệu riêng, ứng dụng Java/Spring đã chạy trên Google Kubernetes Engine (GKE), đối tác vận hành một API trên AWS và nhóm phân tích dùng BigQuery. Khi những thành phần đó cùng phục vụ một quy trình nghiệp vụ, tổ chức cần kiến trúc **hybrid cloud** hoặc **multicloud** có kiểm soát.

Hybrid cloud kết nối hạ tầng tại chỗ với tài nguyên đám mây; multicloud sử dụng dịch vụ từ hai hoặc nhiều nhà cung cấp cloud. Hai mô hình có thể tồn tại đồng thời. Giá trị không chỉ đến từ việc thiết lập VPN hay đường truyền riêng, mà còn nằm ở **định tuyến, DNS, danh tính, phân quyền, dữ liệu, khả năng phục hồi, quan sát, vận hành và chi phí**.

Google Cloud cung cấp các thành phần như Virtual Private Cloud (VPC), HA VPN, Cloud Interconnect, Cross-Cloud Interconnect, Cloud Router, Network Connectivity Center, Cloud DNS, Cloud IAM, GKE, Google Distributed Cloud và các dịch vụ dữ liệu. Mỗi sản phẩm giải quyết một lớp của kiến trúc; không có một dịch vụ duy nhất tự động biến hạ tầng phân tán thành hệ thống bảo mật và có độ tin cậy cao.

Bài học này xây dựng mô hình từ nhu cầu nghiệp vụ đến topology, kết nối, danh tính, dữ liệu và hoạt động vận hành, với ví dụ ứng dụng Java/Spring sử dụng cả hệ thống tại chỗ và Google Cloud.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt private cloud, public cloud, hybrid cloud, multicloud và hybrid multicloud.
- Xác định những tình huống nên sử dụng từng mô hình, thay vì triển khai đa đám mây theo phong trào.
- Thiết kế VPC, địa chỉ IP, routing, DNS và ranh giới project cho hệ thống liên thông.
- So sánh HA VPN, Dedicated/Partner Interconnect và Cross-Cloud Interconnect.
- Giải thích vai trò Cloud Router, BGP và Network Connectivity Center trong các topology hub/spoke.
- Áp dụng Zero Trust, IAM, workload identity và bảo mật đường truyền xuyên môi trường.
- Xây dựng phương án giao tiếp và đồng bộ dữ liệu có RTO/RPO, latency, consistency rõ ràng.
- Chọn cách vận hành ứng dụng Java, Kubernetes và các workload edge trong nhiều môi trường.
- Thiết kế logging, monitoring, IaC, runbook và cost allocation xuyên cloud.
- Lập lộ trình migration, pilot, cutover và rollback có thể kiểm chứng.

## 1. Phân biệt các mô hình hạ tầng

| Mô hình | Đặc điểm | Ví dụ |
|---|---|---|
| On-premises/private cloud | Hạ tầng do tổ chức sở hữu hoặc vận hành tại trung tâm dữ liệu riêng | VMware hoặc Kubernetes on-prem |
| Public cloud | Dịch vụ trên một cloud provider | Ứng dụng Java chạy trên Cloud Run |
| Hybrid cloud | Kết nối hạ tầng tại chỗ và public cloud thành luồng vận hành chung | Java API trên GKE truy cập database on-prem qua HA VPN |
| Multicloud | Sử dụng tài nguyên từ ít nhất hai public cloud providers | Backend trên GCP và analytics trên AWS |
| Hybrid multicloud | Đồng thời có on-prem và nhiều public clouds | ERP on-prem, web trên GCP, dữ liệu đối tác trên Azure |

**Hybrid không có nghĩa tất cả thành phần phải chuyển tiếp dữ liệu liên tục.** Một công ty có thể dùng on-prem cho dữ liệu có yêu cầu lưu trú, cloud cho API và chuyển một phần dữ liệu theo lô.

**Multicloud cũng không bắt buộc mỗi ứng dụng được triển khai trên mọi cloud.** Một chiến lược multicloud có thể phân chia workload: service A chạy ở GCP, service B chạy trên AWS, còn kết nối giữa chúng được kiểm soát qua API và mạng.

### Hybrid và multicloud khác nhau ở điểm nào?

- Hybrid tập trung vào ranh giới giữa môi trường tự vận hành và cloud.
- Multicloud tập trung vào ranh giới giữa các nhà cung cấp cloud.
- Cả hai cần quản lý nhiều nền tảng, quyền truy cập, địa chỉ mạng, logs và chính sách.
- Rủi ro lớn nhất thường nằm ở integration và ownership, không chỉ ở công nghệ kết nối.

## 2. Khi nào cần hybrid hoặc multicloud?

Một số động lực hợp lý:

1. **Từng bước migration:** giữ ERP/database nguồn trong khi chuyển Java API sang GCP.
2. **Data residency:** dữ liệu phải xử lý tại cơ sở hoặc vùng pháp lý cụ thể.
3. **Edge latency:** xử lý cảm biến gần nhà máy, đẩy kết quả tổng hợp lên Google Cloud.
4. **Mergers and acquisitions:** hai doanh nghiệp đang dùng hai cloud khác nhau.
5. **Best-fit services:** một workload cần dịch vụ chuyên biệt từ một provider khác.
6. **Business continuity:** tách một số failure domains hoặc chuẩn bị DR theo yêu cầu.
7. **Hợp đồng và license:** không thể chuyển một ứng dụng hoặc database ngay lập tức.
8. **Tích hợp đối tác:** hệ thống thanh toán hoặc logistics hoạt động trên cloud khác.

### Khi nào không nên chọn?

- Chỉ nhằm tuyên bố tránh vendor lock-in nhưng không có yêu cầu nghiệp vụ.
- Tổ chức chưa có SLO, on-call, IaC, identity governance và network ownership cơ bản.
- Ứng dụng cần transaction đồng bộ giữa hai cloud với latency cực thấp.
- Chi phí egress, observability và vận hành tăng lớn hơn lợi ích.
- Cần active-active nhưng dữ liệu không có chiến lược tránh split-brain.

Một kiến trúc trên một cloud với nhiều zones/regions có thể đáp ứng độ tin cậy tốt hơn và đơn giản hơn multicloud chưa được kiểm chứng. Hãy so sánh theo yêu cầu cụ thể.

## 3. Các mô hình topology phổ biến

### 3.1. Hybrid extension: ứng dụng GCP, dữ liệu on-prem

~~~text
     Users
       |
       v
  Cloud Load Balancing
       |
       v
  Cloud Run / GKE / Compute Engine
       |
       v
   Google Cloud VPC
       |
       +--- Cloud Router (BGP control plane)
       |
       +--- HA VPN hoặc Interconnect
                 |
                 v
        On-prem network
                 |
           +-----+-----+
           |           |
           v           v
        ERP API      Database
~~~

Ưu điểm: chuyển ứng dụng dần dần, tận dụng GCP compute/CI/CD. Rủi ro: request path vẫn phụ thuộc kết nối tới on-prem và có thể tăng latency.

### 3.2. Multicloud phân chia chức năng

~~~text
         Public clients
               |
               v
       Checkout API on GCP
               |
       +-------+--------+
       |                |
       v                v
 Inventory GCP     Partner API on AWS
       |                |
       v                v
  Cloud SQL         Managed database
~~~

Mỗi provider có trách nhiệm riêng. Giao tiếp có thể qua HTTPS có xác thực hoặc kết nối private nếu cần. Không bắt buộc xây mạng liên thông toàn bộ chỉ vì một API cần gọi provider khác.

### 3.3. Hub/spoke nhiều VPC và nguồn ngoài

~~~text
       On-prem DC                   AWS / Azure
          |                              |
       VPN / VLAN                    VPN / VLAN
          |                              |
       Hybrid spoke                 Hybrid spoke
           \                            /
            \                          /
             v                        v
              Network Connectivity Center
                         Hub
                /         |         \
               v          v          v
           VPC Prod    VPC Shared   VPC Analytics
             spoke       spoke         spoke
~~~

Network Connectivity Center (NCC) giúp tổ chức hub/spoke và route exchange theo loại spoke/hub mode. NCC không tự tạo mọi VPN/Interconnect resource hoặc bỏ qua firewall/IAM.

## 4. Landing zone: điểm khởi đầu trước khi nối mạng

Trước khi thiết lập connectivity, nên thống nhất hạ tầng nền tảng:

- Google Cloud organization, folder và project boundaries.
- IAM groups, service accounts và tổ chức cấp quyền.
- VPC layout, subnet/secondary ranges và IPAM.
- Logging, audit, budgets, policies và billing ownership.
- Regions/zones theo latency, residency và availability.
- Terraform hoặc cơ chế Infrastructure as Code (IaC) có review.
- Service perimeter, firewall policy và giới hạn egress.
- Network operations, on-call và escalation giữa các provider.

### Chia project theo chức năng

| Project giả định | Trách nhiệm |
|---|---|
| net-host-prod | Shared VPC, Cloud Router, VPN/Interconnect, DNS |
| app-checkout-prod | Workload Java/Spring production |
| data-prod | Cloud SQL, Storage, BigQuery |
| ops-security | Audit, monitoring và security operations |
| sandbox | Thử nghiệm tách biệt với production |

Shared VPC cho phép nhiều service projects dùng subnet của host project nhưng cần cấp IAM đúng vai trò. Không nhầm Shared VPC với peering hay NCC: mỗi công nghệ có mục tiêu connectivity và scope khác nhau.

### Bảo vệ ranh giới giữa các môi trường

- Dev không mặc định có route và quyền truy cập production.
- Mỗi project/service dùng service account có quyền tối thiểu.
- Không dùng một account hạ tầng với Owner trên toàn bộ cloud providers.
- Các kết nối hybrid phải có inventory, owner, route policy và lịch review.
- Không dùng cùng secrets, database credentials cho test và production.

## 5. Thiết kế IP addressing và subnet

**CIDR trùng lặp là một trong những blocker phổ biến nhất của hybrid/multicloud.** Nếu on-prem dùng 10.20.0.0/16 và VPC GCP cũng dùng 10.20.0.0/16, traffic giữa hai phía không có đường định tuyến rõ ràng theo nhu cầu.

Ví dụ kế hoạch IP:

| Vùng | CIDR minh họa | Chú ý |
|---|---|---|
| On-prem datacenter A | 10.10.0.0/16 | ERP, database |
| On-prem datacenter B | 10.11.0.0/16 | Backup/DR |
| GCP prod VPC | 10.20.0.0/16 | Tách subnets theo region |
| GCP dev VPC | 10.21.0.0/16 | Không route sang prod nếu không cần |
| AWS partner VPC | 10.30.0.0/16 | Kết nối hạn chế theo API |
| GKE Pod ranges | 10.40.0.0/16 | Kiểm tra secondary ranges |
| GKE Service ranges | 10.41.0.0/20 | Cần xem routing/NAT cho từng flow |

Các CIDR chỉ để minh họa. Địa chỉ thực tế phải lấy từ IP Address Management (IPAM) của tổ chức.

### Các bước lập IP plan

1. Thu thập IP từ vSphere/CMDB, router, firewall, AWS VPC, Azure VNet và GCP VPC.
2. Đối chiếu overlap giữa các mạng có thể trao đổi route.
3. Dự trù Pod/service ranges của GKE và mạng của database/private services.
4. Chọn subnet theo region/environment/security zone.
5. Quyết định tuyến nào được quảng bá qua BGP.
6. Nếu không thể renumber, thiết kế NAT hoặc proxy theo use case và đánh giá giới hạn.
7. Lưu IP allocations trong nguồn sự thật có owner.

### Lưu ý về routes

Routes trong GCP VPC không có nghĩa mọi service đều có reachability. Cloud Run/private connectivity, load balancer, Private Service Connect, Cloud SQL private IP và GKE Pod IP có cơ chế routing riêng. Với mỗi đường ứng dụng, hãy kiểm tra source, destination, next hop, firewall, DNS và cơ chế trả lời (return path).

## 6. Chọn HA VPN cho kết nối linh hoạt và có mã hóa

Cloud VPN tạo IPsec VPN tunnels từ VPC tới peer network qua internet công cộng. **HA VPN** là lựa chọn khuyến nghị khi peer hỗ trợ BGP và cần high availability; **Classic VPN** là dạng cũ dùng static routing.

### So sánh

| Đặc điểm | HA VPN | Classic VPN |
|---|---|---|
| Routing | BGP động qua Cloud Router | Static routing |
| Redundancy | Hai interfaces trên HA VPN gateway, nhiều tunnel | Tùy thiết kế redundancy |
| Availability SLA | Có thể đạt 99,99% với topology đạt điều kiện | Thường 99,9% |
| IPsec encryption | Có | Có |
| IPv6 | Hỗ trợ theo cấu hình | Không hỗ trợ |
| Khuyến nghị | Kết nối hybrid mới khi peer hỗ trợ | Khi buộc dùng static routing |

Mức SLA phải được xác minh theo topology và điều kiện dịch vụ, không suy ra mọi cấu hình HA VPN tự đạt 99,99%.

### Luồng triển khai

1. Tạo VPC/subnet trong project network host.
2. Tạo HA VPN gateway.
3. Đăng ký peer VPN gateway với IP/interfaces thích hợp.
4. Tạo Cloud Router có ASN phù hợp.
5. Tạo các VPN tunnels và BGP peers.
6. Quảng bá đúng prefixes, kiểm soát ưu tiên và route filters.
7. Test kết nối và failover từng tunnel.
8. Bật monitoring và alerts cho tunnel/BGP health.

### Vì sao dùng BGP?

BGP giúp hai bên trao đổi IP prefixes và cập nhật route khi topology thay đổi. Khi một tunnel hỏng, routes được cập nhật theo BGP và VPC routing rules, có thể chuyển sang đường còn hoạt động nếu cấu hình redundancy đúng.

Không chỉ kiểm tra "tunnel up"; cần xác nhận route nhận được, route quảng bá, next hop thực tế và application connectivity.

## 7. Cloud Router: control plane, không phải data plane

Cloud Router quản lý **BGP sessions** và các dynamic routes. Cloud Router **không trực tiếp chuyển tiếp application packets**; data forwarding do hạ tầng mạng VPC thực hiện.

~~~text
  On-prem BGP Router
          |
          | BGP route advertisements
          v
       Cloud Router
          |
          | Routes learned/advertised
          v
  GCP VPC dynamic route control
          |
          v
  VPC data plane -> Workload
~~~

### Quyết định routing quan trọng

- Chọn regional/global dynamic routing mode theo nhu cầu VPC.
- Sử dụng ASN không xung đột trong các peer BGP cần thiết.
- Chỉ quảng bá subnet/summary prefixes được phép.
- Dùng priority/MED/route policy theo khả năng hỗ trợ để tránh đường đi bất cân xứng ngoài ý muốn.
- Đặt route filtering và chống quảng bá nhầm default route.
- Kiểm tra route propagation giữa nhiều VPC và các môi trường.
- Có runbook cho BGP session down, route mất, asymmetric path và MTU issue.

**Không để một thay đổi BGP nhỏ vô tình quảng bá dải mạng production ra mọi spoke.** Cấu hình route exchange phải review giống thay đổi firewall và IAM.

## 8. Cloud Interconnect: đường truyền riêng, hiệu năng và trách nhiệm

Cloud Interconnect kết nối on-prem tới mạng Google thông qua kết nối dedicated hoặc qua đối tác.

| Loại | Đường kết nối | Khi phù hợp |
|---|---|---|
| Dedicated Interconnect | Kết nối vật lý trực tiếp tại vị trí colocation được hỗ trợ | Băng thông lớn, hệ thống đã có hạ tầng colocation |
| Partner Interconnect | Qua nhà cung cấp kết nối được hỗ trợ | Không có hiện diện trực tiếp hoặc cần mức băng thông linh hoạt |
| Cross-Cloud Interconnect | Dedicated physical connectivity giữa Google Cloud và một cloud provider khác | Lưu lượng cross-cloud lớn, ổn định |
| Partner Cross-Cloud Interconnect | Qua đối tác/cloud partner được hỗ trợ | Muốn kết nối private cross-cloud qua dịch vụ đối tác |

### Cloud Interconnect không mã hóa dữ liệu mặc định

Đường truyền dedicated/partner không tự tạo IPsec encryption. Nếu cần confidentiality trên transport:

- Dùng **HA VPN over Cloud Interconnect** để bảo vệ traffic qua IPsec theo topology được hỗ trợ.
- Dùng **MACsec** trên các Cloud Interconnect circuits hỗ trợ để bảo vệ link layer.
- Hoặc dùng TLS/mTLS ở tầng ứng dụng, thường vẫn nên thực hiện kể cả khi mạng private.

Đánh giá khả năng hỗ trợ trên loại kết nối và region cụ thể trước khi chọn; yêu cầu regulatory có thể bắt buộc bảo vệ nhiều lớp.

### Tại sao cần redundant links?

Với workload quan trọng:

- Đảm bảo đa dạng failure domains theo location/edge availability domain.
- Thiết kế primary và redundant connections.
- Bảo đảm router/ISP tại nguồn không cùng một single point of failure.
- Có HA VPN hoặc Interconnect backup khi phù hợp.
- Kiểm tra route priorities và failover behavior.
- Đo throughput, MTU, egress và chất lượng mạng trong thực tế.

Không chỉ mua hai VLAN attachments trên một kết nối vật lý rồi coi đó là kiến trúc không có single point of failure.

### Các nguồn chi phí

- Port hoặc attachment fees.
- Phí dịch vụ network provider.
- Data transfer/egress theo hướng và location.
- VPN gateway/tunnel hoặc encryption overlay khi dùng.
- Equipment, cross-connect và operations.
- Nhân sự vận hành, monitoring và change management.

So sánh TCO với HA VPN cần dựa trên lưu lượng, latency, SLA và cost per GB, không chỉ đơn giá cổng kết nối.

## 9. Cross-Cloud Interconnect và multi-provider network

Cross-Cloud Interconnect được thiết kế cho kết nối băng thông cao giữa Google Cloud và một số nhà cung cấp cloud được hỗ trợ, như AWS, Azure, OCI và Alibaba Cloud theo tài liệu hiện hành.

Ví dụ:

~~~text
        AWS VPC / Transit Gateway
                 |
         AWS-side connectivity
                 |
      Cross-Cloud Interconnect
                 |
          Google Cloud VPC
                 |
          Cloud Run / GKE
~~~

Vì kết nối private không đồng nghĩa mã hóa, nên cần kế hoạch TLS/mTLS, MACsec hoặc phương án bảo vệ phù hợp. Quy trình triển khai còn bao gồm provisioning và coordination với cả nhà cung cấp cloud phía đối diện; không thể cấu hình một phía rồi mong đường truyền hoạt động.

### Chọn VPN hay Cross-Cloud Interconnect?

- API call không thường xuyên, dữ liệu ít: HTTPS qua internet có xác thực có thể đơn giản và đủ an toàn.
- Lưu lượng vừa phải và cần private connectivity: HA VPN giữa hai phía có thể phù hợp.
- Lưu lượng rất lớn, ổn định và cần network performance dự đoán được: xem Cross-Cloud Interconnect hoặc đối tác.
- Cross-cloud active-active: phải tính cả data consistency, routing, failover và chi phí egress, không chỉ đường truyền.

Không biến mọi kết nối giữa hai clouds thành full mesh VPC; phân đoạn network theo ứng dụng và least privilege.

## 10. Network Connectivity Center (NCC): điều phối hub/spoke

NCC cho phép tạo **hub** liên kết các loại **spokes** được hỗ trợ:

- VPC spokes: nối nhiều VPC và trao đổi subnet routes theo NCC topology.
- Hybrid spokes: HA VPN tunnels, Cloud Interconnect VLAN attachments và router appliance.
- Một số loại spoke khác như producer VPC và NCC Gateway phục vụ kịch bản chuyên biệt.

Một hub là tài nguyên quản trị toàn cục cho nhiều spokes; một spoke có thể có các ràng buộc project/network và loại backing resource khác nhau.

### Giá trị của NCC

- Giảm số kết nối point-to-point cần vận hành.
- Dễ quản lý topology nhiều VPC, hybrid routes và site-to-site.
- Cho phép mô hình kết nối giữa nhiều network projects.
- Có công cụ route exchange/filtering theo loại spoke.
- Hỗ trợ network segmentation bằng thiết kế spoke group/route policy phù hợp.

### Những hiểu nhầm cần tránh

- **NCC không tự vượt firewall rules, IAM hay IP overlap.**
- VPC spokes không quảng bá mọi loại route như peering/static/dynamic routes trong mọi tình huống; phải đọc rõ quy tắc export/import.
- Hybrid spokes cần backing resource (VPN tunnel, VLAN attachment hoặc router appliance) đã được cấu hình.
- Một số use cases site-to-site có điều kiện network/project riêng.
- Một hub không có nghĩa mọi service trong tất cả VPC tự động được phép truy cập nhau.

Hãy dùng sơ đồ route từ source đến destination, test network path và định nghĩa allowed prefixes/traffic flows cụ thể.

## 11. Shared VPC, Peering và NCC khác nhau thế nào?

| Công nghệ | Mục tiêu | Ranh giới |
|---|---|---|
| Shared VPC | Nhiều service projects dùng chung network/subnet của host project | Centralized network ownership |
| VPC Network Peering | Liên thông hai VPC theo routing constraints | Peering không tự transitive |
| NCC VPC spokes | Kết nối nhiều VPC qua hub với route exchange được hỗ trợ | Cần cấu hình hub/spoke và routing |
| HA VPN/Interconnect | Kết nối VPC với on-prem hoặc cloud khác | Cần peer, route, firewall và DNS |
| Private Service Connect | Truy cập dịch vụ qua private endpoint theo mô hình producer/consumer | Không phải thay thế general-purpose VPC transit |

Không xây topology giả định peering A-B và B-C cho phép A-C tự động truy cập. Với hub/spoke, phải kiểm tra loại route được xuất/nhập và policy của từng thành phần.

## 12. Hybrid DNS: phân giải tên là một phần của connectivity

Một request Java đến **erp.corp.example.com** có thể thất bại dù VPN đã thông, nếu GCP không biết phân giải tên nội bộ. Tương tự, on-prem cần có cách truy cập tên dịch vụ trong Cloud DNS private zone.

Mô hình tham khảo:

~~~text
GCP workload
     |
     v
Cloud DNS private/forwarding zones
     |
     +-- gcp.example.com -> Cloud DNS authoritative
     |
     +-- corp.example.com -> On-prem DNS server
                                   ^
                                   |
           On-prem DNS conditional forwarding
                    -> GCP inbound DNS forwarder
~~~

### Hai thành phần phổ biến

- **Outbound forwarding zone:** GCP chuyển truy vấn cho corp.example.com sang on-prem authoritative DNS.
- **Inbound forwarding policy:** on-prem có thể hỏi Cloud DNS cho zone private đã cấu hình qua forwarding IP.

### Những vấn đề cần kiểm tra

1. Private zone được authorize với đúng VPC.
2. DNS forwarding target và firewall port UDP/TCP 53 hoạt động.
3. On-prem DNS reachable qua VPN/Interconnect.
4. Return path và route đặc biệt cho Cloud DNS forwarders có được cấu hình đúng.
5. TTL, split-horizon DNS và negative caching phù hợp cutover.
6. Tên cloud và on-prem không tạo vòng lặp forwarding.
7. DNS query logs được bật khi điều tra, với lưu ý chi phí và dữ liệu nhạy cảm.

Tài liệu Cloud DNS cho outbound forwarding đến on-prem mô tả IP source range **35.199.192.0/19** và yêu cầu route/firewall phù hợp. Không áp dụng dải này cho mọi loại DNS hoặc mọi ứng dụng; kiểm tra đúng topology và tài liệu hiện hành.

### Ví dụ kiểm tra DNS từ workload

~~~bash
nslookup erp.corp.example.com
nslookup checkout.gcp.example.com
~~~

Khi có lỗi, phân biệt DNS NXDOMAIN, timeout, route unavailable và firewall denied. Không thay IP bằng giá trị hardcode trong source code Java để chữa lỗi tạm thời.

## 13. Identity và Zero Trust xuyên môi trường

Kết nối riêng chỉ giải quyết reachability. Một dịch vụ bên trong VPC hoặc on-prem vẫn cần xác minh danh tính và quyền truy cập.

### Phân chia các lớp bảo mật

| Lớp | Câu hỏi | Cơ chế |
|---|---|---|
| Network | Nguồn nào được nối tới đích? | Firewall, routes, Cloud VPN/Interconnect, network policies |
| Transport | Dữ liệu có được bảo vệ trên đường truyền? | TLS/mTLS, IPsec hoặc MACsec theo nhu cầu |
| Workload authentication | Dịch vụ nào đang gọi? | Service account, OIDC ID token, mTLS identities |
| Authorization | Caller được làm gì? | IAM, application RBAC/ABAC, resource/tenant policy |
| Data protection | Dữ liệu nào được truy cập và lưu? | Encryption, KMS, classification, DLP |
| Audit | Ai đã thay đổi hoặc truy cập? | Cloud Audit Logs, workload logs, SIEM |

### Service account và credential

- GCP workloads dùng runtime service accounts và ADC.
- External workloads ở on-prem/AWS/Azure có thể sử dụng **Workload Identity Federation** với identity provider phù hợp để nhận credential ngắn hạn, thay vì giữ service account key JSON dài hạn.
- Một số flows cần IAM service account impersonation và quyền liên quan.
- GKE workloads có cơ chế Workload Identity Federation for GKE riêng.
- Với service-to-service Cloud Run, dùng Google-signed ID token có audience phù hợp và role Invoker; không coi VPN là cơ chế authentication.
- Quản lý certificate và secret rotation theo policy, tránh lưu credential vào configmap hoặc source control.

### Phân biệt external WIF với GKE WIF

External Workload Identity Federation cho workload bên ngoài GCP dùng identity của môi trường nguồn để truy cập Google Cloud APIs. GKE Workload Identity Federation dùng danh tính Kubernetes trên GKE cho tương tác với IAM. Hai mô hình liên quan nhưng có cấu hình trust và principal khác nhau.

**Không cấp roles/owner chỉ để kiểm thử federation.** Tạo principal, audience, attribute mapping/conditions và role tối thiểu; thử các trường hợp đúng/sai identity.

## 14. Firewall, segmentation và bảo vệ đường truyền

Một network topology có thể cho phép route nhưng vẫn bị chặn bởi firewall. Trong hybrid/multicloud:

- Định nghĩa network zones: user-facing, app, data, management, DR.
- Chỉ mở port/protocol cần thiết theo source/destination cụ thể.
- Dùng hierarchical firewall policy khi phù hợp với organization.
- Không quảng bá 0.0.0.0/0 qua BGP chỉ để sửa lỗi connectivity.
- Không mở toàn bộ RFC 1918 từ on-prem tới production VPC.
- Kiểm tra cả GCP firewall, on-prem firewall và security groups/NSG ở cloud đối diện.
- Dùng TLS/mTLS cho API có dữ liệu nhạy cảm, kể cả trên private link.
- Áp dụng egress policy để giảm rủi ro data exfiltration.
- Xác định điểm kiểm tra traffic, IDS/IPS và logging phù hợp.

**VPC Service Controls** có thể giảm nguy cơ rò rỉ qua một số Google Cloud APIs trong service perimeter được hỗ trợ, nhưng không phải firewall chung cho mọi TCP/IP flow. Cần thiết kế perimeter và exception rõ.

## 15. Nền tảng ứng dụng: Cloud Run, GKE và Google Distributed Cloud

### Cloud Run

Phù hợp khi service Java được container hóa, stateless hoặc state được chuyển ra database/queue. Nếu ứng dụng cần truy cập private on-prem resources, phải cấu hình private network egress và đường VPC tương ứng; không mặc định service có route tới datacenter chỉ vì project đã có VPN.

Ưu điểm:

- Giảm vận hành cluster.
- Autoscale theo request và concurrency.
- Tích hợp IAM, Secret Manager, Cloud Logging và CI/CD.

Ràng buộc:

- Startup/shutdown, CPU allocation và background work.
- Concurrency, connection pools nhân theo số instances.
- Latency tới dependency on-prem ảnh hưởng trực tiếp request.
- Với workloads cần chạy nền đáng tin cậy, cân nhắc Pub/Sub, Cloud Tasks hoặc Cloud Run jobs.

### GKE

Phù hợp khi cần Kubernetes orchestration, advanced networking, sidecars, service mesh và lifecycle control. Dùng VPC-native GKE, Pod/service IP planning và Workload Identity Federation. Không giả định Pod IP luôn routable từ on-prem; cần kiểm tra network policy, masquerading, node routing và các yêu cầu kết nối.

### GKE Multi-Cloud

Google Cloud có giải pháp quản lý Kubernetes clusters trong các môi trường AWS/Azure hoặc attach clusters phù hợp. Khả năng và mô hình quản lý khác nhau tùy cluster option; kiểm tra service support, regions, API và lifecycle mới nhất trước khi chuẩn hóa.

**Kubernetes có API tương đối nhất quán, nhưng storage, load balancing, identity, network và control-plane operations vẫn khác giữa cloud providers.** Không kết luận rằng container có thể chuyển provider mà không cần kiểm thử hạ tầng phụ thuộc.

### Google Distributed Cloud

Một số workload phải chạy tại edge hoặc cơ sở có latency thấp, yêu cầu dữ liệu ở tại chỗ hoặc kết nối không ổn định. Google Distributed Cloud có các lựa chọn theo môi trường, chẳng hạn connected hoặc air-gapped, với mô hình quản lý/đồng bộ khác nhau. Chỉ chọn khi có nhu cầu thật về edge/data locality và chấp nhận yêu cầu phần cứng, lifecycle, connectivity và hỗ trợ tương ứng.

## 16. Thiết kế ứng dụng Java/Spring trong hybrid cloud

Ví dụ checkout-service trên Cloud Run cần gọi ERP API tại on-prem.

### Kiến trúc gọi đồng bộ

~~~text
Frontend
   |
   v
Spring Boot Checkout on Cloud Run
   |
   | HTTPS + application identity
   v
VPC egress / HA VPN or Interconnect
   |
   v
ERP API on-prem
   |
   v
ERP database
~~~

Quy trình đúng:

1. ERP API có contract, TLS và authentication rõ ràng.
2. Cloud Run có route tới ERP qua VPC egress và hybrid connection.
3. Cloud DNS phân giải tên ERP.
4. Firewall chỉ cho phép source/workload đã được phê duyệt.
5. Java client có connect timeout, read timeout, retries có giới hạn.
6. ERP API có idempotency key cho thao tác có side effects.
7. Distributed trace/log có correlation ID xuyên hai môi trường.
8. Khi ERP lỗi, Checkout phản hồi theo business rule chứ không đợi vô hạn.

### Một ví dụ Spring RestClient cấu hình timeout

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration
class ErpClientConfig {

    @Bean
    RestClient erpRestClient() {
        var httpClient = java.net.http.HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .build();

        var requestFactory = new JdkClientHttpRequestFactory(httpClient);
        requestFactory.setReadTimeout(Duration.ofSeconds(5));

        return RestClient.builder()
            .baseUrl("https://erp.corp.example.com")
            .requestFactory(requestFactory)
            .build();
    }
}
~~~

Đoạn mã minh họa timeout cho Java/Spring Boot phiên bản hỗ trợ RestClient; chưa bao gồm mutual TLS, auth, retry, error mapping hay cấu hình endpoint theo môi trường. Trong production, lấy base URL từ @ConfigurationProperties đã validation và dùng secret/certificate manager được phê duyệt, không hardcode credential.

### Vì sao timeout quan trọng?

Nếu request của Checkout có deadline 3 giây nhưng read timeout tới ERP là 30 giây, luồng xử lý có thể vượt SLO, giữ connection và tích tụ queue. Thiết lập deadline tổng, retry budget và bulkhead/concurrency limit phù hợp với latency thực tế xuyên mạng.

### Khi nào đổi sang asynchronous?

Nếu ERP chỉ cần biết đơn mới sau vài giây, dùng Pub/Sub hoặc task queue để giảm phụ thuộc trực tiếp. Ở bên on-prem có thể có connector/worker với đường truy cập, xác thực và retry riêng. Thiết kế idempotency, dead-letter queue và monitoring vì các thông điệp có thể được giao lại.

## 17. Dữ liệu xuyên môi trường: chọn luồng phù hợp

Dữ liệu thường là phần khó nhất khi vận hành hybrid/multicloud:

| Nhu cầu | Mô hình cân nhắc | Rủi ro |
|---|---|---|
| Di chuyển database một lần | Export/import, database migration tool phù hợp | Downtime, version incompatibility |
| Đồng bộ database liên tục | CDC/replication theo khả năng engine | Lag, ordering, schema drift |
| Chuyển tập tin định kỳ | Storage Transfer Service hoặc pipeline được hỗ trợ | Egress, checksum, ACL, retention |
| Stream events | Pub/Sub, Kafka/connector, Dataflow | At-least-once delivery, duplicates |
| Dữ liệu phân tích cross-cloud | Batch export/ELT hoặc giải pháp query hỗ trợ | Cost, latency, governance |
| DR replication | Database/storage replication theo RPO | Split-brain, failover và failback |

### Ownership và system of record

Quy định hệ thống nào là **source of truth** cho từng tập dữ liệu. Không để cả database on-prem và Cloud SQL cùng nhận ghi độc lập mà không có conflict-resolution protocol.

Các nguyên tắc:

- Xác định schema owner và cách version hóa.
- Có data classification, retention, encryption và key ownership.
- Đo replication lag và checkpoint.
- Kiểm tra consistency bằng checksum, counts hoặc reconciliation queries.
- Định nghĩa RPO khi failover và điều kiện failback.
- Không sao chép toàn bộ dữ liệu nhạy cảm lên nhiều cloud nếu use case chỉ cần aggregate.
- Tính chi phí egress, storage, transfer và vận hành khi đồng bộ liên tục.

### Khi nào dữ liệu nên ở gần compute?

Nếu API cần nhiều round trips đồng bộ đến database xuyên VPN, latency tăng nhanh. Có thể:

- Di chuyển compute tới gần data.
- Di chuyển database cùng application group.
- Dùng read replica/cache có consistency policy.
- Đổi critical path sang event-driven khi business semantics cho phép.
- Tách analytics ra khỏi transaction path.

Không chọn cache đơn giản khi hệ thống yêu cầu strong consistency cho tài chính hoặc tồn kho mà chưa có cơ chế invalidate/reconciliation.

## 18. Reliability và disaster recovery

Hybrid/multicloud tạo thêm dependency links và failure modes. Một link hỏng có thể ảnh hưởng hàng loạt service dù các VM/pod đều healthy.

### Các mô hình availability

| Mô hình | Ý tưởng | Độ phức tạp |
|---|---|---|
| Active-passive | Một nơi phục vụ, nơi khác sẵn sàng nhận tải | Trung bình, cần failover plan |
| Active-active | Hai môi trường cùng phục vụ | Cao, cần global routing/data consistency |
| Split-by-domain | Mỗi môi trường xử lý một nghiệp vụ riêng | Thấp hơn active-active, phụ thuộc integration |
| Edge autonomy | Edge xử lý offline, đồng bộ khi kết nối lại | Cao về conflict/reconciliation |

### RTO và RPO

- **RTO**: thời gian tối đa cho phép để phục hồi chức năng sau sự cố.
- **RPO**: lượng dữ liệu tối đa có thể mất, thường tính theo khoảng thời gian.

Ví dụ ERP on-prem có RTO 30 phút, RPO 5 phút. Chỉ có HA VPN dự phòng không chứng minh đạt RTO/RPO này: còn database replication, application warm-up, DNS failover, credentials, network routes và business validation.

### Active-active không đơn giản

Nếu đơn hàng cùng lúc được nhận ở GCP và AWS nhưng cả hai ghi vào dữ liệu riêng, cần quy tắc:

- Phân vùng ownership theo tenant/order hoặc single-writer model.
- Conflict resolution và ordering.
- Idempotency và replay.
- Thời điểm commit được coi là thành công.
- Khôi phục sau network partition.
- Quản lý global IDs, clocks và timestamps.

Nếu chưa giải được semantics dữ liệu, active-passive hoặc domain split thường an toàn hơn.

### Failover drill

Phải thử:

1. Một tunnel VPN down.
2. BGP neighbor down hoặc mất prefix.
3. DNS server on-prem ngừng đáp ứng.
4. Mất một region/zone.
5. Provider khác chậm hoặc giới hạn API.
6. Replication lag tăng.
7. Credentials hết hạn hoặc service account bị revoke.
8. Traffic chuyển hướng rồi quay lại (failback).

Đo time-to-detect, time-to-failover, time-to-recover và dữ liệu bị ảnh hưởng. Không chỉ kiểm tra ping hoặc trạng thái gateway UP.

## 19. Observability xuyên GCP, on-prem và cloud khác

Một request có thể đi qua Cloud Run, VPN, ERP và AWS payment API. Khi lỗi xảy ra, không có một dashboard đơn lẻ tự giải thích toàn bộ đường đi.

### Các tín hiệu quan trọng

| Lớp | Metrics/logs | Công cụ/nguồn |
|---|---|---|
| VPC/network | Throughput, drops, firewall denied, flow logs | Cloud Monitoring, VPC Flow Logs |
| VPN/Interconnect | Tunnel state, BGP sessions, link utilization, errors | Cloud VPN/Interconnect monitoring |
| DNS | Query latency, NXDOMAIN, forwarding failures | Cloud DNS logs và on-prem DNS |
| Applications | Request rate, 5xx, p95/p99, queue depth | Cloud Monitoring/Logging, OpenTelemetry |
| IAM/security | Permission denied, changes to policies, token failures | Cloud Audit Logs và SIEM |
| Data pipeline | Replication lag, checksum mismatches, retries | Database/transfer tooling |
| Billing | Egress by region/provider, interconnect/VPN, storage | Cloud Billing/BigQuery export |

### Dùng trace correlation

Java/Spring có thể dùng OpenTelemetry trace/span IDs. Với downstream ERP, truyền trace context qua HTTP headers khi hai bên hỗ trợ; không đưa bearer token vào telemetry. Nếu hệ thống khác dùng định dạng trace khác, có thể cần gateway hoặc logging correlation rõ ràng.

### Kịch bản điều tra 503

1. Xem service 503 rate và thời điểm bắt đầu.
2. So sánh với change log/deploy và IAM changes.
3. Kiểm tra DNS resolve tới ERP.
4. Kiểm tra firewall/routing/BGP/tunnel health.
5. Đo latency, packet loss và MTU.
6. Xem ERP availability và connection limits.
7. Nếu link lỗi, kích hoạt failover hoặc degraded mode theo runbook.
8. Kiểm tra business requests đã hoàn tất/đã retry sau khôi phục.

## 20. IaC, governance và vận hành đa môi trường

### Infrastructure as Code

Terraform có thể quản lý VPC, Cloud Router, VPN, firewall, IAM và các thành phần GCP khác. Với multicloud, có thể dùng nhiều provider plugins nhưng cần:

- State và quyền riêng theo ranh giới ownership.
- Không để một pipeline có quyền quản trị mọi cloud nếu không thực sự cần.
- Version pinning và review thay đổi định tuyến/phân quyền.
- Change plan cho production và rollback được thử.
- Không lưu state/credentials công khai.
- Tách network platform layer khỏi application layer phù hợp.

### Thay đổi mạng có blast radius lớn

Một route advertisement hoặc firewall policy sai có thể cắt toàn bộ kết nối ERP. Do đó:

- Có peer review bởi network owners ở cả hai phía.
- Có maintenance window cho thay đổi đáng kể.
- Có tài khoản/đường quản trị ngoài luồng trong trường hợp mất kết nối.
- Sao lưu cấu hình BGP/routers và các route sets trước thay đổi.
- Có plan rollback và tiêu chí xác nhận.
- Có kênh liên lạc và incident commander khi thay đổi hệ thống trọng yếu.

### Governance nhiều provider

Sử dụng policy-as-code, inventory, organization-level constraints và quy trình approval chung. Tuy nhiên, **đừng giả định một policy viết trên GCP sẽ tự áp dụng trên AWS/Azure**. Cần ánh xạ control objectives sang từng native IAM/network/data service, rồi kiểm tra hiệu lực riêng.

### Ownership model

| Thành phần | Owner |
|---|---|
| Enterprise IPAM, BGP policies | Network team |
| VPC/Shared VPC/NCC | Cloud platform |
| Cloud VPN/Interconnect | Network + provider/carrier |
| Service account federation | Security/IAM |
| Java API contract, timeouts | Application team |
| Database replication và schema | Data/DBA |
| Business cutover và RTO/RPO | Product/business owner |
| Monitoring, incident response | SRE/Operations |
| Billing, egress cost | FinOps |

Một đường kết nối đa cloud thường cần phối hợp ít nhất hai nhóm/platform. Phải ghi rõ ai xử lý sự cố ở từng đầu link.

## 21. FinOps cho hybrid và multicloud

Một hệ thống hybrid có thể phát sinh chi phí ở nhiều nơi cùng lúc:

- VM/Cloud Run/GKE usage trong GCP.
- VPN tunnel, Interconnect ports/attachments và partner circuit.
- Data egress từ GCP, provider còn lại và ISP.
- Cloud Storage/BigQuery, snapshot và replication.
- Database license, nhân sự on-prem, colocation và hardware.
- Monitoring/SIEM/observability duplication.
- Lưu lượng truyền chéo region hoặc cloud.
- Chi phí kiến trúc dự phòng và failover drill.

### Nguyên tắc tính chi phí

Không chỉ cộng giá VM của hai cloud. Hãy xây mô hình **cost per successful transaction** hoặc **cost per GB processed** có tính latency và năng lực khôi phục.

Ví dụ giả định:

| Mục | Chi phí tháng |
|---|---:|
| GCP app compute | 1.200 USD |
| On-prem ERP operation allocation | 700 USD |
| Network links và VPN/Interconnect | 450 USD |
| Cross-cloud egress | 300 USD |
| Monitoring, logs và transfer | 150 USD |
| Tổng minh họa | 2.800 USD |

Các con số minh họa, không phải bảng giá GCP. Chi phí thực phụ thuộc SKUs, region, traffic, discount, đối tác và cam kết.

### Chiến lược giảm chi phí

- Đưa compute tới gần data khi egress/latency là yếu tố chính.
- Giảm vòng gọi API đồng bộ qua mạng nhiều cloud.
- Dùng batch/async cho dữ liệu không yêu cầu realtime.
- Nén/lọc dữ liệu trước khi chuyển, khi phù hợp.
- Không truyền dữ liệu nhạy cảm thô nếu chỉ cần aggregate.
- Theo dõi nhãn owner/cost center và actual egress.
- So sánh Interconnect với VPN theo throughput/SLA thực tế.
- Không duy trì DR/standby resources mà không review RTO/RPO và utilization.

## 22. Lộ trình triển khai hybrid cloud từng bước

Một migration từ on-prem sang GCP thường nên có các wave:

| Wave | Công việc | Tiêu chí hoàn tất |
|---|---|---|
| 0 – Assessment | Inventory, IPAM, dependency map, SLA, ownership | Không còn blocker connectivity quan trọng |
| 1 – Landing zone | Organization/projects/VPC/IAM/logging/policy | Guardrails hoạt động |
| 2 – Connectivity pilot | HA VPN/BGP, DNS, firewall, test apps | Reachability, failover và security tests đạt |
| 3 – Application pilot | Container Java/Spring chạy trên GCP, gọi ERP on-prem | SLO, auth và rollback được xác nhận |
| 4 – Data migration/sync | CDC, transfer hoặc coexistence | Consistency và RPO trong ngưỡng |
| 5 – Production cutover | Load balancing/DNS/traffic shift | Business transactions và telemetry đạt |
| 6 – Optimization | Rightsizing, data placement, decommission | Savings thực tế, không còn dependency cũ |

### Khi nào chọn Interconnect thay VPN?

Bắt đầu với requirements: băng thông, latency, bảo mật, SLA, địa điểm và forecast traffic. VPN phù hợp pilot nhanh, nhưng không phải luôn là long-term choice cho data movement lớn. Interconnect cần provisioning lead time và phối hợp carrier/colocation; lập kế hoạch sớm trước cutover.

### Rollback trong hybrid khác rollback code

Đổi phiên bản ứng dụng có thể dễ rollback, nhưng chuyển database writer hoặc thay routing/DNS lớn khó hơn. Phải xác định rollback point, data reconciliation và quyết định cutback/failback trước khi chạy migration.

## 23. Bài thực hành 1: kết nối Java API trên GCP với ERP on-prem

**Bối cảnh:** checkout-service đã container hóa trên Cloud Run. ERP database vẫn nằm tại datacenter, được truy cập qua ERP HTTPS API. Yêu cầu:

- Không cấp public IP cho ERP.
- Checkout chỉ truy cập ERP qua private hybrid connectivity.
- ERP bắt buộc TLS và service-to-service authentication.
- Đường mạng chịu được một tunnel lỗi.
- p95 gọi ERP phải dưới ngưỡng do application owner phê duyệt.
- Có fallback và runbook khi ERP không khả dụng.

### Bước A – Thiết kế topology

~~~text
Cloud Run Checkout
     |
 Direct VPC egress / supported connector
     |
 Shared VPC prod
     |
 HA VPN + Cloud Router/BGP
    / \
 Tunnel A  Tunnel B
    \ /
 On-prem VPN gateways
     |
 ERP API over HTTPS
~~~

### Bước B – Kiểm tra tài nguyên hiện có

Lệnh chỉ đọc (đổi placeholder và xác minh đúng project):

~~~bash
gcloud compute networks list --project=PROJECT_ID

gcloud compute networks subnets list --project=PROJECT_ID

gcloud compute routers list --project=PROJECT_ID

gcloud compute vpn-gateways list --project=PROJECT_ID

gcloud compute vpn-tunnels list --project=PROJECT_ID
~~~

Để xem trạng thái một Cloud Router/BGP:

~~~bash
gcloud compute routers get-status ROUTER_NAME \
  --project=PROJECT_ID \
  --region=REGION
~~~

Cần quyền xem network resources. Các lệnh không tạo VPN hay thay route; người học phải làm việc với network owner để xác nhận topology đã được cấp phép.

### Bước C – DNS và authentication

- Tạo forwarding zone cho corp.example.com theo mạng phù hợp.
- Kiểm tra DNS từ GCP workload tới erp.corp.example.com.
- Cấu hình TLS, CA trust, mTLS hoặc token identity theo hệ thống ERP.
- Không đưa credential vào application.yml trong Git.
- Dùng Secret Manager hoặc workload identity mechanism phù hợp.

### Bước D – Kiểm thử

| Test | Kỳ vọng |
|---|---|
| DNS query tới ERP | Resolve đúng IP nội bộ |
| TCP/TLS handshake | Thông khi auth/trust hợp lệ |
| Gọi với identity hợp lệ | Thành công trong latency budget |
| Gọi với identity không hợp lệ | Bị từ chối |
| Tắt tunnel A | Tunnel B tiếp tục route nếu topology đúng |
| DNS on-prem down | Có alert/runbook, không treo vô hạn |
| ERP trả 503 | Checkout có retry budget/degraded mode |
| Deploy revision mới | Không mất cấu hình egress/IAM |

### Bước E – Handoff

Tài liệu phải có sơ đồ nguồn/đích, route prefixes, DNS policies, SLO, contact on-call của hai phía, thủ tục rollback và dashboard link. Không kết thúc pilot chỉ vì ping chạy được.

## 24. Bài thực hành 2: tích hợp một API trên AWS với GCP

**Bối cảnh:** Orders API trên GCP cần gọi Risk Scoring API của đối tác nằm trên AWS. Lưu lượng khoảng vài nghìn request mỗi ngày; dữ liệu truyền nhỏ và được mã hóa.

### Chọn kết nối

Đội kiến trúc so sánh:

| Phương án | Ưu điểm | Trade-off |
|---|---|---|
| HTTPS public endpoint với OIDC/mTLS và allowlist phù hợp | Nhanh, ít thành phần network | Phụ thuộc internet/public endpoint controls |
| HA VPN cross-cloud | Kết nối private IPsec, route động | Thiết kế peer/BGP, throughput và vận hành |
| Cross-Cloud Interconnect | Network performance cho traffic lớn | Provisioning và chi phí cố định cao hơn |

Nếu lưu lượng nhỏ, không có yêu cầu private networking bắt buộc và API có xác thực an toàn, HTTPS thường đơn giản hơn. Không thiết kế Cross-Cloud Interconnect chỉ vì có hai clouds.

### Các kiểm thử cần có

- Identity và authorization không dựa vào IP nguồn đơn thuần.
- TLS certificate validation và rotation.
- Audience, token expiry và replay protections nếu dùng OIDC.
- SLA của Risk Scoring API và retry semantics.
- Timeout của Orders API khi AWS endpoint chậm.
- Phân loại dữ liệu được phép chuyển sang provider khác.
- Cost/egress và observability tương ứng.
- Cơ chế fail-closed/fail-open theo chính sách nghiệp vụ, không mặc định.

Nếu sau này traffic tăng nhiều, có thể đánh giá lại VPN hoặc Interconnect bằng dữ liệu thực tế.

## 25. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Hai môi trường dùng CIDR overlap | Route mơ hồ, không kết nối được | IPAM trước khi tạo mạng |
| Dùng một VPN tunnel cho production quan trọng | Single point of failure | HA VPN/BGP có topology đủ SLA |
| Nghĩ Cloud Router là traffic router | Hiểu sai data path và metrics | Tách control plane và VPC forwarding |
| Coi Interconnect mặc định mã hóa | Rủi ro dữ liệu trên transport | TLS/mTLS, MACsec hoặc HA VPN over Interconnect |
| Coi VPN lên là ứng dụng đã chạy | DNS, firewall, auth có thể vẫn lỗi | Test end-to-end theo luồng nghiệp vụ |
| Coi NCC tự nối mọi mạng | Route/policy không tự đúng | Verify hub/spokes, export/import và filters |
| Dùng VPC Peering như transit tự động | A không tự route qua B tới C | Chọn topology NCC/Router appliances phù hợp |
| Đặt cùng service account trên mọi cloud | Rủi ro credential và quyền rộng | Federation, least privilege và rotation |
| Gọi database cross-cloud quá nhiều round trips | p99 latency/egress cao | Co-locate, cache có policy hoặc async |
| Active-active nhưng không có conflict resolution | Split-brain, dữ liệu không nhất quán | Single-writer/partitioning/reconciliation |
| Không có hybrid DNS strategy | Name resolution thất bại | Forwarding zones/inbound policies có test |
| Cho Dev đi qua toàn bộ prod network | Tăng blast radius | Network segmentation, IAM và policies |
| Không tính egress/provider cost | TCO đánh giá sai | Billing analytics theo hướng và nguồn |
| Không kiểm thử failover của BGP/DNS | Đứt kết nối khi một link lỗi | Chaos/drill và runbook |
| Chọn multicloud để tránh lock-in theo khẩu hiệu | Đội ngũ chịu thêm chi phí/độ phức tạp | Chọn theo business case và SLO |

## 26. Checklist thiết kế production

### Nhu cầu và kiến trúc

- [ ] Có lý do nghiệp vụ rõ cho hybrid/multicloud.
- [ ] Đã xác định RTO, RPO, SLO và latency budgets.
- [ ] Có inventory applications, data, dependencies và owners.
- [ ] Đã chọn mô hình active-passive, domain split hoặc active-active có cơ sở.
- [ ] Không mặc định workload phải chạy được trên mọi cloud.

### Network và DNS

- [ ] IP ranges không overlap trong những mạng cần giao tiếp.
- [ ] VPC/Shared VPC/subnet/secondary ranges được review.
- [ ] HA VPN hoặc Interconnect được chọn theo throughput, SLA, cost.
- [ ] Có redundancy thật về router/link/zone và route failover.
- [ ] BGP advertisements/route imports/exports có chính sách rõ.
- [ ] NCC hub/spoke không tạo kết nối ngoài ý muốn.
- [ ] Cloud DNS forwarding, split-horizon và TTL được kiểm chứng.
- [ ] Network ingress/egress và firewall kiểm tra cả hai chiều.
- [ ] TLS/IPsec/MACsec được áp dụng theo dữ liệu và compliance.

### Identity, ứng dụng và dữ liệu

- [ ] Mỗi workload có identity và IAM tối thiểu.
- [ ] External WIF hoặc GKE WIF được cấu hình đúng use case.
- [ ] Không lưu static service account key trong source/image.
- [ ] API authorization thực hiện tại service boundary.
- [ ] Java clients có deadline, retry budget, bulkhead và telemetry.
- [ ] Các luồng bất đồng bộ có idempotency và dead-letter handling.
- [ ] Data owner, source of truth và consistency model đã rõ.
- [ ] CDC/replication có monitoring lag, checksum và rollback.
- [ ] Secrets, encryption, access audit và data residency đạt yêu cầu.

### Vận hành và tài chính

- [ ] IaC và policy review áp dụng cho thay đổi network/IAM.
- [ ] Có dashboards network, DNS, app, data và billing.
- [ ] Có on-call, escalation và runbook xuyên provider.
- [ ] Đã diễn tập tunnel failover, DNS outage và provider disruption.
- [ ] Có change management cho migration/cutover/failback.
- [ ] Chi phí network egress, interconnect, replication và log được theo dõi.
- [ ] Có budget, owner và cost allocation giữa các đội/platforms.
- [ ] Bài test end-to-end chứng minh business transaction thành công.

## Kết luận

Hybrid cloud và multicloud với Google Cloud là bài toán tích hợp nhiều lớp: **VPC và routing**, **Cloud VPN/Interconnect**, **DNS**, **workload identity**, **quyền truy cập**, **dịch chuyển dữ liệu**, **độ tin cậy** và **vận hành**. HA VPN phù hợp kết nối IPsec linh hoạt; Dedicated/Partner/Cross-Cloud Interconnect phù hợp các nhu cầu network khác nhau; Cloud Router xử lý BGP; NCC hỗ trợ tổ chức hub/spoke. Tuy nhiên, đường mạng thông không chứng minh ứng dụng an toàn hay dữ liệu nhất quán. Thiết kế tốt bắt đầu từ mục tiêu nghiệp vụ và failure modes, chọn cách kết nối vừa đủ, kiểm chứng end-to-end, duy trì ownership rõ ràng và theo dõi cả SLO lẫn chi phí xuyên môi trường.

## Tài liệu tham khảo

- [Google Cloud: Network Connectivity overview](https://docs.cloud.google.com/network-connectivity/docs/concepts)
- [Cloud VPN overview](https://docs.cloud.google.com/network-connectivity/docs/vpn/concepts/overview)
- [Cloud VPN best practices](https://docs.cloud.google.com/network-connectivity/docs/vpn/concepts/best-practices)
- [Cloud Router overview](https://docs.cloud.google.com/network-connectivity/docs/router/concepts/overview)
- [Cloud Interconnect overview](https://docs.cloud.google.com/network-connectivity/docs/interconnect/concepts/overview)
- [Dedicated Interconnect overview](https://docs.cloud.google.com/network-connectivity/docs/interconnect/concepts/dedicated-overview)
- [Partner Interconnect overview](https://docs.cloud.google.com/network-connectivity/docs/interconnect/concepts/partner-overview)
- [Cross-Cloud Interconnect overview](https://docs.cloud.google.com/network-connectivity/docs/interconnect/concepts/cci-overview)
- [Network Connectivity Center overview](https://docs.cloud.google.com/network-connectivity/docs/network-connectivity-center/concepts/overview)
- [NCC VPC spokes](https://docs.cloud.google.com/network-connectivity/docs/network-connectivity-center/concepts/vpc-spokes-overview)
- [Cloud DNS hybrid best practices](https://docs.cloud.google.com/dns/docs/best-practices)
- [Shared VPC overview](https://docs.cloud.google.com/vpc/docs/shared-vpc)
- [VPC Network Peering overview](https://docs.cloud.google.com/vpc/docs/vpc-peering)
- [Private Service Connect documentation](https://docs.cloud.google.com/vpc/docs/private-service-connect)
- [Google Cloud IAM Workload Identity Federation](https://docs.cloud.google.com/iam/docs/workload-identity-federation)
- [GKE Multi-Cloud overview](https://docs.cloud.google.com/kubernetes-engine/multi-cloud/docs)
- [Google Distributed Cloud overview](https://docs.cloud.google.com/distributed-cloud/docs/overview)
- [Cloud Run: Private networking](https://docs.cloud.google.com/run/docs/securing/private-networking)
- [Cloud Billing cost management](https://docs.cloud.google.com/billing/docs/how-to/cost-management)

