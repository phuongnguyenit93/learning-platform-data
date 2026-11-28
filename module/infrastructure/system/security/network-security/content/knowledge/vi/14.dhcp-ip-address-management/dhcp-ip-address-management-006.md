# IP conflict

> **Chương:** DHCP và IP management  
> **Mô-đun:** SECURITY_NETWORK_SECURITY  
> **Phạm vi:** Nhận diện, phân tích và xử lý xung đột địa chỉ IP trong mạng IPv4/IPv6, kết hợp DHCP, IPAM, ARP/NDP, phân đoạn VLAN/subnet, firewall, VPN, xác thực kết nối, giám sát và hạ tầng cloud.

## 1. IP conflict là gì?

**IP conflict** (xung đột địa chỉ IP) là tình huống **hai hoặc nhiều giao diện/thiết bị cùng sử dụng một địa chỉ IP trong phạm vi mạng mà địa chỉ ấy phải duy nhất**, tạo ra sự mơ hồ khi chuyển gói đến đúng thiết bị. Trong mạng LAN IPv4, trường hợp điển hình là hai host trên cùng broadcast domain hoặc cùng subnet lớp 2 đều nhận địa chỉ **10.24.30.120**.

Địa chỉ IP không phải định danh toàn cục duy nhất cho mọi máy trong mọi thời điểm. Cùng một địa chỉ **RFC 1918** có thể được sử dụng hợp lệ ở hai mạng hoàn toàn tách biệt, không có khả năng định tuyến hay liên thông với nhau. Xung đột chỉ phát sinh khi **phạm vi sử dụng và yêu cầu định tuyến** khiến các thiết bị hoặc mạng phải phân biệt hai thực thể đang dùng địa chỉ trùng nhau.

Ở IPv4 LAN, xung đột thường thể hiện bằng **ARP** không nhất quán: máy A cho rằng 10.24.30.120 thuộc MAC thứ nhất, trong khi máy B hoặc một thiết bị khác lại quảng bá địa chỉ đó thuộc MAC thứ hai. Tùy thời điểm, lưu lượng có thể đi tới thiết bị này, thiết bị kia hoặc bị gián đoạn. Ở IPv6, cơ chế **Neighbor Discovery (NDP)** và **Duplicate Address Detection (DAD)** giữ vai trò tương ứng nhưng không dùng ARP.

**Điểm quan trọng:** không phải mọi lần một IP xuất hiện cạnh nhiều MAC đều là cấu hình lỗi. **VRRP/HA virtual IP, proxy ARP, thay đổi MAC khi failover, di chuyển VM và một số kiến trúc đặc thù** có thể tạo tín hiệu tương tự. Trước khi sửa, cần phân biệt **trùng IP ngoài ý muốn** với **địa chỉ ảo được chia sẻ có thiết kế**.

### Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích tại sao IP trùng có thể gây gián đoạn ARP/NDP, DHCP, route và dịch vụ.
2. Phân biệt **duplicate host IP**, **overlapping subnets**, **stale ARP/neighbor cache**, **VIP/HA** và lỗi DNS.
3. Xác định nguyên nhân từ DHCP pool, địa chỉ tĩnh, reservation, rogue DHCP, cấu hình VM/container, VPN hoặc cloud.
4. Sử dụng các công cụ kiểm tra **không làm thay đổi cấu hình** để thu thập bằng chứng trên Linux, Windows và thiết bị mạng.
5. Lập quy trình khoanh vùng, xử lý xung đột, khôi phục kết nối và ngăn tái diễn bằng DHCP/IPAM/NAC.
6. Xem IP conflict như vấn đề **tính sẵn sàng và tính toàn vẹn của ánh xạ địa chỉ**, có thể liên quan đến sự cố bảo mật.

## 2. Nền tảng: địa chỉ IP, subnet và định danh ở lớp 2

Trong một mạng IPv4 thông thường, **IP** định danh một giao diện về mặt lớp 3; **MAC** thường được dùng để chuyển frame trong miền lớp 2. Một host muốn gửi gói IPv4 đến IP nằm cùng subnet có thể dùng **ARP** để tìm địa chỉ MAC liên quan.

~~~mermaid
flowchart LR
    C[Client 10.24.30.10] -->|ARP: Ai giữ 10.24.30.120?| L[LAN / VLAN 30]
    L --> H1[Host A: 10.24.30.120 / MAC A]
    L --> H2[Host B: 10.24.30.120 / MAC B]
    H1 -. ARP reply .-> C
    H2 -. ARP reply .-> C
    C --> X[Ánh xạ IP -> MAC có thể không ổn định]
~~~

Nếu host A và B cùng dùng IP 10.24.30.120 trên VLAN 30, client có thể nhận những thông tin ánh xạ mâu thuẫn. Lưu lượng không nhất thiết luân phiên theo cách đều đặn: việc **OS xử lý ARP, cache, switch, timing, proxy/HA và bảo vệ lớp 2** sẽ quyết định triệu chứng.

### 2.1. Phân biệt các loại định danh

| Khái niệm | Ví dụ | Mục đích | Điểm cần lưu ý |
|---|---|---|---|
| **IPv4 address** | 10.24.30.120 | Địa chỉ lớp 3 | Phải nhất quán theo thiết kế mạng và miền liên thông |
| **IPv6 address** | 2001:db8:30::120 | Địa chỉ lớp 3 IPv6 | Có thể có nhiều địa chỉ trên một interface; DAD xử lý từng địa chỉ |
| **MAC address** | 02:00:00:30:00:12 | Định danh lớp 2 | Có thể đổi do MAC randomization, VM hoặc HA |
| **DHCP client identifier** | Client-ID theo kiểu client | DHCP server nhận diện client để quản lý lease | Không mặc định luôn bằng MAC |
| **DHCPv6 DUID/IAID** | Định danh DHCPv6 | Gắn client/association theo giao thức | Không phải địa chỉ IP và không thay DAD |
| **Hostname/DNS name** | printer.office.example | Tên được phân giải tới IP | DNS sai/chưa cập nhật không đồng nghĩa IP bị trùng |
| **Interface/VLAN/VRF** | VLAN 30, VRF USERS | Chỉ rõ phạm vi kết nối và route | Cùng IP ở hai VRF tách biệt có thể được dùng hợp lệ |
| **Virtual IP (VIP)** | 10.24.30.1 | Địa chỉ dịch vụ/gateway HA | Có cơ chế sở hữu/di chuyển đã thiết kế |

**MAC không phải bằng chứng định danh thiết bị tuyệt đối.** Một thiết bị có thể thay MAC, còn thiết bị giả mạo cũng có thể sử dụng MAC không thuộc quyền của nó. Để kết luận chủ sở hữu một IP cần kết hợp **switch port, DHCP lease, inventory, ARP/NDP, NAC và chủ thiết bị**.

## 3. Xung đột IP khác subnet overlap và routing ambiguity thế nào?

### 3.1. Hai host cùng IP trên cùng VLAN

Ví dụ hai laptop thuộc VLAN 30 đều cấu hình 10.24.30.120/24. Chúng có thể xung đột trực tiếp vì các host khác phải xác định một MAC tương ứng với IP đó trong cùng miền liên kết.

### 3.2. Hai site dùng cùng CIDR

Site A và Site B cùng sử dụng **10.24.30.0/24** nhưng nằm ở hai mạng tách biệt, chưa kết nối: điều này **không tự gây IP conflict tại LAN**. Tuy nhiên khi kết nối qua VPN, peering hoặc SD-WAN, router có thể không biết tuyến 10.24.30.0/24 nên đi tới site nào. Đây là vấn đề **overlapping address space/route ambiguity**; giải pháp có thể là renumber, NAT có kiểm soát hoặc thiết kế VRF/route tách biệt.

### 3.3. Lỗi ARP cache không còn đúng

Một máy đã chuyển VLAN, thay card mạng hoặc failover HA có thể khiến client còn giữ ánh xạ IP–MAC cũ. Đây là **stale ARP/neighbor cache** và có thể giống triệu chứng IP trùng, nhưng không nhất thiết có hai host đang đồng thời sở hữu IP.

### 3.4. DNS trả IP cũ

DNS A/AAAA vẫn trỏ đến IP đã chuyển sang thiết bị khác, khiến người dùng truy cập sai endpoint. Đây trước hết là **DNS/IPAM lifecycle mismatch**, không đủ kết luận hai thiết bị cùng dùng một IP. Cần so dữ liệu DNS, lease, ARP/neighbor và trạng thái host thực.

