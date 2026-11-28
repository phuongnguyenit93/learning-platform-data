# IP Address Management (IPAM): thiết kế, cấp phát và quản trị địa chỉ mạng an toàn

## 1. IP address management là gì?

**IP Address Management (IPAM)** là tập hợp quy trình, dữ liệu và công cụ dùng để **quy hoạch, phân bổ, ghi nhận, theo dõi, kiểm toán và thu hồi** không gian địa chỉ IP của một tổ chức. IPAM không chỉ là bảng tính liệt kê các địa chỉ đã dùng: nó trả lời **địa chỉ hoặc prefix nào thuộc mạng nào, ai sở hữu, dùng để làm gì, cấp theo cách nào, được định tuyến ở đâu, và có còn hợp lệ không**.

Ví dụ, một doanh nghiệp có văn phòng, hệ thống ứng dụng Production, môi trường Dev, VPN và nhiều mạng cloud. Nếu hai đội tự cấp cùng dải **10.42.20.0/24** vào hai nơi rồi kết nối bằng VPN, route có thể mơ hồ hoặc trùng; nếu DNS còn trỏ về IP đã tái sử dụng, người dùng có thể kết nối nhầm dịch vụ. IPAM giúp **phát hiện xung đột trước thay đổi**, bảo toàn lịch sử và giảm cấu hình thủ công sai.

Trong module **SECURITY_NETWORK_SECURITY**, IPAM là một phần của năng lực xây dựng **mạng có phân đoạn, firewall, VPN, NAC, IDS/IPS, bảo vệ DNS, Wi-Fi và kết nối cloud an toàn**. Dữ liệu IPAM tốt hỗ trợ xác định đúng phạm vi rule, nhận diện nguồn của alert, điều tra DHCP/IP spoofing và mô hình hóa những đường truy cập không nên tồn tại.

### Mục tiêu học tập

Sau bài học, người học có thể:

1. Phân biệt IPAM với **DHCP, DNS, DDI, routing và CMDB**; hiểu ranh giới trách nhiệm từng hệ thống.
2. Quy hoạch IPv4/IPv6 bằng CIDR, tính vùng mạng và kiểm tra chồng lấn prefix.
3. Thiết kế **hierarchy site → environment → zone/VLAN/VRF → subnet → address** và theo dõi vòng đời cấp phát.
4. Quản lý liên hệ **IP ↔ hostname/DNS ↔ MAC/identity ↔ thiết bị/workload ↔ owner** phù hợp với từng loại tài sản.
5. Xây dựng chính sách IPAM hỗ trợ segmentation, zero-trust, DHCP security, logging và ứng phó sự cố.
6. Sử dụng ví dụ Python offline để kiểm tra không gian IP và phát hiện xung đột trước khi thay đổi.
7. Đề xuất cơ chế đối soát, tự động hóa, kiểm thử, phân quyền và audit.

## 2. Phân biệt IPAM, DHCP, DNS, DDI và quản lý cấu hình

| Thành phần | Trả lời câu hỏi | Ví dụ | Giới hạn |
| --- | --- | --- | --- |
| **IPAM** | Prefix/IP này được quy hoạch, cấp phát và quản lý cho ai? | 10.42.10.0/24 thuộc Prod-App; 10.42.10.20 đang dành cho API | Bản ghi IPAM **không tự bảo đảm** IP đang chạy hoặc routing đúng |
| **DHCP** | Client được cấp địa chỉ và thông số mạng nào trong thời hạn lease? | DHCPv4 cấp IP, mask, gateway, DNS, lease time | Lease hiện hành là trạng thái thực thi, không thay thế kế hoạch toàn bộ subnet |
| **DNS** | Tên nào được phân giải ra địa chỉ nào, và chiều ngược nếu cấu hình? | api.example.org → 192.0.2.20; PTR cho IP tương ứng | DNS record có thể lỗi thời hoặc khác trạng thái workload |
| **DDI** | Tích hợp **DNS, DHCP và IPAM** | Cấp địa chỉ cùng tạo DHCP reservation và DNS record | Tính đồng bộ và ràng buộc phụ thuộc sản phẩm/quy trình |
| **Routing** | Gói đến prefix nào phải chuyển tới next hop nào? | Route 10.42.10.0/24 qua firewall nội bộ | Có route không đồng nghĩa có quyền truy cập |
| **CMDB/Asset inventory** | Thiết bị, workload, owner, application và mối phụ thuộc là gì? | VM-API-01 thuộc team Billing, môi trường Prod | CMDB có thể thiếu IP động hoặc thay đổi trong cloud |
| **NAC/IAM** | Ai/thiết bị nào có quyền kết nối hay thực hiện hành động? | 802.1X đưa endpoint vào đúng role/VLAN | IP không phải danh tính đáng tin một cách độc lập |

**DDI** thường được dùng khi hệ thống tự động đồng bộ kế hoạch IP, cấp phát và tên miền. Tuy nhiên, có thể triển khai IPAM độc lập kết hợp DHCP/DNS qua API. Nhiệm vụ trọng yếu là xác định **nguồn dữ liệu có thẩm quyền (source of truth)** và chiều đồng bộ, không phải bắt buộc mua một sản phẩm cụ thể.

### Ví dụ xung đột giữa “kế hoạch” và “thực tế”

~~~text
IPAM:             10.42.10.20 = RESERVED cho API mới
DHCP lease:       10.42.10.20 = ACTIVE cho laptop nhân viên
DNS:              api.example.org -> 10.42.10.20
Firewall:         ALLOW đến 10.42.10.20:443 từ một nhóm tin cậy

Kết luận: dữ liệu đang mâu thuẫn; không được coi IPAM hoặc
DHCP hoặc DNS đơn lẻ là bằng chứng máy nào đang giữ địa chỉ.
~~~

Trước khi quyết định, đối chiếu lease log có thời điểm, switch/NAC, hệ điều hành, DHCP reservation, thiết bị thực và thay đổi gần nhất trong phạm vi được phép. **Không tự giải quyết bằng cách bật cùng IP trên máy khác**, vì có thể tạo duplicate IP và làm gián đoạn.

## 3. Nền tảng CIDR và tính toán địa chỉ IPv4

### 3.1. Prefix length và subnet

Trong IPv4, địa chỉ có **32 bit**. CIDR viết dạng **địa chỉ/prefix length**, ví dụ **10.42.10.0/24**, nghĩa là 24 bit đầu xác định phần mạng và 8 bit còn lại dành cho địa chỉ trong prefix.

\[
\text{Số địa chỉ IPv4 trong /p} = 2^{32-p}
\]

| Prefix | Số địa chỉ trong khối | Trường hợp thường gặp |
| --- | ---: | --- |
| /16 | 65.536 | Khối địa chỉ cấp cho site hoặc môi trường (khi phù hợp quy mô) |
| /22 | 1.024 | Một khối cấp phát tương đối lớn |
| /24 | 256 | Subnet ví dụ phổ biến |
| /26 | 64 | Subnet nhỏ hơn bên trong /24 |
| /27 | 32 | Phân đoạn có số lượng endpoint hạn chế |
| /30 | 4 | Liên kết IPv4 truyền thống có hai địa chỉ host dùng được |
| /31 | 2 | Có thể dùng trên **liên kết point-to-point** hỗ trợ theo RFC 3021 |
| /32 | 1 | Một địa chỉ duy nhất, host route hoặc object policy |

Với subnet **/24 truyền thống**, địa chỉ đầu biểu thị network address và địa chỉ cuối là directed broadcast; thường có **254 địa chỉ host dùng được**. Tuy nhiên, không áp công thức “tổng trừ 2” cho mọi loại prefix: **/31 point-to-point** và **/32 single address** có ý nghĩa riêng; nhà cung cấp cloud còn **dành riêng thêm địa chỉ** trong từng subnet theo nền tảng.

### 3.2. Ví dụ chia 10.42.10.0/24

~~~text
Khối cha: 10.42.10.0/24  = 256 địa chỉ

10.42.10.0/26      = 10.42.10.0   - 10.42.10.63  (64 địa chỉ)
10.42.10.64/26     = 10.42.10.64  - 10.42.10.127 (64 địa chỉ)
10.42.10.128/27    = 10.42.10.128 - 10.42.10.159 (32 địa chỉ)
10.42.10.160/27    = 10.42.10.160 - 10.42.10.191 (32 địa chỉ)
10.42.10.192/26    = 10.42.10.192 - 10.42.10.255 (64 địa chỉ)

Tổng: 64 + 64 + 32 + 32 + 64 = 256.
~~~

Các khối con ở đây **không chồng lấn và bao phủ đúng khối cha**. Có thể ánh xạ lần lượt tới Web, Application, Database, Management và vùng dự phòng. Việc chọn kích thước subnet phải dựa trên quy mô, HA, số IP cần dự trữ và đặc tính tầng mạng, không dựa trên ví dụ này một cách máy móc.

