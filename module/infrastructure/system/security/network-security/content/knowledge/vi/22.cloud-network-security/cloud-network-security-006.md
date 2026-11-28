# Route table và định tuyến giữa các subnet trong bảo mật mạng cloud

Trong chương **Bảo mật mạng cloud** thuộc module **SECURITY_NETWORK_SECURITY**, **route table** là thành phần giúp nền tảng mạng ảo xác định gói IP sẽ được chuyển theo **tuyến nào, đến next hop nào và trong phạm vi mạng nào**. Một kiến trúc cloud có thể tạo nhiều subnet để tách lớp public edge, ứng dụng, cơ sở dữ liệu và quản trị; tuy nhiên, việc “khác subnet” **không tự động bảo đảm cách ly bảo mật**. Nếu các subnet có đường định tuyến tới nhau và chính sách truy cập cho phép, workload ở subnet này vẫn có thể kết nối tới subnet kia.

Thách thức không chỉ là thiết lập route **0.0.0.0/0** ra Internet. Người thiết kế phải hiểu **local/system routes, subnet association, longest-prefix match, đường đi hai chiều, peering/transit/VPN, routing policy, firewall/security group, NAT, IPv6** và khả năng kiểm chứng đường thực tế. Một route quá rộng hoặc next hop sai có thể làm lộ vùng nhạy cảm, đưa lưu lượng đi vòng thiết bị kiểm tra, gây bất đối xứng hoặc tạo blackhole.

Sau bài học, bạn có thể:

- Phân biệt **VPC/VNet, subnet CIDR, route table, route entry, destination prefix, next hop, association và effective routes**.
- Giải thích **định tuyến giữa subnet trong cùng mạng ảo**, giữa các VPC/VNet, qua transit hub, peering, VPN và kết nối on-premises.
- Áp dụng **longest-prefix match**, nhận biết vai trò của route local/system, route mặc định IPv4 **0.0.0.0/0** và IPv6 **::/0**.
- Phân biệt **route cho biết đường đi** với **security group/NSG/firewall cho biết quyền truy cập**.
- Đánh giá các rủi ro **route leak, bypass inspection, asymmetric routing, blackhole, overlapping CIDR và default egress sai**.
- Thiết kế và xác minh đường đi **user → application → database**, kiểm soát east–west và north–south traffic.
- Sử dụng các kỹ thuật **effective route inspection, flow logs, firewall/NVA logs, reachability analysis, IaC review** và kiểm thử được cấp quyền.

## 1. Bản chất của subnet trong cloud

**Subnet** là một phần của không gian địa chỉ IP được cấp cho workload hoặc thành phần mạng trong một hệ thống cloud. Mạng ảo cấp trên thường là **VPC (Virtual Private Cloud)** hoặc **VNet (Virtual Network)** tùy nền tảng. Một subnet thường gắn với một dải CIDR và các quy tắc triển khai tài nguyên, nhưng **chi tiết phạm vi vùng/zone và mô hình gán route** khác nhau giữa nhà cung cấp.

Ví dụ thiết kế IPv4:

~~~text
Virtual network:      10.40.0.0/16

Edge subnet:          10.40.10.0/24
Application subnet:   10.40.20.0/24
Database subnet:      10.40.30.0/24
Management subnet:    10.40.90.0/24

Những dải còn lại: dự phòng cho tăng trưởng hoặc dịch vụ khác
~~~

Các địa chỉ này là **ví dụ mạng private**, không phải tài nguyên thật. Trên thực tế, chọn CIDR cần xét **không chồng lấn** với môi trường on-premises, VPN người dùng, các VPC/VNet khác, đối tác và tương lai mở rộng.

### 1.1. Subnet tách địa chỉ, không tự đặt firewall

Một subnet ứng dụng và subnet database khác nhau có thể:

- **Có route tới nhau** nhờ route nội bộ do cloud tạo hoặc quảng bá.
- **Không cần đi qua Internet gateway** để kết nối qua IP riêng.
- **Không tự bị chặn** chỉ vì mỗi subnet có tên private.
- **Bị chặn hoặc được phép** bởi security group, NSG, subnet ACL, firewall, endpoint policy hoặc lớp ứng dụng tùy kiến trúc.

Tách subnet là cách tổ chức ranh giới và tạo nơi áp policy; muốn có **segmentation hiệu quả** cần kết hợp định tuyến **và** kiểm soát quyền.

### 1.2. Subnet, Availability Zone và vùng cloud

Đừng đồng nhất subnet với zone/region:

- Trên một số nền tảng, subnet thuộc một **Availability Zone** cụ thể; nền tảng khác cho phép subnet có phạm vi **regional**.
- VPC/VNet có phạm vi nhất định do nền tảng quyết định; route có thể được áp theo **subnet, interface hoặc toàn VPC**.
- Luồng giữa các zone có thể phải qua những đường chuyển tiếp, chính sách hoặc điểm kiểm soát khác tùy kiến trúc.

Vì thế, ví dụ “hai subnet trong cùng cloud” **chưa đủ** để xác định route. Cần biết **provider, region, zone, VPC/VNet và effective route scope**.

## 2. Route table chứa những gì?

Một bản ghi route thường gồm:

| Thành phần | Ý nghĩa | Ví dụ khái niệm |
| --- | --- | --- |
| **Destination / prefix** | Dải địa chỉ đích route áp dụng | 10.40.30.0/24 |
| **Next hop / target** | Thành phần chuyển tiếp tới đích | local, virtual appliance, transit hub, VPN, NAT gateway |
| **Address family** | IPv4 hoặc IPv6 | 0.0.0.0/0; ::/0 |
| **Nguồn route** | Route system/local, user-defined/static, dynamic/BGP, propagated | Local route của mạng ảo; route học từ VPN |
| **Association/scope** | Subnet/interface/VRF/network nào chịu ảnh hưởng | Application subnet |
| **Preference/priority** | Thuộc tính chọn tuyến khi có route cạnh tranh | Theo quy tắc của cloud provider |
| **Trạng thái** | Route active, invalid, blackhole hoặc không thể dùng | Next-hop appliance đã bị xóa |
| **Owner/change source** | Người hoặc automation chịu trách nhiệm | IaC deployment, network team |

**Route table không phải danh sách firewall rules.** Một route tới database subnet có thể tồn tại dù firewall cấm mọi kết nối tới database; ngược lại, firewall allow không làm packet đi được nếu thiếu route hoặc next hop không reachable.

### 2.1. Ví dụ route table theo góc nhìn một subnet

~~~text
Subnet: 10.40.20.0/24 (APP)

Destination      Next hop                Ý nghĩa
10.40.0.0/16     local/system            Các prefix trong virtual network
172.20.0.0/16    VPN/transit gateway     Mạng on-premises được phê duyệt
0.0.0.0/0        Egress NAT/firewall     Những đích IPv4 còn lại
::/0             (không có)              Chưa cấp default IPv6 egress
~~~

Đây là **bảng khái niệm**, không phải output đúng định dạng của AWS, Azure hay GCP. Không phải mọi provider cho gán một bảng riêng cho từng subnet, và khả năng thay đổi route local/system có giới hạn khác nhau.

### 2.2. Vì sao cần xem effective routes?

Một bảng người vận hành tự khai có thể chỉ là một phần của quyết định routing. Hệ thống còn có:

- **System-generated local/subnet routes**.
- **Dynamic routes** học qua VPN/BGP hoặc transit.
- **Routes được propagate hoặc import** từ kết nối khác.
- **Routing policies** và các quy tắc ưu tiên theo provider.
- **Route association** trên subnet hoặc network interface.

**Effective route** là kết quả các cơ chế đó áp dụng cho một tài nguyên/phạm vi cụ thể. Khi điều tra, cần kiểm tra **route thực sự được dùng cho đúng nguồn, đích và địa chỉ IP version**, không chỉ một file IaC riêng lẻ.

## 3. Longest-prefix match và lựa chọn tuyến

Ở mô hình định tuyến IP thông thường, một route có **prefix cụ thể hơn** được ưu tiên so với prefix ít cụ thể hơn trong tập tuyến đủ điều kiện:

~~~text
Destination IP: 10.40.30.25

10.40.30.0/24   -> virtual appliance   MATCH, prefix dài nhất
10.40.0.0/16    -> local               MATCH
0.0.0.0/0       -> egress gateway      MATCH

Kết quả khái niệm: route /24 cụ thể hơn được chọn.
~~~

Việc **có thể tạo tuyến /24 qua appliance để thay đổi hành vi local route** phụ thuộc quy tắc và tính năng của cloud provider; không được suy rằng mọi VPC/VNet cho tùy ý thay đường đi nội bộ.

### 3.1. Ba câu hỏi bắt buộc

Khi thiết bị A kết nối thiết bị B:

1. **Bảng route/phạm vi nào được dùng cho packet tại điểm nguồn?** Có áp subnet association, routing policy, VRF hoặc interface route không?
2. **Trong những route hợp lệ, route nào được chọn cho destination IP?** Cần xét prefix dài nhất và policy/priority khi các route cạnh tranh.
3. **Next hop có tồn tại và hoạt động không?** Nếu chỉ có route chỉ tới appliance bị lỗi hoặc endpoint bị xóa, packet có thể bị drop/blackhole.

