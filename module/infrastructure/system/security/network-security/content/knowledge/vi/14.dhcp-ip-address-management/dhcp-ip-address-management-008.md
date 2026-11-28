# Network inventory: kiểm kê tài sản mạng, địa chỉ IP và quan hệ kết nối

**Network inventory (kiểm kê mạng)** là tập hợp dữ liệu có cấu trúc về những tài sản, giao diện, địa chỉ, dịch vụ, vùng mạng, đường kết nối và người chịu trách nhiệm trong một hệ thống. Đó không chỉ là “danh sách IP đang ping được”, mà là khả năng trả lời có bằng chứng: **thiết bị nào đang ở đâu, dùng địa chỉ nào vào thời điểm nào, thuộc quyền ai, kết nối tới những vùng nào và được phép cung cấp dịch vụ gì?**

Trong chương **DHCP và IP management** của học phần **SECURITY_NETWORK_SECURITY**, network inventory giúp quản lý vòng đời cấp phát IPv4/IPv6, DHCP, DNS và IPAM; đồng thời là nền tảng cho phân đoạn, firewall, VPN, IDS/IPS, NAC/802.1X, bảo vệ Wi-Fi, cloud security và phân tích mối đe dọa. Nếu không biết tài sản và địa chỉ thật sự thuộc về ai, đội bảo mật khó thiết kế rule chính xác hoặc truy vết một sự kiện theo thời gian.

Bài này xây dựng cách tư duy từ mô hình dữ liệu tới thu thập, đối soát, kiểm chứng, quản lý thay đổi và sử dụng inventory trong điều tra an ninh. Các ví dụ dùng địa chỉ private hoặc dải tài liệu minh họa; những lệnh quan sát chỉ dành cho hệ thống do người học sở hữu hay được cấp quyền quản trị.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt **network inventory**, **asset inventory**, **IP Address Management (IPAM)**, **DHCP**, **DNS** và **CMDB**.
2. Đề xuất các trường thông tin đủ để quản lý thiết bị, interface, VLAN/subnet, IP, lease, hostname, owner và trạng thái vòng đời.
3. Giải thích vì sao quan hệ **IP ↔ thiết bị ↔ người dùng** thay đổi theo thời gian, đặc biệt với DHCP, VPN, Wi-Fi, NAT và cloud.
4. Xây quy trình kết hợp dữ liệu từ DHCP, DNS, switch/router, NAC, EDR, firewall, VPN, IPAM và API cloud.
5. Phân biệt địa chỉ **được khai báo**, **được cấp phát**, **được quan sát** và **được xác minh**, tránh kết luận từ một nguồn đơn lẻ.
6. Thiết kế kiểm tra đối soát để tìm tài sản không có owner, IP trùng, DNS lệch, lease cũ, rule chưa có căn cứ và thiết bị ngoài chính sách.
7. Áp dụng inventory vào phát hiện bất thường, threat modeling, phân đoạn east–west, quản trị firewall và ứng phó sự cố.
8. Thực hiện một số thao tác xem thông tin mạng cục bộ không gây tải và xây checklist duy trì dữ liệu.

## 2. Network inventory là gì và không phải là gì?

Một network inventory có thể gồm thiết bị vật lý, máy ảo, container, workload cloud, firewall, switch, access point, load balancer, DNS resolver, subnet, VLAN, VPN endpoint và những dịch vụ mạng quan trọng.

Tuy nhiên **đơn vị kiểm kê không nhất thiết phải là một IP**. Một máy có nhiều NIC/IP; một IP ảo phục vụ nhiều backend; một workload đổi IP khi được tạo lại; một địa chỉ NAT đại diện hàng trăm client. Do đó inventory tốt tách **đối tượng**, **thuộc tính** và **mối quan hệ theo thời gian**.

### 2.1. Các hệ thống dễ bị nhầm lẫn

| Khái niệm | Câu hỏi chính | Thông tin thường quản lý | Giới hạn nếu chỉ dùng riêng |
|---|---|---|---|
| **Network inventory** | Trong mạng có tài sản, interface và kết nối nào? | Device, NIC, IP, VLAN, zone, vị trí, trạng thái, owner | Có thể thiếu cấu hình nghiệp vụ hoặc nguồn quyền sở hữu |
| **Asset inventory** | Tổ chức sở hữu/quản trị tài sản nào? | Serial, model, OS, chủ sở hữu, vòng đời, độ nhạy | Không luôn cập nhật IP và đường kết nối thực |
| **IPAM** | Prefix/subnet/IP nào đã được phân bổ, giữ chỗ hoặc đang sử dụng? | Prefix, address, reservation, subnet owner, VRF, trạng thái | Một bản ghi IPAM chưa chứng minh host có mặt |
| **DHCP** | IP được cấp cho client nào, trong khoảng thời gian nào? | Lease, pool, client ID, MAC/DUID, thời hạn | Lease có thể tồn tại khi máy đã rời mạng |
| **DNS** | Tên nào phân giải ra bản ghi nào? | A/AAAA, CNAME, PTR, TXT, TTL, zone | DNS record có thể cũ, alias không phải danh tính tài sản |
| **CMDB** | Configuration Item nào có quan hệ với hệ thống/nghiệp vụ? | CI, service owner, environment, dependency, change | Có thể không thấy endpoint xuất hiện tự phát |
| **NAC/802.1X** | Thiết bị hoặc tài khoản nào được tham gia mạng? | Identity, posture, VLAN/role, authentication session | Thành công xác thực không chứng minh đã dùng dịch vụ nào |
| **Discovery/telemetry** | Hệ thống đã quan sát những gì? | L2 neighbor, flow, interface, ARP/ND, hostname, process | Một dấu hiệu quan sát không luôn xác nhận chính xác identity |

**Giá trị của inventory nằm ở việc liên kết các nguồn.** DHCP biết ai được cấp IP theo hợp đồng lease; switch biết thiết bị xuất hiện ở cổng; NAC biết phiên xác thực; EDR có thể biết host ID; firewall thấy luồng; CMDB/IPAM giúp giải thích vai trò và mức độ được phê duyệt.

### 2.2. Bốn trạng thái cần phân biệt

- **Planned/allocated:** địa chỉ hoặc prefix được thiết kế/giữ chỗ cho một nhóm, chưa chắc đã có thiết bị.
- **Assigned/leased:** hệ thống cấp phát ghi nhận một client đang có quyền dùng địa chỉ trong một khoảng thời gian.
- **Observed:** nguồn telemetry thấy một địa chỉ, MAC hoặc luồng vào thời điểm cụ thể.
- **Verified/approved:** đã đối chiếu với owner, cấu hình hay nguồn tin cậy để xác nhận tài sản và mục đích được phép.

Một địa chỉ được phân bổ trong IPAM, có lease DHCP và xuất hiện trong flow logs chưa mặc định có **người dùng** xác định nếu không có dữ liệu về VPN/NAC/endpoint tại cùng thời điểm.

## 3. Mô hình dữ liệu: tài sản, interface, địa chỉ, mạng và dịch vụ

Một mô hình bền vững nên có **ID ổn định** cho đối tượng và các bảng quan hệ thay vì chỉ giữ một file “IP → hostname”.

~~~mermaid
flowchart LR
    ASSET[Tài sản / workload ID] --> IF[Interface / NIC]
    IF --> IP[IP assignment hoặc lease]
    IP --> NET[Prefix / subnet / VRF]
    IF --> L2[Switch port / Wi-Fi AP / VLAN]
    ASSET --> OWN[Owner / service / business role]
    ASSET --> SVC[Dịch vụ / listener]
    ASSET --> SEC[Security zone / policy]
    IP --> DNS[DNS record A/AAAA/PTR]
    ASSET --> EV[Observation / evidence]
    EV --> TIME[Observed_at / validity interval]
~~~

### 3.1. Các lớp thực thể

| Thực thể | Trường nên có | Ví dụ ý nghĩa |
|---|---|---|
| **Asset/Workload** | asset_id, loại, tên, owner, environment, criticality, lifecycle | VM chạy API trong production |
| **Interface** | interface_id, asset_id, MAC nếu có, network attachment, trạng thái | NIC ảo của VM hoặc cổng LAN |
| **IP assignment** | address, IP version, scope/VRF, interface, nguồn cấp, thời gian hiệu lực | IPv4 DHCP được thuê từ pool Staff |
| **Prefix/Subnet** | CIDR, VLAN, VRF/VPC, gateway, DHCP scope, zone, chủ quản | 10.40.20.0/24 thuộc Staff |
| **L2 connection** | switch/AP, port, SSID, VLAN, thời gian quan sát | Máy đang qua AP trong Guest VLAN |
| **DNS record** | zone, name, record type, value, TTL, owner | app.corp.example → private IP |
| **Service/Endpoint** | service_id, protocol/port, exposure, identity, backend | API TCP/443 có load balancer |
| **Identity/Session** | user/workload ID, NAC/VPN session, start/end | Người dùng xác thực với WLAN |
| **Evidence/Source** | nguồn, event ID, observed_at, ingested_at, confidence | DHCP ACK và log cổng switch |

