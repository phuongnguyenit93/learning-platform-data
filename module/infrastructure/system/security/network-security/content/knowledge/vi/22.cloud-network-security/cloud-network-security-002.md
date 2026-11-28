# Subnet public và private: Thiết kế phân vùng mạng cloud an toàn

## 1. Vì sao phải phân biệt public và private subnet?

Trong hạ tầng cloud, một **subnet** là một dải địa chỉ IP được phân bổ cho tài nguyên trong mạng ảo như **VPC (Virtual Private Cloud)** hoặc **VNet (Virtual Network)**. Cách bố trí các subnet ảnh hưởng đến **đường gói tin, khả năng đi Internet, khả năng nhận kết nối từ ngoài, phân đoạn tài sản và điểm kiểm soát bảo mật**.

Hai cách gọi thường gặp là:

- **Public subnet:** subnet được thiết kế để một số tài nguyên có thể có đường kết nối trực tiếp với Internet qua gateway/route thích hợp và địa chỉ có thể định tuyến công khai, theo cơ chế của nền tảng.
- **Private subnet:** subnet không có **đường Internet inbound trực tiếp** theo kiến trúc dự kiến. Tài nguyên bên trong có thể ra ngoài qua **NAT, proxy, firewall, gateway trung gian**, hoặc hoàn toàn không đi Internet.

Đây là **phân loại kiến trúc**, không phải một dấu bảo mật tự động. Đặc biệt, **AWS, Azure và Google Cloud có những mô hình route, địa chỉ công khai và network controls khác nhau**. Không thể dùng một quy tắc duy nhất như “hễ tên subnet chứa `private` thì an toàn” hoặc “có route default thì mọi VM được Internet truy cập”.

Ví dụ, một web load balancer có thể nằm ở tầng công khai để nhận HTTPS, trong khi API service và database nằm ở những subnet chỉ cho phép lưu lượng nội bộ. Nhưng hệ thống vẫn cần **firewall/security groups, identity, TLS, DNS security, network telemetry, IAM và kiểm soát egress**. Một subnet private được kết nối quá rộng qua VPN hoặc peering vẫn có thể bị truy cập từ mạng không mong muốn.

### Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **CIDR, subnet, route table, Internet gateway, NAT gateway, public IP, private IP** và security policy.
2. Giải thích vì sao **public subnet không đồng nghĩa public workload**, **private subnet không đồng nghĩa cô lập tuyệt đối**.
3. Đọc **effective routes và source/destination controls** để xác định đường đi inbound/outbound cho IPv4 và IPv6.
4. Thiết kế mạng **public, private-with-egress và isolated/data subnet** cho kiến trúc nhiều tầng.
5. Phân biệt mô hình AWS VPC, Azure VNet và Google Cloud VPC một cách chính xác.
6. Đánh giá rủi ro NAT, internet egress, peering, transit/hybrid VPN, private endpoints, DNS và failover nhiều Availability Zones.
7. Thực hiện các bước **quan sát chỉ đọc** và xây ma trận kiểm thử allow/deny sau khi triển khai.

Trong module **SECURITY_NETWORK_SECURITY**, subnet public/private là nền tảng để kết hợp **phân đoạn mạng, firewall, VPN, IDS/IPS, xác thực kết nối, routing security, DNS protection và cloud security posture** vào một kiến trúc có thể kiểm chứng.

> **Phạm vi thực hành:** ví dụ sử dụng địa chỉ RFC 1918 và dải IP dành cho tài liệu. Các lệnh và cấu hình đều minh họa, không yêu cầu triển khai hoặc quét Internet. Chỉ thực hiện phép thử kết nối trong lab hoặc môi trường đã được cấp quyền; thay đổi route/ACL/cloud gateway phải theo change control, có rollback và đánh giá chi phí.

## 2. Khái niệm nền tảng: subnet không đứng độc lập

| Thành phần | Chức năng | Câu hỏi bảo mật |
|---|---|---|
| **VPC / VNet** | Miền mạng ảo logic trong cloud | Những tài nguyên và kết nối nào cùng phạm vi? |
| **CIDR** | Dải địa chỉ IP của mạng, ví dụ `10.40.0.0/16` | Có trùng hoặc chồng lấn với mạng khác không? |
| **Subnet** | Một vùng địa chỉ con, ví dụ `10.40.10.0/24` | Workload thuộc tầng nào, vùng/zone nào? |
| **Route table / effective routes** | Chọn next hop/đích theo route và policy | Gói tới Internet hoặc vùng nhạy cảm đi qua đâu? |
| **Internet gateway / Internet next hop** | Cơ chế cloud cung cấp đường Internet khi đủ điều kiện | Có route, public address và điều kiện hỗ trợ? |
| **NAT gateway / outbound proxy** | Cho workload nội bộ chủ động ra ngoài theo cơ chế chuyển địa chỉ/chuyển tiếp | Có giới hạn egress destinations và audit không? |
| **Public IP / external IP** | Địa chỉ được định tuyến từ mạng công khai theo khả năng nền tảng | Có gắn tới tài nguyên/listener không? |
| **Private/internal IP** | Địa chỉ không công khai trực tiếp trên Internet | Có thể bị truy cập qua VPN/peering/transit không? |
| **Security group / NSG / firewall** | Áp dụng allow/deny theo state, direction và rule | Ai được kết nối, giao thức/cổng nào? |
| **Network ACL / policy** | Kiểm soát ở mức subnet hoặc tầng hạ tầng tùy cloud | Có quy tắc chiều về và mức ưu tiên đúng? |
| **DNS và private endpoint** | Phân giải và kết nối tới dịch vụ qua đường private khi cấu hình đúng | DNS trả IP nào, route có bypass firewall không? |

### 2.1. Subnet là ranh giới địa chỉ, không phải firewall

Subnet `10.40.20.0/24` và `10.40.30.0/24` khác nhau về mặt địa chỉ. Nhưng nếu các route và network rules cho phép `10.40.20.10` mở TCP đến `10.40.30.10`, việc “tách subnet” **không tự ngăn traffic**.

Muốn bảo vệ tầng DATA, phải có **luồng được phép rõ ràng** và enforcement tại security group, firewall, NACL/NSG, workload firewall hoặc microsegmentation thích hợp; đồng thời kiểm tra **đường quay về** và IPv6 nếu sử dụng.

### 2.2. IP private không có nghĩa “an toàn”

Các khối IPv4 private theo RFC 1918 là:

- `10.0.0.0/8`
- `172.16.0.0/12`
- `192.168.0.0/16`

Những IP này không được định tuyến trực tiếp trên Internet công khai, nhưng có thể đi qua **VPN site-to-site, Direct Connect/ExpressRoute/Interconnect, peering, transit hub, SD-WAN hoặc một proxy được cấu hình**. Tài nguyên có private IP vẫn có bề mặt tấn công từ các mạng đã được nối.

**Đối với IPv6**, không thể lấy RFC 1918 làm quy tắc: một subnet chứa địa chỉ IPv6 global có thể có route ra Internet mà không cần NAT kiểu IPv4. Trạng thái **inbound reachability** phải được xét qua route, gateway, firewall và sự tồn tại của listener, không chỉ tên subnet.

## 3. Ba mô hình nên phân biệt: public, private có egress, isolated

| Kiểu kiến trúc | Internet inbound trực tiếp | Outbound Internet | Ví dụ workload |
|---|---|---|---|
| **Public subnet** | *Có thể* cho những tài nguyên có public/external address, route và firewall phù hợp | Có thể | Internet-facing load balancer, bastion khi thực sự cần, public reverse proxy |
| **Private subnet có egress** | Không cho direct inbound Internet theo thiết kế | Có thể qua NAT/proxy/firewall hoặc kết nối riêng | Application, job runners, worker nodes |
| **Isolated subnet** | Không | Không có route Internet trực tiếp hoặc NAT egress theo thiết kế | Database, key management dependencies, backend nhạy cảm |

**Quan trọng:** “isolated” ở đây nghĩa là **không có đường Internet theo phạm vi thiết kế**; không nhất thiết không kết nối đến bất kỳ subnet, service endpoint hay hệ thống nội bộ nào. Một database isolated vẫn cần nhận kết nối từ API được duyệt để phục vụ nghiệp vụ.

### 3.1. Sơ đồ điển hình

~~~mermaid
flowchart TD
    U["Người dùng Internet"] --> EDGE["CDN/WAF hoặc public HTTPS LB"]
    subgraph VPC["VPC/VNet ứng dụng — CIDR 10.40.0.0/16"]
        subgraph PUBLIC["PUBLIC — 10.40.10.0/24"]
            LB["Public load balancer / ingress"]
            NAT["NAT gateway hoặc egress appliance"]
        end
        subgraph APP["PRIVATE APP — 10.40.20.0/24"]
            API["API / application"]
        end
        subgraph DATA["ISOLATED DATA — 10.40.30.0/24"]
            DB["Database"]
        end
        SG["Security controls / route policies"]
    end
    EDGE --> LB
    LB --> API
    API --> DB
    API -. "Egress có kiểm soát" .-> NAT
    NAT --> NET["Internet / API bên ngoài"]
    SG -. "Allow/deny giữa các tầng" .-> API
    SG -. "Allow/deny DATA" .-> DB
~~~

Sơ đồ là **kiến trúc khái niệm**, không phải một bản đồ route có thể áp dụng trực tiếp trên mọi cloud. Trong AWS, NAT gateway public điển hình nằm trong public subnet và dùng Internet gateway; trong Azure/GCP, vị trí logic và cơ chế route/NAT được quản lý theo cách khác. Phải diễn giải trên nền tảng cụ thể.

### 3.2. Tại sao đặt database vào private hoặc isolated?

- **Giảm bề mặt Internet-facing:** không cấp public IP/listener cho database nếu không cần.
- **Giới hạn bên gọi:** chỉ app subnet/service identity đã duyệt được kết nối đúng cổng.
- **Giảm tác động khi một web instance bị xâm nhập:** vẫn cần authentication, database roles và phân đoạn.
- **Tách egress:** DATA không có lý do tự ý truy cập mọi dịch vụ Internet.
- **Tăng khả năng audit:** route và kết nối vượt tầng dễ nhận diện trong flow logs.

Không vì DB nằm ở subnet riêng mà mở `0.0.0.0/0` hoặc `::/0` ở database firewall. Đối với network security, **nguồn được phép phải dựa trên security group/service identity hoặc CIDR cụ thể** và có bằng chứng kiểm thử.

## 4. Public subnet không đồng nghĩa “mọi thứ đang phơi ra Internet”

Để một workload IPv4 nhận một kết nối **mới** từ Internet, thông thường phải hội đủ các điều kiện như:

1. Có **địa chỉ public/external** và cơ chế ánh xạ/forward phù hợp.
2. Có **đường mạng inbound và return path**, gồm gateway/route liên quan.
3. Firewall, security groups, NACL/NSG hoặc ingress rules **cho phép** lưu lượng.
4. Có service **listen** đúng địa chỉ/cổng.
5. DNS hoặc client biết địa chỉ public đó (DNS không phải điều kiện cần tuyệt đối nếu client truy cập IP trực tiếp).

Chỉ gán public IP nhưng không có route phù hợp có thể không kết nối được. Chỉ có route tới Internet gateway nhưng VM **không có public IP** cũng không có nghĩa VM đó nhận được kết nối IPv4 trực tiếp từ Internet. Ngay cả khi các điều kiện mạng thỏa, ứng dụng vẫn cần **TLS và authentication/authorization**.

### 4.1. Lộ diện công khai và quyền truy cập khác nhau