Khi nhiều route có **cùng prefix**, quy tắc chọn giữa static/system/BGP/propagated routes khác nhau giữa các nhà cung cấp và loại route. **Không mang một bảng administrative distance của router truyền thống áp nguyên xi cho mọi cloud.**

### 3.2. 0.0.0.0/0 và ::/0

- **0.0.0.0/0** là default route IPv4, khớp với mọi đích IPv4 không có route cụ thể hơn.
- **::/0** là default route IPv6 theo nguyên tắc tương ứng.
- **Default route không tự cấp public IP**, không tự mở firewall, không tự tạo NAT và không xác nhận lưu lượng đã ra Internet.
- Một subnet có thể **không có default Internet route** nhưng vẫn liên lạc với những subnet/network có route cụ thể hơn.

Đặc biệt trong cloud dual-stack, **IPv4 đi qua NAT firewall** không đảm bảo **IPv6 cũng đi qua cùng điểm kiểm soát**. Phải kiểm tra IPv4/IPv6 độc lập.

### 3.3. Route đích cụ thể có thể lấn default route

Nếu APP có tuyến tới **172.20.0.0/16** qua VPN và default qua NAT, request tới **172.20.10.15** đi qua route VPN, không đi NAT. Điều này thường là mong muốn cho kết nối hybrid.

Ngược lại, nếu ai đó đưa **0.0.0.0/0 qua VPN** mà kiến trúc chưa chủ đích dùng **forced tunneling**, toàn bộ egress IPv4 không có route cụ thể hơn có thể chuyển đường. Hệ quả có thể là mất Internet, tăng chi phí, bỏ qua egress inspection hoặc thay đổi IP public xuất hiện với đối tác.

## 4. Luồng packet giữa hai subnet trong cùng mạng ảo

Xét hai workload:

~~~text
Application VM/Pod IP:  10.40.20.15
Database VM IP:         10.40.30.25
DB service:             TCP 5432

Application subnet:     10.40.20.0/24
Database subnet:        10.40.30.0/24
Virtual network CIDR:   10.40.0.0/16
~~~

~~~mermaid
flowchart LR
    U["User / client"] --> E["Public edge / application gateway"]
    E --> A["APP subnet 10.40.20.0/24"]
    A -->|IP private, TCP 5432| D["DB subnet 10.40.30.0/24"]
    A -. "Local/system route" .-> R["Cloud virtual routing fabric"]
    R --> D
    D -. "DB policy" .-> F["Firewall / SG / NSG controls"]
    A -. "APP policy" .-> F
~~~

Sơ đồ mô tả các lớp trách nhiệm, **không phải đường data plane bắt buộc đi qua một router VM hiển thị được**. Cloud thường thực hiện routing trong hạ tầng mạng ảo do nhà cung cấp vận hành.

### 4.1. Phân tích theo từng bước

1. Ứng dụng cần truy cập **10.40.30.25:5432**.
2. Network stack của workload xác định next hop ở tầng host/virtual interface theo cấu hình.
3. Nền tảng cloud chọn effective route phù hợp **đích 10.40.30.25**.
4. Hạ tầng chuyển tiếp packet tới workload đích nếu có đường hợp lệ.
5. **Security groups/NSG/firewall** của cả nguồn và đích, hoặc những lớp policy nằm trên đường, quyết định traffic được phép hay bị chặn.
6. Database service lắng nghe cổng, kiểm tra authentication/authorization, và phải có **đường hồi đáp**.

**Một route local nội bộ không tự cho phép TCP 5432.** Phải kiểm tra cả network policy và ứng dụng.

### 4.2. Vì sao public/private subnet không đồng nghĩa Internet/no Internet?

Trong một số kiến trúc như AWS, “public subnet” thường mô tả subnet có route thích hợp tới **Internet gateway** và workload cần public address/điều kiện khác để thực sự giao tiếp trực tiếp với Internet. “Private subnet” thường không cho workload truy cập trực tiếp Internet qua Internet gateway và có thể dùng **NAT gateway/egress proxy** cho kết nối outbound.

Nhưng các từ public/private là **nhãn kiến trúc**, không phải security flag phổ quát giữa các cloud. Cần kiểm tra **route, public endpoint/address, ingress/egress firewall, NAT và service configuration**.

Một DB subnet không có default Internet route vẫn có thể bị truy cập từ một subnet khác trong virtual network nếu policy cho phép. Vì thế, **data isolation phải được thực thi**, không dựa riêng vào thiếu đường ra Internet.

## 5. Route và security controls: ai quyết định điều gì?

| Lớp | Quyết định chính | Ví dụ |
| --- | --- | --- |
| **Route table** | Packet được chuyển tới next hop nào? | 10.40.30.0/24 qua local |
| **Security group / NSG** | Workload hoặc interface được phép gửi/nhận flow nào? | DB chỉ nhận TCP 5432 từ APP role/subnet được duyệt |
| **Subnet network ACL** | Quy tắc cho traffic qua subnet boundary nếu provider có loại này | Chặn CIDR/port theo inbound/outbound policy |
| **Firewall/NVA** | Inspection, stateful filtering, application controls tại điểm chuyển tiếp | Egress cho phép HTTPS tới service được duyệt |
| **IAM / cloud control plane** | Ai được sửa route, subnet associations, SG/NSG? | Chỉ network deployment role được cập nhật route table |
| **Application authorization** | User/service identity có quyền thực hiện hành động không? | DB role chỉ được đọc dữ liệu được cấp |
| **DNS policy** | Tên dịch vụ phân giải tới IP/endpoint nào? | Internal API trỏ private IP, không public endpoint |
| **Observability** | Có nhìn thấy tuyến và hoạt động thực tế không? | Flow logs, gateway logs, route change audit |

### 5.1. Stateful và stateless: phân biệt theo sản phẩm

Một số hệ thống dùng **stateful security groups**: kết nối được cho phép có thể nhận response traffic theo connection tracking. Một số mô hình **subnet ACL** có tính **stateless** và yêu cầu cấu hình đường đi/đường về cùng các cổng phù hợp.

Không áp một kết luận cho mọi provider:

- AWS **security group** thường là stateful ở phạm vi ENI, trong khi **network ACL** tại subnet có tính stateless.
- Azure có **NSG** áp rule ở subnet/NIC theo hành vi của nền tảng và hỗ trợ connection state trong nhiều tình huống; route do system, UDR hoặc BGP được xử lý riêng.
- GCP áp **VPC firewall policies/rules** và các lớp network security tương ứng; route được quản lý ở phạm vi và cơ chế khác AWS.

Phải kiểm tra semantics của **dịch vụ và phiên bản** đang dùng, đặc biệt khi đường traffic phải qua third-party virtual appliance.

### 5.2. Route có thể bypass security inspection

Giả sử network team đặt **firewall tập trung** để kiểm tra APP → DB. Nếu route chọn đường **local trực tiếp** thay vì một đường chuyển tiếp qua NVA/inspection đã được thiết kế, firewall có thể **không quan sát bất kỳ packet nào của flow đó**.

Một rule rất chặt trên firewall **không có tác dụng với traffic không đi qua nó**. Vì thế, yêu cầu “phải kiểm tra east–west traffic” cần được chứng minh bằng **route selection, enforcement placement và kiểm thử đường đi**.

## 6. Route association: cấu hình đúng bảng cho đúng subnet

Một nguồn lỗi phổ biến là **route table đúng nhưng không được gắn tới subnet có traffic cần kiểm soát**, hoặc subnet thừa hưởng một bảng mặc định không như mong đợi.

### 6.1. Mô hình association

~~~text
Subnet EDGE (10.40.10.0/24) -> Route policy/table EDGE
Subnet APP  (10.40.20.0/24) -> Route policy/table APP
Subnet DB   (10.40.30.0/24) -> Route policy/table DATA

Mục tiêu:
  EDGE:    egress/inbound theo Internet edge policy
  APP:     route tới DB/internal + approved egress inspection
  DB:      private/internal routes; không direct Internet egress
~~~

Đây là mô hình phân quyền route theo subnet. **Không phải mọi cloud có object “một route table mỗi subnet” giống nhau**; cần map ý tưởng sang route association/policy thực của provider.

### 6.2. AWS: main và explicit route table associations

Trong mô hình AWS VPC phổ biến:

- Một VPC có **main route table**; subnet không được explicit associate với route table khác sẽ dùng main.
- Có thể tạo các **custom route tables** và gắn chúng với các subnet để xác định route được áp.
- Route table thường có **local routes** cho VPC CIDR và các route user tạo hoặc propagated tùy cấu hình.
- Đường tới Internet gateway, NAT gateway, peering connection, Transit Gateway, VPN hay firewall appliance phải sử dụng **route targets hợp lệ**.

**Rủi ro:** một subnet nhạy cảm không được gắn explicit table có thể thừa hưởng main table vốn có default route tới đường egress không mong muốn. Trước thay đổi, cần review **association thực** và **đường quay về**.

### 6.3. Azure: system routes, UDR và effective routes

Trong Azure VNet, nền tảng thường tạo **system routes** cho network prefixes và những đường mặc định phù hợp. Quản trị viên có thể dùng **User-Defined Routes (UDR)** gắn với subnet để điều chỉnh lưu lượng, chẳng hạn chỉ định **virtual appliance** hoặc các next-hop types được hỗ trợ.

