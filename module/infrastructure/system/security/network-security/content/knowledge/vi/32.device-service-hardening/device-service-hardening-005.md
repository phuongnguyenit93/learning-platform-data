# Tách management plane khỏi user traffic

## 1. Mục tiêu của việc tách mạng quản trị

Trong chương **Hardening thiết bị và dịch vụ mạng** thuộc module **SECURITY_NETWORK_SECURITY**, một yêu cầu nền tảng là tách lưu lượng quản trị thiết bị khỏi lưu lượng phục vụ người dùng. Đây là biện pháp giảm bề mặt tấn công đối với switch, router, firewall, wireless controller, thiết bị VPN, load balancer và các dịch vụ hạ tầng. Kiến thức này gắn với phân đoạn mạng, chính sách firewall, xác thực kết nối, IDS/IPS, giám sát xâm nhập, bảo vệ DNS, mạng không dây và kiến trúc mạng an toàn trong môi trường on-premises cũng như cloud.

**Management plane** là tập hợp giao diện, giao thức và dịch vụ dùng để cấu hình, giám sát, kiểm tra trạng thái, sao lưu và bảo trì hệ thống. Ví dụ: SSH, HTTPS quản trị, SNMPv3, NETCONF, RESTCONF, gNMI, API của controller, console, truy cập BMC/iLO/iDRAC và những kết nối tới hệ thống AAA, log, NTP hoặc backup.

**User traffic** là lưu lượng nghiệp vụ hoặc truy cập của người dùng đi qua thiết bị để đến ứng dụng, Internet, máy chủ và dịch vụ. Mục tiêu của việc tách là giới hạn ai, ở đâu và bằng giao thức nào được tiếp cận bề mặt quản trị, kể cả khi một máy người dùng hoặc phân đoạn mạng đã bị xâm nhập.

Sau bài học, người học có thể:

1. Phân biệt management plane, control plane và data/forwarding plane.
2. So sánh quản trị **out-of-band (OOB)**, quản trị **in-band được phân đoạn** bằng VLAN/VRF, và quản trị chung với user traffic.
3. Thiết kế các vùng tin cậy, địa chỉ, tuyến đường và chính sách least privilege cho luồng quản trị.
4. Sử dụng bastion/jump host, VPN quản trị, MFA, AAA, PKI, role-based access control và nhật ký kiểm toán.
5. Áp dụng hardening cho giao diện quản trị của switch, router, firewall, hệ thống Wi-Fi và workload cloud.
6. Xây dựng quy trình chuyển đổi, kiểm thử được cả **luồng cho phép** và **luồng phải bị từ chối**, có kế hoạch phục hồi quyền truy cập khi gặp lỗi.
7. Đọc log và bằng chứng mạng để phát hiện truy cập trái phép vào management plane.

**Điều cần nhớ:** tách bằng VLAN, VRF hoặc dây mạng riêng chỉ giải quyết một phần ranh giới. Biện pháp hoàn chỉnh cần cả định tuyến có kiểm soát, firewall/ACL, xác thực danh tính, giám sát, cấu hình an toàn và quy trình thay đổi.

## 2. Ba plane trong thiết bị mạng

Một router hoặc switch thường được mô tả qua ba plane có vai trò khác nhau:

| Plane | Nhiệm vụ | Ví dụ | Rủi ro nếu không kiểm soát |
|---|---|---|---|
| **Data plane / forwarding plane** | Chuyển tiếp lưu lượng theo bảng chuyển tiếp và chính sách | Forward packet, chuyển frame, thực hiện NAT/ACL, truyền lưu lượng ứng dụng | Luồng của người dùng có thể chạm đến dịch vụ quản trị ngoài ý muốn |
| **Control plane** | Hình thành và duy trì thông tin điều khiển của hệ thống mạng | Routing protocol như OSPF/BGP, ARP/ND, STP và một số heartbeat | Gói tin bất thường có thể ảnh hưởng CPU, routing adjacency hoặc tính ổn định mạng |
| **Management plane** | Vận hành, cấu hình, giám sát và quản trị trạng thái | SSH/HTTPS/API, SNMP, telemetry, cấu hình thiết bị, AAA | Chiếm quyền quản trị, sửa ACL/routing, đọc cấu hình hoặc vô hiệu hóa giám sát |

Các plane là **khái niệm chức năng**, không nhất thiết là ba CPU hoặc ba phần cứng khác nhau. Một thiết bị có thể chuyển packet bằng ASIC nhưng xử lý SSH, BGP và log trên cùng bộ xử lý điều khiển. Bởi vậy, tách tuyến truy cập quản trị không loại bỏ nhu cầu **control-plane policing (CoPP/CPPr)**, giới hạn kết nối và bảo vệ CPU.

~~~mermaid
flowchart TB
    U["Người dùng / ứng dụng"] --> D["Data plane<br/>chuyển tiếp lưu lượng"]
    P["Thiết bị định tuyến lân cận"] --> C["Control plane<br/>routing, adjacency"]
    A["Quản trị viên / Automation"] --> M["Management plane<br/>SSH, HTTPS, API, SNMP"]
    M -. "cấu hình và trạng thái" .-> D
    C -. "thông tin định tuyến" .-> D
~~~

Ví dụ: một người dùng truy cập website qua firewall là **user traffic**. Một quản trị viên dùng SSH để thay đổi rule firewall là **management traffic**. Hai luồng đi qua cùng một đường WAN không có nghĩa phải có cùng quyền truy cập hoặc cùng đường định tuyến đến địa chỉ quản trị firewall.

## 3. Vì sao phải tách management plane?

### 3.1. Những đường tấn công thường xuất hiện

- Máy trạm người dùng bị nhiễm mã độc, từ VLAN người dùng kết nối được đến trang quản trị switch, router hoặc firewall.
- Dịch vụ Telnet, HTTP không mã hóa, SNMPv1/v2c hoặc API quản trị quá rộng bị lộ trên một interface có nhiều client.
- Thiết bị quản trị sử dụng chung mật khẩu hoặc tài khoản quyền cao, khiến việc đánh cắp thông tin đăng nhập mở đường cho thay đổi cấu hình.
- Truy cập quản trị qua Internet hoặc VPN dùng chung với người dùng thông thường, không có danh sách nguồn cho phép.
- Mạng Wi-Fi khách hoặc IoT định tuyến được vào subnet chứa thiết bị quản trị.
- Một ACL chỉ lọc IPv4, bỏ quên IPv6; hoặc chỉ bảo vệ interface quản trị thứ nhất, còn SVI/loopback khác vẫn tiếp nhận dịch vụ.
- Đường định tuyến giữa các VRF bị **route leak** ngoài thiết kế, NAT/firewall policy quá rộng hoặc dynamic routing quảng bá nhầm mạng quản trị.
- Trong cloud, security group hoặc public IP làm endpoint API quản trị của thiết bị ảo có thể truy cập từ bên ngoài.

Mối đe dọa không dừng ở việc đăng nhập được. Chỉ cần truy cập tới bề mặt quản trị, kẻ tấn công đã có thể thử thông tin xác thực, dò phiên bản dịch vụ, tạo nhiều kết nối làm cạn tài nguyên hoặc tìm lỗi cấu hình. Nếu quản trị viên dùng máy trạm hằng ngày để truy cập trực tiếp thiết bị trọng yếu, trình duyệt, email và phần mềm trên máy đó còn mở thêm đường dẫn tới thông tin đặc quyền.

