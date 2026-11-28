# Address allocation theo zone trong DHCP và IP Address Management

Một doanh nghiệp có mạng nhân viên, Wi-Fi dành cho khách, thiết bị IoT, máy chủ nội bộ và mạng quản trị. Nếu mọi thiết bị được cấp địa chỉ tùy ý trong cùng một dải, quản trị viên sẽ khó xác định tài sản đang thuộc ranh giới nào, việc áp firewall rule dễ nhầm và một cấu hình DHCP sai có thể khiến máy khách nhận gateway hoặc DNS không phù hợp. Ngược lại, nếu mỗi vùng có kế hoạch địa chỉ và chính sách cấp phát được quản trị rõ ràng, hệ thống dễ mở rộng, vận hành và điều tra sự cố hơn.

**Address allocation theo zone** là thiết kế và vận hành quá trình gán địa chỉ IP, subnet, gateway, DNS và vòng đời lease theo các miền được xác định trước, có thể là **security zone, VLAN, subnet, VRF, tenant hoặc địa điểm**. Chủ đề thuộc chương **DHCP và IP management** trong module **SECURITY_NETWORK_SECURITY**. Nó liên kết quản lý địa chỉ với phân đoạn, firewall, xác thực kết nối/NAC, VPN, IDS/IPS, DNS, mạng không dây, cloud và threat modeling nhằm tạo kiến trúc mạng an toàn, có khả năng kiểm chứng.

**Nguyên tắc cốt lõi:** địa chỉ IP là thông tin định tuyến và quản trị tài nguyên; **nhận được IP từ một pool không phải bằng chứng người dùng hay thiết bị đã được xác thực hoặc được phép truy cập dữ liệu**. Zone cần được bảo vệ bằng mạng, danh tính và quyền truy cập ở những lớp thích hợp.

## 1. Zone là gì trong bài toán cấp phát địa chỉ?

Từ *zone* có thể mang ý nghĩa khác nhau tùy thiết kế:

| Khái niệm | Ý nghĩa | Quan hệ với cấp địa chỉ |
|---|---|---|
| **Security zone** | Nhóm tài sản có mức tin cậy và chính sách lưu lượng tương tự | Xác định ai được liên lạc với ai, nhưng không nhất thiết tương đương một subnet |
| **VLAN** | Miền broadcast Ethernet có định danh VLAN | Thường gắn với một hoặc nhiều IPv4 subnet; DHCP broadcast nằm trong miền L2 trừ khi được relay |
| **IP subnet/prefix** | Tập địa chỉ có cùng tiền tố mạng | Cơ sở để tạo DHCP scope/pool và chọn gateway |
| **VRF/routing domain** | Bảng định tuyến riêng, giúp cô lập đường đi IP | Cùng giá trị IP có thể xuất hiện ở VRF khác nhau nếu đã thiết kế giải quyết chồng lấn |
| **Tenant** | Đơn vị khách hàng/tổ chức có ranh giới dữ liệu và quyền riêng | Cần ánh xạ tenant tới vùng mạng và identity; một tenant có thể có nhiều subnet |
| **Site/region** | Văn phòng, trung tâm dữ liệu hoặc cloud region | Quy hoạch prefix theo địa điểm giúp định tuyến và tổng hợp tuyến |
| **DHCP scope** | Tập cấu hình cho một mạng: pool, option, lease policy | Thường gắn với subnet/relay association, không tự tạo firewall zone |
| **IPAM** | Hệ thống quản lý địa chỉ, prefix, subnet, trạng thái và owner | Nguồn quản trị địa chỉ để phát hiện trùng lặp, cấp phát và kiểm toán |

Một mô hình đơn giản có thể ánh xạ **một VLAN ↔ một subnet ↔ một security zone**, nhưng đó là quyết định thiết kế, không phải đặc tính bắt buộc của các công nghệ. Một security zone có thể gồm nhiều VLAN/site; một subnet trên hạ tầng ảo hóa có thể chứa những nhóm workload cần thêm microsegmentation.

### 1.1. Mục tiêu thiết kế

1. **Không trùng địa chỉ** trong cùng miền định tuyến và không cấp phát địa chỉ đã dành riêng.
2. **Cấp đúng cấu hình cho đúng miền**: subnet mask/prefix, default gateway, DNS, lease lifetime và các option cần thiết.
3. **Hạn chế blast radius**: cấu hình sai hoặc quá tải tại guest zone không ảnh hưởng không cần thiết tới management/server zone.
4. **Hỗ trợ chính sách mạng**: firewall, ACL, VPN/VRF và DNS có thể tham chiếu các prefix/nhóm tài sản đúng.
5. **Có truy vết**: biết ai/cái gì sử dụng địa chỉ nào, ở zone nào và trong khoảng thời gian nào với bằng chứng phù hợp.
6. **Có khả năng phát triển**: đủ địa chỉ khi thêm thiết bị, Wi-Fi, tenant, chi nhánh hoặc workload mới.

## 2. Kiến trúc mẫu: nhiều zone, một dịch vụ DHCP có kiểm soát

Giả sử một doanh nghiệp có core routing/firewall, switch access và DHCP tập trung. Thiết kế minh họa dưới đây dùng các dải địa chỉ riêng do doanh nghiệp quản lý.

~~~mermaid
flowchart TB
    subgraph L2["Các miền kết nối / access"]
        E["Employee VLAN 110"]
        G["Guest Wi-Fi VLAN 120"]
        I["IoT VLAN 130"]
        S["Server VLAN 140"]
        M["Management VLAN 150"]
    end
    subgraph BOUNDARY["Trust boundary: core / firewall / L3 gateway"]
        GW["L3 interfaces, VRF, DHCP relay và firewall policies"]
    end
    subgraph CONTROL["Control plane và hệ thống cấp phát"]
        D["DHCPv4/DHCPv6 services"]
        IPAM["IPAM: prefix, zone, reservations, owner"]
        DNS["Internal DNS / DDNS khi được phép"]
        LOG["Lease, relay và audit logs"]
    end
    E --> GW
    G --> GW
    I --> GW
    S --> GW
    M --> GW
    GW -->|"DHCP relay / controlled paths"| D
    IPAM -->|"Approved allocations / change workflow"| D
    D -.->|"Lease records"| LOG
    D -.->|"Authorized DNS changes"| DNS
~~~

Sơ đồ là **kiến trúc logic**, không phải yêu cầu tất cả zone đều dùng DHCP động. Ví dụ server và management có thể ưu tiên địa chỉ tĩnh hoặc reservation, còn employee/guest chủ yếu dùng pool động. Với nhiều VRF, relay, DHCP server và đường quản trị phải có route/khả năng nhận diện phạm vi độc lập; một server tập trung không tự vượt được ranh giới định tuyến.

### 2.1. Các trust boundary cần đánh dấu

