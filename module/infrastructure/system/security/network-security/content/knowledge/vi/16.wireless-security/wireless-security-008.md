# Guest network: Thiết kế và bảo vệ mạng Wi-Fi dành cho khách

## 1. Guest network là gì?

**Guest network** là vùng mạng dành cho người dùng hoặc thiết bị **không thuộc phạm vi quản trị và tin cậy như thiết bị nội bộ**, chẳng hạn khách đến văn phòng, đối tác đến làm việc ngắn hạn hoặc người tham dự sự kiện. Trong bối cảnh **Wireless security**, guest network thường được cung cấp qua một hoặc nhiều **SSID Wi-Fi dành cho khách** và ưu tiên đáp ứng nhu cầu truy cập Internet có kiểm soát, thay vì cấp quyền trực tiếp vào mạng doanh nghiệp.

Mục tiêu không chỉ là tạo một SSID có tên “Guest”. Một thiết kế hiệu quả cần phân biệt rõ **vùng truy cập của khách**, **các dịch vụ hạ tầng cần thiết để kết nối**, **mạng nội bộ phải bảo vệ** và **cách thực thi chính sách trên đường đi lưu lượng**.

Trong học phần **SECURITY_NETWORK_SECURITY**, guest network kết nối nhiều lớp kiến thức: phân đoạn mạng bằng VLAN/VRF, firewall và kiểm soát truy cập, bảo vệ DNS, xác thực kết nối, phát hiện xâm nhập IDS/IPS, an toàn mạng không dây và kiến trúc nhiều lớp tại văn phòng hoặc cloud. Mạng khách được thiết kế đúng giúp giới hạn tác động nếu thiết bị khách nhiễm mã độc hoặc bị kiểm soát, nhưng không thay thế bảo mật ứng dụng, bảo mật thiết bị và giám sát.

**Sau bài này, bạn có thể:**

1. Giải thích sự khác nhau giữa **SSID**, **VLAN/subnet**, **security zone** và **client isolation**.
2. Xây dựng ma trận lưu lượng cho mạng khách theo nguyên tắc **Internet-only** hoặc chỉ cho đúng dịch vụ đã được phê duyệt.
3. Lựa chọn phương án **Open, OWE/Enhanced Open, WPA2/WPA3-Personal, WPA-Enterprise và captive portal** theo mức tin cậy và khả năng thiết bị.
4. Nhận diện giới hạn của captive portal, mật khẩu dùng chung, địa chỉ MAC ngẫu nhiên và các cách ngăn truy cập ngang giữa khách.
5. Kiểm thử chính sách IPv4, IPv6, DNS, DHCP, roaming và truy cập giữa các client mà không làm gián đoạn hệ thống thật.
6. Lập kế hoạch vận hành, giám sát, ứng phó sự cố và quản lý vòng đời thông tin truy cập khách.

## 2. Ranh giới tin cậy trong mạng Wi-Fi khách

### 2.1. SSID không tự tạo ra phân đoạn mạng

**SSID (Service Set Identifier)** là tên mạng Wi-Fi mà thiết bị có thể nhìn thấy và chọn kết nối. Một SSID có thể được ánh xạ tới VLAN, một mạng được tunnel về controller, hoặc chính sách truy cập được hệ thống WLAN triển khai theo các cơ chế khác. Nhưng **chỉ tạo thêm SSID không tự bảo đảm tách biệt L2/L3**: nếu khách vẫn được bridge vào cùng mạng nội bộ và có thể gửi gói tới máy doanh nghiệp, ranh giới bảo vệ chưa tồn tại.

| Khái niệm | Chức năng chính | Điều không nên nhầm |
| --- | --- | --- |
| **SSID** | Điểm nhận biết và tham gia mạng Wi-Fi | Không tự quyết định các đích IP được phép truy cập |
| **VLAN** | Tách miền quảng bá L2 khi cấu hình đúng | Không tự thay thế firewall/ACL ở ranh giới L3 |
| **Subnet** | Không gian địa chỉ IP của một mạng | Hai subnet vẫn có thể định tuyến tới nhau nếu không bị chặn |
| **VRF** | Tách bảng định tuyến và ngữ cảnh chuyển tiếp | Cần thiết kế đường ra Internet và các điểm nối giữa VRF |
| **Security zone** | Nhóm tài nguyên có chính sách truy cập chung | Cần gắn với điểm thực thi nhìn thấy lưu lượng |
| **Firewall/ACL** | Quyết định cho phép hoặc chặn theo nguồn/đích/dịch vụ | Chỉ có tác dụng trên đường đi hoặc interface được áp dụng |
| **Client isolation** | Hạn chế các client Wi-Fi trao đổi trực tiếp với nhau | Không mặc nhiên chặn mọi đường qua router, dây LAN hoặc AP khác |
| **Captive portal** | Trang/quy trình chấp nhận điều khoản hoặc xác thực truy cập | Không tự mã hóa liên kết Wi-Fi hay thay xác thực ứng dụng |

### 2.2. Các nhóm cần được tách khỏi mạng khách

Một mạng khách điển hình **không cần** đường trực tiếp đến:

- Máy trạm, máy chủ ứng dụng và cơ sở dữ liệu thuộc mạng doanh nghiệp.
- Địa chỉ quản trị của access point, WLAN controller, switch, router, hypervisor và thiết bị bảo mật.
- Mạng lưu trữ, hệ thống backup, camera, thiết bị IoT/OT hoặc dịch vụ in nội bộ không được cấp phép.
- Mạng VPN quản trị, subnet kết nối chi nhánh, các vùng production/development hay đường quản trị cloud riêng.
- Những client khách khác nếu chính sách **guest-to-guest isolation** yêu cầu không cho trao đổi.

Các ngoại lệ như máy in công cộng, màn hình phòng họp hoặc cổng đăng ký sự kiện phải được **thiết kế thành dịch vụ riêng**, không mở toàn bộ mạng nội bộ chỉ để một chức năng hoạt động.

### 2.3. Guest network không đồng nghĩa mạng an toàn tuyệt đối

Thiết bị khách vẫn có thể sử dụng dịch vụ Internet độc hại, bị lừa đăng nhập vào website giả hoặc gửi lưu lượng quá mức. Mạng khách cũng có thể bị giả mạo bằng **evil twin/rogue access point**. Vì thế thiết kế hướng tới **hạn chế phạm vi tin cậy, bảo vệ hạ tầng và duy trì khả năng phục vụ**, không đưa ra lời hứa “không thể bị tấn công”.

## 3. Threat modeling cho guest network

Trước khi cấu hình, hãy xác định:

1. **Tài sản cần bảo vệ:** dữ liệu nội bộ, hệ thống quản trị, băng thông, DNS, Wi-Fi controller, trải nghiệm người dùng và thông tin cá nhân trong portal/log.
2. **Đối tượng truy cập:** khách được mời, người ngoài trong vùng phủ sóng, nhân viên dùng nhầm SSID, thiết bị cá nhân hoặc thiết bị đã bị nhiễm mã độc.
3. **Điểm vào:** sóng Wi-Fi, mật khẩu dùng chung, portal, API quản trị WLAN, DNS/DHCP, gateway, VPN và các dịch vụ được ngoại lệ.
4. **Đường di chuyển:** từ guest WLAN đến client khác, gateway/management, subnet nội bộ, Internet, hoặc ngược vào qua các kết nối đã thiết lập.
5. **Hậu quả:** truy cập trái phép, nghe lén/lừa đảo, đánh cắp thông tin, cạn địa chỉ DHCP, nghẽn airtime và tăng chi phí Internet.

| Nguy cơ | Kịch bản | Lớp bảo vệ nên có |
| --- | --- | --- |
| Truy cập ngang vào mạng doanh nghiệp | Laptop khách tìm kết nối đến máy chủ nội bộ | VLAN/VRF, deny rule và kiểm chứng route |
| Guest-to-guest | Hai thiết bị khách kết nối hoặc dò dịch vụ của nhau | Client isolation, ACL L2/L3, kiểm thử qua nhiều AP |
| Rogue AP/evil twin | Một AP giả dùng tên SSID giống mạng khách | Inventory AP, giám sát vô tuyến, nhận diện điểm truy cập hợp lệ và hướng dẫn người dùng |
| Lộ mật khẩu khách dùng chung | Mật khẩu được chia sẻ ngoài phạm vi dự kiến | Vòng đời credential, voucher/PPSK nếu hỗ trợ, đổi định kỳ theo rủi ro |
| Thiết bị khách không an toàn | Malware từ client cố quét hoặc khai thác các mạng khác | Segmentation, firewall, IDS/IPS hoặc flow monitoring ở vị trí thích hợp |
| DHCP/DNS giả mạo | Client nhận gateway/DNS không đúng | DHCP snooping, bảo vệ RA/DHCPv6, giới hạn cổng tin cậy |
| Quá tải Wi-Fi hoặc Internet | Nhiều thiết bị streaming hoặc nguồn gửi traffic bất thường | QoS, rate/concurrency limits, giám sát airtime/băng thông, upstream protection |
| Lừa đảo qua captive portal | Trang portal giả thu thập thông tin đăng nhập | HTTPS, tên miền được quản trị, không yêu cầu credential nhạy cảm không cần thiết |
| IPv6 bỏ sót | IPv4 bị chặn nội bộ nhưng IPv6 có đường tới mạng doanh nghiệp | Firewall/ACL IPv6, RA/DHCPv6 policy và kiểm thử dual-stack |
| Lộ log truy cập | Portal và DHCP log giữ dữ liệu khách quá mức | Quyền tối thiểu, retention, audit và tối thiểu hóa dữ liệu |