| Cấu hình | Kết luận đúng |
|---|---|
| Instance thuộc subnet public nhưng không có public IP | Không mặc nhiên truy cập inbound IPv4 Internet trực tiếp |
| Instance có public IP nhưng SG/firewall deny inbound | Địa chỉ có thể tồn tại công khai nhưng luồng bị chặn theo control đang có |
| Public load balancer 443 → private API | API có thể **được người dùng Internet gọi qua LB**, dù API không có public IP |
| Private instance dùng NAT ra ngoài | Có egress có chủ đích, không đồng nghĩa Internet gọi trực tiếp vào instance qua NAT |
| Database private có API public gọi vào | Database không public trực tiếp, nhưng **dữ liệu vẫn có thể được ứng dụng public xử lý/trả về** nếu authz sai |
| Tài nguyên private có endpoint VPN/peering | Có thể truy cập từ những mạng nối; không phải cô lập tuyệt đối |

**Diễn đạt đúng khi review:** thay vì viết “private nên không ai truy cập được”, hãy nói “không có direct inbound Internet theo tuyến đã xem; chỉ nhận từ các nhóm nguồn được cho phép, và các tuyến VPN/peering đã được rà soát”.

## 5. Route table quyết định đường đi như thế nào?

### 5.1. Các loại route

Trong mạng cloud thường có:

- **Local/VPC/VNet route:** dẫn traffic trong phạm vi mạng theo cơ chế của provider.
- **Internet next hop:** đường đi tới Internet gateway hoặc cổng Internet của provider.
- **NAT / firewall / virtual appliance next hop:** gửi egress qua thiết bị/cổng trung gian.
- **Peering / transit / VPN / private interconnect:** đi tới mạng cloud khác hoặc on-premises.
- **Blackhole / discard hoặc route không còn khả dụng:** tạo mất kết nối theo trạng thái.
- **Route cụ thể hơn:** chiếm ưu thế trong lookup dựa trên prefix length, với **cách chọn route cạnh tranh cùng prefix** tùy nhà cung cấp.

### 5.2. Ví dụ public route và private route

~~~text
Ví dụ cách diễn giải kiểu AWS VPC cho IPv4:

Route table PUBLIC:
  10.40.0.0/16  -> local
  0.0.0.0/0     -> Internet gateway

Route table PRIVATE APP:
  10.40.0.0/16  -> local
  0.0.0.0/0     -> NAT gateway

Route table ISOLATED DATA:
  10.40.0.0/16  -> local
  (không có default route ra Internet)
~~~

Đây là một **mẫu AWS conceptual**, không phải cấu hình Azure/GCP tương ứng từng dòng. Mọi route còn phải xét **subnet association, route precedence, gateway availability, route đến VPN/peering và policies**. Route table chỉ giải thích **đường có thể đi**, không phải một danh sách kết nối được phép.

### 5.3. Longest prefix match vẫn quan trọng

Giả sử private APP subnet có:

~~~text
Destination         Next hop
10.40.0.0/16        local
10.50.0.0/16        transit gateway
10.50.8.0/24        inspection firewall
0.0.0.0/0           NAT/egress gateway
~~~

Gói tới `10.50.8.10` được xem theo prefix `/24` cụ thể hơn `/16`, nếu route đó được chọn và hợp lệ trong provider's effective route model. Traffic tới `203.0.113.20` dùng default route theo kiến trúc này.

Một route sai có thể **bỏ qua firewall** mặc dù subnet vẫn mang nhãn “private”. Vì vậy khi đánh giá đường đến DATA/MGMT hoặc external services, cần đọc **effective routes**, không chỉ xem tên subnet và default route.

### 5.4. Đường đi và đường về

Kết nối TCP từ APP tới DATA hoặc qua VPN cần đường trả về đúng. Tại một số thiết kế dùng **stateful firewall/NAT**, đường đi bất đối xứng có thể khiến packet response không khớp session state. Route đúng ở APP subnet **không đủ** nếu destination subnet hoặc on-premises không có return route.

**Kiểm thử:** nguồn APP → DATA đúng dịch vụ (ALLOW); nguồn GUEST/USER → DATA sai quyền (DENY); sau failover phải kiểm tra cả hai chiều, không chỉ ping gateway.

## 6. AWS VPC: public/private theo route và Internet gateway

Trong AWS, cách phân loại phổ biến là:

- **Public subnet:** route table gắn với subnet có route tới **Internet gateway (IGW)** cho traffic Internet được thiết kế. Tài nguyên IPv4 vẫn cần public IPv4 hoặc Elastic IP cùng các điều kiện network/security để có đường Internet trực tiếp.
- **Private subnet:** không có route trực tiếp tới IGW cho loại traffic cần xét; có thể ra Internet qua **NAT gateway** hoặc một egress appliance.
- **Isolated subnet:** không có Internet route theo kiến trúc; vẫn có `local` và có thể có những route nội bộ/endpoint được kiểm soát.

### 6.1. Các thành phần và trách nhiệm

| AWS component | Vai trò | Điều cần kiểm tra |
|---|---|---|
| **VPC CIDR** | Không gian IP VPC | Trùng CIDR với on-prem/VPC khác, IPv6 allocation |
| **Subnet** | Đơn vị địa chỉ nằm trong một Availability Zone | AZ, CIDR, auto-assign public IP |
| **Route table association** | Chọn bảng route cho subnet | Subnet gắn bảng explicit hay kế thừa main route table |
| **Internet gateway (IGW)** | Kết nối VPC với Internet khi đường và địa chỉ hợp lệ | Route tới IGW, public IP, IPv4/IPv6 |
| **Public NAT gateway** | Cho phép nhiều private IPv4 workloads chủ động kết nối ra ngoài, sử dụng EIP cho Internet egress | Public subnet/AZ, IGW, route từ private subnet, capacity |
| **Security Group (SG)** | Stateful filter ở mức ENI/tài nguyên được hỗ trợ | Inbound/outbound rules, group references |
| **Network ACL (NACL)** | Stateless subnet-boundary filter | Cả inbound/outbound, ephemeral return ports, rule order |
| **VPC endpoint** | Đường riêng/đường qua mạng AWS tới một số dịch vụ | Endpoint type, policy, route, SG và private DNS |
| **VPC Flow Logs** | Telemetry về flows ở phạm vi cấu hình | Log allow/reject, retention và vị trí thiếu visibility |

### 6.2. Vì sao route tới IGW chưa đủ để công khai EC2?

Giả sử EC2 nằm trong subnet gắn với bảng route `0.0.0.0/0 → igw-...`. Nếu EC2 **chỉ có private IPv4**, nó không mặc nhiên nhận được kết nối IPv4 từ Internet chỉ vì có route đó. Nếu EC2 có public IPv4 nhưng **SG inbound deny** hoặc service không listen, request cũng không thành công.

Ngược lại, một **Application Load Balancer internet-facing** có thể có các node ở public subnets và mở HTTPS inbound theo policy, rồi gửi tới EC2 trong private subnets. Người dùng bên ngoài truy cập **ứng dụng qua ALB**, không cần EC2 mang public IP.

### 6.3. NAT gateway không phải cổng inbound tùy ý

Trong mô hình NAT gateway IPv4 outbound thông thường, private instance **khởi tạo kết nối** tới Internet qua NAT. Một máy ngoài Internet **không thể tự khởi tạo một kết nối bất kỳ vào private instance thông qua NAT đó** như một public listener. Tuy nhiên, traffic chiều về của các kết nối đã thiết lập được xử lý theo trạng thái NAT.

**Giới hạn:** NAT không phải egress firewall cấp ứng dụng và không thay thế kiểm soát destination, DNS, IDS/IPS hoặc data loss prevention. Việc cho private workloads kết nối `0.0.0.0/0` qua NAT là quyền ra ngoài rất rộng nếu không có chính sách bổ sung.

### 6.4. Security group và NACL có ngữ nghĩa khác

SG AWS là **stateful**: lưu lượng trả lời cho kết nối được cho phép có cơ chế xử lý trạng thái phù hợp, không cần sao chép từng ephemeral port theo cách NACL. NACL là **stateless**: phải cân nhắc **cả hai chiều** và cổng động của TCP để tránh gây lỗi vô tình. Không bê nguyên mô hình NACL sang Azure NSG hoặc firewall của GCP.

Ví dụ ý định:

~~~text
SG of public ALB:
  Allow inbound TCP/443 from approved Internet sources
  Allow outbound to API target port per design

SG of private API:
  Allow inbound TCP/8443 from ALB SG
  Restrict outbound by dependency policy

SG of isolated DATA:
  Allow inbound TCP/5432 from API SG
  Do not expose database listener to Internet
~~~

Đây là **policy sketch**, không phải lệnh AWS chạy được. Kiểm tra rule references, routing, certificate/TLS và service ports đúng khi triển khai.

## 7. Microsoft Azure: subnet, public IP và outbound model

Trong **Azure Virtual Network (VNet)**, subnet có thể gắn **Network Security Group (NSG), route table/UDR, NAT Gateway và các cơ chế dịch vụ**. Cách gọi “public/private” trong Azure **không nên suy trực tiếp từ việc có route tới IGW như AWS**. Azure có khái niệm **private subnet** liên quan việc vô hiệu **default outbound access** theo lựa chọn/cấu hình mạng; đồng thời tính riêng tư của một workload còn phụ thuộc **Public IP, inbound rules, gateway, load balancer, effective route và những kết nối VNet khác**.

### 7.1. Những thành phần cần đọc

| Azure component | Mục đích | Điểm dễ nhầm |
|---|---|---|
| **VNet/subnet** | Dải mạng trong một vùng của Azure | Tên `private-app` không tự tạo deny rule |
| **Public IP resource** | Có thể gắn với VM/NIC hoặc frontend của LB theo loại tài nguyên | Phải xét inbound security và mapping thực |
| **System routes và UDR** | Quyết định next hop hiệu lực | Default route có thể bị UDR hoặc gateway thay đổi |
| **NAT Gateway** | Outbound SNAT cho subnet được gắn khi cấu hình đúng | Không phải public inbound listener của private VM |
| **NSG** | Stateful allow/deny theo hướng, nguồn/đích, cổng | Rule priority, association với subnet/NIC, effective rules |
| **Azure Firewall / NVA** | Inspection, egress và segmentation theo thiết kế | Cần route traffic qua đúng thiết bị |
| **Private Endpoint / Private Link** | Truy cập tài nguyên dịch vụ bằng private IP trong VNet khi được cấu hình | DNS, quyền, network policy và data plane |
| **Azure Network Watcher** | Connection troubleshoot/effective routes/NSG diagnostics | Dùng đúng NIC/resource và vùng |

### 7.2. Default outbound access không phải đặc quyền cần mặc định

Một số cấu hình/subnet Azure có thể có cơ chế **default outbound connectivity** theo thế hệ tài nguyên, trong khi các thiết kế **private subnet/explicit outbound** hướng tới việc không cấp outbound public ngầm định. Không nên kết luận từ tên “private subnet” rằng app **không thể đi Internet** nếu nó đã được gắn NAT Gateway, UDR tới firewall hoặc một proxy cho phép egress.

**Khuyến nghị kiến trúc:** chọn **explicit outbound connectivity** (NAT Gateway, Azure Firewall hoặc giải pháp phù hợp), đặt route/NSG và ghi rõ dịch vụ nào được phép đi ra. Khi đánh giá một môi trường thực, đọc **effective routes, Public IP associations và effective security rules**, không đoán theo defaults có thể khác nhau theo cấu hình/thời điểm.

### 7.3. Ví dụ APP ↔ DATA trên Azure

~~~text
VNet: 10.40.0.0/16
APP subnet:  10.40.20.0/24
DATA subnet: 10.40.30.0/24