- **Endpoint ↔ access network:** thiết bị gửi broadcast DHCP chưa chắc đã được xác thực; NAC 802.1X, chính sách switch và Wi-Fi có thể quyết định VLAN hoặc quyền trước/sau khi cấp IP.
- **VLAN/subnet ↔ gateway/firewall:** gateway xác định đường đi và enforcement L3/L4; muốn guest không vào server cần rule phù hợp, **không chỉ subnet khác nhau**.
- **Gateway/relay ↔ DHCP service:** chỉ relay hợp lệ được phép chuyển yêu cầu tới service; metadata relay cần được đánh giá theo nguồn đáng tin.
- **DHCP ↔ IPAM/DNS:** hệ thống cập nhật lease, reservation hoặc bản ghi DNS cần quyền tối thiểu, không cho phép client tự đổi zone chỉ bằng cách khai báo tên.
- **Operator/automation ↔ control plane:** quyền tạo scope, đổi option gateway/DNS hoặc gán pool management là quyền nhạy cảm, phải audit và kiểm soát thay đổi.

## 3. Quy hoạch prefix theo zone có kiểm chứng

### 3.1. Một bảng phân bổ IPv4 mẫu

Ví dụ tổ chức được cấp quyền dùng khối private **10.48.0.0/16** trong mạng riêng. Các zone được phân bổ:

| Zone | VLAN mẫu | Subnet | Số host IPv4 thông thường | Gateway mẫu | Cách cấp phát |
|---|---:|---|---:|---|---|
| Employee | 110 | `10.48.10.0/24` | 254 | `10.48.10.1` | DHCP pool + một số reservation |
| Guest | 120 | `10.48.20.0/23` | 510 | `10.48.20.1` | DHCP động, lease ngắn hơn |
| IoT | 130 | `10.48.30.0/24` | 254 | `10.48.30.1` | Reservation hoặc pool có kiểm soát |
| Servers | 140 | `10.48.40.0/26` | 62 | `10.48.40.1` | Tĩnh/IPAM hoặc reservation |
| Management | 150 | `10.48.50.0/26` | 62 | `10.48.50.1` | Tĩnh hoặc reservation với quyền cao |
| DMZ | 160 | `10.48.60.0/27` | 30 | `10.48.60.1` | Tĩnh/reservation theo dịch vụ |

Đây là **kế hoạch minh họa**, không phải cấu hình đề nghị áp lên một tổ chức cụ thể. Các prefix ở bảng không chồng lấn. Phải kiểm tra cả phần còn lại của `10.48.0.0/16`, các site/VRF được nối, VPN, cloud peering và đối tác trước khi chọn dải thật.

Với mạng IPv4 thông thường:

\[
\text{Tổng địa chỉ trong IPv4 /p} = 2^{32-p}.
\]

Với **/24**, có 256 địa chỉ; địa chỉ mạng và broadcast không dùng làm host trong subnet Ethernet IPv4 thông thường, còn **254 địa chỉ host tiềm năng**, trước khi trừ gateway, reservation và exclusion. Với **/23**, có 512 địa chỉ, thường 510 host; `10.48.20.0/23` kéo dài tới `10.48.21.255`, với network address `10.48.20.0` và broadcast `10.48.21.255`.

Một chi tiết dễ nhầm: **`10.48.20.255` và `10.48.21.0` đều có thể là địa chỉ host hợp lệ trong subnet /23 này**. Không coi mọi địa chỉ có octet cuối bằng 0 hoặc 255 đều là network/broadcast mà bỏ qua prefix length.

### 3.2. Subnet size khác DHCP pool size

Cho Employee /24:

~~~text
Subnet:            10.48.10.0/24
Network address:   10.48.10.0
Gateway:           10.48.10.1
Reserved infra:    10.48.10.2 - 10.48.10.49
DHCP pool:         10.48.10.100 - 10.48.10.230
Other excluded:    10.48.10.50 - 10.48.10.99,
                   10.48.10.231 - 10.48.10.254
Broadcast:         10.48.10.255
~~~

Pool ví dụ từ `.100` tới `.230` có:

\[
230 - 100 + 1 = 131\ \text{địa chỉ}.
\]

Không phải 254 địa chỉ host của /24 đều được cấp qua DHCP. Một phần đã dành cho gateway, thiết bị mạng, hệ thống cần địa chỉ ổn định, vùng dự phòng và cơ chế cấp phát khác. Trên thực tế cần tránh tạo **lỗ trống không có chủ sở hữu**: mọi dải excluded/reserved nên được ghi nhận trong IPAM, kể cả khi chưa có thiết bị sử dụng.

### 3.3. Tiêu chí chọn prefix

- **Số endpoint đồng thời**, dự báo tăng trưởng và khả năng thêm access point/thiết bị.
- **DHCP lease duration** và tốc độ thiết bị thay đổi ở employee, guest, IoT.
- **Định tuyến:** khả năng tổng hợp route theo site/zone, giới hạn broadcast, kiến trúc VRF.
- **Phân đoạn:** nhóm thiết bị có mức tin cậy khác nhau không nên bị gộp chỉ vì đủ IP.
- **Kết nối hybrid:** dải có đụng với cloud, VPN client, đối tác, container hay mạng nhà nhân viên không?
- **Hạ tầng cloud:** một số nền tảng dự trữ địa chỉ riêng trong mỗi subnet; **không lấy công thức host IPv4 thông thường làm số IP cloud có thể cấp** khi provider có quy tắc khác.

Không nên tạo subnet quá lớn chỉ để đỡ quản trị scope, vì nó có thể tăng blast radius, broadcast domain hoặc độ phức tạp của chính sách truy cập.

## 4. Cách gán địa chỉ theo từng zone

| Phương pháp | Cách hoạt động | Zone phù hợp | Điều cần kiểm soát |
|---|---|---|---|
| **DHCP dynamic lease** | Chọn địa chỉ trong pool rồi cấp một lease có thời hạn | Employee, guest và nhóm thiết bị thay đổi | Pool capacity, conflict, renewal, options |
| **DHCP reservation** | Server ưu tiên địa chỉ định trước theo identifier của client | Printer, IoT, thiết bị cần IP ổn định | Identifier có thể thay đổi/giả mạo; inventory và bảo vệ truy cập |
| **Static manual** | IP được cấu hình trực tiếp trên thiết bị/workload | Network appliance, server, một số management device | Phải đăng ký IPAM, tránh cấp trùng trong pool |
| **Orchestrator/cloud-managed** | Cloud/VPC, hypervisor hoặc nền tảng container tự quản lý địa chỉ | VM, pod, managed service | Đồng bộ trạng thái IPAM và quyền control plane |
| **SLAAC/DHCPv6** | IPv6 address từ RA/SLAAC và/hoặc DHCPv6 tùy kiến trúc | Endpoint IPv6, network dual stack | RA guard, prefix, DUID, privacy address, policy L3/L4 |

**DHCP reservation không phải cơ chế xác thực mạnh.** Với DHCPv4, reservation thường ánh xạ identifier hoặc MAC được client trình bày; những thuộc tính đó có thể bị thay đổi/giả mạo trong một số điều kiện. Không mở quyền quản trị chỉ vì IP tương ứng một reservation; cần NAC, danh tính thiết bị, mTLS, firewall và quản trị cấu hình.

### 4.1. Mục đích và thời hạn lease khác nhau