**Nguyên tắc:** không phải mọi rủi ro đều có thể giảm bằng một firewall rule. Chặn L3 có thể bảo vệ máy chủ nhưng không ngăn được evil twin ở lớp vô tuyến; mã hóa Wi-Fi có thể bảo vệ liên kết vô tuyến nhưng không tự ngăn truy cập tới database nếu route/firewall quá rộng.

## 4. Kiến trúc tham chiếu Internet-only

Một thiết kế phổ biến là **guest SSID → vùng guest riêng → firewall/gateway → Internet**, với các rule chỉ cho phép dịch vụ nền cần thiết và từ chối đường tới mạng nội bộ.

~~~mermaid
flowchart LR
    G[Thiết bị khách] -->|SSID Guest| AP[Access point]
    AP -->|VLAN guest hoặc tunnel| W[WLAN controller / switch]
    W --> F[Firewall / gateway vùng GUEST]
    F -->|Chính sách egress| I[Internet]
    F -->|Chỉ luồng được duyệt| H[DNS / DHCP / Portal]
    F -. Chặn .-> C[Mạng doanh nghiệp]
    F -. Chặn .-> M[Mạng quản trị]
    G -. Client isolation .-> G2[Khách khác]
~~~

Sơ đồ minh họa **ranh giới logic**, không yêu cầu mọi triển khai phải có controller hoặc firewall riêng. Nếu AP làm local breakout, gateway có thể tại chi nhánh. Nếu guest traffic được tunnel về controller/cloud, điểm lọc có thể ở nơi kết thúc tunnel. Điều cần xác minh là **đường đi thực tế và đường về**.

### 4.1. Vùng mẫu để thảo luận

| Vùng | Prefix minh họa | Chức năng |
| --- | --- | --- |
| GUEST | 192.0.2.0/24 | Client Wi-Fi khách |
| CORP | 198.51.100.0/24 | Tài nguyên doanh nghiệp |
| MGMT | 203.0.113.0/24 | Quản trị AP, switch, controller, firewall |
| WAN | Đường lên do ISP cấp | Truy cập Internet |

Các prefix IPv4 này **chỉ dành cho tài liệu theo RFC 5737**; cần thay bằng mạng được cấp hợp lệ trong lab/triển khai thực tế. Với IPv6, prefix dùng cho ví dụ là **2001:db8::/32** theo RFC 3849, không phải prefix có thể định tuyến công cộng.

**Lưu ý quan trọng:** khi nói “khách chỉ được đi Internet”, điều đó không có nghĩa phải chặn mọi địa chỉ private trước khi xem xét dịch vụ nền. DHCP, DNS resolver, captive portal hay NTP do tổ chức quản lý có thể nằm ở địa chỉ riêng. Hãy định nghĩa ngoại lệ cụ thể **trước** khi áp dụng deny cho những mạng nội bộ được bảo vệ và đường chuyển tiếp không mong muốn.

### 4.2. Ma trận lưu lượng khuyến nghị theo mục đích

| Nguồn | Đích | Dịch vụ | Quyết định mong muốn |
| --- | --- | --- | --- |
| Client guest | DHCP/relay của vùng guest | DHCPv4 UDP 67/68 theo đường đi | **Allow** theo mô hình cấp IP |
| Client guest | DNS resolver được duyệt | UDP/TCP 53 khi được dùng | **Allow** có giới hạn |
| Client guest | Portal/cổng xác thực | HTTPS và các đích bootstrap cần thiết | **Allow** đúng phạm vi |
| Client guest | Internet công cộng | Dịch vụ theo chính sách truy cập | **Allow** qua gateway/firewall |
| Client guest | Mạng CORP | Mọi dịch vụ không có ngoại lệ | **Deny** |
| Client guest | Vùng MGMT | SSH/HTTPS/SNMP/API quản trị và các cổng khác | **Deny** |
| Client guest | Mạng backup/IoT/OT nội bộ | Mọi dịch vụ không được phê duyệt | **Deny** |
| Client guest | Guest khác | L2/L3 peer traffic không được phép | **Deny** bằng kiểm soát phù hợp |
| Internet bất kỳ | Client guest | Kết nối mới không được cho phép từ trước | **Deny** tại ingress theo chính sách |
| Firewall/gateway | Client guest | Phản hồi thuộc phiên được phép | **Allow** theo stateful policy tương ứng |

Đây là **ma trận ý định**, không phải một bộ rule có thể copy sang mọi sản phẩm. Trật tự và semantics rule, NAT, stateful inspection, multicast, IPv6, broadcast DHCP và luồng tới chính gateway phụ thuộc thiết bị/kiến trúc.

### 4.3. Ranh giới quản trị và data plane

Địa chỉ quản trị của AP/controller nên nằm trong **management VLAN/zone riêng** hoặc hệ thống điều khiển có truy cập hạn chế. Mặc dù AP phục vụ Wi-Fi khách, điều đó không có nghĩa client guest có quyền gọi HTTPS/SSH tới IP quản trị của AP.

Lưu lượng **control/management plane** như controller–AP, RADIUS, syslog, monitoring hoặc firmware update cần được tách khỏi **data plane** chở traffic của khách. Chặn toàn bộ traffic “đến AP” một cách thiếu hiểu biết có thể làm gián đoạn quản trị WLAN; nên định nghĩa chính xác nguồn và đích được phép ở từng lớp.

## 5. Phân đoạn và client isolation ở nhiều lớp

### 5.1. Tách SSID với VLAN/VRF hoặc policy tương đương

Một số hệ thống gắn guest SSID vào VLAN dành riêng; một số dùng tunnel tập trung hoặc phân đoạn dựa trên chính sách. Trong cả hai trường hợp, cần:

- Kiểm tra **SSID-to-VLAN/zone mapping** trên mọi AP và site.
- Xác định gateway, DHCP scope và DNS trả về đúng vùng guest.
- Đảm bảo route đến CORP/MGMT được kiểm soát hoặc không được import giữa VRF.
- Chặn truy cập nội bộ ở **điểm thực thi có nhìn thấy lưu lượng**.
- Xác minh policy cho cả IPv4 và IPv6, và cho cả client trong cùng lẫn khác AP.

**Một VLAN riêng không thay thế được firewall.** Nếu gateway L3 định tuyến từ GUEST đến CORP mà không có rule chặn, khách vẫn có thể truy cập. Ngược lại, nếu hai thiết bị guest cùng VLAN trao đổi ở lớp 2, firewall ở gateway L3 có thể **không thấy** kết nối đó.

### 5.2. Wireless client isolation

**Client isolation** (còn gọi là AP isolation, peer isolation hoặc tính năng tương tự tùy hãng) nhằm chặn hoặc hạn chế trao đổi trực tiếp giữa các station khách trên Wi-Fi.

Các câu hỏi cần kiểm tra:

1. Client cùng một AP có bị chặn giao tiếp unicast trực tiếp không?
2. Client ở **hai AP khác nhau** nhưng cùng SSID/VLAN có bị chặn không?
3. Client Wi-Fi có thể truy cập một thiết bị **cắm dây** vào cùng VLAN không?
4. Có route giữa các guest subnet/site hoặc qua VPN cho phép đi vòng cơ chế cách ly không?
5. Multicast/broadcast, mDNS, SSDP và discovery được xử lý như thế nào?
6. IPv6 Neighbor Discovery và các dịch vụ cần thiết có tiếp tục hoạt động không?

Không mặc định rằng nút “Enable client isolation” thực hiện cùng một chức năng ở mọi controller. Một số tính năng chỉ giới hạn station kết nối cùng AP, trong khi cross-AP hoặc wired peer cần thêm **private VLAN, ACL hoặc policy phân tán**.

### 5.3. Chặn ngang nhưng vẫn giữ dịch vụ nền

Ngay trong một guest VLAN, client vẫn cần **DHCP**, **ARP** đối với IPv4, **Neighbor Discovery/Router Advertisement** đối với IPv6 và các thông điệp phù hợp để hoạt động. Chặn toàn bộ broadcast/multicast hoặc ICMPv6 không phân biệt có thể phá kết nối.

Hãy thiết kế **isolation theo quan hệ đích**: ngăn guest peer-to-peer và bảo vệ management plane, nhưng vẫn cho các giao thức nền cần thiết giữa client với gateway/relay/resolver. Có thể áp dụng kiểm soát DHCP snooping, ARP inspection, RA Guard hoặc các cơ chế access-layer khác nếu nền tảng hỗ trợ và được thử nghiệm.

