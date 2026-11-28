# Default route trong routing security: đường đi mặc định, failover và kiểm soát rủi ro

Trong chương **Routing security** thuộc module **SECURITY_NETWORK_SECURITY**, **default route** (tuyến mặc định) là tuyến mà host hoặc router sử dụng khi không tìm được tuyến đích cụ thể hơn trong bảng định tuyến đang được áp dụng. Nó giúp mạng nội bộ đi ra Internet, kết nối các site, đi qua VPN hoặc chuyển tiếp qua thiết bị bảo mật. Tuy nhiên, một tuyến mặc định sai có thể khiến traffic đi nhầm gateway, bỏ qua firewall, rơi vào blackhole hoặc rò rỉ sang vùng mạng không mong muốn.

Vì default route có phạm vi bao phủ rộng, thay đổi nhỏ ở next hop hoặc mức ưu tiên có thể ảnh hưởng đến rất nhiều đích. Bảo vệ tuyến mặc định không chỉ là thêm một dòng cấu hình; phải xem **định tuyến, điểm thực thi chính sách, NAT, xác thực thiết bị, ranh giới tin cậy, ghi log và khả năng phục hồi** như một hệ thống.

Sau bài học, bạn có thể:

- Giải thích ký hiệu **0.0.0.0/0**, **::/0**, default gateway, next hop và quy tắc *longest-prefix match*.
- Phân biệt lựa chọn tuyến theo độ dài prefix với việc chọn giữa nhiều tuyến cùng prefix theo ưu tiên/metric; biết vai trò của policy routing, VRF và ECMP.
- Thiết kế default route cho host, LAN, mạng có hai ISP, VPN và subnet cloud mà không vô tình tạo đường đi vòng kiểm soát.
- Nhận biết kịch bản **rogue gateway, route injection, route leak, blackhole, egress hijack** và các control phòng ngừa, phát hiện, ứng phó phù hợp.
- Xác minh đường đi bằng route table, policy, packet/flow logs, next-hop adjacency, NAT và kiểm thử có quyền trước/sau thay đổi.

## 1. Default route là gì?

### 1.1. Ký hiệu IPv4 và IPv6

| Hệ địa chỉ | Prefix mặc định | Ý nghĩa |
| --- | --- | --- |
| **IPv4** | **0.0.0.0/0** | Khớp với mọi địa chỉ IPv4, nhưng chỉ được chọn nếu không có prefix phù hợp cụ thể hơn trong bảng định tuyến được xét |
| **IPv6** | **::/0** | Khớp với mọi địa chỉ IPv6 theo cùng nguyên tắc tìm tuyến, trong bảng định tuyến IPv6 tương ứng |

**/0** nghĩa là **không có bit prefix cố định**. Nó không đồng nghĩa thiết bị gửi traffic tới địa chỉ **0.0.0.0** hoặc **::** như một máy chủ đích; hai ký hiệu này ở đây biểu diễn **network prefix**, không phải địa chỉ của gateway.

Ví dụ bảng định tuyến IPv4 trên một router:

~~~text
Prefix            Next hop / Interface        Mục đích
10.60.10.0/24     directly connected / LAN    Mạng hiện diện trực tiếp
10.60.20.0/24     10.60.10.2 / LAN             Đi tới vùng ứng dụng
10.0.0.0/8        10.60.10.3 / LAN             Các mạng nội bộ còn lại
0.0.0.0/0         198.51.100.1 / WAN1          Những đích IPv4 còn lại
~~~

Với đích **10.60.20.25**, tuyến **10.60.20.0/24** được chọn thay vì **10.0.0.0/8** và **0.0.0.0/0**. Với đích **203.0.113.80**, nếu không có tuyến nào khác cụ thể hơn, thiết bị dùng default route qua **198.51.100.1**.

Các IP **198.51.100.0/24**, **203.0.113.0/24** và **192.0.2.0/24** là dải dành cho tài liệu; không được hiểu là gateway hoặc đích Internet thực tế trong môi trường bạn đang sử dụng.

### 1.2. Quy tắc longest-prefix match

Ở bước tìm đường thông thường, thiết bị chọn tuyến có **prefix dài nhất** trong số các tuyến phù hợp với địa chỉ đích, thuộc đúng routing table/VRF và chính sách đang áp dụng.

~~~text
Destination: 10.60.20.25

10.60.20.0/24   MATCH  -> cụ thể nhất
10.0.0.0/8      MATCH
0.0.0.0/0       MATCH

Kết quả: chọn 10.60.20.0/24
~~~

Điều này giải thích vì sao **thêm default route không nhất thiết làm thay đổi đường đi của các mạng nội bộ** nếu các route cụ thể hơn vẫn đúng và có hiệu lực.

Cũng cần hiểu chiều ngược lại: một tuyến sai **cụ thể hơn** có thể lấn át default route hợp lệ. Vì thế, điều tra route hijacking không được giới hạn vào mỗi dòng **0.0.0.0/0**.

### 1.3. Khi không có default route

Nếu bảng định tuyến không có tuyến phù hợp với đích và cũng không có default route, host/router **không có đường chuyển tiếp phù hợp** trong bảng đó. Hệ điều hành có thể báo lỗi như *Network unreachable* hoặc trả thông báo ICMP tùy tình huống.

Việc thiếu default route **không nhất thiết là lỗi bảo mật**: một vùng cơ sở dữ liệu có chủ đích không được phép ra Internet có thể được thiết kế không có tuyến đi ra ngoài, kết hợp firewall và các tuyến cụ thể tới dịch vụ cần thiết. Ngược lại, một máy người dùng cần kết nối Internet thường phải có đường định tuyến tới đích ngoài subnet, thông qua default route hoặc các route đủ cụ thể.

## 2. Default gateway, next hop và forwarding khác nhau thế nào?

**Default gateway** thường là thiết bị hoặc địa chỉ next hop mà **host** dùng để đi tới mạng ngoài subnet của mình. **Default route** là **bản ghi định tuyến** (ví dụ 0.0.0.0/0 via 10.60.10.1). **Next hop** là nút/chặng kế tiếp của tuyến; next hop có thể là router vật lý, địa chỉ ảo HA hoặc một đối tượng forwarding do nền tảng quản lý.

~~~mermaid
flowchart LR
    C["Client 10.60.10.25/24"] -->|LAN / next hop 10.60.10.1| R["Firewall / router"]
    R -->|Default route WAN1| I["ISP / WAN"]
    R -->|Route cụ thể nội bộ| A["Application subnet 10.60.20.0/24"]
    I --> E["Đích ngoài mạng nội bộ"]
~~~

Trên client có thể thấy:

~~~text
10.60.10.0/24 dev eth0 src 10.60.10.25
default via 10.60.10.1 dev eth0
~~~

Khi client gửi đến **10.60.10.53** trong cùng subnet, nó có thể gửi trực tiếp tới host qua L2 theo cơ chế ARP. Khi gửi đến **203.0.113.80**, nó sẽ tìm MAC của **10.60.10.1**, đóng gói Ethernet cho gateway nhưng **giữ đích IP cuối cùng là 203.0.113.80**, trừ các thay đổi như NAT ở chặng sau.

### 2.1. Mỗi router đều tự quyết định chặng kế tiếp