**Một MAC không phải ID toàn cục bất biến**: NIC thay, máy ảo nhân bản, Wi-Fi MAC randomization hoặc công nghệ ảo hóa có thể làm địa chỉ này thay đổi. IP cũng không bất biến. Tài sản nên có một ID hệ thống được quản trị và các identifier khác được lưu thành quan hệ có mốc thời gian.

### 3.2. Mô hình record minh họa

Đây là **YAML biểu diễn dữ liệu inventory**, không phải cấu hình import bắt buộc của một sản phẩm IPAM hoặc CMDB:

~~~yaml
asset:
  asset_id: "asset-app-vm-042"
  type: "virtual-machine"
  display_name: "order-api-02"
  environment: "production"
  owner_team: "orders-platform"
  business_service: "order-api"
  criticality: "high"
  lifecycle_state: "active"
  managed: true

network:
  routing_domain: "corp-prod-vrf"
  segment: "app-vlan-20"
  security_zone: "application"
  interface:
    interface_id: "nic-primary"
    mac_address: "02:00:00:00:20:2A"
    attachment: "vm-network-app"
  addresses:
    - ip: "10.40.20.42"
      version: 4
      assignment: "dhcp-reservation"
      source: "dhcp-scope-app"
      valid_from: "2026-11-28T00:00:00Z"
      valid_until: null

dns:
  names:
    - "order-api-02.corp.example"

evidence:
  - type: "dhcp-lease"
    observed_at: "2026-11-28T02:30:00Z"
    source_system: "dhcp-app-primary"
  - type: "cloud-instance-metadata"
    observed_at: "2026-11-28T02:31:00Z"
    source_system: "cloud-inventory"

review:
  last_verified_at: "2026-11-28T03:00:00Z"
  verification_status: "corroborated"
  next_review_due: "2026-12-28"
~~~

Địa chỉ **10.40.x.x** là ví dụ private, **corp.example** là tên minh họa. MAC bắt đầu bằng **02:** là ví dụ địa chỉ unicast locally administered. Không dùng các định danh minh họa để tìm tài sản ngoài phạm vi.

Cần tránh một trường mơ hồ như **last_seen** không nói rõ được thấy từ đâu. Tốt hơn là giữ **last_seen_by_dhcp**, **last_seen_by_nac**, **last_seen_by_edr** hoặc một tập evidence riêng, mỗi nguồn có timestamp và độ tin cậy.

## 4. Quan hệ IP và thiết bị luôn có yếu tố thời gian

Một sự kiện firewall có nội dung “10.40.20.45 kết nối TCP tới 10.40.30.15 lúc 10:05” không đủ để kết luận máy nào đã gửi. Phải xác định **IP thuộc đối tượng nào tại thời điểm 10:05**, chứ không dùng owner hiện tại của IP.

### 4.1. Ví dụ DHCP cấp lại địa chỉ

~~~text
08:00  Máy A nhận lease 10.40.20.45
10:10  Máy A rời mạng, lease được giải phóng hoặc hết hiệu lực
11:00  Máy B được cấp 10.40.20.45
13:00  Đội SOC điều tra firewall log phát sinh lúc 09:30
~~~

Nếu chỉ tra cứu dashboard **hiện tại**, SOC có thể thấy 10.40.20.45 thuộc **Máy B** và gán sai sự kiện 09:30. Phải đối chiếu lịch sử lease cùng mốc thời gian và các nguồn khác, không mặc định thiết bị dùng IP tại 13:00 là thiết bị dùng IP tại 09:30.

Thực tế hành vi release, renew, lease expiry, DHCP failover và lease time tùy cấu hình. Không phải máy rời mạng là lease lập tức được giải phóng; một lease đang còn hiệu lực cũng không chứng minh máy đang online.

### 4.2. Quan hệ nhiều–nhiều và NAT

- Một **asset** có thể có nhiều IP trên nhiều NIC hoặc nhiều IP cùng một NIC.
- Một **IP public** trên NAT gateway có thể đại diện nhiều host nội bộ.
- Một **VIP** của load balancer đại diện nhiều backend.
- Một **hostname** có thể phân giải ra nhiều A/AAAA; nhiều hostname cùng trỏ tới một IP.
- Một **container/pod** có IP riêng rồi bị thay thế trong một deployment.
- Một **client VPN** có IP khác nhau ở các phiên; cùng IP pool được tái sử dụng.

Trong bài toán attribution, **IP + thời điểm + port + NAT mapping + routing domain + identity** có giá trị hơn IP đơn lẻ.

### 4.3. Tính hợp lệ của bản ghi

Nên phân biệt:

| Mốc | Nội dung |
|---|---|
| **valid_from / valid_until** | Khoảng thời gian một quan hệ/assignment được coi có hiệu lực |
| **observed_at** | Khi thiết bị hoặc sensor thực sự ghi nhận sự kiện |
| **ingested_at** | Khi hệ thống inventory nhận dữ liệu |
| **updated_at** | Khi database inventory bị sửa, không nhất thiết là lúc dữ liệu có hiệu lực |
| **verified_at** | Khi đã được xác nhận bằng quy trình hoặc nguồn hỗ trợ |
| **expires_at** | Khi bằng chứng/lease/policy dự kiến không còn đáng tin |

Đây là thiết kế **temporal inventory**. Nếu event tới muộn, không dùng **ingested_at** thay **observed_at** mà không ghi rõ, vì sẽ làm sai timeline điều tra.

## 5. DHCPv4 đóng góp gì cho network inventory?

**DHCPv4** cấp cấu hình mạng cho client như IP, subnet mask, default gateway, DNS server và lease time. Trao đổi phổ biến gồm các bước **Discover, Offer, Request, Acknowledge (DORA)**, nhưng thực tế có nhiều trạng thái như renew, rebind, release và các tình huống client đã có địa chỉ.

~~~mermaid
sequenceDiagram
    participant C as DHCP client
    participant R as DHCP relay (nếu có)
    participant S as DHCP server
    C->>R: Discover
    R->>S: Discover chuyển tiếp
    S-->>R: Offer (địa chỉ đề xuất)
    R-->>C: Offer
    C->>R: Request
    R->>S: Request
    S-->>R: ACK + cấu hình/lease
    R-->>C: ACK
    Note over S: Lease state và log cấp phát
~~~

Trong mạng cùng broadcast domain, client có thể liên hệ DHCP server trực tiếp, không cần relay. Sơ đồ có relay nhằm minh họa trường hợp server nằm ở subnet khác.

### 5.1. Trường DHCP hữu ích

| Thuộc tính | Giá trị với inventory |
|---|---|
| Lease IP | Địa chỉ được cấp theo DHCP |
| Client hardware address | Có thể dùng để đối chiếu MAC, nếu phù hợp |
| Client identifier (DHCPv4 option 61) | Một định danh có thể được client gửi, không luôn trùng MAC |
| Scope/pool | Gắn IP với subnet hoặc phạm vi cấp phát |
| Lease start/end | Khoảng cấp phát theo log server |
| DHCP relay/giaddr | Gợi ý subnet nơi client yêu cầu, nếu qua relay |
| Option 82 / relay agent information | Có thể chứa thông tin circuit/remote ID ở mạng hỗ trợ |
| Hostname option | Tên client công bố, không mặc nhiên đáng tin |
| Server ID | DHCP server đã xử lý transaction |
| Reservation | Dữ liệu cấu hình dự kiến gán IP cho một client theo rule |

**Client-supplied hostname/MAC/client ID có thể bị giả mạo hoặc thay đổi**, nên không coi một trường do client cung cấp là chứng thực danh tính. Cần đối chiếu NAC, switch port, EDR, hypervisor hoặc hệ thống quản trị khác.

### 5.2. DHCP lease không phải bảng “máy đang online”

Một lease đang active có thể tồn tại khi thiết bị đã tắt, ngủ hoặc ra khỏi mạng. Ngược lại, thiết bị dùng **static IP** sẽ không có lease trong DHCP server.

Cần tách:
- **Address allocated/leased:** server đã cấp quyền dùng địa chỉ.
- **Seen on network:** switch/AP/ARP/ND/flow có dấu vết giao tiếp.
- **Authenticated:** thiết bị/user có session NAC/VPN được ghi.
- **Actively managed:** EDR/MDM/CMDB xác nhận tài sản thuộc phạm vi quản trị.

Nếu DHCP server có **failover**, nhiều site hoặc nhiều scope, cần thu lịch sử đầy đủ và giữ ID nguồn; không gộp hai bản ghi cùng IP từ những routing domain khác nhau như thể chúng là một đối tượng.

### 5.3. Rogue DHCP và biến động bất thường

Một DHCP server không được phê duyệt có thể cung cấp gateway/DNS không mong muốn, gây mất kết nối hoặc chuyển hướng DNS. Inventory giúp phát hiện **DHCP server ID lạ, thay đổi option, pool không đúng, nhiều nguồn cấp phát** hoặc endpoint chuyển VLAN ngoài dự kiến.

Phòng vệ có thể gồm **DHCP snooping**, kiểm soát cổng switch, 802.1X/NAC và chính sách phát hiện tại tầng mạng. Tính năng phụ thuộc thiết bị; chỉ dựa vào việc lưu lease trong IPAM không tự chặn rogue DHCP.

## 6. IPv6 làm network inventory khác đi thế nào?

