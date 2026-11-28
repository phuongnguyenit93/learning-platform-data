# Subnet segmentation

> **Chương:** Segmentation  
> **Mô-đun:** SECURITY_NETWORK_SECURITY  
> **Trọng tâm:** Thiết kế phân đoạn theo subnet trong kiến trúc phòng vệ nhiều lớp: địa chỉ IP/CIDR, VLAN, routing, firewall/ACL, VPN, DNS, Wi-Fi, IDS/IPS và mạng đám mây; phân tích đường tấn công và kiểm chứng khả năng cô lập thực tế.

## 1. Subnet segmentation là gì?

**Subnet segmentation** là cách chia một không gian địa chỉ IP thành nhiều **mạng con (subnet)** để tổ chức thiết bị, giới hạn phạm vi hoạt động và tạo các điểm có thể thực thi chính sách giữa những nhóm tài sản khác nhau. Chẳng hạn, máy người dùng, ứng dụng, cơ sở dữ liệu, thiết bị quản trị và mạng Wi-Fi khách có thể được đặt ở những subnet riêng.

Mỗi subnet IPv4 thường được mô tả bằng một tiền tố CIDR như **10.40.30.0/24**. Các host cùng subnet có thể giao tiếp trực tiếp trong cùng miền liên kết nếu thiết kế lớp 2 cho phép; lưu lượng đi sang subnet khác thường cần định tuyến qua router hoặc thiết bị lớp 3. Điều này tạo cơ hội áp dụng **ACL, firewall, kiểm soát theo zone, logging và giám sát** tại ranh giới.

**Điểm mấu chốt:** *Chia thành nhiều subnet không tự động tạo ra ranh giới bảo mật*. Nếu router cho phép mọi luồng giữa các subnet, máy ở mạng người dùng vẫn có thể truy cập mạng quản trị hoặc cơ sở dữ liệu. Ngược lại, hai host cùng subnet vẫn có thể bị cách ly bằng các biện pháp lớp 2 hoặc chính sách phân tán trên host/workload. Khả năng bảo vệ đến từ **thiết kế đường đi và chính sách được thực thi**, không chỉ từ số lượng subnet.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích mối quan hệ giữa **IP subnet, VLAN, broadcast domain, gateway, routing và trust boundary**.
2. Phân bổ CIDR IPv4/IPv6 không chồng lấn, phù hợp quy mô và nhu cầu mở rộng.
3. Đề xuất ma trận **nguồn → đích → dịch vụ → hành động** để thực thi kiểm soát giữa subnet.
4. Nhận diện giới hạn của phân đoạn theo subnet trong mạng Wi-Fi, VPN, datacenter, cloud và workload động.
5. Xác minh kết quả bằng kiểm tra định tuyến, rule thực tế, log, packet capture và các bài thử allow/deny.

## 2. Phân biệt subnet, VLAN, zone và microsegmentation

| Khái niệm | Vai trò | Có tự bảo đảm cô lập bảo mật không? |
|---|---|---|
| **IP subnet** | Tập địa chỉ cùng tiền tố định tuyến; hỗ trợ cấp IP, route và tổ chức mạng | **Không.** Cần kiểm soát lưu lượng liên subnet và lưu lượng trong subnet nếu có rủi ro. |
| **VLAN (IEEE 802.1Q)** | Chia miền broadcast ở lớp 2, gắn frame vào các VLAN trên trunk | **Không hoàn toàn.** Router/L3 switch vẫn có thể định tuyến tự do giữa các VLAN. |
| **Security zone** | Nhóm tài sản có mức tin cậy/yêu cầu kiểm soát tương tự | Phụ thuộc policy hiệu lực tại ranh giới giữa các zone. |
| **VRF** | Cung cấp bảng định tuyến tách biệt trên thiết bị hỗ trợ | Tách miền định tuyến, nhưng route leaking, shared services và thiết kế control plane vẫn cần đánh giá. |
| **Firewall/ACL** | Thực thi cho phép/chặn theo nguồn, đích, giao thức, trạng thái hoặc danh tính | Có hiệu lực khi traffic đi qua điểm áp dụng và rule đúng. |
| **Microsegmentation** | Áp dụng chính sách chi tiết ở mức workload, endpoint, nhãn hoặc danh tính dịch vụ | Giảm phụ thuộc vào vị trí IP, nhưng vẫn cần coverage, cấu hình và kiểm thử. |

Trong nhiều mạng doanh nghiệp, **một VLAN được gán một subnet IP và một default gateway** đặt trên router hoặc switch lớp 3. Đây là mô hình thông dụng, nhưng không phải quy luật bắt buộc: kiến trúc overlay, virtual networking hoặc một số thiết kế chuyên biệt có thể ánh xạ khác.

~~~mermaid
flowchart LR
    A[Users - VLAN 20 - 10.40.20.0/23] --> R[Router / L3 Switch]
    B[App - VLAN 30 - 10.40.30.0/24] --> R
    C[DB - VLAN 40 - 10.40.40.0/27] --> R
    R --> F[Firewall hoặc ACL liên zone]
    F --> X[Luồng được phép theo chính sách]
~~~

Sơ đồ trên chỉ minh họa các thành phần. **Điểm thực thi thực tế** có thể nằm trên SVI của switch lớp 3, tại router, firewall trung tâm hoặc workload. Nếu lưu lượng Users ↔ DB được định tuyến trực tiếp trên L3 switch mà **không đi qua firewall dự kiến**, firewall ấy sẽ không kiểm soát được luồng này; phải kiểm tra sơ đồ đường đi, bảng route và chính sách trên thiết bị thực.

## 3. Nền tảng CIDR để thiết kế subnet IPv4

Địa chỉ IPv4 gồm **32 bit**. Ký hiệu CIDR **/n** xác định số bit tiền tố mạng; số bit host là **32 − n**. Subnet mask tương ứng có n bit 1 liên tiếp. Ví dụ:

| CIDR | Subnet mask | Số địa chỉ | Số host truyền thống khả dụng |
|---|---|---:|---:|
| /23 | 255.255.254.0 | 512 | 510 |
| /24 | 255.255.255.0 | 256 | 254 |
| /25 | 255.255.255.128 | 128 | 126 |
| /26 | 255.255.255.192 | 64 | 62 |
| /27 | 255.255.255.224 | 32 | 30 |
| /28 | 255.255.255.240 | 16 | 14 |
| /30 | 255.255.255.252 | 4 | 2 |

Với các subnet IPv4 thông thường, hai địa chỉ được dành cho **network address** và **broadcast address**; do đó số host khả dụng truyền thống là **2^(32−n) − 2**. Có ngoại lệ: **/31** có thể dùng cho liên kết point-to-point theo RFC 3021, còn **/32** dùng để biểu diễn một địa chỉ host hoặc route cụ thể. Một số nhà cung cấp cloud còn dành thêm IP trong subnet, nên số IP cấp phát được phải theo **quy định của nền tảng**, không đơn thuần theo bảng trên.

### 3.1. Cách chia một mạng /24 thành các /26

Giả sử nhóm có dải **10.40.100.0/24** và muốn chia thành bốn mạng nhỏ. Mượn thêm hai bit từ phần host sẽ tạo **bốn subnet /26**, mỗi subnet 64 địa chỉ:

| Subnet | Network address | Dải host truyền thống | Broadcast |
|---|---|---|---|
| A | 10.40.100.0/26 | 10.40.100.1 – 10.40.100.62 | 10.40.100.63 |
| B | 10.40.100.64/26 | 10.40.100.65 – 10.40.100.126 | 10.40.100.127 |
| C | 10.40.100.128/26 | 10.40.100.129 – 10.40.100.190 | 10.40.100.191 |
| D | 10.40.100.192/26 | 10.40.100.193 – 10.40.100.254 | 10.40.100.255 |

Lưu ý địa chỉ **10.40.100.64** là network address của subnet B, chứ không phải host bình thường. Gateway phổ biến là địa chỉ host đầu hoặc cuối trong subnet, nhưng **không có quy tắc bắt buộc gateway luôn là .1 hoặc .254**.

### 3.2. Chọn kích thước subnet

- **Đủ số host dự kiến**, kể cả địa chỉ dành cho gateway, thiết bị HA, VIP, DHCP lease, các IP nền tảng dành riêng và tăng trưởng.
- **Dùng VLSM** (Variable Length Subnet Mask) nếu các nhóm có nhu cầu khác nhau; không nhất thiết cấp /24 cho mọi nhóm.
- **Không tạo overlap** trong các miền có thể kết nối qua routing, VPN, cloud peering hoặc mạng đối tác trừ khi có thiết kế giải quyết xung đột địa chỉ rõ ràng.
- **Chừa khoảng để mở rộng** subnet hoặc bổ sung zone, đồng thời quản lý bằng IPAM thay vì cấp IP tùy ý.
- **Cân nhắc tổng hợp route (route summarization)** theo site, zone hoặc region, nhưng không gom prefix để mở quyền truy cập quá rộng trong firewall.

Không dùng địa chỉ **public không thuộc quyền quản lý** làm dải private. Với IPv4 nội bộ có thể sử dụng các dải RFC 1918: **10.0.0.0/8**, **172.16.0.0/12** và **192.168.0.0/16**.

## 4. Subnet segmentation gắn với đường đi của gói tin

Một mạng người dùng tại **10.40.20.0/23** muốn truy cập server **10.40.30.10/24**. Máy người dùng tra bảng định tuyến: đích nằm ngoài subnet nên nó gửi gói qua **default gateway**. Router chọn next hop; nếu tại đó có ACL/firewall phù hợp, rule sẽ kiểm tra luồng. Nếu được phép, gói được chuyển tiếp tới subnet ứng dụng.

~~~mermaid
sequenceDiagram
    participant U as Máy người dùng
    participant G as Gateway/L3
    participant F as Policy enforcement
    participant A as App server
    U->>G: TCP SYN tới App:443
    G->>F: Chuyển tiếp qua chính sách liên zone
    alt Được phép
        F->>A: TCP SYN
        A-->>F: TCP SYN-ACK
        F-->>U: Phản hồi theo state/route
    else Bị chặn
        F--xA: DROP hoặc REJECT theo policy
    end
~~~

Sơ đồ là **luồng logic**: gateway và firewall có thể là cùng một thiết bị, hoặc khác thiết bị. Chiều trả lời phải có route hợp lệ; với **stateful firewall**, phân tích thêm trạng thái kết nối và khả năng xuất hiện **đường đi/về bất đối xứng**. Với thiết bị **stateless**, cần rule chiều về phù hợp.

### 4.1. Lưu lượng cùng subnet có thể bỏ qua firewall liên subnet

Nếu hai máy nằm cùng VLAN và cùng IP subnet, máy gửi thường tìm MAC đích bằng **ARP (IPv4)** hoặc **Neighbor Discovery (IPv6)** rồi gửi frame lớp 2 trực tiếp. Khi đó firewall chỉ đặt tại default gateway có thể **không bao giờ nhìn thấy** lưu lượng giữa hai máy.

Ví dụ: server A và B cùng subnet ứng dụng; nếu A bị chiếm quyền, nó có thể kết nối TCP đến B mà không đi qua firewall liên VLAN. Muốn giới hạn **east–west traffic** trong cùng subnet, có thể cần **private VLAN, port isolation, host firewall, hypervisor/distributed firewall hoặc microsegmentation**.

### 4.2. Phân đoạn ảnh hưởng đến broadcast domain

VLAN riêng thường tạo miền broadcast riêng; ARP request của VLAN Users không tự lan sang VLAN DB. Nhưng **việc subnet hóa IP tự nó không bảo đảm** miền broadcast được chia nếu các subnet cùng chia sẻ một hạ tầng lớp 2 không được cấu hình hợp lý.

Phân đoạn giúp giảm phạm vi một số sự cố broadcast/lớp 2, nhưng không loại bỏ DoS, sự cố route, chuyển tiếp multicast, hoặc quyền truy cập đi ngang đã được cho phép.

