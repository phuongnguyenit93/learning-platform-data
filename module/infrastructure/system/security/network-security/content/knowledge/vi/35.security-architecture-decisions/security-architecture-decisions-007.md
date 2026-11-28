# Bảo vệ đường đi của traffic liên vùng

## 1. Bài toán kiến trúc và kết quả cần đạt

Trong chương **Quyết định kiến trúc bảo mật mạng** của module **SECURITY_NETWORK_SECURITY**, bảo vệ đường đi của traffic liên vùng là thiết kế và kiểm chứng các tuyến mà lưu lượng được phép đi qua giữa những miền có mức độ tin cậy khác nhau. Quyết định này liên quan trực tiếp đến phân đoạn VLAN/VRF, firewall, VPN, IDS/IPS, xác thực kết nối, bảo vệ DNS, mạng không dây, hạ tầng đám mây, phân tích lưu lượng, mô hình hóa mối đe dọa và giám sát xâm nhập.

Ví dụ, máy tính nhân viên cần truy cập ứng dụng nội bộ qua HTTPS nhưng không được mở kết nối trực tiếp tới cơ sở dữ liệu. Một đối tác có VPN site-to-site cần đi tới một API được công bố, nhưng không được dò tìm dịch vụ quản trị. Một workload cloud được phép đọc một dịch vụ nhất định ở trung tâm dữ liệu, nhưng đường đi và đường về của kết nối phải được xác minh để các điểm kiểm soát còn quan sát được.

**Traffic liên vùng (inter-zone traffic)** là lưu lượng đi giữa hai vùng an ninh có chính sách khác nhau. Vùng có thể được xác định bằng subnet, VLAN, VRF, VPC/VNet, cloud account, Kubernetes namespace, tập identity hoặc kết hợp nhiều đặc tính. Ranh giới bảo mật là **nơi chính sách có hiệu lực thực sự**, không nhất thiết trùng với ranh giới subnet hay đường kẻ trên sơ đồ.

Một kiến trúc được xem là có khả năng bảo vệ đường đi khi trả lời được năm câu hỏi:

1. Ai, hoặc workload nào, được **khởi tạo kết nối** đến dịch vụ nào?
2. Gói tin thực sự **đi qua những hop và security control nào** ở cả hai chiều?
3. Những đường thay thế nào xuất hiện khi định tuyến thay đổi, có failover, overlay, VPN hoặc IPv6?
4. Bằng chứng nào chứng minh rule cho phép đúng chức năng và rule từ chối đúng truy cập trái phép?
5. Khi policy hoặc một thiết bị lỗi, mạng ứng xử ra sao và ai quyết định phương án phục hồi?

Sau bài này, người học có thể xây dựng bản đồ luồng, ma trận truy cập, so sánh thiết kế firewall tập trung với enforcement phân tán, phân tích đường đi bất đối xứng, phát hiện bypass và route leak, xác minh bằng traffic test/flow log/PCAP và ghi lại quyết định kiến trúc theo mẫu Architecture Decision Record (ADR).

### 1.1. Ba khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Một hiểu lầm thường gặp |
|---|---|---|
| **Reachability** | Có tuyến mạng và khả năng gửi gói tới một đích | Có route đồng nghĩa được phép truy cập |
| **Policy enforcement** | Điểm thực thi cho phép/từ chối, xác thực và kiểm soát phiên | Có ACL trong cấu hình nghĩa mọi gói đều phải đi qua ACL đó |
| **Observability** | Sensor, log và chỉ số đủ để biết chuyện gì diễn ra | Không thấy alert nghĩa không có lưu lượng |

Ba yếu tố phải được kiểm chứng độc lập. Một luồng có thể có route nhưng bị firewall chặn; có thể bị chặn bởi host firewall trước khi tới ranh giới cần kiểm tra; hoặc đi được nhờ route phụ mà sensor trung tâm không quan sát được.

## 2. Mô hình phân vùng, tài sản và quan hệ tin cậy

### 2.1. Vùng an ninh không chỉ là VLAN

Một security zone là nhóm tài sản chia sẻ quy tắc truy cập và mức độ tin cậy tương đối đồng nhất. Ví dụ:

- **USER:** thiết bị người dùng được quản lý.
- **GUEST / IOT:** khách hoặc thiết bị ít được quản lý.
- **APP:** dịch vụ nghiệp vụ và API.
- **DATA:** cơ sở dữ liệu và hệ thống nhạy cảm.
- **MGMT:** giao diện SSH, HTTPS quản trị, SNMP và automation.
- **PARTNER:** kết nối từ hệ thống đối tác qua VPN.
- **CLOUD-WORKLOAD:** ứng dụng trên VPC/VNet.
- **SHARED-SERVICES:** DNS, NTP, IAM, syslog và các dịch vụ dùng chung.

Một VLAN cung cấp ranh giới broadcast lớp 2. Một VRF cung cấp bảng định tuyến lớp 3 riêng. Cả hai **không tự tạo chính sách truy cập tối thiểu**: nếu có route leak hoặc một thiết bị L3 định tuyến giữa các vùng mà không qua điểm kiểm soát, traffic vẫn có thể đến nơi.

Trong môi trường container hoặc cùng subnet, hai workload có thể giao tiếp trực tiếp mà không đi qua firewall liên VLAN. Khi cần giới hạn bên trong một vùng, cần bổ sung host firewall, workload identity, Kubernetes NetworkPolicy hoặc enforcement phân tán phù hợp.

### 2.2. Phân loại tài sản trước khi vẽ tuyến

| Thuộc tính | Câu hỏi cần trả lời | Ảnh hưởng đến quyết định |
|---|---|---|
| Độ nhạy dữ liệu | Workload lưu/đọc dữ liệu gì? | Độ mạnh kiểm soát và mã hóa |
| Mức quan trọng | Dịch vụ có yêu cầu RTO/độ sẵn sàng nào? | Kiến trúc HA, phương án failover |
| Chủ sở hữu | Ai phê duyệt quyền truy cập? | Quy trình thay đổi và review ngoại lệ |
| Danh tính | User, service account, certificate hay thiết bị? | Xác thực ở lớp ứng dụng và workload |
| Vị trí | On-prem, cloud, Wi-Fi, VPN, branch? | Chọn điểm enforcement và tuyến kết nối |
| Phụ thuộc | DNS, IAM, NTP, backup, monitoring, update? | Tránh chặn nhầm traffic hạ tầng |
| Khả năng quan sát | Có flow log, DNS log, EDR, packet capture ở đâu? | Mức tin cậy của kiểm chứng |

**Nguyên tắc:** đánh giá theo luồng nghiệp vụ thực tế, không chỉ theo sơ đồ subnet hiện tại. Ví dụ, giao diện quản trị của firewall nằm cùng mạng vật lý với USER vẫn phải có ranh giới quyền và chính sách quản trị riêng.

## 3. Phân tích mối đe dọa đối với đường đi liên vùng

Mục tiêu của kẻ tấn công khi chiếm một máy USER có thể là tiếp cận dịch vụ DATA, giao diện quản trị hoặc vùng khác mà chính sách không cho phép. Các dạng sai sót quan trọng:

| Tình huống | Cách xuất hiện | Hệ quả | Bằng chứng/kiểm soát |
|---|---|---|---|
| **Direct routing bypass** | Có route từ USER đến DATA ngoài firewall dự kiến | Lưu lượng không chịu kiểm tra liên vùng | Route table, next hop, capture, deny test |
| **Route leak** | VRF/VPC/transit chia sẻ prefix rộng ngoài thiết kế | Mở reachability giữa vùng tin cậy khác nhau | VRF import/export, transit route tables |
| **Asymmetric return path** | Request qua firewall A, response qua firewall B hoặc đường khác | Mất state, gián đoạn hoặc thiếu quan sát | Session table, routing hai chiều, PCAP |
| **Shadow rule** | Rule ALLOW rộng che rule DENY hẹp | Quy tắc mong muốn không được thực thi | Rule hit ID, policy analysis, test |
| **NAT che định danh** | Nhiều client chung SNAT hoặc proxy | Khó truy ngược tài sản thật | NAT/session mapping, proxy identity |
| **IPv6 bypass** | Chỉ áp ACL IPv4, IPv6 vẫn định tuyến | Có đường thay thế chưa kiểm soát | IPv6 route, ACL và negative test |
| **Overlay / tunnel bypass** | Traffic đi trong VPN, SD-WAN, VXLAN hoặc service mesh | Điểm kiểm soát không thấy luồng bên trong | Tunnel endpoints, chính sách overlay, host logs |
| **L2 adjacency không kiểm soát** | Hai workload cùng subnet/VLAN giao tiếp trực tiếp | Firewall L3 trung tâm không xử lý | Switch topology, host policy, workload rules |
| **Failover khác chính sách** | Đường dự phòng không có rule/log tương đương | Mất kiểm soát khi lỗi mạng | HA/failover matrix, kiểm thử chuyển tuyến |
| **Rủi ro DNS hoặc FQDN policy** | DNS split-horizon, CDN, cache dẫn tới IP khác | Rule theo tên không khớp đường đi | DNS response, FQDN object, flow đích thực |