Desired:
  Internet -> Public Application Gateway/Load Balancer -> APP service
  APP -> DATA only TCP/5432 and approved identity
  DATA -> Internet direct: disallowed by network architecture
  APP -> approved external API: via controlled egress

Enforcement:
  NSG + optional firewall/NVA + UDR + identity/TLS + service policy
~~~

Không chỉ xem inbound rules của NSG: Azure mặc định có những quy tắc liên quan VirtualNetwork và các nhóm nguồn/dịch vụ; cần xem **effective rules**, thứ tự ưu tiên và đường mạng thật, kể cả peering/VPN. Thêm NSG cho một subnet không tự tạo tường lửa bao phủ mọi route ngoài thiết kế.

## 8. Google Cloud VPC: subnet mang tính regional, Internet theo route/VM/firewall

Trong **Google Cloud**, VPC network có phạm vi **global** theo mô hình sản phẩm, còn subnets là **regional**. Đây là khác biệt quan trọng với subnet trong AWS gắn với Availability Zone. Để quyết định một VM có thể đi/nhận Internet, phải xem:

- External IP gắn với VM hay với frontend công khai của load balancer;
- Routes, **default internet gateway** và những lựa chọn route phù hợp;
- VPC firewall rules và hierarchical firewall policies nếu có;
- Cloud NAT hoặc proxy để đi outbound;
- Subnet/zone/region, service account tags, network interfaces và thiết kế Hybrid Connectivity.

### 8.1. Cloud NAT dành cho kết nối khởi tạo từ workload nội bộ

**Cloud NAT** có thể cung cấp SNAT cho những VM/workloads đủ điều kiện không có external IP, giúp chúng chủ động kết nối tới destination được phép. Nó **không tự mở kết nối inbound mới từ Internet đến VM**. Hãy phân biệt Cloud NAT (dịch vụ NAT) với **Cloud Router** (trao đổi route động/hỗ trợ cấu hình của một số mô hình kết nối); không gọi Cloud Router là NAT gateway.

### 8.2. Firewall có thể khác theo loại VPC

VPC firewall rules/policies kiểm soát traffic; cấu hình mặc định phụ thuộc kiểu mạng và policy hiện có. Một **default VPC** có thể chứa những rules tạo sẵn khác với **custom VPC**. Không giả định mọi mạng GCP đều có cùng danh sách cho phép SSH/RDP/ICMP hay mặc định egress.

Khi thiết kế private backend, hãy xem **effective firewall enforcement**, route, external IP assignment, public LB backend path và service accounts. Một VM không có external IP vẫn có thể nhận request thông qua **load balancer công khai** nếu được cấu hình làm backend — tương tự bài toán tách public ingress với private workload.

### 8.3. Cùng yêu cầu, triển khai khác nhau

| Mục tiêu | AWS | Azure | Google Cloud |
|---|---|---|---|
| Web endpoint công khai | Internet-facing ALB/NLB hoặc public resource với IGW route | Application Gateway/Load Balancer/Public IP theo loại | External Application/Network Load Balancer |
| APP không nhận direct inbound từ Internet | Private subnet, private IP, SG/ACL và route phù hợp | Không cấp public exposure, NSG/UDR và subnet policies | VM không external IP, VPC firewall, route và LB design |
| APP outbound IPv4 có kiểm soát | NAT gateway, NAT instance hoặc egress firewall/proxy | NAT Gateway, Azure Firewall/NVA/proxy | Cloud NAT, proxy hoặc firewall path |
| Truy cập dịch vụ cloud qua private path | VPC endpoints theo loại dịch vụ | Private Link / Private Endpoint và DNS | Private Google Access / Private Service Connect theo loại dịch vụ |
| Kiểm tra đường thực | Route tables, SG/NACL, Reachability Analyzer, Flow Logs | Effective routes/NSG, Network Watcher, flow telemetry | Routes, firewall insights/connectivity tests, VPC Flow Logs |

**Đây là bảng tương đương về mục đích, không phải tương đương một-một về API hoặc các tính năng.** Luôn kiểm tra tính khả dụng và giới hạn theo vùng, account/project, loại dịch vụ và phiên bản.

## 9. Outbound Internet từ private subnet: NAT không thay thế firewall

### 9.1. Đường egress và kết nối trở về

~~~mermaid
flowchart LR
    APP["Private APP<br/>10.40.20.10"] --> NAT["Egress NAT<br/>source translation"]
    NAT --> WEB["External API / update endpoint"]
    WEB -. "Response cho flow đã khởi tạo" .-> NAT
    NAT -. "State/translation trả về APP" .-> APP
    EXT["Client Internet không được phép"] -. "Không có direct new inbound qua NAT" .-> APP
~~~

NAT thay nguồn/địa chỉ trong những hoàn cảnh được thiết kế để traffic có thể ra ngoài và hồi đáp. **NAT không chứng thực đích đến là an toàn**; một workload bị xâm nhập trong private subnet có thể cố gắng gửi dữ liệu ra một endpoint bên ngoài nếu egress quá rộng.

### 9.2. Cần kiểm soát cả đích đến, danh tính và giao thức

Với một private APP chỉ cần tải package updates hoặc gọi một API bên thứ ba, hãy xem xét:

- Proxy egress hoặc firewall hỗ trợ kiểm soát domain/application khi cần.
- DNS security, FQDN allowlist theo khả năng và giới hạn (DNS không đồng nhất với IP đích).
- TLS/HTTPS validation và certificate trust để không gửi secrets sang server giả.
- SG/NSG/firewall outbound, network ACL, route tới inspection gateway.
- Logging: nguồn workload, public egress address, destination, bytes, request/identity khi có.
- NAT capacity, port exhaustion, HA/AZ placement, connection timeouts và chi phí.

**Không đặt một rule “APP có thể Internet all ports, all destinations” chỉ vì APP nằm ở private subnet.** Điều đó có thể giảm inbound exposure nhưng vẫn tạo đường exfiltration.

### 9.3. Egress dependency và availability

Một NAT hoặc firewall tập trung có thể thành **single point of failure** cho software updates, identity API, container registry và các dịch vụ gọi ra. Khi NAT unavailable, APP vẫn có thể phục vụ request inbound từ LB nhưng không gọi được dependency ngoài. Thiết kế có HA phù hợp, fallback có kiểm soát và kiểm thử sau failover; đừng xử lý bằng cách cấp public IP cho mọi APP instance mà không review.

## 10. IPv6: private/public cần phân tích riêng

### 10.1. Không lấy việc thiếu NAT IPv4 làm bằng chứng an toàn IPv6

Một tài nguyên có **IPv6 global address** và route `::/0` tới Internet gateway có thể có khả năng gửi/nhận lưu lượng trực tiếp theo điều kiện nền tảng, kể cả khi IPv4 chỉ đi qua NAT. IPv6 không bắt buộc dùng NAT kiểu IPv4 để có kết nối Internet.

Ví dụ kiểu AWS:

~~~text
IPv4 APP route:
  0.0.0.0/0 -> NAT gateway

IPv6 APP route:
  ::/0 -> egress-only internet gateway   (nếu chỉ muốn egress IPv6)

DATA:
  Không có route IPv4/IPv6 Internet theo kiến trúc
~~~

Trong AWS, **egress-only Internet gateway** hỗ trợ IPv6 outbound theo cơ chế không cho lưu lượng IPv6 ngoài khởi tạo kết nối vào theo kiểu public IGW. Không nên coi nó là bản sao một-một của NAT IPv4: **địa chỉ IPv6 nguồn không nhất thiết được dịch** như SNAT IPv4.

### 10.2. Những bài kiểm thử bắt buộc với dual-stack

- Workload có cả A/AAAA/DNS và IPv4/IPv6 listener hay không?
- Firewall/SG/NSG đã áp dụng rule **`::/0`** phù hợp chưa?
- Subnet IPv6 có `::/0` tới đâu? Có route bypass inspection?
- Workload có đường ra ngoài bằng IPv6 ngoài policy IPv4 không?
- Inbound tới IPv6 public có bị chặn đúng như IPv4?
- DNS và load balancer có đưa client tới IPv6 endpoint với TLS/authorization tương đương không?

**Điểm dễ bỏ sót:** chặn Internet inbound trên IPv4 nhưng quên IPv6 có thể tạo một đường không được bảo vệ, nhất là khi ứng dụng bind `::` và security policies IPv6 khác IPv4.

## 11. Routing và firewall: hai câu hỏi độc lập nhưng liên quan

**Định tuyến** trả lời “packet đi theo đường nào?”, còn **kiểm soát mạng** trả lời “packet đó có được phép đi qua/đến đích không?”. Hai chức năng phải cùng đúng. Một thiết bị firewall chỉ áp dụng rule cho traffic **thực sự đi qua nó**; khi route đổi, lưu lượng có thể bypass firewall và làm mất hiệu lực một chính sách tưởng như vẫn đang bật.

### 11.1. Ví dụ ma trận ứng dụng và dữ liệu

Giả sử hệ thống có:

| Vùng | IPv4 subnet | Vai trò |
|---|---|---|
| PUBLIC INGRESS | `10.40.10.0/24` | LB nhận HTTPS |
| PRIVATE APP | `10.40.20.0/24` | API |
| ISOLATED DATA | `10.40.30.0/24` | PostgreSQL |
| MGMT | `10.40.40.0/24` | Bastion hoặc hệ thống quản trị |
| ON-PREM | `10.70.0.0/16` | Mạng kết nối qua VPN/private circuit |

Định nghĩa chính sách theo luồng:

| Nguồn → Đích | Giao thức/cổng | Chính sách | Mục đích |
|---|---|---|---|
| Internet → Public LB | HTTPS TCP/443 | ALLOW theo exposure policy/WAF | Nhận request ứng dụng |
| Internet → Private APP IP | Bất kỳ kết nối direct | DENY | Không bypass ingress |
| LB → APP | HTTPS TCP/8443 | ALLOW | Chuyển request đã được kiểm soát |
| APP → DATA | PostgreSQL TCP/5432 | ALLOW từ service đã duyệt | Truy vấn dữ liệu |
| PUBLIC LB → DATA | TCP/5432 | DENY | Không cho LB chạm DB trực tiếp |
| APP → MGMT | SSH TCP/22 | DENY theo mặc định | Ngăn admin lateral movement |
| MGMT bastion → máy được quản trị | Cổng quản trị được duyệt | ALLOW theo identity | Vận hành có kiểm soát |
| DATA → Internet | Bất kỳ direct egress | DENY theo thiết kế | Giảm exfiltration |
| APP → DNS/NTP/identity | Dịch vụ nền được duyệt | ALLOW có giới hạn | Phục vụ dependency |
| ON-PREM → DATA | Theo application policy; thường DENY mặc định | DENY nếu chưa phê duyệt | Kiểm soát trust boundary hybrid |

Đây là **ma trận mong muốn**, không khẳng định đã được enforce. Các cổng thực tế phụ thuộc workload, và quyền ở tầng database/ứng dụng phải được kiểm tra riêng. Nếu APP → DATA đã được phép theo network policy, điều đó không đồng nghĩa mọi tài khoản ứng dụng được đọc mọi bảng.

### 11.2. Stateful và stateless khác nhau

- **Stateful controls** thường theo dõi kết nối và cho traffic trả lời cho phiên hợp lệ theo các quy tắc tương ứng, ví dụ AWS Security Groups và Azure NSGs.
- **Stateless controls** như AWS Network ACLs xét từng chiều độc lập; cần chú ý các ephemeral ports và rule priority.
- **Firewall appliances** có thể có trạng thái, NAT và application inspection riêng; route bất đối xứng có thể làm state tracking không hoạt động như dự kiến.
- **Kubernetes NetworkPolicy / service mesh** áp dụng control ở những tầng riêng; chúng không thay thế route table hoặc tất cả firewall cloud.