## 5. Thiết kế tham chiếu cho hệ thống doanh nghiệp

Giả sử doanh nghiệp có một site và một mạng ứng dụng kết nối qua VPN với cloud. Ta chọn dải quản lý **10.40.0.0/16** và dành các subnet sau làm ví dụ; địa chỉ chỉ phục vụ học tập.

| Zone / nhóm tài sản | Subnet IPv4 | Gateway minh họa | Chức năng |
|---|---|---|---|
| **Users** | 10.40.20.0/23 | 10.40.20.1 | Laptop/desktop nhân viên; khoảng 510 host theo IPv4 truyền thống |
| **Application** | 10.40.30.0/24 | 10.40.30.1 | API, backend và workload ứng dụng |
| **Database** | 10.40.40.0/27 | 10.40.40.1 | Database và node dữ liệu cần bảo vệ |
| **Guest Wi-Fi** | 10.40.50.0/24 | 10.40.50.1 | Thiết bị khách, không tin cậy |
| **VPN-admin** | 10.40.60.0/24 | Theo kiến trúc VPN | IP pool sau xác thực của nhóm quản trị |
| **Security / SOC** | 10.40.70.0/24 | 10.40.70.1 | Sensor, log collector, hệ thống giám sát |
| **Shared services** | 10.40.80.0/24 | 10.40.80.1 | DNS, NTP, DHCP relay/backend, PKI nếu có |
| **Management** | 10.40.90.0/27 | 10.40.90.1 | Jump host, router/switch management và thiết bị quản trị |

Các dải trên **không overlap** và được dùng để minh họa subnet planning; triển khai thực tế phải xem số host, site/region, địa chỉ VPN/đối tác và chính sách cấp IP của nền tảng. Một VPN dùng **địa chỉ được cấp theo phiên** không nhất thiết là một VLAN hoặc subnet Ethernet có default gateway giống host trong LAN.

### 5.1. Trust boundary đề xuất

~~~mermaid
flowchart TB
    U[Users: 10.40.20.0/23] --> P[Inter-zone policy gateway]
    G[Guest Wi-Fi: 10.40.50.0/24] --> P
    V[VPN-admin: 10.40.60.0/24] --> P
    P --> A[Application: 10.40.30.0/24]
    P --> D[Database: 10.40.40.0/27]
    P --> M[Management: 10.40.90.0/27]
    P --> S[Shared services: 10.40.80.0/24]
    A --> L[Telemetry to SOC: 10.40.70.0/24]
    D --> L
    P --> L
~~~

**Lưu ý kiến trúc:** các đường nối thể hiện *khả năng có luồng cần xét chính sách*, **không phải mọi đường đều được phép**. Ví dụ Guests không được đi tới Database/Management chỉ vì sơ đồ cùng nối vào policy gateway.

### 5.2. Ma trận truy cập liên subnet

| Nguồn | Đích | Dịch vụ ví dụ | Quyết định | Lý do |
|---|---|---|---|---|
| Users | Application VIP | TCP 443 | **ALLOW** | Nhân viên dùng ứng dụng qua HTTPS |
| Application (10.40.30.10) | Database (10.40.40.10) | TCP 5432 | **ALLOW** | Backend truy vấn PostgreSQL |
| Users | Database | TCP 5432 và cổng quản trị | **DENY** | Chỉ tầng ứng dụng được truy cập DB |
| Guest Wi-Fi | Application, DB, Management | Mọi cổng | **DENY** | Khách không thuộc vùng nội bộ tin cậy |
| Guest Wi-Fi | Internet và resolver được chỉ định | Dịch vụ thực sự cần | **ALLOW có giới hạn** | Truy cập web/DNS, kiểm soát egress |
| VPN-admin đủ điều kiện | Jump host (10.40.90.10) | TCP 22 hoặc 3389 theo hệ điều hành | **ALLOW có điều kiện** | Quản trị qua điểm trung gian, cần MFA/role |
| Users | Management | SSH/RDP/API quản trị | **DENY** | Ngăn truy cập trực tiếp từ endpoint |
| Application, Database | DNS nội bộ (10.40.80.53) | UDP/TCP 53 | **ALLOW** | Resolver do tổ chức quản lý |
| Workload/Sensor | SOC collector | Cổng telemetry đã xác định | **ALLOW theo nguồn** | Giám sát và điều tra sự cố |
| Các zone | Đích liên zone còn lại | Các giao thức khác | **DENY mặc định** | Quyền tối thiểu giữa subnet |

Đây là **ma trận logic**, chưa bao gồm đầy đủ các luồng phục vụ xác thực, backup, đồng bộ thời gian, health check, cập nhật phần mềm, DNS/PKI, DHCP relay, giám sát và các thông điệp ICMP hợp lệ. Khi triển khai phải bổ sung các ngoại lệ tối thiểu có cơ sở, kiểm thử theo từng dịch vụ; không coi bảng là file cấu hình firewall hoàn chỉnh.

### 5.3. Chính sách giả mã

~~~text
# Pseudocode minh họa. Không chạy trực tiếp trên thiết bị.
allow  Users        -> App_VIP        tcp/443
allow  App_Server   -> DB_Server      tcp/5432
allow  VPN_Admin    -> Jump_Host      tcp/22   when identity/device permitted
allow  App_and_DB   -> DNS_Resolver   udp,tcp/53
allow  Telemetry_Sources -> SOC       approved_log_ports
allow  required ICMP errors / PMTUD and IPv6 on-link control traffic
deny   Guest        -> Internal_Protected_Zones  any
deny   Users        -> Management     any
deny   Users        -> DB             any
deny   other cross-zone traffic
~~~

Với firewall **first-match**, thứ tự allow cụ thể/deny rộng rất quan trọng. Với nền tảng **allow-only, rule priority hoặc cơ chế policy khác**, phải áp dụng theo semantics của chính nền tảng. Một bản subnet plan không chỉ cần địa chỉ mà còn cần **ai kiểm soát policy và policy được thực thi ở đâu**.

