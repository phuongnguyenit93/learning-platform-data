# Internal Segmentation Firewall (ISFW): Kiểm soát lưu lượng giữa các vùng mạng nội bộ

## 1. Internal Segmentation Firewall là gì?

**Internal Segmentation Firewall (ISFW)** là tường lửa được triển khai tại **ranh giới giữa những vùng mạng hoặc nhóm tài nguyên bên trong tổ chức** để kiểm soát kết nối giữa các vùng đó. Nó thường bảo vệ luồng **east-west**: kết nối từ máy này sang máy khác, từ ứng dụng tới cơ sở dữ liệu, từ mạng văn phòng tới vùng máy chủ hoặc giữa những môi trường sản xuất và thử nghiệm.

Trong chương **Firewall** của học phần **SECURITY_NETWORK_SECURITY**, ISFW là một lớp phòng vệ quan trọng bên cạnh phân đoạn bằng VLAN/VRF, firewall biên, VPN, IDS/IPS, xác thực kết nối, bảo vệ DNS và bảo mật đám mây. Mục tiêu là **giới hạn những hệ thống mà một điểm cuối có thể tiếp cận** nếu tài khoản, máy trạm hoặc ứng dụng bị xâm phạm; đồng thời tạo vị trí áp dụng chính sách và quan sát lưu lượng giữa các vùng tin cậy.

Ví dụ: một nhân viên cần truy cập ứng dụng kế toán qua HTTPS, nhưng máy trạm của họ không cần truy cập trực tiếp cổng cơ sở dữ liệu. Nếu malware kiểm soát máy trạm, ISFW đặt giữa mạng người dùng và mạng cơ sở dữ liệu có thể chặn kết nối trực tiếp đó. Tuy nhiên, malware vẫn có thể thử lạm dụng **luồng HTTPS được phép** đến ứng dụng; phân đoạn không thay thế bảo mật ứng dụng và danh tính.

**Sau bài học, bạn sẽ có thể:**

1. Phân biệt ISFW với firewall biên, host firewall, VLAN/VRF và microsegmentation.
2. Xác định vị trí đặt firewall sao cho lưu lượng cần kiểm soát thực sự đi qua nó.
3. Viết ma trận chính sách theo nguồn, đích, dịch vụ, chiều kết nối và mục đích nghiệp vụ.
4. Phân tích các vấn đề về định tuyến hai chiều, NAT, kết nối stateful, HA, hiệu năng và khả năng quan sát.
5. Thiết kế quy trình triển khai, kiểm thử cho phép/từ chối và giám sát mà không làm gián đoạn dịch vụ quan trọng.

## 2. Vì sao firewall biên chưa đủ?

Một firewall đặt giữa Internet và mạng doanh nghiệp chủ yếu bảo vệ **north-south traffic**: lưu lượng vào/ra tổ chức. Trong khi đó, khi kẻ tấn công đã vào được một máy hợp lệ, các bước dò tìm nội bộ, truy cập máy chủ, đánh cắp dữ liệu và **di chuyển ngang (lateral movement)** thường sử dụng các kết nối east-west.

~~~mermaid
flowchart LR
    NET[Internet] --> EDGE[Firewall biên]
    EDGE --> USERS[Mạng người dùng]
    USERS --> ISFW[Internal Segmentation Firewall]
    ISFW --> APPS[Mạng ứng dụng]
    ISFW --> DATA[Mạng dữ liệu]
    APPS --> ISFW
    DATA --> ISFW
~~~

Sơ đồ chỉ minh họa việc ISFW kiểm soát các kết nối giữa vùng người dùng, ứng dụng và dữ liệu. **Đường truyền thực tế phải được thiết kế** để gói giữa các vùng bắt buộc qua firewall; vẽ firewall giữa hai vùng chưa bảo đảm đường đi mạng sẽ đi qua nó.

### 2.1. Các trường hợp cần phân đoạn nội bộ

| Ranh giới | Rủi ro nếu kết nối quá rộng | Chính sách nên hướng tới |
| --- | --- | --- |
| Máy trạm → Máy chủ ứng dụng | Máy trạm bị xâm phạm tiếp cận cổng quản trị/server | Chỉ cho ứng dụng qua cổng dịch vụ công bố |
| Ứng dụng → Cơ sở dữ liệu | Một ứng dụng truy cập được mọi DB | Chỉ nhóm ứng dụng được phê duyệt gọi đúng DB và cổng |
| Production ↔ Development | Môi trường thử nghiệm là cầu nối vào production | Chặn mặc định, phê duyệt ngoại lệ rõ ràng |
| Mạng văn phòng ↔ Mạng quản trị | Thiết bị người dùng gọi SSH/RDP/hypervisor | Chỉ các máy quản trị được kiểm soát mới được truy cập |
| Server ↔ Backup / Identity / Monitoring | Phạm vi phụ thuộc dịch vụ hạ tầng quá rộng | Quy định chính xác nguồn, đích, giao thức và quyền |
| Đối tác/VPN ↔ Ứng dụng nội bộ | Có tunnel đồng nghĩa đi được khắp mạng | Chỉ mở ứng dụng và tài nguyên theo mục đích hợp tác |
| Workload ↔ Workload trong cloud | VPC/VNet lớn cho phép nhiều luồng không cần thiết | Tách security zone và quy tắc ở điểm thực thi phù hợp |