Một default route trên client chỉ quyết định **chặng đầu tiên**. Router 10.60.10.1 có bảng định tuyến và các chính sách riêng. ISP hoặc router ở xa lại tiếp tục chọn next hop khác. Vì vậy, “client đã có default gateway đúng” **không chứng minh** gói đi được tới Internet hay ngược lại.

### 2.2. Đường đi IPv6 và link-local next hop

Với IPv6, default route là **::/0**. Host IPv6 thường học default router qua **ICMPv6 Router Advertisement (RA)**, có thể sử dụng **địa chỉ link-local fe80::/10** của router làm next hop.

~~~text
default via fe80::1 dev eth0
~~~

Khi next hop là địa chỉ link-local, **interface/zone** là phần quan trọng để xác định đúng láng giềng. **DHCPv6 không cung cấp default-router option tương đương Option 3 của DHCPv4** trong mô hình IPv6 thông thường; một mạng dual-stack cần xem chính sách RA/ND riêng.

## 3. Tuyến mặc định đến từ đâu?

Một host hoặc router có thể học default route từ nhiều nguồn. Nguồn không chỉ ảnh hưởng tính tiện lợi mà còn quyết định **ai có khả năng thay đổi đường đi**.

| Nguồn | Ví dụ | Rủi ro và điểm kiểm soát |
| --- | --- | --- |
| **Static route** | Quản trị viên đặt 0.0.0.0/0 qua next hop WAN | Sai địa chỉ/metric hoặc thay đổi không được duyệt có thể chuyển toàn bộ egress |
| **DHCPv4** | Client nhận default router qua **Option 3** | Rogue DHCP server có thể cung cấp gateway không được phép |
| **IPv6 RA** | Router trên LAN quảng bá default-router lifetime | Rogue RA có thể khiến client chọn router lạ |
| **Routing protocol nội bộ** | OSPF có cấu hình originate default route vào vùng định tuyến | Một router sai cấu hình có thể phát tuyến mặc định đến nhiều thiết bị |
| **BGP / upstream** | Edge router nhận 0.0.0.0/0 hoặc ::/0 từ nhà cung cấp | Session/route policy không được giới hạn có thể nhận default không mong muốn |
| **VPN / SD-WAN** | VPN client thêm default route để dùng full tunnel, hoặc chính sách SD-WAN chọn chặng | Tuyến có thể chuyển egress và DNS sang môi trường khác hoặc vô tình tạo đường bypass |
| **Cloud route table** | Subnet có 0.0.0.0/0 tới Internet gateway, NAT gateway hoặc thiết bị bảo mật | Sai next hop có thể mở đường egress không qua inspection hoặc làm workload mất mạng |

**Static route không tự động an toàn hơn dynamic route**: nó có thể bị thay đổi bởi tài khoản quản trị bị xâm nhập, automation sai hoặc drift cấu hình. Dynamic routing có cơ chế kiểm soát riêng như neighbor authentication, policy import/export và validation, nhưng cần triển khai đúng.

### 3.1. Tuyến mặc định trên host Windows/Linux

Client DHCPv4 có thể nhận nhiều thông số như địa chỉ, mask, router, DNS, thời hạn lease. **Option 3** chỉ là thông tin máy chủ đưa ra; host có thể có thêm route từ VPN, interface khác, metric tự động hoặc chính sách riêng, nên tuyến thực tế phải được kiểm tra trong **effective routing table**.

Ví dụ laptop vừa có Wi-Fi, Ethernet và VPN:

~~~text
Wi-Fi       -> default via 10.60.10.1
Ethernet    -> default via 10.70.10.1
VPN         -> default via 10.90.0.1 (khi full tunnel)
~~~

Không thể chỉ nhìn danh sách ba default gateways để biết đường nào được dùng. Phải xét ưu tiên/metric, reachability, routing policy, routing table đang áp dụng và độ dài prefix cho **đích cụ thể**.

### 3.2. Tuyến mặc định trên router biên

Trong một site nhỏ chỉ có một ISP, edge router có thể có default route tới thiết bị phía ISP. Trong mạng lớn hơn, router có thể nhận default từ BGP hoặc quảng bá default vào routing domain nội bộ.

**Không mặc định quảng bá default route vào mọi VRF/VLAN/site.** Chỉ những vùng đã được thiết kế có đường egress và điểm kiểm soát phù hợp mới nên được phép học và sử dụng tuyến đó.

## 4. Một route được lựa chọn và đưa vào forwarding như thế nào?

### 4.1. Route table, FIB và adjacency

- **RIB (Routing Information Base)** lưu các route mà hệ thống biết, cùng nguồn, thuộc tính và mức ưu tiên.
- **FIB (Forwarding Information Base)** là dữ liệu được dùng để quyết định chuyển tiếp gói trong dataplane; FIB thường được xây dựng từ các tuyến đã được chọn.
- **Next-hop adjacency** mô tả khả năng gửi gói tới láng giềng tiếp theo, ví dụ ánh xạ IPv4 next hop sang MAC qua ARP hoặc IPv6 qua Neighbor Discovery.

Một route được cấu hình nhưng **chưa cài vào FIB**, bị đánh dấu không hợp lệ, next hop không reachable hoặc bị policy khác can thiệp có thể không tạo ra chuyển tiếp thực tế như mong đợi.

~~~text
Ứng dụng gửi packet
       |
Policy routing / lựa chọn bảng (nếu có)
       |
Longest-prefix match trong bảng phù hợp
       |
Chọn next hop / interface và kiểm tra khả năng forward
       |
ARP/ND, encapsulation, NAT/firewall ở các điểm thích hợp
       |
Chuyển gói ra interface
~~~

Thứ tự thực tế của NAT, firewall, policy routing và forwarding **khác nhau theo hệ điều hành/thiết bị**; sơ đồ này chỉ là cách suy luận chức năng, không phải pipeline chuẩn cho mọi nhà cung cấp.

### 4.2. Longest prefix khác administrative distance/metric

Có hai câu hỏi khác nhau:

1. **Tuyến nào khớp đích cụ thể nhất?** Độ dài prefix đóng vai trò chính khi tra cứu route.
2. **Nếu có nhiều đường ứng viên tới cùng một prefix, đường nào được chọn/được cài?** Hệ thống có thể sử dụng administrative distance/preference, route metric, thuộc tính giao thức hoặc ECMP theo chính sách nền tảng.

Ví dụ hai default route cùng prefix:

~~~text
0.0.0.0/0 via 198.51.100.1  preference 10  (primary)
0.0.0.0/0 via 192.0.2.1     preference 50  (backup)
~~~

Trong ví dụ này, giả định **giá trị preference nhỏ hơn được ưu tiên** và hai tuyến thuộc cùng routing domain. Tuy nhiên, ý nghĩa metric/administrative distance và thứ tự tính toán không giống nhau giữa Linux, Windows, router và cloud. Đừng bê nguyên con số ưu tiên từ một nền tảng sang nền tảng khác.

Một tuyến **10.60.20.0/24** cụ thể hơn có thể vẫn được sử dụng dù default route khác có metric thấp hơn; metric không tự làm /0 thắng /24 trong lookup thông thường.

### 4.3. ECMP và nhiều default routes

**ECMP (Equal-Cost Multi-Path)** có thể cho phép nhiều next hop có chi phí bằng nhau cùng được cài và chia lưu lượng theo hash/flow tùy thiết bị. Khi cần bảo vệ kết nối stateful:

- Một luồng đi ra qua WAN1 nhưng trả về WAN2 có thể gặp **asymmetric routing** và thiếu connection state.
- SNAT và public IP nguồn có thể thay đổi theo đường egress; đối tác dùng allowlist sẽ chịu tác động.
- Firewall, NAT, VPN và IDS/IPS phải có **điểm kiểm soát đầy đủ trên mọi đường đi**; không được chỉ giám sát một đường.
- Các luồng nhạy cảm có thể cần policy bảo đảm **session affinity** thay vì tùy ý phân bổ qua nhiều next hop.

## 5. Default route có thể thay đổi vì PBR, VRF hoặc VPN

### 5.1. Policy-based routing

**PBR (Policy-Based Routing)** hoặc routing policy có thể chọn route/table/next hop dựa vào nhiều điều kiện hơn địa chỉ đích, chẳng hạn **source IP, ingress interface, DSCP, mark, tenant** hoặc loại traffic. Vì vậy, một câu lệnh chỉ xem bảng route mặc định có thể không giải thích đường thực tế.

Ví dụ:

~~~text
Thiết bị A thuộc USER VLAN:
  destination Internet -> dùng default WAN1

Thiết bị B thuộc MANAGEMENT VLAN:
  source 10.60.99.0/24 -> policy route tới security inspection gateway

Cùng đích 203.0.113.80 nhưng có thể dùng next hop khác.
~~~

Phải xác định **policy selection** xảy ra ở đâu. Với Linux, các lệnh xem **ip rule** và **ip route show table ...** có thể rất hữu ích; với firewall/router/cloud, cần xem cấu hình route policy hoặc traffic steering tương ứng.

### 5.2. VRF và ranh giới tenant

**VRF (Virtual Routing and Forwarding)** cho phép nhiều bảng định tuyến tách biệt trên một router hoặc nền tảng. Các VRF có thể có **default route riêng**, thậm chí cùng sử dụng prefix địa chỉ giống nhau mà không tự động trao đổi reachability.

~~~text
VRF USER        : 0.0.0.0/0 -> Internet firewall
VRF MANAGEMENT  : 0.0.0.0/0 -> Bastion / quản trị tập trung
VRF DATA        : chỉ route cụ thể; không có Internet default
~~~

Nếu route import/export hoặc route leaking giữa VRF được cấu hình quá rộng, **default route từ vùng ít tin cậy có thể lan vào vùng nhạy cảm**. Muốn kết nối giữa hai vùng, nên dùng điểm kiểm soát được phê duyệt thay vì đưa /0 sang VRF khác mà không đánh giá.

### 5.3. VPN full tunnel và split tunnel

- **Full tunnel:** client có thể nhận default route (hoặc tập route tương đương) để chuyển lưu lượng phù hợp qua VPN; thường dùng khi tổ chức muốn egress qua hệ thống kiểm soát tập trung.
- **Split tunnel:** chỉ các prefix doanh nghiệp cụ thể được gửi qua VPN; traffic khác có thể đi ra local gateway. Một số cấu hình cũng dùng route /1 hoặc PBR để steering, nên không chỉ tìm dòng /0.

Trong cả hai trường hợp, cần kiểm tra **IPv4 và IPv6**, DNS resolver, route tới chính VPN endpoint, kill-switch nếu chính sách yêu cầu, và khả năng fallback khi VPN lỗi. Nếu chỉ đẩy default IPv4 nhưng bỏ quên IPv6, lưu lượng IPv6 có thể đi qua đường ngoài ý định.

## 6. Dual WAN, floating default route và failover

Một site có hai ISP thường muốn **WAN1 làm chính, WAN2 dự phòng**. Có thể sử dụng hai default routes khác mức ưu tiên (*floating static route*), route tracking, dynamic routing hoặc SD-WAN.

~~~mermaid
flowchart LR
    L["LAN / ứng dụng"] --> F["Edge firewall / router"]
    F -->|Primary default| W1["ISP 1 / WAN1"]
    F -. "Backup default" .-> W2["ISP 2 / WAN2"]
    F -. "Path health monitoring" .-> M["Route/SLA monitor"]
    W1 --> I["Internet / đối tác"]
    W2 --> I
~~~

### 6.1. Link up không có nghĩa Internet reachable

Nếu cáp WAN1 còn link nhưng upstream không định tuyến được tới Internet, một tuyến static qua next hop WAN1 có thể **vẫn tồn tại**. Cơ chế failover chỉ dựa vào trạng thái interface chưa chắc chuyển sang WAN2.

Các cách kiểm soát có thể gồm:

- Kiểm tra **reachability của next hop** và nhiều đích giám sát phù hợp, hạn chế dựa vào một host bên ngoài.
- Sử dụng route tracking hoặc SLA/health checks của nền tảng để rút primary route khi đường đi không còn đáp ứng yêu cầu.
- Theo dõi **latency, packet loss, route changes và phiên stateful** khi failover.
- Có **hysteresis/hold-down** hoặc ngưỡng thích hợp để tránh hai route liên tục đảo khi đường chập chờn.
- Ghi rõ chính sách **failback**, bởi khôi phục WAN1 quá nhanh có thể làm gián đoạn các session đang ổn định qua WAN2.

### 6.2. Failover của định tuyến chưa đủ

Khi WAN2 thay WAN1:

1. **SNAT source IP** có thể đổi, khiến một số phiên Internet bị ngắt hoặc đối tác từ chối IP mới.
2. **Stateful firewall** có thể cần tạo phiên mới; HA state synchronization có khả năng và giới hạn riêng.
3. **VPN tunnel** có thể cần thương lượng lại hoặc có đường alternate, DNS và định tuyến quay về phải phù hợp.
4. **Inbound traffic** tới IP public của WAN1 không tự chuyển sang WAN2; có thể cần thiết kế DNS, BGP, dịch vụ edge hoặc mechanism failover khác.
5. **Telemetry** cần ghi biết phiên đi qua đường nào để điều tra chặn nhầm và rủi ro bypass.

Một hệ thống “ping Internet lại được” sau failover vẫn có thể hỏng HTTPS, DNS, inbound service, đường tới đối tác hoặc mạng private. Phải kiểm thử đủ luồng nghiệp vụ.

## 7. Threat model: vì sao default route là bề mặt tấn công?

Default route có phạm vi bao phủ lớn, nên một chủ thể làm thay đổi route hoặc **next-hop resolution** có thể gây tác động lớn. Không phải tình huống nào cũng là chủ đích xấu; sai cấu hình cũng có hậu quả tương tự.