Có thể mô hình hóa qua chuỗi: **nguồn bị xâm nhập → khả năng định tuyến → điểm chính sách → quyền truy cập dịch vụ → tài sản nhạy cảm**. Một thiết kế tốt đặt nhiều lớp kiểm soát để một sai sót về route không tự động cho phép truy cập dữ liệu.

### 3.1. Mô hình giả định cần nêu rõ

Trong bất kỳ thiết kế nào, ghi rõ những điều đang được giả định:

- Firewall đã thực sự nằm trên đường của mọi kết nối liên vùng cần kiểm soát.
- Không có bridge, uplink, overlay hoặc route phụ bỏ qua điểm kiểm soát.
- Mọi thiết bị tham gia có chính sách IPv4/IPv6 tương đương nếu chạy dual-stack.
- Chức năng NAT/proxy và danh tính nguồn có thể được tương quan tại thời điểm sự kiện.
- Tất cả đường dự phòng đều áp chính sách tương đương và có logging.
- Chủ ứng dụng đã xác nhận đúng dependency và port của dịch vụ.

Các giả định này phải trở thành **ca kiểm thử**, không được coi là sự thật chỉ vì hiện diện trong tài liệu.

## 4. Nguyên tắc thiết kế đường đi tin cậy

### 4.1. Bảy nguyên tắc quyết định

1. **Default deny tại ranh giới:** chỉ cho phép những luồng có nhu cầu nghiệp vụ được phê duyệt.
2. **Least privilege theo nguồn, đích và dịch vụ:** tránh mở subnet–subnet, any-any khi chỉ cần một máy hoặc một API.
3. **Mandatory mediation:** mọi đường kết nối thuộc phạm vi phải đi qua điểm kiểm soát tương ứng; không có đường phụ vượt policy.
4. **Identity-aware access:** bổ sung xác thực người dùng/workload, RBAC, mTLS hoặc chính sách ứng dụng khi cần; IP đơn lẻ không đủ đại diện danh tính.
5. **Kiểm soát đường về và trạng thái:** với firewall stateful, phải có session/HA state phù hợp hoặc đường đối xứng đã được thiết kế.
6. **Defense in depth:** kết hợp segmentation, firewall, host/workload policy, DNS, IDS/IPS, EDR và logging.
7. **Có thể kiểm chứng và phục hồi:** mỗi quyết định có positive test, negative test, logging, owner và rollback.

**Điểm quan trọng:** có firewall ở giữa hai thiết bị chưa chứng minh firewall là **choke point bắt buộc**. Muốn chứng minh, cần biết tất cả tuyến chính, tuyến dự phòng và những đường thông qua overlay hoặc cloud.

### 4.2. Phân biệt quyền khởi tạo và quyền phản hồi

Một firewall stateful thường cho phép phản hồi của một kết nối được phép khởi tạo từ USER đến APP mà không cần rule cho APP chủ động mở phiên mới về USER. Đối với ứng dụng có callback, message broker hoặc connection từ server về client, phải định nghĩa riêng luồng thực sự.

Nếu thiết bị hoặc cloud NACL là stateless, có thể phải khai báo rule hai chiều và cổng ephemeral. Không sao chép logic stateful của firewall này sang stateless ACL khác mà không kiểm thử.

## 5. Kiến trúc tham chiếu liên vùng

### 5.1. Mạng lab giả lập

Mọi địa chỉ dưới đây là dải private dành cho ví dụ. Không có thông tin hạ tầng thực hay yêu cầu truy cập ra Internet thật.

| Vùng | Địa chỉ | Chức năng |
|---|---|---|
| USER | 10.40.10.0/24 | Laptop nhân viên |
| GUEST/IOT | 10.40.20.0/24 | Khách và thiết bị ít tin cậy |
| APP | 10.40.30.0/24 | App01: 10.40.30.10 |
| DATA | 10.40.40.0/24 | DB01: 10.40.40.10 |
| MGMT | 10.40.50.0/24 | Switch/router/firewall management |
| SHARED | 10.40.60.0/24 | DNS01: 10.40.60.53; log/AAA |
| PARTNER | 10.41.10.0/24 | Vùng đối tác qua VPN đã cấp phép |
| CLOUD-APP | 10.60.30.0/24 | Workload cloud qua transit được kiểm soát |

~~~mermaid
flowchart TB
    U["USER<br/>10.40.10.0/24"] --> FW["Segmentation Firewall<br/>zone + NAT + IDS/IPS + log"]
    G["GUEST / IOT<br/>10.40.20.0/24"] --> FW
    V["PARTNER VPN<br/>10.41.10.0/24"] --> FW
    C["CLOUD-APP<br/>10.60.30.0/24"] --> T["Cloud / Hybrid Transit<br/>routing kiểm soát"]
    T --> FW
    FW --> APP["APP<br/>App01:443"]
    FW --> DB["DATA<br/>DB01:5432"]
    FW --> MG["MGMT<br/>SSH/HTTPS quản trị"]
    FW --> S["SHARED<br/>DNS / AAA / log"]
    FW -. "policy logs / flow events" .-> SOC["SIEM / NDR"]
~~~

Sơ đồ là **mô hình logic**: tất cả lưu lượng liên vùng được thiết kế để đi qua segmentation firewall hoặc một điểm enforcement tương đương có chính sách nhất quán. Trong triển khai thật, cần đối chiếu chi tiết interface, switch path, VLAN trunk, route table, VRF, cloud transit và đường HA để xác minh sơ đồ đúng.

Nếu APP và DATA dùng cùng một hypervisor, virtual switch hoặc overlay không buộc traffic qua firewall, sơ đồ logic có thể không phản ánh đường đi thực. Khi đó cần routing cưỡng bức (service insertion) hoặc enforcement theo workload.

### 5.2. Ma trận luồng nghiệp vụ

| Nguồn | Đích | Dịch vụ/port minh họa | Chính sách | Điều kiện và lý do |
|---|---|---|---|---|
| USER | App01 10.40.30.10 | HTTPS TCP/443 | ALLOW | Ứng dụng được phê duyệt, xác thực ở lớp app |
| USER | DB01 10.40.40.10 | PostgreSQL TCP/5432 | DENY | Người dùng không truy cập DB trực tiếp |
| APP/App01 | DB01 | PostgreSQL TCP/5432 | ALLOW | Chỉ service identity/host cần DB |
| GUEST/IOT | APP/DATA/MGMT | Mọi dịch vụ | DENY | Không có nhu cầu truy cập nội bộ |
| USER | DNS01 10.40.60.53 | DNS UDP/TCP 53 | ALLOW | Dùng resolver được quản lý |
| USER | MGMT | SSH TCP/22, HTTPS TCP/443 | DENY | Quản trị phải đi qua bastion/AAA |
| Bastion quản trị đã xác thực | MGMT IP cụ thể | SSH/HTTPS theo thiết bị | ALLOW có điều kiện | Quản trị có MFA, RBAC và log |
| PARTNER | App01 API chuyên dụng | HTTPS TCP/443 | ALLOW hạn chế | Chỉ endpoint/identity theo hợp đồng |
| PARTNER | DATA/MGMT | Mọi dịch vụ | DENY | Ngăn lan ngang từ mạng đối tác |
| CLOUD-APP | App01 endpoint nội bộ | HTTPS TCP/443 | ALLOW có điều kiện | Route qua transit, mTLS nếu yêu cầu |
| APP/DATA | Collector log | Syslog TLS TCP/6514 nếu hỗ trợ | ALLOW | Gửi log tới hệ thống được quản lý |
| Các vùng khác | DATA/MGMT | Mọi dịch vụ không được liệt kê | DENY mặc định | Giảm bề mặt truy cập |

Cổng là ví dụ nghiệp vụ, không phải danh sách mở mặc định. Ngoại lệ cần có **owner, business justification, hạn hiệu lực và kế hoạch review**. Đối với ứng dụng dùng nhiều microservice hoặc cổng thay đổi, ưu tiên security group theo service identity hoặc các đối tượng được quản lý thay vì ALLOW rộng cả subnet.

### 5.3. Thế nào là đường đi được bảo vệ?

