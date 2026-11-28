# DHCP snooping

**DHCP snooping** là một tính năng bảo mật thường được triển khai trên switch lớp 2 hoặc thiết bị chuyển mạch có hỗ trợ, nhằm **kiểm tra và kiểm soát các thông điệp DHCP đi qua những cổng được chỉ định**. Mục đích quan trọng nhất là ngăn một thiết bị ở cổng người dùng đóng vai **DHCP server trái phép** (*rogue DHCP server*) và cấp phát thông tin cấu hình mạng sai cho những máy khác.

Ngoài việc lọc thông điệp DHCP, nhiều triển khai DHCP snooping còn xây dựng **bảng ánh xạ IP–MAC–VLAN–cổng–thời hạn thuê địa chỉ** (*DHCP snooping binding table*). Bảng này có thể phục vụ các kiểm soát khác như **Dynamic ARP Inspection (DAI)** và **IP Source Guard**, giúp hạn chế một số hành vi giả mạo địa chỉ và di chuyển ngang trong mạng nội bộ.

Trong module **SECURITY_NETWORK_SECURITY**, DHCP snooping đóng vai trò bảo vệ **ranh giới truy cập của thiết bị đầu cuối**. Nó bổ sung cho phân đoạn VLAN, firewall, VPN, IDS/IPS, xác thực kết nối, bảo vệ DNS, Wi-Fi và chính sách cloud. Tuy nhiên, **DHCP snooping không mã hóa DHCP, không xác thực mật mã máy chủ DHCP và không thay thế việc bảo vệ chính hạ tầng cấp phát địa chỉ**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích DHCPv4 cấp phát địa chỉ qua quá trình **Discover–Offer–Request–ACK (DORA)**.
2. Mô tả vì sao rogue DHCP có thể làm mất kết nối hoặc điều hướng lưu lượng qua gateway/DNS ngoài ý muốn.
3. Phân biệt **trusted port** và **untrusted port** trong DHCP snooping, tránh nhầm chúng với VLAN hoặc trạng thái xác thực người dùng.
4. Giải thích cách switch kiểm tra thông điệp DHCP và tạo, cập nhật, xóa binding.
5. Hiểu liên hệ giữa DHCP snooping, **DHCP relay**, **Option 82**, **DAI** và **IP Source Guard**.
6. Thiết kế sơ đồ cổng/VLAN cho mạng nhân viên, khách và thiết bị IoT, xác định đúng đường tới DHCP server.
7. Xây dựng chính sách, log, phép kiểm thử và kế hoạch rollback không làm gián đoạn việc cấp phát IP.
8. Nhận biết giới hạn với **IP tĩnh, DHCPv6, IPv6 Router Advertisement, mạng ảo, Wi-Fi và cloud**.

## 2. Ôn lại DHCPv4 trước khi nói về bảo mật

**Dynamic Host Configuration Protocol (DHCP)** là giao thức hỗ trợ tự động cấp thông số mạng cho client. Với DHCPv4, dữ liệu thường gồm địa chỉ IPv4, subnet mask, default gateway, DNS resolver, thời gian thuê địa chỉ (*lease*) và các tùy chọn khác.

Trong trường hợp client chưa có địa chỉ IPv4 và server có thể phục vụ yêu cầu, quy trình thường được mô tả bằng **DORA**:

| Bước | Thông điệp | Ý nghĩa |
| --- | --- | --- |
| 1 | **DHCPDISCOVER** | Client tìm DHCP server sẵn có |
| 2 | **DHCPOFFER** | Server đề nghị địa chỉ và thông số cấu hình |
| 3 | **DHCPREQUEST** | Client yêu cầu địa chỉ/đề nghị đã chọn |
| 4 | **DHCPACK** | Server xác nhận cấp phát và thời hạn lease |

~~~mermaid
sequenceDiagram
    participant C as DHCP client
    participant S as DHCP server hợp lệ
    C->>S: DHCPDISCOVER
    S-->>C: DHCPOFFER
    C->>S: DHCPREQUEST
    S-->>C: DHCPACK
    Note over C: Cấu hình IPv4, gateway, DNS và lease
~~~

DHCPv4 chủ yếu sử dụng **UDP 67 phía server** và **UDP 68 phía client**. Giai đoạn đầu có thể sử dụng broadcast; trong quá trình gia hạn lease, client và server có thể trao đổi unicast. Nếu có **DHCP relay**, luồng server–relay có thể sử dụng UDP 67 ở hai đầu. Do đó không nên mô tả mọi DHCP packet đều bắt buộc là broadcast hoặc có cùng một cặp cổng nguồn/đích.

Ngoài DORA còn có các thông điệp và tình huống khác:

- **DHCPNAK:** server từ chối yêu cầu hoặc cho biết cấu hình không hợp lệ.
- **DHCPRELEASE:** client thông báo không còn sử dụng lease; điều này có thể ảnh hưởng việc cập nhật binding tùy thiết bị.
- **DHCPDECLINE:** client báo địa chỉ được đề nghị có vấn đề.
- **DHCPINFORM:** client đã có địa chỉ nhưng cần nhận thêm thông tin cấu hình.
- **Gia hạn lease (renew/rebind):** không nhất thiết lặp lại đầy đủ Discover–Offer–Request–ACK.

**Điểm cần nhớ:** một máy có được địa chỉ IP không đủ để chứng minh nó nhận thông số từ DHCP server được phép. DHCP snooping được thiết kế để áp đặt kiểm soát tại đường truy cập trước khi những thông số không đáng tin cậy đến client.

## 3. Rogue DHCP server là gì và nguy hiểm ra sao?

**Rogue DHCP server** là một thiết bị hoặc phần mềm cấp thông số DHCP cho các client trong mạng mà **không được chủ mạng cho phép thực hiện vai trò đó**. Nó có thể xuất hiện do cấu hình nhầm, chẳng hạn người dùng cắm router gia đình có bật DHCP vào mạng văn phòng, hoặc do hành vi cố ý làm sai lệch cấu hình của máy khác.

Một DHCP server trái phép có thể phát:

- Địa chỉ thuộc subnet không phù hợp, khiến client không liên lạc đúng với dịch vụ.
- **Default gateway** không mong muốn, có khả năng làm thay đổi đường đi của traffic.
- **DNS resolver** ngoài chính sách, khiến quá trình phân giải tên bị ảnh hưởng hoặc bị theo dõi trong một số tình huống.
- Các DHCP option khác không phù hợp với yêu cầu quản trị mạng.

Nếu một client chấp nhận cấu hình sai, hệ quả có thể là **mất mạng**, truy cập nhầm dịch vụ hoặc lưu lượng đi qua thành phần không được phê duyệt. Tuy nhiên, một bản ghi DNS/gateway bất thường **không tự chứng minh có tấn công**: cấu hình sai từ thiết bị được phép cũng có thể tạo triệu chứng tương tự.