**Không sao chép một rule “mở ephemeral range” từ NACL vào SG chỉ vì tên giống nhau.** Cần hiểu điểm thực thi, phương thức state tracking và directionality của từng cơ chế.

### 11.3. Deny by default ở từng tầng

Với mục tiêu segmentation:

1. Quy định những **source zones/service identities** được phép tới từng đích.
2. Thu hẹp **protocol/port**; không dùng `Any` nếu không cần.
3. Tách **inbound** và **egress**; một số mặc định cho egress rộng.
4. Có **negative tests** từ nguồn không được phép, đặc biệt Internet, Guest/VPN và các subnet ứng dụng khác.
5. Lặp lại với **IPv6, failover, peering, transitive paths và DR region**.

Ở mức hệ thống thực, không thể kết luận “deny by default” chỉ từ một bảng SG: cần xem tất cả enforcement points và route đi qua chúng.

## 12. Private connectivity tới dịch vụ cloud

Một private application có thể cần object storage, container registry, secrets manager, managed database hoặc API của cloud provider. Nếu mỗi request phải qua NAT và Internet path, hệ thống sẽ có thêm **egress policy, chi phí, dependency và độ lộ thông tin**.

Nhiều cloud cung cấp kết nối tới một số dịch vụ bằng **private endpoints hoặc access paths trên mạng của provider**, nhưng cách hoạt động không đồng nhất.

### 12.1. Phân biệt các loại private access

| Nền tảng | Ví dụ cơ chế | Bảo vệ gì? | Cần cấu hình gì thêm? |
|---|---|---|---|
| AWS | **Gateway VPC endpoint** cho một số dịch vụ như S3/DynamoDB theo khả năng | Route đến dịch vụ qua endpoint thay vì NAT/IGW theo mô hình hỗ trợ | Endpoint route, policy, resource policy, DNS/app access |
| AWS | **Interface VPC endpoint / PrivateLink** | Private ENI IP trong VPC cho dịch vụ hỗ trợ | Subnet/AZ, endpoint SG, DNS, endpoint policy khi có |
| Azure | **Private Endpoint / Private Link** | Private IP trong VNet tới tài nguyên dịch vụ được hỗ trợ | Private DNS zone, NSG/UDR policies phù hợp, resource access |
| Google Cloud | **Private Google Access** | Một số tài nguyên không external IP truy cập Google APIs/services được hỗ trợ | Route, DNS, firewall và service scopes/permissions |
| Google Cloud | **Private Service Connect** | Private connectivity tới những dịch vụ/producer theo mô hình phù hợp | Endpoint/forwarding rule, DNS, policy, route/firewall |

**Tên “private” không đồng nghĩa tất cả gói đều nằm trong cùng một VPC/VNet**, cũng không tự khẳng định dữ liệu ứng dụng đã được mã hóa. Kiểm tra **trang thái service endpoint, TLS hostname validation, network policies, IAM/resource policies và DNS resolution**.

### 12.2. DNS là điểm dễ lỗi nhất

Một endpoint private có thể được gán **private IP**, nhưng client vẫn truy vấn **public DNS name** nếu private DNS chưa cấu hình đúng. Địa chỉ trả về có thể khiến kết nối đi qua NAT hoặc một đường khác, làm mất mục tiêu egress/private connectivity.

Ví dụ:

~~~text
APP trong 10.40.20.0/24 gọi:
    storage.service.example.test

Expected with private DNS:
    storage.service.example.test -> private endpoint IP 10.40.50.12
    Route: private/local/endpoint path
    TLS: xác minh certificate theo tên dịch vụ hợp lệ

Unexpected if DNS/route misconfigured:
    storage.service.example.test -> public service address
    Route: default NAT/firewall or fail
~~~

Đây là **domain giả định**, không phải một endpoint public thực. Tên DNS public/alias, private DNS zones, split-horizon, CNAME và TLS SNI/hostname phải được thiết kế tương thích theo provider.

### 12.3. Private endpoint không thay IAM và database permissions

Một client được network cho phép kết nối tới private object-storage endpoint **chưa chắc** có quyền đọc bucket/object. IAM, endpoint policy và resource-based policy vẫn có thể từ chối. Ngược lại, identity được cấp quyền quá rộng nhưng mạng không giới hạn egress có thể làm rủi ro data exfiltration tăng.

Đối với managed database, phân biệt:

- **Network reachability:** endpoint có private address/routing?
- **Database firewall/SG:** nguồn APP được cho phép?
- **TLS:** kênh tới dịch vụ và danh tính server được xác minh?
- **Authentication:** account, token, certificate hoặc IAM auth nếu dịch vụ hỗ trợ?
- **Authorization:** tài khoản có quyền SQL/data nào?

Không dùng khái niệm “private endpoint” thay cho cả năm lớp trên.

## 13. Multi-AZ, multi-region và tính sẵn sàng của public/private subnets

### 13.1. High availability không chỉ là có hai subnet

Một kiến trúc production có thể phân phối public LB, private APP và DATA qua nhiều Availability Zones. Tuy nhiên, **subnet ở AZ thứ hai không tự làm hệ thống HA** nếu backend, database, NAT, route, firewall hoặc DNS chỉ còn một điểm lỗi.

~~~mermaid
flowchart TD
    U["Internet users"] --> LB["Public load balancer / WAF"]
    LB --> A1["APP private / Zone A"]
    LB --> A2["APP private / Zone B"]
    A1 --> DB["Managed database HA"]
    A2 --> DB
    A1 -. "External API egress" .-> N1["Egress gateway A"]
    A2 -. "External API egress" .-> N2["Egress gateway B"]
    N1 --> OUT["Approved Internet destinations"]
    N2 --> OUT
~~~

### 13.2. NAT theo zone và route failover

Trong AWS, thiết kế thường cân nhắc **NAT gateway theo AZ** để hạn chế dependency cross-AZ và tăng availability, tùy topology, chi phí và những tính năng NAT cụ thể. Subnet private ở từng AZ cần route egress theo kiến trúc HA tương ứng. Một NAT ở AZ A không bảo đảm APP ở AZ B không bị ảnh hưởng khi AZ A gặp sự cố.

Tại Azure/GCP, cách provider quản lý NAT/zone/region khác AWS; phải dùng **tài liệu availability thực tế của dịch vụ và cấu hình đang áp dụng**. Không mặc định sao chép công thức “một NAT trên mỗi subnet” từ AWS cho mọi cloud.

### 13.3. Failover phải giữ nguyên security posture

Khi APP failover sang AZ/region khác, cần kiểm tra:

- Subnet/route table mới có đưa traffic qua cùng **security enforcement** không?
- LB/backend target group và private IP mapping có đúng?
- Security group/NSG/firewall rules mới có bị mở rộng “tạm thời” không?
- NAT/egress public IP có thay khiến đối tác allowlist không chấp nhận?
- Private endpoints, DNS zones, certificate/TLS và identity services có sẵn tại vùng backup?
- Database replication và **RPO/RTO ứng dụng** có được đáp ứng không?
- Đường đi/đường về qua VPN, firewall stateful có đúng không?

Một request trả HTTP 200 từ vùng dự phòng **không chứng minh rằng GUEST → DATA vẫn bị chặn**. Bắt buộc test cả **positive và negative flows**.

## 14. Hybrid networking: private subnet vẫn có thể lộ qua VPN/peering

Một tổ chức có thể nối VPC/VNet tới on-premises hoặc mạng cloud khác bằng **VPN, dedicated private circuits, peering, hub/spoke hoặc transit gateway**. Khi đó, phạm vi “private” không còn đồng nghĩa “chỉ nội bộ một VPC”.

~~~mermaid
flowchart LR
    ON["On-prem / 10.70.0.0/16"] <-->|"VPN / private interconnect"| HUB["Transit / cloud hub"]
    HUB --> APP["Private APP 10.40.20.0/24"]
    HUB -. "Chỉ theo allowlist" .-> DATA["Isolated DATA 10.40.30.0/24"]
    FW["Transit firewall / policy"] -. "Kiểm soát tuyến đi" .-> HUB
~~~

### 14.1. Rủi ro phổ biến

- **CIDR overlap:** `10.40.0.0/16` trùng mạng khác, làm route lookup sai hoặc kết nối không thực hiện được.
- **Route propagation/import/export quá rộng:** một VPN peer quảng bá prefix ngoài dự kiến.
- **Peering không tự định nghĩa quyền:** được route tới VPC khác chưa chắc có SG/NSG phù hợp, và cũng không nên cho phép tất cả.
- **Transit bypass:** một more-specific route đưa DATA traffic qua đường khác firewall.
- **Asymmetric return path:** packet request qua firewall A nhưng response về đường B gây lỗi stateful inspection.
- **DNS split-view:** ứng dụng hybrid phân giải public endpoint thay vì private, làm sai egress path.

### 14.2. Giới hạn tin cậy của đối tác

Khi kết nối với mạng đối tác, không coi **mọi địa chỉ private của đối tác** là được phép truy cập internal DATA hoặc MGMT. Áp dụng destination allowlist, source identity, firewall logs, mTLS/TLS khi cần và giám sát route changes. Dùng least privilege cho cả **đường mạng lẫn IAM**.

## 15. Threat modeling cho public/private subnet

| Tài sản / mối đe dọa | Con đường có thể xảy ra | Kiểm soát nên có | Cách xác nhận |
|---|---|---|---|
| Web frontend bị tấn công từ Internet | Public LB/API có lỗ hổng | WAF, TLS, patch, app auth, rate limit | Security test có phép và app/WAF logs |
| Direct-to-instance exposure | VM private bị cấp public IP/route ngoài ý định | Deny public assignment, policy-as-code, SG/NSG | Inventory IP và effective routes |
| Lateral movement từ APP sang DATA | APP bị chiếm quyền, dùng private route hợp lệ | Segmentation, DB auth, IAM, workload identity | APP→DATA allow đúng, APP→MGMT deny |
| Egress exfiltration | Private APP gửi dữ liệu qua NAT/proxy | Egress firewall, destination policy, DNS security, DLP | Flow logs, proxy logs và deny tests |
| Public/private route drift | Sửa default route hoặc association | IaC, review, drift detection, cloud policy | Diff/effective route audit |
| VPN route leak / hybrid access | Peering/transit quảng bá prefix sai | Route filtering, firewall, network zoning | Received/advertised routes, connectivity tests |
| IPv6 path bypass | ::/0 và IPv6 firewall khác IPv4 | IPv6 route/SG/NSG parity | IPv4/IPv6 allow/deny tests |
| Private endpoint đi sai DNS | Client dùng public IP qua NAT | Private DNS, endpoint policy, split-horizon validation | DNS answer + effective route + TLS |
| NAT outage | APP không gọi được external dependency | Egress HA, dependency design, monitoring | Failover exercise và app SLO |
| Metadata/service credentials bị lộ | Workload/SSRF chạm metadata API | Instance identity policy, metadata protections, SSRF defense | IAM/EDR/app controls |
| Log thiếu vì traffic đi ngoài inspection | Route mới không qua firewall/IDS | Centralized routing và flow telemetry | Flow path verification |
| Misconfigured data-tier inbound | SG/NSG mở TCP/5432 từ quá rộng | Source group/identity allowlist | Negative tests từ Internet và các zones khác |