| Hiện tượng | Có hai host cùng IP trong miền liên kết? | Nơi xác minh đầu tiên |
|---|---|---|
| Trùng IP thực trên VLAN | Có hoặc nghi ngờ rất cao | Host config, ARP/NDP, switch port, DHCP |
| Hai site trùng subnet trước khi kết nối VPN | Không nhất thiết | IPAM liên site, route table, VRF/NAT |
| MAC mới sau HA failover | Không nhất thiết | Cấu hình VIP, HA state, log failover |
| ARP entry cũ sau di chuyển VM | Không nhất thiết | ARP/neighbor age, hypervisor, switch |
| DNS record cũ | Không nhất thiết | DNS authoritative, DNS cache, IPAM |

## 4. DHCP cấp địa chỉ như thế nào và có thể gây trùng ở đâu?

Trong IPv4 DHCP, quy trình thường được mô tả là **DORA**:

1. **Discover:** client tìm DHCP server.
2. **Offer:** server đề xuất địa chỉ và thông số lease.
3. **Request:** client yêu cầu một đề xuất cụ thể.
4. **ACK:** server xác nhận cấp lease cùng tùy chọn mạng.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as DHCP client
    participant R as DHCP relay / LAN
    participant S as DHCP server
    C->>R: DHCPDISCOVER
    R->>S: Forward nếu có relay
    S-->>R: DHCPOFFER: 10.24.30.120
    R-->>C: Offer
    C->>R: DHCPREQUEST
    R->>S: Forward request
    S-->>R: DHCPACK
    R-->>C: Lease + subnet/gateway/DNS
    C->>C: Kiểm tra khả năng dùng địa chỉ theo hệ điều hành
~~~

Sơ đồ là **đơn giản hóa**. Không phải mọi quá trình cấp mới/renew đều lặp lại đầy đủ DORA theo cách trên: client có thể gia hạn lease trực tiếp với DHCP server; relay có thể chuyển đổi địa chỉ nguồn, thêm thông tin liên kết tùy cấu hình; hệ điều hành có cách kiểm tra IP khác nhau.

### 4.1. DHCP không tự loại trừ mọi xung đột

DHCP server quản lý những địa chỉ **nó biết đã cấp**, nhưng có thể **không biết** máy dùng địa chỉ tĩnh, IP được cấp bởi server khác hoặc một client cũ không còn tuân thủ lease. Nếu scope chồng với dải gán tĩnh hoặc các DHCP server có phạm vi cấp không được phối hợp, xung đột có thể xảy ra.

Một số server có tùy chọn **conflict detection** trước khi cấp lease; một số client kiểm tra địa chỉ trước khi đưa vào sử dụng và có thể gửi **DHCPDECLINE** nếu phát hiện địa chỉ đã được dùng. Những cơ chế này hữu ích nhưng **không đảm bảo phát hiện mọi trường hợp**: host có thể không phản hồi probe, firewall/OS có khác biệt, một thiết bị có thể đang offline, hoặc traffic kiểm tra bị chặn.

### 4.2. Các yếu tố cần phân biệt

| Thuật ngữ | Ý nghĩa | Rủi ro nếu quản lý sai |
|---|---|---|
| **Scope/pool** | Dải IP DHCP được phép cấp | Chồng với IP tĩnh hoặc pool khác |
| **Lease** | Quyền sử dụng địa chỉ trong thời hạn DHCP | Địa chỉ tái cấp khi thiết bị cũ vẫn tự dùng |
| **Reservation** | Ràng buộc địa chỉ dự kiến với client identifier theo server | Reservation và static setting không đồng nhất |
| **Exclusion** | Địa chỉ không được DHCP pool tự cấp | Quên exclude IP gateway, server, thiết bị tĩnh |
| **DHCP relay** | Chuyển thông điệp DHCP qua L3 theo thiết kế | Sai mapping VLAN/giaddr/link selection |
| **DHCP failover/HA** | Phối hợp nhiều DHCP server | Sai đồng bộ lease/state/split pool |
| **DHCP snooping** | Switch phân biệt DHCP message từ cổng tin cậy và không tin cậy | Thiếu bảo vệ rogue DHCP hoặc gây gián đoạn nếu trust sai |

**Reservation không phải lý do để cho thiết bị cũng tự cấu hình IP tĩnh tùy ý.** Cần một nguồn quản lý IPAM thống nhất và phân biệt rõ các dải static, dynamic và HA/VIP.

## 5. Nguyên nhân thường gặp của IP conflict

| Nhóm nguyên nhân | Tình huống minh họa | Dấu hiệu hỗ trợ |
|---|---|---|
| **Static IP trong DHCP pool** | Máy in đặt tĩnh .120, DHCP cũng cấp .120 cho laptop | IPAM/static config trái với DHCP lease |
| **Hai DHCP server không phối hợp** | Router phụ hoặc thiết bị Wi-Fi bật DHCP server ngoài ý muốn | Nhiều server identifier/offer trên cùng VLAN |
| **DHCP scope/reservation sai** | Cấu hình lease/range/exclusion chồng nhau | Scope audit, client ID và lease history |
| **Sao chép VM/thiết bị** | Image có cấu hình IP tĩnh được nhân bản | Nhiều VM cùng IP, cùng thời điểm khởi động |
| **Di chuyển VLAN/subnet** | Thiết bị giữ IP tĩnh của mạng cũ hoặc subnet mask sai | Interface config, switch port VLAN, route |
| **Địa chỉ bị dùng lại sau lease** | Client cũ giữ IP ngoài quản lý, server cấp cho client mới | Lease transition và host offline/online timeline |
| **Thiết bị IoT/printer/OT** | Gán IP thủ công nhưng không đăng ký IPAM | Không có owner/reservation chính thức |
| **HA/VIP cấu hình lỗi** | Hai node cùng nghĩ mình là active owner của VIP | HA split-brain, gratuitous ARP/NA bất thường |
| **VPN/overlapping network** | Remote network cùng CIDR với LAN khi nối tunnel | Route ambiguity, khó phân biệt site |
| **IPv6 DAD thất bại/bị bỏ qua** | Hai interface chọn cùng IPv6 địa chỉ trong một link | DAD/NS/NA logs, duplicate/tentative status |
| **Thiết bị giả mạo ARP/NDP** | Host không được phép quảng bá nó sở hữu IP của gateway | NAC/DAI/ND inspection, bất thường nguồn và hành vi |

Không nên mặc định **mọi IP conflict là tấn công**. Phần lớn tình huống quản trị IPAM/DHCP kém có thể gây lỗi giống nhau; mặt khác một hành vi cố ý giả mạo IP/MAC cũng có thể tạo xung đột hoặc **on-path interception**. Cần dựa vào bằng chứng và threat model.

## 6. Triệu chứng và mức ảnh hưởng

### 6.1. Ở máy người dùng

- Hệ điều hành hiển thị cảnh báo **duplicate IP address** hoặc không đưa IP vào sử dụng.
- Ping hoặc TCP tới một IP lúc được lúc không; cùng IP có thể phản hồi từ máy khác ở các thời điểm.
- Remote Desktop/SSH/API bị kết nối nhầm host hoặc báo lỗi chứng chỉ/hostname.
- Ứng dụng chập chờn sau khi DHCP renew, chuyển Wi-Fi/LAN hoặc VM di chuyển.
- Có hiện tượng packet retransmission, ARP entry đổi bất thường, phiên TCP bị reset.
- Hai máy đều báo “mạng ổn” khi kiểm tra gateway nhưng dịch vụ giữa chúng lỗi.

### 6.2. Ở mạng và dịch vụ

- Switch ghi nhận MAC move hoặc bảo vệ cổng kích hoạt; tuy nhiên MAC move **không đồng nghĩa** IP conflict.
- Firewall/NAC thấy cùng IP đi kèm nhiều MAC hoặc user identity khác nhau.
- DHCP server có nhiều **DHCPDECLINE** hoặc conflict alert; phải phân biệt client/lease và thời điểm.
- Một IP của gateway, DNS, VPN hoặc database bị trùng có thể gây gián đoạn trên diện rộng.
- Hệ thống ghi log theo IP gán nhầm sự kiện cho thiết bị khác, ảnh hưởng điều tra và tính toàn vẹn dữ liệu.

### 6.3. Vì sao triệu chứng có thể không ổn định?

ARP/neighbor cache và thời điểm host trả lời ảnh hưởng luồng gói. Khi một mapping thay đổi, **kết nối mới** có thể đi tới host khác, còn **kết nối đang mở** có thể mất phiên. DHCP lease và hoạt động sleep/wake cũng khiến xung đột chỉ xuất hiện trong một số khoảng thời gian.