## 3. Phân biệt ISFW với các cơ chế liên quan

| Cơ chế | Chức năng chính | Điểm cần nhớ |
| --- | --- | --- |
| **Firewall biên (perimeter)** | Kiểm soát Internet ↔ mạng tổ chức | Không mặc định quan sát được kết nối giữa hai subnet nội bộ |
| **ISFW** | Lọc và giám sát kết nối **qua ranh giới nội bộ** | Phải nằm trên đường lưu lượng cần bảo vệ |
| **Host firewall** | Lọc kết nối ngay trên VM, server, máy trạm | Bảo vệ từng endpoint, kể cả khi lưu lượng không qua firewall tập trung |
| **VLAN** | Tách miền quảng bá ở lớp 2 | Không tự định nghĩa chính sách cho phép hay chặn khi router thực hiện inter-VLAN routing |
| **Subnet / VRF** | Phân chia tiền tố IP hoặc bảng định tuyến | Giúp tạo ranh giới mạng; kiểm soát truy cập cần ACL/firewall/policy tương ứng |
| **Microsegmentation** | Kiểm soát chi tiết giữa workload hoặc nhóm workload | Có thể thực thi ở host, hypervisor, CNI hoặc cloud; bổ sung cho ISFW |
| **IDS/IPS** | Phát hiện hoặc ngăn hành vi đáng ngờ trên luồng quan sát được | Khả năng phát hiện phụ thuộc điểm nhìn, quy tắc và dữ liệu được phân tích |
| **VPN** | Thiết lập kết nối có thể được bảo vệ bằng mật mã | Không tự cấp quyền truy cập tất cả vùng mạng sau khi tunnel thiết lập |

**ISFW không nhất thiết là một thiết bị vật lý riêng.** Chức năng có thể được triển khai bằng appliance, firewall ảo, dịch vụ cloud, hoặc cơ chế phân tán. Điều quyết định là **vùng nguồn và vùng đích được xác định**, lưu lượng đi qua điểm kiểm soát và chính sách được thực thi đúng.

### 3.1. Vai trò của các lớp OSI

Quy tắc phổ biến đối chiếu **địa chỉ IP ở L3**, **TCP/UDP và port ở L4**. Firewall thế hệ mới có thể bổ sung nhận diện ứng dụng, người dùng và phân tích một phần giao thức ở lớp cao hơn. Không nên mặc định mọi ISFW đều đọc được nội dung HTTPS: TLS được mã hóa và kiểm tra sâu cần khả năng, cấu hình, ủy quyền và chính sách bảo vệ dữ liệu phù hợp.

### 3.2. Segmentation không đồng nghĩa xác thực

Cho phép API truy cập DB ở TCP/5432 mới chỉ mở đường mạng. DB vẫn cần TLS khi phù hợp, xác thực client, phân quyền truy vấn và logging. Nếu API bị xâm phạm và được phép kết nối DB, attacker vẫn có thể lạm dụng quyền của API. Vì vậy ISFW là **một lớp hạn chế khả năng tiếp cận**, không phải bảo đảm rằng kết nối được phép thì an toàn.

## 4. Kiến trúc ISFW: Phải đặt đúng trên đường đi gói

### 4.1. Định tuyến qua firewall giữa các VLAN/subnet

Một triển khai thường gặp là tách ba vùng:

- **Users:** máy trạm nhân viên.
- **Application:** web/API và dịch vụ nghiệp vụ.
- **Data:** cơ sở dữ liệu và dịch vụ chứa dữ liệu nhạy cảm.

~~~mermaid
flowchart TD
    U[Users VLAN / subnet] --> FW[ISFW - Điểm kiểm soát liên vùng]
    A[Application VLAN / subnet] --> FW
    D[Data VLAN / subnet] --> FW
    FW --> R[Routing / next hop theo chính sách]
~~~

Để các vùng thực sự được kiểm soát, gateway hoặc tuyến giữa các vùng phải **buộc traffic đi qua firewall**. Nếu switch L3 định tuyến trực tiếp từ Users tới Data, một ISFW đặt cạnh switch nhưng không được đưa vào đường chuyển tiếp sẽ không nhìn thấy luồng đó.

Các lựa chọn kiến trúc có thể gồm:

1. **Routed firewall:** firewall có interface hoặc subinterface trong các vùng, làm gateway hoặc next hop giữa các mạng.
2. **Firewall trong suốt (transparent/bridged), nếu nền tảng hỗ trợ:** lọc gói ở đường L2 mà không nhất thiết thay gateway IP; vẫn phải kiểm tra chính xác đường đi và khả năng HA.
3. **Service insertion / policy-based routing:** hệ thống định tuyến chuyển một số luồng qua firewall. Cần đặc biệt kiểm tra chiều quay về, khi route thay đổi và nguy cơ bypass.
4. **Phân tán:** thực thi trên hypervisor, host, node hoặc cloud fabric; phù hợp với lưu lượng workload mà firewall tập trung khó bao phủ.

**Ranh giới của cùng subnet:** hai máy trên cùng VLAN/subnet có thể trao đổi trực tiếp tại L2, không đi qua gateway L3. Nếu mục tiêu là ngăn kết nối giữa chính các máy đó, cần cơ chế như private VLAN, host firewall, distributed firewall hoặc tách vùng mạng phù hợp.