Một luồng USER → App01 TCP/443 được xem là phù hợp khi:

- USER nằm trong đúng zone, thiết bị có mapping IP/MAC/danh tính được xác minh.
- Lưu lượng đi qua firewall policy bắt buộc, không đi đường phụ không quan sát được.
- Firewall cho phép đúng dịch vụ đích, rule và chiều khởi tạo, đồng thời ghi log cần thiết.
- Đích có TLS và xác thực ứng dụng đúng thiết kế; host firewall vẫn có chính sách phù hợp.
- Traffic phản hồi theo tuyến được dự kiến và không bị drop hoặc bypass do bất đối xứng.
- Một test tương ứng tới DB01:5432 trực tiếp từ USER bị chặn và chứng minh được tại ranh giới.

## 6. Các mẫu kiến trúc để thực thi chính sách

### 6.1. Firewall tập trung (centralized inspection)

Mọi inter-zone traffic được đưa về một cặp firewall hoặc cụm inspection trung tâm.

**Ưu điểm:** dễ tập trung rule, log, IPS và audit; một điểm kiểm soát dễ nhận diện. **Đổi lại:** có thể tăng độ trễ, gây hairpin/trombone traffic, tạo phụ thuộc vào đường transit, scale và HA; nếu một đường bỏ qua firewall, chính sách trung tâm mất hiệu lực đối với đường đó.

Thường phù hợp khi số lượng zone hữu hạn, topology ổn định và có năng lực firewall đủ đáp ứng băng thông thực tế. Cần xem **throughput trong chế độ bật TLS/IPS/log**, không chỉ thông số tối đa của thiết bị.

### 6.2. Firewall phân tán hoặc microsegmentation

Chính sách thực thi tại host, hypervisor, workload, CNI hoặc các virtual firewall gần tài sản. Có thể kiểm soát cả **east–west traffic** giữa workload cùng subnet/overlay.

**Ưu điểm:** giảm nhu cầu đưa mọi packet về trung tâm; giới hạn lan ngang ở mức workload; policy có thể dùng nhãn hoặc danh tính ứng dụng. **Đổi lại:** nhiều enforcement point hơn, phụ thuộc độ chính xác của inventory/label, policy lifecycle, agent health và khả năng tổng hợp logs.

Một thiết kế phân tán vẫn cần điểm kiểm soát **north–south egress** và traffic từ đối tác, không thể mặc nhiên thay thế firewall biên.

### 6.3. VRF riêng với firewall transit

Mỗi vùng có VRF/routing table riêng; chỉ những tuyến được công bố qua transit/firewall cho phép reachability giữa VRF. Dùng route leaking có chủ đích hoặc firewall làm điểm trao đổi.

**Ưu điểm:** ranh giới định tuyến rõ, tách được các vùng có địa chỉ hoặc yêu cầu khác nhau. **Rủi ro:** một route leak rộng có thể tạo đường đi ngang ngoài firewall nếu L3 device định tuyến trực tiếp; asymmetric routing nếu các VRF có default route khác nhau. Kiểm tra cả import/export route target, PBR, NAT, route propagation và return path.

### 6.4. Hub-and-spoke hoặc service insertion trong cloud

Các VPC/VNet ứng dụng kết nối qua transit/hub; các route table dẫn traffic đến một cụm kiểm tra tập trung hoặc các điểm enforcement theo zone. Một số nền tảng hỗ trợ service insertion hoặc gateway load balancing cho thiết bị bảo mật ảo.

**Ưu điểm:** chuẩn hóa chính sách nhiều account/VPC/VNet. **Rủi ro:** route table không đồng nhất, đường peering trực tiếp, NAT, subnet áp dụng sai, thiếu return-path symmetry, scale của firewall ảo và chi phí truyền liên vùng/availability zone.

### 6.5. Bảng so sánh ra quyết định

| Tiêu chí | Tập trung | Phân tán | VRF + firewall transit | Cloud hub + inspection |
|---|---|---|---|---|
| Phạm vi bảo vệ mạnh nhất | Liên VLAN/zone có tuyến đi qua firewall | Workload/host, kể cả east–west nội vùng | Các miền định tuyến tách biệt | VPC/VNet qua transit/hub |
| Quan sát tập trung | Thường thuận lợi | Cần tổng hợp nhiều sensor/agent | Thuận lợi tại firewall transit | Phụ thuộc flow log và service insertion |
| Độ phức tạp quản trị | Rulebase/firewall/HA | Identity, labels, agent lifecycle | VRF/route leak/policy | Route table, attachment, NAT, multi-account |
| Nguy cơ bypass | Route phụ, L2 cùng subnet | Agent thiếu hoặc workload không được gắn policy | Leak ngoài đường transit | Peering, route sai, direct egress |
| Chi phí vận hành | Scale và nâng cấp firewall | Quản lý policy phân tán | Routing/VRF và network operations | Transit/inspection/data transfer |
| Phù hợp | Hệ thống truyền thống, số zone vừa phải | Microservice và mạng east–west dày | Phân vùng định tuyến rõ trên LAN/WAN | Hybrid/multi-account, nhiều VPC/VNet |

Không có một kiến trúc tốt nhất cho mọi hệ thống. Nên đưa ra ADR dựa trên yêu cầu đo được: rủi ro, tính sẵn sàng, lưu lượng, chi phí, độ phủ quan sát và khả năng vận hành của nhóm.

## 7. Xác minh đường đi và đường về

### 7.1. Đường đi của một packet

Với mỗi luồng trong ma trận, vẽ **đường đi thực tế**:

1. Máy nguồn quyết định địa chỉ đích (có thể qua DNS, proxy hoặc service discovery).
2. Hệ điều hành chọn interface, source IP, default gateway và route.
3. Switch hoặc virtual network chuyển traffic đến L3 next hop.
4. Router/VRF/PBR/SD-WAN chọn đường; NAT có thể đổi địa chỉ/cổng.
5. Firewall đánh giá zone, state, policy, IPS hoặc security profile.
6. Traffic tới interface đích, host firewall, proxy/load balancer hoặc service mesh.
7. Dịch vụ đích xử lý; gói phản hồi đi theo route phù hợp.

**Không giả định routing và NAT có cùng thứ tự trên mọi vendor.** Cần dùng flow trace, session lookup và tài liệu nền tảng để xác minh pre-NAT/post-NAT tuple theo chính sản phẩm.

~~~mermaid
sequenceDiagram
    participant U as USER client
    participant R as Router / VRF
    participant F as Firewall
    participant A as App01
    U->>R: TCP SYN đến App01:443
    R->>F: Chuyển theo route được kiểm soát
    F->>F: Xét zone, session, NAT và policy
    F->>A: Cho phép SYN theo rule cụ thể
    A-->>F: SYN-ACK qua đường đã thiết kế
    F-->>R: Phản hồi thuộc state hợp lệ
    R-->>U: Hoàn tất TCP handshake
    U->>A: HTTPS request qua phiên được phép
~~~

Trên sơ đồ lý tưởng này, firewall thấy hai chiều của cùng kết nối. Nếu route chiều về không qua cùng thành phần stateful hoặc không có cơ chế chia sẻ trạng thái hợp lệ, phiên có thể lỗi. Một số nền tảng hỗ trợ asymmetric routing trong điều kiện xác định; phải mô tả cụ thể, không giả định tất cả firewall xử lý như nhau.

### 7.2. Route đối xứng không có nghĩa cùng từng hop

Hai chiều có thể qua các interface khác nhau của cùng một firewall hoặc qua cặp firewall có **session synchronization** được nhà cung cấp hỗ trợ. Điều quan trọng là điểm enforcement có trạng thái đủ để áp dụng chính sách và traffic không đi đường không được kiểm soát.

Cần kiểm tra:

- Route table và VRF trên nguồn, gateway, firewall, transit, destination.
- PBR, ECMP, load balancing và đường failover.
- NAT/SNAT/DNAT; tuple sau dịch dùng khi tra session.
- Interface/zone ingress và egress của từng luồng.
- Security policy và local-in policy tại địa chỉ thiết bị.
- Đường trả lời, state table và cách HA đồng bộ session.
- Đường khác như peering, overlay, direct attachment, VPN hoặc đường IPv6.

### 7.3. Test trường hợp không đối xứng

Một test TCP thất bại khi SYN đi qua firewall nhưng SYN-ACK đi đường khác không chứng minh một rule DENY đúng. Cần xác minh packet tới từng điểm, nguồn của RST/ICMP và session state. Trong môi trường được phê duyệt, có thể lấy capture giới hạn ở hai phía firewall và server để phân biệt sai route với chặn policy.