**Không lấy kết quả ping một lần làm bằng chứng kết luận.** Một host có thể tắt phản hồi ICMP hoặc firewall chặn, nhưng vẫn đang dùng địa chỉ đó.

## 7. ARP và cơ chế phát hiện địa chỉ trùng trong IPv4

**Address Resolution Protocol (ARP)** ánh xạ IPv4 đích trong cùng link sang MAC. Một client thường giữ ánh xạ trong bảng neighbor/cache để tránh phải hỏi liên tục.

### 7.1. ARP Probe và Address Conflict Detection

RFC 5227 mô tả cơ chế **IPv4 Address Conflict Detection (ACD)** dùng ARP Probe/Announcement:

- **ARP Probe:** host kiểm tra xem một IPv4 candidate đã được dùng trên cùng link hay chưa trước khi nhận làm địa chỉ của mình.
- **ARP Announcement:** host thông báo địa chỉ nó đang sử dụng nhằm giúp các neighbor cập nhật thông tin.
- **Phát hiện xung đột:** khi thấy bằng chứng một thiết bị khác sử dụng cùng IP, implementation có thể từ chối, đổi địa chỉ hoặc xử lý theo chính sách.

Trong quy trình DHCP, **DHCPDECLINE** có thể xuất hiện khi client nhận thấy địa chỉ được server cấp đang bị dùng. Nhưng việc có hay không có DHCPDECLINE phụ thuộc **client có thực sự kiểm tra và báo lại** hay không.

### 7.2. Ví dụ dữ liệu quan sát

~~~text
VLAN:       30
IP đang điều tra: 10.24.30.120
Neighbor tại client A:
    10.24.30.120  -> 02:00:00:30:00:12
Neighbor tại client B:
    10.24.30.120  -> 02:00:00:30:00:99

DHCP lease:
    10.24.30.120  -> client laptop-12
Inventory static:
    10.24.30.120  -> printer-03
~~~

Đây là **dữ liệu giả định** gợi ý hai thực thể có thể sở hữu cùng IP. Cần xác minh thời gian các bản ghi, trạng thái host, switch port và VLAN; bảng neighbor ở những máy khác nhau có thể đã **cũ**, hoặc IP đang thuộc VIP được chuyển quyền hợp lệ.

### 7.3. Vì sao ARP spoofing có thể bị nhầm với IP conflict?

ARP spoofing/poisoning có thể phát các thông điệp ARP khiến host tin một **ánh xạ IP–MAC không đúng**. Một thiết bị không nhất thiết phải cấu hình IP đó trên interface mới có thể tạo phản hồi ARP giả.

Vì thế khi IP gateway xuất hiện ở nhiều MAC, không nên lập tức sửa địa chỉ IP của các host như khi hai máy cùng dùng IP tĩnh. Cần xem **bản chất ARP message, switch source port, NAC, DAI, quyền sở hữu IP và trạng thái gateway/HA**. Nếu nghi vấn cố ý, tuân theo quy trình ứng phó bảo mật và giữ bằng chứng.

## 8. IPv6: Neighbor Discovery và Duplicate Address Detection

IPv6 không dùng ARP. Giao thức **Neighbor Discovery (ND/NDP)** sử dụng các thông điệp **ICMPv6 Neighbor Solicitation (NS)** và **Neighbor Advertisement (NA)** để tìm neighbor và hỗ trợ **Duplicate Address Detection (DAD)**.

Khi một interface chuẩn bị dùng một địa chỉ IPv6 unicast, cơ chế DAD phù hợp sẽ xác minh **địa chỉ đó chưa được một node khác sử dụng trên cùng link**. Địa chỉ có thể đi qua trạng thái **tentative** trước khi được dùng bình thường; nếu phát hiện xung đột, host không nên sử dụng địa chỉ theo cách như thể nó duy nhất.

~~~mermaid
flowchart TD
    A[Host có IPv6 candidate] --> B[Địa chỉ ở trạng thái tentative]
    B --> C[DAD qua Neighbor Solicitation phù hợp]
    C --> D{Có bằng chứng địa chỉ đã được sử dụng?}
    D -- Có --> E[Duplicate: không đưa candidate vào sử dụng bình thường]
    D -- Không trong điều kiện DAD quy định --> F[Địa chỉ có thể trở thành usable]
    E --> G[Log/cảnh báo và chọn địa chỉ khác theo implementation]
~~~

### 8.1. Điểm khác IPv4

| Đặc tính | IPv4 | IPv6 |
|---|---|---|
| Tìm MAC neighbor | ARP | NDP (ICMPv6 NS/NA) |
| Phát hiện trùng địa chỉ | IPv4 ACD theo RFC 5227 và hành vi DHCP/OS | DAD theo RFC 4862 và các cơ chế cập nhật liên quan |
| Cấp địa chỉ | Static, DHCPv4, IPv4 link-local | Static, SLAAC, DHCPv6, IPv6 link-local |
| Có nhiều địa chỉ/interface? | Có thể | Rất phổ biến: link-local, global/ULA, temporary |
| Bảo vệ lớp 2 | DHCP snooping, Dynamic ARP Inspection (theo nền tảng) | RA Guard, IPv6 snooping/ND inspection khi thiết bị hỗ trợ |

**DHCPv6 không làm DAD trở nên không cần thiết.** Client vẫn cần xem xét việc địa chỉ IPv6 mà nó dùng có duy nhất trên link theo quy tắc triển khai.

### 8.2. IPv6 link-local giống nhau ở hai link khác nhau có sao không?

Địa chỉ dạng **fe80::/10** có ý nghĩa theo phạm vi link. Cùng giá trị có thể tồn tại ở **hai link tách biệt**, không tự là conflict. Nhưng nếu hai interface trên **cùng link** cùng chọn một địa chỉ không được phép trùng, DAD có thể phát hiện vấn đề.

### 8.3. Không chặn tất cả ICMPv6

NDP/DAD phụ thuộc ICMPv6; lọc toàn bộ ICMPv6 có thể làm IPv6 không hoạt động ổn định. Thiết kế an toàn cần **RA Guard/ND inspection theo khả năng thiết bị, xác thực nguồn và chính sách link phù hợp**, chứ không phải chặn vô điều kiện mọi NS/NA.

## 9. Trường hợp có chủ đích: Virtual IP, HA và MAC move

**Virtual IP (VIP)** thường được dùng để tạo gateway hoặc dịch vụ có tính sẵn sàng cao. Ví dụ hai router dùng **VRRP** để cung cấp default gateway 10.24.30.1. Khi chuyển vai trò, địa chỉ ảo có thể chuyển chủ sở hữu theo giao thức, đồng thời gửi thông tin giúp neighbor cập nhật.

Các hiện tượng sau **cần xem là tín hiệu để xác minh**, không tự động là lỗi:

- **Gratuitous ARP hoặc Neighbor Advertisement** khi VIP đổi node active.
- MAC/port thay đổi do **vMotion/live migration**, failover hoặc bonding/LACP thiết kế hợp lệ.
- Một địa chỉ dịch vụ được quảng bá bởi thiết kế load balancing/Anycast ở những miền routing phù hợp.
- **Proxy ARP** tạo câu trả lời ARP cho IP không cấu hình trực tiếp tại host trả lời.

### 9.1. Khi nào HA trở thành sự cố thực sự?

Nếu cơ chế điều phối bị lỗi và **hai node đồng thời cho rằng mình là chủ sở hữu duy nhất của VIP trên cùng mạng**, có thể xảy ra **split-brain**, phản hồi ARP/NDP mâu thuẫn và gián đoạn dịch vụ. Cần xem:

1. Log HA state và heartbeat/quorum.
2. Quy tắc election/priority và phiên bản cấu hình.
3. Cùng VIP có được sử dụng ở đúng VLAN/VRF không.
4. Có một hay hai node đang nhận traffic cho VIP và tại thời điểm nào.
5. Sự kiện switch port/MAC move có khớp một lần failover dự kiến hay không.

**Không tự tắt một node HA hoặc xóa VIP** chỉ vì thấy hai địa chỉ MAC trong log; hành động đó có thể làm mất gateway hoặc dịch vụ của cả hệ thống.

## 10. Thiết kế IPAM và DHCP để ngăn trùng IP

**IP Address Management (IPAM)** là nguồn quản lý tập trung về **subnet, địa chỉ IP, owner, kiểu cấp phát, vòng đời và liên hệ với thiết bị/dịch vụ**. IPAM có thể được tích hợp với DHCP/DNS hoặc đồng bộ qua hệ thống quản lý cấu hình.

### 10.1. Ví dụ quy hoạch IPv4