### 4.2. Kiểm soát hai chiều và stateful inspection

Phần lớn firewall doanh nghiệp có khả năng **stateful inspection**: theo dõi thông tin các phiên/luồng đã được cho phép để xử lý traffic phản hồi. Ví dụ khi API khởi tạo TCP đến DB, chính sách có thể cho phép kết nối **mới** từ API tới cổng DB và cho phép gói phản hồi thuộc phiên đó.

~~~text
API  -> ISFW -> DB     TCP SYN: nguồn API, đích DB:5432
API  <- ISFW <- DB     TCP SYN/ACK: lưu lượng phản hồi
API  -> ISFW -> DB     TCP ACK: thiết lập phiên
API  <-> ISFW <-> DB   Dữ liệu và phản hồi của phiên được theo dõi
~~~

**Định tuyến bất đối xứng (asymmetric routing)** xảy ra khi chiều đi đi qua firewall A nhưng chiều về đi qua đường khác không đồng bộ trạng thái. Một số thiết bị có thể từ chối gói phản hồi vì không có session hợp lệ. Khi thiết kế nhiều đường ECMP, HA hoặc thay đổi gateway, phải kiểm tra đường đi và đường về, cùng cơ chế chia sẻ trạng thái nếu được hỗ trợ.

UDP không có bắt tay TCP; firewall stateful thường theo dõi lưu lượng UDP bằng thông tin tuple và timeout. ICMP/ICMPv6 có thông điệp điều khiển quan trọng cho chẩn đoán và Path MTU Discovery. Chặn toàn bộ ICMP có thể gây lỗi hoạt động, đặc biệt trên IPv6.

### 4.3. NAT, proxy và load balancer

Trong kết nối nội bộ, không phải lúc nào cần NAT. Tuy nhiên môi trường hybrid, mạng đối tác trùng dải IP hoặc kiến trúc qua proxy có thể dùng SNAT/DNAT.

Tại mỗi điểm lọc cần biết:

- IP nguồn/đích **trước và sau NAT**.
- Proxy hoặc load balancer có chấm dứt TLS hay mở kết nối mới tới backend hay không.
- Firewall so khớp rule theo địa chỉ **quan sát tại vị trí của nó**, không phải luôn theo IP client ban đầu.
- Log giữa gateway, ISFW và ứng dụng có cần ánh xạ session hoặc request ID để điều tra không.

Một rule áp dụng cho IP thật của client có thể không khớp nếu ISFW chỉ thấy IP của reverse proxy. Việc dùng header HTTP để ghi nhận client gốc cho log ứng dụng cũng **không tự thay đổi IP nguồn ở L3**.

## 5. Chia security zone dựa trên độ tin cậy và chức năng

**Security zone** là tập tài nguyên được quản trị theo một chính sách truy cập chung. Một zone có thể tương ứng với subnet/VRF, nhóm interface hoặc nhóm workload; cách biểu diễn tùy công nghệ.

Ví dụ:

| Zone | Chứa tài nguyên | Mức truy cập dự kiến |
| --- | --- | --- |
| USER | Máy trạm thường | Chỉ các dịch vụ cần cho công việc |
| WEB | Web server/reverse proxy | Nhận HTTPS, gọi đúng dịch vụ backend |
| APP | API và nghiệp vụ | Kết nối có chọn lọc đến DB, DNS, telemetry |
| DATA | DB, storage nhạy cảm | Không nhận truy cập trực tiếp từ USER |
| MGMT | Jump host, công cụ quản trị | Chỉ người/thiết bị được phê duyệt, được giám sát |
| SHARED | DNS, NTP, monitoring, identity | Được sử dụng theo từng nhu cầu cụ thể |
| DEV | Dịch vụ phát triển và thử nghiệm | Không mặc định truy cập hệ thống production |

**Không nhất thiết mọi zone có một mức tin cậy xếp hạng tuyến tính.** Ví dụ USER và DEV có mục đích khác nhau; quyết định cần dựa trên nhu cầu giao tiếp và rủi ro, không chỉ tên gọi “inside” hay “trusted”.

### 5.1. Ma trận luồng được phép

Các địa chỉ **192.0.2.0/24**, **198.51.100.0/24** và **203.0.113.0/24** trong bài là dải dành riêng cho tài liệu theo RFC 5737; không dùng nguyên xi trên mạng Internet thực tế.

Giả sử mạng minh họa có:

- USER: 192.0.2.0/24.
- APP: 198.51.100.0/24.
- DATA: 203.0.113.0/24.
- Máy API: 198.51.100.10.
- Máy DB: 203.0.113.20.

| Nguồn | Đích | Dịch vụ | Quyết định | Mục đích |
| --- | --- | --- | --- | --- |
| USER | Web/API được công bố | TCP/443 | Allow | Sử dụng ứng dụng qua HTTPS |
| API 198.51.100.10 | DB 203.0.113.20 | TCP/5432 | Allow | Truy vấn cơ sở dữ liệu theo nghiệp vụ |
| APP có nhu cầu DNS | Resolver được duyệt | UDP/TCP 53 | Allow có giới hạn | Phân giải tên |
| APP | Collector được duyệt | Cổng telemetry thực tế | Allow có giới hạn | Gửi log và metrics |
| MGMT jump host | Máy chủ cần quản trị | TCP/22 hoặc cổng được phê duyệt | Allow có giới hạn | Quản trị, bảo trì |
| USER | DATA | Mọi cổng không được cấp riêng | Deny | Ngăn truy cập trực tiếp tới dữ liệu |
| DEV | DATA production | Mọi cổng | Deny, trừ ngoại lệ rõ ràng | Cách ly môi trường |
| APP khác | DB 203.0.113.20 | TCP/5432 | Deny nếu không được phê duyệt | Giảm lộ DB cho các ứng dụng không liên quan |