| Zone | Đặc tính | Xu hướng chính sách hợp lý |
|---|---|---|
| Employee | Máy được quản lý, di chuyển giữa văn phòng và Wi-Fi | Lease vừa phải, kiểm tra thay đổi mạng/NAC |
| Guest | Thiết bị đến và đi nhanh, lượng kết nối biến động | Lease ngắn hơn và pool đủ rộng; cân nhắc tác động renew |
| IoT | Thiết bị ít di chuyển, firmware khác nhau | Reservation hoặc nhóm scope có kiểm soát; giám sát sai loại thiết bị |
| Server | Địa chỉ cần dễ tra cứu để backup, ACL và dịch vụ | Static/reservation + IPAM change control |
| Management | Quyền và ảnh hưởng rất cao | Phạm vi ít biến động, cấm cấp tùy tiện, phân đoạn mạnh |

Không có một lease lifetime lý tưởng cho mọi hệ thống. Lease ngắn giúp thu hồi địa chỉ nhanh hơn khi thiết bị rời mạng, nhưng tăng DHCP traffic và phụ thuộc availability của server/relay. Lease dài giảm renew nhưng có thể giữ IP cho thiết bị đã rời zone. Thời gian phù hợp phải được kiểm thử với tải và chu kỳ thiết bị thật.

## 5. DHCPv4 nhận biết scope của client như thế nào?

### 5.1. DORA trong cùng mạng

Với một client IPv4 chưa có địa chỉ, vòng đời cơ bản thường bắt đầu bằng:

~~~mermaid
sequenceDiagram
    participant C as DHCP client
    participant R as L2 / L3 gateway / relay
    participant D as DHCPv4 server
    C->>R: DHCPDISCOVER (broadcast trong access VLAN)
    R->>D: Chuyển tiếp nếu cần, gắn thông tin relay
    D-->>R: DHCPOFFER (địa chỉ và options)
    R-->>C: Chuyển offer tới client
    C->>R: DHCPREQUEST (yêu cầu lựa chọn)
    R->>D: Chuyển tiếp request
    D-->>R: DHCPACK (xác nhận lease)
    R-->>C: Chuyển lease và options
~~~

**DORA** là Discover → Offer → Request → Acknowledge. Sơ đồ có relay để minh họa DHCP tập trung; nếu server ở cùng broadcast domain, các bước qua relay có thể không xảy ra. DORA không bao quát hết các thông điệp DHCP như NAK, DECLINE, RELEASE, INFORM hay quá trình renew/rebind.

Client thường cần những thông tin:

- Địa chỉ IPv4 và subnet mask.
- Default router/gateway (DHCP Option 3 khi dùng).
- DNS recursive server (Option 6), tên miền tìm kiếm khi thích hợp.
- Lease time (Option 51) và thông tin server/renewal liên quan.
- Những option bổ sung chỉ khi có nhu cầu và thiết bị hỗ trợ, ví dụ PXE/VoIP.

Sai **gateway hoặc DNS option** có thể làm một client nhận IP hợp lệ nhưng không truy cập đúng dịch vụ, không phân giải được tên nội bộ hoặc đi nhầm đường ra Internet.

### 5.2. Vai trò của DHCP relay và `giaddr`

DHCPDISCOVER kiểu broadcast của client thông thường **không tự vượt router**. Khi DHCP server ở zone khác, thiết bị L3 hoặc dịch vụ relay được cấu hình chuyển tiếp gói qua mạng định tuyến.

Ở DHCPv4, trường **`giaddr` (gateway IP address)** được relay dùng theo quy tắc giao thức; server thường dựa vào nó, hoặc các thông tin link/relay theo khả năng của hệ thống, để xác định subnet/scope tương ứng. Ví dụ:

~~~text
Client:    trong Employee VLAN 110, chưa có IP
Relay:     SVI Employee 10.48.10.1
giaddr:    10.48.10.1 (theo luồng relay thông thường)
Server:    ánh xạ subnet 10.48.10.0/24 -> pool Employee
Offered:   10.48.10.118/24, router 10.48.10.1
~~~

Nếu relay gửi `giaddr` không đúng, hoặc DHCP server không có scope khớp, client có thể không nhận offer hoặc nhận chính sách ngoài ý định, tùy sản phẩm. Với **VRF**, cần xem đường giữa relay và server, địa chỉ source, routing instance, lựa chọn relay và cách server phân biệt mạng trùng lắp.

### 5.3. DHCP Option 82 và ngữ cảnh cổng truy cập

**Relay Agent Information Option (Option 82)** có thể bổ sung thông tin như *circuit ID* và *remote ID* để hỗ trợ chính sách theo vị trí hoặc nguồn kết nối. Trong một số hệ thống, switch access/relay cung cấp thông tin về VLAN, port hoặc circuit, rồi DHCP server áp điều kiện phân loại pool.

Tuy nhiên:

1. Option 82 là **metadata do relay/network element đưa vào**, không phải chứng chỉ danh tính người dùng.
2. Phải phân biệt **cổng tin cậy** và metadata đến từ client/uplink không được phép giả mạo.
3. Cách insert, replace, strip, forward và xử lý Option 82 khác nhau theo vendor/cấu hình.
4. Không để một giá trị circuit ID chưa xác minh tự cấp quyền vào security zone nhạy cảm.
5. Nếu access switch đổi cấu hình hoặc chuyển trunk/VLAN, mapping Option 82 ↔ zone có thể sai dù IPAM vẫn giữ dữ liệu cũ.

**Ví dụ lỗi:** switch guest gửi metadata bị ánh xạ nhầm sang server scope. Đó là sai sót **control plane/relay policy**; không giải quyết chỉ bằng tăng pool size.

## 6. Đúng zone phải được xác định từ đâu?

Trong mạng doanh nghiệp, nguồn ánh xạ vùng nên được phân lớp:

~~~mermaid
flowchart TD
    A["Thiết bị kết nối cổng/sóng Wi-Fi"] --> B["Switch / AP / NAC kiểm tra chính sách"]
    B --> C["VLAN, VRF hoặc access role có thẩm quyền"]
    C --> D["L3 gateway / DHCP relay"]
    D --> E["DHCP server: chọn scope theo link + relay policy"]
    E --> F["Cấp IP, gateway, DNS và lease"]
    F --> G["Firewall/ACL tiếp tục thực thi quyền kết nối"]
    B -.->|"Identity/role được xác minh khi có"| G
~~~

Đường đi phụ thuộc hệ thống NAC. Trong mô hình **802.1X/EAP-TLS**, thiết bị có thể được kiểm chứng bằng chứng chỉ và switch/AP nhận policy từ hệ thống AAA/RADIUS, sau đó gán VLAN/dynamic ACL theo quyền đã cấp. Trong một số chế độ guest/captive portal, client có thể nhận IP trước khi hoàn tất xác thực ứng dụng. Vì vậy **trình tự “xác thực trước DHCP” không phải quy luật tuyệt đối**.

Những điểm không nên coi là bằng chứng quyền:

- Client tự đặt tên hostname `server-admin` trong DHCP.
- MAC/Client Identifier khai báo khớp một reservation.
- Địa chỉ IP trông giống management prefix nhưng client tự đặt tĩnh.
- DHCP Option 82 đi vào từ cổng không đáng tin.
- DNS trả hostname nội bộ hoặc DHCP server cấp đúng IP.