Giả sử mạng LAN minh họa dùng các subnet riêng:

| Zone | CIDR | Dùng cho | Ghi chú |
|---|---|---|---|
| Users / VLAN 30 | 10.24.30.0/24 | Laptop, desktop | Gateway 10.24.30.1 |
| Guest / VLAN 40 | 10.24.40.0/24 | Wi-Fi khách | Không tự có quyền vào LAN nội bộ |
| Management / VLAN 50 | 10.24.50.0/27 | Quản trị switch, firewall, jump host | Quản lý IP tĩnh/reservation chặt |
| Application / VLAN 60 | 10.24.60.0/24 | API và backend | Rule firewall giới hạn đường truy cập |

Ở **Users / VLAN 30**, một quy hoạch cụ thể:

| Dải/địa chỉ | Mục đích | Chính sách cấp phát |
|---|---|---|
| 10.24.30.0 | Network address | Không cấp cho host thông thường |
| 10.24.30.1 | Default gateway (VIP nếu có HA) | Có owner, ghi rõ cơ chế HA |
| 10.24.30.10–10.24.30.49 | Hạ tầng/thiết bị tĩnh được duyệt | Không nằm trong pool cấp động |
| 10.24.30.50–10.24.30.99 | Reservation và dự phòng theo chính sách | Phải đồng bộ với DHCP server/IPAM |
| 10.24.30.100–10.24.30.199 | Dynamic DHCP pool | Chỉ một hệ thống cấp phát có thẩm quyền hoặc HA được phối hợp |
| 10.24.30.200–10.24.30.254 | Dự phòng tăng trưởng/cấp có kiểm soát | Không tự gán IP nếu chưa đăng ký |
| 10.24.30.255 | Broadcast address IPv4 | Không cấp cho host thông thường |

Các dải chỉ là **ví dụ thiết kế**, không có nghĩa mọi tổ chức nên cấp đúng như vậy. Cần xét số host, lease thời gian thực, roaming, thiết bị tĩnh, DNS, VRF, cloud/VPN và chính sách nhà cung cấp.

### 10.2. Quy trình vòng đời IP

1. **Request:** chủ thiết bị/ứng dụng yêu cầu địa chỉ, zone và thời hạn.
2. **Allocate:** IPAM xác nhận subnet và IP chưa được cấp; tạo reservation/static record theo chuẩn.
3. **Deploy:** cấu hình DHCP/reservation/host theo đúng nguồn quản lý.
4. **Validate:** kiểm tra địa chỉ thực, VLAN, gateway, DNS và log DHCP.
5. **Monitor:** phát hiện xung đột, thiết bị mất owner, cấu hình lệch IPAM.
6. **Release/retire:** thu hồi thiết bị, cập nhật DHCP/DNS/IPAM, xem thời gian cache/lease liên quan.

**Không tạo địa chỉ tĩnh “tạm vài ngày” mà bỏ qua IPAM.** Đó là nguyên nhân phổ biến khiến DHCP sau này cấp lại đúng IP đang được một thiết bị cũ âm thầm sử dụng.

### 10.3. Ví dụ bản ghi IPAM minh họa

~~~yaml
# Hồ sơ minh họa, không phải schema của sản phẩm IPAM cụ thể.
subnet: "10.24.30.0/24"
vlan: 30
vrf: "USERS"
gateway: "10.24.30.1"
allocation_policy:
  dynamic_pool: "10.24.30.100-10.24.30.199"
  static_range: "10.24.30.10-10.24.30.49"
  reservations: "10.24.30.50-10.24.30.99"
  enforce_non_overlap: true
records:
  - ip: "10.24.30.25"
    device: "printer-03"
    allocation: "static"
    owner: "Workplace IT"
    state: "active"
  - ip: "10.24.30.120"
    device: "laptop-12"
    allocation: "dhcp"
    owner: "Endpoint Management"
    state: "active"
controls:
  review_dhcp_scope_against_ipam: true
  monitor_duplicate_ip_events: true
  audit_changes: true
~~~

Trong môi trường thật, **lease table không phải một inventory đầy đủ**: máy tĩnh không xuất hiện trong lease, địa chỉ được dùng trước khi log bắt đầu có thể không còn trace, còn một MAC có thể đổi theo chính sách privacy.

## 11. DHCP snooping, Dynamic ARP Inspection và IP Source Guard

Các biện pháp lớp 2 trên switch hỗ trợ có thể giảm IP conflict do cấu hình trái phép và một số kiểu giả mạo. Tuy nhiên chúng không thay IPAM hoặc bảo vệ mọi môi trường.

| Kiểm soát | Cách hỗ trợ | Giới hạn và rủi ro |
|---|---|---|
| **DHCP snooping** | Cho phép DHCP server messages từ các port được tin cậy; tạo binding theo lease trên thiết bị hỗ trợ | Trust uplink/relay sai có thể làm DHCP ngừng hoạt động |
| **Dynamic ARP Inspection (DAI)** | Kiểm tra ARP theo binding tin cậy/policy | Thiết bị IP tĩnh có thể bị chặn nếu không cấu hình binding/ACL phù hợp |
| **IP Source Guard** | Hạn chế frame/gói nguồn sai IP/MAC/port theo binding | Cần quản lý port, lease và ngoại lệ cho môi trường đặc thù |
| **802.1X/NAC** | Xác thực thiết bị/người dùng, gán mạng/VLAN/chính sách | Cần onboarding, fallback có kiểm soát và quản lý thiết bị IoT |
| **Port security** | Hạn chế MAC hoặc phát hiện MAC bất thường trên switch port | Không tự xác minh IP; phù hợp tùy thiết kế |
| **IPv6 RA Guard/ND inspection** | Giảm rogue RA hoặc một số thông điệp ND bất thường | Cần hỗ trợ của switch và kiểm chứng đầy đủ, không thay DAD |
| **Firewall/segmentation** | Hạn chế phạm vi mạng và đường di chuyển ngang | Lưu lượng cùng VLAN thường không đi qua firewall liên subnet |

**Điểm vận hành:** DAI dùng cơ sở binding từ DHCP snooping trong nhiều thiết kế. Với thiết bị IP tĩnh, có thể phải cung cấp **static binding/ARP ACL** đúng theo hãng; bật DAI mà không chuẩn bị sẽ khiến printer, thiết bị mạng hoặc máy chủ tĩnh mất kết nối.

### 11.1. Rogue DHCP và phân đoạn VLAN

Một router Wi-Fi cắm nhầm vào switch access và bật DHCP có thể cấp IP/gateway/DNS trái thiết kế cho client. Khi đó có thể xuất hiện **IP conflict**, nhưng cũng có thể là **sai subnet/gateway/DNS** dù không có địa chỉ trùng. Vì vậy điều tra rogue DHCP cần nhìn:

- DHCP server identifier và source switch port.
- Những **DHCPOFFER/DHCPACK** mà client đã nhận.
- DHCP relay và VLAN thực tế của port/SSID.
- Dải IP, gateway, DNS được cấp có phù hợp policy không.
- Logs từ switch DHCP snooping và NAC nếu triển khai.

Không nên kết luận “IP conflict” chỉ vì máy tính nhận sai gateway; cần chứng minh có địa chỉ trùng khi gắn nhãn nguyên nhân.

## 12. Quy trình phát hiện và thu thập bằng chứng

**Nguyên tắc:** ưu tiên quan sát trước, thay đổi sau. Với hệ thống đang hoạt động, không tự release DHCP lease, flush ARP, đổi IP hoặc shutdown port khi chưa có kế hoạch; các lệnh này có thể cắt phiên quản trị từ xa hoặc làm gián đoạn dịch vụ.

### Bước 1 — Ghi nhận triệu chứng chính xác

Thu thập:

- **IP nghi trùng**, subnet mask/prefix, gateway, VLAN, VRF và interface.
- **Thời điểm** bắt đầu (UTC hoặc timezone rõ ràng), tần suất, tác động tới ứng dụng.
- Hostname, serial/inventory ID, DHCP client identifier/MAC nếu được phép.
- Network path: Wi-Fi SSID, switch port, VLAN, VPN, cloud/VM host.
- Cảnh báo hệ điều hành, DHCPDECLINE, DAD failure, ARP changes và log switch.

### Bước 2 — Xác minh các bên liên quan

So **DHCP lease**, DHCP reservation, IPAM/static allocation, thực tế cấu hình trên host và bảng neighbor/ARP ở những thiết bị có liên quan.

### Bước 3 — Kiểm tra phạm vi lớp 2 và định tuyến