Ma trận trên là **mô hình policy**, không phải trạng thái đo được. Khi triển khai, cần bổ sung đường health check, backup, service discovery, cập nhật hệ thống, identity, kết nối ứng dụng đặc thù và các luồng theo lịch. Không được mặc định tất cả các luồng quan sát thấy đều hợp lệ: traffic thật có thể chứa quét thăm dò hoặc cấu hình sai.

### 5.2. Từ ma trận sang rule chính sách

Một rule tốt thường ghi:

| Trường | Điều cần khai báo |
| --- | --- |
| ID, owner, ticket | Ai yêu cầu và chịu trách nhiệm |
| Source / zone nguồn | Subnet hoặc nhóm workload/danh tính được duyệt |
| Destination / zone đích | Host, VIP, dịch vụ hoặc nhóm đúng phạm vi |
| Application / protocol / port | Những giao thức và cổng thực sự dùng |
| Direction, state | Chiều kết nối mới; xử lý phản hồi tùy loại firewall |
| Action | Allow/Deny và có cần kiểm tra sâu không |
| Log | Sự kiện nào cần ghi để vận hành và điều tra |
| Duration | Quy tắc thường trực hay ngoại lệ có hạn |
| Justification | Phụ thuộc nghiệp vụ và rủi ro chấp nhận |

Ví dụ **quy tắc giả mã để thiết kế**, không phải cú pháp áp dụng được trên thiết bị cụ thể:

~~~text
RULE 100: ALLOW new TCP
  source_zone=APP source=198.51.100.10
  destination_zone=DATA destination=203.0.113.20 port=5432
  reason="order-api -> orders-db"
  log=session-start/session-end as appropriate

RULE 900: DENY new connections
  source_zone=USER destination_zone=DATA
  reason="No direct user-to-database access"
  log=selected-denies-with-rate-limit
~~~

Các rule khác, thứ tự ưu tiên, zone matching, object group và hành vi stateful phụ thuộc nhà sản xuất. Đừng áp dụng nguyên mẫu này lên production. Với firewall có **rule đầu tiên khớp được áp dụng**, rule quá rộng ở phía trên có thể làm rule chặn bên dưới không còn tác dụng; nền tảng khác có thể có cơ chế ưu tiên riêng.

## 6. Những tính năng cần cân nhắc của ISFW

### 6.1. Lọc L3/L4 và kiểm soát theo ứng dụng

Lọc L3/L4 thường dùng IP nguồn/đích, TCP/UDP port và trạng thái. Một số **next-generation firewall (NGFW)** có thể nhận diện ứng dụng, người dùng hoặc dấu hiệu tấn công qua giao thức. Chức năng nào hoạt động thực tế còn phụ thuộc phiên bản, giấy phép, cơ chế định danh, vị trí triển khai, cấu hình TLS và chính sách của tổ chức.

Không nhầm **application identification** với xác thực người dùng cuối: một firewall nhận biết có lưu lượng HTTPS hoặc một ứng dụng cụ thể chưa chắc biết người dùng có quyền gọi API hay không.

### 6.2. IDS/IPS và nội dung được mã hóa

ISFW có thể tích hợp phát hiện/chặn một số dấu hiệu xâm nhập, nhưng IPS cần được đặt trên đường luồng phù hợp; nếu chỉ nhận bản sao traffic thì có thể hỗ trợ phát hiện nhưng không nhất thiết chặn trực tiếp.

TLS và IPsec/VPN có thể che nội dung với firewall trung gian. Nếu có nhu cầu giải mã để kiểm tra sâu, cần đánh giá kỹ thuật, quyền truy cập dữ liệu, hiệu năng, quản trị chứng chỉ và quy định bảo mật. **Không giả định** việc bật firewall đồng nghĩa các phiên HTTPS đều bị kiểm tra nội dung.

### 6.3. High availability (HA) và độ ổn định

ISFW nằm giữa các hệ thống nội bộ quan trọng. Một lỗi hoặc nâng cấp có thể ảnh hưởng nhiều ứng dụng. Thiết kế HA cần xét:

- **Active/passive hoặc active/active:** cách chọn đường, sở hữu IP/gateway, chuyển đổi khi có sự cố.
- **Session/state synchronization:** liệu phiên hiện có có thể duy trì sau failover không.
- **Symmetric routing:** đảm bảo hai chiều qua điểm xử lý phù hợp với trạng thái kết nối.
- **Routing convergence:** khi BGP/OSPF/static route đổi, gói có đi qua đường dự kiến không.
- **Fail-open/fail-closed:** quyết định khi firewall hoặc agent hỏng cần được xác định theo mức bảo vệ và tính sẵn sàng, không tự động chọn một phương án cho mọi zone.
- **Capacity:** throughput, số kết nối đồng thời, tốc độ thiết lập phiên mới, SSL/TLS inspection, logging và khả năng quá tải.