## 8. Kiểm soát route leak và reachability

### 8.1. VRF không tự động là firewall

Giả sử USER thuộc VRF-USER và DATA thuộc VRF-DATA. Mặc định hai bảng route độc lập. Nếu route từ VRF-DATA được import thẳng vào VRF-USER, lưu lượng có thể đi qua router L3 mà **không** qua firewall như thiết kế.

Để tránh lỗi:

- Tách ownership cho route advertisement và security policy.
- Liệt kê prefix nào được phép exchange, next hop/VRF nào thực thi kiểm soát.
- Tránh import/export toàn bộ bảng route chỉ vì cần một dịch vụ.
- Giới hạn prefix list và route policy; theo dõi thay đổi route.
- Kiểm tra cả tuyến đi và tuyến trả lời, IPv4 và IPv6.
- Thử negative reachability giữa các vùng vốn phải cách ly sau mỗi lần đổi BGP/static route.

### 8.2. FIB khác RIB

**Routing Information Base (RIB)** chứa thông tin route được chọn theo control plane; **Forwarding Information Base (FIB)** là bảng chuyển tiếp mà data plane dùng. Một route hiện diện trong control plane không bảo đảm packet thực tế sẽ đi đúng nơi khi còn PBR, NAT, ACL, tunnel, ECMP hoặc phần cứng forwarding.

Khi điều tra sai đường:

1. Kiểm tra tuyến hiệu lực cho đúng destination (longest-prefix match và policy route).
2. Xác minh next hop được phân giải và interface đang hoạt động.
3. Kiểm tra security zone mà packet vào/ra, đặc biệt với virtual interface.
4. Đối chiếu NAT và session logs.
5. Kiểm thử bằng packet có đúng nguồn/đích/giao thức, không suy ra từ ping một địa chỉ khác.

### 8.3. Kiểm soát mạng overlay

VXLAN, GRE, SD-WAN tunnel, site-to-site VPN và service mesh có thể làm gói ban đầu nằm **bên trong** một lớp encapsulation hoặc phiên bảo mật khác. Firewall trung tâm có thể chỉ thấy endpoint tunnel, không thấy client/service gốc.

Cần quyết định rõ enforcement nằm **trước encapsulation, sau decapsulation** hay tại điểm đầu cuối/workload. Không tính tunnel endpoint thành toàn bộ các danh tính ứng dụng. Mọi nhánh đường dự phòng cũng cần kiểm chứng cùng tiêu chí.

## 9. Firewall liên vùng và chính sách least privilege

### 9.1. Chọn rule theo luồng nghiệp vụ

Ví dụ policy logic:

~~~text
ALLOW USER          -> App01      TCP/443
DENY  USER          -> DB01       TCP/5432
ALLOW App01         -> DB01       TCP/5432
DENY  GUEST/IOT     -> APP/DATA   any
ALLOW USER          -> DNS01      UDP/53,TCP/53
DENY  USER          -> MGMT       SSH/HTTPS/SNMP
ALLOW ADMIN-BASTION -> MGMT-IP    only approved management services
DENY  PARTNER       -> DATA/MGMT  any
ALLOW PARTNER       -> APP-API    TCP/443 with app authorization
DENY  other inter-zone flows unless explicitly approved
~~~

Đây là **ý định chính sách**, không phải lệnh cấu hình trực tiếp trên bất kỳ hãng firewall nào. Khi triển khai cần xác nhận order, identity source, NAT, zone, rule UUID, đối tượng FQDN, L7 service và hành động log.

Các vấn đề dễ bị bỏ qua:

- Một **allow-all** phía trên che rule DENY phía dưới.
- Rule cho subnet rộng khi chỉ cần một máy đích.
- Nguồn là IP proxy hoặc SNAT, mất danh tính endpoint.
- Firewall service-object cho phép TCP nhưng ứng dụng dùng cả UDP.
- Rule không gắn zone đúng vì đường đi thực tế qua interface khác.
- Bộ lọc áp cho forwarding nhưng **không** bảo vệ management plane của chính firewall.
- Rule time-based hoặc dynamic identity biến đổi sau khi người kiểm thử kết thúc.

### 9.2. Giao thức không đồng nghĩa ứng dụng

TCP/443 không bảo đảm đó là HTTPS đến đúng dịch vụ; một client có thể sử dụng port 443 cho ứng dụng khác. Do đó, nơi có rủi ro cao nên kết hợp:

- Firewall L3/L4 kiểm soát địa chỉ, dịch vụ, zone và kết nối.
- TLS xác thực server, mTLS nếu cần danh tính hai chiều.
- Authorization ở API/ứng dụng hoặc service mesh.
- IDS/IPS/NDR nhận diện bất thường trong phạm vi quan sát.
- EDR/host firewall ngăn tiến trình trái phép hoặc truy cập nội vùng.
- Ghi log tương quan để kiểm chứng identity, destination và hành động.

Giải mã TLS hoặc DPI chỉ triển khai trong phạm vi được phê duyệt và hiểu ràng buộc riêng tư, hiệu năng, mTLS và certificate pinning. Không nên giả định mọi traffic mã hóa đều có thể được inspection đầy đủ.

## 10. DNS, xác thực kết nối và dữ liệu giám sát

### 10.1. DNS tạo ra đường đi gián tiếp

Một client truy cập app.example nội bộ có thể nhận IP khác theo VPN split-horizon, DNS cache, CDN hoặc cloud private endpoint. Firewall rule theo FQDN có thể cập nhật danh sách IP ở chu kỳ khác với client.

Kiểm thử cần ghi:

- Resolver và câu trả lời DNS ở đúng thời điểm.
- IP mà client thực sự kết nối, không chỉ hostname người dùng nhập.
- FQDN object của firewall và thời điểm cập nhật.
- Port/transport thật, Host header/TLS SNI nếu có.
- Đường tới resolver được phép và chính sách DNS egress.
- Trường hợp DoH/DoT khiến sensor mạng không thấy QNAME nếu không có nguồn hợp lệ ở endpoint/resolver.

Chặn UDP/53 trực tiếp nhưng để lộ đường DNS khác cần được phản ánh trong thiết kế; không thể coi mọi yêu cầu HTTPS tới một resolver ngoài là truy vấn DNS đã giải mã được.

### 10.2. Xác thực và phân quyền tại điểm dịch vụ

IP/zone là tín hiệu vị trí, không thay thế danh tính. Với PARTNER → APP, ngoài kết nối VPN đã xác thực còn cần authorization theo ứng dụng (mTLS, OAuth/OIDC hoặc cơ chế thích hợp). Với ADMIN → MGMT, đi qua bastion, MFA, AAA và RBAC; USER không có quyền trực tiếp vào interface quản trị.

Trong cloud, identity policy/IAM có thể quyết định ai được gọi control plane API, độc lập với việc hai workload reachability ở lớp mạng. Phải ghi rõ lớp nào chịu trách nhiệm **authentication**, **authorization** và **network enforcement**.

## 11. Bảo vệ đường liên vùng trong cloud và hybrid

### 11.1. Các lớp điều khiển cần biết

| Thành phần | Chức năng có thể có | Câu hỏi kiểm chứng |
|---|---|---|
| VPC/VNet subnet route | Chọn next hop cho lưu lượng | Có route trực tiếp bỏ qua inspection hub không? |
| Transit Gateway / Virtual WAN / routing hub | Kết nối các network và bảng route | Attachment/propagation/association nào được bật? |
| Security group / NSG | Kiểm soát inbound/outbound theo interface/workload | Mở đúng nguồn/đích/port và identity không? |
| Network ACL / subnet ACL | Chặn/cho phép ở ranh giới subnet theo nền tảng | Stateful hay stateless, chiều về/ephemeral ports đúng không? |
| Cloud firewall / virtual appliance | Inspection và enforcement tập trung | Flow có thực sự đi qua appliance cả hai chiều? |
| NAT gateway | Dịch địa chỉ egress, đôi khi tập trung lưu lượng | Có nguồn gốc nào bị che, có NAT mapping log không? |
| Load balancer / API gateway | Phân phối, xác thực hoặc lọc ở lớp ứng dụng | Endpoint thật nằm đâu, health check theo route nào? |
| Private endpoint / service endpoint | Kết nối private đến dịch vụ được quản lý | Có đường public thay thế ngoài chính sách không? |
| VPN / private circuit | Kết nối hybrid | Prefix, route, failover, encryption và policy của hai đầu |

Không có một thứ tự chung cho mọi nhà cung cấp. Một số security group có semantics stateful, trong khi một số ACL stateless; mô hình phải dựa trên tài liệu nền tảng thật và test traffic cụ thể.