Tìm xem hai thực thể có thật sự ở **cùng VLAN/link** không. Nếu ở hai VRF/site thì có thể là **route overlap** thay vì ARP conflict. Nếu cùng VLAN nhưng một IP thuộc VIP/HA, kiểm tra chủ sở hữu active.

### Bước 4 — Xác định nguyên nhân và mức ưu tiên

Xung đột địa chỉ **gateway, DNS, VPN concentrator, domain controller, database hoặc management** cần ưu tiên cao hơn một client đơn lẻ vì diện tác động lớn. Nếu nghi IP/MAC giả mạo có chủ đích, phối hợp SOC/IR thay vì chỉ “đổi IP cho hết lỗi”.

### Bước 5 — Chỉ sửa khi đã có phương án rollback

Ghi lại cấu hình trước khi sửa, owner phê duyệt, thời điểm có thể gián đoạn và phép kiểm hồi phục. Có thể cần **kênh quản trị ngoài băng** khi đổi IP/gateway của thiết bị mạng.

## 13. Lệnh chẩn đoán trên Linux

Các lệnh dưới đây chủ yếu **đọc trạng thái** và thích hợp khi được thực hiện trên máy hoặc mạng có quyền quản trị. Không giả định mọi distro có cùng các dịch vụ DHCP/network manager.

~~~bash
# Xem tất cả IPv4/IPv6 address và interface trạng thái ngắn
ip -br address

# Xem chi tiết một interface cụ thể (thay eth0 bằng tên thật)
ip address show dev eth0

# Xem route và default gateway
ip route
ip -6 route

# Xem neighbor cache IPv4/IPv6
ip neigh show
ip neigh show dev eth0

# Xem thông tin do systemd-networkd quản lý, nếu triển khai
networkctl status eth0

# Xem log systemd-networkd trong lần khởi động hiện tại nếu có
journalctl -b -u systemd-networkd --no-pager
~~~

**Gợi ý phân tích:** nếu cùng IP có neighbor MAC thay đổi, cần đối chiếu **thời gian, log thiết bị và trạng thái HA**. Bảng neighbor là cache cục bộ có thể lỗi thời; một lần xuất hiện MAC khác không đủ chứng minh xung đột.

### 13.1. Quan sát ARP có giới hạn

Nếu điều tra viên có quyền packet capture trên interface thuộc phạm vi được phép:

~~~bash
# Chỉ xem tối đa 40 frame ARP, không phát traffic chủ động
sudo tcpdump -ni eth0 -c 40 'arp'

# Nếu cần quan sát NDP/DAD IPv6, lọc ICMPv6 ở phạm vi có phép
sudo tcpdump -ni eth0 -c 40 'icmp6'
~~~

Packet capture có thể chứa metadata mạng nhạy cảm. Chỉ thu ở thời điểm và phạm vi được duyệt, giới hạn thời gian/dung lượng và lưu chứng cứ an toàn.

**Không nên chạy lệnh probe ARP tràn lan hoặc quét toàn subnet để xác minh một IP trùng**; hành vi có thể ảnh hưởng mạng OT/IoT, tạo cảnh báo hoặc làm thay đổi cache. Phương án kiểm chứng chủ động phải được thiết kế và phê duyệt riêng.

## 14. Lệnh chẩn đoán trên Windows

Ở Windows, dùng PowerShell hoặc Command Prompt để xem cấu hình và bảng neighbor; không cần thay đổi IP trong bước quan sát.

~~~powershell
# Xem IP, interface, gateway và DNS
Get-NetIPConfiguration

# Xem danh sách IPv4/IPv6 trên máy
Get-NetIPAddress

# Xem ARP/NDP neighbor cache
Get-NetNeighbor

# Xem route và interface
Get-NetRoute

# Cấu hình DHCP trên interface theo hệ thống
Get-NetIPInterface
~~~

~~~text
REM Command Prompt
ipconfig /all
arp -a
route print
~~~

**Đọc kết quả:** phân biệt địa chỉ **DHCP**, địa chỉ cấu hình thủ công, IPv4 Automatic Private IP Addressing (**169.254.0.0/16**) khi không nhận được cấu hình phù hợp, và IPv6 link-local. Một địa chỉ **169.254.x.x** chưa chứng minh xung đột: đó còn có thể là dấu hiệu DHCP không khả dụng hoặc lỗi kết nối.

Nếu máy chủ Windows vận hành DHCP Server và có công cụ quản trị tương ứng, người có quyền có thể dùng các lệnh **read-only** của DHCP module để xem lease/scope; cú pháp phải theo phiên bản đang triển khai. Không tự xóa lease hoặc reservation trong lúc chưa xác minh quyền sở hữu IP.

## 15. Đối chiếu log DHCP, switch, NAC và IPAM

Một cuộc điều tra đáng tin cần **tương quan nhiều nguồn**, không dựa vào một cảnh báo OS đơn lẻ.

| Nguồn | Thu thập | Câu hỏi |
|---|---|---|
| **DHCP server** | Lease, client ID, server identifier, cấp mới/renew/DECLINE, scope | Server có cấp IP này cho ai và khi nào? |
| **IPAM/CMDB** | IP owner, loại cấp phát, reservation/static, lịch thay đổi | Ai có quyền dùng địa chỉ này? |
| **Switch** | MAC address table, VLAN/port, DHCP snooping, DAI events | MAC liên quan xuất hiện ở đâu? |
| **NAC/802.1X** | Auth session, thiết bị/user, gán VLAN | Thiết bị nào truy cập ở port/SSID đó? |
| **Endpoint/OS** | Interface config, ARP/NDP cache, duplicate alerts | Host thực sự cấu hình và sử dụng IP gì? |
| **Firewall/NDR/IDS** | IP–MAC/flow association nếu thấy, alert ARP spoof | Có dấu hiệu traffic đi sai nơi hoặc giả mạo không? |
| **Hypervisor/cloud** | vNIC, VM migration, ENI/interface ownership, IP assignment | VM/workload nào là owner được nền tảng công nhận? |
| **DNS** | A/AAAA, hostname, record lifecycle | Có record stale hoặc tên bị trỏ sai IP không? |

### 15.1. Ví dụ timeline minh họa

~~~text
09:01:02  DHCP server cấp 10.24.30.120 cho laptop-12
09:01:14  Client A ghi ARP 10.24.30.120 -> MAC-LAPTOP
09:01:20  Switch ghi nhận MAC-PRINTER trên VLAN 30, port 17
09:01:25  Client A ghi ARP 10.24.30.120 -> MAC-PRINTER
09:01:30  IPAM cho biết printer-03 được gán tĩnh 10.24.30.120

Giả thuyết: static IP của printer bị đặt trong dynamic DHCP pool.
Chưa kết luận: cần xác nhận printer-03 đang thực sự dùng IP đó
và đây không phải VIP/proxy ARP hoặc bản ghi cache lỗi thời.
~~~

Các mốc thời gian trong ví dụ không phải log thực tế. Trong hệ thống thật, dùng timezone nhất quán, tính đến log đến chậm và phân biệt **event time** với **ingest time**.

## 16. Kế hoạch xử lý xung đột có kiểm soát

### 16.1. Xác định một chủ sở hữu hợp lệ

Đối với mỗi IP, xác định **thiết bị/dịch vụ phải tiếp tục dùng địa chỉ**, dựa trên IPAM, dịch vụ, owner và chính sách. Nếu IP của gateway/HA, không được tự ý đổi địa chỉ. Với một printer gán sai IP trong pool DHCP, thường nên đưa nó về **dải static hợp lệ** hoặc cấp reservation được quản lý.

### 16.2. Ưu tiên sửa nguyên nhân cấp phát

| Nguyên nhân đã được xác nhận | Hướng sửa | Điều cần tránh |
|---|---|---|
| Static IP nằm trong dynamic pool | Cấp lại static ngoài pool hoặc exclude IP theo thiết kế, đồng bộ IPAM/DNS | Chỉ renew laptop nhưng giữ pool sai |
| Hai DHCP servers cùng cấp địa chỉ | Loại rogue server hoặc cấu hình failover/split đúng, kiểm tra relay | Tắt nhầm DHCP server chính gây gián đoạn toàn VLAN |
| Reservation/client ID sai | Sửa IPAM/reservation, quản lý lease lifecycle | Xóa lease của client đang hoạt động khi chưa có kế hoạch |
| VM clone giữ IP tĩnh | Cấp IP hợp lệ cho từng VM, rà soát template và provisioning | Dùng cùng một template IP tĩnh cho mọi instance |
| HA/VIP split-brain | Khôi phục election/quorum và quyền sở hữu VIP | Tắt cả hai node hoặc thay VIP tùy tiện |
| IPv6 DAD failure | Kiểm tra address generation, link scope, DHCPv6/SLAAC/static config | Vô hiệu hóa DAD để “hết lỗi” |
| Rogue ARP/NDP | Theo IR: giữ bằng chứng, xác thực thiết bị, áp NAC/inspection phù hợp | Chỉ xóa ARP cache mà không xử lý nguồn giả mạo |
| CIDR overlap qua VPN/cloud | Renumber hoặc thiết kế NAT/VRF/route có kiểm soát | Đổi một IP ngẫu nhiên và coi là giải quyết hết route ambiguity |