## 6. Cách thiết lập ranh giới ở LAN và datacenter

### 6.1. VLAN và inter-VLAN routing

Trên access switch, mỗi cổng hoặc SSID gắn vào một VLAN thích hợp. Switch trunk 802.1Q mang frame của nhiều VLAN giữa các thiết bị được cấu hình phù hợp. Mỗi VLAN thường có **SVI (Switched Virtual Interface)** hoặc router subinterface làm gateway.

**Rủi ro:** nếu switch lớp 3 có các SVI và chức năng inter-VLAN routing, Users có thể tới Database mà không qua firewall ở biên Internet. Vì vậy cần ACL ở SVI, route tới firewall phân đoạn, hoặc kiến trúc enforcement phù hợp. Chỉ cấu hình VLAN ID khác nhau không đủ chứng minh đã giảm lateral movement.

### 6.2. Ranh giới vật lý và logic

| Cách tổ chức | Điểm mạnh | Giới hạn/điều kiện |
|---|---|---|
| Thiết bị/cáp/switch riêng | Ranh giới vận hành rõ, giảm chia sẻ hạ tầng lớp 2 | Tốn chi phí; vẫn có liên kết và đường quản trị phải bảo vệ |
| VLAN + ACL trên L3 switch | Linh hoạt, mở rộng dễ, phù hợp LAN | Cần kiểm tra đúng SVI, thứ tự ACL, IPv6 và các đường bỏ qua |
| Firewall giữa zone | Stateful policy, logging, đôi khi IDS/IPS L7 | Hiệu lực phụ thuộc đường đi; có thể tạo bottleneck/đường đi bất đối xứng |
| VRF tách routing | Hữu ích cho tenant hoặc mạng quản trị | Route leak và shared service có thể tạo đường chéo |
| Host/distributed firewall | Kiểm soát chi tiết intra-subnet và east–west | Cần quản lý policy đồng nhất và bảo đảm agent/điểm thực thi hoạt động |

Mạng quản trị là trường hợp cần bảo vệ đặc biệt: có thể dùng subnet riêng, VRF riêng, jump host, MFA, quyền tối thiểu và kênh **out-of-band** để phục hồi khi đường quản trị chính bị lỗi.

## 7. Subnet segmentation trong Wi-Fi và VPN

### Wi-Fi

Tách **Corporate SSID**, **Guest SSID** và **IoT SSID** sang những VLAN/subnet phù hợp giúp quản trị phạm vi truy cập. Ở Wi-Fi doanh nghiệp, **802.1X/RADIUS** có thể gán VLAN hoặc chính sách động theo danh tính và trạng thái thiết bị, tùy bộ điều khiển/AP.

Tuy nhiên, một SSID hoặc VLAN riêng vẫn cần:

- **Client isolation** nếu thiết bị khách không cần kết nối trực tiếp tới nhau.
- Rule rõ ràng từ Guest/IoT sang mạng nội bộ, với default deny khi phù hợp.
- Kiểm soát DNS, DHCP, default gateway và quyền truy cập Internet cần thiết.
- Quản lý rogue AP, xác thực Wi-Fi và các đường nối vật lý ngoài dự kiến.
- Kiểm chứng IPv6: thiết bị có thể tự cấu hình IPv6 qua RA nếu link có router phù hợp.

### VPN

VPN mã hóa hoặc bảo vệ kênh truyền theo kiểu VPN và cấu hình cụ thể, nhưng **không tự cấp quyền an toàn đến mọi subnet**. Tài khoản VPN bị chiếm có thể trở thành bàn đạp nếu route và firewall cho truy cập quá rộng.

Thiết kế tốt gồm **pool/zone riêng cho từng nhóm**, phân quyền theo role, thiết bị, MFA, split-tunnel policy và danh sách đích cho phép. Kiểm soát **cả route từ client vào nội bộ lẫn đường về**. Với VPN site-to-site/peering, kiểm tra **overlap CIDR**, NAT nếu cần, propagation của route và ảnh hưởng MTU.

~~~text
VPN_Admin  -> Jump_Host      : allow theo danh tính/chính sách
VPN_Admin  -> Database       : deny trực tiếp
VPN_User   -> App_HTTPS      : allow
VPN_User   -> Management     : deny
Guest_WiFi -> Internal_Zones : deny
~~~

## 8. Phân đoạn IPv6: không thể chỉ sao chép tư duy IPv4

IPv6 có không gian địa chỉ và cơ chế khám phá láng giềng khác IPv4. Trong LAN, **/64 thường là prefix chuẩn cho SLAAC** (Stateless Address Autoconfiguration) và phù hợp nhiều chức năng IPv6. Các trường hợp sử dụng độ dài prefix khác cần tuân theo yêu cầu giao thức và thiết kế liên kết.

Một thiết kế minh họa với prefix **2001:db8:40::/48** (dải IPv6 dành cho tài liệu, **không dùng làm mạng công cộng thực tế**):

| Zone | Prefix IPv6 minh họa |
|---|---|
| Users | 2001:db8:40:20::/64 |
| Application | 2001:db8:40:30::/64 |
| Database | 2001:db8:40:40::/64 |
| Guest | 2001:db8:40:50::/64 |
| Management | 2001:db8:40:90::/64 |

Ở mạng thật, dùng prefix IPv6 **được cấp phát hợp lệ** hoặc **ULA (Unique Local Address)** theo RFC 4193 nếu phù hợp với mục tiêu nội bộ. Trong môi trường dual-stack, phải tạo và kiểm thử **policy tương đương cho IPv4 và IPv6**; bật IPv6 mà không kiểm soát lưu lượng có thể tạo đường đi ngoài phân đoạn dự kiến.

**ICMPv6 không chỉ là ping:** Neighbor Solicitation/Advertisement, Router Solicitation/Advertisement và Packet Too Big rất quan trọng cho kết nối IPv6. Chặn toàn bộ ICMPv6 có thể khiến NDP hoặc Path MTU Discovery lỗi; phải lọc theo loại thông điệp, vai trò giao diện và phạm vi on-link. Đối với Wi-Fi/LAN, cân nhắc **RA Guard** và các bảo vệ lớp 2 phù hợp để giảm nguy cơ rogue RA; chúng không thay thế xác thực hay giám sát thiết bị cùng liên kết.