### 11.2. Thiết kế hub-and-spoke

Ví dụ CLOUD-APP ở một spoke muốn đến DATA on-prem. Bản vẽ mục tiêu:

~~~mermaid
flowchart LR
    CA["Cloud application spoke"] --> CT["Cloud transit route table"]
    CT --> CF["Cloud firewall / inspection"]
    CF --> VPN["VPN / private circuit"]
    VPN --> DF["Datacenter firewall"]
    DF --> DB["DATA service"]
    CT -. "direct route sai thiết kế" .-> DR["Đường bypass cần loại trừ"]
~~~

Hai firewall có thể cùng tham gia policy nhưng không tự bảo đảm tính nhất quán. Kiểm tra DNS resolution, route trong spoke/transit, NAT, VPN BGP prefix, egress filter, on-prem firewall, chiều về và private/public endpoint. Nếu cloud transit route dẫn thẳng tới VPN bỏ qua cloud firewall, các log ở firewall ảo sẽ không thấy luồng dù đường đi vẫn hoạt động.

### 11.3. East–west trong Kubernetes và cloud native

Khi hai pod hoặc service trong cùng cluster giao tiếp qua overlay, firewall liên VPC có thể không thấy traffic. Cần lựa chọn enforcement theo namespace/pod/service identity, CNI policy, service mesh hoặc host firewall; đồng thời xét DNS, kube-system, ingress controller, egress gateway và network policy mặc định.

Với Kubernetes NetworkPolicy, hiệu lực phụ thuộc CNI/network plugin hỗ trợ và chính sách lựa chọn pod. Không mặc định tồn tại một policy có nghĩa mọi giao thức L7 đều được kiểm soát. Workload identity và mTLS bổ sung kiểm tra danh tính và mã hóa.

## 12. IPv6, Wi-Fi, VPN và thiết bị di động

### 12.1. IPv6

Nếu mạng dual-stack, IPv6 tạo một tập địa chỉ, route và policy riêng. Một ứng dụng có thể dùng IPv6 vì bản ghi AAAA, dù đội vận hành chỉ test IPv4.

Kiểm tra:

- Prefix IPv6 của USER/APP/DATA/MGMT, ULA/GUA và route thực tế.
- Firewall rules, local-in, stateful handling và security groups cho IPv6.
- Router Advertisement, Neighbor Discovery và quyền gửi/nhận ICMPv6 cần thiết.
- Đường tunnel hoặc NAT64/DNS64 nếu triển khai.
- Những test DENY và ALLOW tương ứng với IPv4, từ đúng nguồn.

Không tắt ICMPv6 bừa bãi: một số loại ICMPv6 cần thiết cho hoạt động bình thường của IPv6, bao gồm Neighbor Discovery và Path MTU Discovery.

### 12.2. Wi-Fi, IoT và NAC

SSID guest/employee/IoT có thể ánh xạ động vào VLAN hoặc policy riêng qua NAC. Kiểm chứng người dùng sau roaming có ở zone dự kiến không, gateway nào định tuyến packet, có đường controller tunnel bỏ qua segmentation firewall không. Đặc biệt, thiết bị IoT đôi khi giao tiếp ngang trong cùng VLAN; nếu đó là rủi ro, cần client isolation, private VLAN hoặc microsegmentation tương ứng.

### 12.3. VPN và kết nối đối tác

VPN remote access và site-to-site VPN thường có IP pool, route, split tunnel và policy khác nhau. Một host khi kết nối từ xa có thể dùng cả Internet tại nhà lẫn mạng doanh nghiệp; không suy rằng mọi luồng đều đi qua firewall công ty.

Với đối tác, ưu tiên giới hạn prefix và endpoint, quyền ứng dụng, danh tính và kiểm toán; không quảng bá cả mạng DATA/MGMT qua đường VPN chỉ để truy cập một API.

## 13. Khả năng sẵn sàng, HA và chế độ lỗi

Thiết kế bảo vệ đường đi phải xử lý cả khi link hoặc thiết bị không khả dụng.

### 13.1. Những trạng thái lỗi cần mô phỏng

| Sự kiện | Rủi ro bảo mật/vận hành | Điều kiện kiểm thử |
|---|---|---|
| Firewall primary lỗi | Mất đường hoặc chuyển sang rule không tương đương | Failover có session/policy, ứng dụng được phép tiếp tục |
| Một uplink mất | Route khác đưa qua đường bypass | Negative test vẫn bị chặn sau hội tụ |
| Routing adjacency mất | Prefix bị rút, đường về bất đối xứng | Route/FIB, session log và recovery time |
| Log collector lỗi | Traffic vẫn hoạt động nhưng mất quan sát | Alert về mất telemetry, hàng đợi/buffering |
| DNS/AAA/NTP mất | Dịch vụ xác thực hoặc kiểm toán trục trặc | Đường dự phòng đã được phê duyệt |
| Cloud attachment hoặc transit lỗi | Traffic đi peering/public endpoint hoặc ngừng | Ràng buộc route và health check |
| Host policy agent ngừng | Microsegmentation có thể mất hiệu lực tùy cấu hình | Hành vi fail-open/fail-close đã được quyết định |

**Fail-open và fail-closed** là quyết định kiến trúc có tác động nghiệp vụ: fail-open giữ traffic đi tiếp nhưng có thể giảm kiểm soát; fail-closed bảo vệ ranh giới nhưng làm gián đoạn dịch vụ. Không áp một lựa chọn cho mọi zone mà không đánh giá rủi ro, RTO và khả năng khôi phục.

### 13.2. Quyết định hiệu năng

Lưu lượng qua firewall tập trung có thể tạo bottleneck. Phải ước tính:

- Throughput và packet rate cực đại/p95, bao gồm overhead VXLAN/VPN/TLS.
- Số phiên đồng thời và số kết nối mới mỗi giây.
- Độ trễ thêm do hairpin, inspection, logging và các vùng địa lý.
- Hiệu năng khi bật IPS/SSL inspection, không chỉ thông số firewall theo điều kiện lý tưởng.
- Băng thông khi failover chỉ còn một node hoặc một uplink.
- Chi phí data transfer xuyên availability zone/region/cloud transit.
- Headroom tăng trưởng và cửa sổ nâng cấp.

**Đảm bảo sẵn sàng và bảo mật phải được thử đồng thời.** Một bài failover chỉ chứng minh ứng dụng vẫn trả 200 nhưng không thử luồng DENY sẽ bỏ sót rủi ro mở đường trái phép.

## 14. Kế hoạch xác minh bằng test traffic

Mọi thử nghiệm dưới đây chỉ chạy từ máy nguồn, thiết bị và dịch vụ **thuộc môi trường được cấp phép**. Ưu tiên lab và bảo đảm lưu lượng nhỏ, có thời gian/điều kiện dừng.

### 14.1. Ma trận kiểm thử kiến trúc

| Test ID | Nguồn → đích | Lưu lượng | Kỳ vọng | Bằng chứng cần có |
|---|---|---|---|---|
| IZ-01 | USER → App01 | TCP/443 | ALLOW, HTTPS hợp lệ | Client, policy ALLOW, app log |
| IZ-02 | USER → DB01 | TCP/5432 | DENY | Firewall DENY/hit, ingress path |
| IZ-03 | APP → DB01 | TCP/5432 | ALLOW theo nguồn app | Session/policy, DB listener |
| IZ-04 | GUEST/IOT → App01 | TCP/443 | DENY | Zone, log policy |
| IZ-05 | USER → MGMT | TCP/22 | DENY | Local-in/ACL nếu đích là IP thiết bị, boundary log |
| IZ-06 | USER → DNS01 | UDP/53 | ALLOW, DNS response | DNS log và firewall |
| IZ-07 | USER → DNS01 | TCP/53 | ALLOW khi cần | DNS TCP log và firewall |
| IZ-08 | PARTNER → App01 API | TCP/443 | ALLOW có hạn chế identity | VPN/policy + API auth |
| IZ-09 | PARTNER → DB01 | TCP/5432 | DENY | VPN route + firewall log |
| IZ-10 | CLOUD-APP → App01 | TCP/443 | ALLOW qua transit/inspection | Cloud flow, VPN, on-prem policy |
| IZ-11 | USER IPv6 → MGMT IPv6 | TCP/22 | DENY | IPv6 route/firewall log |
| IZ-12 | USER → DB01 sau failover | TCP/5432 | Vẫn DENY | Rule/log trên node mới |
| IZ-13 | USER → App01 sau failover | TCP/443 | Vẫn ALLOW | Health check và log |
| IZ-14 | Workload cùng subnet → workload nhạy cảm | Port không được duyệt | DENY theo host/workload policy | Host/CNI logs, test tại đích |