### 3.1. Vì sao client có thể nhận đề nghị không mong muốn?

Ở giai đoạn khám phá DHCPv4, client thường chưa có thông tin xác thực máy chủ ở cấp ứng dụng. Trong mạng lớp 2 không có kiểm soát bổ sung, các server có thể cùng nghe được Discover và phát Offer. Client có thể xử lý một trong các đề nghị tùy implementation và trạng thái phiên.

DHCP snooping không nhằm “bảo server nào trả lời nhanh nhất”; nó **lọc các thông điệp DHCP theo vị trí nguồn đi vào switch** để các cổng người dùng không được tự đóng vai đường cung cấp DHCP server.

### 3.2. Những mối đe dọa liên quan

| Tình huống | Mục tiêu hoặc hậu quả | DHCP snooping giúp gì? |
| --- | --- | --- |
| Router gia đình phát DHCP vào VLAN nhân viên | Cấp gateway/DNS sai, gián đoạn kết nối | Chặn server-origin DHCP từ cổng không tin cậy |
| Thiết bị cố ý phát Offer/ACK trái phép | Thay cấu hình của client | Giảm khả năng thông điệp server giả đến máy khác |
| Client phát nhiều yêu cầu DHCP không hợp lệ hoặc bất thường | Tăng tải server/switch, có thể làm cạn pool | **Rate limit / kiểm tra** có thể hỗ trợ, nhưng không bảo đảm chặn mọi dạng cạn pool |
| Máy tự đặt IP tĩnh trùng hoặc giả danh host khác | Xung đột, giả mạo IP | DHCP snooping **không tự chặn**; cần IP Source Guard/DAI, NAC hoặc kiểm soát bổ sung |
| Thiết bị gửi quảng bá IPv6 Router Advertisement trái phép | Client IPv6 dùng gateway/prefix không mong muốn | DHCP snooping cho DHCPv4 **không giải quyết**; cần RA Guard và các biện pháp IPv6 tương ứng |

**DHCP snooping là cơ chế giảm rủi ro tại mạng truy cập, không phải hệ thống phát hiện và xử lý mọi hành vi độc hại ở L2/L3.**

## 4. Trusted port và untrusted port

Điểm then chốt của DHCP snooping là phân loại các **cổng ingress** trên switch.

### 4.1. Untrusted port

**Untrusted port** thường là cổng nối tới thiết bị đầu cuối như laptop, máy in, thiết bị IoT hoặc thiết bị khách. Cổng này có thể gửi thông điệp DHCP ở vai trò client theo chính sách, nhưng **không được phép đưa các thông điệp xuất phát từ DHCP server hợp lệ vào mạng** qua cổng đó.

Ví dụ: một DHCPOFFER hoặc DHCPACK đi **vào switch từ cổng access người dùng** có thể bị DHCP snooping loại bỏ. Danh sách thông điệp bị kiểm tra hoặc loại bỏ còn phụ thuộc sản phẩm và cấu hình.

### 4.2. Trusted port

**Trusted port** là cổng được cấu hình cho phép nhận **thông điệp DHCP phía server hoặc đường relay hợp lệ**. Đây có thể là:

- Cổng nối trực tiếp tới DHCP server đã được phê duyệt.
- Uplink tới thiết bị phân phối/router chứa DHCP relay.
- Uplink nhận lưu lượng DHCP server từ mạng hạ tầng theo topology được xác minh.

**Trusted không đồng nghĩa an toàn tuyệt đối.** Nếu một nguồn DHCP giả lọt vào từ chính đường đang được tin cậy, DHCP snooping tại switch đó có thể không ngăn được. Vì vậy chỉ đánh dấu trusted sau khi xác minh đường đi và bảo vệ chính đường uplink.

### 4.3. Tình huống cần cân nhắc kỹ

Một cổng trunk không mặc nhiên phải trusted; cổng access cũng không mặc nhiên untrusted trong mọi hệ thống. Quyết định phải dựa trên **vai trò của thiết bị ở đầu kia, VLAN, hướng thông điệp DHCP và điểm đang thực thi snooping**.

Ví dụ, một trunk nối tới access point có nhiều SSID/VLAN thường mang traffic của client và không nên được cấp quyền DHCP server chỉ vì đó là trunk. Ngược lại, uplink access switch lên tầng phân phối có DHCP relay có thể cần trusted để nhận phản hồi từ server theo thiết kế.

## 5. DHCP snooping hoạt động trên switch như thế nào?

Một mô hình xử lý điển hình:

1. Quản trị viên bật DHCP snooping trên switch và **chỉ định những VLAN cần được bảo vệ**.
2. Phân loại từng cổng liên quan là trusted hoặc untrusted theo đường đi DHCP thực tế.
3. Khi một thông điệp DHCP đi vào switch, thiết bị xét **VLAN, cổng ingress, loại thông điệp và các trường có hỗ trợ kiểm tra**.
4. Thông điệp từ server đi vào **untrusted port** có thể bị loại bỏ và ghi counter/log.
5. Các trao đổi hợp lệ có thể đi tiếp đến DHCP server/relay và quay về client.
6. Switch học thông tin cấp phát hợp lệ, cập nhật bảng **binding**, xử lý thời hạn lease và những thay đổi trạng thái liên quan.

~~~mermaid
flowchart TD
    A["DHCP packet đi vào switch"] --> B{"DHCP snooping bật cho VLAN này?"}
    B -->|Không| N["Theo chính sách chuyển mạch thông thường"]
    B -->|Có| C["Xét ingress port, loại DHCP message và các kiểm tra"]
    C --> D{"Server-origin message trên cổng untrusted?"}
    D -->|Có| X["Drop / counter / log theo hỗ trợ"]
    D -->|Không| E{"Message hợp lệ theo chính sách?"}
    E -->|Không| Y["Drop hoặc xử lý theo cơ chế sản phẩm"]
    E -->|Có| F["Forward theo topology DHCP/relay"]
    F --> G{"Có dữ liệu cấp phát để cập nhật binding?"}
    G -->|Có| H["Tạo/cập nhật IP–MAC–VLAN–Port–Lease"]
    G -->|Không| I["Giữ trạng thái hiện tại hoặc chờ bước khác"]
~~~

Sơ đồ chỉ mô tả **logic khái niệm**. Các loại DHCP message được phân loại ra sao, cách học binding, kiểm tra MAC/chaddr, xử lý Option 82, timeout và nhật ký khác nhau theo dòng thiết bị. Không sử dụng sơ đồ này để suy rằng mọi switch đều có cùng mặc định hoặc thứ tự kiểm tra.