Quyền nên được thực thi bằng **NAC, segmentation, firewall, identity và application authorization**, có đối chiếu với trạng thái IPAM/lease như dữ liệu hỗ trợ điều tra.

### 6.1. DHCP snooping bảo vệ đường cấp phát

Trên switch hỗ trợ **DHCP snooping**, ta có thể đánh dấu các cổng được tin cậy nhận phản hồi từ DHCP server/relay và chặn những phản hồi cấp phát đến từ cổng user không được phép. DHCP snooping có thể tạo binding table liên hệ MAC, IP, VLAN và port để hỗ trợ **Dynamic ARP Inspection (DAI)** hoặc **IP Source Guard** khi sản phẩm hỗ trợ.

Nhưng cần phân biệt:

- **Trusted port phải chọn đúng**: đánh dấu nhầm cổng user là trusted có thể cho phép rogue server phát offer.
- **Binding table là trạng thái vận hành**, có thể bị thiếu khi switch khởi động lại hoặc với thiết bị dùng static IP nếu chưa tạo binding tĩnh.
- DHCP snooping **không tự xác thực người dùng hoặc chặn toàn bộ traffic IP**; policy 802.1X, VLAN, ACL và firewall vẫn cần thiết.
- Với DHCP relay phân tán, Option 82 và xử lý gói trên trunk/uplink phải được kiểm tra end-to-end theo tài liệu thiết bị.

## 7. IPAM: nguồn quản trị cho prefix và trạng thái địa chỉ

**IP Address Management (IPAM)** phải trả lời nhất quán: prefix nào thuộc zone nào, được cấp cho hệ thống nào, ai chịu trách nhiệm, IP nào đang sử dụng, IP nào reserved và hệ thống nào thực sự cấp lease.

### 7.1. Mô hình dữ liệu IPAM đề nghị

| Thuộc tính | Ví dụ | Tại sao cần |
|---|---|---|
| Prefix/subnet | `10.48.10.0/24` | Phát hiện trùng/chồng lấn |
| Site, VRF, zone, VLAN | `HCM-DC`, `corp-vrf`, Employee, `110` | Biết ranh giới định tuyến và quyền |
| Gateway, DNS, DHCP relay | `10.48.10.1`, resolver nội bộ, relay ID | Phát hiện cấu hình sai option/path |
| Pool và exclusions | `.100-.230`, dải reserved | Không cấp đè IP cố định |
| Lease/reservation status | active, reserved, available, deprecated | Phân biệt trạng thái được kỳ vọng và quan sát |
| Asset ID, owner | `laptop-001`, team IT | Hỗ trợ điều tra và thay đổi |
| Change ticket và thời gian | `NET-CHG-042`, timestamp | Truy vết ai đã đổi prefix/scope |
| Source of truth | DHCP service, cloud VPC, orchestrator, IPAM | Tránh ghi đè lẫn nhau giữa công cụ |
| Security policy references | Zone rule set, NAC group | Đối chiếu đường kết nối với mục đích cấp phát |

Không phải IPAM nào cũng là **nguồn sự thật duy nhất cho mọi chi tiết vận hành**. Lease hiện tại có thể nằm trên DHCP server; mạng cloud/VM và container có control plane riêng. Thiết kế phải chỉ rõ **trường nào do hệ thống nào có quyền ghi**, cơ chế đồng bộ và cách xử lý dữ liệu không khớp.

### 7.2. Ví dụ đặc tả zone allocation (không phải file cấu hình DHCP chạy được)

~~~yaml
# Pseudo-policy phục vụ thiết kế/review, không thuộc schema của DHCP product.
zone: employee
site: hcm-campus
vrf: corp
vlan: 110
ipv4:
  prefix: 10.48.10.0/24
  gateway: 10.48.10.1
  allocationMode: dynamic-with-approved-reservations
  poolStart: 10.48.10.100
  poolEnd: 10.48.10.230
  leasePolicy: calibrated-from-usage
dns:
  resolvers: ["10.48.0.53", "10.48.0.54"]
  searchDomain: corp.example.test
relay:
  expectedLink: employee-vlan110
security:
  nacRole: managed-employee
  firewallZone: employee
  allowDirectToManagement: false
management:
  owner: network-platform-team
  changeApprovalRequired: true
~~~

`10.48.0.53` và `10.48.0.54` là **resolver giả định**: chỉ hoạt động nếu đã triển khai, có route và được firewall cho phép. `allowDirectToManagement: false` là **ý định chính sách**, không tự cấu hình firewall. Không copy pseudo-policy này vào Kea, Windows DHCP, dnsmasq hay thiết bị mạng rồi kỳ vọng engine nhận.

### 7.3. Quy trình quản trị thay đổi

~~~mermaid
flowchart LR
    NEED["Yêu cầu zone, subnet hoặc thiết bị mới"] --> REVIEW["Kiểm tra inventory, route, VRF, xung đột"]
    REVIEW --> APPROVE["Owner + security review/approval"]
    APPROVE --> IPAM["Reserve prefix/pool và version hóa"]
    IPAM --> APPLY["Cập nhật DHCP, relay, DNS, firewall/NAC"]
    APPLY --> TEST["Positive/negative tests và audit"]
    TEST --> SYNC["Reconcile leases, IPAM và cloud inventory"]
~~~

Nếu thay VLAN hay đưa client sang zone mới, cần xem cả **địa chỉ cũ/lease cũ, DNS cache, firewall session, route và trạng thái NAC**. Một thiết bị có thể giữ IP cũ trong thời gian ngắn sau khi chuyển mạng; không được coi lease cũ là bằng chứng hiện tại về zone.

## 8. IPv6: không bê nguyên mô hình DHCPv4 sang

Trong mạng IPv6, thiết bị có thể nhận địa chỉ qua **SLAAC (Stateless Address Autoconfiguration)** sử dụng thông tin Router Advertisement (RA), qua **stateful DHCPv6**, hoặc kết hợp những cơ chế tùy mạng và client. DHCPv6 cũng có thể cung cấp một số option khác, nhưng **default router của IPv6 thông thường được học từ RA**, không phải từ DHCPv6 như DHCPv4 Option 3.

### 8.1. Quy hoạch prefix IPv6 theo zone

Giả sử mạng lab có khối tài liệu `2001:db8:48::/48`, có thể hình dung phân cấp:

~~~text
Employee:   2001:db8:48:110::/64
Guest:      2001:db8:48:120::/64
IoT:        2001:db8:48:130::/64
Servers:    2001:db8:48:140::/64
Management: 2001:db8:48:150::/64
~~~

`2001:db8::/32` là prefix **chỉ dành cho tài liệu**, không dùng để định tuyến Internet. Trong triển khai thực, dùng prefix được ISP/RIR hoặc hạ tầng tổ chức cấp; có thể dùng ULA `fc00::/7` theo quy trình phù hợp cho những mạng nội bộ. **/64** là kích thước subnet phổ biến cho mạng LAN hỗ trợ SLAAC; không lấy số địa chỉ khả dụng khổng lồ làm lý do bỏ qua quản trị endpoint.