### 5.4. Ngoại lệ cho in ấn hoặc trình chiếu

Đôi khi khách cần in tại máy in công cộng hoặc trình chiếu lên một thiết bị trong phòng họp. Không nên tắt toàn bộ guest isolation để việc này hoạt động.

Một kiến trúc có kiểm soát có thể dùng:

- Máy in/thiết bị trình chiếu đặt ở vùng **SHARED-GUEST-SERVICE** riêng.
- Chỉ cho guest đến đúng IP/dịch vụ/port và xác thực phù hợp.
- mDNS/Bonjour gateway được quản trị nếu nhu cầu discovery yêu cầu, thay vì bridge mọi multicast giữa guest và CORP.
- Hạn chế quyền truy cập của thiết bị shared về mạng nội bộ.
- Logging, owner và thời hạn ngoại lệ.

Không suy ra “truy cập được máy in” nghĩa là khách cần truy cập toàn bộ subnet máy in hoặc cổng quản trị của thiết bị đó.

## 6. Mã hóa Wi-Fi và xác thực dành cho khách

Khả năng mã hóa **liên kết vô tuyến** khác với việc cho phép truy cập mạng **qua captive portal** hay xác thực ở ứng dụng. Cần chọn giải pháp phù hợp loại khách và khả năng tương thích thiết bị.

| Phương án | Bảo vệ liên kết vô tuyến | Xác thực/truy cập | Ưu điểm | Rủi ro/giới hạn |
| --- | --- | --- | --- | --- |
| **Open Wi-Fi** | Không có mã hóa truy cập Wi-Fi ở lớp liên kết | Có thể có portal | Đơn giản, nhiều thiết bị hỗ trợ | Traffic không được bảo vệ bởi mã hóa Wi-Fi; ứng dụng phải dùng TLS |
| **OWE / Wi-Fi Enhanced Open** | Mã hóa theo liên kết với khóa riêng theo phiên, không cần mật khẩu dùng chung | Không tự xác thực người dùng hoặc AP | Bảo vệ tính riêng tư so với Open ở lớp vô tuyến | **Không xác thực danh tính AP**; vẫn cần chống evil twin bằng biện pháp khác |
| **WPA2-Personal (AES/CCMP)** | Mã hóa và kiểm tra tính toàn vẹn ở lớp Wi-Fi khi thiết lập đúng | Mật khẩu chia sẻ | Tương thích nhiều thiết bị | Mật khẩu chung có thể bị phát tán; người biết PSK có lợi thế trong một số mô hình tấn công |
| **WPA3-Personal (SAE)** | Cải tiến xác thực và thiết lập khóa so với WPA2-Personal | Mật khẩu/SAE | Phù hợp mạng khách có mật khẩu và client hỗ trợ | Mật khẩu dùng chung vẫn là bí mật phải quản lý; tương thích legacy cần kiểm tra |
| **WPA-Enterprise (802.1X/EAP)** | Xác thực qua hệ thống danh tính và thiết lập khóa theo phiên | RADIUS/EAP, tài khoản/chứng chỉ tùy phương án | Có thể cấp quyền theo định danh | Vận hành và onboarding phức tạp hơn, cần PKI/trust đúng cách |

### 6.1. WPA3-Personal không tự giải quyết quản lý mật khẩu guest

WPA3-Personal sử dụng cơ chế **Simultaneous Authentication of Equals (SAE)** để cải thiện trao đổi khóa so với WPA2-PSK. Tuy nhiên nếu nhiều khách dùng **cùng một mật khẩu**, việc chia sẻ mật khẩu ra bên ngoài vẫn có thể khiến những người không mong muốn tham gia mạng guest. Khi dùng mạng khách mật khẩu chung, cần **vòng đời phân phối/thu hồi**: thay mật khẩu khi cần, cấp theo sự kiện hoặc dùng **PPSK/DPSK/MPSK** nếu nhà cung cấp hỗ trợ mô hình mật khẩu riêng theo nhóm/thiết bị.

Không khuyến nghị dùng WEP, WPA thế hệ cũ hoặc TKIP để tương thích thiết bị lỗi thời. Các client quá cũ cần được xử lý theo chính sách tương thích được phê duyệt, thay vì hạ bảo mật của toàn mạng.

### 6.2. OWE và giới hạn xác thực mạng

**Opportunistic Wireless Encryption (OWE)** giúp mã hóa dữ liệu qua liên kết vô tuyến mà không yêu cầu người dùng biết một mật khẩu chung. Nó cải thiện quyền riêng tư ở mạng không có xác thực người dùng. Nhưng OWE **không chứng minh tên SSID mà client thấy đang thuộc AP hợp pháp của doanh nghiệp**; kẻ xấu vẫn có thể dựng một mạng giả có tên giống và tìm cách lừa người dùng.

Do đó, với OWE/Open, người dùng vẫn cần kiểm tra các website qua HTTPS với chứng chỉ hợp lệ; doanh nghiệp cần có hướng dẫn nhận diện SSID chính thức và giám sát rogue/evil twin khi phù hợp. Không đồng nhất “đã có mã hóa OWE” với “đã xác thực được chủ sở hữu hotspot”.

### 6.3. Protected Management Frames (PMF)

**Protected Management Frames (PMF, 802.11w)** bảo vệ một số frame quản lý Wi-Fi nhất định sau khi các bên thiết lập trạng thái bảo mật phù hợp. WPA3 có những yêu cầu PMF tương ứng; mức hỗ trợ và chính sách mixed/transition mode phụ thuộc thiết bị và profile triển khai.

PMF giúp giảm một số dạng giả mạo frame quản lý, nhưng không khiến Wi-Fi miễn nhiễm với nhiễu sóng, gây nghẽn RF hoặc mọi dạng tấn công vô tuyến. Không tự chọn cấu hình “optional/required” mà chưa kiểm thử thiết bị và tiêu chuẩn bảo mật đang áp dụng.

## 7. Captive portal: Cho phép truy cập, không phải mã hóa Wi-Fi

**Captive portal** là một quy trình đưa người dùng tới trang thông báo hoặc xác thực trước khi cấp quyền mạng theo chính sách. Nó có thể yêu cầu chấp nhận điều khoản sử dụng, nhập voucher, đăng nhập với một danh tính được cấp quyền hoặc hoàn tất thủ tục đăng ký khách.

Một portal có thể được triển khai tại WLAN controller, gateway, cloud WLAN service hay hệ thống quản lý truy cập. **Portal không tự mã hóa frame Wi-Fi**, không thay thế cấu hình WPA2/WPA3/OWE và không chứng minh thiết bị khách là an toàn.

### 7.1. Luồng truy cập minh họa

~~~mermaid
flowchart TD
    Join[Khách tham gia SSID] --> IP[Nhận địa chỉ / DNS theo vùng guest]
    IP --> State{Đã được cho phép truy cập?}
    State -->|Chưa| Portal[Captive portal / quy trình đăng ký]
    Portal --> Verify{Điều kiện truy cập hợp lệ?}
    Verify -->|Không| Restricted[Chỉ cho portal và dịch vụ bootstrap]
    Verify -->|Có| Allowed[Cấp chính sách guest Internet-only]
    State -->|Đã có phiên hợp lệ| Allowed
    Allowed --> FW[Firewall: chặn CORP / MGMT, cho egress theo policy]
~~~

Luồng trên là **mô hình nghiệp vụ**, không quy định một cách chuyển hướng HTTP duy nhất. Một số hệ điều hành có **Captive Network Assistant**, một số mạng sử dụng cơ chế nhận diện portal hiện đại qua DHCP/IPv6 RA và API. Người dùng cũng có thể cần chủ động mở trang portal theo hướng dẫn đã được xác thực.

### 7.2. HTTPS và vấn đề chuyển hướng

Một portal không thể tùy tiện thay nội dung của phiên **HTTPS tới website bất kỳ** mà vẫn giữ xác thực TLS đúng chuẩn. Nếu gateway cố thay thế website HTTPS bằng trang portal không khớp chứng chỉ, trình duyệt có thể cảnh báo bảo mật; **không được hướng dẫn khách bỏ qua cảnh báo chứng chỉ**.

Thiết kế nên:

1. Phục vụ portal qua **HTTPS với tên miền và chứng chỉ hợp lệ**.
2. Sử dụng cơ chế captive portal discovery được client/nền tảng hỗ trợ, khi có.
3. Cho phép đúng các dịch vụ bootstrap cần thiết như DNS, portal và các endpoint kiểm tra kết nối được duyệt.
4. Không chặn/giả mạo TLS của website người dùng để ép hiển thị portal.
5. Tránh yêu cầu mật khẩu email/công ty trong portal guest nếu không cần thiết.

Các tài liệu như **RFC 8908 (Captive Portal API)** và **RFC 8910 (DHCP/RA Captive Portal Identification)** mô tả cơ chế có cấu trúc. Khả năng hỗ trợ phụ thuộc client, gateway và sản phẩm; không mặc định mọi thiết bị đều dùng các cơ chế này.