Với IPv6, một interface có thể đồng thời có **link-local address**, địa chỉ global, stable address và temporary/privacy address. Không phải mọi IPv6 được cấp qua DHCPv6.

### 6.1. SLAAC, RA và DHCPv6

- **Router Advertisement (RA):** cung cấp thông tin prefix và tham số để host cấu hình IPv6; có thể hỗ trợ **SLAAC**.
- **SLAAC:** host tự tạo địa chỉ từ prefix và thông tin của nó; không đòi một DHCPv6 lease tương ứng.
- **DHCPv6:** có thể cấp địa chỉ/trạng thái hoặc các tham số bổ sung tùy môi trường.
- **Link-local:** phạm vi link, thường bắt đầu bằng **fe80::/10**, không định tuyến như địa chỉ global.
- **Temporary/privacy address:** có thể thay đổi theo thời gian nhằm giảm việc theo dõi một thiết bị bằng địa chỉ IPv6 cố định.

**Một inventory chỉ đọc DHCPv6 có thể bỏ sót nhiều IPv6 address** đang sử dụng qua SLAAC, bao gồm các địa chỉ tạm. Cần dữ liệu từ endpoint, ND/neighbour cache, switch/router và nguồn quản trị hạ tầng phù hợp.

### 6.2. DUID, IAID và identifier IPv6

Trong DHCPv6, **DUID** là định danh client; **IAID** phân biệt identity association trong phạm vi client. Chúng không phải MAC address một-một và phải được diễn giải trong ngữ cảnh cấp phát.

Đối với SLAAC/privacy address, không thể suy ra danh tính tài sản chắc chắn chỉ từ phần interface identifier của IPv6. Các cơ chế tạo địa chỉ ngày nay khác nhau theo OS và cấu hình.

### 6.3. Ví dụ prefix IPv6 trong lab

~~~text
Routing domain: corp-v6-lab
Prefix minh họa: 2001:db8:40:20::/64
Interface có thể có:
  fe80::...             (link-local)
  2001:db8:40:20::42    (địa chỉ được quản trị)
  2001:db8:40:20::...   (temporary/privacy address)
~~~

**2001:db8::/32** là dải dành cho tài liệu IPv6, không phải prefix thực dùng trên Internet. Khi lưu inventory cần có **IP version, prefix, zone/routing domain, nguồn bằng chứng và valid interval**. Chính sách IPv4 không tự bảo vệ IPv6; các luồng IPv6 cần được phân đoạn và log phù hợp.

### 6.4. Neighbor Discovery và RA security

IPv6 dùng **Neighbor Discovery (ND)** để tìm hàng xóm và router theo những cơ chế ICMPv6. Một số kiểm soát doanh nghiệp như **RA Guard** có thể giúp hạn chế RA không được phê duyệt trong điều kiện thiết bị hỗ trợ. Host và switch cần giám sát prefix/router lạ, nhưng không được chặn tùy tiện ICMPv6 thiết yếu vì có thể làm hỏng mạng.

**Nhìn thấy một IPv6 trong ND cache không chứng minh đây là tài sản được phê duyệt.** Cần đối chiếu với endpoint identity và ownership theo thời gian.

## 7. DNS, hostname và IPAM phải được đối soát với nhau

IPAM mô tả **địa chỉ được quản lý như thế nào**; DNS mô tả **tên được công bố ra sao**; DHCP mô tả **địa chỉ được cấp khi nào**. Ba nguồn thường liên quan, nhưng không hoàn toàn tương đương.

### 7.1. A, AAAA, PTR và CNAME

| Bản ghi | Vai trò | Sai lầm thường gặp |
|---|---|---|
| **A** | Tên → địa chỉ IPv4 | Coi A record là chứng minh máy đang online |
| **AAAA** | Tên → địa chỉ IPv6 | Bỏ sót IPv6 khi chỉ tra A |
| **PTR** | Địa chỉ → tên reverse DNS | Coi PTR là định danh đã xác thực |
| **CNAME** | Alias → canonical name | Coi alias là một máy vật lý độc lập |
| **SRV** | Khám phá dịch vụ theo tên, protocol, port trong môi trường có dùng | Coi có SRV record nghĩa listener luôn đang hoạt động |

Một **A/AAAA** có thể trỏ tới VIP, load balancer, CDN, nhiều IP hoặc container tồn tại ngắn. Một **PTR** có thể chưa cập nhật sau khi IP được cấp lại. **DNS không thay thế asset ID**; nó là một tập record được quản lý với TTL, owner và thời điểm cập nhật.

### 7.2. Dynamic DNS update

Một số mạng để DHCP hoặc client cập nhật DNS tự động. Quy trình cần xác định:

- Ai có quyền tạo/sửa/xóa A/AAAA/PTR?
- Khi lease hết hiệu lực, record có được thu hồi đúng không?
- Có kiểm tra xung đột và quyền sở hữu tên?
- Có tách public/private zones và split DNS?
- Có log thay đổi kèm actor/time?
- DNSSEC validation và secure updates có phù hợp với hệ thống không?

**Không mặc định DHCP ACK sẽ đồng thời làm DNS chính xác.** Nếu cơ chế cập nhật bị lỗi hoặc cấu hình không phù hợp, DNS và lease có thể lệch.

### 7.3. Ví dụ đối soát

~~~text
IPAM: 10.40.20.45 dự kiến thuộc host-app-01
DHCP: 10.40.20.45 được cấp client-id của host-laptop-15
DNS:  host-app-01.corp.example -> 10.40.20.45
NAC:  Interface hiện thuộc Staff VLAN, không phải App
~~~

Đây là **xung đột cần điều tra**, chưa thể chọn một trong bốn nguồn là đúng tuyệt đối. Cần kiểm tra lịch sử lease, thời điểm DNS update, reservation rule, switch port, owner và routing context. Một bản ghi IPAM cũ và DNS chưa xóa có thể giải thích tình huống mà không cần giả định có tấn công.

## 8. Nguồn dữ liệu để dựng inventory

Không nên dùng một công cụ duy nhất cho toàn bộ môi trường. Mỗi nguồn trả lời một loại câu hỏi.

| Nguồn | Có thể cung cấp | Hạn chế |
|---|---|---|
| DHCPv4/DHCPv6 server | Lease, scope, client ID, DUID/IAID, thời gian | Không thấy static IP và nhiều SLAAC IPv6 |
| DNS server/resolver | Tên, record, query activity, zone/owner | Tên có thể cũ; query không chứng minh endpoint tồn tại |
| Switch/router | Interface, VLAN, MAC forwarding database, LLDP, ARP/ND, route | Bảng động hết hạn; MAC không phải user identity |
| Wi-Fi controller/AP | SSID, AP, client association, VLAN, thời gian | MAC randomization, roaming, session thay đổi |
| NAC/802.1X/RADIUS | Identity, session, posture, role/VLAN | Cần đối chiếu timestamp và cấp quyền |
| Firewall/flow logs | Luồng source–destination–port, zone, NAT, action | Không thấy traffic không đi qua; không chứng minh owner |
| VPN gateway | User/device session, IP pool, start/end | IP tái sử dụng; quyền tunnel khác quyền vào dịch vụ |
| EDR/MDM/agent | Asset ID, OS, NIC, process, trạng thái quản lý | Không phủ unmanaged endpoints; agent có thể offline |
| Hypervisor / VM inventory | VM UUID, vNIC, vSwitch, cluster, power state | Không luôn phản ánh traffic hoặc IP thực tế |
| Cloud API / config inventory | Instance, ENI/NIC, IP, VPC/VNet, SG, tags, LB | Tài nguyên ngắn hạn, tag có thể thiếu/sai |
| Kubernetes API / CNI | Pod UID, node, namespace, service, labels, IP | Pod thay đổi nhanh; service IP không phải pod identity |
| CMDB / ticket system | Owner, service, criticality, lifecycle, approval | Dữ liệu nhập tay có thể chưa cập nhật |
| LLDP/CDP | Láng giềng kết nối vật lý/logic theo giao thức | Không áp dụng mọi endpoint, thông tin quảng bá có thể giả |
| SNMP / streaming telemetry | Interface counters, device type, cấu hình thiết bị | Cần xác thực, phân quyền, tương thích version/schema |

### 8.1. Chủ động và thụ động

**Passive discovery** dùng log, flow, switch table, DHCP events, agent inventory và dữ liệu API có sẵn. Phương pháp này thường ít tác động tới thiết bị hơn, nhưng không thể thấy mọi host chưa phát traffic hoặc nằm ngoài nguồn thu.

**Active discovery** tạo những phép hỏi/kiểm tra tới thiết bị được cho phép, như ICMP reachability, giao thức quản lý hoặc kết nối đến dịch vụ. Nó có thể làm rõ trạng thái thực tế nhưng cần **scope và rate giới hạn**, nhất là với mạng OT, thiết bị cũ, IoT hoặc môi trường sản xuất nhạy cảm.

**Không tự động quét toàn bộ subnet khi chưa có phê duyệt.** Có thể bắt đầu bằng nguồn passive và API quản trị, rồi bổ sung kiểm tra nhỏ, phù hợp thay đổi nghiệp vụ.

### 8.2. SNMP, LLDP và quản lý thiết bị