### 3.3. Dải IPv4 riêng và địa chỉ đặc biệt

| Dải/khái niệm | Ý nghĩa quản trị | Lưu ý khi thiết kế |
| --- | --- | --- |
| **10.0.0.0/8** | Địa chỉ riêng RFC 1918 | Thường dùng nội bộ, cần tránh trùng dải giữa on-prem, cloud và VPN |
| **172.16.0.0/12** | Địa chỉ riêng RFC 1918 | Không phải toàn bộ 172.0.0.0/8 đều là private |
| **192.168.0.0/16** | Địa chỉ riêng RFC 1918 | Hay gặp ở chi nhánh/home VPN, dễ va chạm khi kết nối |
| **100.64.0.0/10** | Shared Address Space theo RFC 6598 | Không đồng nhất với RFC 1918; thường liên quan CGNAT, cần chính sách sử dụng rõ |
| **169.254.0.0/16** | IPv4 link-local | Có thể xuất hiện khi tự cấu hình địa chỉ cục bộ; không nên coi là subnet doanh nghiệp thông thường |
| **127.0.0.0/8** | Loopback | Không gán như địa chỉ host mạng |
| **224.0.0.0/4** | Multicast IPv4 | Không cấp như địa chỉ unicast endpoint |
| **192.0.2.0/24**, **198.51.100.0/24**, **203.0.113.0/24** | TEST-NET cho tài liệu | Dùng trong ví dụ; không dùng làm prefix cấp phát production |

**Trùng private CIDR có thể tồn tại hợp lệ trong các mạng/VRF cô lập**, nhưng nếu có kết nối/route leaking, NAT, DNS hoặc observability dùng chung thì xung đột phải được xử lý có chủ đích. Không đơn giản gộp hai address group trùng dải và coi đây là một miền mạng duy nhất.

## 4. Quy hoạch IPv6 trong IPAM

IPv6 có **128 bit**, nên quản trị khác IPv4 về kích thước và phương pháp cấp phát. Một subnet **/64** có số địa chỉ cực lớn và thường dùng trên LAN hỗ trợ **SLAAC**, thay vì chia khối thành /120 để “tiết kiệm” địa chỉ như tư duy IPv4.

### 4.1. Cấu trúc ví dụ

~~~text
Prefix tài liệu được chỉ định: 2001:db8::/32

Ví dụ hierarchy minh họa:
  2001:db8:1000::/48           Site-A (ví dụ)
  2001:db8:1000:10::/64        Site-A / Prod-Web
  2001:db8:1000:20::/64        Site-A / Prod-App
  2001:db8:1000:30::/64        Site-A / Prod-DB
  2001:db8:1000:40::/64        Site-A / Management
~~~

**2001:db8::/32** được dành cho tài liệu, không sử dụng trên Internet thật. Prefix thực tế do ISP/RIR/cơ chế phân phối địa chỉ và thiết kế của tổ chức quyết định. **/48 cho site** và **/64 cho LAN** là cách tổ chức thường gặp, không phải ràng buộc mọi thiết kế IPv6; liên kết point-to-point, loopback và các mô hình hạ tầng có thể dùng prefix khác theo tiêu chuẩn và năng lực thiết bị.

### 4.2. SLAAC, DHCPv6 và Neighbor Discovery

| Thành phần | Vai trò |
| --- | --- |
| **Router Advertisement (RA)** | Quảng bá thông tin prefix, khả năng tự cấu hình và đặc biệt là default router trong IPv6 thông thường |
| **SLAAC** | Thiết bị tự tạo địa chỉ từ prefix được RA cho phép và interface identifier phù hợp |
| **DHCPv6** | Có thể cấp địa chỉ (stateful), tham số khác hoặc prefix delegation tùy mô hình |
| **NDP/Neighbor Discovery** | Tìm láng giềng, router và phát hiện trùng địa chỉ bằng các thông điệp ICMPv6 |
| **DAD (Duplicate Address Detection)** | Kiểm tra xung đột địa chỉ IPv6 trước khi dùng theo quy tắc giao thức |
| **Temporary/privacy addresses** | Một thiết bị có thể có nhiều địa chỉ IPv6 và thay đổi địa chỉ nguồn theo thời gian |

**DHCPv6 không cung cấp default gateway theo cách DHCPv4 option 3 thường làm**; host IPv6 thường học router mặc định qua RA. Cờ **M/O** và các cờ prefix liên quan phải được diễn giải đúng theo hệ điều hành/client, không mặc định mọi thiết bị sẽ chạy cùng kiểu DHCPv6.

IPv6 không dùng broadcast theo cơ chế IPv4; các chức năng tương đương được xây dựng qua multicast và các giao thức khác. Điều này ảnh hưởng đến thiết kế kiểm soát **RA Guard, DHCPv6 Guard, NDP monitoring** và chẩn đoán.

### 4.3. IPv6 và tính chính xác của inventory

Một host có thể có **link-local**, **global unicast ổn định**, **temporary IPv6** và thậm chí nhiều địa chỉ từ nhiều prefix. IPAM nên phân biệt **prefix allocation** với **address observations**. Không cố duy trì danh mục mỗi địa chỉ SLAAC ngắn hạn như một “máy cố định” nếu không có dữ liệu định danh/bối cảnh; thay vào đó, lưu prefix, chủ sở hữu zone, log RA/DHCPv6 và các sự kiện xác thực phù hợp.

## 5. Tổ chức IPAM theo hierarchy và ranh giới tin cậy

Một IP “10.42.10.20” đơn lẻ là thông tin chưa đủ. Một bản ghi hữu ích còn cần **tenant, VRF/routing domain, site, environment, VLAN/zone và thời gian hiệu lực**.

~~~mermaid
flowchart TD
    ORG["Organization / Tenant"] --> REG["Region / Site"]
    REG --> ENV["Environment: Dev / Staging / Prod"]
    ENV --> VRF["VRF / Routing domain"]
    VRF --> Z["Security zone / VLAN / Subnet"]
    Z --> IP["IP assignment / Reservation"]
    IP --> ASSET["Asset / Service / Owner"]
    Z --> POL["Firewall / NAC / Routing policy"]
    IP --> DNS["DNS / DHCP reference"]
~~~

Đây là **mô hình quan hệ**, không phải quy định VRF luôn nằm vật lý bên trong environment. Có nơi một VRF chứa nhiều zone và site; có nơi một site chứa nhiều VRF; cloud có thể biểu diễn qua VPC/VNet và account. Điều cần giữ là **khóa duy nhất cho mỗi đối tượng cùng ý nghĩa định tuyến**.

### 5.1. Đề xuất dữ liệu tối thiểu

| Trường | Ví dụ | Tại sao cần? |
| --- | --- | --- |
| Prefix / IP | 10.42.10.0/24; 10.42.10.20 | Định danh không gian địa chỉ |
| IP family | IPv4 hoặc IPv6 | Không nhầm quy tắc CIDR và cấp phát |
| Tenant/VRF/routing domain | corp-prod | Phân biệt dải IP giống nhau nhưng nằm trong miền cô lập |
| Site/region | dc-a, cloud-region-a | Hiểu vị trí và đường dự phòng |
| Environment | prod, staging, dev | Tránh cấp nhầm địa chỉ và rule giữa các môi trường |
| Security zone / VLAN | prod-app / VLAN 310 | Gắn với chính sách mạng và NAC |
| Status | available/reserved/allocated/active/retired | Quản lý vòng đời |
| Assignment type | static/DHCP/auto-assigned/SLAAC | Biết hệ thống nào có thẩm quyền cấp |
| Owner/team/contact | team-platform | Có người chịu trách nhiệm xác minh hoặc thu hồi |
| Asset/service ID | vm-api-01, lb-api | Liên kết CMDB và cloud inventory |
| Hostname/FQDN | api.example.org | Hỗ trợ tạo/kiểm tra DNS |
| Source of truth / observation source | IPAM/DHCP/cloud controller | Phân biệt kế hoạch và dữ liệu quan sát |
| Created/updated/lease/validity | ISO 8601 UTC | Phân biệt dữ liệu hiện tại với lịch sử |
| Change/ticket/reference | CHG-001 | Truy vết phê duyệt, rollback |
| Confidentiality/access class | internal-restricted | Bảo vệ thông tin topology và danh tính |

Địa chỉ gắn với danh tính người dùng, MAC, Wi-Fi, VPN và thời gian truy cập có thể là **dữ liệu nhạy cảm**. Chỉ thu thập/giữ lại trường cần thiết, phân quyền truy cập, xác định retention và tuân thủ chính sách quyền riêng tư.