### 16.3. Trật tự xử lý thực tế

1. **Xác minh owner và phạm vi ảnh hưởng**; phân biệt dữ liệu cũ với thiết bị đang hoạt động.
2. **Giữ bằng chứng:** lease, IPAM record, switch port, log DAD/ARP, change events.
3. **Chặn tái cấp sai:** sửa DHCP scope/exclusion hoặc rogue DHCP sau khi hiểu đường mạng.
4. **Sửa thiết bị không có quyền dùng IP:** cấp địa chỉ hợp lệ, subnet/gateway/DNS phù hợp, cập nhật IPAM.
5. **Điều chỉnh cache/neighbor khi cần và có phê duyệt:** có thể phải đợi cache hết hạn, cập nhật mapping bằng giao thức phù hợp, hoặc thực hiện refresh tại điểm được phép.
6. **Kiểm tra chiều đi/về:** route, DNS, host firewall, HTTPS/TLS, ứng dụng, switch/NAC và các luồng bị ảnh hưởng.
7. **Quan sát tái diễn:** lease renew, sleep/wake, roaming, HA failover hoặc restart của thiết bị từng gây lỗi.

**Tránh can thiệp trên production trước khi thu bằng chứng.** Lệnh như **ipconfig /release**, **ipconfig /renew**, flush ARP/neighbor, thay gateway hoặc shutdown switch port **làm thay đổi trạng thái mạng**, có thể cắt kết nối của chính người đang quản trị từ xa. Chỉ thực hiện trong kế hoạch xử lý có owner, impact assessment và rollback.

## 17. IPv4 và IPv6 trong cloud, VPN, Wi-Fi và container

### 17.1. Cloud VPC/VNet

Nhiều nền tảng cloud quản lý chặt quyền sở hữu private IP của **virtual network interface**, nên xung đột dạng ARP truyền thống có thể ít xuất hiện hoặc mạng ảo không trình bày ARP giống Ethernet LAN. Tuy vậy vẫn có rủi ro:

- IP được đăng ký sai trong **IPAM, DNS, service discovery hoặc application configuration**.
- Hai site/VPC sử dụng **CIDR chồng lấn** rồi cố kết nối bằng peering/VPN/transit.
- Thay private IP/ENI, restore VM image hoặc provisioning sai khiến service trỏ đến IP đã chuyển owner.
- Hai workload tự cho rằng mình sở hữu cùng IP ở tầng overlay, container hoặc tunnel do cấu hình ngoài cơ chế cấp phát của nền tảng.

Khi xử lý, ưu tiên **API/control plane của provider, interface ownership, subnet/route table và audit logs**. Đừng giả định có thể sniff ARP toàn VPC hoặc dùng mọi lệnh lớp 2 từ máy ảo để chứng minh xung đột.

### 17.2. VPN và mạng đối tác

Nếu laptop ở nhà dùng subnet **192.168.1.0/24** và mạng doanh nghiệp cũng dùng subnet đó, client có thể định tuyến traffic về LAN tại nhà thay vì tunnel VPN hoặc ngược lại. Đây thường là **overlapping CIDR/routing issue**, không nhất thiết có hai host cùng lớp 2.

Giải pháp có thể gồm thay địa chỉ dải nội bộ, split tunnel/split DNS đúng, route cụ thể, NAT có kiểm soát hoặc chính sách truy cập dựa trên dịch vụ thay vì truy cập toàn subnet. Phải đo ảnh hưởng tới ứng dụng và mạng đối tác trước khi thay đổi.

### 17.3. Wi-Fi, DHCP và roaming

Mạng Wi-Fi corporate/guest/IoT nên có **SSID–VLAN mapping** rõ. Một client chuyển giữa SSID/VLAN nhưng giữ IP cũ, hoặc AP/router khách bật DHCP không phù hợp, có thể gây lỗi kết nối và đôi khi trùng IP.

**MAC randomization** trên thiết bị di động có thể thay đổi DHCP client identity được server quan sát. Điều này không đồng nghĩa IP conflict; cần đối chiếu lease, thời điểm và cơ chế nhận diện của hệ thống NAC.

### 17.4. Container và Kubernetes

Trong Kubernetes, CNI/IPAM thường phân bổ IP cho pod theo mô hình mạng. Pod IP có thể đổi khi workload được thay thế; Service IP và địa chỉ node có vai trò riêng. Các lỗi gán IP, trạng thái CNI stale hoặc overlay sai có thể gây route/endpoint không nhất quán. **Không kết luận đây là LAN IP conflict chỉ vì hai log ứng dụng hiển thị một địa chỉ**: có thể là địa chỉ NAT/proxy, cluster khác hoặc network namespace tách biệt.

Điều tra theo **cluster, namespace, node, CNI allocation, workload UID và thời điểm**; không tự xóa IPAM state trong cluster khi chưa có quy trình của nền tảng.

## 18. IP conflict là vấn đề bảo mật hay vận hành?

IP conflict thường được phát hiện như sự cố **availability**, nhưng có tác động tới bảo mật:

| Trụ cột | Rủi ro |
|---|---|
| **Availability** | Mất kết nối, lỗi DNS/SSH/API, gián đoạn gateway hoặc máy chủ |
| **Integrity** | Gói đến nhầm thiết bị, hệ thống xác định sai chủ sở hữu IP |
| **Confidentiality** | Nếu traffic bị chuyển đến thiết bị không tin cậy và ứng dụng không xác thực đích đúng, có thể rò dữ liệu |
| **Accountability** | Logs gắn IP với sai user/device khiến điều tra và chính sách sai lệch |

Một host cố ý giả mạo ARP có thể tạo đường **on-path**; một rogue DHCP server có thể cấp gateway/DNS do bên khác kiểm soát. Vì vậy ngoài sửa IP trùng, đội bảo mật cần xem liệu có dấu hiệu **cố ý chiếm địa chỉ, chuyển hướng traffic hoặc né phân đoạn/NAC**.

### 18.1. Không dùng IP như danh tính người dùng duy nhất

IP có thể tái cấp, NAT, cùng tồn tại sau proxy, là VIP hoặc bị cấu hình sai. Rule firewall theo IP vẫn có ích trong phân đoạn, nhưng khi cần phân quyền ứng dụng phải kết hợp **xác thực, chứng chỉ, IAM, VPN/ZTNA và ngữ cảnh thiết bị**. Logs phục vụ điều tra nên giữ cả IP, thời điểm lease, MAC/port hoặc identity đã xác thực khi được phép.

### 18.2. Kết hợp các lớp phòng vệ

- **Network segmentation:** giảm phạm vi ảnh hưởng giữa VLAN/subnet; cùng VLAN vẫn có thể gặp IP conflict.
- **Firewall:** chặn luồng liên zone trái phép, nhưng firewall tại gateway có thể không thấy ARP trong cùng VLAN.
- **IDS/IPS/NDR:** phát hiện ARP bất thường/thiết bị lạ khi sensor có độ phủ.
- **802.1X/NAC, DHCP snooping, DAI, IP Source Guard:** hạn chế nguồn cấp phát/gói lớp 2 trái phép theo khả năng switch.
- **VPN và cloud IPAM:** tránh CIDR overlap và quản lý chủ sở hữu IP ở đường kết nối xa.
- **DNS security:** ngăn dữ liệu DNS sai/stale làm trầm trọng hơn nhầm lẫn chủ sở hữu IP.
- **Wi-Fi security:** xác thực SSID/thiết bị, cấu hình gán VLAN và DHCP đúng.

## 19. Tình huống thực hành: printer tĩnh trùng lease DHCP

### 19.1. Bối cảnh

VLAN Users **10.24.30.0/24** có DHCP pool **10.24.30.100–10.24.30.199**. Một máy in được cấu hình thủ công **10.24.30.120** mà không cập nhật IPAM. Một laptop mới nhận DHCP lease cho **10.24.30.120**, sau đó mất kết nối lúc in và xuất hiện cảnh báo IP trùng.

### 19.2. Diễn biến