| Threat / tình huống | Đường tác động | Rủi ro | Control phòng ngừa và phát hiện |
| --- | --- | --- | --- |
| **Rogue DHCPv4** cấp Option 3 sai | Client mới nhận default gateway do server trái phép cung cấp | Mất mạng, chuyển DNS/egress, có thể bị theo dõi/chặn | DHCP snooping tại access, kiểm soát trusted port, IPAM baseline, log OFFER/ACK |
| **Rogue IPv6 RA** | Host học default router IPv6 từ nguồn không được phép | IPv6 traffic đi đường không mong muốn, bypass policy | RA Guard/ND inspection phù hợp, 802.1X/NAC, giám sát RA |
| **Thay đổi route trái phép trên router** | Tài khoản quản trị hoặc automation sửa /0 next hop | Blackhole, chuyển egress ra đối tượng không được duyệt | MFA, quyền tối thiểu, AAA/audit, IaC/config review, cảnh báo diff routing table |
| **Dynamic route injection** | Neighbor hoặc thiết bị chưa tin cậy quảng bá default | Lan default sai tới nhiều mạng | Neighbor authentication nếu hỗ trợ, prefix filters, route policy và giới hạn default originate |
| **Route leak giữa VRF/VPN/tenant** | Import/export hoặc PBR không đúng | Chảy traffic khỏi vùng cách ly, có thể bỏ qua inspection | Tách VRF, whitelist route được import, xét route target/policy, negative tests |
| **BGP route leak/hijack** | Quảng bá route sai hoặc policy BGP lỏng | Chuyển traffic sai trên hệ thống liên miền | Route/prefix/AS-path filtering, giám sát BGP, RPKI origin validation trong phạm vi hỗ trợ |
| **Next-hop spoofing / L2 attack** | ARP/ND bị thao túng dù route ghi gateway đúng | Chuyển packet tới MAC không đúng hoặc gián đoạn | DAI/IP source guard, RA Guard/ND security, segmentation, bảo vệ access port |
| **Failover thiếu kiểm soát** | Route bị rút hoặc chọn backup ngoài chính sách | Mất session, NAT thay đổi hoặc bypass firewall | Health checks, approved backup path, giám sát route change và kiểm thử failover |
| **Default route thiếu** | Workload không có đường tới các dịch vụ cần thiết | Gián đoạn, khó khôi phục, lỗi monitoring | Route inventory, dependency map, synthetic tests, controlled rollout |

### 7.1. Route hijack khác DNS spoofing

Khi **DNS spoofing**, client có thể nhận địa chỉ IP đích sai. Khi **default route bị đổi**, địa chỉ IP đích trong packet có thể **vẫn đúng** nhưng next hop/đường đi đã đổi. Hai cơ chế có thể cùng xuất hiện, nhất là khi rogue DHCP thay cả Option 3 (router) lẫn Option 6 (DNS).

Một gateway không được phép **không tự động đọc được nội dung HTTPS** nếu TLS và xác minh chứng chỉ hoạt động đúng. Tuy vậy, nó có thể quan sát metadata mạng, chặn, làm chậm hoặc chuyển hướng traffic theo khả năng và bối cảnh; vì vậy vẫn là rủi ro cần xử lý.

### 7.2. Route injection trong các giao thức định tuyến

Nếu router nội bộ được phép quảng bá default vào OSPF/BGP nhưng không giới hạn **ai được originate**, một thiết bị hoặc phiên routing bị cấu hình sai có thể đưa default khác vào mạng.

Control nên gắn với **nguồn route tin cậy và policy import/export**:

- Chỉ các edge router được phê duyệt mới được **default originate**.
- Giới hạn adjacency/peer, xác thực control plane theo tính năng của giao thức và nền tảng; không mặc định xác thực neighbor đảm bảo route policy đã an toàn.
- Áp **prefix filter** để chỉ nhận default route khi đây là chủ đích thiết kế, từ peer và routing domain cụ thể.
- Theo dõi **next hop, route source, policy ID, route preference và thời điểm cài route** khi có sự kiện thay đổi.
- Rà soát **route redistribution**: đưa route từ static/BGP vào OSPF hoặc VRF khác không được kéo theo /0 ngoài ý muốn.

Với BGP, **RPKI origin validation** giúp đánh giá tính hợp lệ về **origin AS của prefix được công bố** khi có ROA phù hợp, nhưng **không xác thực toàn bộ đường AS-path, không bảo vệ mọi policy route leak và không thay thế lọc default route từ neighbor**. Không coi “đã bật RPKI” là đủ để cấp quyền học bất kỳ route /0 nào.

## 8. Default route và các lớp phòng vệ khác

### 8.1. Routing không thay thế firewall

**Route quyết định chặng chuyển tiếp**, còn **firewall/ACL quyết định traffic nào được phép** tại điểm kiểm soát của nó. Một default route tới Internet gateway không phải quy tắc cho phép tất cả dịch vụ; một default route tới firewall cũng **không bảo đảm** firewall đã được cấu hình đúng rule.

Ngược lại, firewall có deny rule đúng nhưng traffic đi **qua next hop khác, không qua firewall đó** sẽ không chịu rule mong muốn. Phải kết hợp **route design + enforcement path + tests** để bảo đảm không có đường bypass.

### 8.2. NAT và nhận dạng egress

NAT thường xảy ra trên gateway/firewall khi chuyển traffic từ IP private ra Internet. Nếu route egress thay đổi:

- Traffic có thể đi qua thiết bị **không có SNAT phù hợp**, khiến response không quay về.
- IP public nguồn có thể đổi; hệ thống đối tác dùng source allowlist sẽ từ chối.
- Log ứng dụng và firewall có thể ghi IP trước/sau NAT khác nhau; cần session/NAT mapping để correlate.

**NAT không phải authentication**. Nó không xác minh user hoặc workload có quyền truy cập service. Với yêu cầu bảo vệ dữ liệu hoặc danh tính, cần TLS, xác thực, phân quyền và giám sát bên cạnh routing.

### 8.3. IDS/IPS và khả năng quan sát

Thay đổi default route có thể khiến traffic **không đi qua sensor IDS/IPS** đặt trên đường cũ. Vì vậy, phải xác định toàn bộ **ingress, east–west, egress và backup paths** trong threat model; logging cần đủ để nhìn thấy route change, interface change và sự khác biệt lưu lượng giữa các đường.

### 8.4. DNS và lỗi dễ nhầm với route

Nếu người dùng báo “không vào được website” sau khi route thay đổi, phân biệt:

1. DNS trả đúng IP hay client đang hỏi resolver sai?
2. Có route tới **IP resolver** và **IP đích** không?
3. ARP/ND có phân giải được next hop không?
4. Firewall/NAT có cho phép phiên và response không?
5. TLS/ứng dụng có phản hồi bình thường sau khi transport kết nối không?

Chỉ có lỗi DNS không chứng minh default route sai, và có default route đúng cũng không chứng minh DNS đang hoạt động.

## 9. Default route trong cloud và mạng hybrid

Trong cloud, **route table thường được gắn với subnet hoặc tài nguyên mạng ảo**; next hop có thể là Internet gateway, NAT gateway, VPN gateway, transit hub, virtual appliance hoặc endpoint được nhà cung cấp quản lý. Quy tắc chọn tuyến và cách ưu tiên route tự động/route người dùng tạo **khác nhau giữa các nhà cung cấp**.

Một mô hình khái niệm:

~~~mermaid
flowchart TB
    I["Internet"] --> IGW["Internet gateway / Edge"]
    IGW --> P["Public subnet: reverse proxy"]
    P --> A["Private application subnet"]
    A --> D["Private database subnet"]
    A --> NAT["NAT gateway / egress firewall"]
    NAT --> IGW
    M["On-premises management"] --> VPN["VPN / Transit / Private connection"]
    VPN --> A
~~~

### 9.1. Ví dụ phân tách route table theo mục đích