### 5.1. Những gói thường được bảo vệ

DHCP snooping đặc biệt quan tâm thông điệp phía server như **OFFER, ACK và NAK** đi vào từ cổng không được phép. Một số sản phẩm còn kiểm tra **RELEASE, DECLINE, REQUEST**, tính nhất quán giữa MAC ở header Ethernet và thông tin client DHCP, giới hạn tốc độ và sự phù hợp của binding.

**Không được giả định rằng mọi DHCP message từ untrusted port đều bị chặn.** Cổng client phải được phép gửi những yêu cầu DHCP hợp lệ để có thể nhận IP.

### 5.2. DHCP snooping có phụ thuộc VLAN không?

Nhiều switch áp dụng snooping theo **VLAN cụ thể**, kết hợp với trạng thái trust trên interface. Nếu chỉ bật tính năng toàn cục nhưng quên VLAN liên quan, tính năng có thể không bảo vệ lưu lượng thực tế. Ngược lại, bật trên VLAN chưa hiểu đường đi DHCP có thể làm mất khả năng cấp phát địa chỉ.

Khi thiết kế phải kiểm tra **cả bảng VLAN–interface–trust–đường relay/server**, không chỉ xem một dòng cấu hình bật tính năng.

## 6. Ví dụ kiến trúc phòng vệ tại access switch

Giả sử một văn phòng có **VLAN 10** dành cho nhân viên, **VLAN 20** dành cho guest Wi-Fi và **VLAN 30** dành cho IoT. Một DHCP server được phê duyệt nằm ở vùng hạ tầng; DHCP relay ở switch/router tầng phân phối phục vụ những VLAN cần thiết.

~~~mermaid
flowchart TD
    DHCP["DHCP server hợp lệ"] <--> R["Distribution / DHCP relay"]
    R <--> |"Uplink nhận phản hồi DHCP hợp lệ"| SW["Access switch: DHCP snooping VLAN 10/20/30"]
    SW --> |"Untrusted access port"| PC["Máy nhân viên / VLAN 10"]
    SW --> |"Untrusted trunk theo policy"| AP["Wi-Fi AP: SSID Guest / VLAN 20"]
    SW --> |"Untrusted access port"| IOT["IoT / VLAN 30"]
    SW --> |"Untrusted access port"| RG["Router không được phép phát DHCP"]
    RG -. "DHCPOFFER trái phép bị chặn" .-> SW
~~~

Ở switch truy cập này:

| Kết nối | VLAN liên quan | Vai trò | Trust dự kiến |
| --- | --- | --- | --- |
| Uplink về distribution có relay | 10, 20, 30 | Đường nhận thông điệp DHCP server hợp lệ | **Trusted** theo topology được xác nhận |
| Cổng máy nhân viên | 10 | DHCP client | **Untrusted** |
| Cổng AP phục vụ guest | 20 | Chuyển tiếp traffic của client Wi-Fi | **Untrusted** nếu không có chức năng server/relay cần trust |
| Cổng thiết bị IoT | 30 | DHCP client | **Untrusted** |
| Cổng có router gia đình cắm nhầm | 10 | Có thể phát DHCP server trái phép | **Untrusted**; cần ghi nhận và xử lý thiết bị |

Giả sử router ở cổng không đáng tin cậy gửi DHCPOFFER. Switch có thể loại bỏ thông điệp này theo DHCP snooping trước khi những client khác nhận Offer. Trong khi đó, DHCPOFFER từ DHCP server thật đi theo uplink đã khai báo được phép đi đến client.

**Không tự đưa toàn bộ uplink/trunk vào trusted:** nếu uplink dẫn tới một switch truy cập khác có cổng người dùng chưa được bảo vệ, nguy cơ DHCP server trái phép vẫn có thể đi tới từ hướng đó. Cần thiết kế chuỗi trust xuyên suốt từ access đến distribution.

## 7. DHCP snooping binding table

Ngoài việc chặn server trái phép, DHCP snooping có thể ghi nhận ánh xạ giữa địa chỉ IP, MAC và nơi thiết bị kết nối.

Ví dụ một bảng binding **giả lập**:

| VLAN | IPv4 được cấp | Client MAC giả lập | Cổng ingress | Lease còn hiệu lực |
| ---: | --- | --- | --- | --- |
| 10 | 192.0.2.21 | 02:00:00:00:10:21 | Gi1/0/4 | 3.200 giây |
| 10 | 192.0.2.22 | 02:00:00:00:10:22 | Gi1/0/5 | 3.500 giây |
| 20 | 198.51.100.31 | 02:00:00:00:20:31 | Gi1/0/10 | 1.200 giây |
| 30 | 203.0.113.41 | 02:00:00:00:30:41 | Gi1/0/16 | 5.000 giây |

Ba dải **192.0.2.0/24**, **198.51.100.0/24** và **203.0.113.0/24** được dành cho tài liệu minh họa, **không phải dải private IPv4 để áp dụng nguyên xi trong mạng nội bộ**. Khi triển khai thực, sử dụng địa chỉ riêng phù hợp (ví dụ RFC 1918) và chính sách IPAM đã phê duyệt.

### 7.1. Khi nào binding được tạo?

Nhiều thiết bị học binding sau khi quan sát quy trình cấp phát DHCPv4 hợp lệ, đặc biệt từ thông điệp **DHCPACK** qua đường được phép. Chi tiết thời điểm, thông tin client identity, xử lý relay và các trường có trong binding phụ thuộc implementation.

Một binding thường gắn với:

- VLAN hoặc miền L2 nơi client truy cập.
- Cổng/interface nơi client được quan sát.
- IPv4 của client.
- MAC address hoặc thông tin định danh liên quan.
- Thời hạn thuê và loại binding (động hay cấu hình tĩnh, nếu thiết bị hỗ trợ).

### 7.2. Khi binding thay đổi hoặc hết hạn

Khi client gia hạn lease, chuyển cổng, thay VLAN hoặc lease hết hiệu lực, bảng binding cần được cập nhật theo cơ chế sản phẩm. Một số switch cho phép **lưu binding database ra bộ nhớ bền vững** để giảm mất trạng thái sau reboot.

Nếu binding bị mất nhưng client vẫn giữ IP đã được cấp từ trước, **DAI hoặc IP Source Guard phụ thuộc vào binding** có thể chặn nhầm lưu lượng hợp lệ. Vì vậy cần xây dựng phương án khôi phục binding, thời gian học lại, đồng bộ với DHCP lease và xử lý client đang hoạt động khi switch khởi động lại.

### 7.3. Thiết bị dùng IP tĩnh

Thiết bị đặt IP tĩnh **không có lease DHCP** để switch học theo cách thông thường. Nếu áp dụng DAI/IP Source Guard dựa hoàn toàn trên DHCP snooping binding, các máy in, camera, server hoặc gateway dùng IP tĩnh có thể bị mất kết nối.