## 9. Subnet trong hạ tầng cloud

Trong cloud, subnet thường là đơn vị phân bổ địa chỉ và gắn tài nguyên vào một miền mạng ảo. Nhưng bảo mật hiệu lực phụ thuộc vào **route table, security group/NSG, network ACL, cloud firewall, network policy, IAM và điểm truy cập dịch vụ**.

| Thành phần | Vai trò trong cloud | Câu hỏi bảo mật |
|---|---|---|
| VPC/VNet | Không gian mạng ảo ở cấp phạm vi cloud | Có peering, transit gateway, hybrid VPN hoặc điểm truy cập ngoài nào? |
| Subnet | Tập địa chỉ dùng cho tài nguyên theo phạm vi nền tảng | Subnet có route tới Internet, NAT, private link hoặc mạng khác không? |
| Route table | Xác định next hop của traffic | Luồng đi qua điểm firewall được thiết kế hay vòng qua bằng route khác? |
| Security group / NSG | Chính sách truy cập gắn tài nguyên hoặc interface theo nền tảng | Có rule quá rộng, áp dụng cả IPv4/IPv6 và đúng workload? |
| NACL / subnet ACL | Chính sách trên ranh giới subnet nếu nhà cung cấp hỗ trợ | Stateful/stateless? Thứ tự rule, chiều về và default action? |
| Cloud firewall / gateway | Enforcement tập trung hoặc phân tán | Có nhìn thấy đầy đủ east–west và traffic qua peering/tunnel không? |
| Host firewall / container policy | Kiểm soát ngay tại workload | Có thể chặn intra-subnet và luồng giữa pod/container khi được thực thi? |

**Ví dụ trên AWS:** security group thường là **stateful allow rules**, còn network ACL là **stateless** và hỗ trợ rule allow/deny theo thứ tự; một subnet “private” do route không đi thẳng ra Internet **không mặc nhiên ngăn lưu lượng từ mạng peering, VPN hoặc các tài nguyên khác trong VPC**. Các đặc tính cụ thể phải kiểm tra theo dịch vụ và nhà cung cấp.

**Trong Kubernetes:** NetworkPolicy, khi CNI triển khai hỗ trợ, có thể phân đoạn các pod theo label/namespace và hướng lưu lượng. Việc chia subnet node hoặc pod **không tự động có chính sách deny traffic giữa workload**. Cần kiểm thử policy thực tế cùng DNS, control plane, ingress và egress.

## 10. Threat modeling cho subnet segmentation

Phân đoạn làm giảm khả năng **di chuyển ngang (lateral movement)** và giới hạn phạm vi ảnh hưởng khi một host bị chiếm. Tuy nhiên không có phân đoạn nào đảm bảo rằng kẻ tấn công không thể vượt ranh giới: quyền danh tính, rule quá rộng, lỗ hổng ứng dụng và đường quản trị có thể tạo lối đi khác.

~~~mermaid
flowchart TD
    A[Attacker chiếm laptop ở Users] --> B{Users có thể kết nối trực tiếp DB?}
    B -- Có --> C[Thử khai thác DB hoặc tài khoản dịch vụ]
    B -- Bị chặn --> D[Đường trực tiếp bị hạn chế]
    D --> E{Có đường qua App/API hợp lệ?}
    E -- Có --> F[Phải kiểm soát app auth, authz, input và quyền DB]
    E -- Không --> G[Giảm thêm bề mặt di chuyển ngang]
    C --> H[Telemetry, phát hiện và ứng cứu]
    F --> H
~~~

### Các kịch bản nên xem xét

| Kịch bản | Cơ chế vượt phân đoạn | Biện pháp giảm nguy cơ |
|---|---|---|
| Laptop người dùng bị chiếm | ACL cho phép Users → DB hoặc Management quá rộng | Default deny liên zone, kiểm thử đường bị cấm và quyền tối thiểu |
| App server bị chiếm | App cần kết nối DB, tài khoản DB quá quyền | Giới hạn source IP/service, quyền DB, mTLS/xác thực và giám sát truy vấn |
| Nhóm Guest Wi-Fi dùng mạng nội bộ | SSID gắn sai VLAN, route/ACL sai, thiếu client isolation | Xác thực/gán VLAN đúng, deny tới internal, thử từ thiết bị khách thực |
| VPN của đối tác mở rộng quyền | CIDR overlap, route quá rộng hoặc rule any-any | Scope route/permission, phân role và review kết nối liên tổ chức |
| Workload cloud ra ngoài không kiểm soát | Egress quá rộng, thay đổi route, public endpoint hoặc service role | Egress filtering, policy-as-code, inventory và phát hiện drift |
| Di chuyển ngang trong cùng subnet | Traffic đi trực tiếp lớp 2, không qua gateway firewall | Host firewall, private VLAN, distributed policy hoặc phân đoạn nhỏ hơn |
| IPv6 bypass rule IPv4 | Policy chỉ có IPv4 nhưng host nhận IPv6 hợp lệ | Thiết kế dual-stack, rule IPv6, kiểm soát RA/NDP và kiểm thử |
| Cố tình làm gián đoạn DNS/ICMP | Rule deny quá mức phá dịch vụ chung/PMTUD | Mô hình hóa luồng hạ tầng tối thiểu, kiểm thử chức năng và log lỗi |

**Rủi ro tồn dư:** ngay cả khi Users không thể truy cập DB trực tiếp, người dùng có thể gửi yêu cầu qua ứng dụng hợp lệ. Nếu API có lỗi phân quyền hoặc injection, dữ liệu vẫn có thể bị lộ. Subnet segmentation là **một lớp phòng vệ**, phải kết hợp xác thực, phân quyền ứng dụng, mã hóa, giới hạn đặc quyền và giám sát xâm nhập.

## 11. Quy trình triển khai có kiểm soát