Các thông số công bố bởi nhà sản xuất thường phụ thuộc loại traffic và tính năng bật. Một firewall đạt throughput cao khi chỉ lọc L3/L4 chưa chắc đạt mức đó nếu bật phân tích sâu hoặc ghi log chi tiết.

## 7. Thiết kế trong data center, cloud và hybrid

### 7.1. Data center truyền thống

ISFW có thể kết nối với switch L3, mạng VLAN/VRF hoặc nằm giữa các vùng máy chủ. Cần kiểm tra:

1. Gateway và bảng route tại mỗi subnet.
2. Đường đi/đường về, kể cả khi dùng nhiều gateway và ECMP.
3. Trường hợp hai workload nằm cùng VLAN/subnet.
4. Cổng vật lý, subinterface, trunk, HA và khả năng tránh vòng lặp L2.
5. Các dịch vụ quản trị, DNS, NTP, identity, backup, monitoring đi qua firewall.

Nếu lưu lượng hai máy chủ cùng subnet không vượt qua ISFW, có thể cần đổi cách phân đoạn hoặc bổ sung host/distributed firewall. **Tăng số zone trên sơ đồ không đủ** để tạo phân đoạn hiệu quả.

### 7.2. Mạng đám mây

Cloud có thể cung cấp VPC/VNet, subnet, route table, security group, network ACL, cloud firewall hoặc khả năng chèn appliance ảo. Mỗi sản phẩm có mô hình statefulness, ưu tiên rule và phạm vi áp dụng riêng.

Ví dụ với workload nằm ở các subnet khác nhau, bạn có thể đặt route buộc luồng đi qua một virtual firewall, đồng thời dùng security group để hạn chế ngay tại giao diện VM. Tuy nhiên, cần xác định cơ chế routing của nền tảng có cho phép service insertion trên đường đi và về không; không thể giả định mọi cloud đều hoạt động giống nhau.

**Quản trị tự động hóa:** khi tạo/hủy workload, nhóm địa chỉ và nhãn có thể thay đổi; hãy quản lý rule bằng cấu hình có kiểm soát, có review và phát hiện drift. Một máy ảo bị gắn sai tag có thể bị đưa vào nhóm cho phép sai mục đích nếu nhóm động dựa trên tag đó.

### 7.3. Kubernetes và service mesh

Trong Kubernetes, traffic pod-to-pod có thể đi qua overlay, CNI, node hoặc service abstraction. **Kubernetes NetworkPolicy** (khi CNI hỗ trợ) có thể áp dụng allow tại cấp pod, giúp phân đoạn chi tiết hơn một ISFW tập trung chỉ nhìn thấy kết nối node/VPC.

NetworkPolicy chuẩn có giới hạn ở L3/L4 và không định nghĩa policy deny tường minh theo thứ tự ưu tiên. Service mesh có thể thêm mTLS và authorization theo danh tính workload; tuy nhiên không thay thế phân đoạn mạng, route, host firewall và bảo vệ đường kết nối ra ngoài mesh.

Một thiết kế hybrid thường kết hợp **ISFW giữa các vùng lớn** với **microsegmentation giữa pod/VM trong từng vùng**, cùng chính sách xác thực ở lớp ứng dụng.

### 7.4. VPN và truy cập từ đối tác

Khi VPN kết nối người dùng từ xa, chi nhánh hoặc đối tác vào mạng nội bộ, ISFW có thể giới hạn những subnet hoặc dịch vụ mà nguồn qua VPN được phép truy cập. Tunnel đã mã hóa **không có nghĩa** máy đối tác được quyền mở mọi cổng nội bộ. Cần quan sát IP nguồn sau tunnel/NAT, xác thực danh tính, phân quyền và log theo phiên.

## 8. Threat modeling: ISFW hạn chế đường di chuyển ngang nào?

Giả sử attacker đã kiểm soát một máy người dùng. Đường tấn công mong muốn có thể là:

~~~mermaid
flowchart LR
    USER[Máy người dùng bị chiếm] -->|HTTPS hợp lệ| WEB[Web/API]
    USER -. ISFW chặn .-> DB[(Database)]
    USER -. ISFW chặn .-> MGMT[Máy quản trị]
    WEB -->|Kết nối được phê duyệt| DB
~~~

**Giảm thiểu rủi ro:** firewall nội bộ ngăn máy người dùng tiếp cận DB và mạng quản trị trực tiếp, qua đó giảm khả năng quét, khai thác dịch vụ nội bộ và di chuyển ngang.

**Rủi ro còn lại:** nếu attacker lạm dụng tài khoản hợp lệ hoặc khai thác web/API mà người dùng được phép gọi, đường WEB → DB vẫn có thể bị sử dụng sai. Do đó cần phối hợp xác thực mạnh, phân quyền tối thiểu, vá lỗi, giám sát ứng dụng và quyền DB.