Các tuyến do **BGP/on-premises gateway** cung cấp cũng có thể tham gia vào effective routing. Thứ tự ưu tiên và các giới hạn thực tế phụ thuộc route type, prefix và quy tắc Azure; nên dùng **effective routes ở NIC/subnet** để kiểm chứng thay vì chỉ xem UDR do người dùng tạo.

### 6.4. GCP: routing ở phạm vi VPC không giống subnet route table của AWS

Trong Google Cloud VPC, **subnet routes, static routes và dynamic routes** được quản lý theo mô hình của VPC network, với scope/priority và chính sách mạng tùy loại route. Một subnet **không nhất thiết có route-table association riêng** theo kiểu AWS.

Khi dịch kiến trúc giữa provider, hãy phân biệt rõ:

- **Route resource/policy scope** thực ở nhà cung cấp.
- **Static/dynamic/system-generated routes**.
- Các quy tắc về **route priority, next-hop validity, peering và dynamic routing mode**.
- Firewall rules/policies độc lập với quyết định route.

Đừng sao chép Terraform hay sơ đồ “mỗi subnet một bảng route” từ AWS vào GCP rồi mặc định rằng security boundary tương đương.

## 7. So sánh mô hình route AWS, Azure và GCP

| Khía cạnh | AWS VPC | Azure VNet | Google Cloud VPC |
| --- | --- | --- | --- |
| **Phạm vi routing phổ biến** | Route table gắn subnet; main/custom associations | System routes và UDR gắn subnet; effective routes tại NIC | Route resources và subnet routes trong mô hình VPC; không mặc định per-subnet table kiểu AWS |
| **Đường nội bộ** | Local route cho VPC CIDR theo khả năng và policy | System routes cho các prefix phù hợp | System-generated subnet routes và cloud fabric |
| **Internet egress** | IGW/NAT gateway hoặc target khác tùy kiến trúc | Internet route/NAT gateway/firewall/NVA theo topology | Default internet gateway, Cloud NAT hoặc next hop khác theo cấu hình |
| **Hub/transit** | Transit Gateway, peering, Cloud WAN/VPN và giải pháp tương ứng | Hub-and-spoke, peering, VPN/ExpressRoute, Route Server và NVA | VPC peering, Network Connectivity Center, VPN/Interconnect và các kết nối tương ứng |
| **Security enforcement** | Security groups, network ACLs, Network Firewall/thiết bị khác | NSG, Azure Firewall/NVA, policy liên quan | VPC firewall policy/rules, Cloud NGFW và thành phần liên quan |
| **Nguồn dynamic route** | BGP/VPN, propagated routes tùy gateway/table | BGP/gateway/route server và effective routing | Cloud Router/BGP và dynamic route modes |
| **Điểm QA quan trọng** | Subnet association, route targets, return path, SG/NACL | UDR + system + propagated, effective NIC routes, NVA forwarding | VPC route scope/priority, route eligibility, firewall và next-hop reachability |

**Bảng chỉ tổng hợp kiến trúc**; khả năng và tên dịch vụ có thể thay đổi theo sản phẩm, loại tài khoản, vùng, phiên bản và tính năng mới. Không dùng bảng này thay tài liệu provider hoặc output effective routes của môi trường cụ thể.

### 7.1. “Route table” có thể là các object khác nhau

Trong AWS còn có **Transit Gateway route tables** dành cho routing giữa các attachments; chúng **không phải** subnet route tables bên trong từng VPC. Trong mô hình hub-and-spoke Azure/GCP, route propagation và policy có thể quyết định reachability ở nhiều cấp.

Khi một flow đi qua transit, phải kiểm tra **mỗi routing domain và mỗi attachment** chứ không chỉ subnet nguồn.

## 8. Public subnet, private subnet, NAT và đường egress

### 8.1. Phân biệt outbound và inbound

Một **default route qua NAT gateway/egress firewall** thường phục vụ kết nối outbound từ workload private tới Internet hoặc dịch vụ bên ngoài. Nó **không tự cho phép bên ngoài chủ động tạo phiên inbound** tới private workload.

~~~mermaid
flowchart LR
    A["APP private subnet"] --> N["NAT / Egress security"]
    N --> I["Internet / external API"]
    I -. "Return traffic for existing flow" .-> N
    N -. "Translated return path" .-> A
    U["Unsolicited Internet client"] -. "Không có inbound mapping mặc định" .-> A
~~~

**NAT không phải firewall hoặc authentication.** Việc một workload dùng IP private và NAT không tự bảo vệ ứng dụng nếu firewall/identity policies sai; NAT chủ yếu chuyển đổi địa chỉ và thiết kế kết nối.

### 8.2. DB subnet có cần default route?

Câu trả lời phụ thuộc dependencies. Database có thể cần kết nối tới **dịch vụ backup, update, logging, KMS, identity hoặc monitoring**. Có các hướng:

- Chỉ cấp **private routes** tới các service endpoints/đường mạng được duyệt.
- Sử dụng **private endpoints/PrivateLink hoặc phương án tương đương** khi provider và service hỗ trợ.
- Nếu cần egress Internet, dùng **egress firewall/proxy/NAT có policy hẹp**, không mở “mọi nơi” theo thói quen.
- Kiểm tra **DNS, route và firewall** cho các dịch vụ phụ thuộc trước khi xóa default route.

**Không có 0.0.0.0/0** có thể tăng độ cô lập nhưng cũng có thể gây outage nếu thiếu routes tới dependency cần thiết. Kiến trúc phải dựa trên **network flows đã được kiểm kê**.

### 8.3. IPv6 cần route và policy riêng

IPv6 có thể cung cấp globally routable addresses mà không dùng NAT IPv4 theo mô hình quen thuộc. Các route **::/0**, IPv6 firewall, public endpoints và egress-only capability (nếu provider hỗ trợ) phải được đánh giá độc lập.

Một ứng dụng có bản ghi **AAAA** và IPv6 route ra ngoài có thể chọn IPv6 dù đội vận hành chỉ kiểm thử IPv4 NAT/inspection. **Dual-stack không thể được chứng minh an toàn chỉ bằng bảng IPv4.**

## 9. Định tuyến giữa VPC/VNet: peering, transit và mạng hybrid

Khi subnet nguồn và đích nằm trong **hai mạng ảo khác nhau**, route nội bộ của một VPC/VNet thường **không tự tạo kết nối** tới mạng còn lại. Cần một cơ chế networking hợp lệ và chính sách routing tương ứng.

~~~mermaid
flowchart LR
    A["VPC APP 10.40.0.0/16"] --> H["Transit / Hub / Peering / VPN"]
    H --> B["VPC DATA 10.50.0.0/16"]
    H --> O["On-premises 172.20.0.0/16"]
    A -. "Source route + SG" .-> X["Security / Flow validation"]
    B -. "Destination route + SG" .-> X
    O -. "Return path + firewall" .-> X
~~~

### 9.1. Peering không mặc định tạo transit đầy đủ

VPC/VNet peering thường cho phép kết nối private giữa hai mạng theo điều kiện provider. Tuy nhiên:

- **Kết nối peering không tự làm mọi subnet được phép nói chuyện.**
- Nhiều nền tảng có hạn chế về **transitive routing** qua peering; không thể giả định A peering B và B peering C thì A tự tới C.
- Cần kiểm tra **route propagation, DNS resolution, firewall policies và return path**.
- CIDR overlapping có thể khiến peering không được hỗ trợ hoặc routing không xác định theo quy tắc provider.

Nếu cần hub transit lớn, nên dùng dịch vụ **transit/hub routing** được thiết kế cho việc đó, có segmentation và route policy rõ ràng.

### 9.2. Transit Gateway/hub có route table riêng

Một flow APP → DATA qua transit thường trải qua:

~~~text
1. APP subnet effective route: 10.50.0.0/16 -> transit attachment
2. Transit/hub route domain:  10.50.0.0/16 -> DATA attachment
3. DATA network routing:      packet tới destination subnet/workload
4. DATA firewall/policy:      quyết định có cho phép flow không
5. Return route:              10.40.0.0/16 quay về APP qua đường hợp lệ
~~~

Nếu thiếu **bước 2 hoặc 5**, packet có thể mất dù source route và security group có vẻ đúng.

### 9.3. VPN/Interconnect và BGP route propagation

Kết nối on-premises thường sử dụng **site-to-site VPN, dedicated/private connectivity hoặc SD-WAN**. Gateway có thể nhận route từ **BGP** hoặc dùng static routes.

Rủi ro đặc trưng:

- On-premises quảng bá **0.0.0.0/0** ngoài ý muốn; cloud workloads đổi đường Internet egress.
- Route CIDR quá rộng từ đối tác làm lộ vùng nội bộ.
- Thiếu route quay về trong firewall/router on-premises.
- Một tunnel UP nhưng **BGP session/route propagation** không cung cấp đường đi cần thiết.
- Bất đối xứng qua hai VPN links làm firewall stateful từ chối response.

Cần giới hạn **prefix được import/export**, phân biệt các VRF/route domains và kiểm chứng effective routes ở cả hai đầu.

## 10. NVA/Cloud Firewall và forced tunneling

**Network Virtual Appliance (NVA)** là VM hoặc dịch vụ bảo mật/định tuyến đứng trên đường chuyển tiếp để thực hiện inspection, NAT, routing hoặc các control khác. Trong cloud có thể dùng **managed firewall** hay third-party appliances tùy nhu cầu.

### 10.1. East–west inspection và north–south inspection