### 7.3. Walled garden và ngoại lệ tiền xác thực

**Walled garden** là tập đích người dùng có thể truy cập **trước khi hoàn tất portal**. Một mạng có thể cần:

- DHCP và DNS để client có cấu hình và phân giải portal.
- HTTPS đến hostname của portal.
- Endpoint xác thực đã được phê duyệt.
- Các dịch vụ tối thiểu cần để client phát hiện tình trạng captive.

Mở walled garden quá rộng có thể tạo đường tránh portal. Mở quá hẹp có thể làm portal không hiển thị vì client không thể giải quyết DNS, tải đúng tài nguyên hoặc xác minh chứng chỉ. Cần kiểm thử với các hệ điều hành và đường mạng thực tế, đồng thời giới hạn ngoại lệ theo đích/chức năng rõ ràng.

### 7.4. Session portal, voucher và quyền truy cập

| Phương án | Phù hợp khi | Điều cần quản lý |
| --- | --- | --- |
| Chấp nhận điều khoản | Truy cập khách công cộng ít yêu cầu định danh | Truyền thông chính sách, giới hạn phiên, rate limit |
| Voucher theo sự kiện | Khách tham dự sự kiện, truy cập có hạn | Hạn dùng, số thiết bị, quyền cấp và thu hồi voucher |
| Tài khoản khách được bảo trợ | Đối tác cần phê duyệt từ nhân viên | Sponsor, thời hạn, nhật ký, quy trình thu hồi |
| Mật khẩu SSID luân chuyển | Văn phòng nhỏ, client không hỗ trợ onboarding phức tạp | Phạm vi chia sẻ, lịch đổi mật khẩu, hỗ trợ client |
| Định danh/khóa riêng theo khách | Nhu cầu thu hồi từng khách | Hỗ trợ hệ thống, vòng đời, bảo vệ secret và privacy |

**MAC address không phải danh tính mạnh.** Client có thể dùng địa chỉ MAC ngẫu nhiên cho từng SSID, và địa chỉ MAC cũng có thể bị giả mạo. Việc ghi MAC trong portal chỉ là một tín hiệu vận hành, không đủ để chứng minh danh tính người dùng hay mức đáng tin cậy.

### 7.5. Bảo vệ hệ thống portal

Portal có thể là một ứng dụng web và cần được bảo vệ như ứng dụng khác:

- TLS hợp lệ, không lưu credential ở URL hoặc log.
- Chống session hijacking và quản lý thời hạn phiên.
- Xác thực/ủy quyền chặt với tài khoản sponsor, admin và API cấp voucher.
- Rate limiting, chống lạm dụng form và quan sát lỗi.
- Không công khai hệ thống quản trị controller thông qua portal.
- Kiểm soát tích hợp danh tính/SSO nếu được sử dụng.
- Chỉ thu thập dữ liệu khách thực sự cần, công bố mục đích sử dụng và thời gian lưu.

**Chấp nhận điều khoản sử dụng không tự là bước xác thực danh tính**, và một voucher hợp lệ không chứng minh thiết bị đã được kiểm tra bảo mật.

## 8. DHCP, DNS và IPv6 trong mạng khách

### 8.1. DHCPv4 và quản lý pool

Thiết bị khách cần nhận IP, subnet mask, gateway và DNS phù hợp với vùng GUEST. Nếu dùng DHCP relay tới server tập trung, hãy kiểm tra **relay, scope, phân đoạn VLAN, policy DHCP snooping** và đường cho phép UDP cần thiết.

Ví dụ mô tả scope trong lab:

~~~text
Guest subnet:     192.0.2.0/24
Gateway:          192.0.2.1
Dynamic pool:     192.0.2.100 - 192.0.2.199
DHCP server:      Gateway hoặc relay đã phê duyệt
DNS service:      Resolver dành cho guest
Policy:           Chỉ Internet và các ngoại lệ hạ tầng
~~~

Pool có **100 địa chỉ** từ .100 đến .199. Để chọn lease duration, cần xem số client đồng thời, mức luân chuyển thiết bị và thời gian gián đoạn DHCP có thể chấp nhận. Lease quá dài có thể làm hết địa chỉ trong sự kiện đông khách; lease quá ngắn gây renewal thường xuyên và tăng rủi ro khi relay/server mất liên lạc.

Không suy ra “client có DHCPACK” là đã có Internet: captive portal, DNS, route, firewall hoặc upstream có thể vẫn chặn.

### 8.2. DNS dành cho khách

DNS resolver dùng cho guest cần được xác định rõ:

1. Client được phép truy vấn những resolver nào?
2. Resolver có vô tình tiết lộ vùng DNS nội bộ hoặc tên máy nhạy cảm không?
3. Chính sách DNS filtering/monitoring (nếu có) được áp dụng tại resolver hay gateway?
4. Nếu dùng captive portal, client có phân giải được portal trước khi đăng nhập không?
5. Nếu client dùng **DNS over HTTPS (DoH)** hoặc **DNS over TLS (DoT)**, hệ thống có thực sự kiểm soát/quan sát được như dự kiến không?

**Chặn UDP/TCP 53 đến resolver không được duyệt không bảo đảm chặn mọi DNS mã hóa**: DoH dùng HTTPS và có thể không được phát hiện chỉ dựa trên port. Không đưa ra lời hứa lọc DNS tuyệt đối nếu kiến trúc không có cơ chế và quyền thực thi phù hợp.

Trong mạng doanh nghiệp, có thể chọn resolver riêng cho guest để tránh lộ internal split-horizon zone. Không cho rằng resolver chỉ phục vụ guest là an toàn nếu nó vẫn có thể trả lời các bản ghi nội bộ nhạy cảm.

### 8.3. Bảo vệ DHCP và ARP ở lớp truy cập

**Rogue DHCP server** có thể gửi gateway/DNS không hợp lệ, làm khách mất kết nối hoặc chuyển hướng traffic. **DHCP starvation** có thể khiến pool cạn nếu thiết bị gửi nhiều yêu cầu với những client identifier khác nhau.

Các tính năng như **DHCP snooping**, giới hạn lưu lượng DHCP trên access port, **Dynamic ARP Inspection (DAI)** và **IP Source Guard** có thể hỗ trợ nếu nền tảng triển khai đúng. Phải cấu hình cổng trusted của AP/controller/relay phù hợp; một cấu hình snooping không đúng có thể chặn toàn bộ DHCP hợp lệ.

Không nên giả định mọi AP hỗ trợ đầy đủ các tính năng của switch truy cập doanh nghiệp hoặc rằng DHCP snooping có hiệu lực với mọi luồng khi Wi-Fi được tunnel về controller.

### 8.4. IPv6: Không bỏ quên một con đường truy cập

Với **dual-stack**, khách có thể có IPv4 đồng thời với một hoặc nhiều IPv6 address. IPv6 có thể được cấu hình qua **Router Advertisement (RA), SLAAC** và/hoặc DHCPv6 theo thiết kế. Chính sách chỉ chặn CORP qua IPv4 **không đủ** nếu còn route IPv6 đến mạng nội bộ.

Cần kiểm tra:

- Guest có nhận đúng IPv6 prefix, default router và DNS không?
- IPv6 firewall có chặn guest → CORP/MGMT và những peer không được phép không?
- Có **rogue RA/DHCPv6** trên WLAN không và hạ tầng có Guard tương ứng không?
- **ICMPv6 Neighbor Discovery và Path MTU Discovery** có được cho phép đúng chức năng không?
- Hệ thống phát hành địa chỉ IPv6 công khai cho guest có áp dụng chính sách inbound/outbound như thiết kế không?
- Mọi kiểm thử allow/deny đã được chạy trên cả IPv4 và IPv6 chưa?

**Không mặc định dùng NAT66 để thay thế firewall IPv6.** IPv6 có thể cung cấp địa chỉ global cho client, nhưng default deny ingress, giới hạn kết nối nội bộ và các rule egress vẫn cần được thiết kế. Nếu tổ chức **không hỗ trợ IPv6**, hãy quản trị nhất quán RA, route và cấu hình client, tránh giả định “không có IPv6 trong DHCPv4” nghĩa là IPv6 không hoạt động.

### 8.5. Gateway và NAT

Với IPv4, guest subnet có thể được chuyển qua **source NAT (SNAT/PAT)** tại gateway để truy cập Internet. Khi đó dịch vụ phía ngoài thường thấy IP công cộng của gateway, không phải IP private từng client. Điều này ảnh hưởng đến điều tra và rate limit theo nguồn.

NAT **không phải lớp phân đoạn đầy đủ**: phải có firewall policy chặn các đích nội bộ và kết nối mới từ WAN theo thiết kế. Nếu gateway dùng nhiều đường WAN, VPN hoặc route xuyên site, cần kiểm tra không có đường guest → internal bypass qua route khác.

## 9. Chính sách truy cập: Giới hạn theo đúng nhu cầu

### 9.1. Ví dụ chính sách theo ý định