Không nên bắt đầu bằng cách chia IP thật nhanh rồi hy vọng ứng dụng tự hoạt động. Một quy trình thực tế:

1. **Kiểm kê tài sản và luồng:** IP/MAC, loại thiết bị, owner, môi trường, gateway, route, ứng dụng, DNS/DHCP/NTP/PKI và các kết nối liên quan.
2. **Phân loại trust zone:** Users, Guests, IoT, Application, Database, Management, SOC, Partner, VPN; xem mức nhạy cảm dữ liệu và đường quản trị.
3. **Lập IPAM/CIDR:** đảm bảo đủ IP, không overlap với site/cloud/VPN/đối tác, có chỗ mở rộng và tuân theo nhu cầu IPv6.
4. **Xây topology VLAN/subnet/gateway:** xác định switch/trunk, VRF, route table, điểm thực thi policy và đường dự phòng.
5. **Lập ma trận luồng:** nguồn, đích, giao thức/cổng, lý do nghiệp vụ, mức tin cậy, chiều về và owner.
6. **Thiết kế rule:** giới hạn quyền liên zone, kiểm tra stateful/stateless, NAT, IPv4/IPv6, các luồng vận hành và ngoại lệ có thời hạn.
7. **Triển khai theo từng đợt nhỏ:** dùng pilot/canary, xác định thời điểm ít rủi ro, chuẩn bị kênh quản trị và rollback.
8. **Kiểm thử allow/deny và dịch vụ phụ thuộc:** reachability, xác thực, DNS, log, ứng dụng, failover, PMTU và các luồng được phép đi/về.
9. **Theo dõi và điều chỉnh:** flow log, hit counter, anomaly, error rate, tài sản đổi subnet, thay route và policy drift.
10. **Ghi quyết định và trạng thái:** sơ đồ mới, owner, ngày xác minh, rủi ro tồn dư và điều kiện rà soát khi có thay đổi.

### 11.1. Lưu ý khi di chuyển subnet

Việc chuyển một máy từ subnet này sang subnet khác thường làm thay đổi **địa chỉ IP, default gateway, DHCP reservation, DNS record, firewall object và cơ chế khám phá dịch vụ**. Đồng thời, có thể còn ảnh hưởng allowlist ở hệ thống bên thứ ba, khóa phiên TCP đang mở, route quảng bá và chính sách xác thực. Cần kiểm thử phụ thuộc và kế hoạch quay lại nếu dịch vụ không hoạt động.

Với server hoặc thiết bị mạng quan trọng, cần chuẩn bị **out-of-band management hoặc phương án rollback chắc chắn**; thay nhầm VLAN/route có thể làm mất đường điều khiển thiết bị đang cấu hình.

## 12. Kiểm chứng và chẩn đoán phân đoạn

Mục tiêu kiểm chứng là chứng minh **traffic hợp lệ được đi**, **traffic không được cấp phép bị chặn**, và kết quả đến từ **đúng điểm chính sách**.

### 12.1. Ma trận kiểm thử ví dụ

| Test | Nguồn | Đích | Kết quả mong đợi | Phép kiểm |
|---|---|---|---|---|
| T-01 | Users | App TCP 443 | **ALLOW** | TLS/HTTP thành công và log ghi nhận |
| T-02 | Users | DB TCP 5432 | **DENY** | Không thiết lập kết nối trực tiếp; rule deny/hit/log phù hợp |
| T-03 | App 10.40.30.10 | DB 10.40.40.10 TCP 5432 | **ALLOW** | Kết nối DB và ứng dụng làm việc |
| T-04 | Guest | Management TCP 22 | **DENY** | Không có đường SSH; thấy tại điểm enforcement |
| T-05 | VPN-admin đủ quyền | Jump host 10.40.90.10 TCP 22 | **ALLOW** | Kết nối và xác thực SSH bình thường |
| T-06 | Users thường | Jump host TCP 22 | **DENY** | ACL chặn đúng dù người dùng có IP nội bộ |
| T-07 | App/DB | DNS 10.40.80.53 UDP/TCP 53 | **ALLOW** | Resolver trả kết quả hợp lệ |
| T-08 | Guest | Máy Guest khác nếu có client isolation | **DENY** | Gói không qua gateway vẫn bị cô lập |
| T-09 | Dual-stack workload | Kết nối IPv6 sang vùng bị cấm | **DENY** | Kiểm tra độc lập rule IPv6 |
| T-10 | Ứng dụng qua VPN | Gói lớn/PMTU | **HOẠT ĐỘNG** | Không làm rơi ICMP báo MTU cần thiết |

**Chỉ kiểm thử từ đúng vị trí và tài khoản được ủy quyền.** Kết quả timeout chưa đủ để kết luận firewall chặn: có thể do không có route, host không phản hồi, DNS lỗi, ứng dụng không lắng nghe hoặc đường về bị đứt. Cần đối chiếu log, counter và packet capture.

### 12.2. Lệnh kiểm tra từ máy Linux

~~~bash
# Xem địa chỉ, subnet, default gateway và route
ip -br address
ip route
ip -6 route

# Quan sát route được chọn để đi tới DB
ip route get 10.40.40.10

# Xem ARP/NDP neighbor cache
ip neigh

# Thử một TCP port cụ thể từ zone có quyền kiểm thử
nc -vz -w 3 10.40.40.10 5432

# Kiểm tra tên miền qua DNS được thiết kế
dig @10.40.80.53 example.com

# Khám phá đường đi khi cần
traceroute -n 10.40.40.10
~~~

Nếu có quyền và cần quan sát gói tại giao diện thích hợp (thay **eth0** bằng giao diện thật):

~~~bash
sudo tcpdump -ni eth0 'host 10.40.40.10 and tcp port 5432'
~~~

Không nên tự động xem **ping không phản hồi** là lỗi phân đoạn; Echo có thể bị chặn hoặc rate-limit theo chính sách trong khi TCP tới dịch vụ vẫn bình thường.

### 12.3. Kiểm tra trên Windows PowerShell