- **North–south:** lưu lượng giữa workload và Internet/on-premises/ngoài trust boundary.
- **East–west:** lưu lượng giữa subnet, workload hoặc VPC/VNet trong cùng hoặc liên quan các vùng nội bộ.

Chỉ đặt firewall tại **Internet edge** có thể không thấy một kết nối **APP → DB** nếu cloud fabric định tuyến trực tiếp theo local route. Nếu threat model yêu cầu kiểm tra east–west, phải thiết kế **traffic steering** phù hợp với khả năng của provider.

### 10.2. Phải giữ forward và return path nhất quán

Ví dụ abstract:

~~~text
APP 10.40.20.15
   |
   | route DB prefix -> NVA
   v
NVA 10.40.90.10
   |
   v
DB  10.40.30.25

Nếu DB reply đi thẳng về APP theo local route:
   DB -> APP (không qua NVA)

Kết quả có thể là asymmetric routing.
~~~

Một **stateful firewall** thường cần nhìn được trạng thái kết nối của cả hai hướng, trừ khi có cơ chế state sharing/flow symmetry đặc thù. Đường trả về khác đường đi có thể khiến response bị drop hoặc session không được theo dõi đúng.

### 10.3. Những thành phần cần có ở NVA

1. **IP forwarding** hoặc tính năng network appliance mode phù hợp được bật trên tài nguyên và trong OS/appliance khi cần.
2. Có đủ **interfaces, route tables và next hops** để forward tới destination.
3. **Firewall policy** cho phép các flow đã được phê duyệt, default deny cho những luồng khác.
4. Thiết kế **return-path symmetry**, NAT/SNAT nếu được lựa chọn, và stateful session behavior.
5. **HA/failover** phù hợp từng zone và region, route failover/health monitoring.
6. Capacity cho **throughput, concurrent sessions, TLS inspection**, logging và tăng trưởng.
7. Trường hợp NVA lỗi: **fail-open hay fail-closed**, ai phê duyệt và tác động bảo mật/khả dụng.

**Đặt một next hop IP tới VM chưa tự tạo ra firewall hoạt động.** Nếu NVA chưa bật forwarding, không có route trả về hoặc policy sai, luồng có thể thành blackhole.

### 10.4. Bypass cần được kiểm thử

Hãy xác định liệu workload có thể:

- Chọn **đường local/peering** không qua firewall dự kiến?
- Có **secondary network interface**, public endpoint hoặc IPv6 egress riêng?
- Đi qua **private service endpoint** có chính sách bảo mật khác?
- Sử dụng **route cụ thể hơn** do propagation từ gateway khác?
- Dùng **connection state** vẫn còn trên đường cũ sau thay đổi route?

Một kiểm thử tốt phải chứng minh **flow thực đi qua enforcement point** bằng log/session evidence, không chỉ nhìn sơ đồ.

## 11. Threat model: các lỗi route ảnh hưởng an toàn cloud

| Threat / tình huống | Nguồn rủi ro | Hậu quả có thể xảy ra | Phòng ngừa và phát hiện |
| --- | --- | --- | --- |
| **Route leak giữa các vùng** | Import/propagation CIDR hoặc route target quá rộng | Truy cập ngoài ý muốn giữa tenant/VRF/VPC | Prefix allowlists, segmentation, review route domains |
| **Direct egress bypass** | Subnet có default route qua gateway ngoài egress firewall | Không có inspection/egress policy, tăng rủi ro dữ liệu đi ra ngoài | Approved next-hop policy, flow validation, config guardrails |
| **Local east–west bypass** | APP → DB đi trực tiếp dù policy yêu cầu NVA | Firewall tập trung không nhìn thấy flow | Traffic steering đúng khả năng provider, end-to-end tests |
| **Blackhole** | Next hop bị xóa, NVA chết, route thiếu target hợp lệ | Gián đoạn API/DB, retry storm | Route health/blackhole alerts, IaC dependency, failover runbook |
| **Asymmetric routing** | Forward qua firewall, response đi đường local/khác zone | Stateful session drop và khó điều tra | Return-path mapping, SNAT theo thiết kế, symmetry tests |
| **Default route injection** | BGP/route propagation đưa 0/0 không được duyệt | Đổi egress, mất Internet hoặc đi qua đối tác | Prefix filters, explicit acceptance, change monitoring |
| **CIDR overlap** | On-prem, peering, VPN, cloud networks trùng địa chỉ | Khó route chính xác, split routing hoặc connectivity failure | Global IPAM, non-overlapping CIDR allocation |
| **Over-permissive connectivity** | Route thông nhưng SG/NSG/firewall quá rộng | Lateral movement tới data/management subnet | Default deny, role identity, negative tests |
| **Unauthorized route modification** | IAM bị chiếm hoặc IaC token quyền quá lớn | Thay next hop/association và bypass security | Least privilege IAM, MFA, approvals, audit, policy-as-code |
| **Internet exposure sai** | Public IP + inbound rule + internet route không kiểm soát | Workload nhạy cảm reachable từ ngoài | Asset exposure inventory, firewall/SG validation, public endpoint controls |
| **IPv6 escape path** | IPv4 đã inspect, ::/0 hoặc public IPv6 còn đi thẳng | Lưu lượng ra ngoài không qua policy mong muốn | Dual-stack route/firewall review, IPv6 negative tests |
| **DNS mismatch** | Private DNS trả IP public/nhầm VPC | Traffic chọn route không dự kiến | Split DNS/Private DNS policy, query + route correlation |
| **Transit route table mismatch** | Attachment và route domain không đồng nhất | Flow tới sai spoke hoặc mất đường trả về | Attachment inventory, propagated route audit, reachability analysis |

### 11.1. Route leak không đồng nghĩa traffic đã vượt firewall

Một route bị leak có thể **tạo khả năng định tuyến** tới subnet ngoài ý muốn, nhưng vẫn có thể bị SG/NSG/firewall chặn. Cần phân biệt:

- **Potential reachability:** có đường đi nếu những policy khác cho phép.
- **Permitted network flow:** policy enforcement cho phép connection cụ thể.
- **Observed successful access:** endpoint/app thực sự nhận và xử lý thao tác.

Không kết luận dữ liệu đã bị truy cập chỉ từ việc phát hiện route được thêm.

### 11.2. Route tampering có thể là lỗi automation

Đổi route table do deployment bị lỗi có thể tạo hậu quả tương đương sự cố an ninh. Khi điều tra, cần **actor, API action, role, resource ID, config revision và change window** để phân biệt sai cấu hình với truy cập trái phép.

### 11.3. Không phải route sai nào cũng cần “chặn Internet”

Nếu business service phải gọi API ngoài, chỉ xóa default route sẽ tạo outage. Biện pháp đúng có thể là **đổi next hop về egress firewall**, chỉ cấp endpoint/service cụ thể, hoặc dùng private connectivity. Phòng vệ phải giữ **luồng hợp lệ** theo SLO.

## 12. Thiết kế phân đoạn APP–DB–MGMT có thể kiểm chứng

Giả sử một dịch vụ gồm:

~~~text
VPC / VNet:    10.40.0.0/16
EDGE subnet:   10.40.10.0/24
APP subnet:    10.40.20.0/24
DB subnet:     10.40.30.0/24
MGMT subnet:   10.40.90.0/24
On-prem:       172.20.0.0/16

Allowed business flows:
Internet -> EDGE        TCP 443 tới approved public entry
EDGE     -> APP         TCP 8443 hoặc app port được phê duyệt
APP      -> DB          TCP 5432 chỉ từ APP identity được phép
MGMT     -> APP/DB      Chỉ qua bastion/JIT management path
APP      -> Internet    Qua approved egress/NAT policy
DB       -> Internet    Default deny, ngoại lệ có đánh giá
~~~

### 12.1. Ma trận tuyến và đường kiểm soát

| Nguồn → đích | Route/next hop cần xét | Enforcement cần có | Test bắt buộc |
| --- | --- | --- | --- |
| **Internet → EDGE** | Public endpoint/edge route theo thiết kế | WAF/LB/SG/firewall ingress | Only HTTPS 443 từ phạm vi được phép |
| **EDGE → APP** | Local/private route | App SG/NSG, mTLS khi áp dụng | Chỉ app port; chặn SSH/RDP trái quyền |
| **APP → DB** | Local hoặc NVA/inspection nếu chủ đích | DB SG/NSG và DB auth; NVA nếu bắt buộc | 5432 allowed theo identity, port khác denied |
| **USER → DB trực tiếp** | Có thể có local route | DB policy phải chặn | Negative test từ USER subnet |
| **MGMT → APP/DB** | Bastion/management path theo kiến trúc | PAM/JIT, admin auth, firewall, audit | Chỉ tài khoản quản trị hợp lệ |
| **APP → Internet** | Default qua egress firewall/NAT | Egress allowlist, DNS và logs | Outbound đúng đích, source IP dự kiến |
| **DB → Internet** | Không có direct default hoặc đi qua exception path | Restricted egress + audit | Negative direct egress; positive backup/KMS nếu cần |
| **APP → on-prem** | 172.20.0.0/16 qua VPN/transit | Routing policy + on-prem firewall | Đúng site/port, return path và DNS |

**Ma trận chỉ là thiết kế**, phải đối chiếu capabilities của provider và platform hiện tại. Trong nhiều cloud, lưu lượng nội bộ có thể đi theo system local route, nên yêu cầu “qua NVA” cần khả năng **traffic steering chuyên biệt** chứ không chỉ thêm một dòng route bất kỳ.