### 5.2. Các trạng thái cần định nghĩa thống nhất

~~~text
FREE / AVAILABLE
      │ request + validation
      ▼
RESERVED  ──(approval + provisioning)──> ALLOCATED
      │                                     │
      └──(hủy yêu cầu)──> FREE               ▼
                                         ACTIVE
                                           │
                              release / decommission
                                           ▼
                                     QUARANTINED
                                           │
                               verify cleanup and cooldown
                                           ▼
                                         FREE
~~~

**Ví dụ nghĩa trạng thái:** AVAILABLE là chưa được phân bổ; RESERVED là giữ chỗ có thời hạn; ALLOCATED là đã giao cho người sở hữu/workload; ACTIVE nghĩa có bằng chứng cấp phát hay hoạt động theo định nghĩa của tổ chức; QUARANTINED ngăn tái sử dụng ngay sau thu hồi. Có thể có trạng thái **RETIRED** cho prefix hoặc tài sản đã ngừng. Không coi sơ đồ này là chuẩn bắt buộc của mọi công cụ.

**Trạng thái ACTIVE không nhất thiết có nghĩa có host online tại thời điểm xem**; một máy tắt có thể vẫn giữ IP static hợp lệ, còn một lease đã hết hạn có thể vẫn hiện trong log cũ.

## 6. Quy trình cấp phát và thu hồi địa chỉ

### 6.1. Cấp mới một subnet

1. **Tiếp nhận yêu cầu:** Môi trường, site, VRF/tenant, owner, mục đích, số lượng endpoint, IPv4/IPv6, HA và nhu cầu tăng trưởng.
2. **Chọn khối cha hợp lệ:** Kiểm tra thuộc quyền quản lý và có route/thiết kế thích hợp; loại trừ dải cấm, pool hạ tầng, vùng đang dùng hoặc dải xung đột với đối tác/VPN.
3. **Tìm prefix còn trống:** Kiểm tra chồng lấn với prefix đang cấp trong cùng routing domain; nhận diện aggregate/parent-child có chủ đích.
4. **Kiểm tra biên và phụ thuộc:** VLAN/VRF, subnet gateway, DHCP relay, DNS, NAT, firewall rules, cloud quotas và route.
5. **Phê duyệt:** Owner mạng và owner ứng dụng xác nhận mục đích, phạm vi và trách nhiệm.
6. **Ghi IPAM:** Đăng ký subnet và người sở hữu, trạng thái và change ticket **trước khi triển khai cấu hình phụ thuộc**.
7. **Triển khai có kiểm soát:** IaC/API/configuration management theo cơ chế của hệ thống; giám sát đổi route/policy.
8. **Kiểm chứng:** Route, DHCP/DNS, firewall, NAC và cả luồng ALLOW/DENY; đối soát kết quả trở lại IPAM.

### 6.2. Cấp một địa chỉ trong subnet

| Loại endpoint | Cách cấp phát thường gặp | Lưu ý |
| --- | --- | --- |
| Máy người dùng | DHCPv4, SLAAC/DHCPv6 | Lease/identity có thời hạn, thay đổi theo VLAN/Wi-Fi/VPN |
| Server/VM | Static, DHCP reservation hoặc cloud-managed assignment | Giữ IP ổn định khi thật sự cần, gắn asset owner |
| Container/Pod | CNI/cloud controller cấp động | Pod IP có thể thay đổi nhanh; inventory nên theo workload/service và prefix |
| Load balancer/virtual IP | Virtual/managed IP theo nền tảng | Ghi ownership, failover model, health/routing |
| Router point-to-point | Prefix phù hợp giao thức/topology | Đánh giá /31 IPv4 và /127 IPv6 theo thiết kế |
| Loopback | Host route /32 IPv4 hoặc /128 IPv6 | Không nhầm với subnet LAN |
| VPN client | Pool do VPN concentrator cấp | Xác thực người dùng, session logs, chống trùng site |

**Cấp phát IP không tự kích hoạt DNS, route hay firewall.** Những thành phần này phải được điều phối và xác minh theo cùng thay đổi.

### 6.3. Thu hồi và tái sử dụng

Một IP **không nên trở lại FREE ngay khi VM bị xóa** nếu DNS cache, static DNS record, firewall allowlist, security group, load balancer, TLS certificate, monitoring hoặc dịch vụ đối tác vẫn tham chiếu đến nó.

Quy trình thu hồi nên:

1. Ghi nhận owner yêu cầu và bằng chứng service đã ngừng.
2. Thu hồi DHCP reservation/cloud attachment/NAT rule theo phạm vi.
3. Kiểm tra các DNS A/AAAA/PTR và TTL, record liên quan, service discovery.
4. Rà soát allowlist firewall/IPS, VPN access, IAM binding và application config.
5. Xác minh không còn route/traffic phụ thuộc trước khi tái sử dụng.
6. Áp dụng **quarantine/cooldown** theo nguy cơ của tổ chức, rồi mới đánh dấu AVAILABLE.
7. Lưu lịch sử owner/assignment để phục vụ điều tra, không xóa sạch audit.

## 7. Kết hợp DHCP với IPAM: lease, pool và reservation

### 7.1. DHCPv4 cấp phát thế nào?

DHCPv4 thường theo chuỗi **Discover → Offer → Request → Acknowledge (DORA)** trong trường hợp cấp phát mới. Server chọn địa chỉ từ pool khả dụng và trả các tùy chọn mạng theo chính sách. Client giữ **lease có thời hạn** và có thể gia hạn; với các trạng thái khác của DHCP, trình tự trao đổi không nhất thiết giống DORA.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant R as DHCP Relay / Gateway
    participant S as DHCP Server
    participant I as IPAM / Address inventory
    C->>R: DHCPDISCOVER (LAN broadcast)
    R->>S: Chuyển tiếp qua relay (nếu khác subnet)
    S->>S: Chọn pool và kiểm tra lease/reservation
    S-->>R: DHCPOFFER
    R-->>C: DHCPOFFER
    C->>R: DHCPREQUEST
    R->>S: Chuyển tiếp request
    S-->>R: DHCPACK + option/lease
    R-->>C: DHCPACK
    S-.->I: Đồng bộ lease/assignment theo kiến trúc
~~~

Sơ đồ mô tả cách **DHCP relay** thường chuyển tiếp thông điệp; nếu DHCP server nằm cùng mạng L2, client có thể trao đổi trực tiếp. IPAM không bắt buộc tham gia **từng gói DHCP**; nó có thể quản lý pool trước khi triển khai và đối soát lease sau cấp phát.

### 7.2. Pool và phần địa chỉ không được cấp động

Ví dụ một **phương án DHCP độc lập** cho subnet **10.42.10.0/24**; không triển khai đồng thời với phương án chia /24 thành các subnet nhỏ hơn ở mục 3.2:

~~~text
Subnet:             10.42.10.0/24
Gateway (ví dụ):    10.42.10.1
Static/reserved:    10.42.10.2 - 10.42.10.49
DHCP pool:          10.42.10.50 - 10.42.10.199
Future/reserved:    10.42.10.200 - 10.42.10.254
Broadcast:          10.42.10.255
~~~

Không để **DHCP pool** chứa địa chỉ đã gán static; cần ghi rõ phần reserved, excluded ranges và chính sách DHCP failover. Các giá trị ví dụ là lựa chọn thiết kế, không phải quy tắc bắt buộc.

### 7.3. DHCP reservation và sự thay đổi danh tính thiết bị

DHCP reservation thường ánh xạ địa chỉ theo MAC/client identifier hoặc tiêu chí server hỗ trợ. Tuy nhiên, thiết bị Wi-Fi có thể dùng **MAC randomization**, máy ảo đổi NIC, client có nhiều interface, và client identifier có thể khác MAC. Cần dùng hệ thống định danh/NAC phù hợp thay vì xem MAC là danh tính bất biến hoặc không thể giả mạo.

### 7.4. DHCP failover và lease consistency

Khi có nhiều DHCP server, phải xác minh cơ chế **failover/replication** được sản phẩm hỗ trợ. Hai server cấp phát cùng một pool nhưng không có phối hợp lease đúng cách có thể làm tăng nguy cơ trùng địa chỉ. IPAM nên ghi **owner của scope, máy chủ có quyền cấp, lease policy và vùng dự phòng**; không tự xem hai bản sao DHCP là một cluster đồng bộ.

## 8. Liên kết DNS, reverse DNS và độ tin cậy của bản ghi

### 8.1. Forward và reverse lookup