Có thể cần **binding tĩnh, ARP ACL, chính sách ngoại lệ hoặc phương pháp kiểm soát riêng** tùy thiết bị và vai trò cổng. Mọi ngoại lệ phải giới hạn theo tài sản, được ghi trong IPAM và có người chịu trách nhiệm.

## 8. Liên hệ với Dynamic ARP Inspection và IP Source Guard

DHCP snooping thường được nhắc cùng hai tính năng bảo vệ khác, nhưng **không phải cùng một cơ chế**.

### 8.1. Dynamic ARP Inspection (DAI)

**DAI** kiểm tra một số thông tin trong ARP để hạn chế hành vi giả mạo ánh xạ IP–MAC (*ARP spoofing / ARP poisoning*) trên các VLAN được bảo vệ. Nó có thể đối chiếu thông tin với **DHCP snooping binding table** và, tùy thiết bị, ARP ACL hoặc danh sách tĩnh.

Nếu một client gửi thông điệp ARP khẳng định một địa chỉ IP không phù hợp binding được tin cậy, DAI có thể từ chối và ghi nhận. Nhưng DAI **không tự bảo vệ IPv6 Neighbor Discovery**, vì IPv6 sử dụng giao thức và thông điệp khác.

### 8.2. IP Source Guard

**IP Source Guard** là cơ chế giới hạn lưu lượng nguồn trên một cổng truy cập, thường dựa vào địa chỉ IPv4 và có thể kết hợp MAC/VLAN/binding. Mục tiêu là ngăn máy trên cổng sử dụng địa chỉ nguồn không phù hợp với quyền được ghi nhận.

Đây là bước kiểm soát **sau khi client đã có IP**, khác với việc DHCP snooping chặn Offer từ server giả. Các điều kiện kiểm tra thực tế và khả năng bảo vệ IPv4/IPv6 phụ thuộc nền tảng.

### 8.3. So sánh vai trò

| Cơ chế | Mục tiêu chính | Nguồn thông tin | Lưu ý |
| --- | --- | --- | --- |
| **DHCP snooping** | Chặn DHCP server trái phép và học binding | DHCP message, ingress port, VLAN | Chủ yếu được dùng với DHCPv4 trong mô hình cơ bản |
| **DAI** | Kiểm tra ARP IP–MAC | DHCP bindings hoặc ARP ACL | Cần xử lý địa chỉ tĩnh; không áp dụng trực tiếp cho NDP của IPv6 |
| **IP Source Guard** | Giới hạn IP/MAC nguồn tại cổng | Binding hoặc cấu hình tĩnh | Mất binding có thể làm gián đoạn kết nối |
| **802.1X / NAC** | Kiểm soát danh tính/quyền vào mạng | Danh tính, trạng thái thiết bị, chính sách | Không tự phát hiện mọi DHCP server giả |
| **Firewall/segmentation** | Kiểm soát đường liên VLAN và giữa trust zone | Nguồn, đích, dịch vụ, chính sách | Không tự thay thế lọc DHCP trên mạng lớp 2 |

**Một bộ kiểm soát nhiều lớp** có thể gồm 802.1X/NAC cấp quyền vào VLAN, DHCP snooping bảo vệ cấu hình DHCP, DAI/IP Source Guard hạn chế giả mạo tại cổng và firewall giới hạn luồng đi giữa các vùng.

## 9. DHCP relay, Option 82 và những điểm phải kiểm tra

### 9.1. DHCP relay

DHCP broadcast từ client thường không tự đi qua router đến subnet khác. **DHCP relay** là thành phần nhận yêu cầu tại mạng client rồi chuyển tiếp đến DHCP server ở mạng khác, mang thông tin giúp server nhận diện mạng cần cấp địa chỉ.

Trong DHCPv4, trường **giaddr** có thể được relay dùng để chỉ thông tin mạng/địa chỉ liên quan tới việc chuyển tiếp. Phản hồi của server trở về qua đường relay, rồi được relay chuyển tới client theo cơ chế phù hợp.

**DHCP snooping tại access switch** cần nhận biết uplink nào dẫn tới relay/server hợp lệ. Một gói Offer từ đường relay trên cổng bị đánh dấu untrusted có thể bị chặn, khiến toàn bộ client trong VLAN không nhận IP dù server vẫn hoạt động.

### 9.2. DHCP Option 82

**Option 82 (Relay Agent Information Option)** có thể cung cấp thông tin về vị trí truy cập, ví dụ **circuit ID** hoặc **remote ID**, để server/relay hỗ trợ áp dụng chính sách cấp phát theo cổng hoặc mạng.

Một số switch snooping có thể **chèn Option 82 vào yêu cầu DHCP từ client** rồi đưa đến relay/server. Những thiết bị trung gian có thể kiểm tra, giữ, thay hoặc loại bỏ Option 82 theo chính sách.

Những rủi ro vận hành cần xem:

- Server không chấp nhận hoặc xử lý sai Option 82 làm client không nhận Offer/ACK.
- Switch từ chối request chứa Option 82 trên untrusted port theo hành vi mặc định của một số sản phẩm.
- Nhiều tầng relay/snooping chèn hoặc xử lý Option 82 không nhất quán.
- Ánh xạ Option 82 về circuit/port sai khi thay đổi topology hoặc cấu hình trunk.

**Không mặc định cần bật Option 82 trên mọi switch.** Phải kiểm tra đúng đường relay, chính sách server, thiết bị hỗ trợ và các trường hợp DHCP failover. Một số hệ thống có thể yêu cầu cấu hình riêng cho Option 82 và trạng thái trusted; hãy dùng tài liệu của nền tảng thực tế.

## 10. Giới hạn tốc độ DHCP và bảo vệ trước cạn tài nguyên

Nhiều switch hỗ trợ **DHCP snooping rate limiting** cho các cổng nhất định. Khi số DHCP packet vượt ngưỡng hoặc vi phạm điều kiện, thiết bị có thể loại bỏ lưu lượng, ghi sự kiện hoặc đưa cổng vào trạng thái hạn chế/error-disabled, tùy sản phẩm.

**Mục đích:** giảm tác động của luồng DHCP bất thường từ máy khách và bảo vệ cả switch hoặc DHCP server khỏi một số trường hợp quá tải.

**Không được hiểu rate limiting là bảo đảm chống mọi DHCP starvation.** Kẻ tấn công có thể có nhiều nguồn, nhiều cổng hoặc lưu lượng dưới ngưỡng. Một số thông điệp hợp lệ cũng có thể tăng mạnh khi mất điện và nhiều máy khởi động cùng lúc.