~~~text
ZONE GUEST:
  allow DHCP to approved DHCP service / relay
  allow DNS to approved guest resolvers
  allow HTTPS to approved captive portal/bootstrap endpoints
  deny  GUEST -> CORP subnets
  deny  GUEST -> MGMT subnets and network-device management
  deny  GUEST -> protected IOT/OT/STORAGE/VPN subnets
  deny  direct guest-peer communication if isolation policy requires
  allow GUEST -> Internet according to approved egress rules
  deny  other unsolicited inbound / inter-zone connections

Notes:
  * IPv4 and IPv6 must both be evaluated.
  * DHCP/ARP/RA/ND have distinct L2/L3 handling.
  * Stateful reply traffic follows the firewall platform's semantics.
  * This is vendor-neutral policy intent, not executable configuration.
~~~

**Không copy thứ tự dòng trên vào một firewall bất kỳ.** Một số nền tảng ưu tiên rule đầu tiên khớp, một số dùng zone policy hoặc ACL có semantics riêng; những gói đi tới chính gateway khác gói được forward qua gateway. Cần xây rule thực tế theo đường đi và kiểm tra tác động.

### 9.2. Không mở mạng nội bộ chỉ để khách “có Internet”

Một thiết kế rủi ro là:

~~~text
ALLOW GUEST -> ANY ANY
DENY  GUEST -> CORP (ở sau rule cho phép toàn bộ)
~~~

Nếu firewall sử dụng **first-match**, rule ALLOW quá rộng có thể làm DENY phía dưới không bao giờ khớp. Cần xét cả các **network management interfaces**, dải private/routed của chi nhánh, địa chỉ service đặc biệt, IPv6 và đường VPN/hybrid chứ không chỉ một subnet CORP.

Ngoại lệ cần được quản lý theo **source, destination, protocol, owner, lý do và thời hạn**. Khi khách cần một hệ thống nội bộ, có thể cấp quyền qua dịch vụ trung gian/portal hoặc một profile mạng đối tác riêng thay vì mở trực tiếp guest zone.

### 9.3. Client isolation và firewall là hai kiểm soát bổ sung

Một firewall gateway có thể chặn GUEST → CORP nhưng **không thấy** guest A → guest B nếu chúng cùng subnet và trao đổi trực tiếp ở L2. Ngược lại, client isolation có thể ngăn A ↔ B nhưng **không tự chặn** guest → CORP qua gateway nếu routing được mở.

Phải kiểm tra **cả hai đường**. Thậm chí khi các station cùng AP bị cô lập, khả năng đi vòng qua controller, AP khác, subnet khác hoặc thiết bị dây trong cùng VLAN vẫn cần được đánh giá.

### 9.4. Chính sách cho phép guest kết nối VPN cá nhân

Khách có thể cần dùng VPN hợp pháp của cơ quan họ để làm việc. Nếu mạng khách hạn chế giao thức/cổng, một số VPN có thể không kết nối hoặc tự chuyển chế độ. Quyết định cho phép hay từ chối VPN nên xuất phát từ **chính sách sử dụng mạng khách** và yêu cầu nghiệp vụ, không phải giả định rằng mọi VPN traffic là độc hại.

Chấp nhận VPN của khách không có nghĩa tổ chức quản lý được nội dung đã mã hóa trong tunnel. Kiểm soát vẫn cần tập trung vào **phân đoạn nguồn, giới hạn tài nguyên, truy cập nội bộ bị cấm và telemetry metadata phù hợp**.

## 10. Duy trì hiệu năng, tính sẵn sàng và công bằng tài nguyên

Mạng khách không chỉ phải an toàn mà còn cần có **kết nối đủ ổn định** cho người dùng hợp lệ. Một chính sách quá chặt có thể cản trở công việc; chính sách quá lỏng có thể làm ảnh hưởng mạng doanh nghiệp thông qua băng thông, CPU gateway hoặc tài nguyên AP dùng chung.

### 10.1. Airtime và RF không đồng nghĩa băng thông WAN

Wi-Fi dùng **tài nguyên vô tuyến chia sẻ**. Nhiều thiết bị trong vùng phủ sóng có thể tranh chấp airtime ngay cả khi guest và CORP đã được tách VLAN.

| Tài nguyên | Rủi ro | Hướng bảo vệ |
| --- | --- | --- |
| **Airtime** | Client yếu hoặc quá đông khiến thời gian chiếm kênh tăng | Thiết kế mật độ AP, kênh, công suất, band steering/airtime fairness theo khả năng |
| **WAN bandwidth** | Guest streaming/upload làm nghẽn đường lên của doanh nghiệp | Giới hạn băng thông/traffic shaping và ưu tiên ứng dụng quan trọng |
| **DHCP pool** | Quá nhiều thiết bị mới, lease không được tái sử dụng | Pool sizing, lease duration và cảnh báo cấp phát |
| **DNS resolver** | Quá nhiều truy vấn hoặc DNS lỗi | Resolver có năng lực, giới hạn lạm dụng, giám sát độ trễ |
| **Controller/gateway** | Quá tải session, NAT, portal, TLS | Capacity planning, dự phòng, giới hạn kết nối và quan sát |
| **Captive portal** | Sự cố portal khiến khách không hoàn tất đăng nhập | Health check, phương án xử lý downtime và hỗ trợ người dùng |

Không có một ngưỡng **Mbps/client** phù hợp cho mọi tổ chức. Thiết lập phải dựa trên số client, nhu cầu hội họp/video, uplink, mức ưu tiên của mạng nội bộ và khả năng AP/controller. **Giảm băng thông Internet không tự giải quyết nghẽn airtime RF**, và ngược lại.

### 10.2. Rate limit và quota

Có thể áp dụng giới hạn theo SSID, nhóm client, tài khoản/voucher hoặc toàn guest zone:

- **Băng thông tối đa hoặc shaping:** tránh một client chiếm đường uplink.
- **Session/concurrent connection limits:** bảo vệ state table hoặc gateway khi cần.
- **DNS/HTTP rate limits:** giảm một số dạng lạm dụng hoặc retry storm.
- **Quota theo phiên/khách:** giới hạn thời gian hoặc dung lượng nếu chính sách yêu cầu.
- **Ưu tiên lưu lượng:** giữ mức dịch vụ cho thoại/họp trực tuyến hoặc mạng doanh nghiệp theo thiết kế.

Không áp dụng rate limit theo **IP công cộng của một NAT gateway** khi ý định là giới hạn từng khách: làm vậy có thể gộp mọi người vào một bucket. Tương tự, chỉ dựa vào MAC không đủ nếu client randomize hoặc thay địa chỉ.

### 10.3. Tăng số SSID không phải cách duy nhất tăng bảo mật

Nhiều SSID trên cùng radio có thể tăng overhead quản lý và phức tạp cấu hình. Một số nền tảng hỗ trợ gắn policy/VLAN theo nhóm người dùng hoặc profile thay vì tạo SSID riêng cho từng đối tác. Chọn phương án phải xét **tính tương thích, khả năng vận hành, phân vùng thực tế và tài nguyên RF**.

Vùng tần số 2,4 GHz, 5 GHz và 6 GHz có đặc tính phủ sóng/thiết bị tương thích khác nhau; tên băng tần **không tự quyết định** mức tin cậy của client. Các yêu cầu an toàn riêng của Wi-Fi 6E/7 hoặc WPA3 trong một số chế độ phải được kiểm tra theo thiết bị và chuẩn hỗ trợ.

### 10.4. Roaming và chuyển AP

Khi khách di chuyển giữa AP:

1. SSID/security profile có nhất quán không?
2. Client có giữ IP/lease và captive-portal session theo thiết kế không?
3. Việc chuyển AP hoặc controller có làm mất client isolation hoặc gắn VLAN sai không?
4. Nếu sang site/segment mới, portal có yêu cầu đăng nhập lại đúng chính sách không?
5. Có điểm lộ traffic tạm thời trong chuyển đổi trạng thái auth/policy không?

**Roaming thành công về kết nối không chứng minh phân đoạn vẫn đúng.** Cần kiểm tra rule sau khi client chuyển AP và khi tái kết nối từ trạng thái sleep.

## 11. Triển khai guest network theo từng giai đoạn

### Bước 1 — Xác định chính sách sử dụng

Chốt ai được dùng mạng khách, mục đích, dịch vụ được phép (Internet, VPN của đối tác, in/trình chiếu công cộng), thời hạn tài khoản và yêu cầu pháp lý/quy định nội bộ về thông báo, lưu log, quyền riêng tư.

Đừng tự động cấp quyền CORP chỉ vì khách là đối tác thường xuyên. Nếu cần làm việc với hệ thống nội bộ, thiết kế **profile đối tác** hoặc cơ chế truy cập ứng dụng có xác thực và phân quyền riêng.

### Bước 2 — Kiểm kê và threat model

Ghi AP, switch, controller, router/firewall, DHCP/DNS, captive portal, RADIUS nếu dùng, đường WAN và các subnet IPv4/IPv6. Xác định ranh giới tin cậy, đường có thể bypass, client cùng AP/khác AP và những tài nguyên quản trị cần bảo vệ.