~~~mermaid
sequenceDiagram
    autonumber
    participant P as Printer (static .120)
    participant S as DHCP server
    participant L as Laptop
    participant N as Client/Neighbor trên LAN
    P->>N: Printer dùng IP .120
    L->>S: Xin IP qua DHCP
    S-->>L: Cấp lease .120 do IPAM chưa đăng ký static
    L->>N: Laptop bắt đầu dùng hoặc kiểm tra .120
    P->>N: ARP/traffic với .120
    L->>N: ARP/traffic với .120
    N-->>L: Luồng hoặc cảnh báo bất thường
~~~

**Giới hạn của ví dụ:** một client có triển khai conflict detection tốt có thể phát hiện địa chỉ đã dùng và gửi DHCPDECLINE, không nhất thiết bắt đầu dùng IP rồi mới lỗi. Đây là một kịch bản để giải thích nguyên nhân, không phải hành vi bắt buộc của mọi hệ điều hành.

### 19.3. Hướng điều tra

1. Xác minh **subnet/VLAN**, cả hai thiết bị có cùng link và hiện vẫn hoạt động.
2. Xem lease của DHCP server, client ID/MAC, thời điểm cấp và thông số gateway/DNS.
3. Xem IP tĩnh trên printer, owner và bản ghi IPAM.
4. Kiểm tra ARP/neighbor mapping và switch port để chắc không phải VRRP/HA/proxy ARP.
5. Xác nhận phạm vi tác động (chỉ laptop/printer hay nhiều client).

### 19.4. Khắc phục

Đưa printer sang địa chỉ **được cấp phát chính thức ngoài pool**, hoặc thay mô hình sang reservation được quản lý, cập nhật DNS/IPAM. Sau đó quản lý vòng đời lease của laptop và kiểm tra kết nối. Không tự xóa lease khỏi server khi laptop còn đang dùng IP mà chưa có kế hoạch; phải xử lý **cả hai đầu sử dụng IP**.

### 19.5. Phòng tái diễn

Tạo quy định thiết bị tĩnh phải đăng ký IPAM, audit scope/exclusion định kỳ, kiểm tra provisioning printer/IoT và giám sát DHCP conflict. Khi một subnet được mở rộng hoặc đổi dải DHCP, chạy kiểm tra overlap với toàn bộ static/reservation trước khi triển khai.

## 20. Tình huống khác cần phân biệt

### Tình huống A — Hai DHCP server trả offer trên cùng VLAN

Người dùng nhận gateway/DNS khác nhau và đôi khi cùng địa chỉ IP. Điều tra bằng server identifier, DHCP snooping logs, switch port và relay configuration. **Không tắt server thứ hai trước khi biết đó là rogue hay thành phần failover hợp lệ**.

### Tình huống B — Xung đột IPv6 sau cấu hình tĩnh

Hai máy trong cùng link được gán cùng IPv6 unicast. Hệ điều hành báo DAD failure/tentative address không hoạt động. Kiểm tra NS/NA, interface, prefix và nguồn cấu hình static/DHCPv6/SLAAC, sau đó sửa nguồn gán địa chỉ; không vô hiệu hóa DAD.

### Tình huống C — Mạng VPN trùng 192.168.1.0/24

Laptop tại nhà và LAN doanh nghiệp cùng subnet; ứng dụng nội bộ không truy cập được dù DHCP hoạt động bình thường. Xem route trên client và tunnel, kiểm tra split DNS và dải mạng hai đầu. Đây chủ yếu là **routing overlap**, không nhất thiết phải điều tra ARP conflict tại văn phòng.

### Tình huống D — Gateway VIP thay đổi MAC

Sau failover VRRP, neighbor entry cho gateway thay MAC và switch ghi MAC move. Nếu HA election đúng, đây có thể là **sự kiện bình thường**. Chỉ điều tra conflict thật khi có dấu hiệu hai node đồng thời giữ VIP, gói đi sai hoặc ứng dụng mất kết nối.

### Tình huống E — VM clone cùng IP tĩnh

Một bản VM template chứa IPv4 tĩnh được dùng để triển khai nhiều VM vào cùng subnet. Hai VM khởi động cùng lúc tạo xung đột. Sửa template/provisioning, cấp IP độc lập qua IPAM/DHCP/reservation và kiểm tra cả địa chỉ IPv6 tĩnh nếu có.

### Tình huống F — IP vừa được giải phóng nhưng dịch vụ vẫn sai

IPAM/DHCP cho thấy chỉ một owner, nhưng user vẫn bị chuyển nhầm. Kiểm tra **ARP stale, DNS A/AAAA stale, load balancer pool, application cache và TTL** trước khi kết luận IP conflict còn tồn tại.

## 21. Ma trận kiểm thử và xác minh sau khắc phục

Các phép kiểm nên thực hiện tại **mạng/thiết bị được cấp phép**, ưu tiên đọc trạng thái và chạy probe nhỏ đã được phê duyệt. Chỉ kết luận hoàn thành khi cả kết nối nghiệp vụ và nguồn quản lý địa chỉ đều nhất quán.

| Test | Kịch bản | Kết quả mong đợi | Bằng chứng |
|---|---|---|---|
| T-01 | DHCP client trên VLAN Users nhận IP | Trong pool hợp lệ, không overlap static/reservation | Lease, IPAM, interface config |
| T-02 | Printer/IoT cấu hình tĩnh | IP thuộc dải được cấp, không bị DHCP tái cấp | IPAM, DHCP exclusions, thiết bị |
| T-03 | Hai DHCP servers HA hợp lệ | Lease và scope phối hợp nhất quán | Failover status, lease logs |
| T-04 | Rogue DHCP được mô phỏng an toàn trong lab | Port không được tin cậy không thể phát hành lease trái phép | DHCP snooping logs |
| T-05 | ARP mapping cho IP vừa xử lý | Khớp owner thực, không biến động ngoài dự kiến | Neighbor table, switch port |
| T-06 | Gateway HA failover theo kế hoạch | VIP vẫn hoạt động, không có split-brain | HA events, route, ARP/NA |
| T-07 | IPv6 DAD trong lab với cấu hình hợp lệ | Địa chỉ trở thành usable, không có duplicate errors | IPv6 interface/DAD logs |
| T-08 | Thiết bị có IP tĩnh dưới DAI/IP Source Guard | Hoạt động nhờ binding/policy chính xác | Binding table, permit/deny logs |
| T-09 | VPN nối mạng đối tác/cloud | CIDR không chồng lấn hoặc có giải pháp route/NAT được duyệt | IPAM toàn hệ thống, route tests |
| T-10 | Wi-Fi corporate và guest | Đúng VLAN, DHCP scope và quyền truy cập | SSID/VLAN, DHCP options, firewall |
| T-11 | DNS A/AAAA sau đổi IP | Trỏ đúng owner theo TTL/chính sách | Authoritative DNS, client cache |
| T-12 | Ứng dụng tới IP vừa khắc phục | Kết nối và xác thực đích đúng, không chỉ ping thành công | TLS/SSH fingerprint theo quy trình, app logs |
| T-13 | Sau renew/reboot/roaming dự kiến | Xung đột không tái diễn | DHCP/OS logs, monitoring |
| T-14 | Hệ thống cảnh báo IP conflict | Có owner xử lý, phân biệt HA/VIP với lỗi thật | Alert/ticket và log tương quan |

## 22. Những sai lầm thường gặp

| Ngộ nhận hoặc lỗi | Hậu quả | Cách làm đúng |
|---|---|---|
| “Hai thiết bị khác VLAN có cùng IP chắc chắn conflict.” | Điều tra sai phạm vi | Kiểm tra link/VRF/route; phân biệt overlap với duplicate host IP |
| “ARP thay MAC là do có attacker.” | Báo động sai khi HA hoặc VM migration | Kiểm tra VIP, failover, switch và owner |
| “DHCP đã bật thì không thể trùng IP.” | Bỏ sót static, rogue server và lease lỗi | IPAM, scope exclusions, snooping, audit |
| “Ping thành công là IP không trùng.” | Một host trong số nhiều host có thể phản hồi | Đối chiếu MAC/port/lease và triệu chứng theo thời gian |
| “Ping timeout nghĩa là IP conflict.” | Có thể do firewall, routing hoặc host offline | Xác minh config, neighbor và log |
| “Xóa ARP cache là sửa tận gốc.” | Mapping xấu có thể quay lại | Sửa nguồn cấp IP, host, ARP spoof hoặc HA |
| “Chỉ cần đổi địa chỉ laptop.” | Printer tĩnh vẫn ở DHCP pool, conflict tái diễn | Sửa allocation policy và IPAM |
| “Bật DAI cho mọi VLAN là an toàn ngay.” | Thiết bị static có thể mất kết nối | Chuẩn bị binding/ACL và test |
| “IP là danh tính ổn định của người dùng.” | Audit và phân quyền có thể sai khi lease đổi/NAT | Kết hợp identity, lease time và thiết bị |
| “IPv6 không thể có duplicate address.” | Lỗi DAD/ND bị bỏ qua | Kiểm tra SLAAC/DHCPv6/static và ND |
| “Cloud không có ARP nên không có lỗi địa chỉ.” | Bỏ qua overlap, IPAM/control-plane và overlay | Kiểm tra giao diện ảo, route, IPAM và DNS |
| “Đổi IP gateway từ xa là thao tác nhỏ.” | Nguy cơ mất toàn bộ quản trị hoặc outage | Kế hoạch bảo trì, out-of-band access và rollback |