| Vùng | Các tuyến khái niệm | Tác dụng và giới hạn |
| --- | --- | --- |
| **Public edge subnet** | CIDR nội bộ theo route local; **0.0.0.0/0 → Internet gateway** nếu thiết kế yêu cầu | Cho phép có đường tới Internet; quyền inbound còn phụ thuộc địa chỉ public, firewall/security group, NACL và service |
| **Private application subnet** | Route nội bộ; **0.0.0.0/0 → NAT/egress inspection** theo kiến trúc | Cho phép outbound cần thiết qua điểm kiểm soát; không tự tạo quyền inbound trực tiếp từ Internet |
| **Private database subnet** | Route nội bộ và các route tối thiểu tới dịch vụ phụ trợ; có thể **không có default Internet route** | Giảm khả năng tiếp xúc Internet; cần xem backup, monitoring và phụ thuộc hợp lệ |
| **Hybrid subnet / VPN** | Route cụ thể cho prefix on-premises qua VPN/transit; default đi qua điểm egress được chỉ định | Không để 0/0 từ đường VPN thay thế mọi route ngoài ý muốn |

Với kiến trúc theo kiểu AWS, private subnet IPv4 thường có thể dùng NAT gateway ở public subnet, còn public subnet dùng Internet gateway. Nhưng **đây không phải cấu hình đúng duy nhất cho mọi cloud** và không đủ để chứng minh an toàn. Cần xem chính xác semantics của route table, security group/NSG, NACL, gateway, public IP và chính sách của dịch vụ cloud đang dùng.

### 9.2. IPv6 egress không giống IPv4 NAT

Nhiều kiến trúc cloud cung cấp IPv6 globally routable cho workload mà không dùng NAT IPv4 thông thường. Với một số nền tảng, đường **::/0** có thể tới Internet gateway hoặc một **egress-only Internet gateway** để giới hạn kết nối khởi tạo từ ngoài; hành vi phụ thuộc sản phẩm và security policy đi kèm.

**Không suy luận rằng IPv4 private subnet sử dụng NAT thì IPv6 cũng tự được bảo vệ tương đương.** Phải thiết kế và kiểm thử riêng route IPv6, inbound/outbound policy, DNS AAAA và giám sát.

### 9.3. Route leak qua peering, transit hoặc VPN

Một prefix cụ thể tới VPC/VNet đối tác thường an toàn và dễ review hơn route **0.0.0.0/0** vô tình được nhập từ một mạng khác. Nếu default được advertise/import qua transit, có thể xảy ra:

- Lưu lượng Internet của subnet rẽ qua kết nối hybrid hoặc đối tác ngoài kế hoạch.
- Bỏ qua egress firewall dự kiến hoặc đi qua gateway không có NAT.
- Hình thành tuyến bất đối xứng, làm lỗi stateful firewall.
- Tăng chi phí egress hoặc truyền dữ liệu sai vùng pháp lý/chính sách.

Route propagation/import/export nên có **allowlist prefix, owner, phạm vi VRF/route table và kiểm thử** rõ ràng. Một đường VPN đang lên (tunnel up) không chứng minh tất cả route đã được cài và dùng đúng.

## 10. Kiểm tra default route trên hệ thống thực

**Chỉ dùng các lệnh quan sát trong hệ thống được phép quản trị.** Các địa chỉ ví dụ thuộc dải tài liệu, không phải mục tiêu kiểm thử ngoài Internet. Khi điều tra, ưu tiên đọc cấu hình, trạng thái và log trước khi thay route; không tự xóa default route trên máy đang truy cập từ xa vì có thể làm mất kết nối quản trị.

### 10.1. Linux: route table, policy và next-hop

~~~bash
# Hiển thị các default route IPv4 và IPv6.
ip -4 route show default
ip -6 route show default

# Hiển thị toàn bộ bảng route chính của từng address family.
ip -4 route show
ip -6 route show

# Hỏi kernel chọn đường nào tới một đích IPv4 minh họa.
ip -4 route get 203.0.113.80

# Hỏi đường tới một địa chỉ IPv6 thuộc dải tài liệu.
ip -6 route get 2001:db8::80

# Kiểm tra routing policy và các bảng được cấu hình.
ip rule show
ip route show table all

# Xem next-hop neighbors và trạng thái ARP/ND.
ip neigh show

# Xem IPv4 địa chỉ/đường mạng của interface.
ip -4 address show
~~~

Ví dụ đầu ra giả định:

~~~text
default via 10.60.10.1 dev eth0 proto dhcp metric 100
10.60.10.0/24 dev eth0 proto kernel scope link src 10.60.10.25 metric 100

203.0.113.80 via 10.60.10.1 dev eth0 src 10.60.10.25 uid 1000
    cache
~~~

Giải thích: kernel **dự kiến** gửi traffic tới 203.0.113.80 qua gateway 10.60.10.1 theo lookup đang dùng. Nó **không chứng minh gói đã đi qua gateway**, firewall chấp nhận hay endpoint đích phản hồi. Với PBR hoặc traffic từ một nguồn/mark/interface khác, kết quả lookup có thể khác; cần mô phỏng đúng ngữ cảnh của luồng.

### 10.2. Windows: route và interface đang được chọn

~~~powershell
# Xem địa chỉ, gateway và DNS theo adapter.
Get-NetIPConfiguration

# Xem toàn bộ bảng route ở Windows.
route print

# Chỉ xem default route IPv4.
Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0'

# Chỉ xem default route IPv6.
Get-NetRoute -AddressFamily IPv6 -DestinationPrefix '::/0'

# Xem thông tin IP, DNS và DHCP server theo adapter.
ipconfig /all

# Xem đường đi tới một đích tài liệu bằng probe thông thường, nếu được phép.
tracert -d 203.0.113.80
~~~

Trên Windows, **route metric và interface metric** có thể cùng góp phần lựa chọn route. VPN client hoặc policy quản trị endpoint còn có thể thêm/sửa route khi kết nối; cần so sánh trước/sau khi bật VPN.

### 10.3. Packet/flow evidence cần đối chiếu

| Nguồn | Dữ kiện hữu ích | Giới hạn |
| --- | --- | --- |
| **Route table/FIB** | Prefix, next hop, source protocol, preference, trạng thái install, VRF | Có route không có nghĩa packet được phép forward |
| **Routing policy/PBR** | Rule theo nguồn/đích/mark/interface, bảng được chọn | Sai ngữ cảnh lookup có thể gây kết luận nhầm |
| **ARP/Neighbor table** | Next-hop IP ↔ MAC, interface, trạng thái reachability | MAC có thể bị spoof; entry cũ có thể tồn tại trong cache |
| **Firewall/session/NAT logs** | Original/translated tuple, zone, policy ID, egress interface | Log có thể chỉ ghi khi mở/đóng session hoặc bị sampling |
| **VPN/SD-WAN logs** | Tunnel ID, route push/learn, health/selected path | Tunnel UP không đảm bảo mọi route đúng |
| **BGP/OSPF route logs** | Neighbor, prefix advertised/received, origin, route changes | Cần đối chiếu import policy và FIB, không chỉ control-plane |
| **DHCP/IPv6 RA capture** | Option 3 hoặc RA router lifetime, nguồn và interface | Chỉ quan sát được phạm vi capture; source có thể bị giả mạo |
| **Cloud route table/audit** | Subnet association, next-hop resource, thay đổi cấu hình | Control plane đúng chưa đảm bảo security group/NAT đúng |