**SNMP** có thể cung cấp thông tin interface, thiết bị và bộ đếm. Với mạng doanh nghiệp, nên ưu tiên **SNMPv3 có xác thực/mã hóa** khi khả thi, phân quyền read-only và kiểm soát máy collector; không lưu community string/credential trong tài liệu hay inventory công khai.

**LLDP** giúp thu neighbor relationship giữa các thiết bị hỗ trợ nhưng là dữ liệu công bố tại link; không mặc định chính xác hoặc đủ để xác thực đối tượng. Ghép LLDP với cấu hình switch port, inventory phần cứng và vị trí thiết bị để có sơ đồ topology đáng tin hơn.

### 8.3. Trust level của từng nguồn

Một bảng đánh giá ví dụ:

| Bằng chứng | Giá trị thường có | Điểm cần kiểm tra |
|---|---|---|
| Cloud instance ID từ API control plane | Mạnh về identity của VM/workload trong account được quản lý | Scope account/region và quyền API, thời điểm tài nguyên tồn tại |
| EDR agent ID được quản trị | Mạnh về một endpoint managed | Agent có bị giả/nhân bản hay offline không |
| DHCP lease do server tin cậy cấp | Mạnh về IP assignment tại thời điểm đó | Client ID/MAC có thể thay đổi; không tự xác minh user |
| NAC session đã xác thực | Mạnh về access identity trong phạm vi session | Mapping identity–IP/VLAN phải đồng bộ và đúng thời gian |
| ARP/ND cache | Dấu hiệu mạng thấy láng giềng | Có thể stale/spoofed, không phải chứng minh owner |
| DNS PTR | Gợi ý tên miền | Có thể cũ hoặc không phản ánh host thật |
| Banner/service fingerprint | Gợi ý ứng dụng/OS | Không chứng minh asset ID, phiên bản hoặc quyền truy cập |

**Độ tin cậy phụ thuộc threat model và quyền kiểm soát nguồn**, không có thứ hạng tuyệt đối trong mọi trường hợp.

## 9. Network inventory trong LAN, Wi-Fi và VPN

### 9.1. LAN có VLAN và switch port

Một bản ghi thiết bị tại LAN có thể gắn:

~~~text
asset_id: laptop-managed-041
interface: ethernet-0
switch: sw-floor-02
switch_port: Gi1/0/24
vlan: staff-20
ip: 10.40.20.45
observed_by: switch FDB + NAC + DHCP
time: 2026-11-28T03:00:00Z
~~~

Cùng một cổng switch có thể đi qua **IP phone, docking station, hypervisor hoặc bridge** chứa nhiều MAC. Một MAC forwarding entry thường chỉ cho biết switch đã học MAC trên port; chưa chắc mỗi MAC là một laptop riêng.

### 9.2. Wi-Fi và MAC randomization

Thiết bị Wi-Fi hiện đại có thể dùng địa chỉ MAC riêng cho từng SSID hoặc thay đổi theo chính sách OS. Vì thế một thiết bị có thể xuất hiện với nhiều MAC tại nhiều thời điểm hoặc SSID.

Nên kết hợp **802.1X identity, certificate/device ID, DHCP lease, AP association và MDM/EDR** thay vì gán toàn bộ lịch sử chỉ theo MAC. Với Wi-Fi Guest, dữ liệu identity có thể ít hơn; cần ghi rõ giới hạn attribution và thời hạn lưu riêng tư.

### 9.3. VPN và địa chỉ ảo

VPN concentrator có thể cấp IP từ một pool cho mỗi session. Inventory cần lưu:

- VPN session ID, authenticated identity, device posture nếu có.
- Assigned tunnel IP, routing domain, bắt đầu/kết thúc phiên.
- Gateway/region và loại đường full tunnel/split tunnel.
- Quyền theo nhóm/role và những subnet được truy cập.
- Mapping với firewall/flow logs có cùng timestamp.

**Một người đăng nhập VPN thành công không mặc nhiên được quyền vào mọi mạng.** Inventory kết hợp policy giúp xác định chính xác nguồn được phép tới server quản trị hoặc DB và truy vết một log từ VPN pool mà không gán sai user.

## 10. Network inventory trong cloud, container và Kubernetes

### 10.1. Cloud infrastructure inventory

Trong cloud, nên lấy từ **API quản trị** các thông tin: account/project/subscription, region/zone, VPC/VNet, subnet, NIC/ENI, private/public IP, instance ID, image, IAM role, network/security group, load balancer và tag owner.

~~~mermaid
flowchart TD
    ACC[Cloud account / project] --> VPC[VPC / VNet]
    VPC --> SUB[Subnet]
    SUB --> NIC[Network interface]
    NIC --> VM[VM / Workload ID]
    NIC --> IP[Private/public IP]
    NIC --> SG[Security group / policy]
    VM --> TAG[Owner, service, environment]
    VM --> LOG[Flow + audit + monitoring]
~~~

Tài nguyên auto-scaling có thể tồn tại chỉ vài phút. Không nên đợi một lần quét hàng tháng mới cập nhật inventory. Có thể dùng **cloud events + API polling/reconciliation** để duy trì trạng thái và lịch sử thay đổi.

**Cloud resource tag có thể bị thiếu hoặc tự đặt sai.** Để xác minh owner/criticality, cần kết hợp CI/CD metadata, account ownership, service catalog và quyền thay tag.

### 10.2. Kubernetes: không dùng IP pod làm ID ổn định

Một **Pod UID** xác định một lần tồn tại pod, còn tên deployment/namespace/label mô tả nhóm workload. Pod có thể được thay bằng pod mới với IP khác; service có **ClusterIP/VIP** và backend thay đổi theo endpoints.

Nên liên hệ:
- Cluster ID, namespace, node ID.
- Deployment/StatefulSet/Job và owner references.
- Pod UID, creation/deletion time, labels.
- Pod IP, node IP, Service IP, ingress/gateway endpoint.
- NetworkPolicy và CNI thực thi.
- Workload/service account identity.
- Bằng chứng flow từ CNI hoặc proxy.

Khi điều tra **10.244.2.15 lúc 09:30**, phải xác định pod UID nào giữ địa chỉ đó lúc 09:30. Chỉ xem danh sách pod hiện tại không đủ để truy nguồn sự kiện cũ.

### 10.3. CIDR trùng nhau và network context

Dải **10.40.20.0/24** có thể xuất hiện ở hai VPC độc lập hoặc ở mạng lab và production. Một IP **10.40.20.42** trong VPC A không phải cùng tài sản với IP đó trong VPC B.

Vì vậy khóa địa chỉ inventory nên bao gồm **routing domain/VRF, VPC/VNet hoặc tenant, IP version, địa chỉ và khoảng hiệu lực**, không chỉ địa chỉ IP.

### 10.4. Các endpoint không gắn với một máy

Load balancer, CDN, NAT gateway, service VIP, DNS alias và private endpoint là **network entities** đáng kiểm kê. Chúng có thể sở hữu IP nhưng không phải host chạy ứng dụng cuối.

Cần lưu quan hệ **public endpoint → load balancer → target group/backend → application → data dependency**, để thiết kế firewall và điều tra không nhầm một VIP với một máy duy nhất.

## 11. Chuẩn hóa và đối soát dữ liệu từ nhiều nguồn

### 11.1. Pipeline tổng quát

~~~mermaid
flowchart LR
    D[DHCP/DNS/IPAM] --> ING[Ingest]
    N[NAC/Switch/VPN] --> ING
    C[Cloud/Kubernetes API] --> ING
    H[EDR/CMDB/Telemetry] --> ING
    ING --> PARSE[Normalize + timestamp + identity map]
    PARSE --> MATCH[Correlate / reconcile]
    MATCH --> INV[(Inventory + history)]
    MATCH --> ERR[Conflict / review queue]
    INV --> SOC[Firewall, SOC, IPAM, risk, operations]
~~~

Các bước nên độc lập, có khả năng audit:

1. **Thu dữ liệu:** API, event stream, syslog hoặc export từ những nguồn được phép.
2. **Chuẩn hóa:** IP version, CIDR, casing hostname, asset ID, timestamp UTC và routing domain.
3. **Lưu bằng chứng gốc:** source event ID, payload tham chiếu, observed_at/ingested_at.
4. **Ghép đối tượng:** dùng identifier có mức tin cậy phù hợp và đúng thời gian.
5. **Đối soát:** tìm mâu thuẫn giữa địa chỉ dự kiến và quan sát.
6. **Phân loại:** confirmed, inferred, unverified, conflict, stale, decommissioned.
7. **Đưa vào quy trình:** yêu cầu owner xác minh, cập nhật IPAM/CMDB/DNS hoặc tạo ticket.
8. **Lưu lịch sử:** không xóa bản ghi cũ trước khi giữ các mốc cần điều tra.

### 11.2. Pseudocode ghép một event theo thời gian

~~~text
input:
  event_time, source_ip, ip_version, routing_domain
  optional: source_port, mac, client_id, vpn_session, interface

candidates = assignments WHERE
  address == source_ip
  AND ip_version == event.ip_version
  AND routing_domain == event.routing_domain
  AND valid_from <= event_time
  AND (valid_until IS NULL OR event_time < valid_until)

for each candidate:
  correlate with DHCP / NAC / EDR / cloud / NAT evidence
  compare timestamps and source confidence
  report all consistent candidates and contradictions