| Bản ghi | Ví dụ minh họa | Mục đích |
| --- | --- | --- |
| **A** | api.example.org → 192.0.2.20 | Hostname sang IPv4 |
| **AAAA** | api.example.org → 2001:db8:1000::20 | Hostname sang IPv6 |
| **PTR** | 20.2.0.192.in-addr.arpa → api.example.org | Reverse DNS của IPv4 |
| **PTR IPv6** | Dưới ip6.arpa theo từng nibble | Reverse DNS IPv6 |
| **CNAME** | service.example.org → api.example.org | Alias, phải tuân thủ quy tắc DNS về CNAME |

Các tên, địa chỉ ở đây dùng **chỉ cho tài liệu**. **Reverse DNS/PTR không phải bằng chứng bảo mật đủ tin cậy về chủ sở hữu host**; bản ghi có thể thiếu, cũ hoặc được quản lý bởi chủ prefix khác với đơn vị vận hành service.

### 8.2. Quy tắc đồng bộ

1. IPAM lưu **địa chỉ/prefix dự định dùng**, owner và liên hệ DNS khi cần.
2. DHCP cấp lease và có thể kích hoạt **DNS dynamic updates** theo chính sách được phê duyệt.
3. DNS server có dữ liệu trả lời cuối cùng cho client, subject to caching và TTL.
4. Hệ thống reconciliation tìm bản ghi **IPAM có mà DNS không có**, **DNS trỏ IP đã nghỉ**, bản ghi PTR thiếu và dữ liệu DHCP khác kế hoạch.
5. Thay đổi được ghi theo request/ticket và rollback; không tự ý xóa record chỉ vì không ping được IP.

**DNS TTL** ảnh hưởng thời gian client giữ record cũ. Khi tái sử dụng một IP, cần quản lý DNS và thời gian lan truyền để giảm rủi ro client kết nối tới dịch vụ mới bằng tên của dịch vụ cũ.

### 8.3. DHCP/DNS và quyền cập nhật

DNS dynamic updates phải được xác thực, giới hạn theo zone/record và ghi audit; không cho mọi client tự ghi/sửa bản ghi tên quan trọng như **admin**, **vpn**, **payment** hoặc authoritative infrastructure. Nếu DDI tự động tạo DNS record, tài khoản tích hợp cần **quyền tối thiểu** và review các luồng sync.

## 9. IPAM hỗ trợ phân đoạn và các chính sách bảo mật như thế nào?

Một firewall rule kiểu “ALLOW 10.42.0.0/16 → DB TCP/5432” có thể rộng hơn ý định thực nếu khối /16 chứa cả **Dev, Staging, User Wi-Fi và Production**. IPAM có thể cung cấp **danh mục CIDR gắn environment/zone/owner** để review phạm vi trước khi tạo ACL.

| Kiểm soát | IPAM cung cấp gì? | Không nên suy diễn điều gì? |
| --- | --- | --- |
| **Segmentation/Firewall** | Prefix nào thuộc Dev/Prod/DMZ, security zone, owner | IP đúng subnet không có nghĩa người dùng đã được phép |
| **VPN/Remote access** | VPN pool, ranh giới với LAN/site khác, lịch sử assignment | Một IP VPN không xác thực danh tính nếu không có session/AAA log |
| **802.1X/NAC** | VLAN/subnet mapping, lease liên quan endpoint | MAC/IP có thể đổi hoặc giả mạo; cần identity/device posture |
| **IDS/IPS/SIEM** | Bổ sung asset/environment vào alert theo IP và thời điểm | IP được NAT/chia sẻ/tái sử dụng; không xác định user nếu không join log |
| **DNS security** | Resolver/server prefixes, zone owner, domain/IP relationship | IPAM không xác thực DNS response hoặc ngăn DNS poisoning |
| **Cloud security** | VPC/VNet CIDRs, private endpoints, workload ownership | Route, SG/NSG và IAM phải được kiểm tra độc lập |
| **DDoS response** | Prefix public cần bảo vệ, dịch vụ/owner, downstream dependencies | Không tự xác nhận prefix đã được ISP/CDN bảo vệ |

**Điểm mấu chốt:** IPAM là **cơ sở ngữ cảnh cho kiểm soát**, không thay việc xác thực truy cập, giám sát packet hay kiểm tra policy thực thi. Một địa chỉ có thể được nhiều thiết bị sử dụng theo thời gian; mọi tương quan cần kèm **timestamp và routing domain/NAT context**.

## 10. Các mối đe dọa khi quản lý địa chỉ

IPAM vừa là công cụ tổ chức tài nguyên, vừa chứa thông tin **topology, địa chỉ quản trị, tên hệ thống và phân đoạn nhạy cảm**. Khi mô hình hóa mối đe dọa phải xét khả năng **lạm dụng dịch vụ cấp phát** và **rò rỉ/sửa trái phép danh mục IP**.

| Kịch bản | Điểm yếu thường gặp | Hệ quả có thể xảy ra | Phòng vệ phù hợp |
| --- | --- | --- | --- |
| **Rogue DHCP server** | Thiết bị lạ trả DHCP OFFER/ACK trên LAN | Client nhận gateway/DNS hoặc IP sai | DHCP snooping, port role, NAC, giám sát switch |
| **DHCP starvation** | Pool nhỏ, không giới hạn cấp phát phù hợp | Client hợp lệ không lấy được lease | Capacity, rate limit theo khả năng, NAC, cảnh báo pool |
| **ARP spoofing** | Không kiểm soát ARP trên miền L2 | Traffic bị chuyển sai đường, nguy cơ MITM | Dynamic ARP Inspection (DAI), DHCP snooping bindings, segmentation |
| **IPv6 rogue RA** | Host nhận Router Advertisement trái phép | Default router/prefix sai | RA Guard, switch security, quản lý router hợp lệ |
| **IPv6 NDP abuse** | Thiết bị giả láng giềng hoặc lạm dụng NS/NA | Chuyển hướng, gián đoạn hoặc cạn ND state | Giám sát ND và các cơ chế bảo vệ phù hợp |
| **Duplicate IP/static conflict** | Static IP trùng DHCP, không đối soát | Mất kết nối, ARP/ND flapping | IPAM validation, reservation, kiểm tra xung đột có kiểm soát |
| **Overlapping CIDR** | Mỗi đội tự cấp khối, VPN/peering không kiểm tra | Route leak, định tuyến mơ hồ, mất kết nối | Quản lý routing domain, kiểm tra overlap trước kết nối |
| **IPAM unauthorized edit** | Tài khoản/automation có quyền viết quá rộng | Đổi owner, subnet, DNS/DHCP record, làm sai ACL | RBAC, MFA, audit, approval, backup |
| **DNS stale record** | IP tái sử dụng trước khi dọn DNS | Truy cập nhầm tài nguyên | DNS/PTR reconciliation, cooldown |
| **IPAM information disclosure** | Dashboard/API không kiểm soát quyền xem | Lộ dải quản trị, environment và topology | Phân quyền, bảo vệ export, monitoring |
| **Automation race condition** | Hai request cùng chọn IP trống | Cấp trùng một địa chỉ | Transaction/lock/atomic allocation, unique constraints |

### 10.1. DHCP snooping, DAI và IP Source Guard

**DHCP snooping** trên một số switch phân biệt cổng tin cậy (đường tới DHCP server/relay hợp lệ) với cổng không tin cậy, có thể chặn thông điệp cấp phát từ cổng sai và tạo **binding table** IP–MAC–VLAN–port–lease.

**Dynamic ARP Inspection (DAI)** có thể kiểm tra ARP dựa trên binding/ACL; **IP Source Guard** có thể dùng ràng buộc nguồn để hạn chế gói mang địa chỉ không được cấp cho cổng. Khả năng và cú pháp tùy thiết bị; các host dùng **static IP** phải có binding hoặc exception đúng để không bị chặn sai.

DHCP snooping không đủ chống mọi giả mạo trong **Wi-Fi, hypervisor trunk, overlay, NAT** hoặc nơi traffic đi vòng switch thực thi policy. Đừng coi địa chỉ nguồn là danh tính bất biến.

### 10.2. IPv6 RA Guard không thay thế phòng vệ toàn diện

**RA Guard** nhằm hạn chế Router Advertisement trái phép trên cổng không được tin cậy. Khi dùng phải kiểm tra hỗ trợ thiết bị, extension headers, các kiểu đóng gói và trường hợp lưu lượng phân mảnh. Cần kết hợp kiểm soát router, DHCPv6 nếu dùng, NDP monitoring và bảo vệ layer 2.

### 10.3. IPAM có phải nguồn định danh người dùng?

**Không.** IP có thể thay theo DHCP, VPN, NAT, Wi-Fi, cloud hoặc temporary IPv6. Muốn điều tra event lúc **10:30 UTC** phải join đúng khoảng thời gian của IP/lease, NAT mapping, NAC/AAA, thiết bị và asset owner. Với CGNAT/proxy có thể cần thêm source port và session metadata hợp pháp. Không quy kết người dùng dựa vào owner **hiện tại** của một IP từng xuất hiện trong alert cũ.