### 10.1. Vì sao ngưỡng không thể đặt tùy ý?

| Cổng hoặc thiết bị | Mẫu lưu lượng | Điểm cần cân nhắc |
| --- | --- | --- |
| Cổng máy đơn lẻ | Ít yêu cầu DHCP trong hoạt động bình thường | Có thể dùng ngưỡng phù hợp theo baseline |
| Cổng IP phone nối tiếp PC | Có thể có nhiều DHCP client hợp lệ | Không coi một port luôn tương đương một máy |
| Cổng access point | Nhiều client Wi-Fi chia sẻ uplink | Ngưỡng thấp có thể làm khách không lấy được IP |
| Trunk giữa switch | Tổng hợp nhiều VLAN/nguồn | Không dùng ngưỡng của cổng máy đơn lẻ |
| Thời điểm khởi động lại cả khu vực | Nhiều client renew/discover cùng lúc | Cần dự phòng đột biến hợp lệ |

Nếu thiết bị có hành vi **err-disable port** khi vượt rate limit, phải có runbook khôi phục và giám sát rõ ràng. Một chính sách quá nhạy có thể làm mất mạng của cả access point hoặc nhiều thiết bị nằm phía sau một cổng.

## 11. Chính sách triển khai trung lập với nhà cung cấp

Đoạn YAML sau mô tả tư duy thiết kế; **không phải lệnh có thể đưa trực tiếp lên Cisco, Juniper, Aruba, Huawei hay bất kỳ switch nào**:

~~~yaml
dhcpSnoopingPolicy:
  name: campus-access-protection
  purpose: prevent-unauthorized-dhcp-service
  enabledVlans: [10, 20, 30]
  interfaces:
    - name: uplink-to-distribution
      role: approved-dhcp-server-or-relay-path
      trust: trusted
      vlans: [10, 20, 30]
    - name: employee-access
      role: client-facing
      trust: untrusted
      vlans: [10]
    - name: guest-access-point
      role: client-traffic-trunk
      trust: untrusted
      vlans: [20]
    - name: iot-access
      role: client-facing
      trust: untrusted
      vlans: [30]
  controls:
    blockUnauthorizedServerReplies: true
    inspectClientIdentifiersWhereSupported: true
    option82: review-relay-and-server-compatibility
    rateLimits: derive-from-port-role-and-baseline
  bindings:
    learnFromApprovedDhcpLeases: true
    retainAcrossRestartIfSupported: true
    manageStaticIpExceptions: true
  observability:
    recordDropsAndViolations: true
    monitorBindingTable: true
    monitorDhcpLeaseSuccess: true
  changeControl:
    requireApproval: true
    verifyRollback: true
    testAllProtectedVlans: true
~~~

Khi chuyển thành cấu hình thiết bị, cần đọc chính xác **mặc định trusted/untrusted**, cách bật theo VLAN, cách phân loại DHCP message, mức giới hạn packet, lưu binding database, chính sách Option 82 và hành vi khi vi phạm. Những đặc tính này **không thống nhất giữa các nhà cung cấp và dòng switch**.

### 11.1. Không làm giảm an toàn để “chữa” lỗi DHCP

Khi người dùng mất IP sau khi bật snooping, **không nên lập tức đánh dấu mọi cổng là trusted**. Việc đó có thể khôi phục lưu lượng nhưng cũng loại bỏ ý nghĩa bảo vệ.

Thay vào đó, kiểm tra đường đi của Offer/ACK hợp lệ, trạng thái trust uplink, VLAN đã bật snooping, giaddr/Option 82 và log drop; chỉ tạo ngoại lệ đúng cổng hoặc đường đi cần thiết.

## 12. Quy trình thiết kế và triển khai DHCP snooping

### Bước 1 – Kiểm kê mạng và trách nhiệm

Liệt kê VLAN, switch access/distribution, DHCP server, DHCP relay, router, AP, DHCP failover, các subnet được cấp phát động và những tài sản dùng IP tĩnh. Ghi chủ sở hữu thay đổi và người liên hệ khi mất dịch vụ.

### Bước 2 – Vẽ đường DHCP thực tế

Với mỗi VLAN, tìm nơi client gửi Discover, cổng nào nhận Offer/ACK, relay nằm ở đâu, DHCP server thuộc zone nào và có đường dự phòng nào. Không suy rằng mọi DHCP server nối trực tiếp với access switch.

### Bước 3 – Xác định trusted và untrusted theo cổng

Trust **chỉ những ingress cần tiếp nhận thông điệp DHCP phía server hợp lệ**. Cổng người dùng, AP chở client, thiết bị IoT và phòng họp thường là untrusted nếu không có nhu cầu server/relay được phê duyệt.

### Bước 4 – Xác định VLAN và phụ thuộc

Chọn VLAN cần bật, kiểm tra trunk, VLAN tagging, link aggregation, private VLAN hoặc những tính năng L2 liên quan. Xác minh DHCP server/relay và chính sách Option 82 có tương thích với cấu hình dự định.

### Bước 5 – Chuẩn bị giám sát và đường khôi phục

Lưu cấu hình, trạng thái trust và bảng binding hiện tại theo phương thức được phép; kiểm tra quyền truy cập out-of-band hoặc kế hoạch rollback nếu một thay đổi làm thiết bị mất IP quản trị.

### Bước 6 – Triển khai thử nghiệm theo phạm vi nhỏ

Bắt đầu ở VLAN và một nhóm cổng được kiểm soát, theo dõi cấp phát mới, gia hạn lease và trạng thái thiết bị có IP tĩnh. Không áp dụng đồng thời các chính sách rate limiting, DAI và IP Source Guard rộng khi chưa xác định nguồn lỗi.

### Bước 7 – Xác minh bằng phép thử tích cực và âm tính

Phải kiểm tra cả **DHCP hợp lệ vẫn hoạt động** và **server trái phép bị chặn** trong một lab tách biệt. Cần có kế hoạch rõ về nguồn log và bằng chứng, tránh làm gián đoạn mạng dùng chung.

### Bước 8 – Mở rộng, ghi nhận ngoại lệ và rà soát

Mở rộng theo access switch/VLAN khi các phép thử đạt. Rà soát trusted interfaces khi thay đổi dây, thay switch, di chuyển relay hoặc thêm AP; giám sát cổng err-disabled, binding quá hạn và dấu hiệu mất khả năng cấp IP.

## 13. Quan sát, log và chỉ số vận hành

DHCP snooping cần được **kiểm chứng bằng trạng thái thực tế**, không chỉ bằng thông báo “feature enabled”.