Khi cần packet capture, chọn điểm quan sát **trước và sau enforcement point** trong phạm vi được cấp quyền, rồi đối chiếu 5-tuple, NAT, route và timestamp. Một kết nối timeout có thể do route, firewall, DNS, MTU, thiết bị đích hoặc đường trả về; **không được gán ngay cho default route**.

### 10.4. Những dấu hiệu và cách đọc

| Triệu chứng | Khả năng cần xét | Bước kiểm chứng |
| --- | --- | --- |
| Không có dòng default, đích ngoài subnet báo unreachable | Thiếu route hoặc policy chọn table khác | Kiểm tra routing tables/VRF, source, interface |
| Default route đúng nhưng không ra Internet | ARP/ND, upstream, NAT, firewall, DNS, path health | Kiểm tra neighbor, route trên gateway, session/NAT log |
| Bật VPN thì Internet đi qua IP egress khác | Full-tunnel default hoặc PBR thay đổi | So route/rules trước–sau và VPN session config |
| Một số subnet đi qua WAN2 dù WAN1 vẫn hoạt động | PBR/ECMP, route cụ thể, VRF, path tracking | Lookup đúng nguồn/đích, ECMP hash và policy |
| Sau failover chỉ HTTPS/đối tác lỗi | NAT/allowlist/TLS/session path bị thay đổi | Đối chiếu SNAT IP, flow và app logs |
| Client IPv4 ổn, IPv6 bypass VPN | Thiếu chính sách ::/0 hoặc route IPv6 qua gateway lạ | Kiểm tra RA, IPv6 routes, VPN và firewall IPv6 |
| Firewall có allow nhưng không thấy session | Route bypass, capture sai vị trí, rule khác ưu tiên | Xem path, ingress/egress zone, NAT, routing policy |

**Traceroute/tracert** dùng TTL hoặc hop-limit và các phản hồi ICMP để suy ra một phần đường đi, nhưng một hop không trả lời không nhất thiết lỗi; ECMP, NAT và firewall có thể làm kết quả thay đổi theo loại probe. Không dùng traceroute như chứng cứ duy nhất cho đường đi của traffic ứng dụng.

## 11. Case study: default gateway bị thay do rogue DHCP

### 11.1. Bối cảnh

Một văn phòng dùng mạng **10.60.10.0/24** với default gateway đã được phê duyệt **10.60.10.1**; traffic Internet bắt buộc đi qua **firewall biên có NAT và IDS/IPS**. Sau khi một thiết bị mới được cắm vào switch, một nhóm laptop không còn truy cập được dịch vụ nội bộ hoặc có đường truy cập Internet bất thường.

Đội SOC nghi vấn **rogue DHCP server** phát default router không đúng. Đây là giả thuyết, cần có evidence trước khi kết luận.

### 11.2. Evidence giả định

| Mã | Nguồn | Quan sát |
| --- | --- | --- |
| **E1** | Client A / route table | Default route qua **10.60.10.254** thay vì 10.60.10.1 |
| **E2** | DHCP client log | DHCPACK gần thời điểm lỗi chứa Option 3 = **10.60.10.254** và server ID không thuộc inventory |
| **E3** | Packet capture ở access VLAN | Có OFFER/ACK từ một nguồn không được phê duyệt cho cùng transaction/client |
| **E4** | Switch/port mapping | MAC nguồn liên quan được học ở một access port mới có thiết bị lạ |
| **E5** | Firewall biên | Giảm session từ nhóm client ảnh hưởng; không đủ một mình để chứng minh bypass |
| **E6** | Test có kiểm soát sau containment | Client mới nhận DHCPACK từ server hợp lệ, default route 10.60.10.1 và lưu lượng đi qua firewall dự kiến |

### 11.3. Cách xử lý an toàn

1. **Ghi hiện trạng trước khi sửa:** timestamp, interface, DHCP server identifier, router option, route table, IP/gateway/DNS thực, MAC và VLAN; giữ log theo chính sách dữ liệu.
2. **Xác nhận đường phát DHCP:** đối chiếu packet, switch port, inventory và thiết bị thật; tránh quy trách nhiệm chỉ từ MAC hoặc IP tự khai.
3. **Khoanh nguồn sai:** áp DHCP snooping trên VLAN/port phù hợp hoặc cô lập thiết bị đã xác minh theo change/incident process; không tắt bừa một trunk/AP/uplink có nhiều dịch vụ.
4. **Khôi phục lease có kiểm soát:** renew client đại diện, xác minh default route 10.60.10.1, DNS resolver đúng và route cụ thể tới vùng nội bộ vẫn hoạt động.
5. **Kiểm tra forwarding và policy:** so flow/NAT logs tại firewall, bảo đảm egress không vòng qua IDS/IPS, đồng thời đo thành công truy cập dịch vụ.
6. **Tìm phạm vi ảnh hưởng:** kiểm tra client có lease cũ chưa renew, các VLAN khác, IPv6 RA và dấu hiệu DNS/gateway ngoài danh sách.
7. **Đóng sự cố:** lưu evidence IDs, kết luận theo mức chắc chắn, thay đổi đã phê duyệt, owner và kế hoạch giám sát recurrence.

**Residual risk:** rogue DHCP chỉ là một cách thay đổi default route; người dùng VPN, RA IPv6, tài khoản quản trị router hoặc policy cloud sai vẫn có thể tạo đường đi không mong muốn. Cần kiểm soát thêm các nguồn thay đổi tuyến phù hợp kiến trúc.

## 12. Case study: failover WAN thành công nhưng API đối tác lỗi

### 12.1. Bối cảnh

Một chi nhánh có WAN1 và WAN2, traffic bình thường ra qua firewall với SNAT public IP của WAN1. Sau khi WAN1 mất, default route tự chuyển qua WAN2. Người dùng lướt web được nhưng API đối tác trả timeout hoặc từ chối kết nối.

### 12.2. Phân tích theo từng lớp

- **Route:** lookup cho IP đối tác có đi qua WAN2 theo policy hay một route cụ thể vẫn trỏ WAN1?
- **NAT:** source public IP qua WAN2 là gì, có thuộc allowlist bên đối tác chưa?
- **Firewall/session:** kết nối mới có policy allow không, session cũ còn state WAN1 không?
- **Đường trả về:** đối tác hoặc mạng upstream có route về public IP mới không?
- **VPN/TLS:** nếu API đi qua VPN tunnel hoặc mTLS, đường mới có đáp ứng đúng ràng buộc kết nối không?
- **DNS:** phân giải hostname có đúng đích và dùng resolver theo policy không?

### 12.3. Thiết kế cải thiện

Cần ghi lại **approved primary/backup egress**, IP nguồn và cơ chế thông báo cho đối tác, path health SLA, failback policy, khả năng khởi tạo lại session và bộ kiểm thử nghiệp vụ. Failover chỉ được coi là đạt khi cả tuyến, NAT, firewall và ứng dụng cần thiết hoạt động theo SLO đã đặt.

## 13. Checklist thay đổi và kiểm thử default route

### 13.1. Mẫu mô tả kiểm soát