## 11. Thiết kế IPAM cho cloud, container và hybrid network

### 11.1. Mạng cloud và tài nguyên động

Các VPC/VNet thường có **điều khiển cấp phát IP riêng** từ nhà cung cấp. IPAM doanh nghiệp cần liên kết API/asset inventory để biết **VPC/VNet CIDR, subnet, network interface, instance, load balancer, private endpoint và public IP attachment**.

~~~mermaid
flowchart LR
    I["IPAM / Source of truth"] --> O["Change & provisioning workflow"]
    O --> A["On-prem DHCP/DNS"]
    O --> B["Cloud VPC/VNet provisioning"]
    O --> C["IaC / GitOps"]
    B -. "Read-only inventory/observations" .-> R["Reconciliation"]
    A -. "Lease + DNS evidence" .-> R
    C -. "Deployed state" .-> R
    R --> I
~~~

Không mặc định IPAM có quyền sửa mọi resource cloud. Có thể dùng **API read-only** để đối soát và workflow đã phê duyệt riêng cho thay đổi. Đặc biệt cần phân quyền theo tenant/account/subscription/project/environment.

### 11.2. Thiết kế không gian IP khi kết nối hybrid

~~~text
On-prem production:      10.42.0.0/16
Cloud production:        10.43.0.0/16
Staging/QA:              10.44.0.0/16
VPN client pools:        10.45.0.0/20
Shared services:         10.46.0.0/16
~~~

Đây là **quy hoạch độc lập để minh họa**, không phải bắt buộc chọn các dải này. Trước khi cấu hình private peering, transit gateway, VPN hay SD-WAN, cần so với **dải nhà cung cấp, đối tác, mạng remote user, NAT và các mạng từng sáp nhập**.

Khi không thể bỏ trùng CIDR, cân nhắc **renumber, NAT có kiểm soát, route domain/VRF riêng hoặc kiến trúc truy cập dịch vụ qua gateway/proxy**. Các phương án có chi phí DNS, identity, quan sát và vận hành; không dùng NAT để che giấu việc thiếu owner/kế hoạch.

### 11.3. Kubernetes, CNI và tuổi thọ địa chỉ

Cluster Kubernetes có thể sử dụng **Pod CIDR, Service CIDR, Node subnet, load-balancer IP, egress/NAT IP** và overlay/routing riêng của CNI. Pod IP có thể thay đổi rất nhanh; NetworkPolicy thường áp dụng qua **labels, namespace và IPBlock**, theo mô hình được CNI hỗ trợ.

IPAM nên ghi **khối cấp cho cluster/node**, owner và trạng thái sử dụng. Việc lưu từng Pod IP ngắn hạn có thể là **dữ liệu quan sát có TTL**, không nên coi như bản ghi static xác định một workload mãi mãi. Khi điều tra, kết hợp audit Kubernetes, CNI flow logs, workload labels, Node/VPC và timestamp.

### 11.4. Public IP và địa chỉ dịch vụ

Public IP cần có hồ sơ:

- **RIR/ISP/provider assignment**, prefix và quyền/thời hạn sử dụng.
- Dịch vụ/public endpoint, DNS/PTR, TLS/ingress owner.
- Egress NAT, load balancer, BGP advertisement, DDoS protection status.
- Ingress/egress policy, environment, kinh phí, trách nhiệm vận hành.
- Ngày tái đánh giá, khả năng thu hồi hoặc đổi attachment.

IP public đổi chủ/attachment nhưng DNS, allowlist và đối tác chưa cập nhật có thể gây rủi ro. Không quảng bá BGP một prefix không thuộc quyền kiểm soát hoặc không được phép của tổ chức.

## 12. Nguồn dữ liệu có thẩm quyền và workflow cấp phát

### 12.1. Phân biệt source of truth và observed state

**Source of truth (SoT)** ghi điều **dự kiến/được phê duyệt**, ví dụ prefix Prod-App cấp cho account A với owner Team Platform. **Observed state** là những gì runtime thực sự ghi nhận: DHCP leases, cloud interfaces, DNS, route tables hoặc devices.

Nếu dữ liệu khác nhau, tạo **drift event** với owner để điều tra. Không tự quyết một bên đúng và xóa bên còn lại khi chưa xét thời gian/scope.

| Loại dữ liệu | Nơi có thẩm quyền thường gặp | Đối soát với |
| --- | --- | --- |
| Danh mục subnet/prefix dự kiến | IPAM có phê duyệt | Router/cloud VPC/VNet, IaC |
| DHCP pool/reservation dự kiến | IPAM/DDI hoặc DHCP management | DHCP server config và lease logs |
| IP gắn vào cloud NIC | Cloud control plane | IPAM, CMDB, IaC |
| DNS zone/record thực tế | Authoritative DNS server/provider | IPAM/DDI, workload config |
| Router/route/VRF hiện hành | Thiết bị hoặc network controller | IPAM prefix và network design |
| Host/service identity | CMDB, platform/Kubernetes identity | IP assignment theo thời gian |

### 12.2. Cấp phát atomic thay vì đọc-rồi-ghi

Hai request song song đều có thể thấy **10.42.10.21 AVAILABLE**. Nếu cùng ghi, xảy ra **double allocation**.

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant DB as IPAM database
    A->>DB: Allocate next free IP (transaction)
    DB->>DB: Lock/validate uniqueness + reserve IP
    DB-->>A: 10.42.10.21 RESERVED
    B->>DB: Allocate next free IP (transaction)
    DB->>DB: Chọn IP còn trống khác
    DB-->>B: 10.42.10.22 RESERVED
~~~

Sơ đồ chỉ minh họa. Sản phẩm có thể dùng transaction isolation, advisory lock, optimistic concurrency hoặc allocation API. Các bất biến quan trọng:

1. Một địa chỉ có tối đa **một allocation active trong cùng routing domain và khoảng hiệu lực**, trừ mô hình VIP/anycast chia sẻ IP có owner rõ.
2. Prefix allocations không chồng lấn ngoài quan hệ parent-child/VRF đã được phê duyệt.
3. Request có **idempotency key/workflow ID** để retry không cấp thêm IP ngoài ý định.
4. Nếu DNS/DHCP/cloud provisioning lỗi một phần, lưu trạng thái pending/failed và điều phối retry/reconciliation/compensating action, không báo hoàn tất giả.
5. Có audit log, quyền ghi hẹp và khả năng hủy reservation/rollback.

### 12.3. Schema minh họa cho allocation

~~~yaml
# Mô hình để học, không phải schema tiêu chuẩn của một công cụ.
allocation_id: alloc-001
tenant: corp
routing_domain: vrf-prod
site: dc-a
environment: production
parent_prefix: 10.42.10.0/24
assigned_prefix: 10.42.10.64/26
purpose: application-zone
owner: team-platform
status: allocated
source_of_truth: central-ipam
requested_by: approved-workflow
change_reference: CHG-001
created_at: "2026-01-10T09:00:00Z"
review_at: "2026-04-10T09:00:00Z"
~~~

Trường **routing_domain** cần định danh miền định tuyến thực; có thể phải dùng **tenant ID + VRF ID + site/region** nếu tên VRF không duy nhất toàn tổ chức. Không suy rằng hai cloud account có cùng tên “vrf-prod” thì dùng chung một miền định tuyến.

## 13. Thực hành Python offline: phát hiện CIDR chồng lấn

Bài lab dùng **ipaddress** của Python chuẩn. Dữ liệu có sẵn ngay trong chương trình, **không kết nối mạng, không quét host, không thay cấu hình**. Mục tiêu là tìm xung đột **leaf allocations trong cùng routing domain**, phân biệt với dải trùng ở VRF độc lập.

~~~python
from dataclasses import dataclass
from ipaddress import ip_network, IPv4Network, IPv6Network
from typing import Union

IPNetwork = Union[IPv4Network, IPv6Network]


@dataclass(frozen=True)
class Allocation:
    name: str
    routing_domain: str
    prefix: str

    def network(self) -> IPNetwork:
        # strict=True phát hiện địa chỉ chưa căn đúng network boundary.
        return ip_network(self.prefix, strict=True)


allocations = [
    Allocation("prod-web", "vrf-prod", "10.42.10.0/26"),
    Allocation("prod-app", "vrf-prod", "10.42.10.64/26"),
    Allocation("prod-db", "vrf-prod", "10.42.10.128/27"),
    Allocation("dev-lab", "vrf-dev", "10.42.10.0/24"),
    Allocation("prod-shadow", "vrf-prod", "10.42.10.32/27"),
    Allocation("prod-v6-web", "vrf-prod", "2001:db8:1000:10::/64"),
    Allocation("prod-v6-app", "vrf-prod", "2001:db8:1000:20::/64"),
]