### 8.2. Router Advertisement và DHCPv6

| Thành phần | Vai trò | Lỗi dễ gặp |
|---|---|---|
| **RA / ICMPv6** | Cung cấp router mặc định và thông tin prefix/flag | Rogue RA chỉ sai gateway/prefix, hoặc chặn ICMPv6 làm lỗi hoạt động |
| **SLAAC** | Thiết bị tự tạo địa chỉ theo prefix và thuật toán của nó | Client dùng privacy/temporary address; IP đổi theo thời gian |
| **DHCPv6 stateful** | Cấp địa chỉ/option theo hỗ trợ client và chính sách | Client khác nhau về hỗ trợ; không thay vai trò default router của RA |
| **DHCPv6 stateless** | Cấp option bổ sung khi địa chỉ được tạo qua cơ chế khác | Không phải mọi client đều dùng DHCPv6 cho DNS |
| **DHCPv6 relay** | Chuyển yêu cầu giữa link/zone và DHCPv6 server | Cần đúng link/context, route và policy |
| **Prefix Delegation (PD)** | Cấp prefix cho router/CPE để chia tiếp cho mạng phía sau | Cần theo dõi phân cấp prefix, thu hồi và thay đổi prefix |

Hai flag **M (Managed)** và **O (Other configuration)** trong RA thể hiện tín hiệu mong muốn về DHCPv6, nhưng hành vi thực tế còn phụ thuộc hệ điều hành/thiết bị. Không giả định mọi thiết bị (đặc biệt nhóm mobile/IoT) đều hỗ trợ stateful DHCPv6 giống nhau. Thiết kế nên kiểm thử từng loại client quan trọng.

### 8.3. Bảo mật IPv6 theo zone

- **RA Guard** trên switch hỗ trợ có thể giúp ngăn RA trái phép từ cổng endpoint; cần kiểm chứng giới hạn xử lý/thiết bị và không xem nó bảo vệ mọi hình thức ND spoofing.
- **DHCPv6 Guard**, ND inspection và cơ chế bảo vệ IPv6 ở access layer có thể hỗ trợ tùy nhà sản xuất.
- **IPv6 ACL/firewall** phải có chính sách riêng; chặn IPv4 guest → management không tự chặn IPv6 tương ứng.
- Không chặn toàn bộ **ICMPv6** chỉ vì muốn giảm bề mặt tấn công: Neighbor Discovery, Path MTU Discovery và những chức năng mạng khác cần các loại ICMPv6 phù hợp.
- Lưu **prefix, địa chỉ ổn định/tạm thời, danh tính thiết bị và zone** theo mức cần thiết để điều tra; không coi một địa chỉ IPv6 duy nhất là ID bất biến của user.

## 9. Kết hợp địa chỉ với phân đoạn và chính sách firewall

Ví dụ ma trận kết nối cần được triển khai **độc lập** với DHCP scope:

| Nguồn → đích | Mục đích | Chính sách logic |
|---|---|---|
| Employee → internal DNS | Phân giải tên nội bộ | ALLOW tới resolver được quản lý, cổng/protocol đúng |
| Employee → application API | Sử dụng ứng dụng nghiệp vụ | ALLOW theo port/dịch vụ và identity nếu có |
| Employee → management zone | Truy cập quản trị | DENY mặc định; ngoại lệ từ bastion/ZTNA đã cấp quyền |
| Guest → Internet | Web và dịch vụ được phê duyệt | ALLOW egress có kiểm soát; lọc DNS/web theo policy |
| Guest → server/management | Không có nhu cầu nghiệp vụ | DENY ở cả IPv4 và IPv6 khi áp dụng |
| IoT → collector | Gửi telemetry đúng chủng loại | ALLOW tới IP/identity/port cần thiết |
| IoT → Employee | Không cần thiết | DENY mặc định |
| Management → network devices | Quản trị có kiểm soát | ALLOW hẹp theo tài khoản, thiết bị nguồn, audit |

**IPAM mô tả ownership và kỳ vọng cấp phát; firewall thực thi kết nối; NAC/IdP xác thực và ủy quyền chủ thể; ứng dụng kiểm tra quyền dữ liệu.** Một attacker có thể tự đặt IP `10.48.50.23` (nằm trong ví dụ management `10.48.50.0/26`); firewall chỉ dựa vào source IP không tự xác minh người đó thật sự thuộc management zone. Cần kiểm soát port/VLAN/VRF, anti-spoofing và các lớp identity.

### 9.1. Zone, VRF và trường hợp địa chỉ chồng lắp

Hai tenant tách VRF đôi khi dùng cùng dải `10.0.0.0/24`. Đây là **chồng lấn được cô lập theo routing domain**, không phải một scope duy nhất dùng chung:

- IPAM phải lưu khóa xác định duy nhất theo **VRF/tenant + prefix + IP**, thay vì chỉ `IP`.
- DHCP relay/server phải chọn đúng routing context; nếu không có khả năng phân biệt, có nguy cơ cấp nhầm pool.
- Khi cần liên thông giữa VRF, thường phải giải quyết **NAT, proxy, dịch vụ trung gian hoặc thiết kế renumber** tùy yêu cầu; không thể chỉ gộp bảng route trùng nhau.
- Audit và log cần ghi **VRF, interface, tenant và thời gian**, nếu không một IP có thể chỉ nhiều endpoint khác nhau.

Không dùng overlap như giải pháp mặc định vì nó làm vận hành, DNS, SIEM và kết nối đối tác khó hơn. Trước khi liên kết cloud/VPN/site, hãy phân tích toàn bộ kế hoạch IP và khả năng route summarization.

## 10. DHCP, DNS và đăng ký tên thiết bị

DHCP có thể cung cấp recursive DNS server, domain search và trong một số thiết kế kích hoạt **Dynamic DNS (DDNS)** cập nhật A/AAAA hoặc PTR record. Điều này giúp truy vết thiết bị theo hostname, nhưng có các điểm nhạy cảm:

1. Hostname do client gửi **không tự đáng tin**, không được dùng trực tiếp để cấp quyền quản trị.
2. Chỉ DHCP server/automation được phép cập nhật zone cụ thể, sử dụng cơ chế quyền phù hợp (ví dụ TSIG trong những hệ thống hỗ trợ).
3. Không cho thiết bị guest tự tạo record trong namespace nội bộ quan trọng.
4. Phân biệt forward/reverse DNS, PTR stale và lease đã hết hạn.
5. Quản trị các zone private/split-horizon để record của employee không vô tình xuất hiện trên DNS public.
6. Khi có nhiều VRF/tenant, cùng hostname hoặc IP có thể không định danh được duy nhất tài sản nếu thiếu scope.

Đối với DHCPv6 và SLAAC, IPAM có thể không nhìn thấy tất cả địa chỉ được tự tạo từ RA; cần nguồn bổ sung như network telemetry, NAC, neighbor discovery và endpoint management, tuân thủ chính sách riêng tư.

## 11. Bảo mật dịch vụ cấp địa chỉ và threat modeling

### 11.1. Các đường lạm dụng thường gặp