~~~yaml
# Mô tả yêu cầu để review, không phải cú pháp cấu hình cho router/cloud.
control_id: ROUTE-DEFAULT-008
objective: "Internet egress of user network must traverse approved firewall"
address_families: ["IPv4", "IPv6"]
scope:
  routing_domain: "USER-VRF"
  sources: ["User VLANs"]
allowed_default_next_hops:
  primary: "Approved edge firewall path"
  backup: "Approved secondary inspection path"
denied_conditions:
  - "Unapproved DHCP/RA default gateway"
  - "Default route imported from untrusted routing peer"
  - "Direct Internet egress bypassing inspection"
preventive_controls:
  - "DHCP snooping and RA Guard where supported"
  - "Route advertisement/import filtering"
  - "Change control and least-privilege administration"
detective_controls:
  - "RIB/FIB and next-hop change alert"
  - "Firewall egress/session telemetry"
  - "IPAM and routing policy comparison"
tests:
  - "Approved user traffic egresses through inspection"
  - "Internal route retains more-specific prefix"
  - "Unapproved route advertisement is rejected"
  - "Failover uses approved backup without cross-VRF leak"
owner: "Network Platform / Security Operations"
review_trigger: "ISP, VPN, topology, IPv6, cloud or firewall policy change"
~~~

### 13.2. Positive và negative tests

| Test | Kịch bản | Kết quả kỳ vọng / evidence |
| --- | --- | --- |
| **P1 – Internet bình thường** | Client được phép tới đích ngoài mạng nội bộ | Default route và firewall/NAT đúng, có session log |
| **P2 – Mạng nội bộ cụ thể** | Client đi tới app subnet có route riêng | Route cụ thể thắng /0, không bị gửi ra WAN |
| **P3 – Quay về qua stateful firewall** | Server phản hồi phiên được phép | Không lệch đường gây drop session ngoài dự kiến |
| **P4 – VPN theo policy** | Client bật full/split tunnel | Traffic IPv4/IPv6 và DNS đi đúng nơi, không mất đường tới VPN endpoint |
| **N1 – Rogue gateway** | Lab cô lập có DHCPv4 Option 3/IPv6 RA không được phê duyệt | Chính sách access ngăn hoặc phát hiện; route hợp lệ không bị thay |
| **N2 – Default route không tin cậy** | Mô phỏng import/quảng bá /0 từ peer không được phép | Route không được cài vào FIB theo policy |
| **N3 – Bypass inspection** | Luồng user thử đi tới Internet qua next hop ngoài danh sách | Không có đường egress được phép ngoài checkpoint |
| **F1 – Failover** | Ngắt đường WAN1 trong môi trường được ủy quyền | Route backup được chọn theo ngưỡng, NAT/ứng dụng cần thiết hoạt động |
| **F2 – Failback** | Khôi phục WAN1 | Trở lại đường mong muốn không flap hoặc gây gián đoạn quá SLO |
| **O1 – Observability** | Tạo một thay đổi route trong staging | Alert có route prefix, source, next hop cũ/mới, VRF, interface, time |

Các test có thể ảnh hưởng kết nối và khả năng quản trị. Cần có **staging hoặc maintenance window, đường quản trị dự phòng, rollback, owner và phạm vi được cấp quyền**. Không cố tạo rogue route hoặc thay default trên mạng sản xuất chỉ để xem chuyện gì xảy ra.

### 13.3. Kiểm chứng khi chưa thể tạo sự cố thật

Nếu không được phép ngắt WAN hay mô phỏng rogue DHCP, vẫn có thể:

- Review **running configuration**, backup route và health checks hiện tại.
- So sánh **RIB/FIB, policy và network diagram** với approved baseline.
- Dùng tính năng **route lookup/policy simulation** của nền tảng.
- Xem historical route changes, log failover đã xảy ra và session/NAT tại thời điểm đó.
- Kiểm thử trên lab/VRF cô lập hoặc digital twin khi có hạ tầng phù hợp.

Chứng cứ từ cấu hình và simulator giúp giảm bất định, nhưng **không phải bằng chứng thực nghiệm đầy đủ** cho mọi kiểu failover; báo cáo cần ghi rõ mức độ xác minh.

## 14. Monitoring và incident response cho routing security

### 14.1. Các tín hiệu quan trọng

| Tín hiệu / metric | Vì sao cần | Cảnh báo nên có ngữ cảnh |
| --- | --- | --- |
| Route **0.0.0.0/0** hoặc **::/0** được thêm, xóa hoặc đổi next hop | Phát hiện thay đổi đường đi diện rộng | VRF/table, source protocol, metric, interface, owner |
| Primary → backup hoặc ECMP membership thay đổi | Phát hiện failover/flap | Health-check result, link state, duration |
| Next-hop ARP/ND entry đổi bất thường | Phát hiện nguy cơ spoofing hoặc migration ngoài kế hoạch | VLAN/port, MAC, IP, change ticket |
| Default route từ peer BGP/OSPF lạ | Phát hiện route injection/leak | Neighbor, prefix filter, route policy, AS/area |
| Egress interface/public source IP thay đổi | Phát hiện NAT/route drift | Workload, VPN/site, nguồn–đích và app impact |
| IDS/IPS hoặc firewall session volume thay đổi mạnh | Gợi ý traffic chuyển đường hoặc không qua inspection | Log coverage, backup paths, traffic baseline |
| Route table cloud hoặc VPN thay đổi | Phát hiện control-plane drift | Resource ID, subnet association, actor và audit ID |
| IPv4 bình thường, IPv6 traffic thay đổi đường | Phát hiện lỗ hổng dual-stack | ::/0, RA, IPv6 firewall, endpoint network state |

### 14.2. Thu thập evidence theo chuỗi

Một bản ghi sự cố default route nên có:

~~~text
Case ID:
Time window + timezone:
Affected users / network / VRF:
Destination prefix and expected path:
Observed route prefix + next hop + preference:
Source of route (static/DHCP/RA/BGP/VPN/cloud):
Routing policy and route table:
Ingress/egress interface, NAT and firewall policy:
RIB/FIB snapshot + ARP/ND or neighbor state:
Flow / session / route-change logs:
Positive/negative tests with timestamps:
Business impact and residual risk:
Owner / change ticket / rollback:
~~~

Cần giữ **snapshot trước/sau** khi có thể, nêu trạng thái route thực và mốc thời gian. Log có thể lệch múi giờ hoặc sampling; không suy luận nguyên nhân chỉ từ một dòng syslog “route changed”. Nếu có điều tra an ninh, giữ evidence đúng quyền truy cập, che thông tin nhạy cảm, ghi nơi lưu và người thu thập.

### 14.3. Phân biệt sự kiện mạng và sự cố an ninh

Một default route đổi vì ISP mất tín hiệu có thể là **failover hợp lệ**. Cùng một thay đổi do tài khoản quản trị lạ hoặc một DHCP server không được phê duyệt có thể là **sự kiện bảo mật**. Cần so sánh policy, change window, route source, cấu hình đã duyệt và mức độ ảnh hưởng trước khi kết luận.

## 15. Các sai lầm thường gặp