| Tình huống | ISFW hỗ trợ như thế nào? | Biện pháp bổ sung |
| --- | --- | --- |
| Malware ở máy trạm quét DB | Chặn USER → DATA trực tiếp | EDR, bản vá endpoint, giới hạn tài khoản |
| Lộ thông tin đăng nhập quản trị | Giới hạn cổng quản trị vào từ jump host | MFA, PAM, audit, quản trị khóa |
| Ứng dụng dev tìm đường sang DB production | Chặn DEV → DATA production | IAM, phân vùng môi trường, kiểm soát CI/CD |
| API bị chiếm muốn gọi DB khác | Chỉ cho phép API đúng DB/cổng | Quyền DB tối thiểu, TLS, xác thực dịch vụ |
| Firewall bị bypass do route khác | Chưa đủ tác dụng nếu gói không qua ISFW | Thiết kế route, kiểm tra đường đi, telemetry |
| DoS làm đầy bảng session | Rate limit và một số kiểm soát tại ISFW nếu hỗ trợ | Capacity planning, chống DDoS, bảo vệ ứng dụng |

**Phân tích threat model cần mô tả chính xác điểm thực thi.** Nếu một cặp workload có thể giao tiếp qua đường khác không qua firewall, chính sách trên firewall không kiểm soát cặp đó.

## 9. Quy trình xây dựng chính sách ISFW

### Bước 1 — Phân loại tài sản và vùng

Lập inventory máy chủ, ứng dụng, DB, mạng người dùng, máy quản trị, thiết bị hạ tầng, DNS/NTP, backup, identity và kết nối đối tác. Với mỗi tài sản, ghi owner, môi trường, mức nhạy cảm dữ liệu, interface và IP thực tế.

### Bước 2 — Thu thập dữ liệu kết nối

Kết hợp flow logs, NetFlow/IPFIX, firewall log, host telemetry, log ứng dụng và tài liệu dependency. Ghi **source, destination, protocol, port, thời điểm, tần suất, trạng thái và mục đích**. Quan sát đủ khoảng thời gian để thấy job cuối ngày, sao lưu theo tuần hoặc tác vụ bảo trì ít diễn ra.

**Không tự động đưa mọi lưu lượng quan sát được vào allowlist.** Một số luồng có thể đến từ thử quét, cấu hình nhầm hoặc hệ thống đã ngừng sử dụng.

### Bước 3 — Xây ma trận allow và rule owner

Mỗi luồng cần một người xác nhận nhu cầu, mức hạn chế nguồn/đích, cổng và thời hạn. Quy tắc cụ thể cho API → DB tốt hơn “mọi server APP được truy cập mọi server DATA”. Với ngoại lệ tạm thời, ghi ticket, owner, expiry và kế hoạch xóa.

### Bước 4 — Thiết kế topology buộc đi qua firewall

Vẽ cả chiều đi và về. Kiểm tra gateway, routing, VRF, NAT, load balancer, overlay, HA, đường dự phòng và kết nối trong cùng subnet. Xác định nơi rule sẽ thực thi; bổ sung host firewall hoặc microsegmentation khi ISFW tập trung không quan sát được luồng.

### Bước 5 — Đánh giá hiệu năng và khả năng phục hồi

Lập baseline throughput, concurrent sessions, new sessions per second, latency, khả năng xử lý sự cố và logging. Thiết kế HA/failover phù hợp với ứng dụng quan trọng. Bảo đảm đường quản trị khẩn cấp và phương án rollback.

### Bước 6 — Triển khai theo phạm vi nhỏ

Nếu sản phẩm hỗ trợ, dùng chế độ monitor/simulate trước khi bật block. Bắt đầu với vùng không quá phức tạp hoặc nhóm ứng dụng có flow matrix rõ, xác nhận ứng dụng vận hành rồi mới mở rộng. Tránh áp dụng default deny toàn hệ thống trong một lần mà chưa kiểm tra luồng thực tế.

### Bước 7 — Kiểm thử allow và deny

Thử từ **đúng nguồn được phép** và **nguồn nằm ngoài phạm vi**, ghi đường đi và kết quả. Với giao thức có TLS hoặc xác thực ứng dụng, kiểm tra thêm hoạt động ở lớp cao sau khi xác nhận kết nối L3/L4.

### Bước 8 — Giám sát, rà soát và phát hiện drift

Thu log allow/deny cần thiết, correlation với IDS/IPS và ứng dụng, phát hiện route bypass, nhóm đối tượng thay đổi và các rule quá rộng. Định kỳ xác minh rule còn owner, còn nhu cầu và không kéo dài vô thời hạn.

## 10. Thực hành kiểm chứng trong lab được phép

**Mô hình thử:** tạo các máy ảo hoặc namespace lab có ranh giới USER, APP, DATA; cấu hình router/firewall ảo sao cho traffic liên vùng đi qua ISFW. Thay mọi địa chỉ minh họa bằng địa chỉ lab thuộc quyền quản trị trước khi chạy.

| Nguồn thử | Đích | Cổng | Kỳ vọng |
| --- | --- | --- | --- |
| Client USER | Web/API được duyệt | TCP/443 | Allow và trả phản hồi HTTPS hợp lệ |
| Client USER | DB server | TCP/5432 | Deny |
| API server | DB được duyệt | TCP/5432 | Allow nếu cả dịch vụ và xác thực hợp lệ |
| APP server khác | DB không thuộc ứng dụng đó | TCP/5432 | Deny |
| Jump host MGMT | Server được quản trị | TCP/22 | Allow theo danh sách được duyệt |
| Máy USER | SSH trên DB | TCP/22 | Deny |