IZ-14 chỉ áp dụng khi kiến trúc yêu cầu **intra-zone isolation**; nếu không, ghi rõ rủi ro tồn tại. Với mỗi ca, ghi Test ID, địa chỉ ở thời điểm đó, zone, protocol, port, timestamp UTC, expected, actual, policy ID, thiết bị quan sát, trạng thái PASS/FAIL/INCONCLUSIVE/NOT RUN.

### 14.2. Lệnh chẩn đoán từ máy Linux trong lab

Xác minh source IP, route và interface:

~~~bash
ip -br address
ip route get 10.40.30.10
ip route get 10.40.40.10
~~~

Ví dụ kiểm tra kết nối TCP ở các cổng được đưa vào test plan:

~~~bash
nc -vz -w 3 10.40.30.10 443
nc -vz -w 3 10.40.40.10 5432
~~~

Kiểm tra HTTPS bằng tên được cấu hình trong DNS lab:

~~~bash
curl --connect-timeout 3 --max-time 10 \
  --resolve app.lab.example:443:10.40.30.10 \
  https://app.lab.example/health
~~~

Kiểm tra DNS UDP và TCP (chỉ khi DNS01 có bản ghi lab):

~~~bash
dig @10.40.60.53 app.lab.example A +tries=1 +time=2
dig +tcp @10.40.60.53 app.lab.example A +tries=1 +time=2
~~~

Nếu dùng CA nội bộ, cấu hình trust store hoặc tham số --cacert theo đúng quy trình. Không bỏ kiểm tra TLS để có kết quả PASS. TCP connect thành công chưa đồng nghĩa truy cập ứng dụng/DB đã được ủy quyền; cần đối chiếu app log và tầng xác thực.

### 14.3. Kiểm tra đường thực tế

Trên Linux, traceroute có thể cung cấp dữ liệu về một số hop nhưng **không chứng minh** mọi packet đều theo đường được vẽ, nhất là với ECMP, NAT, firewall lọc ICMP hoặc overlay.

~~~bash
traceroute -n 10.40.30.10
~~~

Bằng chứng mạnh hơn gồm:

- Route/FIB lookup trên source, gateway, router/VRF, firewall, cloud transit và destination.
- Log session/policy rule ID, ingress/egress interface và NAT translation.
- Packet capture có filter hẹp ở nhiều điểm nếu cần.
- Ứng dụng đích xác nhận yêu cầu có timestamp phù hợp.
- Negative test đúng đường phải chặn, không chỉ ping thất bại.

### 14.4. Capture giới hạn ở môi trường được cấp phép

Ví dụ tại một sensor lab:

~~~bash
sudo tcpdump -i <IFACE> -nn -s 128 -c 200 \
  -w /var/tmp/iz-01.pcap \
  'host 10.40.10.25 and host 10.40.30.10 and tcp port 443'
~~~

Thay IFACE bằng interface thật. Nếu có NAT, filter có thể cần thay theo IP trước/sau dịch tại vị trí thu. Tham số -s 128 giới hạn dữ liệu thu, có thể thiếu payload; -c 200 dừng khi nhận đủ gói, cần giới hạn thời gian riêng nếu không có traffic.

Phân tích offline:

~~~bash
capinfos /var/tmp/iz-01.pcap
tshark -r /var/tmp/iz-01.pcap -q -z conv,tcp
sha256sum /var/tmp/iz-01.pcap
~~~

Không thu packet toàn hệ thống khi chỉ cần một flow và không đưa PCAP chứa dữ liệu nhạy cảm lên dịch vụ không được phép. Hash chỉ xác minh file giữ nguyên byte từ lúc tính, không chứng minh capture đầy đủ.

## 15. Cách xác nhận một negative test đạt yêu cầu

**Một timeout trên client không tự động là PASS.** Có ít nhất năm nguyên nhân khiến kết nối thất bại: firewall chặn, server không lắng nghe, route sai, host firewall chặn, hoặc packet chưa tới firewall.

Với IZ-02 (USER → DB01 TCP/5432), quy trình kết luận:

1. Kiểm tra máy test ở đúng USER VLAN, IP, VRF và route tới DB01.
2. Xác nhận DB01 hoặc môi trường lab đang tồn tại, có khả năng nhận kết nối từ nguồn phù hợp.
3. Quan sát packet thử ở ingress của ranh giới dự kiến.
4. Xác nhận firewall ghi DENY với **đúng 5-tuple/zone, rule ID và timestamp**.
5. Kiểm tra không có đường khác trong phạm vi kiểm thử đi qua direct route, overlay hoặc IPv6.
6. Ghi evidence ID, kết quả và khoảng trống còn lại.

Nếu client timeout và firewall không thấy luồng, ghi **INCONCLUSIVE** cho mục tiêu “firewall đã chặn”. Nếu DB listener đang tắt nhưng rule vẫn ALLOW, test bảo mật có thể **FAIL** vì network policy không chặn; việc ứng dụng không hoạt động không thay thế việc đánh giá ranh giới.

### 15.1. Phân loại đúng kết quả

| Trạng thái | Cách áp dụng |
|---|---|
| PASS | Hành vi đúng kỳ vọng, có bằng chứng ở control point phù hợp |
| FAIL | Hành vi khác kỳ vọng hoặc có bypass được xác minh |
| INCONCLUSIVE | Thiếu telemetry, chưa xác định packet path hoặc đích chưa sẵn sàng |
| NOT RUN | Chưa thực hiện, không nằm trong scope hoặc không được phép |

Kết quả chỉ đúng cho **đường, nguồn, thời điểm và cấu hình** đã kiểm tra. Không tuyên bố “toàn bộ mạng đã cô lập” từ một lần test giữa hai máy.

## 16. Phân tích log và vận hành giám sát lâu dài

### 16.1. Các nguồn dữ liệu cần phối hợp

| Nguồn | Dữ liệu hữu ích | Giới hạn |
|---|---|---|
| Firewall traffic/session | 5-tuple, action, rule ID, source/destination zone, NAT, session | Có thể thiếu payload, log sampling |
| Router/VRF/BGP | Thay đổi route, prefix, next hop, route leak | Route tồn tại không chứng minh flow đã đi |
| NetFlow/IPFIX | Bytes, packets, thời gian, đích, xu hướng | Không cho biết nội dung và ý định |
| DNS resolver | QNAME, client, answer, thời điểm | Không bao phủ resolver ngoài hoặc DNS mã hóa khi không có log thích hợp |
| Proxy/SWG/API gateway | Identity, request/response, đích và policy | HTTPS passthrough giới hạn thông tin L7 |
| IDS/IPS/NDR | Signature, cảnh báo hành vi, mức độ tin cậy | Alert không phải bằng chứng xâm nhập thành công |
| EDR/host firewall | Process, người dùng, kết nối và hành động tại host | Agent có thể thiếu hoặc mất kết nối |
| Cloud flow/security logs | VPC/VNet, attachment, security group/NSG, direction | Nhiều loại log chỉ chứa metadata, có thể trễ |
| NAC/VPN/WLAN | Device identity, IP pool, VLAN/SSID, thời gian phiên | Dynamic address cần mapping theo timestamp |

### 16.2. Những alert hữu ích

- Có route mới cho phép USER reach DATA qua một next hop không đi qua inspection.
- Firewall liên vùng ngừng ghi log nhưng traffic theo flow collector vẫn tiếp diễn.
- Cùng một endpoint bị DENY tại firewall, sau đó kết nối thành công tới đích bằng đường IPv6 hoặc proxy khác.
- Rule ALLOW với source any được thêm vào vùng DATA/MGMT.
- Cloud transit có attachment/route table mới dẫn traffic giữa hai security zone vốn tách biệt.
- DNS hoặc proxy cho thấy đích mới ngoài danh sách được phép sau thay đổi policy.
- Failover xảy ra nhưng security rule và session logging không tương đương giữa các node.
- Số luồng trực tiếp USER → DATA thay đổi bất thường so với baseline.

Cảnh báo phải được đối chiếu với change record và asset owner. Một route mới có thể hợp lệ nếu có phê duyệt; một rule DENY tăng có thể là tín hiệu kiểm soát tốt hoặc dấu hiệu dò quét, cần điều tra thêm.

### 16.3. Chỉ số đánh giá định kỳ