### 12.2. Không dùng CIDR quá rộng thay thế identity

Rule “DB nhận toàn bộ 10.40.0.0/16” dễ cấu hình nhưng cho phép quá nhiều nguồn cùng VPC/VNet. Khi có thể, ưu tiên **security group reference, workload identity, tag/service account hoặc role-based policy** do provider hỗ trợ; đồng thời duy trì **DB authentication**.

CIDR vẫn hữu ích cho các ranh giới route/ACL, nhưng **identity và mục đích truy cập** là những tín hiệu mạnh hơn cho policy ứng dụng.

### 12.3. Hãy mô hình hóa return path

Ở trạng thái khỏe:

~~~text
APP 10.40.20.15:51000  ->  DB 10.40.30.25:5432
DB  10.40.30.25:5432   ->  APP 10.40.20.15:51000
~~~

Nếu đường đi qua NVA có SNAT, packet DB nhìn thấy có thể mang **source IP của NVA** thay vì APP thật. Điều này ảnh hưởng **audit, firewall allowlist, connection correlation** và khả năng ứng dụng ghi đúng identity. Không dùng SNAT như giải pháp ngẫu hứng để che vấn đề routing nếu nó làm mất yêu cầu điều tra.

## 13. IaC và policy-as-code cho route tables

Route changes cần được review như **thay đổi security boundary**, đặc biệt với production, data subnet và kết nối ngoài tổ chức.

### 13.1. Mẫu policy mô tả (không phải cú pháp cloud provider)

~~~yaml
# Đặc tả phục vụ architecture review; không deploy trực tiếp.
control_id: CLOUD-NET-ROUTES-006
environment: production
virtual_network: "10.40.0.0/16"
address_families: [IPv4, IPv6]

subnet_policies:
  edge:
    cidr: "10.40.10.0/24"
    internet_egress: "approved edge gateway only"
  app:
    cidr: "10.40.20.0/24"
    internet_egress: "egress inspection / NAT"
    allowed_internal_destinations:
      - "database service via approved private path"
      - "management services only by policy"
  data:
    cidr: "10.40.30.0/24"
    direct_internet_egress: false
    permitted_dependencies:
      - "approved private backup/KMS/monitoring endpoints"
  management:
    cidr: "10.40.90.0/24"
    access: "bastion / privileged identity with audit"

route_security:
  forbid_unapproved_default_route_to_internet: true
  forbid_unapproved_cross_tenant_route_import: true
  require_return_path_review_for_stateful_nva: true
  deny_overlapping_cidr_allocations: true
  require_ipv6_route_review: true
  require_route_change_audit: true

validation:
  - "Effective routes match approved architecture"
  - "APP-to-DB allowed on required service only"
  - "USER-to-DB and Internet-to-DB are denied"
  - "Egress flows traverse approved inspection path"
  - "Transit/VPN return routes remain symmetric"
owner: "Cloud Network Platform + Information Security"
review_trigger: "New subnet, peering, route propagation, VPN, IPv6 or NVA change"
~~~

### 13.2. Kiểm soát pull request và deployment

Một review IaC nên hỏi:

1. **Route destination CIDR** có đúng prefix được phê duyệt không, có overlap không?
2. **Next hop** có còn tồn tại, thuộc đúng môi trường và có năng lực forward không?
3. **Association/scope** có thay đổi ở subnet nhạy cảm hoặc thừa hưởng default table không?
4. **Default route IPv4/IPv6** có chuyển egress ra ngoài security gateway không?
5. **Peering/transit/VPN propagation** có mang thêm CIDR ngoài allowlist không?
6. Thay đổi có thể tạo **asymmetric routing hoặc mất return path** không?
7. Có ảnh hưởng **DNS, SG/NSG, firewall rule, NAT và các private endpoints** không?
8. Có bằng chứng **reachability simulation, positive/negative tests, canary và rollback** không?
9. IAM principal áp thay đổi có đang có **quyền quá rộng** không?

**IaC plan success không chứng minh packet flow đúng.** Resource có thể tạo thành công nhưng route target chưa healthy, firewall chặn, DNS sai hoặc route propagation không đạt.

### 13.3. Phát hiện drift

Phải đối chiếu **desired state trong IaC** với **running/effective configuration** của cloud. Một thay đổi thủ công có thể tạo route ngoài repository; dynamic propagation cũng có thể làm tuyến hiệu lực thay đổi khi BGP session đổi.

Kênh detection nên thu **audit logs, route table snapshots/effective routes, resource relationships** và cảnh báo theo security baseline, không chỉ dựa trên git diff.

## 14. Kiểm chứng routing trên cloud mà không thay đổi production

Chỉ dùng các thao tác kiểm tra trên **tài khoản/project/subscription và tài nguyên được cấp quyền**. Bắt đầu bằng **read-only control-plane inspection**, sau đó mới chạy connectivity tests phù hợp scope.

### 14.1. Checklist kiểm tra control plane

~~~text
Source:
  Account/project/subscription:
  VPC/VNet and subnet:
  NIC/ENI + private/public IPv4/IPv6:
  Source security policy:
  Effective route scope / table association:

Destination:
  Account/project/subscription:
  VPC/VNet and subnet:
  IP, port, service identity:
  Destination security policy:

Path:
  Route prefix / next hop at source:
  Peering/transit/VPN route domain (if any):
  NVA/firewall/NAT path (if required):
  Return route / response path:
  DNS resolution and private endpoints:
  Provider reachability/flow test results:
~~~

### 14.2. AWS: route table và reachability

Các công cụ/hướng tiếp cận có thể bao gồm:

- **VPC route tables** và association cho subnet nguồn/đích.
- Route table ở **Transit Gateway** và trạng thái attachment nếu flow qua TGW.
- **VPC Reachability Analyzer** hoặc công cụ reachability liên quan khi hỗ trợ trường hợp cần kiểm tra.
- **VPC Flow Logs**, firewall logs, NAT Gateway metrics và audit từ CloudTrail cho thay đổi route/control plane.
- **Security groups, network ACLs và endpoint policies**, không chỉ route.

Ví dụ read-only, thay ID bằng tài nguyên được phép:

~~~bash
# AWS CLI: xem route tables liên quan VPC được phép.
aws ec2 describe-route-tables \
  --filters "Name=vpc-id,Values=vpc-EXAMPLE" \
  --region YOUR_REGION

# AWS CLI: xem thông tin subnet và VPC association.
aws ec2 describe-subnets \
  --subnet-ids subnet-EXAMPLE \
  --region YOUR_REGION
~~~

Khi một subnet không được explicit associate với custom route table, cần kiểm tra **main association**, không chỉ tìm route table có tên subnet.

### 14.3. Azure: UDR, subnet và NIC effective routes

Trong Azure, cần xem:

- **User-defined route tables** đã gắn với subnet nào.
- **Effective routes** trên NIC/workload, gồm system, user-defined và dynamic/BGP routes trong phạm vi có hiệu lực.
- **NSG effective rules**, Azure Firewall/NVA policy và các tính năng network troubleshooting/connection monitor.
- VPN/ExpressRoute route propagation, peering configuration và các ràng buộc trên từng subnet.

Ví dụ dạng read-only:

~~~bash
# Azure CLI: kiểm tra subnet và route-table association.
az network vnet subnet show \
  --resource-group YOUR_RESOURCE_GROUP \
  --vnet-name YOUR_VNET \
  --name YOUR_SUBNET

# Azure CLI: xem effective route table của NIC được phép.
az network nic show-effective-route-table \
  --resource-group YOUR_RESOURCE_GROUP \
  --name YOUR_NIC
~~~

Tùy quyền IAM, trạng thái VM/NIC và phiên bản CLI, effective route diagnostics có thể không sẵn sàng; cần sử dụng tính năng tương đương của portal/provider khi đó.

### 14.4. Google Cloud: VPC routes và firewall

Với GCP, kiểm tra **VPC network, subnet routes, static/dynamic routes, Cloud Router/BGP, route priority, VPC peering và firewall policies**. Các routes không phải lúc nào được gán theo subnet table giống AWS; vì vậy, điều tra cần xem **network scope và route applicability**.

~~~bash
# Google Cloud CLI: liệt kê route resources trong project đã chọn.
gcloud compute routes list --project=YOUR_PROJECT

# Xem subnet resources trong project và vùng tương ứng.
gcloud compute networks subnets list --project=YOUR_PROJECT
~~~

Khi kiểm tra traffic qua peering, VPN, hybrid hoặc next-hop service, phải đối chiếu cơ chế phân phối/ưu tiên route và effective reachability của nền tảng đang dùng. Gcloud CLI output của một bảng route **không tự cung cấp toàn bộ quyết định firewall hoặc kết quả packet forwarding**.

### 14.5. Không dùng traceroute làm bằng chứng duy nhất

Các cloud fabric có thể không phản hồi ICMP TTL-expired ở mọi hop, và traffic còn chịu **ECMP, overlay, NAT và firewall**. Traceroute thất bại ở một hop không tự chứng minh đường đi ứng dụng bị lỗi.

Ưu tiên kết hợp **effective route + reachability tool + flow logs + firewall session/NAT logs + thử kết nối ứng dụng được cấp quyền**.

## 15. Data-plane verification và đọc evidence