| ID | Điểm yếu | Tình huống | Hậu quả | Kiểm soát phòng vệ |
|---|---|---|---|---|
| T01 | **Rogue DHCP server** | Thiết bị trái phép phát DHCPOFFER trên access VLAN | Client nhận gateway/DNS giả, mất kết nối hoặc chuyển traffic sai đường | DHCP snooping, trusted ports, bảo vệ access |
| T02 | **DHCP starvation** | Nhiều yêu cầu/identifier làm cạn pool | Client hợp lệ không nhận IP | Port security, rate limit access, giám sát pool, NAC |
| T03 | **MAC/client-ID spoofing** | Client giả mạo identifier của reservation | Nhận địa chỉ dành riêng, tranh chấp lease | Không coi reservation là authentication; 802.1X và anti-spoofing |
| T04 | **Option 82 bị tin nhầm** | Metadata từ đường không đáng tin được dùng để chọn scope | Cấp sai zone/policy | Trusted relay boundary, kiểm tra insertion/stripping |
| T05 | **Relay misconfiguration** | `giaddr`/VRF mapping sai, relay không tới server | Thiếu offer hoặc sai subnet | Kiểm tra SVI, route, scope association, end-to-end |
| T06 | **Gateway/DNS option bị đổi** | DHCP option bị thao túng hoặc deploy sai | Redirect, mất phân giải DNS, downtime | Quyền quản trị, review, audit option diff |
| T07 | **Overlapping pool / static IP** | IP fixed không excluded hoặc HA server cấp độc lập | IP conflict, gián đoạn mạng | IPAM reconciliation, coordinated failover, conflict monitoring |
| T08 | **Unauthorized zone change** | Port/VLAN/NAC role hoặc scope bị thay trái phép | Thiết bị xuất hiện trong vùng đặc quyền | IAM/RBAC, change approval, logging |
| T09 | **Rogue IPv6 RA** | Gateway/prefix IPv6 giả trên client VLAN | Thiết bị đi đường IPv6 ngoài dự kiến | RA Guard khi hỗ trợ, IPv6 ACL, endpoint monitoring |
| T10 | **Control-plane outage** | DHCP service/relay hoặc DNS hỏng | Client mới và client hết lease bị ảnh hưởng | HA, backup, capacity, failover exercise |
| T11 | **IPAM drift** | Sổ địa chỉ khác trạng thái DHCP/cloud | Trùng/thiếu địa chỉ và sai incident attribution | Reconciliation và source-of-truth ownership |
| T12 | **Static-IP bypass** | Endpoint tự đặt IP từ zone nhạy cảm | Ngộ nhận thiết bị được cấp quyền | 802.1X, port binding, firewall và identity |
| T13 | **Log thiếu ngữ cảnh** | Chỉ lưu IP mà không có thời gian/VRF/lease | Không xác định đúng thiết bị khi điều tra | Log lease interval, source, zone và time sync |
| T14 | **Guest scope kéo dài vào vùng khác** | Cấu hình pool/mask sai hoặc trùng prefix | Lỗi route, broadcast và segmentation | Validate prefix math, peer review, negative tests |

### 11.2. Chuỗi sự cố giả định: gateway giả từ DHCP

~~~mermaid
sequenceDiagram
    participant C as Guest client
    participant S as Access switch
    participant R as Rogue DHCP endpoint
    participant D as Authorized DHCP
    C->>S: DHCPDISCOVER
    S->>D: Chuyển đúng đường tới service được phép
    R-->>S: DHCPOFFER không được phép
    Note over S: DHCP snooping / trusted-port enforcement nếu cấu hình đúng
    S--xC: Chặn offer từ cổng untrusted
    D-->>C: Lease và options hợp lệ qua đường được phép
~~~

Sơ đồ **mô tả hành vi phòng vệ mong muốn**, không khẳng định mọi switch tự động chặn rogue DHCP. Nếu switch không hỗ trợ/tắt DHCP snooping, rogue offer có thể đến client. Kiểm thử trong lab cần được cấp quyền và không đưa rogue server lên mạng doanh nghiệp thật.

### 11.3. Những thông tin cần bảo vệ

Lease logs có thể liên kết **IP, MAC, Client Identifier, hostname, cổng switch, user/device identity, location, tenant và thời gian**. Đây là dữ liệu quan trọng để điều tra nhưng cũng có thể thuộc dữ liệu cá nhân hoặc cấu trúc mạng nhạy cảm. Cần hạn chế quyền truy cập, quản lý retention, time synchronization, redaction khi phù hợp và ghi audit thao tác tra cứu.

## 12. Tính capacity, churn và giám sát pool

### 12.1. Độ sử dụng pool

Với Employee DHCP pool có **131** địa chỉ, giả sử 105 lease đang được xem là occupied theo định nghĩa của hệ thống:

\[
\text{Pool utilization} = \frac{105}{131}\times100\% \approx 80{,}15\%.
\]

Tỷ lệ này **khác** tỷ lệ sử dụng toàn subnet /24. Khi giám sát cần biết occupied nghĩa là *active binding*, reserved, declined, quarantined hay excluded, vì sản phẩm có thể đo theo cách khác nhau.

Không đặt ngưỡng duy nhất 80% cho mọi zone. Một pool guest có churn cao và nhiều access point có thể cần khoảng dự phòng lớn; một server scope chỉ có reservation cố định sẽ có ý nghĩa giám sát khác.

### 12.2. Dự đoán số địa chỉ cần thiết

Một cách lập kế hoạch ban đầu:

\[
N_{\mathrm{planned}} = \left\lceil N_{\mathrm{peak}} \times (1+g) \right\rceil + N_{\mathrm{reserve}},
\]

trong đó:

- `N_peak`: số lease đồng thời trong giờ/ngày cao điểm **đã đo**, kể cả nhiều thiết bị/người.
- `g`: hệ số tăng trưởng dự báo trong kỳ hoạch định, ví dụ 0,25 cho 25%.
- `N_reserve`: dung lượng dự phòng vận hành cho sự kiện bất thường, bảo trì và churn.

Ví dụ peak là 180, tăng trưởng 25%, dự phòng 30 địa chỉ:

\[
N_{\mathrm{planned}} = \lceil 180\times1{,}25\rceil + 30 = 255.
\]

Một subnet /24 thông thường có tối đa 254 host IPv4, **và phải trừ gateway/reservations**, nên không phù hợp nếu yêu cầu tới 255 địa chỉ DHCP khả dụng. Cân nhắc một subnet lớn hơn, nhiều subnet hoặc thiết kế nhiều VLAN/zone tùy chính sách; không đơn giản mở scope chồng lấn sang zone khác.

### 12.3. Dashboard và cảnh báo