def conflicts(items: list[Allocation]) -> list[tuple[str, str]]:
    # Chỉ kiểm tra leaf allocations; không đưa parent prefixes vào danh sách.
    found: list[tuple[str, str]] = []
    for i, left in enumerate(items):
        for right in items[i + 1:]:
            if left.routing_domain != right.routing_domain:
                continue
            a, b = left.network(), right.network()
            if a.version == b.version and a.overlaps(b):
                found.append((left.name, right.name))
    return found


for a, b in conflicts(allocations):
    print(f"CONFLICT: {a} overlaps {b}")

assert conflicts(allocations) == [("prod-web", "prod-shadow")]
~~~

Kết quả dự kiến:

~~~text
CONFLICT: prod-web overlaps prod-shadow
~~~

**Giải thích:** **10.42.10.0/26** và **10.42.10.32/27** có phần chung, lại cùng **vrf-prod** nên cần điều tra cấp trùng. Dải **10.42.10.0/24** của **vrf-dev** trùng về mặt số học với Prod nhưng nằm trong routing domain độc lập giả định: chưa phải xung đột nếu hai miền không có peering/route leaking hoặc đường đi bất ngờ. Hai prefix IPv6 không chồng nhau.

### 13.1. Giới hạn của ví dụ

- Chỉ kiểm tra **leaf allocations**. Parent chứa child có chủ đích không phải lỗi; cần metadata loại bản ghi.
- Không xem route leaking, VPC peering, IPsec VPN, NAT, identity, thời gian hiệu lực hay quyền firewall.
- Không đọc DHCP/DNS/cloud, không xác nhận IP thật đang hoạt động hoặc các trường hợp chia sẻ VIP/anycast có chủ đích.
- Thuật toán so từng cặp có độ phức tạp O(n²), chỉ thích hợp lab nhỏ; production cần index/constraint/transaction.
- **Không chạy** như công cụ tự sửa IPAM production; nó chỉ báo cáo dữ liệu mô phỏng.

### 13.2. Bài tập mở rộng

1. Thêm một allocation **10.42.10.128/27** với owner khác vào vrf-prod và dự đoán kết quả.
2. Thêm parent **10.42.10.0/24** và giải thích cách phân biệt parent-child hợp lệ với overlap ngang cấp.
3. Thêm trường **tenant/site**; định nghĩa khi nào hai object cùng routing domain.
4. Thêm trạng thái **retired** và **valid_from/valid_to** để kiểm tra tái sử dụng sau khi hết hiệu lực.
5. Thêm IPv6 **2001:db8:1000:10::/63** rồi giải thích ý nghĩa network boundary và strict=True.

## 14. Case study: VPN nối chi nhánh làm lộ xung đột địa chỉ

**Bối cảnh giả định:** Data center dùng **10.42.0.0/16**; chi nhánh đã dùng **10.42.20.0/24** để cấp DHCP nhiều năm. Hai mạng cô lập hoạt động bình thường. Sau khi thiết lập **site-to-site IPsec VPN**, các đích ở dải trùng có hành vi định tuyến không mong muốn.

### 14.1. Dấu hiệu

- Một số dịch vụ ở data center không truy cập được từ chi nhánh sau khi bật VPN.
- DHCP chi nhánh vẫn cấp lease bình thường, nên lỗi không nhất thiết ở DHCP.
- Routes, traffic selectors hoặc địa chỉ on-link ở chi nhánh xung đột với đích cần qua tunnel.
- DNS trả IP của data center, nhưng client xem đích thuộc subnet cục bộ.

~~~text
Data center:
  Prefix:       10.42.0.0/16
  Service IP:   10.42.20.50

Chi nhánh:
  Subnet DHCP:  10.42.20.0/24
  Client:       10.42.20.100/24
  Gateway:      10.42.20.1

Đích 10.42.20.50 nằm ngay trong subnet 10.42.20.0/24.
Client chi nhánh có thể ARP on-link thay vì đi qua VPN.
~~~

Đây là **lỗi quy hoạch địa chỉ**; chỉ mở firewall ALLOW rộng hơn không giải quyết quyết định “on-link” của client.

### 14.2. Phương án và đánh đổi

| Phương án | Điểm mạnh | Đánh đổi |
| --- | --- | --- |
| **Renumber chi nhánh** sang prefix trống | Xử lý tận gốc, routing dễ quản lý | Phải đổi DHCP, DNS, ACL, printer/IoT, static IP, VPN |
| **Renumber một phần data center** | Phù hợp khi chỉ ít host bị ảnh hưởng | Rủi ro service/DB và phụ thuộc cũ |
| **NAT giữa hai miền** có mapping rõ | Có thể dùng tạm trong giai đoạn chuyển đổi | Khó giám sát, DNS, ACL, chiều về, troubleshooting |
| **Service proxy/gateway** | Thu hẹp số endpoint cần kết nối | Thêm thành phần trung gian, auth và vận hành |
| **Giữ cô lập** nếu không thật sự cần nối trực tiếp | Tránh route leaking | Có thể không đáp ứng nghiệp vụ |

### 14.3. Quy trình xử lý

1. Tạm ngừng mở rộng peering/VPN và ghi lại prefix, owner, dịch vụ liên quan.
2. Thu thập từ IPAM, DHCP, DNS, IPsec selectors và route tables trong phạm vi được phép.
3. Xác định dịch vụ phải liên lạc, những thiết bị khó renumber, thời điểm chuyển đổi an toàn.
4. Chọn phương án đã được phê duyệt, ưu tiên quy hoạch lại prefix nếu khả thi.
5. Lập ma trận kiểm thử DNS, route, tunnel, TCP, đường trả về, firewall DENY/ALLOW và logs.
6. Chuyển theo nhóm, đo kết quả, có rollback và cập nhật IPAM.
7. Sau thay đổi, kiểm tra không còn overlap ngoài ý định trong các miền đang nối.

**Bài học:** Trước khi kết nối LAN, VPN, cloud peering hoặc SD-WAN, phải kiểm tra **địa chỉ của toàn bộ miền định tuyến sẽ kết nối**, không chỉ trong một văn phòng riêng.

## 15. Giám sát drift và điều tra sự cố IPAM

### 15.1. Reconciliation pipeline

~~~mermaid
flowchart TB
    IPAM["IPAM: desired allocations"] --> N["Normalize: prefix, VRF, site, time"]
    DHCP["DHCP leases / reservations"] --> N
    DNS["DNS A/AAAA/PTR"] --> N
    CLOUD["Cloud NIC / VPC / subnet inventory"] --> N
    ROUTE["Router/VRF route inventory"] --> N
    N --> C{"Có mâu thuẫn không?"}
    C -- "Không" --> H["Cập nhật last-verified timestamp"]
    C -- "Có" --> T["Ticket + owner + evidence"]
    T --> R["Xác minh trước khi sửa"]
    R --> A["Approved change và readback"]
~~~

Nguồn quan sát có độ trễ và phạm vi khác nhau. Một lease vừa hết hạn có thể chưa biến mất khỏi hệ thống giám sát; một cloud NIC vừa bị xóa có thể còn nằm trong queue sự kiện. Cần có **grace period và phân loại độ tin cậy** để phân biệt dữ liệu stale với xung đột đã xác nhận.

### 15.2. Các cảnh báo nên ưu tiên

| Tín hiệu | Nguyên nhân có thể | Bước xác minh |
| --- | --- | --- |
| **Duplicate IPv4/IPv6** cùng routing domain | Static trùng DHCP, automation race | Lease, host, switch/NAC, timestamp và owner |
| **DHCP pool utilization cao** | Nhiều client, lease quá dài, exhaustion/abuse | Số lease, cấp/thu hồi, endpoint hợp lệ, capacity |
| **Rogue DHCP offer** | Server lạ hoặc switch trust sai | DHCP snooping, MAC/interface, nguồn thật |
| **Rogue IPv6 RA/prefix** | Router/host phát RA trái phép | Switch/RA logs, source, prefix, ND history |
| **Unknown IP active** | Endpoint chưa đăng ký, IP đổi hoặc log lệch | CMDB, DHCP/NAC, cloud NIC và discovery được phép |
| **DNS points to retired IP** | Quên record hoặc reuse sớm | Authoritative DNS, TTL, service owner và lịch sử |
| **Prefix overlap trước peering/VPN** | Hai site/tenant thiếu kế hoạch chung | VRF, route domain, NAT design |
| **IPAM API write bất thường** | Automation lỗi hoặc quyền bị lạm dụng | Audit log, identity, scope và change |
| **IPv4 pool thấp, IPv6 /64 ít sử dụng** | Sai đơn vị so capacity hoặc quy hoạch lệch | Usable pool thực tế, per-family allocation goals |
| **Public IP attachment đổi bất ngờ** | Migration, resource delete hoặc compromise | Provider audit, DNS, ingress, asset owner |