Lệnh chẩn đoán trên Linux từ **máy lab có quyền kiểm tra**:

~~~bash
# Xem IP và route để biết gói dự kiến đi đâu
ip -br address
ip route
ip -6 route
ip route get 203.0.113.20

# Kiểm tra chỉ khả năng mở kết nối TCP đến cổng đích
nc -vz -w 3 203.0.113.20 5432

# Khi ứng dụng lab có endpoint HTTPS, kiểm tra kết nối ứng dụng
curl -I --max-time 5 https://app.lab.test/

# Quan sát các hop nếu công cụ được cài (không bảo đảm mọi hop trả lời)
traceroute -n 203.0.113.20
~~~

**Đọc kết quả đúng cách:**

- Một phép kết nối TCP thành công chỉ chứng minh có đường tới cổng trong điều kiện đo; chưa chứng minh rằng DB cho phép đăng nhập.
- Một lần timeout có thể do firewall, route, host down hoặc dịch vụ không phản hồi; phải đối chiếu log và trạng thái điểm cuối.
- Không nhận được phản hồi từ một hop trên traceroute không chứng minh hop đó không chuyển tiếp gói.
- Một phép thử từ subnet được phép không chứng minh chính sách đã chặn các subnet khác; cần kiểm tra tiêu cực.
- Kết quả IP có thể khác kết quả dùng hostname nếu DNS, load balancer, proxy hoặc NAT chọn đường/đích khác.

### 10.1. Đối chiếu log và đường đi

Ví dụ sự kiện **giả lập** ở ISFW:

~~~text
time=2026-11-28T09:30:00Z
device=isfw-lab-01
src_zone=USER dst_zone=DATA
src_ip=192.0.2.50 dst_ip=203.0.113.20
protocol=tcp dst_port=5432
action=DENY rule=deny-user-to-data
~~~

Diễn giải: có kết nối mới từ USER đến cổng DB bị từ chối theo chính sách. Điều này là bằng chứng về một **lần thực thi rule**; chưa thể kết luận người dùng đang tấn công. Cần đối chiếu với lịch kiểm thử, chương trình inventory, log endpoint và tần suất để xác định nguyên nhân.

Đối với sự cố “rule allow mà ứng dụng vẫn lỗi”, kiểm tra:

1. Dịch vụ có listen đúng IP/cổng không và chính sách host firewall có cho phép không.
2. DNS, tuyến đi và tuyến về có hợp lệ không; có NAT/proxy làm đổi địa chỉ không.
3. ISFW có nhìn thấy gói ở cả hai chiều và tạo session hợp lệ không.
4. Có rule deny ưu tiên cao hơn, application policy hay IPS làm ngắt kết nối không.
5. MTU/Path MTU Discovery, TLS, chứng chỉ, xác thực, quyền ứng dụng hoặc DB có lỗi không.

## 11. Vận hành, giám sát và chỉ số đánh giá

### 11.1. Giám sát có chủ đích

Các nguồn dữ liệu hữu ích gồm firewall session/deny logs, rule hit counters, flow telemetry, routing events, HA failover events, system capacity, IDS/IPS alerts và log của ứng dụng. Cần đồng bộ thời gian để ghép sự kiện giữa nhiều lớp.

Log nên cho biết **thời gian, zone/interface, IP nguồn/đích, cổng/giao thức, action, rule ID, byte/packet nếu có và trạng thái phiên**. Chỉ ghi dữ liệu thật sự cần thiết, tuân thủ yêu cầu lưu giữ và giảm lộ thông tin nhạy cảm. Logging toàn bộ phiên ở mức chi tiết cao có thể gây quá tải và tốn lưu trữ.

### 11.2. Các chỉ số có ý nghĩa

| Chỉ số | Mục đích | Hạn chế khi diễn giải |
| --- | --- | --- |
| Tỷ lệ luồng được phê duyệt có rule tương ứng | Đo độ bao phủ nghiệp vụ | Rule tồn tại chưa chắc gói đi qua firewall |
| Tỷ lệ kiểm thử deny thành công | Xác minh luồng ngoài phạm vi bị chặn | Chỉ có giá trị cho nguồn/đích đã thử |
| Số rule any-to-any hoặc ngoại lệ quá hạn | Tìm điểm cần thu hẹp quyền | Số rule ít không tự động nghĩa là an toàn |
| Lưu lượng liên vùng không có owner | Tìm dependency hoặc kết nối bất thường | Flow có thể là traffic vận hành hợp lệ chưa được khai báo |
| Session drops, failover, CPU/memory và throughput | Phát hiện suy giảm khả năng phục vụ | Cần so với baseline và thời điểm đổi cấu hình |
| Chênh lệch rule và route theo thời gian | Phát hiện drift/bypass | Cần kiểm tra tác động của thay đổi hợp lệ |