if no trusted candidate:
  mark "unresolved" and request investigation
else if multiple conflicting candidates:
  mark "conflict" and preserve evidence
else:
  return asset candidate with confidence and source trail
~~~

Đây là logic khái niệm, không phải truy vấn áp dụng trực tiếp cho hệ thống thật. Với NAT, cần xét **source port, mapping tại thời điểm đó và public/private hop**; với IP trùng, bắt buộc phân biệt routing domain.

### 11.3. Không tự chọn “nguồn cuối cùng ghi là đúng”

**Last writer wins** có thể làm xóa bằng chứng lịch sử đúng. Ví dụ, bản ghi DHCP đến chậm sẽ cập nhật asset hiện tại sai nếu hệ thống dùng ingestion time thay event time. Nên phân biệt **source of authority** theo loại thuộc tính:

| Thuộc tính | Nguồn có thể có thẩm quyền chính | Cần đối chiếu |
|---|---|---|
| Prefix owner / subnet purpose | IPAM/network design được phê duyệt | Router/VPC config, CMDB |
| DHCP allocation | DHCP server authoritative cho scope đó | NAC, switch/AP, client logs |
| Asset lifecycle | CMDB/cloud control plane/MDM tùy asset | EDR, CI/CD, owner xác nhận |
| User connected at time T | NAC/VPN/IdP session logs theo ngữ cảnh | DHCP assignment, endpoint identity |
| Actual reachability | Flow logs và kiểm chứng đường đi có quyền | Firewall ACL, listener, routing |
| Service owner | Service catalog/CMDB hoặc nhóm vận hành | Repo/CI/CD metadata và ticket |
| IP currently answering | Nguồn quan sát có timestamp | Asset ID, lease, NAT, topology |

Nên lưu **provenance (nguồn gốc dữ liệu)** và quy tắc ưu tiên công khai, thay vì dùng tên cột owner đơn lẻ không giải thích lý do tin cậy.

## 12. Phát hiện sai lệch và vấn đề bảo mật từ inventory

Một hệ thống inventory có ích phải chỉ ra những điều **không phù hợp với thiết kế**.

### 12.1. Một số mẫu cần theo dõi

| Dấu hiệu | Ý nghĩa khả dĩ | Kiểm chứng trước khi kết luận |
|---|---|---|
| IP quan sát được nhưng không có trong IPAM | Static IP chưa đăng ký, shadow IT, tài sản mới | Kiểm tra VRF, owner, DHCP/EDR/cloud |
| DHCP lease gắn với identifier ngoài danh sách | BYOD, máy chưa quản trị hoặc identifier thay đổi | NAC, MAC randomization, MDM |
| IP trùng trong cùng routing domain | Konflikt địa chỉ hoặc telemetry sai thời gian | Interface state, ARP/ND, lease timestamps |
| PTR/A record vẫn trỏ IP đã cấp lại | Stale DNS | DNS TTL, DDNS update, release/renew |
| AP/switch port thấy thiết bị lạ | Guest/unmanaged endpoint hoặc bridge | SSID/VLAN, NAC session, owner |
| Có public IP mới ở máy nội bộ | Phơi bày dịch vụ ngoài kế hoạch | Cloud LB/SG, router policy, service owner |
| Management device thiếu owner | Quản trị cấu hình và bản vá khó kiểm soát | CMDB, site owner, switch location |
| Cloud resource không có tag | IaC/deployment không gắn metadata | Account/CI pipeline và actor |
| Workload đã decommission nhưng flow vẫn xuất hiện | Reused IP, service chưa tắt hoặc ID nhầm | Bằng chứng thời gian, NAT, route |
| Firewall rule trỏ subnet không còn dùng | Rule tồn dư hoặc thay đổi dependency | Rule hit, owner, change history |
| VPN source IP không ánh xạ phiên | Log thiếu, thời gian sai hoặc địa chỉ bị tái sử dụng | VPN logs, clock/timezone, IP pool |

**Inventory là công cụ phát hiện sai lệch, không phải hệ thống phán quyết hành vi độc hại.** Một địa chỉ ngoài IPAM có thể là tài sản hợp lệ mới triển khai; không nên tự động cô lập khi chưa xác minh theo quy trình, đặc biệt với hệ thống trọng yếu.

### 12.2. Rogue DHCP, IP spoofing và giả mạo quan sát

Trong một số mạng không đủ kiểm soát L2, client có thể giả MAC hoặc dùng source IP không được cấp. Do đó DHCP lease **không tự chứng minh** rằng mọi gói mang địa chỉ đó đều xuất phát từ client được cấp.

Những lớp phòng vệ có thể hỗ trợ gồm:

- **DHCP snooping** để xây bảng gán cấp phát trên switch hỗ trợ.
- **IP Source Guard** hoặc cơ chế tương tự để giới hạn nguồn IP trên port theo binding đáng tin.
- **Dynamic ARP Inspection** trong IPv4 LAN phù hợp.
- **802.1X/NAC**, posture/identity và phân đoạn theo vai trò.
- **RA Guard** và kiểm soát IPv6 phù hợp.
- **Host firewall, ACL, monitoring và IDS/IPS** để phát hiện traffic ngoài kỳ vọng.

Từng tính năng có điều kiện hỗ trợ và nguy cơ cấu hình sai. Không bật hàng loạt trên production chỉ dựa vào một bảng inventory; cần thiết kế trust port, DHCP relay, virtual switch, IPv6 và các use case đặc biệt.

## 13. Inventory hỗ trợ thiết kế phân đoạn và firewall

Một chính sách **source → destination → protocol/port** chỉ có giá trị khi nguồn và đích gắn với đúng asset/service:

~~~mermaid
flowchart LR
    STAFF[Staff VLAN 20] -->|HTTPS/443| WEB[Frontend]
    APP[App VLAN 30] -->|TCP/5432| DB[(Database)]
    GUEST[Guest VLAN 50] -.DENY.-> DB
    VPN[Admin VPN] -->|SSH theo role| J[Jump Host]
    INV[(Inventory + IPAM + Identity)] -.Role/owner/source truth.-> WEB
    INV -.Role/owner.-> DB
    INV -.Access context.-> J
~~~

Khi App workload thay đổi IP hoặc một service được chuyển sang cloud, các rule cũ dựa trên IP có thể không còn chính xác. Network inventory giúp:

1. Xác định **danh sách service và owner** đang sử dụng một vùng mạng.
2. Thu hẹp rule từ **Any** thành subnet, host, service group hoặc workload identity có thể kiểm soát.
3. Phát hiện subnet/VLAN bị gán sai trust zone.
4. Xác định luồng nào cần đi qua firewall, VPN hoặc distributed policy.
5. Đối chiếu rule thay đổi với deployment và IPAM plan.
6. Review rule thừa sau khi một tài sản decommission.
7. Đánh giá **blast radius** nếu một nguồn được phép bị chiếm quyền.

**Đổi IP không thay thế việc kiểm tra danh tính ứng dụng.** Một workload có IP nằm trong dải được allow vẫn phải xác thực và chỉ có quyền nghiệp vụ tối thiểu khi truy cập DB/API.

### 13.1. Policy theo subnet và theo workload identity

Với dịch vụ ổn định, IP/CIDR phù hợp để mô tả một số ranh giới mạng. Với cloud/Kubernetes có workload ngắn hạn, có thể dùng **security group reference, label, workload identity hoặc service account** khi nền tảng có thể thực thi đáng tin.

Inventory nên lưu cả **địa chỉ tại thời điểm hiện tại** và **nhóm vai trò có ý nghĩa nghiệp vụ**, vì IP và label đều có rủi ro khi bị thay đổi bởi actor không được cấp quyền. Phải bảo vệ control plane và log thay đổi policy.

### 13.2. Không nhầm tài sản với cổng dịch vụ

Một asset được biết đang có IPv4 10.40.30.15 chưa chứng minh dịch vụ TCP/5432 đang lắng nghe hoặc reachable từ mọi zone. Inventory có thể lưu **expected service/port**, còn việc thực thi phải được kiểm chứng qua listener, network policy, flow/connection logs hoặc bài test có quyền.

## 14. Network inventory phục vụ threat modeling và ứng phó sự cố

### 14.1. Xác định tài sản và đường tấn công

Threat modeling hỏi:

- Tài sản có dữ liệu/khả năng quan trọng nào?
- Nó nằm ở subnet, zone, account và môi trường nào?
- Nó liên lạc với ai, qua những port/giao thức nào?
- Thiết bị bị chiếm ở Guest/Staff/App có thể tới tài sản nào?
- Ai có quyền đổi routing, DHCP option, DNS record, VLAN, security group hoặc CNI policy?
- Có điểm đo/IDS/EDR nào thực sự nhìn thấy traffic?
- Có thể truy vết IP một sự kiện về asset và identity ở thời điểm đó không?

Inventory giúp biến sơ đồ lý thuyết thành **đối tượng thực có owner và bằng chứng**, giúp phân tích khả năng di chuyển ngang, quản lý phạm vi kiểm tra và phát hiện tài sản bỏ sót.

### 14.2. Điều tra một firewall event

Giả sử firewall có event:

~~~text
2026-11-28T03:10:00Z
source=10.40.20.45:53124
destination=10.40.30.15:5432
protocol=tcp action=deny rule=STAFF-TO-DB-DENY
~~~

Một quy trình hợp lý:

1. Xác định thiết bị firewall/zone và IP/port trước-sau NAT theo log.
2. Tra IPAM: 10.40.20.45 thuộc **routing domain nào**, subnet/zone nào?
3. Tra **lịch sử DHCP lease tại 03:10 UTC**, không chỉ lease hiện tại.
4. Ghép DHCP client identifier với NAC/802.1X, switch port/AP và EDR đúng thời điểm.
5. Kiểm tra asset owner, trạng thái quản trị và deployment/change ticket.
6. Đối chiếu log khác từ cùng asset: DNS, VPN, EDR, firewall, DB nếu có.
7. Xác định đây là thử kết nối không được phép, lỗi cấu hình hay hành vi nghi vấn; ghi độ tin cậy.
8. Nếu cần biện pháp phản ứng, phối hợp owner và theo runbook được cấp quyền.

**Kết luận đúng mức:** firewall đã deny một flow từ địa chỉ được quan sát tại thời điểm đó. Không viết “người X cố tấn công DB” khi chưa có dữ liệu xác thực user cùng mốc.

### 14.3. Độ bao phủ giám sát

Inventory có thể hỗ trợ trả lời những câu hỏi:

- Bao nhiêu server production được EDR quản lý?
- Bao nhiêu subnet có firewall/flow logging?
- Có VM public nào chưa có owner?
- Bao nhiêu thiết bị mạng được cấu hình SNMPv3/streaming telemetry?
- Có Wi-Fi guest client nào đi vào VLAN quản trị?
- Có IPv6 address trên host quan trọng nhưng chưa có rule/log tương ứng?

**Không thể đo coverage chỉ dựa vào số dòng IPAM.** Cần mẫu số phù hợp: tập tài sản expected từ cloud/control plane, DHCP/ARP/ND, NAC, hypervisor, CMDB, hoặc dữ liệu khác; các nguồn đều có điểm mù nên phải ghi phương pháp ước lượng.

## 15. Đánh giá chất lượng Network inventory

Inventory phải được kiểm tra bằng tiêu chí định lượng chứ không chỉ “đã nhập dữ liệu”.

| Chỉ số | Ý nghĩa | Ví dụ cách đo |
|---|---|---|
| **Coverage** | Tỷ lệ tài sản trong phạm vi có record | Số VM cloud có record / tổng VM từ API được quản lý |
| **Completeness** | Tỷ lệ record có trường quan trọng | Asset có owner, zone, environment, ID |
| **Freshness** | Độ mới của evidence | Tuổi của lần xác minh gần nhất theo nguồn |
| **Accuracy** | Thông tin đúng khi đối chiếu ground truth | Mẫu record được owner xác nhận |
| **Conflict rate** | Tỷ lệ dữ liệu mâu thuẫn | IPAM vs DHCP vs DNS khác nhau |
| **Uniqueness** | Không có định danh trùng sai | Asset ID duy nhất; IP theo VRF và thời gian |
| **Attribution quality** | Tỷ lệ event map được tới asset/identity với bằng chứng | Firewall flow có mapping hợp lệ |
| **Orphan rate** | Tỷ lệ tài sản thiếu owner | Unowned VM, network device, prefix |
| **Lifecycle hygiene** | Tài sản nghỉ dùng có thu hồi không | Decommissioned assets còn IP/DNS/rule |
| **Discovery latency** | Trễ từ khi xuất hiện đến lúc inventory nhận biết | Cloud event time → inventory ingest |

### 15.1. Ví dụ tính coverage

Nếu cloud API trong phạm vi được quản lý ghi nhận **200 VM** tại thời điểm kiểm tra và inventory có record hợp lệ cho **188 VM**, coverage theo nguồn đó là:

\[
\text{Coverage}_{VM} = \frac{188}{200}\times 100\% = 94\%.
\]

Con số này **không đại diện** cho tất cả endpoint, thiết bị vật lý, pod, IoT hoặc tài sản bên ngoài phạm vi API. Nên công bố **phạm vi và nguồn mẫu số** khi báo cáo.

### 15.2. Ví dụ tính tỷ lệ owner đầy đủ

Nếu inventory có 500 record trong phạm vi đánh giá và 445 record có owner được xác minh:

\[
\text{Owner completeness} = \frac{445}{500}\times 100\% = 89\%.
\]

Một trường owner không rỗng chưa chắc **đã xác minh**; có thể là tên nhóm cũ. Cần định nghĩa rõ trường được coi là đủ bằng chứng khi đo.

### 15.3. Độ mới theo loại tài sản

Một IP của pod hoặc VPN session có thể thay đổi theo phút, trong khi serial của switch ít thay đổi hơn. Vì vậy **ngưỡng freshness nên khác nhau theo trường và loại tài sản**:

- Cloud VM/pod/lease: cần cập nhật gần real-time hoặc qua event và reconcile định kỳ.
- Switch/router/interface: kiểm tra định kỳ và ngay sau change.
- Owner/criticality: xác minh theo quy trình và chu kỳ review.
- DHCP lease/VPN session: giữ lịch sử đầy đủ theo chính sách để truy nguồn event.

Không nên dùng một TTL 30 ngày cho mọi trường rồi kết luận inventory “đang cập nhật”.

## 16. Quy trình vận hành inventory từ lúc cấp phát tới thu hồi

### Giai đoạn 1 — Thiết kế và cấp địa chỉ

1. Phê duyệt subnet/prefix, VRF/VPC, VLAN/zone và mục đích.
2. Chọn dải DHCP, reservation, static assignment và DNS naming convention.
3. Chỉ định subnet owner, service owner, gateway, DNS/DHCP service và chính sách IPv6.
4. Ghi planned allocations trong IPAM trước khi mở kết nối nghiệp vụ.
5. Xác định firewall/ACL và NAC policy tương ứng.

### Giai đoạn 2 — Onboarding tài sản

1. Tạo asset ID và owner hợp lệ.
2. Gắn NIC/vNIC và network segment.
3. Xác định loại IP assignment: static, DHCPv4, DHCPv6, SLAAC, cloud allocated.
4. Đối chiếu DHCP/DNS/switch/NAC/EDR/cloud evidence.
5. Xác minh thiết bị được phép hoạt động trong đúng zone.
6. Lưu ngày onboarding và version cấu hình.

### Giai đoạn 3 — Duy trì và quan sát

1. Nhận change events từ DHCP, cloud, hypervisor, Wi-Fi, VPN và CMDB.
2. Định kỳ reconcile với dữ liệu tổng từ API/source of authority.
3. Gắn evidence và timestamp cho từng thay đổi.
4. Tạo ticket cho orphan asset, IP conflict và DNS mismatch.
5. Review rule firewall và quyền service liên quan khi IP/role thay đổi.
6. Theo dõi telemetry loss và độ mới của inventory.

### Giai đoạn 4 — Thay đổi/migration

Nếu VM chuyển subnet hoặc tài nguyên được chuyển VPC:

1. Ghi desired state mới và kế hoạch thay đổi.
2. Xác định DNS, IPAM, DHCP, security group/ACL, route, monitoring, backup và certificate dependencies.
3. Thực hiện thay đổi theo quy trình được phê duyệt.
4. Xác minh kết nối đúng luồng, ranh giới deny và trạng thái DNS.
5. Chốt lịch sử old/new assignment cùng thời gian hiệu lực.
6. Thu hồi rule hoặc địa chỉ cũ sau khi xác nhận không còn dependency.

### Giai đoạn 5 — Decommission

1. Xác nhận owner đồng ý ngừng tài sản.
2. Thu hồi/tắt workload và credential phù hợp.
3. Thu hồi IP reservation/lease khi điều kiện cho phép, DNS record và route liên quan.
4. Xem xét security group, firewall rule, monitoring, backup, license và secret.
5. Giữ lịch sử inventory, lease và audit theo retention để hỗ trợ điều tra cũ.
6. Đổi lifecycle_state thành decommissioned và đánh dấu assignment đã hết hiệu lực.

**Không xóa sạch lịch sử** khi một IP được tái cấp; điều đó làm mất khả năng điều tra sự kiện cũ.

## 17. Thực hành an toàn: đọc thông tin mạng trên máy được quản trị

Các lệnh dưới đây **chỉ dùng để quan sát** máy do người học sở hữu hoặc được cấp quyền. Không quét mạng hay đăng nhập thiết bị của bên khác. Lệnh và output khác nhau theo OS, bản phân phối, quyền và công cụ được cài.

### 17.1. Linux

~~~bash
# Liệt kê interface và địa chỉ IPv4/IPv6 ngắn gọn
ip -br addr

# Xem route IPv4
ip -4 route show

# Xem route IPv6
ip -6 route show

# Xem neighbor entries đã được host ghi nhận
ip neigh show

# Nếu dùng NetworkManager, xem cấu hình interface và DHCP properties
nmcli device show

# Nếu hệ thống dùng systemd-resolved, xem DNS config
resolvectl status
~~~