| Metric | Ý nghĩa | Nguyên nhân cần phân biệt |
|---|---|---|
| Pool utilization / available | Còn bao nhiêu địa chỉ cấp được? | Tăng người dùng, lease quá dài, stale binding, starvation |
| DHCP success/NAK/timeout | Tỷ lệ yêu cầu thành công và lỗi | Scope, relay, ACL, DNS, HA, xung đột |
| Discover/Offer/Request/Ack rate | Hành vi cấp phát và renew | Giờ cao điểm, mạng rớt, client retry, bất thường |
| Lease churn và age | Tốc độ tái sử dụng IP và vòng đời thuê | Guest density, privacy MAC, thiết bị thay đổi |
| Relay health | Đường đi và tỷ lệ lỗi của từng VLAN/VRF | Gateway failover, routing sai, ACL thiếu |
| Duplicate/conflict/decline | Client phát hiện địa chỉ không dùng được | Static overlap, DHCP server HA, rogue network |
| IPAM reconciliation drift | Kỳ vọng khác thực tế cấp phát | Chưa sync, provisioning thủ công, cloud orchestration |
| Rogue server / IPv6 RA events | Đường cấp phát không được phép | Cắm thiết bị lạ, sai trusted port, đổi topology |

Cần liên kết **timestamp, relay ID, subnet, VRF, lease identifier và client context** ở mức tối thiểu hợp lý, nhưng không đưa password/token hay dữ liệu riêng tư không liên quan vào telemetry.

## 13. High availability, failover và khôi phục

DHCP là dịch vụ nền tảng. Khi DHCP không hoạt động, thiết bị còn lease chưa hết có thể tiếp tục sử dụng IP trong một khoảng thời gian, trong khi thiết bị mới/renew có thể gặp khó khăn. Cách diễn giải chính xác tùy giai đoạn lease và hành vi client.

**Không triển khai hai DHCP server độc lập phát cùng một pool mà không có cơ chế phối hợp.** Nếu không đồng bộ trạng thái, cả hai có thể cấp cùng địa chỉ cho hai client và làm gián đoạn mạng.

Các phương án có thể dùng, tùy sản phẩm:

- DHCP failover/HA hỗ trợ **replicate lease state** và chính sách xử lý khi mất kết nối.
- Chia pool có chủ đích và không chồng lấn, kèm kiến trúc relay phù hợp (không coi đây là thay thế hoàn toàn cho failover protocol).
- Nhiều relay/helper target với thiết kế đảm bảo DHCP server có thông tin scope/VRF chính xác.
- Backup cấu hình zone, lease database và metadata IPAM theo chính sách khôi phục.
- Theo dõi thời gian cấp IP và lỗi khi chuyển site/VRF hoặc failover gateway.

### 13.1. Cần thử những gì trước khi chuyển HA?

1. Client mới nhận lease đúng zone khi một server ngừng phục vụ.
2. Client đang hoạt động renew/rebind khi backend đổi vai trò.
3. Reservation, exclusions, DHCP options và DNS update không bị lệch giữa hai node.
4. Lease database không cấp trùng, thời gian hệ thống đồng bộ, địa chỉ conflict được xử lý.
5. Mạng guest không nhận sai scope employee vì relay target thay đổi.
6. IPv6 RA/DHCPv6/PD, nếu có, cũng được đánh giá theo thiết kế HA riêng.
7. Logs và IPAM ghi đúng node, thời gian và nguyên nhân chuyển trạng thái.

Không thử bằng cách tắt DHCP server production ngoài change window được phê duyệt. Dùng lab hoặc diễn tập điều phối có phương án rollback.

## 14. Kiểm chứng thực tế và troubleshooting

### 14.1. Lệnh chỉ đọc trên endpoint

Với Windows:

~~~powershell
# Xem trạng thái cấu hình IP, gateway và DNS của client.
ipconfig /all
Get-NetIPConfiguration
Get-DnsClientServerAddress
~~~

Trên Linux (nếu hệ thống có các tiện ích tương ứng):

~~~bash
# Xem địa chỉ của các interface và route hiện có.
ip -br address
ip -4 route show
ip -6 route show

# Xem DNS của systemd-resolved nếu máy sử dụng dịch vụ này.
resolvectl status
~~~

Những lệnh trên **không đổi lease**. Nếu máy không có `resolvectl` hoặc dùng trình quản lý DNS khác, xem phương pháp phù hợp với hệ điều hành đó. Không chạy `release/renew` hoặc thay DNS/gateway trên máy đang phục vụ công việc quan trọng nếu chưa có kế hoạch kiểm thử.

### 14.2. Đọc PCAP DHCPv4 đã được cho phép

Ví dụ với một PCAP **lab có nguồn gốc và quyền sử dụng rõ ràng**:

~~~bash
# Phân tích file capture có sẵn; không bắt gói mới và không phát DHCP.
tcpdump -nn -vv -r /path/to/approved-dhcp-lab.pcap 'udp port 67 or udp port 68'
~~~

Các đường dẫn là placeholder; lệnh cần file có thật trong môi trường được phép. PCAP DHCP có thể chứa MAC, hostname và tùy chọn mạng nhạy cảm; chỉ lưu và chia sẻ theo quyền được phê duyệt. Trong luồng DHCPv4, chú ý **DHCP Message Type**, server identifier, offered/assigned IP, subnet mask, gateway, DNS, `giaddr` và Option 82 (nếu có).

Không suy ra DHCP server sai chỉ từ một packet bị thiếu: capture có thể không nhìn thấy cả chiều offer/ack, đặc biệt qua relay, NAT hoặc đường đi bất đối xứng.

### 14.3. Ma trận kiểm thử theo zone

| ID | Nguồn/thiết bị | Thử nghiệm | Kết quả mong muốn |
|---|---|---|---|
| P01 | Laptop Employee ở VLAN 110 | Nhận DHCPv4 lease | IP thuộc `10.48.10.0/24`, đúng gateway/DNS |
| P02 | Guest ở VLAN 120 | Nhận lease | IP thuộc `10.48.20.0/23`, đúng chính sách guest |
| P03 | IoT hợp lệ ở VLAN 130 | Nhận reservation/pool đã được cấp | IP đúng IoT, chỉ đi tới collector được phép |
| N01 | Guest | Kết nối management API | Bị firewall/access control từ chối dù guest có IP hợp lệ |
| N02 | Guest hoặc client lạ | Tự đặt IP management | Không được cấp quyền vào management; anti-spoofing khi hỗ trợ |
| N03 | Cổng user không đáng tin | Phát DHCP offer trái phép trong lab | Bị chặn bởi access control/snooping theo thiết kế |
| N04 | Relay sai VRF/mapping | Xin scope không thuộc link thật | Server không cấp sai pool; có log lỗi phù hợp |
| P04 | Client chuyển từ Employee sang Guest | Nhận config zone mới | Release/renew hoặc xử lý chuyển mạng đúng; không giữ quyền cũ |
| P05 | Một DHCP server HA ngừng trong lab | Client mới xin lease | Server còn lại phục vụ đúng scope, không trùng IP |
| P06 | IPv6-capable client | Nhận RA/SLAAC/DHCPv6 đúng thiết kế | Prefix/gateway/DNS/ACL IPv6 đúng zone |
| N05 | Guest IPv6 | Truy cập địa chỉ management IPv6 | Bị từ chối theo firewall/RA policy phù hợp |
| P07 | Client Employee | Resolve tên dịch vụ nội bộ | Dùng resolver nội bộ được phép, không rò private DNS qua guest |
| P08 | Sau thay đổi scope | Đối chiếu IPAM và lease logs | Không còn prefix/pool conflict, owner và audit chính xác |