**Mấu chốt:** tấn công cloud không cần “đi vào” private subnet trực tiếp từ Internet nếu kẻ tấn công đã kiểm soát một workload **được phép kết nối** tới subnet đó. Do đó network zoning phải kết hợp **identity, application hardening, least-privilege IAM và audit**.

## 16. Quan sát trạng thái mạng cloud: đừng dựa vào tên subnet

Để xác định workload **có thể nhận kết nối từ đâu** và **có thể chủ động kết nối tới đâu**, cần thu bằng chứng từ nhiều lớp, không chỉ ảnh chụp giao diện “Public/Private”.

### 16.1. Checklist quan sát theo thứ tự

1. **Inventory:** account/subscription/project, VPC/VNet, subnet CIDR, region/AZ, workload, NIC, IPv4/IPv6.
2. **Exposure:** public/external IP, public LB/listener, DNS và public/private endpoint associations.
3. **Route:** subnet association, effective routes, default route IPv4/IPv6, peering/transit/VPN và UDR khi có.
4. **Security controls:** SG, NSG, NACL, VPC firewall policies, firewall appliance, workload firewall.
5. **Application:** process listening, TLS certificate/hostname, API authentication, IAM, database authorization.
6. **Telemetry:** network flow logs, firewall decisions, DNS logs, proxy logs và application traces.
7. **Proof:** positive/negative connectivity tests đúng nguồn, đúng đích, đúng port và từng đường đi.

Khi nghi ngờ một resource đang public, đừng chỉ nhìn thuộc tính `public-ip`: có trường hợp **public load balancer** xuất bản ứng dụng mà backend vẫn private. Ngược lại, một host không public IPv4 nhưng có IPv6 direct reachability hoặc đang nối VPN tới mạng ngoài có thể nằm ngoài threat model ban đầu.

### 16.2. Những log thường giúp ích

| Nguồn telemetry | Mục đích | Giới hạn |
|---|---|---|
| Cloud flow logs / VPC flow logs | Quan sát luồng mạng theo metadata được hỗ trợ | Có thể sampled/aggregated; không thay full packet capture |
| Firewall/NSG/SG policy telemetry | Xác định allow/deny và rule hiệu lực | Chỉ thấy điểm thực thi có logging |
| NAT gateway / egress proxy logs | Theo dõi các destination, lỗi SNAT/port và egress | NAT logs không giải thích quyền API người dùng |
| DNS resolver query logs | Biết hostname được phân giải và loại record | Không chứng minh ứng dụng dùng IP đó cho mọi phiên |
| LB/WAF access logs | Đường public traffic đến backend, TLS/client signals | XFF/raw headers có thể giả nếu không chuẩn hóa |
| Application logs/tracing | HTTP status, dependency latency, identity | TLS/HTTP success không chứng minh mọi route an toàn |
| Cloud audit logs | Ai sửa route, SG, NSG, public IP, endpoint | Cần thời gian đồng bộ và quyền truy cập tối thiểu |

**Không thấy log** chưa đủ kết luận một flow không tồn tại: logging có thể tắt, sampling, sai scope hoặc traffic đi qua đường không được giám sát. Kết hợp **route evidence + enforcement state + controlled tests**.

### 16.3. Định nghĩa nhãn exposure rõ ràng

Một bảng inventory hữu ích nên có các trường độc lập:

~~~yaml
asset: api-lab-01
environment: authorized-lab
network: vpc-app-lab
subnet: snet-app-private-a
private_ipv4: 10.40.20.10
public_ipv4: null
ipv6_address: null
ipv4_default_next_hop: egress-nat-a
ipv6_default_next_hop: none
public_load_balancer_backend: true
allowed_inbound:
  - source: public-lb-security-identity
    protocol: tcp
    port: 8443
approved_egress:
  - package-mirror-via-egress-policy
verified_internet_direct_inbound: false
last_validation: pending
owner: cloud-platform-team
~~~

Các giá trị trên **chỉ mô phỏng inventory**, không phải kết quả scan. Tách bạch **public IP của host** với việc **ứng dụng được truy cập qua LB** để tránh báo cáo sai về exposure.

## 17. Các lệnh kiểm tra chỉ đọc trên AWS, Azure và Google Cloud

Chỉ thực hiện trên **account/subscription/project đã được cấp quyền**. Những tên/ID viết hoa dưới đây là placeholder; thay bằng ID thực của lab thuộc quyền quản lý. Lệnh `describe`, `show`, `list` chỉ lấy metadata và **không sửa route**, nhưng có thể hiển thị địa chỉ nội bộ, cấu hình IAM hoặc tên tài nguyên; không đăng công khai đầu ra.

### 17.1. AWS CLI: subnet, route, security group và workload address

~~~bash
# AWS — các placeholder chỉ có nghĩa khi thay bằng ID hợp lệ trong lab.
aws ec2 describe-subnets \
  --filters "Name=vpc-id,Values=VPC_ID"

# Xem TẤT CẢ route tables của VPC để không bỏ sót main route table.
aws ec2 describe-route-tables \
  --filters "Name=vpc-id,Values=VPC_ID"

# Đọc Internet gateway, NAT gateway hiện có.
aws ec2 describe-internet-gateways \
  --filters "Name=attachment.vpc-id,Values=VPC_ID"
aws ec2 describe-nat-gateways \
  --filter "Name=vpc-id,Values=VPC_ID"

# Đọc SG và NACL của môi trường.
aws ec2 describe-security-groups \
  --filters "Name=vpc-id,Values=VPC_ID"
aws ec2 describe-network-acls \
  --filters "Name=vpc-id,Values=VPC_ID"

# Inventory instance network interfaces và public/external addresses.
aws ec2 describe-instances \
  --filters "Name=vpc-id,Values=VPC_ID"
~~~

**Lưu ý AWS:** nếu một subnet không có explicit route-table association, nó có thể sử dụng **main route table** của VPC. Chỉ truy vấn bảng route gắn với subnet bằng explicit association có thể bỏ sót route thực. Phải đọc cả **main association và subnet association**, cùng những route specific hơn, trạng thái target và endpoint routes.

Khi xem instance, public IP có thể được gắn qua network interface hoặc cơ chế riêng; không kết luận từ tên subnet. Với SG/NACL, xem inbound lẫn outbound; với IPv6 xem `::/0` và IPv6 network rules.

### 17.2. Azure CLI: subnet, NIC effective routes và NSG

~~~bash
# Azure — các tên ví dụ cần thay bằng resource group/VNet/NIC của lab.
az network vnet subnet show \
  --resource-group RG_LAB \
  --vnet-name VNET_LAB \
  --name SNET_APP

# NIC effective route table nếu resource/permission hỗ trợ.
az network nic show-effective-route-table \
  --resource-group RG_LAB \
  --name NIC_APP

# NIC effective NSG rules nếu có hỗ trợ và đủ quyền.
az network nic list-effective-nsg \
  --resource-group RG_LAB \
  --name NIC_APP

# Liệt kê public IP resources đã được cấp trong resource group.
az network public-ip list \
  --resource-group RG_LAB
~~~

**Lưu ý Azure:** effective routes/rules phụ thuộc NIC, trạng thái VM, resource và hỗ trợ Network Watcher/API. Không thể đánh giá một VNet chỉ từ subnet JSON: cần xem UDR, NAT Gateway/Firewall, NSG gắn NIC/subnet, load balancer, private endpoints và outbound model đang áp dụng.

### 17.3. Google Cloud CLI: subnet, route, firewall và VM

~~~bash
# Google Cloud — thay PROJECT_ID, SUBNET_NAME, REGION, VM_NAME, ZONE.
gcloud compute networks subnets describe SUBNET_NAME \
  --region=REGION \
  --project=PROJECT_ID

gcloud compute routes list \
  --project=PROJECT_ID

gcloud compute firewall-rules list \
  --project=PROJECT_ID

gcloud compute instances describe VM_NAME \
  --zone=ZONE \
  --project=PROJECT_ID
~~~

**Lưu ý GCP:** hierarchical firewall policies, network tags, service accounts, route priorities và effective network behavior cần xem ngoài output của vài lệnh trên. Một VM không có external IP nhưng là backend của external load balancer vẫn có thể phục vụ request từ Internet thông qua LB.

### 17.4. Test DNS/HTTPS từ đúng workload

~~~bash
# Chỉ thử trên endpoint kiểm thử được phê duyệt.
# Chạy bên trong chính private APP instance/container đã được phép.
nslookup storage.service.example.test

# Kiểm tra kết nối HTTPS được xác thực, không bỏ certificate verification.
curl --head --verbose \
  --connect-timeout 3 --max-time 10 \
  https://storage.service.example.test/health
~~~

Tên `storage.service.example.test` là giả định, nên sẽ không hoạt động nếu lab chưa cung cấp DNS và endpoint đó. **DNS trả IP private không tự chứng minh TLS đúng**, và `curl` thành công không chứng minh traffic đã đi qua private endpoint: cần xem DNS/route/provider telemetry.

### 17.5. Không dùng thay đổi production làm “kiểm thử nhanh”

Không tự tạo public IP, route `0.0.0.0/0`, NAT gateway hoặc mở inbound SG chỉ để chứng minh một subnet “có thể public”. Những thay đổi này có thể **phơi tài nguyên, làm thay đổi chi phí và mất kết nối hợp lệ**. Khi cần thử, dùng lab cô lập với cấu hình được review và rollback.

## 18. Cấu hình như mã: diễn đạt ý định và kiểm soát drift

Thay vì phụ thuộc tên subnet hoặc chỉnh thủ công qua giao diện, tổ chức nên quản lý **CIDR, route tables, security groups, endpoint policies và ownership** bằng Infrastructure as Code (IaC) với review.

### 18.1. Mẫu policy-as-data

~~~yaml
network_design:
  vpc_cidr: 10.40.0.0/16
  zones:
    - name: public-ingress
      cidr: 10.40.10.0/24
      allowed_public_entry:
        - tcp/443 via approved-lb
      direct_app_public_ip: forbidden
    - name: private-app
      cidr: 10.40.20.0/24
      internet_ipv4_egress: via-approved-nat-firewall
      direct_public_inbound: forbidden
      incoming_sources:
        - approved-lb-to-tcp-8443
    - name: isolated-data
      cidr: 10.40.30.0/24
      internet_egress: forbidden
      incoming_sources:
        - approved-app-to-tcp-5432
  controls:
    default_public_ip_assignment: denied-except-approved-ingress
    require_ipv6_policy_review: true
    audit_effective_routes: true
    audit_firewall_rules: true
    require_positive_negative_connectivity_tests: true
~~~

Đây **không phải schema có thể triển khai trực tiếp** cho Terraform/CloudFormation/Bicep/Deployment Manager. Nó chỉ thể hiện **ý định kiểm soát** để nhóm nền tảng chuyển thành cấu hình và test tương ứng.

### 18.2. Điều nên kiểm tra trong pull request IaC

- Có subnet mới vô tình gắn **main route table với IGW** không?
- Có tài nguyên nhạy cảm được bật **public IP auto-assignment** hoặc external IP không?
- SG/NSG/firewall có mở inbound `0.0.0.0/0` hoặc `::/0` tới database/admin ports?
- NAT/egress route có đi qua inspection theo thiết kế và có HA?
- Route đến DATA/MGMT có bypass firewall khi có more-specific route?
- Private DNS/endpoint policies, VPC peering và VPN propagation có phù hợp?
- IPv6 có thiết lập tương đương IPv4 về allow/deny?
- Secrets/certificate/IAM permissions có bị hardcode hoặc mở quá rộng?
- Có **owner, approval, automated policy checks, drift alert và rollback plan**?

### 18.3. Drift detection khác unit test template