**Cách đọc:** danh sách địa chỉ trên một máy là **local observation**. Nó không thể xác nhận prefix owner, trạng thái lease chính thức của DHCP server, identity NAC hoặc tài sản khác trên subnet. Neighbor cache có thể thiếu những endpoint im lặng hoặc chứa entry cũ, và không phải danh sách thiết bị đầy đủ.

### 17.2. Windows PowerShell

~~~powershell
# Địa chỉ IP và interface hiện tại
Get-NetIPAddress |
  Select-Object InterfaceAlias, AddressFamily, IPAddress, PrefixLength

# Các interface mạng và thông tin MAC có sẵn
Get-NetAdapter |
  Select-Object Name, Status, MacAddress, InterfaceDescription

# Route hiện có
Get-NetRoute |
  Select-Object DestinationPrefix, NextHop, InterfaceAlias

# Neighbor cache ở máy
Get-NetNeighbor |
  Select-Object InterfaceAlias, IPAddress, LinkLayerAddress, State

# DNS servers được cấu hình trên interface
Get-DnsClientServerAddress

# Tổng quan cấu hình từ ipconfig, gồm DHCP nếu interface dùng
ipconfig /all
~~~

Không nên dùng output **ipconfig /all** làm bản kiểm kê “toàn mạng”; nó chỉ cho biết thông tin client đang được cấu hình và một số thuộc tính lease, không thay được DHCP server history và IPAM.

### 17.3. Đọc thông tin Kubernetes trong cluster có quyền

~~~bash
# Liệt kê pod, node và pod IP hiện tại
kubectl get pods -A -o wide

# Liệt kê service (Service IP/VIP)
kubectl get services -A -o wide

# Liệt kê node và địa chỉ được Kubernetes quảng bá
kubectl get nodes -o wide

# Xem NetworkPolicy trong cluster
kubectl get networkpolicy -A
~~~

Những lệnh này chỉ đọc tài nguyên Kubernetes khi có quyền RBAC phù hợp. Pod IP là trạng thái hiện tại; điều tra sự kiện cũ cần **lịch sử Pod UID và event/flow telemetry** chứ không chỉ danh sách vừa truy vấn.

### 17.4. Mẫu bảng ghi kết quả thực hành

| Trường | Giá trị minh họa | Bằng chứng |
|---|---|---|
| Asset ID | lab-laptop-01 | Bản ghi quản lý lab |
| OS | Linux | Quan sát trên endpoint |
| Interface | eth0 | ip -br addr |
| IPv4 | 10.40.20.45/24 | ip -4 addr |
| IPv6 | fe80::... | ip -6 addr |
| Default gateway | 10.40.20.1 | ip route |
| DNS resolver | 10.40.1.53 | resolvectl status |
| DHCP lease | Cần đối chiếu server | DHCP lease log, không suy từ IP |
| VLAN/zone | Cần xác minh | Switch/NAC/port profile |
| Owner | Nhóm lab | Service/asset catalog |
| Evidence time | 2026-11-28T03:00:00Z | Timestamp khi quan sát |

Khi thực hành, hãy ghi **observed_at** theo thời gian thật của bài lab và đính kèm nguồn. Không chép dữ liệu thật chứa serial, định danh cá nhân, MAC, IP nội bộ hoặc thông tin nhạy cảm vào tài liệu chia sẻ công khai.

## 18. Xây bài toán đối soát trong một lab nhỏ

Giả sử một mạng lab có:

| Vùng | Prefix | Quy ước |
|---|---|---|
| Management | 10.40.99.0/24 | Thiết bị quản trị mạng |
| Staff | 10.40.20.0/24 | Máy trạm có NAC |
| Application | 10.40.30.0/24 | VM dịch vụ |
| Guest | 10.40.50.0/24 | Thiết bị khách |
| IPv6 lab | 2001:db8:40:20::/64 | Prefix minh họa |

Dữ liệu quan sát:

~~~text
DHCP log:
  09:00  10.40.20.45 -> client-id C1, lease active

NAC log:
  09:02  session N1, role Staff, device-id laptop-01

Switch log:
  09:03  MAC M1 observed at port Gi1/0/24, VLAN 20

IPAM:
  10.40.20.45 marked "reserved for retired-laptop-07"

DNS:
  retired-laptop-07.corp.example -> 10.40.20.45
~~~

**Câu hỏi:** có thể kết luận laptop-01 đã chiếm IP của retired-laptop-07 trái phép không?

**Phân tích:** chưa đủ. Reservation IPAM hoặc DNS có thể stale; lease hiện tại có thể hợp lệ nếu cấu hình reservation cũ đã được hủy nhưng IPAM chưa cập nhật. Cần kiểm tra DHCP scope/reservation thật, client ID tương ứng, MAC/DUID, thời điểm gắn identity của NAC, port switch, owner và change ticket.

**Quy trình sửa dữ liệu:** khi xác định nguồn có thẩm quyền và trạng thái đúng, cập nhật IPAM/DNS theo quy trình, giữ lịch sử của bản ghi cũ, thêm ticket và kiểm chứng lại. Nếu có dấu hiệu rogue DHCP hoặc giả mạo identity, chuyển SOC/NOC xử lý theo runbook, không tự động xóa mọi lease.

### 18.1. Một bài toán NAT trong điều tra

Firewall biên thấy **198.51.100.24:53124** gửi kết nối; phía trong NAT gateway có nhiều client. Muốn gắn sự kiện với một client phải biết **NAT mapping của source IP/port và thời gian**. Không thể lấy bảng client đang online hiện tại rồi chọn tùy ý một máy.

Dải **198.51.100.0/24** dành cho tài liệu, không đại diện một IP public hoạt động trong lab.

## 19. Bảo mật và quyền riêng tư của dữ liệu inventory

Network inventory mô tả cấu trúc hạ tầng, vị trí máy, subnet, owner, dịch vụ và quan hệ truy cập. Nếu rò rỉ, nó có thể hỗ trợ đối thủ hiểu bề mặt mạng. Một số nguồn còn chứa danh tính người dùng, thiết bị hoặc hành vi sử dụng.

### 19.1. Nguyên tắc bảo vệ inventory

1. **Least privilege:** người xem IPAM không tự có quyền sửa DHCP, DNS, firewall hay IAM.
2. **Phân tách quyền:** owner subnet, operator DHCP, admin CMDB, SOC và auditor có scope khác nhau.
3. **Xác thực nguồn thu thập:** API tokens, SNMPv3, syslog/agent trust và xác minh thiết bị gửi dữ liệu.
4. **Bảo vệ transport và storage:** mã hóa phù hợp, quản lý khóa và backup.
5. **Audit change:** ghi actor, trước/sau, lý do, thời gian, đối tượng và approval.
6. **Tối thiểu hóa PII:** chỉ lưu identity cần cho mục đích được phê duyệt, giới hạn quyền truy vấn lịch sử DHCP/VPN/NAC.
7. **Retention rõ:** giữ lịch sử đủ để điều tra theo chính sách, xóa dữ liệu hết hạn an toàn.
8. **Kiểm soát export:** tránh xuất toàn bộ topology/subnet/credential vào spreadsheet chia sẻ rộng.
9. **Bảo vệ control plane:** người sửa tag, label, DHCP reservation, DNS hoặc firewall rule có thể thay dữ liệu cần cho quyết định bảo mật.
10. **Khả năng phục hồi:** có backup, kiểm tra integrity, phục hồi sau sự cố và phát hiện ingestion bất thường.

Không lưu mật khẩu SNMP, secret API, token VPN, khóa TLS hoặc thông tin xác thực dưới dạng plaintext trong record inventory. Nên giữ **tham chiếu tới hệ thống secret quản lý phù hợp**.

### 19.2. Dữ liệu lịch sử nhạy cảm

Lịch sử **IP → user → vị trí AP/địa điểm** có thể là dữ liệu cá nhân. Phải xác định ai có quyền truy vấn, mục đích và thời hạn lưu. Đội bảo mật có thể cần dữ liệu để điều tra, nhưng điều đó không có nghĩa mọi nhóm vận hành đều phải nhìn thấy thông tin cá nhân chi tiết.

**Data minimization** và **purpose limitation** giúp kiểm soát rủi ro, đồng thời giữ đủ evidence để xác minh sự kiện theo chính sách tổ chức.

## 20. Sai lầm thường gặp