| Nguồn dữ liệu | Thông tin cần theo dõi | Ý nghĩa |
| --- | --- | --- |
| Switch DHCP snooping counters | Số DHCP message bị drop theo lý do/cổng/VLAN | Nhận diện rogue server hoặc cấu hình chưa phù hợp |
| Trust configuration | Danh sách trusted/untrusted ports, VLAN áp dụng | Phát hiện cổng bị cấp trust ngoài ý muốn |
| Binding table | IP, MAC, port, VLAN, lease, loại binding | Kiểm tra học cấp phát và phụ thuộc của DAI/IPSG |
| DHCP server logs | Discover, Offer, Request, Ack, Nak, lỗi pool | Phân biệt server không nhận request và phản hồi bị switch chặn |
| Relay logs/config | giaddr, Option 82, địa chỉ server chuyển tiếp | Khoanh vùng lỗi nhiều subnet |
| DHCP success metrics | Thời gian lấy IP, tỷ lệ thất bại, lease renewal success | Đánh giá tác động thực tế tới client |
| NAC/Wi-Fi/switch logs | Port migration, AP client count, err-disable | Phân tích thay đổi đầu cuối và false positive |
| ARP/DAI/IPSG violations | IP–MAC không khớp binding | Đánh giá chính sách phụ thuộc có gây lỗi không |

### 13.1. Log giả lập

~~~json
{
  "timestamp": "2026-11-28T14:15:00+07:00",
  "device": "access-switch-lab-01",
  "event": "dhcp_snooping_drop",
  "vlan": 10,
  "ingress_port": "Gi1/0/18",
  "port_trust": "untrusted",
  "dhcp_message_type": "DHCPOFFER",
  "decision": "drop",
  "reason": "server-origin-message-on-untrusted-port",
  "affected_clients_verified": false,
  "data_source": "synthetic-training-event"
}
~~~

Sự kiện này cho biết switch **đã chặn một DHCPOFFER ở cổng untrusted**. Nó chưa đủ kết luận ai cố ý tấn công: đó có thể là router cắm nhầm hoặc một thiết bị nằm sai cổng. Khi xử lý cần đối chiếu vị trí cổng, asset inventory, MAC/LLDP nếu có và người phụ trách.

### 13.2. Mẫu điều tra khi máy không nhận IP

1. Client có link/VLAN đúng và gửi DHCPDISCOVER hay không?
2. DHCP relay hoặc server có nhận yêu cầu không?
3. Server có gửi DHCPOFFER/DHCPACK tới đúng VLAN/relay không?
4. Những phản hồi này đi vào switch qua **cổng trusted** hay bị drop?
5. Option 82 hoặc các kiểm tra MAC/giaddr có gây từ chối không?
6. Có rate limit, err-disable hoặc ACL/firewall chặn UDP 67/68 hoặc liên lạc server–relay không?
7. Binding có được ghi đúng khi ACK hợp lệ không?
8. Client có nhận lease nhưng bị DAI/IP Source Guard hoặc firewall chặn lưu lượng sau đó không?

**Phân biệt hai giai đoạn lỗi:** “client không nhận được cấu hình DHCP” và “client có IP nhưng không truy cập được mạng”. Chúng thường cần dữ liệu ở những lớp khác nhau.

## 14. Kiểm thử DHCP snooping trong lab an toàn

Chỉ kiểm thử với switch/VLAN, DHCP server và máy client **thuộc quyền quản lý và được cấp phép**, tránh đưa DHCP server thực nghiệm vào mạng sản xuất dùng chung.

### 14.1. Sơ đồ lab tối thiểu

- Một switch hỗ trợ DHCP snooping, VLAN thử nghiệm.
- Một DHCP server giả lập **được phép** đi qua cổng trusted.
- Một máy client nhận địa chỉ qua untrusted port.
- Một thiết bị lab thứ hai có khả năng phát DHCP server để kiểm tra kịch bản untrusted trong **mạng cô lập**, không nối tới mạng người dùng thật.
- Một nơi ghi cấu hình, counter và binding table.

Không cần tạo số lượng lớn DHCP request để đánh giá cơ chế chặn rogue server. Chỉ một số giao dịch thử nghiệm được kiểm soát là đủ để xác minh đường đi và policy.

### 14.2. Ma trận test

| Mã | Tình huống | Kỳ vọng |
| --- | --- | --- |
| T-01 | Client ở VLAN đã bật snooping xin lease từ server hợp lệ | Nhận IP, gateway và DNS đúng chính sách |
| T-02 | Client gia hạn lease qua relay/uplink được duyệt | Lease renewal thành công, binding cập nhật phù hợp |
| T-03 | Thiết bị lab phát Offer từ untrusted port trong VLAN cô lập | Offer trái phép bị drop, có counter hoặc log |
| T-04 | Server hợp lệ ở trusted port trả Offer/ACK | Không bị lọc nhầm bởi snooping |
| T-05 | Thiết bị IP tĩnh dùng kết nối có DAI/IPSG | Hoạt động theo binding tĩnh hoặc policy đã được duyệt |
| T-06 | AP thử nghiệm có nhiều client DHCP hợp lệ | Không bị rate limit nhầm làm mất IP |
| T-07 | Lab dùng Option 82 qua DHCP relay | Server chấp nhận, client nhận lease và ghi nhận đúng nguồn |
| T-08 | Switch reboot trong lab có binding persistence | Dữ liệu/khả năng học lại phù hợp kế hoạch; không làm mất mạng kéo dài |
| T-09 | VLAN không nằm trong phạm vi snooping | Hiểu rõ tính năng không bảo vệ VLAN đó; không gọi đây là PASS bảo mật |

Với mỗi ca ghi rõ **thiết bị, port, VLAN, thời điểm, policy version, kết quả cấp IP, counter và ảnh hưởng ngoài mong muốn**.

### 14.3. Cách kết luận

**“Đã bật DHCP snooping”** chỉ là trạng thái cấu hình. **“Phòng vệ hoạt động”** phải có bằng chứng rằng Offer/ACK từ untrusted port bị chặn **và** Offer/ACK từ server được cấp phép vẫn tới client trên các VLAN/cổng được thiết kế. Nếu cần DAI/IPSG, phải xác minh thêm binding và kết nối hợp lệ không bị chặn.

## 15. DHCP snooping, IPv6 và những cơ chế không tương đương

### 15.1. DHCPv4 không đồng nghĩa DHCPv6

DHCPv4 và DHCPv6 khác nhau về thông điệp, cổng UDP, chế độ phát hiện server/relay và cách client sử dụng cấu hình. DHCPv6 thường dùng **UDP 546 (client)** và **UDP 547 (server/relay)**. Một tính năng ghi tên **DHCP snooping** trên switch có thể chỉ hỗ trợ DHCPv4 hoặc có năng lực DHCPv6 riêng.