IaC định nghĩa cấu hình mong muốn nhưng **không bảo đảm trạng thái cloud đang chạy đúng** nếu có manual changes, service-managed resources, failover hoặc policy ngoài module. Cần so **desired state** với **effective state**, thực hiện connectivity tests, log kiểm tra và cảnh báo các route/public IP phát sinh ngoài quy trình.

## 19. Ma trận kiểm thử public, private và isolated subnets

Một bài kiểm thử tốt phải chỉ ra **nguồn, đích, giao thức/cổng, thời điểm, đường route, điểm thực thi policy và kết quả ứng dụng**. Chỉ xem response `timeout` hoặc status `200` không đủ để chứng minh kiến trúc an toàn.

| Test ID | Điều cần chứng minh | Cách kiểm tra trong lab được phép | Điều kiện PASS |
|---|---|---|---|
| **PUB-01** | Internet → public HTTPS LB hoạt động | Request HTTPS từ test client public | TLS/HTTP đúng, WAF/LB logs và target health hợp lệ |
| **PUB-02** | Internet → private APP direct không hoạt động | Connectivity test từ mạng ngoài tới endpoint đã chỉ định | Không có direct path, không mở private service |
| **PUB-03** | Internet → DATA direct bị chặn | Đọc public IP/route/SG và phép thử giới hạn khi được phép | Không có direct exposure; flow được chặn đúng policy |
| **PUB-04** | APP không tự gắn public IP ngoài chủ đích | Đọc instance/NIC/public IP inventory | Không có public/external address ở APP/DATA |
| **ROUTE-01** | Public subnet đi qua next hop dự kiến | Đọc effective route table của subnet ingress | Route/gateway đúng, không có route bypass |
| **ROUTE-02** | APP IPv4 egress qua NAT/firewall đã duyệt | Đọc route và quan sát egress telemetry | Next hop, source egress và policy đúng |
| **ROUTE-03** | DATA không có Internet default egress | Đọc effective routes + thử một request vô hại có phép | Không có direct/default Internet path ngoài policy |
| **ROUTE-04** | Return path đúng khi có VPN/NVA | Đọc route hai phía và kiểm tra session trong lab | Stateful firewall/NAT không làm hỏng luồng hợp lệ |
| **ALLOW-01** | LB → APP TCP/8443 được phép | Request qua LB và xem backend flow | Dịch vụ hoạt động, đúng peer/policy |
| **ALLOW-02** | APP → DATA TCP/5432 được phép | Kiểm tra kết nối từ APP test identity | Kết nối đúng DB, TLS/auth theo policy |
| **DENY-01** | PUBLIC ingress → DATA không được phép | Negative test từ LB/ingress test workload | Bị firewall/SG/NSG chặn theo policy |
| **DENY-02** | APP → MGMT SSH bị chặn | Negative connectivity test đúng source zone | Không có đường được phép vào admin port |
| **DENY-03** | GUEST/ON-PREM không tự truy cập DATA | Test từ VPC/VPN guest được phê duyệt | Bị deny trừ trường hợp allowlist được duyệt |
| **IPV6-01** | Internet inbound IPv6 không bypass | Kiểm tra ::/0, IPv6 listener, IPv6 firewall | Exposure parity với IPv4 |
| **IPV6-02** | DATA IPv6 không có egress ngoài ý định | Đọc route IPv6, thử kết nối giới hạn | Không có route hoặc policy allow ngoài mục tiêu |
| **ENDPOINT-01** | APP dùng private service endpoint | Kiểm tra private DNS, endpoint route và service access | Traffic theo đường private dự kiến, identity/TLS hợp lệ |
| **ENDPOINT-02** | Endpoint không cho identity sai truy cập | Thử resource policy/IAM với principal lab bị hạn chế | Truy cập bị từ chối đúng ở data plane |
| **EGRESS-01** | APP không gửi ra destination ngoài allowlist | Thử một đích lab nằm ngoài danh sách đã duyệt | Egress policy deny và ghi log |
| **NAT-01** | NAT/failover không gây outage ngoài SLO | Diễn tập lỗi trong môi trường cho phép | APP vẫn đáp ứng requirement hoặc rollback thành công |
| **FAILOVER-01** | AZ/region dự phòng giữ security boundary | Lặp các test allow/deny sau failover | Không mở thêm quyền, đạt SLO/đường về |
| **HYBRID-01** | VPN/peering không leak DATA/MGMT | Đọc routes/filters + negative test từ peer lab | Không có reachability ngoài policy |
| **AUDIT-01** | Thay đổi public IP, route, SG có thể truy vết | Kiểm tra cloud audit record và IaC change reference | Owner, actor, thời gian và diff rõ ràng |

### 19.1. Cách kết luận bài test

- **PASS:** đủ bằng chứng về **đường mạng + enforcement + kết quả**. Ví dụ APP→DATA kết nối DB thành công qua đúng đường private, đồng thời Internet→DATA bị chặn và không có external exposure.
- **FAIL:** bằng chứng trái mục tiêu. Ví dụ DATA có public IPv6 và firewall nhận traffic từ Internet, hoặc APP gửi egress qua một tuyến ngoài inspection bắt buộc.
- **INCONCLUSIVE:** phép thử không xác định được lỗi mạng hay dịch vụ. Ví dụ `curl` timeout vì endpoint tắt, chưa xác nhận DNS, source tester nằm sai subnet, hoặc flow logs không bật/không đủ granularity.

**Negative test cần có positive control.** Nếu kết nối tới DATA bị từ chối, cần biết database đang hoạt động và một APP test được phép vẫn truy cập thành công; nếu không, sự cố DB có thể bị nhầm thành “firewall chặn đúng”.

### 19.2. Dữ liệu tối thiểu cần lưu cho một phép thử

~~~yaml
test_id: DENY-INTERNET-TO-DATA-LAB-01
environment: authorized-isolated-lab
time_utc: "2026-11-28T09:00:00Z"
source_zone: internet-test-client
destination_zone: isolated-data
destination_ip: 10.40.30.10
protocol: tcp
destination_port: 5432
network_expectation: deny-direct-inbound
route_expectation: no-public-route-to-data
positive_control: app-to-data-tcp-5432-succeeds
evidence_required:
  - workload-public-address-inventory
  - effective-route-table
  - firewall-or-security-rule-decision
  - source-connectivity-result
  - application-positive-control-result
result: pending
~~~

Mẫu **chưa được thực thi**. Các địa chỉ là giả định. Nếu dịch vụ không thực sự có public destination, có thể dùng **cloud reachability analysis** và bằng chứng inventory/rules thay vì cố quét IP công khai ngoài phạm vi cho phép.

## 20. Runbook thiết kế hoặc thay đổi subnet an toàn

### Bước 1 — Xác định nhu cầu nghiệp vụ và trust boundaries

Phân loại từng workload:

- **Internet-facing ingress** cần nhận kết nối công khai hay chỉ qua CDN?
- **APP** phục vụ backend nào, có cần outbound Internet không?
- **DATA** chỉ chấp nhận nguồn nào, có cần private endpoints đến dịch vụ cloud?
- **MGMT** đi qua SSO/bastion/VPN hay một đường quản trị độc lập?
- **Hybrid** có những mạng on-prem/partner nào cần route và truy cập?

Không chọn `public subnet` chỉ vì “VM cần tải packages”; private subnet với egress được kiểm soát thường đáp ứng nhu cầu đó mà không cấp public IP cho workload.

### Bước 2 — Lập kế hoạch địa chỉ

Chọn CIDR theo capacity, IPv4/IPv6, expected growth, region/AZ, các môi trường khác và kết nối hybrid. Kiểm tra **overlap**, reserve ranges, subnet sizing theo hạn chế provider và nhu cầu IP của load balancer/endpoints. Không dùng cùng CIDR cho nhiều VPC cần định tuyến trực tiếp với nhau nếu không có kế hoạch xử lý cụ thể.

### Bước 3 — Thiết kế route và security controls

Tạo sơ đồ đường đi cho **inbound public, egress, east–west, VPN/peering và management**. Chỉ rõ:

1. Default routes IPv4/IPv6 và next hops.
2. More-specific routes tới private endpoints/transit/firewall.
3. SG/NSG/NACL/firewall rule ở nguồn/đích.
4. NAT, source-IP translation và return routes.
5. TLS termination, service identity và DNS.

**Cần xét cả đường backup.** Một tuyến failover bỏ qua firewall là sai kiến trúc, kể cả khi tăng availability.

### Bước 4 — Áp dụng guardrails

Dùng IaC, review hai người theo yêu cầu, deny public IP assignment cho tài sản nhạy cảm, policy kiểm tra inbound rules mở rộng, kiểm soát quyền `CreateRoute`, `AssociateRouteTable`, thay SG/NSG và tạo public endpoints. Áp dụng least privilege cho cloud roles và audit change events.

### Bước 5 — Pilot và kiểm thử

Triển khai trên lab hoặc canary:

- Xác minh các tuyến public/private/isolated thực tế.
- Test **ALLOW** từ LB→APP và APP→DATA, **DENY** Internet→APP/DATA và GUEST→DATA.
- Test private DNS/endpoints, NAT egress, IPv6, TLS và external dependency.
- Quan sát cloud logs và application health trước/sau thay đổi.

### Bước 6 — Triển khai theo kế hoạch có rollback

Thay đổi route table association hoặc security controls có thể ngắt kết nối ngay. Chuẩn bị **quyền quản trị dự phòng**, phiên bản IaC trước đó, thứ tự thay đổi và phương án khôi phục. Với NAT/firewall/peering, lưu ý flow đang hoạt động và trạng thái stateful devices.

### Bước 7 — Hậu kiểm liên tục

Gắn evidence, owner, ngày review và quyết định exception. Giám sát route/public IP drift, SG rules mới, VPN prefixes, egress đột biến, certificate expiry, endpoint DNS và connectivity SLO. Chạy lại ma trận kiểm thử sau migration, failover và thay đổi cloud provider service.

~~~mermaid
flowchart TD
    A["Yêu cầu nghiệp vụ + dữ liệu nhạy cảm"] --> B["CIDR / subnet / AZ + IPv6"]
    B --> C["Route, gateway, endpoint, DNS, IAM"]
    C --> D["Policy SG/NSG/firewall + IaC review"]
    D --> E["Lab/canary: allow và deny tests"]
    E --> F{"Đúng security path và SLO?"}
    F -- "Không" --> G["Sửa thiết kế / rollback"]
    G --> C
    F -- "Có" --> H["Rollout theo kế hoạch"]
    H --> I["Quan sát route / logs / ứng dụng"]
    I --> J{"Có drift hoặc regression?"}
    J -- "Có" --> G
    J -- "Không" --> K["Lưu bằng chứng + periodic review"]
~~~

## 21. Case study: Database tưởng private nhưng bị công khai ngoài ý muốn

### 21.1. Bối cảnh giả định

Một nhóm ứng dụng vận hành dịch vụ quản lý đơn hàng trên cloud. Thiết kế được phê duyệt:

~~~text
Internet -> HTTPS public LB -> private APP -> isolated DATA

APP:
  - Không có public IP
  - Chỉ nhận từ LB
  - Egress bên ngoài qua NAT / firewall

DATA:
  - Không có public IP
  - Chỉ nhận PostgreSQL/5432 từ APP
  - Không có Internet default route
~~~

Trong một đợt migration, đội triển khai tạo subnet mới có tên `data-private-migration` nhưng **gắn nhầm route table public** và bật một cơ chế cấp public IPv4 cho tài nguyên được tạo trong subnet đó. Cùng lúc, một rule firewall/SG thử nghiệm mở TCP/5432 từ phạm vi Internet không được phê duyệt.