~~~powershell
Get-NetIPConfiguration
Get-NetRoute
Get-NetNeighbor

# Kiểm tra một dịch vụ TCP được phép kiểm thử
Test-NetConnection -ComputerName 10.40.40.10 -Port 5432

# Truy vấn DNS qua resolver được chỉ định
Resolve-DnsName example.com -Server 10.40.80.53

# Đường đi cơ bản
tracert -d 10.40.40.10
~~~

### 12.4. Đọc log để tìm nguyên nhân

Đối với mỗi phép thử, so sánh **5-tuple** (IP nguồn, IP đích, protocol, source/destination port), chiều lưu lượng, zone, rule ID, action, thời điểm, NAT, trạng thái phiên và log mạng/host. Với ICMP, phân tích type/code thay cho cổng TCP/UDP.

Khi một truy cập bị cấm vẫn đi được, có thể là:

- Rule allow rộng hơn đã khớp trước rule deny trên firewall first-match.
- Traffic không đi qua firewall cần kiểm soát do **định tuyến trực tiếp, overlay hoặc đường dự phòng**.
- Hai máy **cùng subnet** và giao tiếp qua lớp 2, bỏ qua gateway.
- Một phiên stateful đã tồn tại trước thay đổi rule.
- Cloud policy có cơ chế khác (allow-only hoặc không xét rule theo thứ tự), hay một chính sách ở lớp khác cho phép.
- IPv6 hoặc địa chỉ thay thế không nằm trong tập IP được kiểm soát.

Khi truy cập hợp lệ bị chặn, kiểm tra route, DHCP, gateway, DNS, NAT, stateful return path, port thực tế, service discovery, health check, MTU và các dịch vụ phụ thuộc. **Chỉ mở rộng rule sau khi xác định được đường kết nối cần thiết.**

## 13. Giám sát, IDS/IPS và đánh giá hiệu quả

Phân đoạn là biện pháp phòng ngừa, nhưng cũng tạo những điểm dễ quan sát hành vi bất thường ở ranh giới.

| Tín hiệu | Ý nghĩa có thể có | Cách xác minh |
|---|---|---|
| Users liên tục kết nối tới nhiều DB hoặc cổng admin | Dò quét, nhầm cấu hình hoặc phần mềm trái phép | Correlate IP/user, lịch bảo trì, log firewall và EDR |
| Guest gửi gói tới Management/Database | Thiết bị khách cấu hình sai hoặc cố vượt phân đoạn | Kiểm tra Wi-Fi VLAN/SSID, ACL, nguồn thiết bị và event NAC |
| App gọi tới địa chỉ chưa nằm trong ma trận | Dịch vụ mới, dependency ẩn hoặc dấu hiệu bất thường | Kiểm tra owner, flow log, rollout và mã nguồn nếu thích hợp |
| Truy cập qua VPN tới subnet không được thiết kế | Rule/routing mở quá rộng hoặc phân quyền sai | Đối chiếu nhóm VPN, pool, route, identity và policy |
| Flow log tăng đột biến sau thay đổi | Rule đang chặn ứng dụng hợp lệ hoặc lưu lượng tấn công | Xem change ticket, error metric và packet capture |
| Không thấy log ở điểm enforcement | Traffic bypass hoặc telemetry hỏng | Xác minh đường đi, sensor coverage, thu thập log |

**IDS/IPS và NDR** có thể phát hiện hành vi ở các luồng được phép, nhưng độ bao phủ tùy vị trí sensor và khả năng quan sát traffic mã hóa. Một hệ thống giám sát chỉ nhìn north–south traffic ở biên Internet có thể bỏ lỡ **east–west traffic** bên trong datacenter/cloud.

Các chỉ số theo dõi hữu ích gồm: tỷ lệ luồng liên zone có owner và lý do, số rule any-any/ngoại lệ hết hạn, số đường được phép ngoài ma trận, tỷ lệ test allow/deny đạt, độ phủ flow log theo subnet và thời gian phát hiện drift.

## 14. Những lỗi thiết kế thường gặp

| Ngộ nhận / lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| “Chia VLAN là đã an toàn.” | Inter-VLAN routing mở toàn bộ | Xác định điểm enforcement; áp ACL/firewall theo zone và kiểm thử |
| “Chỉ có host khác subnet mới cần bảo vệ.” | Lateral movement giữa host cùng subnet | Bổ sung host firewall, port isolation hoặc microsegmentation |
| “Tạo subnet private trên cloud là tự cô lập.” | Peering/VPN/route/SG vẫn có thể cấp đường truy cập | Kiểm kê route, endpoint và rule đang có hiệu lực |
| “NAT thay thế firewall.” | Chỉ đổi địa chỉ; không áp dụng nguyên tắc quyền tối thiểu | Thiết kế policy độc lập với NAT |
| “Một firewall rule IPv4 đủ cho dual-stack.” | Traffic IPv6 có thể bypass | Kiểm tra IPv6, RA/NDP và policy tương đương |
| “Càng chia nhiều subnet càng an toàn.” | Vận hành phức tạp, nhiều exception, điểm kiểm soát không thống nhất | Phân đoạn theo trust boundary và nhu cầu truy cập có bằng chứng |
| “Deny all traffic giữa subnet là xong.” | DNS, xác thực, quản lý, backup, PMTU hoặc monitoring có thể hỏng | Lập inventory luồng phụ thuộc và cho phép tối thiểu có kiểm thử |
| “Subnet không overlap trong site là đủ.” | VPN/peering/đối tác dùng cùng CIDR tạo xung đột | IPAM toàn hệ sinh thái, thiết kế site và cloud trước khi nối mạng |
| “ACL ở biên Internet bảo vệ mọi east–west flow.” | Luồng nội bộ có thể đi trực tiếp qua switch/cloud fabric | Xác minh route thực và đặt kiểm soát tại đúng điểm |
| “Không ping được nên phân đoạn đã chặn.” | ICMP bị lọc, nhưng cổng dịch vụ vẫn có thể mở | Kiểm thử đúng cổng và xác minh log/capture |

## 15. Checklist triển khai subnet segmentation