**Không giả định bật DHCPv4 snooping thì DHCPv6 cũng được bảo vệ.** Cần kiểm tra danh sách tính năng DHCPv6 Guard/Snooping trên sản phẩm và các cổng hợp lệ.

### 15.2. Router Advertisement trong IPv6

Với IPv6, client thường nhận thông tin prefix/default router qua **Router Advertisement (RA)** thuộc ICMPv6, trong nhiều môi trường qua **SLAAC**. Một thiết bị phát RA trái phép có thể gây rủi ro khác với rogue DHCPv4.

Các biện pháp phù hợp có thể gồm **RA Guard**, DHCPv6 Guard, kiểm soát NDP hoặc xác thực thiết bị mạng theo năng lực nền tảng. **DHCPv4 snooping không tự chặn RA giả**.

### 15.3. Địa chỉ IPv6 privacy và địa chỉ tĩnh

IPv6 có thể dùng SLAAC, DHCPv6 hoặc địa chỉ cấu hình tĩnh tùy chính sách. Do đó không thể dùng bảng DHCPv4 binding làm nguồn chân lý cho mọi ánh xạ IPv6 của máy.

## 16. DHCP snooping trong Wi-Fi, VPN, cloud và mạng lai

### 16.1. Wi-Fi và access point

Nhiều client Wi-Fi có thể đi vào switch qua **một uplink AP**. Khi đó một cổng vật lý có thể đại diện hàng chục thiết bị, sử dụng cùng hoặc nhiều VLAN. Cần:

- Xác định nơi DHCP broadcast/relay thực sự đi qua (AP bridge, controller hay tunnel).
- Đặt trust theo **vai trò port và đường server**, không mặc nhiên tin toàn bộ AP.
- Đo rate limit với số lượng client thực tế và những thời điểm đồng loạt renew.
- Kiểm tra client isolation, VLAN mapping, 802.1X/NAC và hệ thống log Wi-Fi.

Nếu AP tunnel traffic về wireless controller, DHCP snooping tại access switch nối AP có thể **không quan sát được DHCP của client ở dạng đã giải mã**. Cần đặt kiểm soát ở điểm traffic đi ra từ tunnel hoặc dùng tính năng tương ứng trên controller.

### 16.2. VPN

Nhiều VPN cấp cấu hình địa chỉ bằng cơ chế riêng, không phải một chuỗi DHCPv4 broadcast đi qua access switch. Vì vậy DHCP snooping tại mạng LAN **không tự bảo vệ toàn bộ việc cấp IP cho người dùng VPN**. Phải xem VPN gateway, pool địa chỉ, phân quyền truy cập, DNS được cấp và log phiên.

### 16.3. Cloud VPC/VNet

Trong cloud, DHCP hoặc chức năng cấp địa chỉ có thể do hạ tầng của nhà cung cấp quản lý; người dùng không nhất thiết có quyền cấu hình trust port như trên switch vật lý. Không nên suy rằng cloud security group, network ACL hoặc subnet tương đương với DHCP snooping trên mạng truy cập.

Biện pháp bảo vệ cần tùy vào mô hình cloud: DHCP options, route table, network policy, IAM, log cấp phát địa chỉ, các chức năng kiểm soát source/destination được nhà cung cấp hỗ trợ.

### 16.4. IP Address Management (IPAM)

**IPAM** quản lý dải địa chỉ, subnet, reservation, lịch sử phân bổ và chủ sở hữu tài sản. DHCP snooping **quan sát và kiểm soát thông điệp DHCP trên đường mạng**, không thay thế cơ sở dữ liệu IPAM.

Khi điều tra một binding, nên đối chiếu địa chỉ IP với DHCP lease, thông tin switch port, VLAN và IPAM để tránh nhận nhầm tài sản. Bản ghi IPAM có thể chưa cập nhật kịp hoặc chỉ thể hiện quyền sử dụng dự kiến; không nên xem một nguồn duy nhất là bằng chứng tuyệt đối về danh tính thiết bị.

## 17. Tình huống phân tích: sau khi bật snooping, máy không nhận được IP

Một doanh nghiệp bật DHCP snooping cho **VLAN 10** trên access switch. Sau thay đổi, nhiều máy nhân viên báo không lấy được địa chỉ. Quản trị viên thấy DHCP server vẫn nhận yêu cầu từ relay và gửi Offer.

### 17.1. Những giả thuyết hợp lý

- Uplink từ switch truy cập tới distribution/relay đang bị đặt **untrusted**, nên Offer/ACK hợp lệ bị drop.
- Snooping chưa bật đúng VLAN hoặc trust áp dụng ở sai interface/trunk.
- Switch chèn Option 82 nhưng DHCP server/relay không chấp nhận định dạng hoặc chính sách mới.
- Rate limiting được áp dụng nhầm cho uplink hoặc AP, khiến packet hợp lệ bị loại bỏ.
- Firewall/ACL hoặc cấu hình relay/giaddr đã thay đổi cùng thời điểm, không phải nguyên nhân từ snooping.

### 17.2. Cách điều tra có cấu trúc

1. Xác định client bị ảnh hưởng có cùng VLAN và access switch không.
2. So sánh thời điểm bật snooping với thời điểm lỗi bắt đầu.
3. Kiểm tra counter drop, lý do, cổng ingress và loại DHCP message.
4. Đối chiếu **sơ đồ đường đi thực** từ server/relay tới access switch và client.
5. Kiểm tra Option 82, giới hạn tốc độ và trạng thái port.
6. Thử lại một client lab qua chính đường đã sửa; xem Offer/ACK và binding.
7. Kiểm tra kết nối sau cấp IP, đặc biệt nếu DAI/IP Source Guard cũng đang được bật.

### 17.3. Kết luận có căn cứ

Nếu log cho thấy DHCPACK từ relay đi vào uplink bị từ chối do untrusted port, đó là bằng chứng cụ thể của **lỗi phân loại trust trên đường server hợp lệ**. Giải pháp là điều chỉnh **đúng cổng uplink được phê duyệt**, không mở toàn bộ cổng người dùng thành trusted.

Sau thay đổi phải xác minh cả hai vế: **client hợp lệ nhận IP** và **DHCPOFFER từ cổng client không được phép vẫn bị chặn**. Một thay đổi làm DHCP hoạt động nhưng cho phép rogue server đi qua không đạt mục tiêu bảo mật.

## 18. Sai lầm thường gặp và cách phòng tránh