**Kết quả nhận IP đúng không đủ kết luận zone đã an toàn.** Mỗi ca liên quan quyền phải xác minh thêm routing, firewall/ACL, NAC và hành vi ứng dụng.

### 14.4. Bảng chẩn đoán sự cố

| Triệu chứng | Nguyên nhân cần kiểm tra | Bằng chứng |
|---|---|---|
| Client không nhận IPv4 lease | Thiếu DHCP service, relay, route, ACL, pool hết | DORA capture, relay logs, DHCP server health |
| Client nhận IP sai zone | VLAN/NAC role sai, giaddr/Option 82 sai, overlapping scope | Port/VLAN, relay mapping, scope selection |
| IP đúng nhưng không truy cập Internet | Gateway option sai, default route/NAT/firewall | DHCP option, route, firewall logs |
| IP đúng nhưng DNS lỗi | DNS option/ACL/forwarder sai, split DNS | DNS server được cấp, query path, DNS logs |
| Nhiều IP conflict | Static overlap, HA state sai, rogue DHCP | Lease DB, IPAM, DHCPOFFER, conflict logs |
| Pool cạn dù ít người dùng | Lease dài, MAC randomization, stale bindings, starvation | Active lease count/churn, discover rate |
| Chỉ guest gặp lỗi | Thiếu relay cho VLAN 120, guest VRF không tới server | VRF route, ACL, helper, scope |
| IPv4 ổn nhưng IPv6 bypass | RA/AAAA/IPv6 ACL chưa cấu hình | RA capture, IPv6 routes, firewall counters |
| Cloud VM có IP khác IPAM | Cloud control plane giữ quyền phân bổ, sync trễ | Cloud inventory, IPAM reconciliation |
| Sau failover một số client mất kết nối | Relay target, lease state hoặc DNS policy không đồng bộ | HA event, lease database, resolver logs |

## 15. Tình huống thực hành: mở rộng mạng khách nhưng không phá phân đoạn

**Bối cảnh:** doanh nghiệp có Employee `10.48.10.0/24` với DHCP pool 131 IP và Guest `10.48.20.0/23`. Trong một hội nghị, nhiều khách kết nối Wi-Fi làm pool Guest đạt 95%; cùng lúc một số laptop nhân viên thỉnh thoảng nhận DNS dành cho mạng Guest. Quản trị viên đề xuất “mở scope Employee sang `10.48.20.0/23` để tận dụng địa chỉ trống” và giảm toàn bộ lease time xuống 60 giây.

Hãy đánh giá:

1. Vì sao **không** thể chỉ cho hai scope chia sẻ phần địa chỉ của nhau?
2. Cần kiểm tra VLAN assignment, relay/`giaddr`, Option 82 và IPAM thế nào khi nhân viên nhận sai DNS?
3. Ngoài tăng kích thước pool, những yếu tố nào ảnh hưởng đến số IP có thể cấp cho Guest?
4. Điều gì có thể xảy ra khi rút lease time quá ngắn đối với DHCP server, relay và client?
5. Phải chứng minh những chính sách nào vẫn đúng sau khi mở rộng?

**Gợi ý đối chiếu:**

- Employee và Guest có **security boundary riêng**; chồng pool hoặc thay prefix không đi kèm VLAN/routing/firewall sẽ tạo xung đột và có thể làm mất kiểm soát. Mở rộng Guest theo kế hoạch prefix hợp lệ, hoặc thêm subnet/VLAN cho guest, chứ không lấy trực tiếp dải của Employee.
- Kiểm tra access port/SSID mapping, AAA/NAC role, L3 SVI/relay, `giaddr` và policy server, rồi đối chiếu DNS option trên DHCPACK theo từng zone.
- Xem peak concurrent leases, tốc độ khách rời mạng, thiết bị dùng MAC ngẫu nhiên, lease còn chiếm sau khi rời, địa chỉ excluded/reserved, DHCP decline và khả năng chịu tải.
- Lease 60 giây có thể làm tăng mạnh renew/rebind và yêu cầu DHCP, khiến sự cố relay/HA ảnh hưởng nặng hơn; cần đo thực tế và đặt lifetime phù hợp.
- Positive: cả hai nhóm nhận đúng subnet/gateway/DNS. Negative: Guest không vào Employee/server/management, client giả MAC/IP không tự vượt ACL, IPv6 không tạo đường bypass; kiểm tra cả IPAM/lease/HA và audit.

## 16. Checklist triển khai Address allocation theo zone

- [ ] Zone được định nghĩa rõ theo mức tin cậy, VLAN, subnet, VRF, site và tenant khi liên quan.
- [ ] Mỗi prefix và pool có owner, mục đích, capacity, exclusion, reservation và trạng thái IPAM.
- [ ] Không có overlap ngoài mô hình VRF đã thiết kế; đã xét VPN, cloud, đối tác và container.
- [ ] Đã tính đúng usable IPv4 host theo prefix và số IP thực tế có thể cấp qua DHCP.
- [ ] Đã chọn dynamic/reservation/static theo vòng đời và độ quan trọng của thiết bị.
- [ ] DHCP server chọn scope đúng theo link/`giaddr`/relay/VRF; Option 82 chỉ được tin ở biên hợp lệ.
- [ ] DHCP snooping, trusted ports, NAC/802.1X và chống spoofing được đánh giá ở access layer.
- [ ] Cấp IP không tự tạo quyền: firewall, phân đoạn, identity và authorization vẫn được áp dụng.
- [ ] DHCP options (gateway, DNS, domain, lease) được review riêng cho từng zone.
- [ ] IPv6 được thiết kế đủ RA/SLAAC/DHCPv6, prefix /64 khi phù hợp, RA Guard và ACL IPv6.
- [ ] DHCP → DNS/DDNS updates có quyền tối thiểu và không làm lộ tên/zone private.
- [ ] IPAM, DHCP lease DB và cloud/orchestrator có ranh giới source-of-truth rõ; reconciliation định kỳ.
- [ ] Capacity theo peak/churn/growth, cảnh báo pool và HA/relay health được theo dõi.
- [ ] DHCP HA không cấp trùng lease, có backup, failover test và rollback.
- [ ] Lease logs có thời gian, zone, relay, VRF, client context phù hợp và được bảo vệ quyền riêng tư.
- [ ] Có ma trận kiểm thử positive/negative cho Employee, Guest, IoT, Server, Management và IPv6.
- [ ] Khi đổi scope/VLAN có kiểm tra lease cũ, route, DNS, firewall state và ảnh hưởng người dùng.
- [ ] Không thử rogue DHCP, exhaustion hoặc failover gây gián đoạn trên mạng sản xuất ngoài quy trình được phê duyệt.

**Ghi nhớ:** **Address allocation theo zone không chỉ là chia một dải IP thành nhiều pool**. Thiết kế đúng phải liên kết **prefix/subnet, relay, định danh kết nối, IPAM và DNS** với **security zone, routing domain, firewall và kiểm soát quyền thực sự**. Cấp phát nhất quán, giám sát được và kiểm thử ở cả IPv4/IPv6 mới giúp doanh nghiệp mở rộng mạng mà không mở rộng nhầm quyền truy cập.