## 12. Những sai lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Đã chia VLAN nghĩa là tất cả VLAN đã được bảo vệ bởi ISFW.” | Phải kiểm tra inter-VLAN routing, ACL và nơi gói thực sự đi qua. |
| “Firewall nội bộ tự bảo vệ được mọi máy trong cùng subnet.” | Traffic cùng subnet có thể đi trực tiếp ở L2 và bỏ qua ISFW tập trung. |
| “Cho phép APP → DATA là đủ.” | Có thể quá rộng; nên giới hạn đúng nguồn, đích, cổng và mục đích. |
| “Đã có VPN thì người dùng được truy cập mọi vùng nội bộ.” | VPN tạo kết nối, còn quyền vào từng vùng phải kiểm soát riêng. |
| “Stateful firewall không cần quan tâm đường về.” | Route bất đối xứng có thể làm phiên thất bại khi state không được chia sẻ. |
| “Có IPS nghĩa là mọi HTTPS đều được giải mã và phân tích.” | Mã hóa và cấu hình kiểm tra ảnh hưởng trực tiếp khả năng quan sát. |
| “Mở rule khẩn cấp rồi để nguyên.” | Cần owner, thời hạn, review và thu hồi ngoại lệ. |
| “Tất cả deny log là tấn công.” | Cần đối chiếu test hợp lệ, lỗi cấu hình và bối cảnh sự kiện. |
| “Một kết nối được firewall cho phép là đủ an toàn.” | Xác thực, phân quyền, bảo vệ ứng dụng và dữ liệu vẫn cần thiết. |

## 13. Bài tập tình huống: Bảo vệ mạng dữ liệu

**Bối cảnh:** hệ thống đặt máy người dùng trong vùng USER, hai API trong vùng APP và một DB trong vùng DATA. Chỉ API-A được quyền kết nối DB tại TCP/5432. Nhóm vận hành có jump host ở vùng MGMT để quản trị DB theo cổng và quyền được phê duyệt. Mạng DEV không cần truy cập DB production.

Các chính sách hiện tại:

~~~text
ALLOW USER -> APP tcp/443
ALLOW APP(any host) -> DATA(any host) tcp/5432
ALLOW MGMT(jump host) -> DATA(db host) tcp/22
DENY  DEV -> DATA all
DENY  USER -> DATA all
~~~

**Câu hỏi:**

1. Quy tắc nào quá rộng nếu chỉ API-A cần dùng DB? Hãy viết lại bằng nhóm/địa chỉ đúng vai trò.
2. Nếu switch L3 vẫn có route trực tiếp APP → DATA mà không qua ISFW, chính sách trên còn bảo vệ được luồng đó không?
3. Nếu API-A kết nối DB thành công nhưng sau đó timeout, những nguyên nhân liên quan tới đường về/stateful/MTU cần kiểm tra?
4. Khi một API mới được autoscaling tạo ra, làm sao bảo đảm chỉ instance của API-A nhận quyền DB?
5. Nếu một máy USER bị chiếm, ISFW chặn luồng trực tiếp nào và luồng hợp lệ nào attacker vẫn có thể thử lạm dụng?
6. Vì sao cần kết hợp kết quả kiểm thử từ các nguồn USER, APP, DEV và MGMT thay vì chỉ thử từ máy DB?

**Gợi ý trả lời:** (1) Thu hẹp APP(any) → DATA(any) thành API-A → đúng DB:5432; bổ sung quyền theo owner. (2) Không, nếu gói bypass điểm thực thi. (3) Route bất đối xứng, session timeout, NAT hoặc Path MTU và thông điệp ICMP. (4) Dùng nhóm/tag/danh tính workload được quản trị và kiểm soát quyền gắn nhãn. (5) Chặn USER → DB/management trực tiếp, nhưng HTTPS USER → APP vẫn cần bảo vệ ứng dụng. (6) Quyết định phụ thuộc nguồn, đường đi và rule thực tế.

## 14. Tổng kết

**Internal Segmentation Firewall** là lớp kiểm soát được đặt giữa các vùng mạng nội bộ để hạn chế truy cập trái mục đích và giảm khả năng di chuyển ngang. Thiết kế có hiệu quả khi xác định rõ **ranh giới tin cậy, ma trận luồng, đường đi thực tế, chính sách stateful, đường quay về, HA và mức quan sát**.

Trong **SECURITY_NETWORK_SECURITY**, ISFW phải được phối hợp với VLAN/VRF và routing, host firewall, microsegmentation, xác thực ứng dụng, VPN, IDS/IPS, logging và quy trình thay đổi. Kết quả cần được chứng minh bằng **kiểm thử allow/deny từ đúng vị trí nguồn**, rà soát rule thường xuyên và khả năng phát hiện đường bypass — không chỉ bằng việc đã lắp đặt một thiết bị firewall.

### Tài liệu tra cứu

- **NIST SP 800-41 Rev. 1 — Guidelines on Firewalls and Firewall Policy:** phân loại firewall và quản trị chính sách lọc.
- **NIST SP 800-207 — Zero Trust Architecture:** mô hình kiểm soát truy cập theo tài nguyên và hạn chế tin cậy ngầm định.
- **NIST SP 800-125B — Secure Virtual Network Configuration for Virtual Machine (VM) Protection:** phân đoạn, kiểm soát mạng ảo trong môi trường VM.
- **RFC 1918 — Address Allocation for Private Internets:** dải địa chỉ IPv4 riêng trong triển khai nội bộ.
- **RFC 5737 — IPv4 Address Blocks Reserved for Documentation:** dải địa chỉ IPv4 dùng trong ví dụ.
- **RFC 4890 — Recommendations for Filtering ICMPv6 Messages in Firewalls:** cân nhắc lọc ICMPv6 mà không phá chức năng mạng.