| KPI | Cách đo có ý nghĩa |
|---|---|
| Tỷ lệ luồng trong ma trận được kiểm thử | Số test PASS / tổng test bắt buộc, tách FAIL/INCONCLUSIVE |
| Số đường bypass đã xác minh | Phát hiện qua review path, flow và negative test |
| Policy drift | Rule/route không có owner, không khớp ADR hoặc exception quá hạn |
| Telemetry completeness | Phần trăm nguồn log bắt buộc có dữ liệu đúng thời gian |
| Thời gian phát hiện route/policy sai | Event time → alert/analyst acknowledgement |
| Độ trễ inspection p95 | Đo riêng cho ứng dụng quan trọng và trạng thái HA |
| Failover policy equivalence | Positive và negative test vẫn đạt khi chuyển tuyến |
| Số ngoại lệ quá hạn | Exception không có gia hạn hoặc lý do còn hiệu lực |

Không chỉ dùng số lần firewall chặn packet để đánh giá độ an toàn: nhiều DENY có thể phản ánh tấn công, cấu hình ứng dụng sai hoặc test, còn ít DENY có thể do không có lưu lượng hoặc mất log.

## 17. Quy trình triển khai một thay đổi phân đoạn mạng

### 17.1. Bảy bước triển khai

**Bước 1 — Khảo sát hiện trạng:** vẽ zone, tài sản, route/VRF, NAT, VPN, cloud attachments, DNS, application dependencies và điểm logging. Thu baseline flow thực tế theo khoảng thời gian hợp lý.

**Bước 2 — Xác nhận yêu cầu:** chủ hệ thống phê duyệt luồng tối thiểu; xác định các kết nối hai chiều, background jobs, health checks, backup, NTP, DNS, monitoring và identity services.

**Bước 3 — Lựa chọn kiến trúc:** so firewall tập trung, phân tán, VRF transit, cloud hub theo các tiêu chí bảo mật, hiệu năng, sẵn sàng và vận hành. Ghi lý do trong ADR.

**Bước 4 — Lập thiết kế chi tiết:** địa chỉ/zone, route table/next hop, firewall/NAT rules, return path, HA, log, threat detection, policy IaC nếu có và ownership.

**Bước 5 — Chuẩn bị thay đổi:** backup cấu hình, snapshot, đường quản trị/OOB, maintenance window, test source/destination, owner, tiêu chí dừng, kế hoạch rollback.

**Bước 6 — Thử ở lab/pilot:** thực hiện ma trận IZ-01–IZ-14 phù hợp; kiểm tra cả allow, deny, route leak, IPv6, failover và tác động tới ứng dụng. Điều chỉnh trước khi mở rộng.

**Bước 7 — Triển khai từng pha:** thay đổi theo phạm vi nhỏ, đo log/latency/health, chạy regression test, cập nhật asset/route/ADR và bàn giao vận hành.

### 17.2. Các cổng quyết định trước khi chuyển pha

| Gate | Điều kiện bắt buộc | Ai xác nhận |
|---|---|---|
| Thiết kế | Luồng, zone, route đi/về, enforcement point được thể hiện rõ | Network/Security architect |
| Chấp nhận rủi ro | Các đường bypass còn lại và exception có owner | Risk/Service owner |
| Sẵn sàng triển khai | Backup, console/OOB, rollback, đầu mối và cửa sổ thay đổi | NOC/Change manager |
| Xác minh pilot | Positive/negative test có chứng cứ; không phát sinh lỗi nghiệp vụ nghiêm trọng | Security tester + App owner |
| Hoàn tất | Log/monitoring hoạt động; policy drift đã xử lý | SOC/NOC/Service owner |

Trong production, không tự chặn cả VLAN hoặc thay đổi route diện rộng khi chỉ cần kiểm soát một API. Lộ trình triển khai theo từng vùng giảm khả năng mất truy cập dịch vụ trọng yếu.

## 18. Kế hoạch rollback và tình huống sự cố

### 18.1. Ví dụ lỗi do route leak

**Tình huống:** sau khi thêm route cho APP truy cập DATA qua firewall, một import route khác vô tình công bố cả DATA prefix vào VRF-USER. Test USER → DB01:5432 có TCP connect thành công nhưng firewall liên vùng không thấy log.

**Chẩn đoán có căn cứ:**

1. Xác nhận nguồn test thật sự nằm trong USER, đích thực sự là DB01.
2. Kiểm tra route/FIB và next hop của USER, gateway, VRF transit và DATA.
3. Tìm sự khác nhau giữa đường thiết kế và đường thực tế; kiểm tra route import/export.
4. Xem capture/flow ở L3 thiết bị liên quan, xác nhận bypass.
5. Ghi evidence: thời gian, route thay đổi, policy, kết quả test và tác động.

**Khắc phục:** theo change control, rút route leak hoặc điều chỉnh route policy để USER chỉ đi tới DATA qua điểm enforcement bắt buộc. Thử lại cả USER → DB01 DENY và APP → DB01 ALLOW; kiểm tra những luồng nghiệp vụ không liên quan.

### 18.2. Ví dụ lỗi do asymmetric routing

**Tình huống:** APP → DATA được firewall cho phép nhưng TCP handshake timeout khi đường dự phòng BGP hoạt động. Firewall thấy SYN ở ingress và egress, nhưng không thấy SYN-ACK.

**Chẩn đoán:** kiểm tra route về trên DB01 gateway, ECMP, firewall HA state, NAT và thiết bị dự phòng; xác minh response thực sự đi qua đâu. Không sửa thành ALLOW any-any khi dấu hiệu chỉ ra sai đường về.

### 18.3. Điều kiện rollback

- Đường cho phép quan trọng bị mất hoặc ứng dụng không đạt health check theo ngưỡng đã phê duyệt.
- Có bypass tới DATA/MGMT hoặc negative test trọng yếu FAIL.
- Firewall/route thay đổi gây asymmetric traffic không được hỗ trợ.
- Khả năng quan sát biến mất và không có nguồn thay thế đáng tin cậy.
- Đường quản trị, DNS, AAA hoặc VPN phụ thuộc bị ảnh hưởng ngoài phạm vi chấp nhận.
- Có sai lệch giữa cấu hình production và phương án đã được review.

Sau rollback, **lặp lại positive và negative smoke tests** và xác nhận monitoring/route table đã về trạng thái dự kiến. Không chỉ tin thông báo “config restored”.

## 19. Mẫu Architecture Decision Record (ADR)

Một ADR đủ tốt ghi quyết định có thể được người vận hành và kiểm thử lại, không chỉ nói “dùng firewall để tăng bảo mật”.

### 19.1. Mẫu điền

~~~markdown
# ADR: Bảo vệ traffic liên vùng <mã dự án>

Trạng thái: Proposed / Accepted / Superseded
Ngày quyết định: <YYYY-MM-DD>
Chủ sở hữu: <Architecture owner>
Người phê duyệt: <Security / Network / Service owner>

## Bối cảnh
- Vùng/tài sản, loại dữ liệu, luồng nghiệp vụ và rủi ro.
- Topology, ràng buộc hiệu năng/HA/chi phí.
- Điểm mù telemetry và đường bypass hiện có.

## Quyết định
- Mẫu kiến trúc: central firewall / distributed / VRF transit / cloud hub.
- Nguồn, đích, danh tính, dịch vụ được phép.
- Enforcement point cho từng luồng và đường dự phòng.
- Route đi/về, NAT, IPv4/IPv6, DNS, TLS, AAA.
- Log, cảnh báo, quyền quản trị và rollback.

## Lựa chọn đã xem xét
- Phương án A: ưu/nhược, chi phí và lý do không chọn.
- Phương án B: ưu/nhược, chi phí và lý do không chọn.

## Hệ quả
- Bảo mật, độ trễ, điểm phụ thuộc, năng lực vận hành.
- Rủi ro tồn đọng và người chịu trách nhiệm.

## Xác minh
- Ma trận test allow/deny, failover, IPv6 và route leak.
- Chứng cứ bắt buộc: rule ID, route/FIB, flow/PCAP, app logs.
- Điều kiện PASS/FAIL/INCONCLUSIVE và lịch kiểm tra lại.

## Phương án thay đổi
- Change ID, kế hoạch triển khai, người liên hệ, điều kiện dừng.
- Backup, rollback và post-change monitoring.
~~~

### 19.2. ADR ví dụ cho mô hình lab

**Quyết định minh họa:** chọn VRF phân vùng cho USER/APP/DATA và một cụm firewall transit để kiểm tra inter-zone traffic; bổ sung host firewall cho workload DATA cần hạn chế kết nối trong cùng subnet.

**Lý do:** giữ route rõ ràng theo vùng, có log/policy tập trung cho kết nối giữa các vùng, trong khi host enforcement xử lý lateral movement mà firewall trung tâm không nhìn thấy.