- [ ] Có danh sách tài sản, owner, ứng dụng, đường quản trị và độ nhạy cảm của dữ liệu.
- [ ] Phân zone theo mức tin cậy/nhu cầu nghiệp vụ, không chỉ theo cơ cấu tổ chức.
- [ ] CIDR không chồng lấn trong phạm vi mạng có thể kết nối; dung lượng đủ và có kế hoạch mở rộng.
- [ ] IPAM ghi rõ subnet, VLAN/SSID, gateway, VRF, site/cloud region và owner.
- [ ] Có sơ đồ **đường đi thực**, gồm routing liên VLAN, VPN, cloud peering, NAT và đường dự phòng.
- [ ] Chọn **điểm thực thi policy** mà traffic thực sự đi qua.
- [ ] Có ma trận allow/deny cho nguồn, đích, cổng, protocol và lý do.
- [ ] Kiểm soát đúng traffic **intra-subnet** nếu host cùng subnet không được tin cậy nhau.
- [ ] Cân nhắc cả IPv4 và IPv6; giữ ICMP/ICMPv6 phục vụ PMTU/NDP theo vai trò.
- [ ] Kiểm tra DNS, DHCP, NTP, PKI, logging, backup, health check và các dịch vụ chung.
- [ ] Giới hạn quyền truy cập VPN, Wi-Fi Guest/IoT và mạng quản trị; dùng MFA/NAC khi phù hợp.
- [ ] Thực hiện test allow và deny, so log ở enforcement và capture tại các điểm cần thiết.
- [ ] Chuẩn bị rollback, quản lý thay đổi, phát hiện cấu hình drift và rà soát exception có thời hạn.
- [ ] Ghi nhận rủi ro tồn dư và điều kiện phải đánh giá lại khi có subnet/workload mới.

## 16. Câu hỏi tự kiểm tra

**1. Vì sao hai subnet khác nhau vẫn có thể giao tiếp hoàn toàn tự do?**  
Vì router hoặc switch lớp 3 có thể định tuyến giữa chúng và không có rule hạn chế. CIDR khác nhau tự nó không phải một lệnh deny.

**2. Đặt hai server vào cùng subnet có làm firewall liên VLAN ngăn truy cập giữa chúng không?**  
Không nhất thiết. Chúng có thể giao tiếp trực tiếp ở lớp 2. Cần kiểm soát tại port, host, hypervisor hoặc microsegmentation nếu yêu cầu.

**3. 10.40.100.0/24 được chia thành bốn subnet bằng nhau thì prefix mới là gì?**  
**/26**, mỗi subnet có 64 địa chỉ, thông thường 62 host khả dụng. Các network address là .0, .64, .128 và .192.

**4. Vì sao tạo subnet dành cho Database trong cloud chưa đủ để gọi là “đã cô lập”?**  
Vì route, security group/NSG, ACL, peering, VPN và endpoint còn có thể cho phép những đường truy cập không mong đợi. Phải đối chiếu policy hiệu lực và kiểm thử.

**5. Người dùng VPN truy cập được subnet ứng dụng nhưng không được truy cập quản trị. Có cần sửa default route để mở rộng truy cập không?**  
Không. Trước tiên xác định đó có phải hành vi chính sách dự kiến không; nếu đúng thì giữ deny. Nếu có nhu cầu quản trị hợp lệ, đánh giá role/MFA/thiết bị, route và policy tối thiểu có phê duyệt.

**6. Vì sao kiểm thử phân đoạn phải có cả tình huống kết nối được phép và bị cấm?**  
Chỉ thử allow không chứng minh khả năng cô lập; chỉ thử deny không chứng minh hệ thống vẫn hoạt động. Cần cả hai cùng log, route, ứng dụng và trạng thái phiên.

**7. Tại sao không nên chặn toàn bộ ICMPv6 ở ranh giới subnet?**  
ICMPv6 còn đảm nhiệm báo lỗi như Packet Too Big và những chức năng NDP trong phạm vi liên kết. Chặn thiếu phân biệt có thể gây lỗi IPv6 hoặc PMTUD; chính sách phải xét loại thông điệp và vị trí áp dụng.

## 17. Tài liệu tham khảo

- [RFC 1918 — Address Allocation for Private Internets](https://www.rfc-editor.org/rfc/rfc1918): các dải địa chỉ IPv4 private.
- [RFC 4632 — Classless Inter-domain Routing (CIDR)](https://www.rfc-editor.org/rfc/rfc4632): tư duy CIDR và tổng hợp prefix.
- [RFC 3021 — Using 31-Bit Prefixes on IPv4 Point-to-Point Links](https://www.rfc-editor.org/rfc/rfc3021): trường hợp /31 cho liên kết point-to-point.
- [RFC 4193 — Unique Local IPv6 Unicast Addresses](https://www.rfc-editor.org/rfc/rfc4193): địa chỉ ULA trong IPv6.
- [RFC 4861 — Neighbor Discovery for IPv6](https://www.rfc-editor.org/rfc/rfc4861): khám phá router và láng giềng.
- [RFC 8201 — Path MTU Discovery for IPv6](https://www.rfc-editor.org/rfc/rfc8201): vai trò PMTUD và thông điệp Packet Too Big.
- [NIST SP 800-41 Rev. 1 — Guidelines on Firewalls and Firewall Policy](https://csrc.nist.gov/pubs/sp/800/41/r1/final): chính sách firewall và kiểm soát truy cập mạng.
- [NIST SP 800-207 — Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final): nguyên tắc xác minh và quyền tối thiểu vượt ra ngoài vị trí IP.

**Ghi nhớ:** Subnet segmentation tạo cấu trúc địa chỉ và những vị trí có thể đặt ranh giới truy cập; **segmentation thực sự được chứng minh bởi đường đi, rule được thực thi, thử nghiệm allow/deny và giám sát liên tục**. Thiết kế cần đồng thời giữ kết nối nghiệp vụ cần thiết và hạn chế đường di chuyển ngang khi một host hoặc danh tính bị xâm nhập.