**Phân biệt điều kiện:** tên subnet `data-private-migration` không tạo bất cứ bảo vệ nào. Với một workload cụ thể, nguy cơ Internet-facing tăng khi đồng thời có **public address/đường Internet và inbound policy cho phép**. Một public route đơn lẻ chưa đủ khẳng định DB đã lộ; phải xác minh đủ các điều kiện network/service.

### 21.2. Dấu hiệu cần điều tra

Một hệ thống posture management phát cảnh báo giả định:

~~~text
Finding: UNEXPECTED_PUBLIC_DB_EXPOSURE
Asset: db-lab-01
Subnet label: data-private-migration
Observed route: 0.0.0.0/0 -> public Internet gateway (platform-specific)
Observed instance interface: public IPv4 assigned
Observed inbound rule: TCP/5432 from 0.0.0.0/0
Application listener: PostgreSQL on configured interface
Status: REQUIRES AUTHORIZED VALIDATION
~~~

Đây là **tình huống giả định**, không phải phát hiện từ một hệ thống thật. Để đánh giá exposure, phải xác định tiếp **public address mapping, effective route, mọi network policies, listener, source path và trạng thái thực thi**. Không suy rằng “có 0.0.0.0/0 trong SG” đồng nghĩa người ngoài chắc chắn đã kết nối được nếu các điều kiện khác chưa rõ.

### 21.3. Phân tích nguyên nhân gốc

| Lớp | Thiết kế đúng | Sai lệch giả định | Tác động |
|---|---|---|---|
| Subnet association | DATA theo isolated route table | DATA gắn public route table | Có thể tạo Internet path ngoài ý định |
| IP assignment | DB không có public IP | DB có public IPv4 | Tăng khả năng trở thành endpoint công khai |
| Security control | Chỉ APP SG → DATA TCP/5432 | Inbound TCP/5432 từ Internet | Mất least-privilege network policy |
| Workload listener | DB chỉ nhận nguồn cho phép | Listener tiếp nhận ở interface/port áp dụng | Có thể bị tiếp cận nếu đường mạng đủ điều kiện |
| IaC review | Policy kiểm tra route/SG/public IP | Guardrail không chặn thay đổi | Cấu hình sai lọt vào deployment |
| Monitoring | Alert về exposure và config drift | Chưa có hoặc cảnh báo bị bỏ qua | Kéo dài thời gian phát hiện |

Lỗ hổng không phải do “database nằm trong subnet tên public” mà do **sự kết hợp của đường truyền, public address, firewall và dịch vụ thực tế**. Kể cả khi vẫn yêu cầu password và TLS cho database, việc public exposure không phê duyệt là một sai lệch đáng xử lý.

### 21.4. Quy trình khắc phục có thứ tự

1. **Khoanh vùng:** xác định endpoint, owner, change ticket, thời gian xuất hiện public IP/rule, flow logs và workload dependencies.
2. **Khôi phục network boundary:** theo kế hoạch được duyệt, chặn Internet inbound ngoài allowlist và đưa DB về route/subnet đúng. Đảm bảo không tự làm mất đường vận hành/cứu hộ.
3. **Gỡ public IP khi phù hợp:** kiểm tra tác động lên DNS, client và connection trước khi thu hồi/đổi địa chỉ.
4. **Đảm bảo APP→DATA vẫn hoạt động:** positive test từ APP chính đáng bằng đúng port/TLS/database credentials.
5. **Negative test:** Internet/Guest/những source zones không được duyệt không thể kết nối DATA; thử cả IPv4/IPv6 trong phạm vi cho phép.
6. **Rà soát exposure history:** firewall logs, database authentication events, audit trails và dấu hiệu truy cập bất thường; không giả định “chưa có breach” chỉ vì không thấy log.
7. **Sửa IaC và policy:** deny public IP/Internet inbound cho DATA, kiểm tra route table associations, gắn các rule theo service identity, bổ sung regression tests.
8. **Báo cáo và theo dõi:** thông báo cho đội phản ứng sự cố nếu có bằng chứng truy cập không được phép; lưu thay đổi, owner, kết quả và điều kiện để đóng finding.

### 21.5. Sơ đồ trước/sau

~~~mermaid
flowchart TD
    NET["Internet"]
    subgraph BEFORE["Trước: migration sai"]
        BDB["DB có public IP + route Internet + inbound quá rộng"]
    end
    subgraph AFTER["Sau: mô hình đúng"]
        LB["Public HTTPS LB"]
        APP["Private APP"]
        DB["Isolated DATA"]
    end
    NET -. "Có thể mở đường sai cấu hình" .-> BDB
    NET --> LB
    LB --> APP
    APP --> DB
    NET -. "Không có direct path tới DATA" .-> DB
~~~

### 21.6. Bằng chứng đóng sự cố

~~~text
Case: PUBLIC-DATA-EXPOSURE-LAB

Expected after remediation:
  DATA public/external IPv4: NONE
  DATA direct Internet inbound: DENY
  DATA IPv6 Internet route/exposure: NONE by policy
  APP -> DATA TCP/5432: ALLOW + application authentication
  INTERNET -> PUBLIC LB HTTPS/443: ALLOW as designed
  INTERNET -> DATA TCP/5432: DENY
  Route association: verified isolated DATA table
  Firewall SG/NSG: scoped sources only
  Change approval and IaC diff: recorded

Outcome: PENDING authorized validation
~~~

**Bài học:** bảo vệ cloud subnet phải dựa vào **effective network state**, không phải tên, mô tả, icon hoặc cảm giác “nó là IP private”. Guardrails cần kiểm tra nhiều yếu tố phối hợp và bảo đảm security posture không suy giảm khi migration/failover.

## 22. Troubleshooting: khi đường public/private không hoạt động như mong đợi

| Triệu chứng | Giả thuyết | Bằng chứng nên thu |
|---|---|---|
| VM public không truy cập Internet được | Thiếu external IP, IGW/default route, outbound policy, DNS | NIC addresses, route table, SG/NSG, DNS |
| Public LB mở nhưng backend 502/504 | Backend private unreachable, wrong port, TLS mismatch | LB target health, app logs, inbound rules |
| APP private không gọi external API | NAT/firewall route, DNS, allowlist hoặc port exhaustion | Effective route, NAT logs, proxy/firewall logs |
| APP chạy một AZ nhưng AZ khác lỗi | Egress gateway một AZ, route association khác, SG mismatch | Per-AZ routes/targets, health and NAT status |
| Private subnet vẫn nhận được request từ Internet qua app | Public LB/proxy chuyển request đúng | LB and app logs; không nhầm với direct VM exposure |
| DATA có public IP ngoài dự kiến | Auto-assign/public NIC/LB association/config drift | Instance NIC, address inventory và audit events |
| DATA không nhận APP dù rule ALLOW | Route chiều về thiếu, SG/NACL/NSG, DB listener/TLS | Flow logs, return route, DB health |
| GUEST/VPN vào được DATA ngoài ý định | Peering/route propagation, firewall policy quá rộng | Effective routes, source zone, policy |
| SG deny nhưng một đường vẫn truy cập được | Test sai tài nguyên, LB proxy, IPv6 hoặc policy khác | Exact destination ENI/resource, flow path |
| NACL chặn lưu lượng trả lời | Stateless ephemeral port rule thiếu | NACL direction, TCP handshake state |
| Azure VM outbound thất bại | Chưa có explicit outbound path hoặc UDR/firewall sai | NIC effective route, NAT Gateway association |
| GCP VM không external IP không đi Internet | Thiếu Cloud NAT/PGA hoặc firewall/route | VM NIC, Cloud NAT, route/firewall |
| Private endpoint resolve public IP | Private DNS zone/link/records sai hoặc resolver split-view | DNS từ chính workload và endpoint metadata |
| Private endpoint IP đúng nhưng 403 | IAM/resource policy/service permission từ chối | Service logs, principal identity, endpoint policy |
| Private endpoint IP đúng nhưng timeout | NSG/SG/route, endpoint status hoặc DNS đã stale | Endpoint health, effective route, flow logs |
| IPv4 bị chặn nhưng IPv6 hoạt động ngoài policy | IPv6 `::/0`, public v6 hoặc rule khác | IPv6 route, address, listener, allow/deny |
| Một VPN app lỗi sau thay route | CIDR overlap, asymmetric path hoặc NAT collision | Route tables hai đầu, VPN logs, flow path |
| Internet-facing service hoạt động nhưng IDS không thấy traffic | Traffic đi ngoài inspection path hoặc TLS không được giải mã | Effective route, WAF/flow logs và TLS endpoint |
| Route table trông đúng nhưng test vẫn lỗi | Subnet dùng main association khác hoặc resource/namespace sai | Effective association, workload NIC, source/destination |
| Failover route đã hoàn tất nhưng app lỗi | DNS, certificate, database, firewall, NAT egress IP đổi | App SLO, dependency logs, LB and PKI state |

### 22.1. Quy trình điều tra theo từng lớp

1. **Xác định flow:** source/destination IP, IPv4 hay IPv6, protocol/port, subnet, VPC/VNet, region/AZ và thời gian.
2. **Kiểm tra endpoint:** VM/NIC có public/external IP hay private IP? Dịch vụ có listener và DNS đúng?
3. **Xem effective routing:** bảng route thực gắn subnet/NIC, route cụ thể hơn, default gateway, peering/transit.
4. **Xem security controls:** SG, NACL, NSG, cloud firewall, proxy, workload firewall và IAM/resource policies.
5. **Xem đường về và NAT:** stateful session, SNAT address, asymmetric routing, ephemeral ports.
6. **Xem TLS/DNS và ứng dụng:** certificate, authn/authz, HTTP/DB response, endpoint dependencies.
7. **So positive/negative controls:** dịch vụ đích thực sự hoạt động chưa, source test đúng vùng chưa?
8. **So cloud telemetry:** flow logs, audit events và config diff theo thời gian.
9. **Khắc phục theo change process:** review impact, canary, rollback; đừng mở `0.0.0.0/0` để “thử nhanh”.

### 22.2. Một request timeout không đủ để kết luận “private”

Nếu một tester cố gọi database và bị timeout, điều đó **chỉ nói rằng phép thử cụ thể không thành công**. Nó có thể do DNS, route, firewall, TLS, database down, sai cổng hoặc kiểm thử từ sai nguồn. Để xác nhận yêu cầu “Internet không thể trực tiếp tới DATA”, cần chứng minh **không có exposure path ngoài dự kiến**, bằng inventory, effective routes, security controls và phép thử phù hợp.

Ngược lại, nếu một client Internet nhận HTTP 200 từ API public trong khi backend là private, đây **có thể hoàn toàn đúng** vì LB được thiết kế chuyển tiếp request vào backend. Mục tiêu của private subnet là giới hạn **direct reachability và quyền theo luồng**, không làm mọi ứng dụng private trở nên vô dụng với người dùng ngoài.

## 23. Bài tập vận dụng

### Bài 1 — Có route tới Internet gateway là public hoàn toàn?

Một EC2 nằm trong subnet có route `0.0.0.0/0 → IGW`, nhưng EC2 chỉ có private IPv4 và inbound SG không mở. Có thể khẳng định EC2 nhận được kết nối IPv4 trực tiếp từ Internet không?

*Đáp án gợi ý:* **không**. Route là một điều kiện của public-subnet pattern, không tự cấp public IPv4 hay mở security rules. Cần kiểm tra public IP mapping, return path, SG/NACL, listener và tất cả các đường kết nối.

### Bài 2 — NAT có cho kết nối inbound không?