1. **“0.0.0.0/0 chỉ tới địa chỉ 0.0.0.0.”** Đây là prefix /0 khớp mọi IPv4; next hop là thông tin riêng.
2. **“Có default route nghĩa là có Internet.”** Route không bảo đảm ARP, NAT, firewall, DNS hay upstream hoạt động.
3. **“Default route luôn thắng mọi route khác nếu metric nhỏ.”** Lookup thông thường ưu tiên prefix cụ thể hơn trước khi chọn giữa các tuyến cùng prefix.
4. **“Default gateway trên máy là đường Internet của cả tổ chức.”** Nó chỉ là chặng đầu của host; các router phía sau có policy riêng.
5. **“Bật VPN nghĩa mọi traffic đi trong tunnel.”** Split tunnel, PBR, route /1 và IPv6 có thể cho kết quả khác.
6. **“DHCPv6 cung cấp default gateway như DHCPv4.”** Default router IPv6 thường đến từ RA.
7. **“Có firewall rule nghĩa mọi traffic phải đi qua firewall đó.”** Route bypass hoặc đường WAN dự phòng có thể đi ngoài sensor/policy.
8. **“WAN interface UP nghĩa default route còn dùng tốt.”** Upstream có thể không reach được; cần end-to-end path health.
9. **“Failover route thành công nghĩa toàn bộ ứng dụng thành công.”** SNAT IP, firewall state, VPN, DNS và inbound path có thể khác.
10. **“Hai default route luôn là lỗi.”** Có thể chủ động dùng backup hoặc ECMP; phải xét ưu tiên, policy và topology.
11. **“Thay đổi /0 không ảnh hưởng bảo mật nếu mã hóa TLS đã bật.”** Route thay đổi vẫn có thể chặn, lộ metadata, gây DoS hoặc bỏ qua giám sát.
12. **“RPKI bảo vệ mọi route leak và xác thực toàn bộ đường BGP.”** RPKI origin validation chỉ xử lý một phần nguồn gốc prefix theo ROA, không thay route filters.
13. **“Tuyến trong bảng route luôn được forwarding như mong muốn.”** Còn PBR, VRF, FIB, adjacency, NAT, firewall và session state.
14. **“Chặn ::/0 không cần kiểm tra nếu IPv4 đã an toàn.”** Mạng dual-stack có thể dùng IPv6 ra ngoài không qua điểm IPv4 dự kiến.
15. **“Traceroute không hiện một hop nghĩa hop đó chặn tất cả.”** ICMP/TTL filtering và đường trả về có thể khiến hop không phản hồi dù traffic khác vẫn đi qua.

## 16. Bài tập vận dụng và gợi ý đáp án

### Bài 1 — Chọn tuyến theo prefix

Một router có:

~~~text
10.0.0.0/8       via 10.60.10.3
10.60.20.0/24    via 10.60.10.2
0.0.0.0/0        via 198.51.100.1
~~~

**Câu hỏi:** traffic tới **10.60.20.15** và **203.0.113.80** chọn tuyến nào? Nếu default có metric thấp hơn /24, nó có thắng không?

**Gợi ý:** 10.60.20.15 dùng **10.60.20.0/24**, còn 203.0.113.80 dùng **0.0.0.0/0** nếu không có tuyến phù hợp hơn. Metric không làm /0 lấn át prefix /24 ở lookup thông thường.

### Bài 2 — Laptop bật full-tunnel VPN

Laptop có default IPv4 qua Wi-Fi và default khác qua VPN. Đội bảo mật muốn mọi lưu lượng ứng dụng ra Internet qua egress VPN. Chỉ kiểm tra **ip -4 route show default** có đủ không?

**Gợi ý:** chưa đủ. Xem route thực tế tới đích, policy routing, route /1 hoặc route cụ thể, DNS, IPv6 **::/0**, VPN endpoint route và log egress. Cần xác minh cả đường phản hồi và trạng thái ứng dụng.

### Bài 3 — Default route giả mạo từ LAN

Client đang dùng gateway **10.60.10.254** ngoài danh sách approved, nhưng app vẫn dùng HTTPS bình thường. Có thể bỏ qua cảnh báo không?

**Gợi ý:** không. Xác minh DHCPACK/Option 3, IPv6 RA nếu liên quan, route table, ARP/ND và switch port. HTTPS thành công không chứng minh đường đi đúng policy; gateway lạ vẫn có thể gây rủi ro giám sát, metadata hoặc sự cố tương lai.

### Bài 4 — Default route trong private cloud subnet

Ứng dụng ở private subnet cần gọi dịch vụ cập nhật bên ngoài. Route **0.0.0.0/0** đang trỏ thẳng Internet gateway nhưng workload không có public IP và policy chỉ cho phép egress qua NAT/inspection.

**Gợi ý:** xem semantics cloud hiện tại, route table/subnet association, NAT gateway hoặc private service endpoints, security policy, log egress và nhu cầu IPv6 riêng. Không cho rằng chỉ thêm /0 tới Internet gateway là bảo đảm kết nối và an toàn.

### Bài 5 — Failover WAN sai đường

WAN1 mất, WAN2 nhận lưu lượng nhưng API đối tác lỗi. Đội network muốn đổi tất cả firewall allow rule thành Any–Any để thử. Cách phân tích ít rủi ro hơn là gì?

**Gợi ý:** kiểm tra effective default/route cụ thể, SNAT public IP, đối tác source allowlist, session/NAT log, VPN và path quay về. Dùng test có quyền và thay đổi nhỏ có rollback, không mở rộng rule diện rộng khi chưa xác định nguyên nhân.

### Bài 6 — Lập ma trận threat → control → evidence

Thiết kế một hệ thống có **USER VRF**, **DATA VRF**, **hai ISP**, **VPN từ xa** và **workload cloud**. Với mỗi vùng, xác định:

- Có nên có **0.0.0.0/0**, **::/0** không, và next hop nào được phê duyệt?
- Default route được học từ static, DHCP/RA, BGP, VPN hay cloud route table?
- Route nào **không được phép import/leak** sang VRF khác?
- Các điểm firewall/NAT/IDS/IPS nào phải đi qua trên **đường chính và đường dự phòng**?
- Bộ positive/negative/failover tests và log nào chứng minh cấu hình đúng?

**Gợi ý:** bắt đầu từ sơ đồ **trust boundary và luồng nghiệp vụ**, xác định route cụ thể cần thiết trước, rồi cấp default route cho vùng có nhu cầu, kèm monitoring, owner và quy trình rollback.

## 17. Tổng kết

**Default route** là tuyến dự phòng của hệ thống định tuyến: **0.0.0.0/0** trong IPv4 và **::/0** trong IPv6. Nó chỉ được dùng khi không có tuyến cụ thể hơn phù hợp trong ngữ cảnh routing table và policy hiện tại. Đường đi thực tế còn phụ thuộc **next hop, route preference, PBR/VRF, ARP/ND, NAT, firewall và trạng thái đường truyền**.

Trong bảo mật mạng, cần kiểm soát **ai được thay đổi hoặc quảng bá default route**, nơi tuyến được đưa vào FIB, các đường chính/dự phòng và điểm enforcement phải đi qua. DHCP snooping, RA Guard, route filtering, quyền quản trị tối thiểu, BGP/OSPF policy, segmentation, giám sát IDS/IPS và kiểm chứng failover giúp giảm nguy cơ **route hijack, route leak, blackhole và bypass inspection**. Một tuyến chỉ được xem là phù hợp khi đã xác minh **đường đi đến đúng đích, qua đúng điểm kiểm soát, có đường trả về và phục vụ được các luồng nghiệp vụ hợp lệ**.