## 23. Checklist vận hành DHCP và IP management

- [ ] Có IPAM làm nguồn quản lý tập trung cho mọi subnet, VRF, site, VPC/VNet, VPN và owner.
- [ ] Ghi rõ static IP, reservation, dynamic pool, gateway/VIP, exclusion và dải dự phòng.
- [ ] DHCP scopes không chồng với IP tĩnh/reservation hoặc với DHCP server không được phối hợp.
- [ ] DHCP failover/HA, relay, server identifier và VLAN mapping được kiểm tra khi thay cấu hình.
- [ ] Thiết bị IoT/printer/OT và server tĩnh phải đăng ký owner và địa chỉ chính thức.
- [ ] Theo dõi DHCPDECLINE, client duplicate warnings, IPv6 DAD failure và ARP/ND anomalies.
- [ ] Áp DHCP snooping, DAI, IP Source Guard, NAC nơi thích hợp và test thiết bị IP tĩnh.
- [ ] Phân biệt ARP spoofing, stale ARP, VIP/HA, VM migration và IP conflict thực sự.
- [ ] Kiểm tra cả IPv4 và IPv6; không chặn toàn bộ ICMPv6 làm ảnh hưởng NDP/DAD.
- [ ] Gắn log IP–MAC–switch port–VLAN–lease time với identity và quyền truy cập khi phù hợp.
- [ ] Có quản trị MAC randomization trên Wi-Fi và thiết bị di động không làm sai chính sách nhận diện.
- [ ] Xác minh IPAM giữa on-prem, cloud, VPN/SD-WAN và đối tác để tránh overlapping CIDR.
- [ ] Cập nhật DNS A/AAAA và service discovery khi địa chỉ/owner thay đổi.
- [ ] Có runbook lưu bằng chứng, cô lập nguyên nhân, sửa cấu hình, kiểm chứng và rollback.
- [ ] Không thay lease/IP/ARP hoặc shutdown port production mà thiếu owner và đánh giá tác động.
- [ ] Có kiểm thử DHCP renew, host reboot, Wi-Fi roaming, HA failover và VM deployment.
- [ ] Review những cảnh báo duplicate có false positive để không bỏ sót sự cố thật.

## 24. Câu hỏi tự kiểm tra

**1. Thế nào là IP conflict thực sự?**  
Hai hoặc nhiều thực thể đồng thời sử dụng một địa chỉ trong phạm vi địa chỉ phải là duy nhất, gây mơ hồ khi chuyển traffic đến đúng đích. Cùng IP trong hai mạng hoàn toàn tách biệt không tự là conflict.

**2. Vì sao static IP nằm trong DHCP pool là nguy cơ lớn?**  
Vì DHCP server có thể không biết địa chỉ do một host tự cấu hình, sau đó cấp cùng IP cho client khác.

**3. DHCPDECLINE có nghĩa gì?**  
Client báo địa chỉ được đề xuất/cấp không thể sử dụng, chẳng hạn do phát hiện conflict. Không phải mọi hệ điều hành hay mọi lỗi đều tạo DHCPDECLINE.

**4. Vì sao hai MAC trả lời cho một IP chưa đủ kết luận có hai host cấu hình trùng IP?**  
Có thể do HA/VIP, proxy ARP, stale neighbor, failover hoặc giả mạo ARP. Cần xem switch port, chủ sở hữu, trạng thái và thời gian.

**5. DAD trong IPv6 làm nhiệm vụ gì?**  
Kiểm tra địa chỉ IPv6 candidate chưa được node khác sử dụng trong cùng link trước khi đưa vào sử dụng bình thường theo quy tắc triển khai.

**6. Vì sao mạng tại nhà và mạng công ty cùng 192.168.1.0/24 gây lỗi VPN nhưng không hẳn là xung đột ARP?**  
Vì hai LAN tách biệt; vấn đề xuất hiện khi route đến cùng prefix trở nên mơ hồ hoặc chọn sai next hop qua VPN.

**7. DHCP snooping và DAI khác nhau như thế nào?**  
DHCP snooping giúp kiểm soát nguồn thông điệp DHCP và tạo binding; DAI có thể kiểm tra ARP theo binding/policy. DAI phải được thiết kế cho host dùng IP tĩnh.

**8. Vì sao không nên chạy ipconfig /release trên máy quản trị từ xa ngay khi nghi conflict?**  
Nó có thể làm máy mất địa chỉ/đường kết nối, khiến người quản trị không còn truy cập được và chưa chắc sửa nguyên nhân.

**9. Khi đã đổi IP cho printer, vì sao vẫn phải kiểm tra DNS và IPAM?**  
Vì tên máy có thể còn trỏ tới IP cũ và DHCP vẫn có thể cấp sai nếu pool/reservation chưa được sửa; thay đổi cần đồng bộ toàn vòng đời.

**10. IP conflict có thể là tín hiệu an ninh không?**  
Có. ARP/NDP spoofing hoặc rogue DHCP có thể làm traffic tới sai thiết bị. Nhưng cần bằng chứng phân biệt với lỗi vận hành thường gặp.

## 25. Tài liệu tham khảo

- [RFC 2131 — Dynamic Host Configuration Protocol](https://www.rfc-editor.org/rfc/rfc2131): cấp lease IPv4 DHCP và các thông điệp như DHCPDECLINE.
- [RFC 5227 — IPv4 Address Conflict Detection](https://www.rfc-editor.org/rfc/rfc5227): ARP Probe/Announcement và cơ chế phát hiện xung đột IPv4.
- [RFC 826 — An Ethernet Address Resolution Protocol](https://www.rfc-editor.org/rfc/rfc826): cơ chế ARP ánh xạ IPv4 tới Ethernet MAC.
- [RFC 4861 — Neighbor Discovery for IP version 6 (IPv6)](https://www.rfc-editor.org/rfc/rfc4861): IPv6 NS/NA và neighbor cache.
- [RFC 4862 — IPv6 Stateless Address Autoconfiguration](https://www.rfc-editor.org/rfc/rfc4862): SLAAC và Duplicate Address Detection.
- [RFC 8415 — Dynamic Host Configuration Protocol for IPv6 (DHCPv6)](https://www.rfc-editor.org/rfc/rfc8415): mô hình DHCPv6, DUID/IAID và cấp địa chỉ.
- [RFC 5798 — Virtual Router Redundancy Protocol (VRRP) Version 3](https://www.rfc-editor.org/rfc/rfc5798): virtual routers/gateway HA, điểm cần phân biệt với xung đột IP trái phép.
- [RFC 1918 — Address Allocation for Private Internets](https://www.rfc-editor.org/rfc/rfc1918): các dải IPv4 private, dùng lại được khi các mạng tách biệt.
- [NIST SP 800-41 Rev. 1 — Guidelines on Firewalls and Firewall Policy](https://csrc.nist.gov/pubs/sp/800/41/r1/final): chính sách firewall và phân đoạn liên quan đến quản lý địa chỉ.
- [NIST SP 800-207 — Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final): giới hạn việc tin cậy danh tính chỉ dựa vào vị trí/IP.

**Ghi nhớ:** IP conflict không chỉ là “hai máy có cùng địa chỉ” trên giấy: phải xác định **cùng phạm vi liên kết/định tuyến, cùng thời điểm và đúng chủ sở hữu được phép sử dụng IP**. Phòng ngừa hiệu quả đòi hỏi **DHCP được phối hợp, IPAM có owner, kiểm soát ARP/NDP và lớp 2, quản lý VIP/HA, cùng quy trình thay đổi an toàn**. Khi điều tra, hãy giữ bằng chứng, phân biệt conflict với route overlap hoặc cache cũ, **sửa nguồn cấp phát sai** rồi mới xác minh kết nối và giám sát tái diễn.