### Bước 3 — Xây vùng guest độc lập

Thiết lập SSID và mapping vào VLAN/VRF hoặc tunnel zone theo kiến trúc. Bảo đảm DHCP scope, default gateway và DNS chỉ tới dịch vụ dành cho guest; kiểm tra route giữa các vùng và chính sách client isolation.

Nếu các AP chạy ở nhiều chi nhánh, quyết định giữa **local breakout** và **central tunnel**:

- **Local breakout:** lưu lượng khách ra Internet tại site; cần chính sách firewall/DNS/giám sát nhất quán trên từng site.
- **Central tunnel:** lưu lượng đi qua controller/gateway trung tâm; thuận tiện tập trung chính sách nhưng ảnh hưởng độ trễ, dung lượng tunnel và phụ thuộc kết nối site–center.

Không mặc định một mô hình luôn tốt hơn: cần xét topology, tài nguyên, tính sẵn sàng và lưu lượng thực tế.

### Bước 4 — Chọn Wi-Fi security và onboarding

Lựa chọn Open/OWE/WPA2/WPA3/Enterprise theo chính sách và client được hỗ trợ; thiết lập PMF phù hợp, vô hiệu hóa cơ chế không an toàn hoặc không cần thiết, quản trị mật khẩu/voucher và portal HTTPS nếu sử dụng.

Kiểm tra các hệ điều hành phổ biến trong phạm vi được phép. Nếu dùng một **transition mode** để hỗ trợ client cũ, hãy đánh giá tác động bảo mật và kế hoạch thay thế thiết bị không tương thích thay vì giữ cấu hình yếu vô thời hạn.

### Bước 5 — Thực thi policy L2, L3 và ứng dụng

Áp dụng các điều kiện:

- Guest → CORP/MGMT/IoT/OT/STORAGE: deny mặc định trừ ngoại lệ rõ.
- Guest → Internet: allow theo egress policy, chặn ingress ngoài ý muốn.
- Guest ↔ Guest: cách ly theo yêu cầu; kiểm tra cả cross-AP và wired peer.
- DHCP/DNS/RA/ND/portal: cho phép chính xác các luồng cần thiết.
- IPv6: thực thi tương đương IPv4, không bỏ qua firewall/guard.
- Quản trị WLAN: chỉ từ vùng quản trị/định danh được phê duyệt.

### Bước 6 — Kiểm thử lab trước khi mở rộng

Kiểm tra **allow và deny** từ hai thiết bị khách, nhiều AP, các hệ điều hành và cả IPv4/IPv6. Đối chiếu thông tin route, DHCP, DNS, portal và log firewall. Không dùng chỉ một phép ping làm bằng chứng cho toàn bộ chính sách.

### Bước 7 — Theo dõi vận hành và lập rollback

Bật giám sát cấp phát IP, khả năng tới DNS, tỷ lệ hoàn tất portal, số client, lỗi xác thực, băng thông/airtime, sự kiện chặn sai và trạng thái controller/AP. Có phương án phục hồi SSID, VLAN mapping, firewall/portal policy và nâng cấp phần mềm.

### Bước 8 — Rà soát định kỳ

Thu hồi voucher quá hạn, rà soát ngoại lệ cho máy in/portal, xác minh site mới dùng cùng chính sách, cập nhật danh sách AP hợp lệ và kiểm tra các rule không còn chủ sở hữu. Khi thay WAN, DNS, controller hoặc giải pháp bảo mật, phải chạy lại ma trận kiểm thử.

## 12. Kiểm thử guest network trong phòng lab được phép

**Thiết lập đề xuất:** hai thiết bị khách A/B; một hoặc hai AP của lab; vùng guest và các endpoint kiểm thử đại diện cho CORP/MGMT (không có dữ liệu sản xuất); một gateway/firewall có log. Tất cả nguồn, đích và phép thử phải nằm trong phạm vi bạn được phép quản trị.

### 12.1. Ma trận kiểm chứng

| Trường hợp | Nguồn → đích | Kỳ vọng |
| --- | --- | --- |
| Lấy IPv4 | Guest A → DHCP guest | Nhận IP đúng pool, gateway, DNS |
| Phân giải Internet | Guest A → DNS guest | Phân giải tên công cộng hợp lệ |
| Kết nối Internet | Guest A → endpoint công cộng được phép | Kết nối theo chính sách, TLS hợp lệ |
| Portal trước đăng nhập | Guest A chưa auth → portal | Chỉ có những đích bootstrap cần thiết |
| Portal sau đăng nhập | Guest A đã auth → Internet | Có quyền trong thời hạn/phiên được cấp |
| Cách ly mạng nội bộ | Guest A → CORP lab | **Không được phép** |
| Chặn quản trị | Guest A → MGMT lab | **Không được phép** |
| Cùng AP | Guest A → Guest B trên cùng AP | Bị chặn nếu bật guest isolation |
| Khác AP | Guest A → Guest B ở AP khác | Bị chặn nếu chính sách yêu cầu cách ly toàn guest |
| Wired peer | Guest A → endpoint cắm dây cùng guest VLAN | Bị chặn nếu policy yêu cầu cách ly peer |
| Roaming | Guest A chuyển AP | Vẫn giữ policy và đúng vùng |
| IPv6 | Guest A → CORP/MGMT qua IPv6 | **Không được phép** |
| DHCP/RA trái phép | Hệ thống kiểm thử được kiểm soát | Phát hiện/chặn theo cơ chế guard đã triển khai |
| Quota/timeout | Voucher/hạn mức lab | Hết hạn và gia hạn đúng hành vi đã công bố |

**Không cần thực hiện deauthentication flood, brute force, quét diện rộng hoặc dựng evil twin trên mạng người khác** để chứng minh một guest policy. Những kiểm thử RF/tấn công chuyên sâu cần lab cô lập, phê duyệt và kế hoạch riêng.

### 12.2. Kiểm tra cấu hình IP và route của client

Trên Windows (chỉ đọc):

~~~powershell
# Xem SSID/adaptor liên quan, DHCP, DNS, gateway.
netsh wlan show interfaces
ipconfig /all

# Xem bảng định tuyến IPv4/IPv6.
route print

# Tra DNS qua resolver đang được cấu hình.
nslookup example.com
~~~

Trên Linux (chỉ đọc; một số lệnh phụ thuộc NetworkManager/systemd-resolved):

~~~bash
# Xem tên mạng Wi-Fi đang kết nối (nếu dùng NetworkManager).
nmcli -t -f ACTIVE,SSID dev wifi

# Xem IPv4, IPv6 và đường định tuyến.
ip -4 addr show
ip -4 route
ip -6 addr show
ip -6 route

# Kiểm tra cấu hình resolver nếu có systemd-resolved.
resolvectl status
~~~

Các lệnh chỉ cho biết **cấu hình đang thấy tại client**; không chứng minh firewall đã áp dụng đúng. Để xác minh deny, cần **các endpoint lab được chỉ định** và quan sát log enforcement ở gateway, AP/controller hoặc host tương ứng.

### 12.3. Kiểm tra luồng ứng dụng

~~~bash
# Xác minh HTTPS tới trang kiểm thử công khai được phê duyệt.
curl -I --max-time 10 https://example.com/

# Kiểm tra hostname của portal trong lab đã cấu hình DNS.
# URL chỉ là ví dụ; phải có portal thật trong môi trường lab.
curl -I --max-time 10 https://portal.lab.test/
~~~

Nếu gặp lỗi TLS, **không thêm tùy chọn bỏ qua kiểm tra chứng chỉ** để làm phép thử “thành công”. Cần kiểm tra portal hostname, chứng chỉ và chuỗi tin cậy đúng theo thiết kế.

Một lệnh kết nối bị timeout **chưa chắc** chứng minh firewall đã chặn: đích có thể offline hoặc route không tồn tại. Nên xác minh máy lab đích đang lắng nghe, có đường truy cập từ nguồn được phép và có **log deny** hoặc bằng chứng chính sách từ điểm thực thi. Ngược lại, một HTTP response thành công từ Internet không chứng minh guest không đi được vào CORP.

### 12.4. Kiểm thử trước/sau captive portal

Chỉ sử dụng **tài khoản/voucher thử nghiệm**:

1. Kết nối SSID với client chưa được cấp quyền portal.
2. Ghi IP, DNS, default route, loại mã hóa Wi-Fi và trạng thái IPv6.
3. Kiểm tra DNS/portal bootstrap hoạt động; một đích Internet không thuộc walled garden chưa được truy cập.
4. Hoàn tất xác thực/chấp nhận điều khoản theo chính sách.
5. Kiểm tra Internet được cấp nhưng CORP/MGMT vẫn bị deny.
6. Thử logout/hết hạn voucher, roaming và kết nối lại để xác minh quyền được thu hồi đúng.

**Trạng thái portal cho phép truy cập Internet không được làm mất chính sách phân đoạn.** Nếu hệ thống sau khi “đăng nhập” chuyển client vào VLAN nội bộ không mong muốn, đó là sai cấu hình nghiêm trọng dù người dùng thấy Internet hoạt động bình thường.