| Sai lầm | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Chỉ bật tính năng toàn cục, quên VLAN | VLAN mục tiêu không được bảo vệ | Kiểm tra phạm vi VLAN thực thi |
| Đánh dấu tất cả trunk là trusted | Có đường DHCP server trái phép được tin cậy | Dựa trên topology DHCP, không dựa riêng loại cổng |
| Giữ uplink server/relay là untrusted | Client không nhận Offer/ACK | Xác định ingress server hợp lệ và trust đúng cổng |
| Không kiểm tra Option 82 | DHCP bị drop hoặc cấp sai chính sách | Phối hợp switch, relay, server trước triển khai |
| Rate limit như cổng PC trên uplink AP | Nhiều client Wi-Fi bị mất IP | Đo baseline theo vai trò và số client |
| Chỉ chặn rogue DHCP rồi cho rằng đã ngăn IP spoofing | Máy vẫn có thể dùng địa chỉ giả tĩnh | Xem xét DAI, IP Source Guard, NAC và policy khác |
| Bật DAI/IPSG không xử lý IP tĩnh | Máy in, camera, server không còn kết nối | Thiết lập binding/exception tĩnh có kiểm soát |
| Không lưu/khôi phục binding | Reboot switch gây chặn nhầm traffic hợp lệ | Thiết kế persistence và quy trình học lại |
| Nhầm DHCPv4 snooping với bảo vệ IPv6 | Rogue RA/DHCPv6 không được kiểm soát | Dùng RA Guard/DHCPv6 protection tương ứng |
| Chỉ kiểm tra client nhận IP | Không biết rogue Offer có bị chặn không | Bổ sung negative test trong VLAN lab cô lập |
| Gắn nhãn cố ý tấn công từ một DHCP drop | Điều tra sai người/tài sản | Đối chiếu port, asset, log và bối cảnh |
| Không rà soát sau đổi topology | Cổng trusted không còn đúng vai trò | Quản lý thay đổi và kiểm tra trust định kỳ |

## 19. Câu hỏi và bài tập tự kiểm tra

### Câu hỏi 1

Vì sao DHCPOFFER từ một access port của người dùng thường nên bị chặn, trong khi DHCPDISCOVER từ cùng port cần được cho phép?

**Gợi ý:** Discover là yêu cầu của client; Offer là phản hồi ở vai trò server. Client cần xin IP, nhưng không được tự cấp cấu hình cho máy khác.

### Câu hỏi 2

Trusted port có phải cổng “đã xác thực 802.1X” hoặc “được phép đi tới mọi VLAN” không?

**Gợi ý:** Không. Trust ở đây mô tả vai trò cổng với **thông điệp DHCP**; quyền vào mạng và định tuyến giữa zone là kiểm soát khác.

### Câu hỏi 3

Một máy có IP tĩnh nhưng không có DHCP snooping binding. Vì sao nó có thể bị DAI hoặc IP Source Guard chặn?

**Gợi ý:** chính sách phụ thuộc binding có thể không có ánh xạ phù hợp; cần cách khai báo tài sản tĩnh theo khả năng nền tảng.

### Câu hỏi 4

Sau khi chuyển DHCP relay sang switch tầng phân phối mới, nhiều client không nhận IP. Bạn sẽ kiểm tra gì trước khi tắt DHCP snooping?

**Gợi ý:** tuyến Offer/ACK, trust uplink, VLAN, Option 82, giaddr, rate limit và counter drop.

### Câu hỏi 5

Vì sao một cổng AP có thể cần ngưỡng rate limit khác cổng PC?

**Gợi ý:** nhiều client Wi-Fi chia sẻ một cổng và có thể đồng thời nhận/gia hạn lease.

### Câu hỏi 6

DHCP snooping cho DHCPv4 có giúp ngăn một thiết bị phát IPv6 Router Advertisement trái phép không?

**Gợi ý:** Không. RA là ICMPv6; cần RA Guard hoặc các cơ chế IPv6 phù hợp.

### Câu hỏi 7

DHCP snooping có thay thế IPAM, firewall và NAC không?

**Gợi ý:** Không. Snooping kiểm soát luồng DHCP, IPAM quản trị tài nguyên địa chỉ, firewall giới hạn luồng giữa zone và NAC kiểm soát quyền vào mạng.

### Bài tập thiết kế trên giấy

Một văn phòng có ba VLAN **10 (Employees), 20 (Guest Wi-Fi), 30 (IoT)**, một DHCP relay ở distribution, một DHCP server thuộc vùng hạ tầng và hai access switch. Hãy:

1. Vẽ DORA từ một client ở VLAN 10 tới relay/server và trở lại.
2. Đánh dấu trusted/untrusted cho uplink, cổng PC, cổng AP và cổng IoT kèm giải thích.
3. Liệt kê các VLAN được bật DHCP snooping trên mỗi switch.
4. Thiết kế ít nhất **bốn phép thử**: client hợp lệ, renew, rogue Offer ở lab và một kiểm tra với IP tĩnh/DAI.
5. Mô tả bảng binding tối thiểu cần ghi và cách đồng bộ với IPAM.
6. Xác định cách xử lý Option 82, rate limit, đường dự phòng và khôi phục sau reboot.
7. Giải thích vì sao RA Guard/DHCPv6 protection vẫn cần nếu doanh nghiệp dùng IPv6.

**Tiêu chí đạt:** client được phép nhận địa chỉ và cấu hình chính xác; thông điệp DHCP server từ cổng không được phép bị chặn; mọi ngoại lệ và đường DHCP hợp lệ được ghi nhận, kiểm thử và quản lý.

## 20. Những điều cần ghi nhớ

- **DHCP snooping bảo vệ quá trình cấp phát DHCP trên mạng truy cập**, đặc biệt bằng cách chặn thông điệp DHCP server trái phép đi vào từ untrusted port.
- **Trusted/untrusted là vai trò cổng trong chính sách DHCP**, không phải giấy phép cho mọi traffic hoặc bằng chứng danh tính thiết bị.
- **Phải bật tính năng đúng VLAN, đúng đường server/relay**, đồng thời kiểm tra trunk, Option 82, giaddr và những uplink dự phòng.
- **DHCP snooping binding table ghi ánh xạ IP–MAC–VLAN–port–lease** và có thể làm nền cho DAI/IP Source Guard; cần xử lý IP tĩnh và tình trạng mất binding.
- **Rate limit phải dựa vào loại cổng và lượng client hợp lệ**, đặc biệt tại AP/trunk, để tránh tự gây gián đoạn.
- **DHCPv4 snooping không tự bảo vệ DHCPv6, Router Advertisement hoặc tất cả hình thức giả mạo IP**; kết hợp kiểm soát IPv6, NAC, firewall và phân đoạn mạng.
- **Kiểm thử cả luồng hợp lệ lẫn luồng rogue trong lab cô lập**, theo dõi log drop, tỷ lệ lấy IP, bảng binding và hiệu ứng tới người dùng.
- **An toàn và tính sẵn sàng phải đi cùng nhau:** đừng giải quyết lỗi cấp phát bằng cách đặt tất cả cổng thành trusted.