### 15.3. Quy trình xử lý duplicate IP

1. **Khoanh phạm vi cấp phát** bị nghi, nếu có quyền và ít ảnh hưởng; không tắt DHCP toàn site chỉ vì một địa chỉ trùng.
2. Xác nhận **routing domain, VLAN, prefix, timestamp** và địa chỉ thực sự có vấn đề.
3. Đối chiếu DHCP lease/reservation, IPAM, switch MAC table, ARP/ND, NAC, cloud NIC, host logs.
4. Kiểm tra có **VIP/anycast hoặc HA** cố ý dùng chung một IP không; tránh xử lý cấu hình hợp lệ như duplicate.
5. Xác định thiết bị nào có quyền dùng IP và thực hiện thay đổi theo một người điều phối; tránh hai bên đồng thời đổi.
6. Sửa scope/reservation/static assignment, kiểm tra **hết ARP/ND flapping** và ứng dụng phục hồi.
7. Ghi root cause, change/ticket, owner và cập nhật IPAM trước khi khép sự cố.

### 15.4. SIEM và mapping theo thời gian

Một alert “10.42.10.55 truy cập địa chỉ quản trị lúc 09:15 UTC” cần được bổ sung theo thời điểm:

~~~text
Event time:          2026-01-10T09:15:00Z
Observed source:     10.42.10.55:55000
Routing domain:      vrf-users
Sensor location:     firewall-branch-a (pre-NAT)
DHCP at that time:   lease/client identifier trong khoảng hiệu lực
NAC at that time:    device/identity/port hoặc Wi-Fi attachment
Asset mapping:       owner/workload theo timestamp
Security policy:     zone, rule ID và decision lúc xảy ra event
Confidence:          dựa trên chất lượng các nguồn dữ liệu
~~~

Không lấy owner hiện tại của IP để áp cho tất cả các sự kiện lịch sử. **NAT source port, session ID, routing domain và timestamp** có thể là những trường bắt buộc để ghép log trong mạng chia sẻ địa chỉ.

## 16. IPAM theo nguyên tắc quyền tối thiểu và change control

### 16.1. Phân quyền theo chức năng

| Vai trò | Quyền hợp lý | Quyền nên hạn chế |
| --- | --- | --- |
| Network architect | Đề xuất CIDR/VRF, review overlap, sơ đồ phân đoạn | Ghi trực tiếp mọi subnet Prod không có approval |
| IPAM operator | Cấp/thu hồi address từ các pool được giao | Sửa namespace/tenant khác, xem dữ liệu người dùng không cần |
| DHCP/DNS operator | Quản lý scope/zone thuộc trách nhiệm | Cập nhật mọi DNS zone không giới hạn |
| Application team | Yêu cầu IP, xem subnet/tài nguyên mình sở hữu | Sửa gateway, route, VRF của team khác |
| SOC/IR | Đọc mapping, lịch sử và audit phục vụ điều tra | Cấp/xóa IP ngoài nhiệm vụ |
| Automation account | API scope hẹp cho hành động được phê duyệt | Full admin token tồn tại lâu và không audit |
| Auditor | Read-only lịch sử, approval, drift, validation | Thay đổi đối tượng đang vận hành |

Áp dụng **MFA, RBAC/ABAC theo môi trường, token ngắn hạn, audit log và quản lý secrets**. Backup phải được bảo vệ và kiểm thử restore, tránh export IPAM làm lộ topology hoặc danh tính.

### 16.2. Mẫu hồ sơ thay đổi

~~~text
REQUEST / TICKET: CHG-001
OWNER / APPROVER: team-platform / network-review
SCOPE: environment=prod, vrf=vrf-prod, site=dc-a
CURRENT: 10.42.10.64/26 assigned to application-zone
PROPOSED: [mô tả thay đổi và tác động]
PURPOSE: [nghiệp vụ + data flow + capacity]
VALIDATION: overlap, DHCP/DNS/route/security checks
RISKS: duplicate assignment, DNS stale, ACL scope, IP reuse
ROLLBACK: [phương án hoàn nguyên có thẩm quyền]
READBACK: [đối chiếu deployed state + IPAM sau triển khai]
~~~

Không coi script trả exit code 0 là hoàn tất nếu IPAM ghi ALLOCATED nhưng DHCP, DNS hoặc cloud provisioning vẫn lỗi. Kết quả phải được **readback** ở hệ thống thực thi và được đồng bộ ngược vào IPAM.

### 16.3. Các chỉ số vận hành

| Chỉ số | Ý nghĩa |
| --- | --- |
| **IPv4 usable pool utilization** | Phần địa chỉ cấp được thực sự đã chiếm, trừ excluded/provider-reserved |
| **Free capacity theo site/zone** | Số địa chỉ/prefix phù hợp còn đủ cho mở rộng |
| **Prefix fragmentation** | Khối trống có bị chia vụn làm khó cấp subnet lớn |
| **Duplicate/overlap incidents** | Lỗi quy hoạch hoặc runtime cần điều tra |
| **Stale DNS / stale asset mapping** | Bản ghi không khớp tài sản và thời điểm |
| **IP reclaim cycle time** | Thời gian decommission đến khi tái sử dụng an toàn |
| **Allocation lead time** | Thời gian xử lý yêu cầu đúng quy trình |
| **Reconciliation drift rate** | Desired và observed có mâu thuẫn bao nhiêu theo tiêu chí rõ |
| **Audit coverage** | Tỷ lệ thay đổi có owner, approval, readback |

**Không dùng % địa chỉ IPv6 /64 đã dùng để đánh giá capacity như IPv4.** IPv6 có không gian rất lớn và nhiều địa chỉ trên một host; nên đánh giá **prefix allocation, định tuyến, khả năng quản trị và bảo mật**.

## 17. Ma trận kiểm thử IPAM trước khi triển khai

| Test ID | Kịch bản | Kết quả kỳ vọng |
| --- | --- | --- |
| IPAM-01 | Cấp hai leaf subnet không chồng lấn cùng VRF | Chấp nhận, ghi owner/status |
| IPAM-02 | Hai request đồng thời lấy một IP trong cùng VRF | Chỉ một allocation thành công, request còn lại retry/chọn IP khác |
| IPAM-03 | Cấp một leaf subnet trùng subnet đã có | Conflict/deny hoặc workflow xem xét |
| IPAM-04 | Parent /24 chứa các child /26 có chủ đích | Ghi hierarchy, không coi là cấp trùng ngang cấp |
| IPAM-05 | Cùng CIDR thuộc hai VRF cô lập | Ghi khác routing domain; cảnh báo khi chuẩn bị kết nối |
| IPAM-06 | Địa chỉ không căn network boundary | Lỗi hoặc chuẩn hóa với cảnh báo theo policy |
| IPAM-07 | DHCP pool bao gồm static/reserved IP | Cảnh báo/từ chối pool definition |
| IPAM-08 | DHCP lease hợp lệ được cấp | Có lease ID/timestamp, scope/owner khớp |
| IPAM-09 | Rogue DHCP OFFER trên cổng không trust trong lab | Snooping/NAC cảnh báo hoặc chặn đúng policy |
| IPAM-10 | IPv6 rogue RA trong lab | RA Guard/monitor hoạt động, không chặn router hợp lệ |
| IPAM-11 | Xóa VM nhưng A/AAAA/PTR còn tồn tại | IP quarantine hoặc reconciliation ticket |
| IPAM-12 | Cloud NIC đổi IP sau scale | Dữ liệu IPAM cập nhật từ API runtime sau độ trễ được phép |
| IPAM-13 | SIEM join alert với DHCP/VPN lease lịch sử | Mapping theo timestamp/VRF, không gán owner hiện tại |
| IPAM-14 | Thay subnet Prod mở rộng firewall allow sai | Policy diff và allow/deny regression test phát hiện |
| IPAM-15 | Hai HA node có VIP dùng chung theo thiết kế | Có model ownership rõ, không xóa nhầm như duplicate |
| IPAM-16 | Unauthorized write đến IPAM API | Bị từ chối và có audit |
| IPAM-17 | Ghi IPAM thành công nhưng tạo DNS lỗi | Không báo provisioning hoàn tất, có error/rollback |
| IPAM-18 | Reuse IP trước thời hạn quarantine | Bị ngăn trừ exception được duyệt |
| IPAM-19 | Thêm VPN tới mạng trùng prefix | Có cảnh báo overlap trước khi cấu hình route |
| IPAM-20 | Restore IPAM từ backup | Phục hồi history/owner và đối soát lại runtime |

### 17.1. Ba mức kiểm chứng