## 13. Giám sát guest network và quyền riêng tư

### 13.1. Số liệu kỹ thuật cần quan sát

| Dữ liệu | Mục đích | Điểm thận trọng |
| --- | --- | --- |
| Số client kết nối theo AP/SSID/site | Phát hiện quá tải và xu hướng nhu cầu | MAC có thể randomize, không suy ra số người tuyệt đối |
| Authentication/association failures | Chẩn đoán không kết nối được Wi-Fi | Không quy mọi lỗi là tấn công |
| DHCP pool và lease failures | Phát hiện cạn IP hoặc relay lỗi | Active lease chưa chắc bằng client đang online |
| DNS success/latency | Kiểm tra trải nghiệm sau kết nối | DNS mã hóa có thể làm giảm khả năng quan sát |
| Portal completion/expiry/errors | Tìm false blocking, lỗi voucher/SSO | Chỉ thu thập dữ liệu định danh cần thiết |
| Guest → CORP/MGMT denies | Xác minh phân đoạn và tìm hành vi bất thường | Deny có thể do lỗi cấu hình/phần mềm, không tự là tấn công |
| AP airtime, channel utilization, retry | Phân tích chất lượng RF | WAN tốt không chứng minh RF tốt |
| Gateway CPU/session/throughput | Phát hiện nghẽn firewall/NAT | Cần so với baseline và sự kiện triển khai |
| Rogue AP observations | Phát hiện AP có tên/tín hiệu bất thường | SSID trùng tên không tự chứng minh thiết bị độc hại |
| Chính sách/credential changes | Audit vòng đời và drift | Bảo vệ log, hạn chế quyền sửa |

### 13.2. Dùng log một cách có trách nhiệm

Không nên ghi lại **mật khẩu Wi-Fi, token portal, Authorization header hoặc nội dung nhạy cảm** vào nhật ký. Những bản ghi như địa chỉ MAC, IP, thời điểm kết nối, voucher hoặc tài khoản sponsor có thể liên quan tới cá nhân; cần giới hạn quyền truy cập, mục đích sử dụng, thời hạn lưu và chính sách bảo vệ dữ liệu.

Một bản ghi giả lập:

~~~text
timestamp=2026-11-28T11:00:00Z
site=lab-site-01 ssid=Guest-Lab
client_id=anon-guest-003
src_zone=GUEST dst_zone=MGMT
src_ip=192.0.2.110 dst_ip=203.0.113.10
protocol=tcp dst_port=443
action=DENY policy=guest-to-management-deny
~~~

Log này chứng minh **một lần kiểm soát** tại điểm thực thi. Nó **không tự khẳng định** client đang tấn công: có thể là ứng dụng dò tìm thiết bị, thiết lập cũ hoặc hoạt động thử đã được phép. Cần đối chiếu time, asset, rule, hành vi lặp lại và bối cảnh vận hành.

### 13.3. Giám sát thiết bị Wi-Fi trái phép

Khi hệ thống WIDS/WIPS hoặc WLAN controller báo rogue AP/SSID:

- Phân biệt **AP của hàng xóm** với AP cắm trái phép vào LAN của tổ chức.
- Đối chiếu BSSID, tín hiệu, vị trí, inventory, uplink switch nếu có.
- Không tự động kết luận trùng SSID là hành vi ác ý.
- Quy trình xử lý cần được phê duyệt; các biện pháp can thiệp RF có thể chịu hạn chế kỹ thuật/pháp lý.
- Không triển khai phản ứng gây nhiễu/deauthentication hàng loạt ngoài phòng lab cô lập và phạm vi cho phép.

## 14. Chẩn đoán sự cố guest network

~~~mermaid
flowchart TD
    A[Khách không dùng được Internet] --> B{Đã kết nối và có Wi-Fi security phù hợp?}
    B -->|Không| C[Kiểm tra SSID, mật khẩu, OWE/WPA, PMF, RF]
    B -->|Có| D{Client nhận IP, DNS, gateway đúng?}
    D -->|Không| E[Kiểm tra VLAN mapping, DHCP, relay, snooping, RA]
    D -->|Có| F{Portal/permission đã hoàn tất?}
    F -->|Không| G[Kiểm tra portal HTTPS, walled garden, voucher, DNS]
    F -->|Có| H{Route, firewall, NAT, WAN và DNS đúng?}
    H -->|Không| I[Đối chiếu IPv4/IPv6, log deny, đường đi]
    H -->|Có| J[Kiểm tra TLS, ứng dụng, băng thông và upstream]
~~~

### 14.1. Thấy SSID nhưng không kết nối được

**Nguyên nhân:** sai WPA2/WPA3 password, incompatibility với SAE/OWE/PMF, chính sách client limit, AP quá tải hoặc chất lượng RF kém. Đừng mở toàn mạng thành Open chỉ để tránh lỗi tương thích; hãy xác định client và profile bảo mật trước.

### 14.2. Kết nối Wi-Fi được nhưng không có IPv4

**Nguyên nhân:** guest SSID bị ánh xạ VLAN sai ở AP/switch, DHCP scope cạn, relay lỗi hoặc DHCP snooping chặn phản hồi hợp lệ. Kiểm tra lease obtained/expiry, DHCP server thực tế và log ở controller/gateway; không dùng lệnh làm mất IP của máy đang điều khiển từ xa nếu chưa có phương án khôi phục.

### 14.3. Có IP nhưng portal không hiện

**Nguyên nhân:** DNS portal không phân giải được; walled garden chặn tài nguyên/certificate validation; client không hỗ trợ cách portal được phát hiện; portal bị lỗi; hoặc người dùng đang truy cập HTTPS mà gateway cố chuyển hướng không hợp lệ.

**Cách xử lý:** kiểm tra hostname và chứng chỉ portal, trạng thái portal session, DNS/gateway và phương thức discovery được client hỗ trợ. Không hướng dẫn tắt kiểm tra TLS để đăng nhập.

### 14.4. Portal xong nhưng Internet không hoạt động

**Nguyên nhân:** chính sách sau xác thực chưa có hiệu lực, NAT hoặc route WAN sai, DNS bị chặn, firewall rule thứ tự không đúng hoặc tài khoản bị áp quota. Kiểm tra khác nhau giữa IPv4 và IPv6, xác định liệu request tới origin có qua đúng firewall/WAF hay không.

### 14.5. Khách vẫn truy cập được thiết bị nội bộ

Đây là **sự cố phân đoạn ưu tiên cao**. Kiểm tra guest-to-VLAN mapping, route/VRF leak, NAT, các policy allow quá rộng, ngoại lệ cũ, IPv6, split-tunnel/VPN và đường guest → internal qua thiết bị trung gian. Thực hiện thay đổi tại điểm có quyền quản trị và theo quy trình; không chỉ đổi tên SSID.

### 14.6. Client guest thấy hoặc truy cập client khác

Kiểm tra client isolation trên cùng AP, **cross-AP isolation**, L2 bridge tới switch, traffic multicast/discovery và các luồng đi vòng qua router hoặc thiết bị cắm dây. Phân biệt “thấy tên thiết bị” qua discovery với “truy cập được dịch vụ”: cả hai đều cần so với chính sách yêu cầu.

### 14.7. Lúc đông khách mạng quá chậm

So sánh **airtime/channel utilization, retries, số client/AP, RSSI/SNR**, WAN throughput, gateway CPU/session, DNS latency và portal failures. Chỉ tăng tốc độ Internet khi nghẽn nằm ở WAN; nếu RF đã quá tải, cần điều chỉnh AP/channel/công suất và phân phối client phù hợp.

## 15. Bài tập tình huống thiết kế

**Bối cảnh:** một văn phòng có hai tầng, một hệ thống WLAN controller, bốn AP và firewall ở gateway. Mạng nhân viên dùng vùng CORP, quản trị AP/controller ở MGMT. Khách tới họp cần Internet, họp video và đôi khi trình chiếu trên một thiết bị công cộng được quản lý. Tổ chức muốn hạn chế guest-to-guest, dùng một captive portal và hỗ trợ cả IPv4/IPv6.

Kế hoạch ban đầu của một kỹ thuật viên:

~~~text
SSID: Office-Guest
VLAN: 30, nhưng dùng chung gateway/router với CORP
Firewall: ALLOW GUEST -> ANY
Isolation: bật trên hai AP ở tầng 1, tắt ở tầng 2
Portal: mở HTTP, yêu cầu nhập mật khẩu email cá nhân
DNS: dùng resolver nội bộ của nhân viên
IPv6: không có rule; chỉ chặn IPv4 CORP
Device sharing: mở toàn bộ CORP để khách thấy màn hình họp
~~~

### 15.1. Đánh giá các vấn đề