1. **Coi một IP là một thiết bị.** NAT/VIP, nhiều NIC và IP dùng lại làm mapping sai.
2. **Coi DHCP lease active là host online.** Lease có thể còn hiệu lực khi thiết bị offline.
3. **Chỉ dựa vào DHCP mà bỏ static IP và IPv6 SLAAC.** Inventory sẽ thiếu tài sản.
4. **Dùng MAC làm định danh bất biến.** MAC randomization/VM clone làm thay đổi hoặc trùng identifier.
5. **Coi DNS record là bằng chứng chủ sở hữu.** A/AAAA/PTR có thể stale hoặc trỏ VIP.
6. **Dùng IPAM làm nguồn quan sát mạng.** IPAM phản ánh planned/managed allocation, không tự thấy traffic thật.
7. **Gán user theo IP hiện tại khi điều tra log cũ.** DHCP/VPN tái sử dụng IP làm sai attribution.
8. **Không ghi routing domain/VRF/VPC.** Hai mạng private trùng IP sẽ bị gộp sai.
9. **Không tách observed_at và ingested_at.** Event đến muộn làm đảo lịch sử.
10. **Xóa record khi decommission.** Mất bằng chứng truy vết IP và thay đổi cũ.
11. **Chỉ quét chủ động để tìm tài sản.** Có nguy cơ gây tải, bỏ host im lặng và thiếu danh tính.
12. **Không giám sát chất lượng nguồn dữ liệu.** Sensor/agent offline khiến inventory “trông sạch” giả tạo.
13. **Tự tin vào hostname do client khai báo.** Có thể giả mạo, không thay xác thực.
14. **Không liên hệ owner/criticality.** Danh sách IP không giúp ưu tiên vá lỗi hoặc xử lý incident.
15. **Không phân biệt expected service và actual listener.** Một port được ghi trong CMDB chưa chắc đang open.
16. **Chỉ cập nhật thủ công theo quý cho cloud/pod.** Tài nguyên tồn tại ngắn và nhiều thay đổi bị bỏ sót.
17. **Không quản lý quyền sửa tag/label.** Actor có thể tự gán nhãn để đi qua security policy dựa trên identity.
18. **Chỉ đếm số bản ghi làm coverage.** Một tài sản có thể có nhiều IP, một IP đại diện nhiều backend.
19. **Thiếu kiểm soát riêng tư.** Lịch sử IP/VPN/Wi-Fi có thể gắn với danh tính và vị trí.
20. **Cho rằng inventory chính là enforcement.** Kiểm kê phát hiện và hỗ trợ policy; firewall/NAC/OS/app mới thực thi quyền khi được cấu hình đúng.

## 21. Bài tập phân tích có đáp án gợi ý

### Tình huống A — Lease cấp lại, SOC truy sai máy

Một log lúc 09:10 ghi 10.40.20.45 kết nối tới DB; dashboard hiện tại lúc 13:00 nói IP đó thuộc Máy B.

**Gợi ý:** tra DHCP/VPN/NAC history tại **09:10**, kèm VRF và NAT mapping nếu có. Không dùng owner hiện tại để gán log quá khứ. Nếu không đủ evidence, ghi attribution **unresolved**, không đoán.

### Tình huống B — Thiết bị không có DHCP record

Firewall nhìn thấy một máy dùng 10.40.99.25, nhưng DHCP server không có lease.

**Gợi ý:** có thể là IP tĩnh hợp lệ của thiết bị quản trị, địa chỉ cloud static, hoặc một thiết bị ngoài policy. Kiểm tra IPAM reservation, switch port, interface, device owner và dấu hiệu chống spoofing; thiếu DHCP lease không tự chứng minh rogue device.

### Tình huống C — IPv6 ngoài danh sách

Host có một IPv4 được quản lý và một vài IPv6 temporary addresses; IPAM chỉ có IPv4.

**Gợi ý:** xác định IPv6 prefix/router, nguồn SLAAC/RA, endpoint identity và chính sách firewall IPv6. Không yêu cầu DHCPv6 lease cho địa chỉ sinh bằng SLAAC rồi kết luận nó giả mạo.

### Tình huống D — VPC trùng subnet

Hai VPC độc lập đều dùng 10.40.20.0/24; cloud API trả cùng địa chỉ 10.40.20.42 cho hai VM khác nhau.

**Gợi ý:** khóa IP phải bao gồm **VPC/VRF/routing domain và valid interval**. Không gộp VM chỉ vì IP giống nhau. Ghi riêng cloud resource ID và account/region.

### Tình huống E — Cloud VM có public IP mới

Một VM production vừa được cấp public IP, trong khi service catalog ghi “internal only”.

**Gợi ý:** xác minh subnet, route, internet gateway, security group, load balancer, firewall và owner. Public IP assignment là tín hiệu cần review, không tự chứng minh đã có truy cập Internet hoặc vi phạm dữ liệu.

### Tình huống F — DNS PTR còn tên máy cũ

IP 10.40.20.45 đã cấp cho laptop mới, nhưng PTR trả retired-laptop-07.corp.example.

**Gợi ý:** cần kiểm tra dynamic DNS update, TTL, quyền sửa zone, lease và CMDB trước khi cập nhật DNS. PTR là dữ liệu phân giải tên, không phải định danh tuyệt đối.

### Tình huống G — Guest Wi-Fi bị nhận nhầm nhân viên

Một thiết bị dùng MAC randomization, được thấy ở Guest rồi Staff SSID tại thời điểm khác nhau.

**Gợi ý:** không ghép hai MAC chỉ bằng phỏng đoán. Dùng xác thực 802.1X, device ID, MDM, AP session và timestamp, đồng thời bảo vệ quyền riêng tư.

### Tình huống H — Pod đổi IP sau triển khai

Một alert NIDS lúc 10:00 gắn IP 10.244.2.15; lúc 11:00 IP đó đã thuộc pod khác.

**Gợi ý:** tìm Kubernetes Pod UID/owner/namespace/node và thời gian tồn tại tại 10:00, kết hợp CNI flow logs. Không quy alert cho pod hiện tại.

### Tình huống I — IPAM và DHCP báo hai owner

IPAM ghi một địa chỉ dành cho server, DHCP báo laptop được cấp cùng địa chỉ.

**Gợi ý:** ưu tiên điều tra cấu hình reservation/scope, routing domain, mốc thời gian, lịch thay đổi và owner. Không tự cập nhật owner theo bản ghi mới nhất mà không có kiểm chứng.

### Tình huống J — Firewall rule cũ chưa được gỡ

Một subnet ứng dụng đã ngừng sử dụng, nhưng firewall vẫn cho subnet đó truy cập DB.

**Gợi ý:** dùng IPAM, network inventory, flow logs và change tickets xác định subnet đã thực sự hết dependency; có owner phê duyệt thu hồi rule và kiểm thử cả luồng allow/deny sau thay đổi.

## 22. Checklist triển khai và duy trì Network inventory

- [ ] Đã xác định scope gồm on-prem, Wi-Fi, VPN, cloud, Kubernetes và vùng ngoại lệ.
- [ ] Có entity model riêng cho asset, interface, IP assignment, subnet, DNS và service.
- [ ] Dùng asset ID ổn định, không dùng IP/MAC/hostname làm ID duy nhất mặc định.
- [ ] Ghi routing domain/VRF/VPC/tenant, IP version và thời gian hiệu lực cho IP.
- [ ] Có dữ liệu DHCPv4/DHCPv6, static IP, SLAAC IPv6 và network attachment khi cần.
- [ ] Lưu cả DHCP lease start/end, observed_at, ingested_at và các nguồn evidence.
- [ ] Đối soát DNS A/AAAA/PTR, reservations, IPAM, DHCP và owner.
- [ ] Có nguồn từ switch/LLDP/ARP/ND, NAC, AP, VPN, firewall, EDR và cloud API theo khả năng.
- [ ] Xác định source of authority cho từng nhóm thuộc tính; không áp last-writer-wins tùy tiện.
- [ ] Có cơ chế xử lý duplicate, conflict, stale record và orphan asset.
- [ ] Có tag environment, criticality, business service, owner, lifecycle và network zone.
- [ ] Kiểm kê được VIP/load balancer/NAT/public endpoint, không chỉ máy chủ.
- [ ] Có bản ghi cloud instance/pod/service theo thời gian thay đổi, đặc biệt tài nguyên ngắn hạn.
- [ ] Theo dõi coverage, completeness, freshness, accuracy và discovery latency.
- [ ] Có quy trình onboarding, change, migration và decommission có audit.
- [ ] Có thể gắn firewall/VPN/NIDS alert với tài sản đúng **thời điểm sự kiện** hoặc ghi unresolved.
- [ ] Kết hợp inventory để kiểm chứng phân đoạn, egress, rule và policy giữa các zone.
- [ ] Có kiểm soát chống rogue DHCP/spoofing và quyền sửa network control plane khi cần.
- [ ] Bảo vệ dữ liệu inventory và lịch sử identity bằng quyền truy cập, encryption và retention.
- [ ] Có người chịu trách nhiệm review chất lượng dữ liệu và xử lý exception.

## 23. Tổng kết

**Network inventory** là mô hình đang được duy trì về **tài sản, địa chỉ, đường kết nối và trách nhiệm vận hành**, có nguồn bằng chứng và thời gian hiệu lực rõ ràng. Trong bài toán **DHCP và IP management**, nó liên kết IPAM, DHCP lease, DNS, VLAN, switch/AP, NAC, VPN, cloud và Kubernetes thay vì chỉ lưu một bảng IP–hostname dễ lỗi thời.

Giá trị bảo mật xuất hiện khi inventory được dùng để **xác định đúng chủ thể ở đúng thời điểm, tìm tài sản chưa quản trị, kiểm chứng phân đoạn/firewall, thu hẹp quyền kết nối, ưu tiên giám sát IDS/IPS và hỗ trợ điều tra**. Muốn đạt kết quả đáng tin, phải bảo toàn lịch sử, đối soát nhiều nguồn, quản lý dữ liệu nhạy cảm và đo chất lượng liên tục. Network inventory không thay thế các cơ chế enforcement; nó cung cấp bức tranh và bằng chứng để những cơ chế đó được thiết kế và vận hành đúng.