1. **Static validation:** CIDR đúng, không chồng lấn ngoài ý định, đúng owner/site/VRF, pool hợp lệ, thay đổi được phê duyệt.
2. **Runtime readback:** DHCP/DNS/cloud/route và IPAM đã đồng bộ theo mô hình.
3. **End-to-end network tests:** Traffic hợp lệ được ALLOW, luồng trái quyền bị DENY; xác minh DNS và ứng dụng trong phạm vi kiểm thử.

Không phải lần cấp IP nào cũng cần scan host. Với mạng lab hoặc production, mọi phép thử active phải có **ủy quyền và phạm vi**; nên bắt đầu từ API read-only và log khi đủ bằng chứng.

## 18. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “IPAM là DHCP server.” | IPAM quản lý quy hoạch/owner/trạng thái; DHCP cấp lease theo scope và policy. |
| “Có IP trong IPAM nghĩa là máy online.” | IPAM có reserved, allocated, retired; cần observed state và timestamp. |
| “DNS record chứng minh IP thuộc ứng dụng hiện tại.” | Record có thể stale, TTL còn giữ IP cũ hoặc IP đã đổi chủ. |
| “/24 IPv4 luôn có 254 IP cấp được trên mọi cloud.” | Provider có thể reserved thêm địa chỉ; /31 và /32 có ngữ nghĩa riêng. |
| “Private IPv4 không thể trùng.” | Các mạng đối tác/chi nhánh/cloud có thể chọn cùng dải. |
| “Hai VRF trùng CIDR chắc chắn là lỗi.” | Có thể hợp lệ khi cách ly thực sự; phải xét route leaking và NAT/peering. |
| “IPv6 /64 nên chia thành nhiều /120 như IPv4.” | /64 phổ biến cho SLAAC; cách quản lý prefix khác IPv4. |
| “DHCPv6 cấp default gateway giống DHCPv4.” | IPv6 thường dùng RA để học default router. |
| “IP/MAC là định danh người dùng không thể giả.” | DHCP, NAT, MAC randomization và spoofing đòi hỏi identity/session log. |
| “Đổi IP trong IPAM là DNS/firewall tự cập nhật.” | Chỉ đúng nếu workflow tích hợp thực sự chạy và readback PASS. |
| “Hai node HA dùng một IP chắc chắn bị duplicate.” | VIP/anycast có thể hợp lệ với owner/role/logic phù hợp. |
| “Không ping được nghĩa là địa chỉ trống.” | ICMP có thể bị chặn hoặc host tắt tạm, IP vẫn được cấp. |
| “API cấp IP không thể race.” | Thiếu transaction/idempotency có thể double allocate. |
| “Cùng dải /16 có thể gộp thành một firewall allow.” | Có thể vô tình mở quyền xuyên Dev/Prod/Management. |
| “Xóa VM xong có thể xóa luôn history.” | Cần dọn DNS/DHCP/ACL, cooldown và lưu audit. |

## 19. Câu hỏi tự kiểm tra và bài tập thiết kế

1. **IPAM quản lý những đối tượng gì?** Prefix/subnet/IP, owner, site/VRF/zone, trạng thái, lịch sử và liên kết DHCP/DNS/asset.
2. **DDI là viết tắt của gì?** DNS, DHCP, IP Address Management.
3. **Một /26 IPv4 có bao nhiêu địa chỉ?** 64 địa chỉ; số host dùng được phụ thuộc ngữ cảnh và quy tắc nền tảng.
4. **Vì sao một /24 cloud không nhất thiết có 254 IP cấp được?** Provider có thể giữ thêm địa chỉ và áp hạn chế.
5. **Vì sao routing domain cần nằm trong khóa IPAM?** Để phân biệt private CIDR giống nhau ở các VRF/tenant độc lập.
6. **DHCP lease khác reservation?** Lease là trạng thái cấp IP có thời hạn; reservation là chính sách/dự định giữ địa chỉ cho đối tượng.
7. **DHCPv6 có cấp default router giống DHCPv4 không?** Không; router mặc định IPv6 thường được học từ RA.
8. **Một thiết bị có thể có nhiều IPv6 không?** Có, ví dụ link-local, global ổn định và temporary/privacy addresses.
9. **Rủi ro reuse IP quá sớm?** DNS/ACL/client cache cũ có thể trỏ nhầm sang thiết bị mới.
10. **IPAM giúp xử lý IDS/IPS alert như thế nào?** Enrich mapping theo timestamp, zone/VRF, owner và DHCP/NAT/NAC logs.
11. **Parent /24 chứa child /26 khi nào bình thường?** Khi đó là quan hệ hierarchy có owner/loại đối tượng rõ.
12. **Vì sao API trả 200 OK chưa đủ xác nhận provisioning?** DHCP/DNS/cloud có thể chưa triển khai; cần runtime readback.

### Bài tập cuối chương

Thiết kế địa chỉ cho tổ chức có văn phòng chính 300 endpoint, hai chi nhánh mỗi nơi 80 endpoint, Dev/Staging/Prod và mạng quản trị riêng. Hai VPC cloud phải nối on-prem qua VPN. Tổ chức dùng dual-stack IPv4/IPv6, Wi-Fi 802.1X, client VPN và DNS nội bộ.

Hãy:

1. Vẽ cây IPAM theo **tenant/site/environment/VRF/security zone**, có owner và trạng thái.
2. Đề xuất prefix IPv4 không overlap trong các miền phải kết nối, có khoảng tăng trưởng.
3. Quy hoạch prefix IPv6 cho site và /64 cho các LAN SLAAC, phân biệt RA/DHCPv6.
4. Lập ma trận DHCP pool/reservation, DNS A/AAAA/PTR, VLAN/NAC và firewall policy.
5. Nêu cách xử lý khi một chi nhánh đang dùng CIDR trùng với một cloud network.
6. Đề xuất cấp phát atomic, rollback khi DNS tạo thất bại và cooldown khi thu hồi.
7. Lập ít nhất tám ca kiểm thử, gồm rogue DHCP, DNS stale, overlap, cloud reconciliation và Dev → Prod DENY.

**Gợi ý:** Mỗi subnet cần có **owner, route/VRF, DHCP/DNS policy, phân đoạn, quyền cấp phát và bằng chứng runtime**; chỉ tính tổng số địa chỉ là chưa đủ.

## 20. Checklist review IP Address Management

- [ ] Đã lập danh mục IPv4/IPv6 prefix, site, tenant, VRF, environment và owner?
- [ ] Đã định nghĩa source of truth cho plan, DHCP leases, DNS và cloud IP?
- [ ] Mọi subnet child cấp từ parent hợp lệ, không trùng leaf allocations?
- [ ] Kiểm tra overlap trước VPN, peering, SD-WAN, DR và sáp nhập mạng?
- [ ] Phân biệt IPv4 /31-/32, cloud-reserved IP và IPv6 /64/SLAAC?
- [ ] DHCP pool không chứa static/reserved IP, có failover phù hợp?
- [ ] Bảo vệ rogue DHCP/ARP/IPv6 RA tại switch/network phù hợp?
- [ ] Có DNS A/AAAA/PTR, TTL, dynamic update và reconciliation record stale?
- [ ] IPAM lưu status, owner, ticket, lease/validity và lịch sử thay đổi?
- [ ] Đã có RBAC, MFA, audit, API scope và phân quyền Dev/Prod?
- [ ] Provisioning có transaction/idempotency và xử lý lỗi từng phần?
- [ ] Runtime readback kiểm tra DHCP/DNS/cloud/route/NAC/firewall sau thay đổi?
- [ ] Có quarantine/cooldown trước khi tái sử dụng IP?
- [ ] IDS/IPS/SIEM liên kết địa chỉ với routing domain/NAT và timestamp?
- [ ] Public IP có owner, DNS/TLS, DDoS protection, ISP/provider reference?
- [ ] Có báo cáo capacity, fragmentation, stale mapping và drift định kỳ?
- [ ] Backup/restore được kiểm thử và runbook khôi phục IPAM/DDI?
- [ ] Có ma trận ALLOW/DENY, rollback và owner cho các thay đổi nhạy cảm?

**Kết luận:** Quản lý địa chỉ IP an toàn không chỉ là tránh hết IP. Một IPAM hữu ích phải duy trì **mô hình nhất quán về prefix, routing domain, environment, owner và thời gian**, điều phối DHCP/DNS/cloud đúng mức, phát hiện sai lệch giữa kế hoạch và thực tế, đồng thời hỗ trợ kiểm soát truy cập và điều tra sự cố. **Đúng địa chỉ, đúng vùng tin cậy, đúng thời điểm và đúng quyền thay đổi** là những điều kiện cốt lõi để xây dựng mạng mở rộng được mà không làm suy yếu bảo mật.