### 3.2. Các mục tiêu có thể kiểm chứng

Một thiết kế phân tách tốt cần trả lời được:

1. **Ai được quản trị?** Danh tính cá nhân, vai trò, phê duyệt, thiết bị nguồn và phương thức MFA.
2. **Quản trị từ đâu?** VPN quản trị hoặc jump host được bảo vệ; không phải toàn bộ office LAN.
3. **Tới thiết bị nào?** Tập địa chỉ management/IP thiết bị và mức quyền tương ứng.
4. **Bằng dịch vụ nào?** Chỉ SSH, HTTPS/API, SNMPv3 hoặc công cụ quản trị thực sự cần.
5. **Đường đi nào?** OOB, management VLAN, VRF, firewall và đường trả lời đã được xác định.
6. **Kiểm toán thế nào?** AAA command accounting, log, SIEM, session recording nếu phù hợp.
7. **Khôi phục quyền truy cập ra sao?** Console/OOB, tài khoản khẩn cấp có bảo vệ và rollback có phê duyệt.

Chỉ số hiệu quả không phải “đã tạo VLAN 90” mà là **người dùng không có quyền không thể chạm tới service quản trị**, trong khi quản trị viên hợp lệ vẫn vào được qua đường được kiểm soát và có nhật ký.

## 4. Các kiến trúc phân tách và mức bảo đảm

### 4.1. Quản trị out-of-band (OOB)

**OOB management** sử dụng đường kết nối quản trị tách khỏi đường truyền lưu lượng sản xuất, thường qua cổng management riêng của thiết bị, OOB switch, console server và một đường kết nối từ xa riêng nếu cần.

~~~mermaid
flowchart LR
    ADMIN["Admin VPN + MFA"] --> BASTION["Bastion / PAM"]
    BASTION --> OOBFW["Firewall quản trị"]
    OOBFW --> OOBSW["OOB switch riêng"]
    OOBSW --> MG1["mgmt0: Router"]
    OOBSW --> MG2["mgmt0: Firewall"]
    OOBSW --> MG3["Console server"]
    USERS["User VLAN"] --> PROD["Production switch / router"]
    PROD --> APPS["Ứng dụng / Internet"]
~~~

**Ưu điểm:** có thể quản lý thiết bị ngay cả khi forwarding/routing sản xuất gặp sự cố; giảm phụ thuộc vào user VLAN và production route. **Giới hạn:** OOB vẫn là một mạng cần firewall, AAA, logging và cập nhật bảo mật. Nếu OOB và production dùng chung đường uplink, nguồn điện, firewall hoặc đường WAN, cần ghi rõ phụ thuộc còn lại. “Có cổng mgmt0” không mặc nhiên chứng minh OOB đã độc lập.

**Phù hợp:** thiết bị lõi, edge firewall, core router, switch quan trọng, hạ tầng hypervisor và các nơi có yêu cầu phục hồi khi mạng sản xuất gặp lỗi.

### 4.2. In-band management qua VLAN riêng

**Management VLAN** dùng một VLAN quản trị tách broadcast domain khỏi các VLAN người dùng trên cùng hạ tầng switch. Có thể đặt địa chỉ quản trị trên SVI hoặc interface logic nếu thiết bị hỗ trợ.

**Ưu điểm:** triển khai thuận tiện và ít thêm thiết bị. **Giới hạn:** nếu cùng router/L3 switch vẫn định tuyến tự do giữa hai subnet thì người dùng vẫn chạm được management IP. Việc tách VLAN **không phải chính sách kiểm soát L3**. Cần ACL/firewall và khóa trunk/port đúng thiết kế.

**Phù hợp:** mạng nhỏ, lab, access layer hoặc hệ thống chưa có cổng management chuyên dụng. Tránh xem VLAN là ranh giới bảo mật duy nhất.

### 4.3. Management VRF / routing instance riêng

**VRF (Virtual Routing and Forwarding)** tạo bảng định tuyến tách biệt trên thiết bị. Management interface thuộc VRF quản trị sẽ dùng route của VRF này khi xử lý traffic tương ứng, nếu hệ điều hành thiết bị thực sự hỗ trợ service binding theo VRF.

**Ưu điểm:** giảm nguy cơ route người dùng trực tiếp dẫn vào subnet quản trị; cho phép quản lý mạng in-band phức tạp hơn. **Giới hạn:** VRF dùng chung thiết bị vật lý và thường chung control/management CPU. Sai sót ở route leaking, firewall policy, tunnel, NAT hoặc service bind vẫn có thể mở đường từ user network.

Khi triển khai VRF phải kiểm tra cả:

- Interface quản trị thực sự nằm trong VRF nào.
- Default route của management VRF dẫn đi đâu.
- Dịch vụ SSH/HTTPS/SNMP/API lắng nghe ở interface nào và có hỗ trợ chọn VRF hay không.
- DNS, NTP, syslog, AAA, backup và automation dùng **source interface/VRF** nào.
- Có route leaking nào giữa \`MGMT\` và \`PROD\`, và rule nào cho phép đường đi qua firewall.
- Đường trả lời từ dịch vụ chung hoặc jump host có tuyến ngược hợp lệ hay không.

### 4.4. So sánh ba lựa chọn

| Tiêu chí | OOB độc lập | VLAN quản trị | Management VRF |
|---|---|---|---|
| Cách tách chính | Cáp/cổng/hạ tầng quản trị riêng | Broadcast domain riêng | Bảng định tuyến/đường đi L3 riêng |
| Khả năng thao tác khi production routing lỗi | Thường tốt nếu phụ thuộc thật sự độc lập | Thường thấp nếu dùng production path | Phụ thuộc hạ tầng vật lý và routing |
| Nguy cơ cấu hình sai | OOB uplink, ACL, AAA, hạ tầng chung | Trunk, ACL inter-VLAN, SVI | Route leak, service binding, NAT, return path |
| Chi phí vận hành | Cao hơn do thêm thiết bị/đường kết nối | Thấp hơn | Trung bình, cần năng lực vận hành L3 |
| Nên bổ sung | Bastion, MFA, ACL, logs, console | Firewall/ACL L3, bastion, log | Firewall tại ranh giới VRF, bastion, log |

Có thể **kết hợp**: dùng OOB cho hạ tầng trọng yếu; dùng VRF và VLAN quản trị cho thiết bị access. Chọn thiết kế theo mức độ quan trọng, khả năng cô lập khi lỗi và các ràng buộc sẵn có.

## 5. Mô hình lab: user VLAN, bastion và management VRF

Mọi địa chỉ sau đây là **địa chỉ riêng trong lab**, không phải cấu hình của một tổ chức thực.

| Vùng | Subnet/địa chỉ | Vai trò |
|---|---|---|
| USER | \`10.20.10.0/24\` | Máy trạm và lưu lượng nghiệp vụ |
| ADMIN-VPN | \`10.20.50.0/24\` | Phiên VPN quản trị đã xác thực |
| ADMIN-SERVICES | \`10.20.91.0/24\` | Bastion \`10.20.91.10\` |
| MANAGEMENT | \`10.20.90.0/24\` | Management VRF \`MGMT\` |
| MGMT-SERVICES | \`10.20.92.0/24\` | AAA, log, NTP, DNS, monitoring |
| MANAGEMENT gateway | \`10.20.90.1\` | Firewall/gateway của vùng quản trị |
| Switch management | \`10.20.90.11\` | SSH/HTTPS quản trị switch |
| Router management | \`10.20.90.21\` | SSH/telemetry quản trị router |
| Wi-Fi controller management | \`10.20.90.31\` | HTTPS/API controller |

~~~mermaid
flowchart LR
    U["USER VLAN<br/>10.20.10.0/24"] --> F["Firewall / L3 policy"]
    V["ADMIN VPN<br/>10.20.50.0/24<br/>MFA"] --> B["Bastion<br/>10.20.91.10"]
    B --> F
    S["Management services<br/>10.20.92.0/24"] --> F
    F --> G["MGMT VRF / VLAN<br/>10.20.90.0/24"]
    G --> SW["Switch mgmt<br/>.11"]
    G --> RT["Router mgmt<br/>.21"]
    G --> WC["WLAN controller<br/>.31"]
    U --> APP["Ứng dụng người dùng"]
~~~

Các kết nối trong sơ đồ thể hiện **khả năng kết nối vật lý/logic**, không đồng nghĩa tất cả luồng được phép. Firewall phải áp dụng chính sách cụ thể trước khi lưu lượng qua ranh giới. Bastion là điểm truy cập được cấp quyền từ VPN quản trị, không phải một proxy mặc định mở cho toàn mạng.

Thiết kế này mô phỏng **in-band management có phân vùng**, vì các subnet có thể vẫn dùng chung switch và đường uplink. Nếu yêu cầu tiếp cận thiết bị lúc production bị lỗi, cần thêm OOB switch, console server và đường remote access độc lập.

### 5.1. Bảng vùng tin cậy

| Vùng | Độ tin cậy và quyền | Điều không được mặc định |
|---|---|---|
| USER | Chỉ truy cập dịch vụ nghiệp vụ đã phê duyệt | Không được vào management SSH, HTTPS, SNMP, API |
| Guest Wi-Fi / IoT | Giới hạn Internet hoặc ứng dụng chuyên biệt | Không được định tuyến vào management network |
| ADMIN-VPN | Chỉ phiên có danh tính, MFA và chính sách thiết bị phù hợp | Không có quyền trực tiếp tới mọi địa chỉ quản trị |
| Bastion | Điểm truy cập quản trị có ghi log và phân quyền | Không tự động cho phép mọi port/mọi thiết bị |
| MANAGEMENT | Địa chỉ và dịch vụ quản trị của network device | Không là transit network cho user traffic |
| MGMT-SERVICES | AAA, DNS, NTP, syslog, monitoring, backup | Không tự động có quyền đăng nhập đặc quyền vào thiết bị |

Trong mạng lớn, nên chia **management zone theo mức độ quan trọng**: firewall/core, switch access, Wi-Fi, virtualization, BMC, cloud control. Việc gom toàn bộ management interface vào một subnet duy nhất có thể khiến rủi ro lan ngang quá rộng.

## 6. Ma trận truy cập tối thiểu

**Default deny** giữa USER và MANAGEMENT; chỉ tạo quy tắc rõ nguồn, đích, giao thức, chiều và mục đích. Bảng dưới đây là **ví dụ học tập**; cổng thực tế phụ thuộc sản phẩm và cấu hình dịch vụ.

| Nguồn | Đích | Giao thức/cổng | Quyết định | Lý do |
|---|---|---|---|---|
| USER \`10.20.10.0/24\` | MGMT \`10.20.90.0/24\` | Mọi dịch vụ | **DENY** | Người dùng không quản trị thiết bị |
| Guest/IoT | MGMT | Mọi dịch vụ | **DENY** | Không có quan hệ tin cậy |
| ADMIN-VPN người được duyệt | Bastion \`10.20.91.10\` | HTTPS/TCP 443 hoặc giao thức quản trị bastion được phê duyệt | **ALLOW có MFA** | Truy cập có danh tính |
| Bastion \`10.20.91.10/32\` | Các IP MGMT cụ thể | SSH/TCP 22 | **ALLOW có điều kiện** | CLI quản trị qua điểm kiểm soát |
| Bastion \`10.20.91.10/32\` | Thiết bị cần Web UI | HTTPS/TCP 443 | **ALLOW có điều kiện** | Chỉ thiết bị có Web UI cần thiết |
| Monitoring \`10.20.92.10/32\` | Thiết bị MGMT | SNMPv3/UDP 161 | **ALLOW giới hạn** | Giám sát, phân quyền đọc phù hợp |
| Thiết bị MGMT | AAA \`10.20.92.11/32\` | TACACS+/TCP 49 nếu sử dụng | **ALLOW** | Xác thực/ủy quyền/ghi nhận lệnh |
| Thiết bị MGMT | Syslog \`10.20.92.12/32\` | Syslog over TLS/TCP 6514 nếu hỗ trợ | **ALLOW** | Lưu log có bảo vệ truyền tải |
| Thiết bị MGMT | NTP \`10.20.92.13/32\` | NTP/UDP 123 | **ALLOW** | Đồng bộ thời gian cho audit |
| Thiết bị MGMT | DNS \`10.20.92.15/32\` | DNS/UDP,TCP 53 nếu cần | **ALLOW** | Phân giải đích nội bộ/được duyệt |
| Backup \`10.20.92.14/32\` | IP MGMT được quản lý | SSH hoặc API chuyên dụng | **ALLOW theo tài khoản dịch vụ** | Sao lưu cấu hình có kiểm toán |
| MGMT | Internet trực tiếp | Mọi dịch vụ | **DENY mặc định** | Cập nhật cần qua proxy/repository phê duyệt |

**Chiều kết nối quan trọng:** SNMP polling thường đi từ monitoring đến thiết bị, trong khi syslog thường được thiết bị đẩy tới collector. SNMP traps có thể cần chiều khác (UDP 162); gNMI/streaming telemetry có thể cần phiên thiết bị hoặc collector chủ động tùy hệ thống. Chỉ mở giao thức thực sự triển khai.

Các phiên phản hồi thuộc kết nối hợp lệ có thể được firewall stateful cho phép qua \`ESTABLISHED,RELATED\`; firewall stateless cần rule chiều về chính xác. Việc chặn traffic người dùng đến MGMT không thay thế quyền admin RBAC sau khi truy cập thành công.

## 7. Bảo vệ đường truy cập quản trị

### 7.1. VPN quản trị và jump host

Một luồng đăng nhập lý tưởng có thể là:

~~~mermaid
sequenceDiagram
    participant A as Admin
    participant I as VPN / IdP
    participant B as Bastion / PAM
    participant F as Firewall MGMT
    participant D as Network Device
    participant L as AAA / Audit
    A->>I: Xác thực + MFA
    I-->>A: Phiên VPN quản trị theo chính sách
    A->>B: Truy cập bastion bằng danh tính cá nhân
    B->>L: Kiểm tra vai trò và ghi audit
    B->>F: SSH/HTTPS tới thiết bị được phép
    F->>D: Chỉ chuyển qua rule allow cụ thể
    D->>L: Xác thực, ủy quyền, accounting
    D-->>A: Kết quả phiên qua bastion
~~~

Các kiểm soát cần có:

- Quản trị viên sử dụng **tài khoản cá nhân**, MFA tại VPN/bastion, quy trình cấp và thu hồi quyền.
- Bastion được harden, cập nhật, giám sát; chỉ những thiết bị và giao thức cần thiết được phép đi tiếp.
- Quyền thao tác được cấp theo vai trò và thời hạn; ưu tiên tài khoản ít đặc quyền cho giám sát, backup, automation.
- Nếu dùng privileged access management (PAM), cân nhắc cấp quyền just-in-time, quản lý khóa và ghi nhận phiên theo quy định dữ liệu.
- Mã hóa phiên SSH/TLS; kiểm chứng host key và chứng chỉ CA. Tránh bỏ kiểm tra host key hoặc TLS trong thao tác thường ngày.
- Có quy trình khẩn cấp khi VPN, IdP hoặc bastion lỗi: console/OOB và tài khoản **break-glass** được lưu giữ, giám sát và kiểm soát độc lập.

MFA ở bastion là bước tăng bảo vệ nhưng **không tự cấp quyền mọi thiết bị**. Thiết bị đích vẫn phải xác thực và ủy quyền lệnh qua AAA hoặc cơ chế tương đương.

### 7.2. AAA, RBAC và logging

- **Authentication:** xác thực danh tính qua TACACS+, RADIUS, SSH key, certificate hoặc phương thức thiết bị hỗ trợ.
- **Authorization:** quy định người dùng được đọc cấu hình, chỉnh interface, thay firewall policy hay chỉ xem telemetry.
- **Accounting:** ghi thời điểm, kết quả đăng nhập, lệnh/thay đổi đã thực hiện, danh tính và địa chỉ nguồn.

TACACS+ thường được dùng cho quản trị thiết bị khi cần tách quyền lệnh và accounting; RADIUS phổ biến trong network access và cũng có thể hỗ trợ quản trị tùy khả năng của nhà cung cấp. Chọn giải pháp có **mã hóa kết nối phù hợp, cấu hình bí mật mạnh, phân quyền và log**, tránh suy đoán mọi vendor thực thi cùng một bộ chức năng.

Khi AAA không truy cập được, thiết bị có thể cần tài khoản local khẩn cấp. Tài khoản đó phải có thông tin xác thực mạnh, quyền và điều kiện sử dụng được quy định, lưu trong vault, kiểm tra định kỳ và ghi nhận sau sự kiện. Không dùng một tài khoản admin chia sẻ vĩnh viễn cho mọi kỹ thuật viên.

## 8. Hardening dịch vụ và giao diện quản trị

### 8.1. Những dịch vụ nên ưu tiên kiểm soát

| Dịch vụ | Cấu hình khuyến nghị | Điều cần xác minh |
|---|---|---|
| SSH | Bật phiên bản an toàn, key/cipher hiện đại do sản phẩm hỗ trợ, timeout và giới hạn thử đăng nhập | Chỉ nghe trên management interface/VRF, ACL chỉ cho bastion |
| HTTPS / Web UI | Tắt HTTP plaintext, dùng TLS/certificate hợp lệ, RBAC và timeout | Không còn Web UI mở ở user-facing IP |
| SNMP | Ưu tiên SNMPv3 với authentication + privacy, hạn chế view và nguồn polling | Không còn community mặc định/v1/v2c khi không có ngoại lệ |
| NETCONF / RESTCONF / gNMI | Chỉ bật khi cần; dùng SSH/TLS và danh tính máy rõ ràng | API không bị public hoặc mở cho mạng người dùng |
| Telnet / HTTP cũ | Tắt nếu không có yêu cầu ngoại lệ có phê duyệt | Probe từ user VLAN và admin subnet đều không thấy service cũ |
| Console / BMC | Đặt trên OOB hoặc vùng quản trị có ACL riêng, quyền cao được kiểm toán | Không lộ iLO/iDRAC/console server qua Internet |
| Syslog / telemetry | Chọn nguồn mgmt nếu thiết bị hỗ trợ, chuyển tới collector được duyệt | Có timestamp đúng, log đăng nhập và cấu hình |
| Backup / firmware management | Tài khoản dịch vụ giới hạn, kho bảo vệ, integrity và lịch bảo trì | Không cần cấp Internet trực tiếp cho mọi thiết bị |

Cần kiểm tra **mọi giao diện lắng nghe** của thiết bị. Một số sản phẩm cho phép SSH/HTTPS trên nhiều SVI, loopback hoặc interface data-plane dù đã có mgmt0. Giới hạn dịch vụ ở interface quản trị nếu được hỗ trợ; nếu không, áp dụng ACL lọc **đến control/management CPU của thiết bị** trên các interface liên quan, đồng thời lọc tại firewall.

### 8.2. IPv6 là một phần của chính sách

Nếu thiết bị bật IPv6, phải kiểm tra:

- Địa chỉ IPv6 link-local và global trên interface management lẫn production.
- Dịch vụ quản trị có nghe trên \`::\` (mọi địa chỉ IPv6) hay không.
- Chính sách firewall/ACL IPv6 và route/VRF IPv6 có tương đương với IPv4 không.
- IPv6 neighbor discovery, router advertisement và các đường quản trị nội bộ có bị mở ngoài ý muốn không.

Một thiết bị được chặn SSH bằng ACL IPv4 nhưng vẫn cho phép SSH qua IPv6 là **chưa hoàn tất phân tách**. Không tắt IPv6 máy móc nếu tổ chức có dùng; hãy cấu hình bảo mật tương ứng.

### 8.3. Ngăn truy cập quản trị từ chính data-plane interface

Có ba lớp kiểm soát nên kết hợp:

1. **Service binding:** dịch vụ quản trị chỉ bind management interface/VRF nếu hệ điều hành hỗ trợ.
2. **Network admission:** firewall hoặc ACL chỉ cho địa chỉ bastion/monitoring đến đúng port đích.
3. **Identity and authorization:** AAA/RBAC giới hạn từng thao tác sau khi kết nối.

Trong một số thiết bị, traffic tới địa chỉ IP của chính thiết bị đi tới CPU theo đường **local input**, không đi qua rule forward thông thường. Vì vậy, chỉ cấu hình ACL giữa các subnet chưa đủ; cần kiểm tra management access class, control-plane ACL/host-inbound policy hoặc chức năng tương đương của đúng vendor. **CoPP** giới hạn tốc độ đến CPU, nhưng không thay thế danh sách nguồn quản trị được phép.

## 9. Quy trình chuyển đổi an toàn từ mạng quản trị chung

Thiết lập ranh giới trước khi thay đổi production là điều quan trọng: thay đổi SSH/VRF hoặc default route có thể làm mất phiên quản trị đang dùng.

### Bước 1 — Kiểm kê bề mặt quản trị

Lập bảng cho từng thiết bị gồm: tên/serial, vị trí, chủ sở hữu, phần mềm, IP quản trị hiện tại, interface/cổng mgmt riêng, dịch vụ SSH/HTTPS/SNMP/API, AAA, console/OOB, đường kết nối, logging và cấu hình backup. Đánh dấu thiết bị có địa chỉ quản trị trên user VLAN hoặc WAN.

### Bước 2 — Thiết kế và rà soát phụ thuộc

Vẽ đường từ admin VPN → bastion → firewall → interface quản trị; vẽ riêng đường chiều về. Liệt kê AAA, DNS, NTP, syslog, monitoring, backup, firmware repository, controller và automation. Kiểm tra thiết bị có hỗ trợ **management VRF**, routing theo VRF và ràng buộc service theo VRF hay không.

### Bước 3 — Chuẩn bị quyền truy cập phục hồi

- Xác nhận console/OOB thật sự hoạt động, đã kiểm thử và có người trực sử dụng.
- Sao lưu running và startup configuration; xác minh khả năng phục hồi cấu hình.
- Chuẩn bị maintenance window, người phê duyệt, liên lạc với NOC và service owner.
- Xác định thời điểm tự động rollback hoặc phương án can thiệp qua console khi mất phiên.
- Kiểm tra sẵn tài khoản/đường đăng nhập thứ hai qua mạng quản trị mới trước khi xóa đường cũ.

### Bước 4 — Dựng mạng quản trị và rule chính sách

Tạo management VLAN/VRF hoặc OOB link, địa chỉ quản trị, các static/default route theo thiết kế và vùng firewall. Áp chính sách default deny từ user zone. Cho phép luồng đến dịch vụ hạ tầng cần thiết theo **ma trận truy cập**.

### Bước 5 — Di chuyển dịch vụ và xác thực

Ràng buộc SSH/HTTPS/API/SNMP vào management interface nếu hỗ trợ; cấu hình AAA, logging, source-interface và VRF cho DNS/NTP/syslog/telemetry/backup. Kiểm tra đăng nhập từ bastion bằng tài khoản ít quyền và tài khoản admin được phê duyệt. Không xóa địa chỉ quản trị cũ cho đến khi đường mới đã được xác minh theo change plan.

### Bước 6 — Khóa đường cũ và thực hiện negative test

Tắt các dịch vụ không cần trên user-facing interface; cập nhật local input ACL và firewall. Từ **USER VLAN** và các vùng không được cấp quyền, thử truy cập các cổng quản trị đã nằm trong phạm vi kiểm thử; phải thất bại theo chính sách. Kiểm tra cả IPv4 và IPv6 nếu có.

### Bước 7 — Giám sát và đóng thay đổi

Quan sát log DENY/ALLOW, AAA login, tác động tới giám sát SNMP/telemetry, NTP, syslog, automation, ứng dụng nghiệp vụ và tình trạng CPU. Ghi bằng chứng trước/sau, xác nhận của người chịu trách nhiệm và mốc kết thúc thay đổi.

## 10. Pseudoconfig: cách diễn đạt chính sách mà không phụ thuộc vendor

Khối sau là **pseudocode minh họa ý định cấu hình**, không phải cú pháp có thể dán trực tiếp lên Cisco, Junos, FortiOS, RouterOS hay hệ điều hành mạng cụ thể. Cần đối chiếu tài liệu của chính thiết bị và kiểm thử trong lab.

~~~yaml
device: sw-access-01
management:
  interface: mgmt0
  vrf: MGMT
  address: 10.20.90.11/24
  gateway_in_mgmt_vrf: 10.20.90.1
  services:
    ssh:
      enabled: true
      bind: mgmt0
      allowed_sources:
        - 10.20.91.10/32
      authentication: aaa_and_approved_ssh_keys
    https:
      enabled: false  # chỉ bật nếu có Web UI thật sự cần
    telnet:
      enabled: false
    http:
      enabled: false
    snmp:
      version: v3
      allowed_sources:
        - 10.20.92.10/32
      access: read_only
  dependencies:
    aaa_server: 10.20.92.11
    syslog_server: 10.20.92.12
    ntp_server: 10.20.92.13
    dns_server: 10.20.92.15
  emergency_access:
    via_console: true
    local_break_glass: controlled_vault
~~~

**Điểm kiểm chứng:** nếu thiết bị không hỗ trợ bind SSH vào \`mgmt0\`, cần áp ACL local input để nguồn từ data-plane không tới được SSH. Nếu SNMP polling dùng IP khác với \`10.20.92.10\`, thay đổi phải được cập nhật trong cả ACL thiết bị và firewall.

Ví dụ rule logic cho firewall ranh giới:

~~~text
POLICY MGMT-SEGMENT
  DENY  USER                -> MANAGEMENT          any
  DENY  GUEST / IOT         -> MANAGEMENT          any
  ALLOW AUTHORIZED-ADMINVPN -> BASTION             tcp/443
  ALLOW BASTION             -> SW-ACCESS-01        tcp/22
  ALLOW BASTION             -> ROUTER-MGMT         tcp/22
  ALLOW MONITORING          -> MGMT-DEVICES        udp/161
  ALLOW MGMT-DEVICES        -> AAA                 tcp/49
  ALLOW MGMT-DEVICES        -> SYSLOG              tcp/6514
  ALLOW MGMT-DEVICES        -> NTP                 udp/123
  ALLOW MGMT-DEVICES        -> MGMT-DNS            udp/53,tcp/53
  DENY  MANAGEMENT          -> INTERNET           any
  DENY  ANY                 -> MANAGEMENT          any
  LOG   deny events at boundary, with rate limit
~~~

Đây là **ma trận mục tiêu**: trên firewall thực tế phải xét thứ tự rule, zone, địa chỉ sau NAT, security policy, session tracking, IPv6, return traffic và giới hạn logging. Đừng chuyển pseudocode thành lệnh chạy production mà không kiểm tra syntax, phạm vi, change control và cơ chế rollback.

### 10.1. Source-interface và đường về

Thiết bị có thể thực hiện SSH inbound qua management VRF nhưng tự gửi syslog hoặc TACACS+ qua routing table production do chưa cấu hình source VRF cho service tương ứng. Hậu quả: truy cập quản trị thành công nhưng AAA timeout, log mất hoặc gói phản hồi đi sai đường.

Với từng dịch vụ, kiểm tra đồng thời:

- Source IP và VRF khi thiết bị **khởi tạo** phiên đến server.
- Route đi và route trở về đối với client, bastion, AAA, DNS, NTP, collector.
- ACL/firewall ở cả hai phía, session state và NAT.
- Kết quả DNS resolve và timezone/NTP; thất bại DNS có thể khiến tên AAA/syslog không phân giải.
- Trạng thái khi một uplink hoặc một server AAA bị mất.

Trong mô hình OOB, nếu cổng mgmt0 dùng cáp riêng thì **không** giả định route/data-plane của thiết bị sẽ tự chuyển lưu lượng sang OOB khi một uplink lỗi. Khả năng chuyển đổi phụ thuộc thiết kế và hỗ trợ của thiết bị.

## 11. Kiểm thử kết nối và chứng minh đã phân tách

### 11.1. Positive test và negative test

Bộ kiểm thử phải kiểm tra cả đường được phép **hoạt động** lẫn đường bị cấm **thực sự bị chặn**.

| Mã | Nguồn → đích | Kỳ vọng | Chứng cứ |
|---|---|---|---|
| T01 | Quản trị viên hợp lệ qua VPN → bastion | MFA và cấp quyền thành công | IdP/VPN log, bastion audit |
| T02 | Bastion → switch \`10.20.90.11:22\` | SSH thành công với tài khoản đúng vai trò | Firewall ALLOW, AAA log, phiên SSH |
| T03 | USER \`10.20.10.25\` → \`10.20.90.11:22\` | Kết nối bị từ chối/chặn theo chính sách | Firewall DENY hoặc ACL counter |
| T04 | USER → \`10.20.90.11:443\` | Không có Web UI truy cập được | Local input ACL và test kết nối |
| T05 | Guest Wi-Fi/IoT → subnet MGMT | Không truy cập dịch vụ quản trị | Zone policy và log |
| T06 | Monitoring \`10.20.92.10\` → SNMPv3 | Poll đúng thiết bị, đúng quyền | Monitoring dashboard và audit |
| T07 | Thiết bị → AAA/syslog/NTP | Giao tiếp bình thường qua management VRF | AAA auth, nhận log, offset NTP |
| T08 | USER → mạng ứng dụng hợp lệ | Vẫn hoạt động | Health check nghiệp vụ |
| T09 | Admin không đủ quyền → thao tác thay đổi | Bị từ chối, có audit | AAA authorization/accounting |
| T10 | Truy cập từ mạng không được phép qua IPv6 | Bị chặn tương đương IPv4 | IPv6 ACL/firewall log |
| T11 | Trình tự rollback/console theo lab | Lấy lại quyền quản trị được | Biên bản kiểm thử phục hồi |

**Không coi ping thất bại là bằng chứng đầy đủ**. ICMP có thể bị chặn trong khi SSH/HTTPS vẫn mở. Ngược lại, ping có thể được cho phép vì chẩn đoán mà cổng quản trị vẫn được bảo vệ.

### 11.2. Lệnh kiểm tra thụ động và kết nối hạn chế trong lab

Trên máy Linux ở đúng vùng kiểm thử:

~~~bash
# Kiểm tra hệ điều hành chọn đường tới IP quản trị nào
ip route get 10.20.90.11

# Xem địa chỉ và route của máy kiểm thử
ip -brief address
ip route show

# Chỉ kiểm tra một cổng được cho phép thử trong lab
nc -vz -w 3 10.20.90.11 22
~~~

Trên Windows PowerShell:

~~~powershell
Test-NetConnection -ComputerName 10.20.90.11 -Port 22
Get-NetRoute -AddressFamily IPv4
~~~

Kết quả **T03** từ USER VLAN nên là kết nối thất bại và có bằng chứng policy từ firewall/ACL. Việc hiển thị một route trên máy nguồn **không đủ chứng minh** tuyến thực sự được phép đi tới đích; cần đối chiếu trạng thái trên ranh giới.

Nếu đăng nhập SSH thành công từ bastion, kiểm tra host key, danh tính và quyền của tài khoản theo quy trình vận hành. Chỉ thực hiện thay đổi cấu hình trong maintenance window được phê duyệt.

### 11.3. Kiểm thử đường đi thực tế

Một lộ trình từ bastion tới IP quản trị phải thỏa mãn:

1. Đi qua đúng interface/gateway của vùng quản trị.
2. Không bypass firewall nhờ một route tắt, bridge, NAT hoặc trunk sai.
3. Có đường trả lời hợp lệ, không rơi sang VRF sản xuất.
4. Không có interface khác của thiết bị còn cho phép cùng dịch vụ từ USER/WAN.
5. Hoạt động khi VLAN/VRF/route failover theo thiết kế; mất đường dự phòng phải phát cảnh báo.

Nếu đang giám sát bằng flow log, phân biệt **flow bị DENY** với session thành công; số packet và byte trong metadata không chứng minh một phiên SSH đã xác thực.

## 12. Các lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách kiểm tra và sửa |
|---|---|---|
| Có VLAN quản trị nhưng vẫn route any-any | User traffic truy cập trực tiếp SSH/Web UI | Kiểm tra inter-VLAN ACL/firewall, negative test |
| Management VRF nhưng có route leak rộng | Đường từ user network vẫn vào được MGMT | Audit VRF route table, import/export route-target, policy |
| Quên local input ACL | Thiết bị nhận SSH ở IP của data interface | Xác minh service binding và ACL tới CPU |
| Chỉ chặn IPv4 | IPv6 mở cửa quản trị | Kiểm tra listening sockets, IPv6 rules và test |
| Bastion có quyền đến toàn subnet và mọi port | Nếu bastion bị chiếm, khó giới hạn ảnh hưởng | Thu hẹp theo host, port, nhóm quản trị, RBAC |
| AAA chỉ đi qua production route | Khi đổi VRF, admin không đăng nhập được | Test source VRF, DNS và return path trước chuyển đổi |
| Syslog/NTP/SNMP bị chặn sau thay đổi | Mất giám sát và lệch thời gian điều tra | Test đủ dependency và alert pipeline |
| OOB dùng chung đúng một đường/uplink rủi ro | Production lỗi kéo theo OOB lỗi | Kiểm kê vật lý, đường WAN/nguồn và DR test |
| Địa chỉ quản trị còn lộ trên WAN | Bị quét, brute force, lộ dịch vụ | Đánh giá mọi interface/listener và firewall edge |
| Dùng SNMPv2c mặc định | Community bị lộ hoặc có quyền quá rộng | SNMPv3 authPriv, nguồn cho phép, quyền read-only |
| Tắt đường quản trị cũ quá sớm | Bị lockout, cần thao tác onsite | Đường console/OOB, phiên thứ hai và rollback |
| NAT che nguồn truy cập quản trị | Audit không xác định được ai | Bảo toàn định danh ở bastion/VPN, mapping NAT và log |
| Quá nhiều ngoại lệ firewall | Dần trở về trạng thái any-any | Owner/hạn hết hiệu lực, review định kỳ, test hồi quy |

Một cách kiểm tra thiết kế hữu ích là chọn ngẫu nhiên một thiết bị bất kỳ và trả lời: **IP quản trị của nó có những đường vào nào, ai có thể sử dụng mỗi đường, quyền của họ là gì, bằng chứng nào cho thấy các đường khác bị chặn?**

## 13. Phối hợp với giám sát an ninh và điều tra sự cố

Tách management plane tạo ranh giới dễ giám sát hơn, nhưng cần có dữ liệu đủ tốt để phát hiện truy cập trái phép.

### 13.1. Nguồn log và alert

| Nguồn | Sự kiện cần giám sát | Ý nghĩa điều tra |
|---|---|---|
| VPN/IdP | Login thất bại, MFA bất thường, nguồn địa lý/thiết bị lạ, cấp quyền mới | Xác minh ai bắt đầu phiên quản trị |
| Bastion/PAM | Mở phiên, thiết bị đích, thời lượng, lệnh được duyệt và kết thúc phiên | Truy vết đường truy cập đặc quyền |
| Device AAA | Login, command authorization, thay đổi quyền hoặc dùng break-glass | Xác minh hành động trên thiết bị |
| Firewall/ACL | Truy cập USER → MGMT bị DENY, nguồn mới, spike thử cổng | Phát hiện truy cập từ vùng không được phép |
| Switch/NAC | Thay đổi VLAN, trunk, switchport, 802.1X mapping | Tìm nguyên nhân phân đoạn bị thay đổi |
| Routing/VRF | Route leak, thay đổi default route, dynamic routing adjacency | Phát hiện xuất hiện đường quản trị ngoài ý muốn |
| Device config audit | Thay đổi SSH, SNMP, API, ACL, AAA hoặc firmware | Phát hiện suy giảm hardening |
| Syslog/telemetry pipeline | Thiết bị ngừng gửi log, độ trễ tăng, collector lỗi | Phân biệt “không còn sự kiện” với mất quan sát |

**Ví dụ cảnh báo có giá trị:** “Một IP từ USER VLAN có 30 kết nối bị chặn tới \`10.20.90.11:22\` trong 2 phút, đồng thời thiết bị có thay đổi ACL”. Điều này chưa chứng minh xâm nhập, nhưng đủ căn cứ ưu tiên kiểm tra firewall, endpoint nguồn, nhật ký cấu hình và người thực hiện thay đổi.

### 13.2. Quy trình xử lý khi phát hiện đường tắt vào MGMT

1. Xác nhận sensor/ACL báo sự kiện thật, xác định timestamp và IP nguồn/đích.
2. Kiểm tra DHCP/NAC/VPN/NAT để biết tài sản và người dùng tại thời điểm đó.
3. Kiểm tra thay đổi firewall, route, VRF và dịch vụ thiết bị gần thời điểm sự kiện.
4. Đánh giá liệu phiên quản trị đã được thiết lập hay chỉ là kết nối bị từ chối.
5. Giới hạn đường đi sai phạm bằng rule hẹp có phê duyệt; giữ chứng cứ và đảm bảo đường quản trị hợp lệ còn hoạt động.
6. Tìm nguồn gốc sai cấu hình hoặc tài khoản bị lạm dụng, xử lý và xác minh lại bằng T01–T11.
7. Bổ sung kiểm thử hồi quy, owner và hạn xử lý cho nguyên nhân gốc.

Với mỗi kết luận, tách **fact**, **hypothesis** và **unknown**. Ví dụ “Firewall ghi DENY một phiên thử SSH” là fact; “máy nguồn bị chiếm quyền” mới là giả thuyết cần chứng cứ endpoint/EDR.

## 14. Trường hợp đặc biệt: Wi-Fi, VPN, cloud và controller

### 14.1. Wi-Fi và controller

Access point có thể xử lý traffic SSID của người dùng, còn quản trị AP và controller cần mạng quản trị riêng. Cần phân biệt **SSID/VLAN của client** với **AP management VLAN** và đường CAPWAP/control của controller theo thiết kế. Guest SSID không được truy cập trang quản trị AP/controller. Kiểm tra trunk native VLAN, tagging, DHCP, NAC và lưu lượng controller–AP; nếu sai có thể làm AP mất liên lạc với controller.

### 14.2. Thiết bị VPN và truy cập từ xa

VPN mang traffic người dùng có thể kết thúc trên cùng firewall với VPN admin. Phân biệt bằng chính sách xác thực, nhóm quyền, địa chỉ cấp phát, route/policy và security zone. Chỉ cấp đường đến bastion cho **nhóm quản trị**, sau MFA và kiểm tra thiết bị nếu áp dụng. Không cho phép mọi phiên VPN truy cập trực tiếp interface quản trị firewall.

### 14.3. Mạng cloud và thiết bị ảo

Trong cloud, phân tách management plane có thể dùng VPC/VNet hoặc subnet riêng, route table, security group/NSG, network firewall, private endpoint và identity policy. Đối với network virtual appliance, kiểm tra cả management NIC và data NIC, các security group gắn với từng interface, public IP, route table và khả năng appliance tự chạy dịch vụ admin trên data interface.

**Cloud provider control plane** (API quản lý tài nguyên cloud) khác với management plane của network appliance nằm trong workload. Bảo vệ control plane cloud còn cần IAM, MFA, audit API và chính sách tổ chức. Tạo management subnet riêng cho appliance không tự động khóa quyền thay đổi cloud route/security group.

### 14.4. Cơ sở hạ tầng dùng chung và tự động hóa

Automation platform, configuration management, backup và observability có thể cần kết nối xuyên vùng. Mỗi hệ thống nên có danh tính máy/tài khoản dịch vụ riêng, quyền hạn tối thiểu, log và cơ chế xoay khóa. Không gán cho mọi công cụ quyền SSH admin đến toàn bộ subnet. Nếu cần repository cập nhật firmware, dùng đường đi được kiểm soát thay vì mở unrestricted Internet từ management zone.

## 15. Thay đổi cấu hình, rollback và khả năng phục hồi

### 15.1. Hồ sơ thay đổi tối thiểu

Mỗi thay đổi tách management plane nên ghi:

- **Change ID**, thời gian, người phê duyệt, phạm vi thiết bị và phụ thuộc nghiệp vụ.
- Sơ đồ trước/sau: management IP, interface, VLAN/VRF, firewall zone và route.
- Ma trận traffic được cho phép và bị từ chối, gồm IPv4/IPv6.
- Backup cấu hình và cách khôi phục, kiểm chứng console/OOB.
- Lệnh/thao tác triển khai phù hợp đúng vendor/version và thứ tự thao tác.
- Bộ test T01–T11, nguồn thực hiện, kỳ vọng và bằng chứng.
- Điều kiện rollback: mất admin access, AAA/SNMP/syslog lỗi, hoặc nghiệp vụ bị ảnh hưởng ngoài ngưỡng.
- Kết quả thực hiện, mọi ngoại lệ, owner theo dõi và ngày review.

### 15.2. Tình huống rollback mẫu

**Tình huống:** vừa gắn interface quản trị vào VRF \`MGMT\`, đội vận hành không còn SSH đến switch vì default route của VRF thiếu đường tới bastion.

Quy trình xử lý:

1. Giữ nguyên phạm vi thay đổi, báo Incident/Change Commander và kích hoạt mốc rollback.
2. Sử dụng phiên console/OOB đã thử trước đó để kiểm tra table \`MGMT\`, route, gateway và binding SSH.
3. Khôi phục route/policy đúng thiết kế hoặc hoàn tác cấu hình thay đổi theo kế hoạch đã được phê duyệt.
4. Xác minh truy cập từ bastion, log AAA, NTP/syslog và negative test từ USER.
5. Ghi nguyên nhân, dữ liệu chẩn đoán và cập nhật playbook trước khi triển khai tiếp.

Trong tình huống này, **không mở tạm SSH từ toàn user network** chỉ để khắc phục lockout. Giải pháp cần duy trì ranh giới đã đặt ra, đồng thời đảm bảo có lối khôi phục thông qua console/OOB.

## 16. Bài thực hành: thiết kế phân tách cho văn phòng nhỏ

### 16.1. Đề bài

Một văn phòng có:

- 120 laptop ở \`10.20.10.0/24\` và 40 thiết bị IoT ở \`10.20.30.0/24\`.
- Hai access switch, một router biên và một wireless controller.
- Địa chỉ quản trị hiện dùng chung với user VLAN; SSH và HTTPS có thể mở từ mọi laptop.
- Một VPN người dùng đã tồn tại, nhưng chưa có VPN nhóm quản trị hoặc bastion.
- Monitoring và syslog cần tiếp tục thu thập từ thiết bị khi tách mạng.

Hãy thiết kế mô hình mục tiêu dùng mạng \`10.20.90.0/24\` cho thiết bị, bastion \`10.20.91.10\` và dịch vụ quản trị \`10.20.92.0/24\`. Cần nộp: sơ đồ mạng, ma trận firewall, danh sách dịch vụ cần bind, phương án xác thực, nguồn log, kịch bản kiểm thử và rollback.

### 16.2. Gợi ý giải pháp

1. Chọn OOB nếu có hạ tầng/cổng riêng cho router hoặc firewall trọng yếu. Với access switch, dùng management VLAN và VRF nếu hỗ trợ, kèm policy L3.
2. Phân biệt nhóm VPN quản trị với VPN người dùng, yêu cầu MFA và đi qua bastion.
3. Cho bastion tới IP quản trị bằng SSH/HTTPS theo host và vai trò; cho monitoring SNMPv3, syslog/NTP/AAA theo đúng chiều.
4. Cấu hình local input ACL; vô hiệu Telnet, HTTP plaintext và SNMP legacy khi không có yêu cầu ngoại lệ.
5. Kiểm tra DHCP/NAC và trunk để thiết bị IoT không vào management VLAN.
6. Chứng minh laptop/IoT không SSH/HTTPS tới các thiết bị; xác nhận backup, syslog, SNMP, NTP, AAA vẫn chạy.
7. Đặt điều kiện rollback và xác minh console/OOB trước khi xóa management IP cũ.

### 16.3. Mẫu rubric 100 điểm

| Tiêu chí | Điểm tối đa | Bằng chứng |
|---|---:|---|
| Phân biệt plane, chọn phương án tách | 15 | Sơ đồ và giải thích OOB/VLAN/VRF |
| Phân vùng và định tuyến | 20 | Địa chỉ, VRF/VLAN, route đi và về, không route leak |
| Chính sách least privilege | 20 | Ma trận nguồn/đích/cổng và default deny |
| Danh tính và hardening service | 15 | VPN/MFA, bastion, AAA/RBAC, SSH/HTTPS/SNMPv3 |
| Kiểm thử và giám sát | 20 | Positive/negative test, IPv6, log AAA/firewall/syslog |
| Phục hồi và vận hành | 10 | Backup, console/OOB, rollback, change log |
| **Tổng** | **100** | Không chấm “đã tạo VLAN” là hoàn thành nếu user vẫn vào được SSH |

## 17. Câu hỏi tự đánh giá

**Câu 1.** Nếu management VLAN đã khác VLAN người dùng nhưng core switch vẫn có route giữa hai VLAN, mạng quản trị đã được cách ly đủ chưa?

*Gợi ý:* Chưa. Routing L3 và ACL/firewall vẫn cho phép hoặc ngăn lưu lượng; phải kiểm tra policy thực tế và các cổng lắng nghe của thiết bị.

**Câu 2.** Management VRF có thay thế firewall và AAA hay không?

*Gợi ý:* Không. VRF cô lập bảng route, nhưng route leaking, service binding, NAT và cấu hình nhầm có thể làm lộ quản trị; AAA/RBAC giới hạn quyền của danh tính hợp lệ.

**Câu 3.** Vì sao phải kiểm tra cả DNS, NTP, syslog, SNMP và TACACS+ sau khi chuyển đường quản trị?

*Gợi ý:* Chúng có thể dùng source-interface/VRF hoặc route khác SSH. Đăng nhập thành công chưa chứng minh giám sát, xác thực/ủy quyền và kiểm toán hoạt động.

**Câu 4.** Trong một hệ thống có cổng mgmt0 chuyên dụng nhưng OOB switch chia sẻ đúng uplink của production, có thể kết luận quản trị không bị ảnh hưởng khi production mất mạng không?

*Gợi ý:* Không. Phải kiểm kê và thử nghiệm phụ thuộc vật lý, upstream, power, firewall và WAN của đường quản trị.

**Câu 5.** Nếu thử SSH từ USER VLAN thất bại, đã chứng minh toàn bộ management plane không thể truy cập từ user network chưa?

*Gợi ý:* Chưa. Còn HTTPS/API/SNMP, interface/SVI/loopback khác, NAT bypass, IPv6, route tắt và quyền truy cập qua các vùng khác; phải kiểm tra cả ma trận.

**Câu 6.** Một tài khoản admin xác thực được trên bastion có nên mặc nhiên có quyền cấu hình mọi thiết bị không?

*Gợi ý:* Không. Đích được phép và quyền thiết bị vẫn phải giới hạn theo RBAC/AAA và nhu cầu công việc, có audit và quy trình cấp quyền.

**Câu 7.** Firewall ghi nhiều dòng DENY từ IoT VLAN tới management IP. Có thể kết luận thiết bị IoT đã bị chiếm quyền không?

*Gợi ý:* Chưa. Cần phân biệt cấu hình sai, health probe, người vận hành kiểm thử hoặc mã độc; thu DHCP/NAC, firewall logs và EDR/asset telemetry, kiểm tra các giả thuyết.

## 18. Checklist hoàn thành

- [ ] Đã kiểm kê địa chỉ quản trị, giao thức admin, chủ sở hữu, interface và đường phụ thuộc của từng thiết bị.
- [ ] Đã xác định chính xác management, control và data plane trong thiết kế.
- [ ] Đã chọn OOB, management VLAN/VRF hoặc tổ hợp phù hợp với mức quan trọng.
- [ ] Management traffic có phân vùng địa chỉ, route, firewall/ACL và local input policy rõ ràng.
- [ ] USER, Guest/IoT và VPN người dùng không có đường truy cập trực tiếp tới management services.
- [ ] Quản trị viên vào qua VPN/bastion được phê duyệt; MFA, danh tính cá nhân và RBAC/AAA hoạt động.
- [ ] Dịch vụ SSH/HTTPS/API/SNMP chỉ bật khi cần, bind và lọc đúng nguồn; dịch vụ legacy được tắt hoặc có ngoại lệ.
- [ ] IPv4 và IPv6 đều được kiểm tra; không còn SVI/loopback/data interface mở quản trị ngoài ý muốn.
- [ ] DNS, NTP, syslog, SNMP/telemetry, backup và AAA dùng source route/VRF phù hợp.
- [ ] Có positive test và negative test, lưu kết quả cùng firewall/AAA log.
- [ ] Có backup cấu hình, đường console/OOB đã thử và quy trình rollback.
- [ ] Có giám sát route leak, thay đổi policy, login thất bại và thiếu telemetry.
- [ ] Các ngoại lệ có người phụ trách, thời hạn, lý do và kế hoạch xem xét lại.

**Tiêu chí kết thúc:** tách management plane khỏi user traffic chỉ đạt yêu cầu khi có thể **chứng minh đường truy cập đặc quyền là hữu hạn, được xác thực và được kiểm toán**, trong khi tất cả các đường không được phép đều bị ngăn chặn bằng biện pháp phù hợp với kiến trúc thực tế. Thực hành cần gắn segmentation với firewall, AAA, vận hành, kiểm thử an toàn và khả năng khôi phục khi mạng gặp sự cố.