| Vấn đề | Rủi ro | Cách sửa ở mức thiết kế |
| --- | --- | --- |
| Rule GUEST → ANY | Khách có thể đi vào CORP/MGMT và vùng khác | Ma trận allow/deny rõ ràng, chặn nội bộ trước egress Internet theo policy |
| Isolation không đồng nhất giữa AP | Cùng một SSID nhưng quyền peer thay đổi theo vị trí | Chính sách cách ly toàn site, thử cross-AP và wired peer |
| Portal dùng HTTP và yêu cầu mật khẩu email | Lộ thông tin nhạy cảm, dễ bị giả mạo | Portal HTTPS, xác thực/voucher phù hợp và tối thiểu dữ liệu |
| DNS chung với CORP | Nguy cơ lộ tên miền nội bộ và chính sách chưa phù hợp | Resolver guest riêng/segmented, kiểm soát zone trả lời |
| Không có IPv6 policy | Client có thể đi vào mạng IPv6 nội bộ | Firewall/RA/DHCPv6/ND policy tương ứng |
| Mở CORP để trình chiếu | Cấp quyền quá rộng ngoài nhu cầu | Shared guest service/gateway chỉ cho đích và giao thức được duyệt |
| Gateway dùng chung | Không nhất thiết sai nhưng dễ bị cấu hình route/policy quá rộng | Zone/interface/VRF rõ, chống bypass và kiểm tra đường đi |

### 15.2. Ma trận chính sách sau chỉnh sửa

| Luồng | Chính sách |
| --- | --- |
| Guest → Internet | Allow theo egress policy, NAT IPv4 nếu dùng |
| Guest → DHCP/DNS/portal guest | Allow đúng dịch vụ |
| Guest → CORP/MGMT | Deny mọi kết nối không có ngoại lệ được phê duyệt |
| Guest → client guest khác | Deny theo isolation policy L2/L3 |
| Guest → màn hình phòng họp công cộng | Allow chính xác dịch vụ được duyệt qua vùng shared hoặc proxy phù hợp |
| Guest → quản trị màn hình/AP | Deny |
| Guest → CORP/MGMT qua IPv6 | Deny như IPv4 |
| Internet → Guest không có phiên được phép | Deny inbound theo firewall policy |

### 15.3. Câu hỏi tự kiểm tra

1. Tại sao một SSID tên “Guest” không đủ chứng minh người dùng bị cách ly khỏi CORP?
2. VLAN riêng có giải quyết mọi đường guest-to-guest trong cùng VLAN không?
3. Khi có AP isolation trên một AP, tại sao vẫn phải thử từ hai thiết bị ở hai AP khác nhau?
4. OWE khác gì Open Wi-Fi và tại sao OWE không xác thực được danh tính hotspot?
5. Captive portal được dùng với Open Wi-Fi có tự mã hóa traffic vô tuyến không?
6. Vì sao phải xử lý HTTPS/certificate của portal đúng chuẩn thay vì yêu cầu bỏ qua cảnh báo trình duyệt?
7. Nếu IPv4 rule chặn CORP nhưng IPv6 đang được cấp, điều gì cần kiểm chứng?
8. Tại sao guest có thể cần DNS/DHCP trước khi được portal xác thực?
9. Khi một khách dùng VPN doanh nghiệp của họ, tại sao guest firewall vẫn cần chặn đường vào mạng nội bộ?
10. Nếu khách không mở được website, làm thế nào phân biệt lỗi DHCP, DNS, portal, WAN và firewall?
11. Tại sao portal log chứa MAC và thời gian chưa đủ để khẳng định danh tính một người?
12. Vì sao khi phòng họp đông người, WAN còn băng thông nhưng Wi-Fi vẫn chậm?

**Gợi ý:** (1) Cần mapping tới vùng mạng và rule thật. (2) Không; cần L2/client isolation và bảo vệ wired peer. (3) Cross-AP có thể đi qua bridge/controller không cùng cơ chế. (4) OWE mã hóa liên kết mà không xác thực chủ AP. (5) Không. (6) TLS cần đúng tên miền và chứng chỉ, không MITM portal. (7) Đường IPv6/RA/DHCPv6 và firewall dual-stack. (8) Đây là dịch vụ bootstrap. (9) Tunnel cá nhân không cấp quyền vào CORP. (10) Kiểm tra từng lớp và log, không chỉ ping. (11) MAC có thể randomize hoặc giả mạo. (12) RF airtime và contention có thể nghẽn trước WAN.

## 16. Checklist nghiệm thu triển khai guest network

| Hạng mục | Câu hỏi nghiệm thu | Bằng chứng phù hợp |
| --- | --- | --- |
| Segmentation | Guest không có đường truy cập CORP/MGMT? | Kiểm thử deny và log từ đúng nguồn |
| Mapping | Mọi AP/site gán SSID vào đúng vùng? | Cấu hình controller, DHCP scope và route |
| Client isolation | Peer cùng AP, khác AP và wired peer được xử lý đúng? | Ma trận kiểm thử L2/L3 |
| Wi-Fi security | OWE/WPA2/WPA3/PMF đúng client và policy? | Cấu hình profile, kiểm thử client |
| Portal | HTTPS, voucher/session, walled garden hoạt động? | Kiểm thử trước/sau auth và expiry |
| DHCP/DNS | Guest nhận đúng IP/gateway/DNS, không lộ internal DNS? | Client config, query, DHCP/DNS logs |
| IPv6 | Không có đường bypass qua IPv6? | Kiểm thử route/deny IPv6, RA/ND |
| Performance | Airtime, WAN, DNS, gateway có mức dự phòng? | Baseline và theo dõi peak |
| Monitoring | Có log rule, DHCP, portal, sự kiện rogue AP? | Dashboard và cảnh báo có owner |
| Privacy | Log/voucher tối thiểu, retention và quyền truy cập rõ? | Chính sách và audit thực tế |
| Resilience | Mất AP/controller/portal/DNS xử lý thế nào? | Runbook và thử nghiệm phục hồi |
| Change management | Có rollback và rà soát ngoại lệ? | Ticket, kết quả kiểm thử và lịch audit |

**Nghiệm thu phải dựa trên hành vi quan sát được**, không chỉ ảnh chụp trạng thái “Enabled” của một tính năng. Đặc biệt cần kết hợp kiểm tra **đường được phép** (Internet, DNS, portal) và **đường bị cấm** (CORP, MGMT, guest peer).

## 17. Tổng kết

**Guest network** là vùng truy cập dành cho các thiết bị có mức tin cậy thấp hơn mạng doanh nghiệp. Muốn an toàn cần thiết kế nhất quán từ **Wi-Fi security**, **SSID-to-zone mapping**, **client isolation**, **firewall/ACL**, **DHCP/DNS/IPv6**, **captive portal** đến **khả năng giám sát và thu hồi quyền**.

Những điểm cần nhớ:

- **Tên SSID không phải chính sách phân đoạn**; phải buộc lưu lượng đi qua đúng điểm kiểm soát.
- **Client isolation** và **firewall L3/L4** bổ sung cho nhau, không thay thế nhau.
- **Captive portal** không tự mã hóa liên kết vô tuyến; Open/OWE/WPA2/WPA3 có mô hình bảo vệ khác nhau.
- **IPv6, DNS, DHCP, management plane và các dịch vụ shared** phải được xét trong threat model để tránh bypass hoặc chặn nhầm.
- **Giới hạn băng thông, airtime, session và lease** cần bảo đảm trải nghiệm của khách mà không ảnh hưởng tài nguyên quan trọng.
- Độ tin cậy của thiết kế phải được xác minh bằng **allow/deny tests, log, kiểm tra roaming và rà soát thay đổi định kỳ**.

Trong **SECURITY_NETWORK_SECURITY**, mạng khách thể hiện nguyên tắc phòng vệ nhiều lớp: tách vùng, cấp quyền tối thiểu, bảo vệ kết nối, giám sát bất thường và vận hành có khả năng phục hồi. Khi cần tiếp cận hệ thống nội bộ, hãy dùng kiến trúc truy cập được xác thực và giới hạn theo mục đích thay vì mở rộng quyền của toàn bộ guest zone.

### Tài liệu tham khảo

- **NIST SP 800-153 — Guidelines for Securing Wireless Local Area Networks (WLANs):** quản trị kiến trúc và an toàn WLAN.
- **Wi-Fi Alliance — WPA3 và Wi-Fi CERTIFIED Enhanced Open:** đặc tính bảo mật WPA3 và OWE.
- **IEEE 802.11 / 802.11w:** cơ chế truy cập Wi-Fi và bảo vệ management frames trong các profile phù hợp.
- **RFC 8908 — Captive Portal API:** thông tin trạng thái captive portal theo API.
- **RFC 8910 — Captive-Portal Identification in DHCP and Router Advertisements:** cơ chế giới thiệu thông tin portal tới client.
- **RFC 2131 — Dynamic Host Configuration Protocol:** cấp phát DHCPv4 và vòng đời lease.
- **RFC 4861 / RFC 4862 — IPv6 Neighbor Discovery / Stateless Address Autoconfiguration:** RA, ND và SLAAC.
- **RFC 5737 / RFC 3849 — Documentation Address Prefixes:** dải IPv4/IPv6 dành cho tài liệu và lab.