Một route trên console cho biết **cấu hình/đường dự kiến**, không nhất thiết chứng minh traffic được chuyển tới ứng dụng.

| Evidence | Trả lời câu hỏi | Giới hạn |
| --- | --- | --- |
| **Effective routes** | Đích sẽ chọn next hop nào theo ngữ cảnh cloud? | Không nói firewall cho phép hay app phản hồi |
| **SG/NSG/ACL effective policy** | Policy có cho phép 5-tuple không? | Không chứng minh route đã hoạt động |
| **VPC/VNet flow logs** | Flow có được quan sát, accept/reject và metadata nào? | Tùy provider có sampling, aggregation và vị trí quan sát |
| **NVA/firewall session logs** | Có traffic thực đi qua điểm inspection không? | Không thấy log có thể do route bypass hoặc telemetry coverage |
| **NAT translations** | Source/destination trước/sau NAT và đường trả về? | Cần đối chiếu time window và connection mapping |
| **VPN/BGP logs** | Tunnel/session UP, route prefixes learned/advertised? | Tunnel UP không đồng nghĩa app reachable |
| **DNS logs** | Tên dịch vụ giải ra IP private/public nào? | Cache/DoH/split DNS có thể thay đổi nguồn quan sát |
| **App/DB audit** | Request thực sự được xử lý và quyền nào được dùng? | Phải correlate user/workload identity với flow network |
| **Cloud control-plane audit** | Ai thêm/xóa route hoặc đổi association? | Không đo trực tiếp kết quả data plane |

### 15.1. Ví dụ sự kiện giả định

~~~json
{
  "caseId": "CLOUD-ROUTE-006",
  "timestamp": "2026-11-28T04:10:12Z",
  "sourceSubnet": "10.40.20.0/24",
  "destinationIp": "10.40.30.25",
  "destinationPort": 5432,
  "effectiveRoute": "10.40.0.0/16",
  "nextHop": "local",
  "securityDecision": "deny",
  "policyId": "DB-ALLOW-APP-ONLY",
  "observation": "Synthetic test from non-approved source",
  "result": "No database session established"
}
~~~

Đây là **schema mẫu do nhóm tự tổng hợp**, không phải log nguyên bản của provider. Hãy phân biệt **policy evaluation**, **flow accepted/rejected** và **kết quả ứng dụng**. Một deny trên firewall không đồng nghĩa mọi đường khác đã được chặn nếu còn route/endpoint bypass.

### 15.2. Đọc theo cả hai chiều

Với kết nối TCP APP → DB, nên thu:

~~~text
Forward:
  APP 10.40.20.15:51000 -> DB 10.40.30.25:5432
  Effective route / security decision / NVA logs

Return:
  DB 10.40.30.25:5432 -> APP 10.40.20.15:51000
  Effective return route / stateful policy / NAT translation
~~~

Nếu có SNAT, source/destination trong log tại từng hop sẽ khác. Phải sử dụng **mapping NAT, session ID và time window**, tránh kết luận hai flow khác nhau chỉ vì IP biến đổi.

### 15.3. Vì sao không thấy log ở firewall?

Có thể:

1. Traffic **không đi qua firewall** vì route local hoặc đường peering khác.
2. Firewall **log level** chưa bật cho rule đó.
3. Flow chưa tới firewall vì **DNS/route/NVA lỗi trước đó**.
4. Log đang ở **region/account/device** khác hoặc bị sampling/retention.
5. Kết nối đã được xử lý bởi một **endpoint/service managed** có telemetry riêng.

Cần xác minh **vị trí sensor và coverage** trước khi coi thiếu log là bằng chứng không có traffic.

## 16. Case study: APP không kết nối DB sau khi thêm NVA

### 16.1. Bối cảnh giả định

Ứng dụng tại **10.40.20.15** trước đây kết nối DB **10.40.30.25:5432** qua route nội bộ. Đội bảo mật đưa một NVA vào kiến trúc để kiểm tra east–west traffic. Sau change, application connection timeout dù DB còn hoạt động.

### 16.2. Evidence theo thời gian

| Evidence | Quan sát | Diễn giải |
| --- | --- | --- |
| **E1 – Change record** | APP route tới DB prefix được chuyển qua NVA | Có thay đổi chặng đi của APP |
| **E2 – Effective route APP** | 10.40.30.0/24 chọn NVA theo provider policy | Forward path bắt đầu qua appliance |
| **E3 – NVA forward log** | Nhận SYN từ APP và chuyển tới DB | Chứng minh NVA thấy một chiều |
| **E4 – DB security policy** | Cho phép TCP 5432 từ nguồn sau NAT hoặc APP tùy thiết kế | DB policy không nhất thiết là nguyên nhân |
| **E5 – Effective route DB** | Response tới APP subnet chọn local route, không đi NVA | Có nguy cơ asymmetric routing |
| **E6 – NVA stateful log** | Session không thấy return traffic hoặc đánh dấu incomplete | NVA không đủ state của flow |
| **E7 – Pilot after adjustment** | Hai chiều được kiểm soát, API/DB query thành công | Cần tiếp tục kiểm tra negative tests |

Đây là **case học tập giả định**. Việc thêm route cụ thể qua NVA phải được provider hỗ trợ theo kiến trúc; không phải mọi cloud cho thực hiện cùng một thao tác.

### 16.3. Quy trình xử lý

1. **Ghi snapshot** route trước/sau và các điều kiện áp policy cho subnet APP/DB.
2. Xác minh NVA đã bật **IP forwarding**, có route tới DB và return network.
3. Xem NVA có **nhận và chuyển SYN** hay không, DB có phản hồi không.
4. Kiểm tra **DB effective route** tới nguồn thực tế (APP hoặc SNAT IP) và cách stateful firewall theo dõi phiên.
5. Thiết kế **return path qua điểm kiểm soát dự kiến** hoặc sử dụng kỹ thuật symmetry/SNAT được phê duyệt.
6. Kiểm tra cả **SG/NSG/ACL, DB authentication và host firewall**, không chỉ route.
7. Kiểm thử **APP → DB positive**, **USER → DB negative**, các zone/availability variants và failover.
8. Có rollback an toàn khi inspection path làm gián đoạn production.

### 16.4. Bài học

**Chỉnh đường đi một chiều chưa đủ cho stateful inspection**. Một thay đổi route cần xét **flow forward, return, HA và security policy**. Khi đã xử lý timeout, phải chứng minh NVA thực sự được đi qua trên **mọi đường cần kiểm soát**, không chỉ sự thành công của ứng dụng.

## 17. Case study: private subnet đi Internet trực tiếp ngoài ý định

### 17.1. Bối cảnh giả định

Một đội phát hành hạ tầng tạo subnet **APP 10.40.20.0/24** với yêu cầu **tất cả Internet egress phải qua security inspection và NAT đã được phê duyệt**. Sau một lần tái cấu trúc IaC, subnet dùng bảng route mặc định có 0.0.0.0/0 tới một egress khác. Ứng dụng vẫn gọi external API thành công nên lỗi không được phát hiện ngay.

### 17.2. Bằng chứng

~~~text
Expected:
  APP subnet -> 0.0.0.0/0 -> Egress firewall/NAT A

Observed:
  APP subnet -> 0.0.0.0/0 -> Alternative egress gateway B

Symptoms:
  - External API still returns HTTP 200
  - Egress firewall A sees fewer APP sessions
  - Source public IP seen by partner differs from approved IP
  - Route association changed in infrastructure audit
~~~

HTTP 200 chỉ chứng minh service phản hồi, **không chứng minh request đã đi qua security inspection**.

### 17.3. Ứng phó

1. Xác định **route association mới, actor và thời điểm thay đổi** qua cloud audit/IaC diff.
2. Đánh giá IP nguồn/đích, egress gateway và **flow logs** để nhận diện phạm vi traffic có khả năng bypass.
3. Khôi phục **approved next hop** theo change/incident process, không xóa route khi chưa có đường egress hợp lệ.
4. Kiểm tra **IPv6**, peering, alternate NIC và các subnet khác có cùng association.
5. Rà soát **dữ liệu/endpoint đã truy cập**, bảo mật và rủi ro còn lại theo bằng chứng có được.
6. Bổ sung **policy guardrails** ngăn APP subnet gắn route table ngoài danh sách và cảnh báo drift.
7. Chạy **positive/negative tests** xác minh source IP, firewall log và các luồng nghiệp vụ hợp lệ.

### 17.4. Bài học

Một hệ thống **vẫn hoạt động** không có nghĩa nó hoạt động **đúng kiến trúc bảo mật**. Route drift cần được giám sát qua control-plane audit và **data-plane evidence**, không chỉ theo dõi availability.

## 18. Checklist kiểm thử route và segmentation có kiểm soát

Các kiểm thử bên dưới chỉ áp dụng trên **account/subscription/project, mạng và endpoints đã được cấp quyền**. Khi test liên quan thay route, failover hay chặn traffic, ưu tiên staging/canary, có out-of-band access và rollback.