**Trade-off:** phức tạp hơn ở quản lý VRF/import route, có thêm latency tại firewall, cần năng lực vận hành HA và rulebase. Rủi ro route leak, failover và IPv6 được đưa thành ca test bắt buộc.

**Tiêu chí chấp thuận:** USER → App01:443 hoạt động, USER → DB01:5432 bị DENY tại điểm dự kiến, APP → DB01:5432 được phép đúng nguồn; GUEST/PARTNER không vào DATA/MGMT; sau failover, các negative test vẫn đạt và logging vẫn nhận dữ liệu. Số liệu benchmark phải được đo trong môi trường triển khai, không tự áp giá trị của lab vào production.

## 20. Bài thực hành tổng hợp

### 20.1. Đề bài: ranh giới USER–APP–DATA–CLOUD

Một tổ chức có năm vùng: USER 10.40.10.0/24, APP 10.40.30.0/24, DATA 10.40.40.0/24, MGMT 10.40.50.0/24 và CLOUD-APP 10.60.30.0/24. Mạng đang dùng core L3 switch với inter-VLAN routing; đã có firewall edge Internet, nhưng chưa buộc traffic liên VLAN đi qua firewall segmentation.

**Yêu cầu:**

1. USER chỉ được đến App01 TCP/443, không được trực tiếp đến DB01.
2. APP được đến DB01 TCP/5432, giới hạn đúng workload.
3. CLOUD-APP đến App01 qua hybrid transit có kiểm soát; không được vào MGMT.
4. Người quản trị vào MGMT bằng bastion/VPN và AAA, không truy cập trực tiếp từ USER.
5. Có chính sách IPv6 tương ứng nếu hệ thống dùng dual-stack.
6. Khi một link/firewall hỏng, không xuất hiện đường USER → DATA ngoài policy.

**Sản phẩm cần nộp:** sơ đồ topology hiện trạng và mục tiêu, threat model, ma trận luồng, phương án enforcement, ADR, bảng route, kế hoạch test, log/capture minh họa và rollback.

### 20.2. Tình huống A — Route leak trong failover

Sau failover, USER không kết nối được App01 nhưng lại reach được DB01. Đội phải xác định route/VRF/policy nào thay đổi; kiểm tra đường đi, đường về và log. Một đáp án tốt đưa ra giải pháp hẹp, bảo toàn bằng chứng và chạy lại cả positive lẫn negative test.

### 20.3. Tình huống B — IPv6 bỏ qua policy

IPv4 USER → MGMT bị DENY đúng rule nhưng IPv6 SSH vẫn truy cập được. Đội cần xác định ranh giới thực thi IPv6, interface lắng nghe, policy local-in, route và cơ chế kiểm thử; không kết luận toàn bộ management network đã được tách nếu còn lỗ hổng này.

### 20.4. Tình huống C — Cloud transit route trực tiếp

CLOUD-APP truy cập App01 thành công nhưng cloud inspection firewall không có log, còn on-prem firewall thấy nguồn NAT gateway. Đội phải kiểm tra route table của spoke/transit, NAT mapping, attachment và cloud flow log để biết có bypass inspection không. Traffic thành công chưa chứng minh nó đã qua đúng policy.

### 20.5. Tình huống D — Negative test timeout

Tester từ USER kết nối DB01:5432 và bị timeout, báo PASS. Firewall không thấy packet, DB01 không có listener đang chạy. Hãy chỉ ra vì sao đây là **INCONCLUSIVE**, dữ liệu còn thiếu và phép thử cần chạy lại.

### 20.6. Rubric 100 điểm

| Năng lực | Điểm tối đa | Bằng chứng |
|---|---:|---|
| Mô hình zone/tài sản/luồng | 15 | Tài sản, owner, phân loại và ma trận |
| Threat model và đường bypass | 15 | Route leak, L2/overlay, NAT, IPv6, failover |
| Lựa chọn kiến trúc có trade-off | 20 | ADR so phương án và lựa chọn rõ |
| Routing/policy/identity | 20 | Route đi/về, enforcement point, ACL/AAA/mTLS |
| Test allow/deny và tính sẵn sàng | 15 | Log/capture, rule ID, test failover |
| Giám sát và ứng phó | 10 | Telemetry, alert, triage, owner cải tiến |
| Rollback và tài liệu bàn giao | 5 | Change plan, recovery, residual risks |
| **Tổng** | **100** | Chấm bằng chứng có thể kiểm tra, không chỉ bản vẽ |

## 21. Lỗi thường gặp khi quyết định kiến trúc

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Cho rằng tách VLAN đã bảo mật | Core L3 vẫn route giữa các VLAN | Bắt buộc đi qua policy, negative test |
| Có firewall nhưng route bypass | Firewall không thấy một số traffic | Kiểm tra FIB/VRF và mọi đường phụ |
| Chặn chỉ một chiều | State/session hoặc ứng dụng bị lỗi | Phân tích return path, callback và loại ACL |
| Dùng subnet allow-all | Lan ngang tới nhiều tài sản | Thu hẹp theo app/service identity |
| Bỏ qua local-in quản trị | Giao diện firewall/router vẫn lộ | Local-in ACL, bastion, AAA |
| Không tính tới NAT/proxy | Không truy được endpoint nguồn | NAT/session/proxy mapping có timestamp |
| Chỉ thử IPv4 | IPv6 còn reachability | Kiểm thử IPv6 và security policy riêng |
| Coi traceroute là đủ | ICMP có thể theo tuyến khác | Policy log, FIB và capture thực |
| Không xem cùng-subnet traffic | Intra-zone lateral movement không qua firewall L3 | Microsegmentation, host policy |
| Chọn central firewall không kiểm tra năng lực | Latency và bottleneck | Đo throughput khi bật inspection, HA |
| Failover bỏ kiểm thử DENY | Tuyến dự phòng mở đường không phép | Test allow và deny sau chuyển tuyến |
| Không kiểm tra DNS/mTLS | Đúng IP nhưng sai dịch vụ hoặc identity | Kiểm tra resolver và xác thực L7 |
| Bỏ qua log health | Không alert nhưng traffic vẫn tiếp diễn | Monitor ingest và sensor availability |
| Không có ADR và owner | Policy drift, ngoại lệ tồn lâu | Ghi quyết định, review và test hồi quy |

## 22. Checklist nghiệm thu kiến trúc

- [ ] Phân loại zone và tài sản; xác định chủ sở hữu và yêu cầu nghiệp vụ.
- [ ] Ma trận luồng mô tả nguồn, đích, giao thức, cổng, danh tính, chiều và kỳ vọng.
- [ ] Có threat model cho lateral movement, route leak, NAT, overlay, IPv6, đường dự phòng.
- [ ] Mọi luồng liên vùng cần bảo vệ có enforcement point **trên đường đi thực tế**.
- [ ] Đường đi và đường về được mô tả theo route/VRF, PBR, NAT, VPN và cloud transit.
- [ ] Không có rule/subnet route rộng làm bypass hoặc shadow security policy.
- [ ] Đã bảo vệ management plane, DNS egress, VPN/partner, Wi-Fi/IoT và các điểm cloud.
- [ ] Với traffic cùng subnet/workload, đã đánh giá yêu cầu host/CNI microsegmentation.
- [ ] Positive test kiểm chứng ứng dụng hợp lệ, không chỉ TCP connect.
- [ ] Negative test chứng minh policy thực sự chặn tại ranh giới dự kiến.
- [ ] Đã kiểm tra IPv4/IPv6, NAT, policy L7 và trạng thái phiên mới/cũ khi có liên quan.
- [ ] Có capture/log đầy đủ timestamp UTC, rule ID, session, route và evidence ID.
- [ ] Kiểm thử failover giữ được chính sách, logging, độ sẵn sàng và performance mục tiêu.
- [ ] Có kế hoạch triển khai, backup, rollback, người phê duyệt và mốc dừng.
- [ ] ADR nêu phương án, đánh đổi, rủi ro tồn đọng, owner và lịch kiểm tra lại.
- [ ] Các ca FAIL, INCONCLUSIVE hoặc NOT RUN được ghi minh bạch kèm bước xử lý.

**Kết luận:** bảo vệ đường đi của traffic liên vùng là quyết định về **topology, định tuyến, identity, chính sách và vận hành**, được kiểm chứng trên cả lưu lượng được phép lẫn lưu lượng phải chặn. Một rule firewall chỉ có giá trị khi traffic thuộc phạm vi thật sự đi qua nó; một đường mạng chỉ đáng tin khi các tuyến dự phòng, dữ liệu quan sát và cách khôi phục cũng được thiết kế, thử nghiệm và ghi nhận rõ ràng.