Một APP trong private subnet truy cập external API qua NAT gateway. Một client từ Internet có thể chủ động kết nối TCP mới vào APP qua NAT như một public load balancer không?

*Đáp án gợi ý:* **không**, theo mô hình NAT gateway outbound thông thường. NAT cho kết nối khởi tạo từ APP và chiều trả lời, không tự cung cấp direct inbound listener. Nhưng APP vẫn có thể bị lạm dụng **egress** nếu được phép gọi destination ngoài chính sách.

### Bài 3 — Database private mà API vẫn public

Browser truy cập API public, API đọc database private và trả dữ liệu. Có phải DB đã trở thành Internet-facing direct endpoint không?

*Đáp án gợi ý:* không nhất thiết. Browser đi qua LB/API tới DB. DB không cần public IP; **API authorization, database permissions và bảo vệ dữ liệu** quyết định dữ liệu nào được trả về. Không nên đồng nhất “dữ liệu được phục vụ qua API” với “DB có đường direct inbound”.

### Bài 4 — Isolated không có nghĩa disconnected

Một DATA subnet không có `0.0.0.0/0`, nhưng APP vẫn kết nối TCP/5432 được. Thiết kế có mâu thuẫn không?

*Đáp án gợi ý:* không. DATA có thể nhận traffic nội bộ được phép qua local/private routes mà vẫn không có Internet egress route. Cần xác nhận chỉ nguồn APP được duyệt có quyền và database xác thực đúng.

### Bài 5 — Hai cloud, cùng thuật ngữ

Vì sao không thể dùng nguyên tắc AWS “public subnet có default route tới IGW” để phân loại trực tiếp subnet Azure?

*Đáp án gợi ý:* Azure dùng VNet, system routes/UDR, Public IP, NSG, NAT Gateway và mô hình default/explicit outbound khác AWS. Phải xem **effective routes/exposure** của resource, không lấy cú pháp IGW của AWS làm chuẩn cho Azure.

### Bài 6 — IPv6 bypass

APP chỉ dùng NAT IPv4 và inbound SG IPv4 deny. Nhưng subnet có IPv6 global address và `::/0` tới Internet gateway. Đã đủ cơ sở khẳng định APP không có direct Internet inbound không?

*Đáp án gợi ý:* chưa. Kiểm tra IPv6 route, address, SG/NSG/firewall rules và listener, kể cả AAAA/DNS. Nếu chỉ muốn IPv6 outbound trong AWS, xem cơ chế **egress-only Internet gateway** phù hợp.

### Bài 7 — Private endpoint và DNS

Ứng dụng đã tạo Private Endpoint tới storage, nhưng DNS của workload vẫn trả về public IP. Điều gì có thể sai?

*Gợi ý:* private DNS zone/link/record, split-horizon resolver, service name hoặc endpoint policy. Cần xem **IP thật client kết nối, effective route, endpoint state và TLS validation**; việc resource tồn tại không bảo đảm traffic đã đi private path.

### Bài 8 — SG và NACL

Một rule SG cho APP→DATA TCP/5432 nhưng DATA response không về được. Vì sao cần kiểm tra NACL?

*Đáp án gợi ý:* trong AWS, SG stateful còn NACL stateless; NACL có thể chặn traffic trả lời hoặc ephemeral ports. Đồng thời phải xem route chiều về, firewall/NAT state và ứng dụng.

### Bài 9 — Hybrid VPN

ON-PREM `10.70.0.0/16` được kết nối với VPC chứa APP/DATA. Có thể mặc định mọi máy on-prem được gọi DB private không?

*Đáp án gợi ý:* không. Route/VPN chỉ đưa ra khả năng kết nối; cần firewall allowlist, DB auth, TLS và chính sách trust/identity. Kiểm tra route propagation và chính sách DATA từ các subnet đối tác.

### Bài 10 — Failover đa AZ

APP ở Zone A và B, nhưng tất cả APP ra Internet qua NAT gateway ở Zone A. Có rủi ro vận hành nào?

*Gợi ý:* dependency vào một AZ, chi phí/cross-zone path và outage khi NAT/AZ A lỗi. Xem thiết kế egress HA thích hợp theo nền tảng và kiểm thử phục hồi ở tầng ứng dụng.

### Bài 11 — Route cụ thể hơn

Một APP có `0.0.0.0/0 → NAT` và `10.50.8.0/24 → transit firewall`. Packet tới `10.50.8.20` sẽ đi theo route nào nếu các route hợp lệ trong cùng effective table?

*Đáp án gợi ý:* route `/24` cụ thể hơn. Cần xác minh **firewall path và return route**. Default NAT không thắng một route cụ thể hơn chỉ vì nó “mặc định”.

### Bài 12 — Case public DB

Một DB có SG mở TCP/5432 từ Internet nhưng **không có public address hoặc public LB path**, nằm trong isolated subnet. Có thể kết luận DB đã trực tiếp phơi Internet thành công không?

*Đáp án gợi ý:* chưa đủ bằng chứng direct Internet reachability vì thiếu các điều kiện địa chỉ/route/exposure. Tuy nhiên rule SG quá rộng vẫn là **misconfiguration cần sửa**, nhất là nếu topology thay đổi hoặc có VPN/peering. Cần xác minh tất cả source zones và effective controls.

### Bài 13 — Private subnet bị xâm nhập

Giả sử một APP private instance bị tấn công qua lỗ hổng API công khai. Vì sao DB private vẫn cần network allowlist, IAM/DB permissions, TLS và monitoring?

*Gợi ý:* attacker có thể dùng **quyền network hợp lệ của APP** để đi lateral. Private subnet giúp giới hạn direct public exposure nhưng không chống mọi hành vi phát sinh từ workload đã được cho phép.

### Bài 14 — Đánh giá một thiết kế cloud

Hãy thiết kế VPC/VNet có WEB public ingress, APP private, DATA isolated, một private endpoint đến secret store và kết nối VPN về on-prem. Mô tả **một luồng ALLOW và hai luồng DENY**, đường egress, IPv6 policy và cách xác minh.

*Gợi ý:* WEB LB→APP đúng port; APP→DATA đúng port; Internet→DATA DENY; ON-PREM→MGMT/DATA DENY theo mặc định; APP egress qua firewall/NAT khi cần; secret store qua private endpoint + private DNS; đo route, controls, log và test từ đúng zones.

## 24. Checklist bảo mật subnet public/private

- [ ] Có **inventory VPC/VNet, subnet CIDR, region/AZ, IPv4/IPv6 và owner** cho từng workload.
- [ ] Tách **public ingress, private application, isolated DATA và management plane** theo trust boundaries thực tế.
- [ ] Kiểm tra **public/external IP assignments** và public load balancer associations; không chỉ nhìn tên subnet.
- [ ] Đọc **effective route table**, cả main/implicit associations và more-specific routes.
- [ ] Internet inbound trực tiếp chỉ được thiết kế cho **những entry points được phê duyệt**.
- [ ] Private APP không có public IP nếu không cần, nhưng có **egress có kiểm soát** cho dependency hợp lệ.
- [ ] DATA không có direct Internet path theo policy; chỉ các sources/ports được duyệt có quyền tới DB.
- [ ] Xác minh SG/NSG/firewall/NACL phù hợp **stateful/stateless semantics** của từng platform.
- [ ] Có **negative tests** Internet→APP/DATA, PUBLIC→DATA, GUEST/VPN→DATA, APP→MGMT khi chưa phê duyệt.
- [ ] Có **positive tests** LB→APP, APP→DATA, DNS/NTP/identity và các service endpoints cần thiết.
- [ ] IPv6 `::/0`, IPv6 SG/NSG/firewall rules và AAAA DNS được kiểm tra **độc lập với IPv4**.
- [ ] NAT/egress proxy có **destination policy, telemetry, capacity và HA**, không mặc định mở toàn Internet.
- [ ] Private endpoints dùng **private DNS, endpoint policies, IAM và TLS validation** đúng.
- [ ] VPN/peering/transit routes được review; không tự tin mọi network nối bằng private IP.
- [ ] Route failover/multi-AZ/multi-region giữ **security enforcement tương đương** và đường trả về hợp lệ.
- [ ] TLS/PKI, authentication/authorization, secrets và IAM được áp dụng tại các workload, không phó mặc cho subnet.
- [ ] Infrastructure as Code có **review, change controls, drift detection, audit logs và rollback**.
- [ ] Flow logs, firewall, NAT, DNS, LB và application logs được thu theo chính sách, không lộ dữ liệu mật.
- [ ] Các kết quả đánh giá phân biệt **direct public reachability**, **public API accessibility** và **egress capability**.
- [ ] Không sử dụng “timeout”, “private IP” hay “subnet tên private” làm bằng chứng an toàn duy nhất.

**Kết luận:** public và private subnet là cách **tổ chức đường mạng và giảm bề mặt truy cập**, không phải nhãn chứng nhận bảo mật. Một kiến trúc vững cần xác định rõ **tài nguyên nào có public ingress, tài nguyên nào chỉ nhận từ service được duyệt, outbound được phép tới đâu, từng packet đi qua route/firewall nào và mỗi giới hạn được kiểm thử thế nào**. Khi kết hợp subnet design với segmentation, identity, TLS, DNS security, egress control và giám sát, các lớp phòng vệ cloud mới phát huy hiệu quả.

### Tài liệu tham khảo

- [RFC 1918 — Address Allocation for Private Internets](https://www.rfc-editor.org/rfc/rfc1918): địa chỉ IPv4 private và phạm vi sử dụng.
- [RFC 4632 — Classless Inter-domain Routing (CIDR)](https://www.rfc-editor.org/rfc/rfc4632): địa chỉ prefix và mô hình định tuyến.
- [RFC 4291 — IP Version 6 Addressing Architecture](https://www.rfc-editor.org/rfc/rfc4291): các loại địa chỉ và cách định danh IPv6.
- [AWS — VPC Subnets](https://docs.aws.amazon.com/vpc/latest/userguide/VPC_Subnets.html): subnet và các thuộc tính của VPC.
- [AWS — Internet Gateways](https://docs.aws.amazon.com/vpc/latest/userguide/VPC_Internet_Gateway.html): Internet access và route tới IGW.
- [AWS — NAT Gateways](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-nat-gateway.html): outbound connectivity cho private workloads.
- [AWS — Security Groups](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html): stateful network controls.
- [AWS — Network ACLs](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-network-acls.html): subnet-level stateless controls.
- [Microsoft Learn — Azure Virtual Network traffic routing](https://learn.microsoft.com/en-us/azure/virtual-network/virtual-networks-udr-overview): system routes, UDR và next hops.
- [Microsoft Learn — Azure NAT Gateway](https://learn.microsoft.com/en-us/azure/nat-gateway/nat-overview): kết nối outbound có chủ đích.
- [Microsoft Learn — Azure Private Endpoints](https://learn.microsoft.com/en-us/azure/private-link/private-endpoint-overview): private IP connection và policy.
- [Google Cloud — VPC networks](https://cloud.google.com/vpc/docs/vpc): global VPC và regional subnets.
- [Google Cloud — Cloud NAT overview](https://cloud.google.com/nat/docs/overview): egress NAT và phạm vi sử dụng.
- [Google Cloud — Private Google Access](https://cloud.google.com/vpc/docs/private-google-access): private access to supported Google APIs/services.
- [Google Cloud — VPC Firewall Rules](https://cloud.google.com/vpc/docs/firewalls): kiểm soát traffic và chính sách.
- [NIST SP 800-41 Rev. 1 — Guidelines on Firewalls and Firewall Policy](https://csrc.nist.gov/pubs/sp/800/41/r1/final): phân đoạn và quản trị điểm kiểm soát mạng.