| Test | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| **P1 – APP → DB hợp lệ** | APP identity được phê duyệt kết nối TCP 5432 | Route/SG/DB auth cho phép và ứng dụng hoạt động |
| **N1 – USER → DB** | User subnet không thuộc danh sách cho phép thử kết nối DB | Bị deny ở điểm policy được thiết kế, có log |
| **N2 – Internet → DB** | Xem external exposure và test có quyền với DB | Không có đường public inbound ngoài thiết kế |
| **P2 – APP → Internet** | APP gọi external API được duyệt | Egress đi qua firewall/NAT, IP nguồn/log đúng |
| **N3 – Egress bypass** | Kiểm tra alternate route, IPv6, public NIC và peering | Không có đường đi vòng điểm inspection |
| **P3 – APP → on-prem** | Kết nối private theo prefix đã cấp | Qua VPN/transit, cả chiều về và firewall đúng |
| **N4 – Unapproved route import** | Mô phỏng BGP/propagation của prefix ngoài policy trong lab | Route không được đưa vào effective routing |
| **N5 – Subnet association drift** | IaC test gắn sai default table vào data subnet | Policy-as-code từ chối hoặc cảnh báo trước deploy |
| **F1 – NVA failover** | Trong staging làm NVA primary unavailable | Backup path đúng policy; không bypass theo trạng thái không được duyệt |
| **F2 – Transit path failure** | Chuyển hướng một kết nối hybrid trong lab | Không asymmetric/blackhole ngoài SLO |
| **N6 – CIDR overlap** | Thử cấu hình overlap trong plan test | IPAM/policy guardrail phát hiện và chặn |
| **P4 – IPv6** | Dual-stack workload dùng IPv6 service hợp lệ | ::/0 và IPv6 firewall/inspection đúng chính sách |
| **N7 – IPv6 bypass** | IPv6 đích không được duyệt | Không thoát ra đường IPv6 ngoài kiểm soát |
| **O1 – Route change alert** | Tạo route diff được phê duyệt ở staging | Audit ghi actor, prefix, next-hop cũ/mới, subnet |
| **O2 – Flow correlation** | Dùng một kết nối kiểm thử có request ID | Ghép được route, firewall/NVA flow và app result |

### 18.1. Một negative test cần bằng chứng gì?

Nếu thử kết nối DB thất bại, có thể do **DNS sai, route unreachable, firewall deny hoặc DB service down**. Kết quả “không kết nối được” **không tự chứng minh security policy đang chặn đúng cách**.

Negative test phải có:

- Source/destination/port rõ ràng và **đúng subnet/identity đang kiểm chứng**.
- Kết quả **effective route** và nguồn/đích thực tế.
- **Deny event/policy ID** hoặc evidence enforcement tương đương tại điểm mong muốn.
- Một **positive control** chứng minh app/service hoạt động và route hợp lệ không hỏng.
- Mốc thời gian/region và điều kiện test, tránh gán lỗi do outage thành “bảo mật đạt”.

### 18.2. Không kiểm thử bằng cách gây mất mạng diện rộng

Không tự xóa default route, làm NVA fail hoặc quảng bá route BGP trên production chỉ để chứng minh cơ chế phòng vệ. Có thể dùng **provider reachability analyzer, policy simulation, staging, change preview và historical incident logs** trước khi tiến hành failover test theo quy trình.

## 19. Troubleshooting: có route nhưng kết nối vẫn thất bại

| Triệu chứng | Nguyên nhân cần cân nhắc | Bước đầu xác minh |
| --- | --- | --- |
| APP không tới DB trong cùng VPC/VNet | SG/NSG, subnet ACL, local route override, host firewall, DB listening | Effective route + packet/flow logs + policy |
| APP được DB trả lời nhưng kết nối timeout | Return path/NVA symmetry, NAT, stateful session | Hai chiều forward/return và firewall logs |
| On-prem tới cloud một chiều | Cloud route, VPN/BGP prefix import, on-prem route/ACL | Effective route cả hai đầu + session evidence |
| DB private subnet gọi dịch vụ ngoài thất bại | Không có egress route, NAT, DNS/private endpoint | DNS, default/specific route, firewall/endpoint |
| Internet egress IP bất thường | Route association thay đổi hoặc gateway/NAT khác | Route audit, NAT/egress logs, source public IP |
| Một subnet có đường đi khác các subnet khác | Different association/UDR/policy hoặc region/zone | Compare effective routes per subnet/NIC |
| VPN tunnel UP nhưng không tới resource | BGP/propagation/route target chưa đạt hoặc firewall | Prefix tables và return path, SG/NSG |
| Route blackhole | Next-hop attachment/NVA/endpoint bị xóa hoặc inactive | Route state, resource health và deployment history |
| Chỉ IPv6 tạo kết nối ngoài mong đợi | ::/0 khác, public IPv6, DNS AAAA | IPv6 route/policy/flow logs |
| Firewall tập trung không thấy flow | Local bypass, sampling, log policy hoặc upstream failure | Route/inspection path + telemetry coverage |
| Peering A↔B chạy, A↔C qua B thất bại | Thiếu transitive routing theo kiến trúc/provider | Peering limits, transit design, routes từng domain |
| Application sử dụng IP public dù có private path | DNS split/view/private endpoint mapping sai | DNS answer, resolved IP, effective route |
| Sau failover nhiều 502/504 | NVA capacity, NAT, session state, routing asymmetry | Proxy timing, NVA log, source IP, path tests |

### 19.1. Quy trình điều tra bảy bước

1. **Định danh flow:** source workload, source subnet, destination IP/port, protocol và timestamp.
2. **Xác định IP sau DNS:** tên dịch vụ phân giải thành private/public IPv4/IPv6 nào, có split DNS không?
3. **Xem effective route phía nguồn:** prefix được chọn, target, route table association, propagated/policy routes.
4. **Xem các chặng trung gian:** peering/transit/VPN/NVA, route domains và firewall/NAT.
5. **Xem return path:** effective route và chính sách phía đích về source, đặc biệt nếu đi qua stateful appliance.
6. **Đối chiếu enforcement:** SG/NSG/ACL, host firewall, application auth, cloud flow/session logs.
7. **Kiểm chứng có kiểm soát:** positive/negative tests, ghi rõ nguyên nhân, phạm vi, thay đổi, rollback và telemetry sau sửa.

Không sửa bừa toàn bộ SG/firewall thành **Any–Any** chỉ để chứng minh “do route hay do firewall”; điều này tạo rủi ro thực và thường không giúp phân biệt lỗi chính xác.

## 20. Monitoring, change management và incident response

### 20.1. Những sự kiện nên cảnh báo

| Tín hiệu | Lý do bảo mật | Ngữ cảnh cần kèm |
| --- | --- | --- |
| **0.0.0.0/0 hoặc ::/0 đổi next hop** | Có thể thay đổi toàn bộ egress | Subnet/route domain, actor, approved target |
| **Route table association thay đổi** | Có thể mở hoặc cắt reachability của cả subnet | Old/new table, affected subnet, change ticket |
| **Route mới tới DATA/MGMT CIDR** | Nguy cơ route leak hoặc mở đường kết nối không chủ đích | Source network/attachment, prefix, policy |
| **Transit attachment/propagation đổi** | Reachability giữa VPC/VNet/tenant thay đổi | Hub table, associated/propagated attachments |
| **NVA/managed firewall unhealthy** | Có thể blackhole hoặc chuyển đường bypass | HA group, fallback mode, impacted flows |
| **Firewall sessions đột ngột giảm** | Có thể flow đi qua đường khác | Egress/inspection path và logging coverage |
| **Public IP/NAT source thay đổi** | Có thể đổi egress policy hoặc subnet route | Affected workload/partner allowlist |
| **BGP learned prefix bất thường** | Có thể import default/overbroad prefix | Neighbor, route source, accepted/denied |
| **Cloud IAM thay đổi quyền sửa route** | Ai đó có thêm khả năng thay network boundary | Role/principal, approval, audit |
| **IPv6 route/SG thay đổi ngoài kế hoạch** | Đường IPv6 có thể bypass IPv4 inspection | IPv6 subnet, ::/0, endpoint và AAAA |

### 20.2. Hồ sơ sự cố định tuyến

~~~text
Case ID / severity:
UTC time window:
Affected cloud account/project/subscription:
Virtual network and subnet(s):
Source identity/IP:
Destination identity/IP/port:
Expected route and security enforcement:
Observed effective route and next hop:
All intermediate transit/peering/VPN/NVA domains:
Return path and NAT identity:
Firewall/SG/NSG policy IDs:
Cloud audit actor/action/config revision:
Flow logs, gateway logs, app result:
Changes applied / rollback:
Positive & negative tests:
Residual risk, owner, follow-up:
~~~

Log có thể chứa IP, thông tin workload, username, domain và kiến trúc mạng nhạy cảm. Bảo quản bằng chứng theo nguyên tắc **quyền tối thiểu, retention, timestamp có timezone, provenance và che thông tin không cần thiết**. Không đưa credential/token hoặc private key vào ticket chỉ vì đang điều tra routing.

## 21. Những nhầm lẫn thường gặp

1. **“Hai subnet khác nhau luôn được cách ly.”** Chúng có thể được nối bởi local/system route; phải xét firewall/identity.
2. **“Route table là firewall.”** Route chỉ quyết định đường đi, không tự cấp hoặc từ chối quyền.
3. **“Private subnet không thể liên lạc với Internet.”** Có thể có outbound qua NAT, firewall, proxy hoặc service endpoints.
4. **“0.0.0.0/0 tự tạo public IP.”** Default route không cấp địa chỉ công khai.
5. **“Có route tới DB nghĩa được dùng DB.”** Còn SG/NSG/ACL, host firewall và DB authentication.
6. **“Firewall allow nghĩa packet chắc tới đích.”** Có thể thiếu route, next hop lỗi hoặc đường trả về sai.
7. **“Chỉ kiểm tra route APP là đủ.”** Return route, transit domain, NAT và stateful firewall có thể làm kết nối thất bại.
8. **“Mỗi subnet trên mọi cloud có một route table kiểu AWS.”** AWS, Azure và GCP có mô hình scope khác nhau.
9. **“Peering mặc định là transit cho các mạng thứ ba.”** Cần kiểm tra hạn chế transitivity và dùng hub nếu cần.
10. **“Tunnel VPN UP nghĩa prefix đã tới được.”** Phải xác minh route propagation, security policy và data plane.
11. **“NVA có IP là tự forward packet.”** IP forwarding, route, firewall, symmetry và HA phải đúng.
12. **“Route local luôn đi qua firewall tập trung.”** Không nhất thiết; có thể đi trực tiếp qua cloud fabric.
13. **“Làm route APP → NVA là đủ cho stateful inspection.”** Return path có thể đi thẳng DB → APP.
14. **“NAT là security boundary đầy đủ.”** NAT không thay thế firewall và application authentication.
15. **“SG/NSG cho cả 10.40.0.0/16 vẫn là least privilege vì toàn private.”** VPC/VNet có thể gồm nhiều role/tenant.
16. **“Một VPC Flow Log không thấy traffic chứng minh traffic không tồn tại.”** Cần xét vị trí sensor, sampling và logging coverage.
17. **“IPv4 egress an toàn tức IPv6 cũng an toàn.”** ::/0, IPv6 public endpoints và firewall cần kiểm tra riêng.
18. **“DNS resolve thành công chứng minh route hoạt động.”** DNS query có thể thành công dù packet tới resolved IP không đi được.
19. **“Không có Internet default route nghĩa subnet hoàn toàn cô lập.”** Vẫn có local/specific routes tới mạng khác.
20. **“Đổi route không cần security review vì không sửa SG.”** Thay next hop/association có thể bypass mọi inspection controls.
21. **“IaC apply thành công nghĩa traffic đúng.”** Còn effective route, next-hop health, NAT, firewall và return path.
22. **“Đổi route gây timeout nên cứ mở firewall Any–Any.”** Cần chứng cứ đúng lớp để sửa phạm vi hẹp và có rollback.

## 22. Bài tập vận dụng và gợi ý

### Bài 1 — Hai subnet có được phép nói chuyện?

VPC 10.40.0.0/16 có APP **10.40.20.0/24** và DB **10.40.30.0/24**. Route local cho phép chuyển tiếp trong VPC; DB SG chỉ nhận TCP 5432 từ APP role.

**Câu hỏi:** liệu một VM ở USER subnet cùng VPC có thể vào DB chỉ vì có local route không?

**Gợi ý:** không tự động. Local route tạo reachability, còn DB SG và các policy khác giới hạn người gọi; cần negative test với evidence chặn tại enforcement point.

### Bài 2 — Prefix nào thắng?

Một effective route table có **10.40.0.0/16 → local**, **10.40.30.0/24 → inspection NVA** và **0.0.0.0/0 → NAT**. Traffic đích 10.40.30.25 chọn route nào?

**Gợi ý:** nếu route /24 được provider hỗ trợ và đang hợp lệ, **/24** cụ thể hơn được chọn. Tuy nhiên, cần kiểm tra khả năng steering route nội bộ của provider và route quay về, không chỉ lý thuyết prefix.

### Bài 3 — APP ra Internet vẫn thành công nhưng firewall không ghi log

Ứng dụng gọi external API được HTTP 200, trong khi egress firewall dự kiến không thấy flow. Đội vận hành muốn kết luận hệ thống khỏe.

**Gợi ý:** chưa đủ. Kiểm tra effective default route, subnet association, NAT/public source IP, IPv6, alternative egress, firewall log coverage và cloud audit. Thành công ứng dụng không chứng minh đi đúng security path.

### Bài 4 — Thêm NVA tạo asymmetric path

APP gửi qua NVA để tới DB nhưng DB reply đi trực tiếp về APP. Vì sao kết nối có thể lỗi?

**Gợi ý:** stateful NVA có thể không thấy response và không duy trì trạng thái kết nối đúng; cần thiết kế return path/symmetry hoặc NAT hợp lệ, kiểm chứng cả forward và reverse flow.

### Bài 5 — Route leak từ kết nối hybrid

On-premises quảng bá **0.0.0.0/0** qua BGP thay vì chỉ **172.20.0.0/16**. Điều gì cần kiểm tra?

**Gợi ý:** route import filter/priority và effective routes, đường Internet egress, NAT/firewall, dependency on-premises, rollback và logging. Không nhận default route nếu không phải thiết kế forced tunneling có phê duyệt.

### Bài 6 — Dual-stack

APP có IPv4 default qua egress firewall nhưng IPv6 **::/0** đi qua gateway khác. Một external API có DNS AAAA. Câu hỏi: hệ thống có thể bypass đường IPv4 không?

**Gợi ý:** có thể, tùy resolver và lựa chọn IP của client; cần xem IPv6 route, public IPv6, firewall/NVA policy, DNS AAAA và flow logs IPv6.

### Bài 7 — Bản đồ threat → control → evidence

Thiết kế mạng cloud có **EDGE, APP, DB, MGMT**, kết nối **on-premises qua VPN/transit** và egress Internet tập trung. Hãy xây dựng bảng:

- Effective routes tại mỗi subnet/network và **đường hồi đáp**.
- Những **luồng được phép** theo user/service identity và những luồng phải bị chặn.
- Quyền IAM nào cho phép tạo route, đổi association hoặc import BGP prefix.
- Điểm inspection nào phải quan sát **east–west và north–south**.
- Cách xử lý khi **NVA fail**, không được tự động bypass policy ngoài thiết kế.
- Positive/negative/failover tests và log nào chứng minh đường đi đúng.

**Gợi ý:** bắt đầu từ flow matrix và trust boundary, kiểm tra provider-specific route scope, rồi dựng evidence theo từng chặng bằng route inspection, firewall logs và test ứng dụng.

## 23. Checklist ngắn trước khi chấp thuận thiết kế

| Câu hỏi | Bằng chứng mong đợi |
| --- | --- |
| Có IPAM/CIDR không overlap giữa VPC/VNet, on-prem và đối tác chưa? | CIDR inventory và review peering/VPN |
| Mỗi subnet/workload dùng effective route nào? | Association/scope và output từ provider |
| Local/system routes và override limitations đã được hiểu đúng? | Provider-specific topology/validation |
| Default IPv4 và IPv6 egress có đúng security policy? | 0.0.0.0/0, ::/0, NAT/NVA/IGW và firewall |
| APP → DB có được bảo vệ bằng identity/SG/NSG và DB auth? | Positive/negative connection tests |
| EAST–WEST traffic có thật qua NVA khi bắt buộc? | Route selection, NVA session logs, flow evidence |
| Return path đi đúng nơi và không gây asymmetric drop? | Reverse effective routes, NAT/session correlation |
| Transit/peering/VPN có kiểm soát import/export prefix? | Attachment/route table/BGP policy audit |
| Có direct-origin/public endpoint/secondary NIC bypass không? | Network asset inventory và negative tests |
| DNS private/public resolution có đúng route không? | DNS answer, private endpoint và route lookup |
| SG/NSG/NACL/firewall có least privilege và không Any–Any? | Effective policy review và deny logs |
| NVA và next-hop targets có HA/failover được kiểm chứng? | Health/failure simulations và rollback |
| Có policy-as-code chặn route drift và default route sai? | IaC review/checks, alert và control-plane audit |
| Cloud flow, firewall, NAT và app logs có correlate được? | Timestamp, workload/flow IDs, source/dest mapping |
| Change có owner, maintenance window và rollback không? | Ticket, architecture diff, test report |

## 24. Tổng kết

**Route table và định tuyến giữa các subnet** giúp cloud quyết định đường đi của packet qua **local/system routes, user-defined routes, dynamic propagation, next hops và routing domains**. Trong cùng một VPC/VNet, các subnet có thể trao đổi traffic theo route nội bộ; **định tuyến thông suốt không đồng nghĩa truy cập được phép**. Bảo mật thực tế phụ thuộc **security group/NSG, firewall/NVA, subnet ACL, xác thực ứng dụng, IAM và khả năng quan sát**.

Khi mở rộng sang **peering, transit hub, VPN/on-premises hoặc IPv6**, cần xem đủ **route phía nguồn, tất cả chặng trung gian, đường hồi đáp và chính sách tại mỗi trust boundary**. Thiết kế sai có thể gây **route leak, bypass inspection, asymmetric routing, blackhole hoặc thay đổi egress ngoài ý định**. Mô hình route của AWS, Azure và GCP có khác nhau; không được áp một mẫu route-table association duy nhất cho mọi nền tảng.

Một kiến trúc **SECURITY_NETWORK_SECURITY** an toàn phải chứng minh bằng **effective routing, flow/firewall/NAT logs, control-plane audit và positive/negative tests** rằng **luồng nghiệp vụ hợp lệ đi qua đường được phê duyệt**, **các vùng không được phép vẫn bị chặn đúng điểm enforcement**, và **thay đổi route/next hop được quản trị, giám sát, có khả năng phục hồi và không mở đường vòng kiểm soát**.
